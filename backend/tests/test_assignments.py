"""老师布置作业：作业锁定智能体设置、学生开始作业、班级隔离、老师查看完成情况与对话。"""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from agent import agent as agent_mod
from api.db import Assignment, engine
from api.main import app
from tests.test_agent_modes import chat, scripted
from tests.test_auth import auth_on, login_admin, new_client, register  # noqa: F401  复用登录夹具


def _cleanup():
    with Session(engine()) as s:
        for a in s.exec(select(Assignment)).all():
            s.delete(a)
        s.commit()


def test_assignment_needs_login():
    with TestClient(app) as c:
        assert c.get("/api/assignments").status_code == 400


def test_assignment_flow(auth_on, monkeypatch):  # noqa: F811
    with new_client() as adm, new_client() as tea, new_client() as stu, new_client() as other:
        login_admin(adm)
        adm.put("/api/auth/teacher-invite", json={"code": "teach-2027", "enabled": True})
        register(tea, "王老师", invite="teach-2027", role="teacher")
        room = tea.post("/api/classes", json={"name": "量化一班"}).json()
        register(stu, "一班学生", invite=room["invite_code"])
        register(other, "默认班学生")

        a = tea.post(f"/api/classes/{room['id']}/assignments", json={
            "title": "双均线参数实验", "task": "只用双均线策略，比较两组均线周期", "due": "2026-12-01",
            "control": {"mode": "auto", "strategies": ["dual_ma_stock"], "max_backtests": 3}}).json()
        assert a["control"]["strategies"] == ["dual_ma_stock"] and a["control"]["max_backtests"] == 3
        assert stu.post(f"/api/classes/{room['id']}/assignments", json={"title": "x"}).status_code == 403

        mine = stu.get("/api/assignments").json()
        assert [x["title"] for x in mine] == ["双均线参数实验"] and mine[0]["mine"] is None
        assert other.get("/api/assignments").json() == []  # 别的班看不到
        assert other.post(f"/api/assignments/{a['id']}/start").status_code == 404
        sid = stu.post(f"/api/assignments/{a['id']}/start").json()["session_id"]
        assert stu.post(f"/api/assignments/{a['id']}/start").json()["session_id"] == sid  # 继续同一个对话
        assert stu.get(f"/api/chat/sessions/{sid}").json()["assignment"]["title"] == "双均线参数实验"

        # 学生在自己的控制面板里放开了限制，但作业对话仍按老师锁定的设置执行
        monkeypatch.setattr(agent_mod, "stream_chat", scripted([
            ("", [("get_strategy", {"strategy": "海龟"}), ("get_strategy", {"strategy": "双均线"})]),
            ("好的。", []),
        ]))
        ev = chat(stu, "试试海龟", {"mode": "auto", "strategies": None}, sid)
        ends = [e for e in ev if e["type"] == "tool_end"]
        assert not ends[0]["ok"] and "不在学生允许" in ends[0]["error"] and ends[1]["ok"]

        d = tea.get(f"/api/assignments/{a['id']}").json()
        row = next(r for r in d["rows"] if r["display_name"] == "一班学生")
        assert row["session_id"] == sid and row["questions"] == 1
        view = tea.get(f"/api/assignments/{a['id']}/sessions/{sid}").json()
        assert view["student"] == "一班学生" and [m["role"] for m in view["messages"]] == ["user", "assistant"]
        lst = tea.get("/api/assignments").json()
        assert lst[0]["students"] == 1 and lst[0]["started"] == 1
        assert stu.get(f"/api/assignments/{a['id']}").status_code == 403  # 学生不能看全班完成情况

        assert tea.delete(f"/api/assignments/{a['id']}").json() == {"ok": True}
        assert stu.get(f"/api/chat/sessions/{sid}").json()["assignment"] is None  # 对话保留，只是解除绑定
    _cleanup()


def test_experiment_report_docx(monkeypatch):
    import io
    import zipfile
    with TestClient(app) as c:
        monkeypatch.setattr(agent_mod, "stream_chat", scripted([
            ("", [("run_backtest", {"strategy": "dual_ma_stock", "start": "2023-01-01", "end": "2023-12-31"})]),
            ("## 结论\n- **回撤**较小\n\n| 指标 | 数值 |\n|---|---|\n| 夏普 | 0.5 |", []),
        ]))
        sid = chat(c, "回测双均线 2023 年")[0]["session_id"]
        r = c.get(f"/api/chat/sessions/{sid}/report")
        assert r.status_code == 200 and "wordprocessingml" in r.headers["content-type"]
        xml = zipfile.ZipFile(io.BytesIO(r.content)).read("word/document.xml").decode()
        for text in ("量化策略实验报告", "回测双均线 2023 年", "执行回测", "回测结果", "我的结论", "不构成任何投资建议"):
            assert text in xml, text
        assert c.get("/api/chat/sessions/nope/report").status_code == 404
