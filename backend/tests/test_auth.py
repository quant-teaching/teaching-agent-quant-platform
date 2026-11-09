"""账号与班级：注册（学生凭班级邀请码、老师凭教师注册码）、登录与会话、班级隔离、老师管理班级和学生、
批量导入、管理员管理账号、防暴力猜测。"""

import base64

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from api import auth
from api.db import AppSetting, ChatSession, ClassRoom, User, engine
from api.main import app
from api.settings import get_settings

PERIOD = {"start": "2023-01-01", "end": "2023-12-31"}


@pytest.fixture()
def auth_on(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "auth_enabled", True)
    monkeypatch.setattr(st, "invite_code", "class-2026")  # 旧版本的全局邀请码 → 迁移为「默认班级」
    monkeypatch.setattr(st, "teacher_invite_code", "")
    monkeypatch.setattr(st, "admin_username", "teacher")
    monkeypatch.setattr(st, "admin_password", "Teacher-pass-1")
    auth._fails.clear()
    yield
    with Session(engine()) as s:  # 每个测试用干净的班级与设置，避免互相影响
        for row in s.exec(select(ClassRoom)).all():
            s.delete(row)
        gone = [u.id for u in s.exec(select(User).where(User.role != "admin")).all()]
        for u in s.exec(select(User).where(User.role != "admin")).all():  # 测试中注册的学生和老师
            s.delete(u)
        from api.db import Assignment
        for row in s.exec(select(ChatSession).where(ChatSession.user_id.in_(gone or [-1]))).all():  # 防止 id 复用后串号
            s.delete(row)
        for row in s.exec(select(Assignment)).all():
            s.delete(row)
        from api.db import DerivedStrategy, InviteCode, ModelUsage
        for row in s.exec(select(DerivedStrategy).where(DerivedStrategy.user_id != None)).all():  # noqa: E711
            s.delete(row)
        for model in (InviteCode, ModelUsage):
            for row in s.exec(select(model)).all():
                s.delete(row)
        for key in (auth.INVITE_KEY, auth.TEACHER_INVITE_KEY, "quota.defaults"):
            row = s.get(AppSetting, key)
            if row:
                s.delete(row)
        s.commit()


def new_client():
    return TestClient(app)


def register(c, username, password="abc12345", invite="class-2026", role="student"):
    return c.post("/api/auth/register", json={"username": username, "password": password, "invite_code": invite,
                                              "role": role})


def login_admin(c):
    r = c.post("/api/auth/login", json={"username": "teacher", "password": "Teacher-pass-1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"


def test_login_required_and_registration(auth_on):
    with new_client() as c:
        me = c.get("/api/auth/me").json()
        assert me == {"enabled": True, "user": None, "registration": True,
                      "registration_modes": {"student": True, "teacher": False}}
        assert c.get("/api/strategies").status_code == 401
        assert c.get("/api/health").status_code == 200
        assert c.get("/").status_code == 200  # 登录页本身不需要登录

        assert register(c, "学生甲", invite="wrong").json()["detail"] == "班级邀请码不正确或已被使用"
        assert "字母和数字" in register(c, "学生甲", password="abcdefgh").json()["detail"]
        assert "8 到 64" in register(c, "学生甲", password="a1").json()["detail"]
        assert "用户名" in register(c, "a").json()["detail"]
        assert register(c, "想当老师", role="teacher").json()["detail"] == "当前未开放老师注册，请联系平台管理员"
        r = register(c, "学生甲")
        u = r.json()["user"]
        assert r.status_code == 200 and u["role"] == "student" and u["class_name"] == "默认班级"
        cookie = r.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert c.get("/api/auth/me").json()["user"]["username"] == "学生甲"
        assert c.get("/api/strategies").status_code == 200
        assert register(new_client(), "学生甲").json()["detail"] == "这个用户名已经被注册了"

        c.post("/api/auth/logout")
        assert c.get("/api/strategies").status_code == 401


def test_registration_closed_when_class_closed(auth_on):
    with new_client() as adm:
        login_admin(adm)
        (room,) = adm.get("/api/classes").json()
        adm.patch(f"/api/classes/{room['id']}", json={"registration_open": False})
        assert new_client().get("/api/auth/me").json()["registration"] is False
        r = register(new_client(), "路人")
        assert r.status_code == 403 and "未开放注册" in r.json()["detail"]


def test_data_isolated_between_users_and_classes(auth_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "teacher_invite_code", "teach-2026")
    with new_client() as a, new_client() as b, new_client() as t2, new_client() as other:
        register(a, "隔离甲")
        register(b, "隔离乙")  # 同班同学
        register(t2, "二班老师", invite="teach-2026", role="teacher")
        room2 = t2.post("/api/classes", json={"name": "二班"}).json()
        register(other, "二班学生", invite=room2["invite_code"])

        rid = a.post("/api/backtests", json={"strategy": "dual_ma_stock", "config": PERIOD}).json()["id"]
        assert [r["id"] for r in a.get("/api/backtests").json()] == [rid]
        assert b.get("/api/backtests").json() == []
        assert b.delete(f"/api/backtests/{rid}").status_code == 404  # 不能删别人的记录
        assert b.get(f"/api/backtests/{rid}").status_code == 200  # 同班同学可以打开分享的报告
        assert other.get(f"/api/backtests/{rid}").status_code == 404  # 其他班级看不到
        assert other.get(f"/api/backtests/{rid}/export").status_code == 404
        assert t2.get(f"/api/backtests/{rid}").status_code == 404  # 别的班的老师也看不到

        uid_a = a.get("/api/auth/me").json()["user"]["id"]
        with Session(engine()) as s:
            s.add(ChatSession(id="sess_of_a", title="甲的对话", user_id=uid_a))
            s.commit()
        assert [x["id"] for x in a.get("/api/chat/sessions").json()] == ["sess_of_a"]
        assert b.get("/api/chat/sessions").json() == []
        assert b.get("/api/chat/sessions/sess_of_a").status_code == 404
        assert b.delete("/api/chat/sessions/sess_of_a").status_code == 404

        # 衍生策略只对创建者可见
        d = a.post("/api/strategies/derived", json={"base": "dual_ma_stock", "name": "甲的慢均线", "params": {"slow": 60}})
        assert d.status_code == 200
        assert any(x["name"] == "甲的慢均线" for x in a.get("/api/strategies").json())
        assert not any(x["name"] == "甲的慢均线" for x in b.get("/api/strategies").json())


def test_only_admin_changes_model_settings(auth_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "teacher_invite_code", "teach-2026")
    with new_client() as stu, new_client() as tea, new_client() as adm:
        register(stu, "普通学生")
        register(tea, "某老师", invite="teach-2026", role="teacher")
        body = {"name": "x", "base_url": "https://x.example.com", "api_key": "sk-xxxxxxxxxxxx"}
        for c in (stu, tea):
            assert c.get("/api/llm/lock").json() == {"locked": True, "mode": "role"}
            assert c.post("/api/llm/providers", json=body).status_code == 403
            assert all(x["api_key_masked"] in ("已设置", "") for x in c.get("/api/llm/providers").json())
        assert stu.get("/api/users").status_code == 403  # 学生不能管理账号
        assert stu.get("/api/classes").status_code == 403

        login_admin(adm)
        assert adm.get("/api/llm/lock").json() == {"locked": False, "mode": "role"}
        pid = adm.post("/api/llm/providers", json=body).json()["id"]
        adm.delete(f"/api/llm/providers/{pid}")


def test_teacher_manages_own_classes_and_students(auth_on, monkeypatch):
    with new_client() as adm, new_client() as tea, new_client() as stu:
        login_admin(adm)
        r = adm.put("/api/auth/teacher-invite", json={"code": "teach-2027", "enabled": True})
        assert r.json() == {"code": "teach-2027", "enabled": True, "source": "db"}
        assert new_client().get("/api/auth/me").json()["registration_modes"] == {"student": True, "teacher": True}
        assert register(new_client(), "冒充老师", invite="class-2026", role="teacher").json()["detail"] == "教师注册码不正确或已被使用"
        u = register(tea, "王老师", invite="teach-2027", role="teacher").json()["user"]
        assert u["role"] == "teacher" and u["class_id"] is None

        # 老师建班，学生凭班级邀请码进班
        room = tea.post("/api/classes", json={"name": "量化一班", "description": "周三下午"}).json()
        assert room["teacher_name"] == "王老师" and room["invite_code"].startswith("class-")
        assert register(stu, "一班学生", invite=room["invite_code"]).json()["user"]["class_name"] == "量化一班"
        register(new_client(), "默认班学生")  # 默认班级（管理员的班）

        # 老师只看得到自己的班级和学生
        assert [c["name"] for c in tea.get("/api/classes").json()] == ["量化一班"]
        assert {c["name"] for c in adm.get("/api/classes").json()} == {"默认班级", "量化一班"}
        users = tea.get("/api/users").json()
        assert [x["username"] for x in users] == ["一班学生"]
        sid = users[0]["id"]
        other = next(x for x in adm.get("/api/users", params={"q": "默认班学生"}).json())
        assert tea.patch(f"/api/users/{other['id']}", json={"display_name": "x"}).status_code == 404
        default_id = next(c["id"] for c in adm.get("/api/classes").json() if c["name"] == "默认班级")
        assert tea.patch(f"/api/classes/{default_id}", json={"name": "抢班"}).status_code == 404

        # 新建、改名、重置密码、停用、删除
        created = tea.post("/api/users", json={"username": "手动建的", "display_name": "赵六", "class_id": room["id"]}).json()
        pw = created["initial_password"]
        assert len(pw) == 8 and new_client().post("/api/auth/login", json={"username": "手动建的", "password": pw}).status_code == 200
        assert tea.post("/api/users", json={"username": "想建老师", "role": "teacher"}).status_code == 403
        assert tea.patch(f"/api/users/{sid}", json={"display_name": "小明"}).json()["display_name"] == "小明"
        new_pw = tea.post(f"/api/users/{sid}/reset-password", json={}).json()["password"]
        assert stu.get("/api/strategies").status_code == 401  # 重置后原会话失效
        assert new_client().post("/api/auth/login", json={"username": "一班学生", "password": new_pw}).status_code == 200
        assert tea.patch(f"/api/users/{sid}", json={"disabled": True}).json()["disabled"] is True
        r = new_client().post("/api/auth/login", json={"username": "一班学生", "password": new_pw})
        assert r.status_code == 403 and "停用" in r.json()["detail"]

        # 班级可视化统计、关闭注册、换邀请码、删除班级
        stats = tea.get("/api/classes").json()[0]
        assert stats["student_count"] == 2 and stats["disabled_count"] == 1
        act = tea.get(f"/api/classes/{room['id']}/activity").json()
        assert len(act["dates"]) == 30 and len(act["backtests"]) == 30
        old_code = room["invite_code"]
        assert tea.post(f"/api/classes/{room['id']}/regenerate-code").json()["invite_code"] != old_code
        assert register(new_client(), "旧码学生", invite=old_code).json()["detail"] == "班级邀请码不正确或已被使用"
        assert tea.delete(f"/api/classes/{room['id']}").status_code == 400  # 还有学生
        assert tea.delete(f"/api/users/{sid}").json() == {"ok": True}
        assert tea.delete(f"/api/users/{created['id']}").json() == {"ok": True}
        assert tea.delete(f"/api/classes/{room['id']}").json() == {"ok": True}


def test_import_students_from_csv_and_xlsx(auth_on):
    with new_client() as adm:
        login_admin(adm)
        room = adm.post("/api/classes", json={"name": "导入班"}).json()
        tpl = adm.get("/api/users/import-template")
        assert tpl.status_code == 200 and tpl.content.startswith(b"\xef\xbb\xbf") and "用户名" in tpl.content.decode("utf-8-sig")

        csv_text = "用户名,姓名,初始密码\nimp_ok1,甲,\nimp_ok2,乙,goodpass9\nimp_ok1,重复,\nimp_bad,丙,123\nx,太短,\n"
        content = base64.b64encode(csv_text.encode("gbk")).decode()  # Excel 另存的 CSV 常是 GBK
        prev = adm.post(f"/api/classes/{room['id']}/import", json={"filename": "名单.csv", "content": content}).json()
        assert (prev["total"], prev["valid"], prev["created"]) == (5, 2, False)
        errors = {x["row"]: x["error"] for x in prev["rows"] if x["error"]}
        assert errors[4] == "与表格中前面的行重复" and "8 到 64" in errors[5] and "用户名" in errors[6]
        assert not any(u["username"] == "imp_ok1" for u in adm.get("/api/users").json())  # 预览不建号

        done = adm.post(f"/api/classes/{room['id']}/import",
                        json={"filename": "名单.csv", "content": content, "dry_run": False}).json()
        made = {x["username"]: x["password"] for x in done["rows"] if not x["error"]}
        assert done["created"] and made["imp_ok2"] == "goodpass9" and len(made["imp_ok1"]) == 8
        r = new_client().post("/api/auth/login", json={"username": "imp_ok1", "password": made["imp_ok1"]})
        assert r.status_code == 200 and r.json()["user"]["class_name"] == "导入班"

        # Excel（.xlsx）同样可以导入
        from io import BytesIO

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["用户名", "姓名", "初始密码"])
        ws.append(["imp_xlsx", "丁", None])
        buf = BytesIO()
        wb.save(buf)
        x = adm.post(f"/api/classes/{room['id']}/import", json={
            "filename": "名单.xlsx", "content": base64.b64encode(buf.getvalue()).decode(), "dry_run": False}).json()
        assert x["valid"] == 1 and x["rows"][0]["username"] == "imp_xlsx"
        bad = adm.post(f"/api/classes/{room['id']}/import", json={
            "filename": "名单.csv", "content": base64.b64encode("姓名\n甲\n".encode()).decode()})
        assert bad.status_code == 400 and "用户名" in bad.json()["detail"]
        with Session(engine()) as s:  # 清理，避免影响其他测试
            for u in s.exec(select(User).where(User.username.startswith("imp_"))).all():
                s.delete(u)
            s.commit()


def test_admin_manages_all_accounts(auth_on):
    with new_client() as adm:
        login_admin(adm)
        t = adm.post("/api/users", json={"username": "新老师", "role": "teacher", "password": "teach1234"}).json()
        assert t["role"] == "teacher" and t["initial_password"] == "teach1234"
        assert adm.post("/api/users", json={"username": "无班学生", "role": "student"}).status_code == 400
        room = adm.post("/api/classes", json={"name": "转交班", "teacher_id": t["id"]}).json()
        assert room["teacher_name"] == "新老师"
        assert adm.delete(f"/api/users/{t['id']}").status_code == 400  # 还负责班级
        me = adm.get("/api/auth/me").json()["user"]
        assert adm.patch(f"/api/classes/{room['id']}", json={"teacher_id": me["id"]}).json()["teacher_id"] == me["id"]
        assert adm.patch(f"/api/users/{t['id']}", json={"role": "student"}).status_code == 400  # 学生必须有班级
        assert adm.patch(f"/api/users/{me['id']}", json={"role": "student"}).status_code == 400  # 不能改自己的角色
        assert adm.delete(f"/api/users/{t['id']}").json() == {"ok": True}
        roles = {u["role"] for u in adm.get("/api/users").json()}
        assert "admin" in roles


def test_login_lockout_and_password_change(auth_on):
    with new_client() as c:
        register(c, "改密学生")
        c.post("/api/auth/logout")
        for _ in range(auth.MAX_FAILS):
            assert c.post("/api/auth/login", json={"username": "改密学生", "password": "wrong"}).status_code == 401
        r = c.post("/api/auth/login", json={"username": "改密学生", "password": "abc12345"})
        assert r.status_code == 429 and "分钟后再试" in r.json()["detail"]
        auth._fails.clear()

        assert c.post("/api/auth/login", json={"username": "改密学生", "password": "abc12345", "remember": True}).status_code == 200
        assert c.put("/api/auth/profile", json={"display_name": "新名字"}).json()["user"]["display_name"] == "新名字"
        assert c.post("/api/auth/password", json={"old": "bad", "new": "newpass123"}).status_code == 400
        assert c.post("/api/auth/password", json={"old": "abc12345", "new": "newpass123"}).json() == {"ok": True}
        c.post("/api/auth/logout")
        assert c.post("/api/auth/login", json={"username": "改密学生", "password": "abc12345"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "改密学生", "password": "newpass123"}).status_code == 200


def test_password_hash_is_salted_scrypt():
    h1, h2 = auth.hash_password("abc12345"), auth.hash_password("abc12345")
    assert h1 != h2 and h1.startswith("scrypt$") and "abc12345" not in h1
    assert auth.verify_password("abc12345", h1) and not auth.verify_password("abc12346", h1)


def test_one_time_codes_for_students_and_teachers(auth_on):
    with new_client() as adm:
        login_admin(adm)
        room = adm.post("/api/classes", json={"name": "一次性码班"}).json()
        adm.patch(f"/api/classes/{room['id']}", json={"registration_open": False})  # 关掉通用码
        codes = adm.post(f"/api/classes/{room['id']}/codes", json={"count": 3, "note": "补录"}).json()
        assert len(codes) == 3 and all(len(c["code"]) == 9 and c["state"] == "unused" for c in codes)
        assert register(new_client(), "通用码学生", invite=room["invite_code"]).status_code == 403  # 通用码已关闭

        u = register(new_client(), "一次性学生", invite=codes[0]["code"].lower()).json()["user"]  # 不区分大小写
        assert u["class_name"] == "一次性码班"
        r = register(new_client(), "抢用学生", invite=codes[0]["code"])
        assert r.status_code == 400 and "已被使用" in r.json()["detail"]
        listed = {c["code"]: c for c in adm.get(f"/api/classes/{room['id']}/codes").json()}
        assert listed[codes[0]["code"]]["state"] == "used" and listed[codes[0]["code"]]["used_by_name"] == "一次性学生"

        assert adm.delete(f"/api/codes/{codes[1]['code']}").json() == {"ok": True}
        assert register(new_client(), "作废码学生", invite=codes[1]["code"]).status_code == 400
        assert adm.delete(f"/api/codes/{codes[0]['code']}").status_code == 400  # 已使用的不能作废

        # 批量：改备注、作废、删除；已使用的跳过
        more = [c["code"] for c in adm.post(f"/api/classes/{room['id']}/codes", json={"count": 4}).json()]
        r = adm.post("/api/codes/batch", json={"codes": more + [codes[0]["code"]], "action": "note", "note": "第二批"}).json()
        assert r == {"done": 5, "skipped": 0}
        r = adm.post("/api/codes/batch", json={"codes": more[:2] + [codes[0]["code"]], "action": "revoke"}).json()
        assert r == {"done": 2, "skipped": 1}
        r = adm.post("/api/codes/batch", json={"codes": more + [codes[0]["code"]], "action": "delete"}).json()
        assert r == {"done": 4, "skipped": 1}
        left = {c["code"]: c for c in adm.get(f"/api/classes/{room['id']}/codes").json()}
        assert codes[0]["code"] in left and left[codes[0]["code"]]["note"] == "第二批" and not set(more) & set(left)

        t = adm.post("/api/auth/teacher-codes", json={"count": 1}).json()[0]["code"]
        assert new_client().get("/api/auth/me").json()["registration_modes"]["teacher"] is True
        assert register(new_client(), "一次性老师", invite=t, role="teacher").json()["user"]["role"] == "teacher"
        assert register(new_client(), "再用老师码", invite=t, role="teacher").status_code in (400, 403)


def _platform_model():
    from agent import llm
    p = llm.upsert_provider({"name": "平台", "base_url": "https://p.example.com/v1", "api_key": "sk-platformxxxx",
                             "models": ["plat-a"]})
    old = llm.get_routing()
    llm.save_routing(llm.Routing(primary=llm.ModelRef(provider_id=p.id, model="plat-a")))
    return p, old


def _fake_chat(monkeypatch):
    import json as _json

    import agent.agent as agent_mod
    from agent.llm import Completion

    async def fake(messages, tools=None, prefer=None, user=None):
        yield {"type": "model", "provider": "x", "model": "plat-a", "fallback": False}
        yield {"type": "delta", "text": "好"}
        yield {"type": "done", "completion": Completion(content="好", model="plat-a", provider="x")}
    monkeypatch.setattr(agent_mod, "stream_chat", fake)
    return _json


def test_quota_limits_platform_model_usage(auth_on, monkeypatch):
    from agent import llm
    _fake_chat(monkeypatch)
    p, old = _platform_model()
    try:
        with new_client() as adm, new_client() as stu:
            login_admin(adm)
            assert adm.put("/api/quota/defaults", json={"teacher": None, "student": 5}).json() == {"teacher": None, "student": 5}
            uid = register(stu, "额度学生").json()["user"]["id"]
            room = adm.get("/api/classes").json()[0]
            assert stu.get("/api/quota/me").json()["limit"] == 5
            adm.patch(f"/api/classes/{room['id']}", json={"quota_daily": 3})
            assert stu.get("/api/quota/me").json() == {"limit": 3, "used": 0, "remaining": 3, "source": "班级默认"}
            adm.patch(f"/api/users/{uid}", json={"quota_daily": 2})
            assert stu.get("/api/quota/me").json()["source"] == "个人设置"
            for _ in range(2):
                assert stu.post("/api/chat", json={"message": "你好"}).status_code == 200
            r = stu.post("/api/chat", json={"message": "你好"})
            assert r.status_code == 429 and "已用完（2 / 2）" in r.json()["detail"]
            assert stu.get("/api/llm/choices").json()["quota"]["remaining"] == 0
            row = next(u for u in adm.get("/api/users").json() if u["id"] == uid)
            assert row["quota"]["used"] == 2 and row["quota_daily"] == 2
            adm.patch(f"/api/users/{uid}", json={"quota_daily": None})  # 恢复沿用班级默认
            assert stu.get("/api/quota/me").json()["limit"] == 3
    finally:
        llm.save_routing(old)
        llm.delete_provider(p.id)


def test_own_channels_are_private_and_permissions(auth_on, monkeypatch):
    from agent import llm
    p, old = _platform_model()
    monkeypatch.setattr(get_settings(), "teacher_invite_code", "teach-own")
    monkeypatch.setattr(llm, "check_public_url", lambda url: None if "example.com" in url else (_ for _ in ()).throw(
        llm.LLMError("出于安全原因，自己添加的模型渠道只能使用公网地址，不能指向本机或内网")))
    try:
        with new_client() as adm, new_client() as a, new_client() as b, new_client() as tea:
            login_admin(adm)
            ua = register(a, "自带渠道甲").json()["user"]
            register(b, "自带渠道乙")
            register(tea, "管学生老师", invite="teach-own", role="teacher")
            body = {"name": "我的 DeepSeek", "base_url": "https://mine.example.com/v1", "api_key": "sk-mineeeeeeeee", "models": ["my-m"]}
            mine = a.post("/api/llm/my-providers", json=body).json()
            assert mine["owner_id"] == ua["id"] and "sk-mineeeeeeeee" not in str(mine)
            assert b.get("/api/llm/my-providers").json() == []  # 别人看不到
            assert b.put(f"/api/llm/my-providers/{mine['id']}", json={"name": "x"}).status_code == 404
            assert adm.put(f"/api/llm/providers/{mine['id']}", json={"name": "x"}).status_code == 404  # 平台接口不能改个人渠道
            assert all(x["id"] != mine["id"] for x in adm.get("/api/llm/providers").json())
            bad = a.post("/api/llm/my-providers", json={**body, "base_url": "http://127.0.0.1:8080/v1"})
            assert bad.status_code == 400 and "公网地址" in bad.json()["detail"]

            groups = {g["section"]: g for g in a.get("/api/llm/choices").json()["groups"]}
            assert set(groups) == {"platform", "own"} and groups["own"]["models"] == ["my-m"]
            assert llm.uses_platform(llm.plan(llm.ModelRef(provider_id=mine["id"], model="my-m"), _user("自带渠道甲"))) is False

            # 管理员关闭甲的平台权限：Auto 改用自己的渠道；关闭自建渠道权限后无法再添加
            adm.patch(f"/api/users/{ua['id']}", json={"allow_platform": False})
            ch = a.get("/api/llm/choices").json()
            assert ch["platform_allowed"] is False and [g["section"] for g in ch["groups"]] == ["own"]
            assert [m for _, m in llm.plan(None, _user("自带渠道甲"))] == ["my-m"]
            assert tea.patch(f"/api/users/{ua['id']}", json={"allow_own": False}).status_code == 404  # 别班老师管不到
            adm.patch(f"/api/users/{ua['id']}", json={"allow_own": False})
            assert a.post("/api/llm/my-providers", json=body).status_code == 403
            assert a.get("/api/llm/choices").json()["groups"] == []
    finally:
        llm.save_routing(old)
        llm.delete_provider(p.id)
        with Session(engine()) as s:
            from api.db import LLMProvider
            for row in s.exec(select(LLMProvider).where(LLMProvider.owner_id != None)).all():  # noqa: E711
                s.delete(row)
            s.commit()


def _user(username):
    with Session(engine()) as s:
        return s.exec(select(User).where(User.username == username)).first()


def test_teacher_sets_quota_and_platform_access_for_own_students(auth_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "teacher_invite_code", "teach-q")
    with new_client() as tea, new_client() as stu:
        register(tea, "额度老师", invite="teach-q", role="teacher")
        room = tea.post("/api/classes", json={"name": "额度班"}).json()
        uid = register(stu, "额度班学生", invite=room["invite_code"]).json()["user"]["id"]
        assert tea.patch(f"/api/classes/{room['id']}", json={"quota_daily": 20}).json()["quota_daily"] == 20
        r = tea.patch(f"/api/users/{uid}", json={"quota_daily": 8, "allow_platform": False}).json()
        assert r["quota"]["limit"] == 8 and r["allow_platform"] is False
        assert tea.patch(f"/api/users/{uid}", json={"allow_own": False}).status_code == 403  # 只有管理员能关自建渠道
        assert tea.patch(f"/api/users/{uid}", json={"quota_daily": -1}).status_code == 400
        assert tea.get("/api/quota/defaults").status_code == 403
