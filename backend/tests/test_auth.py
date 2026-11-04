"""账号登录：注册邀请码、登录与会话、按用户隔离数据、管理员权限、防暴力猜测、停用账号。"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from api import auth
from api.db import AppSetting, ChatSession, engine
from api.main import app
from api.settings import get_settings

PERIOD = {"start": "2023-01-01", "end": "2023-12-31"}


@pytest.fixture()
def auth_on(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "auth_enabled", True)
    monkeypatch.setattr(st, "invite_code", "class-2026")
    monkeypatch.setattr(st, "admin_username", "teacher")
    monkeypatch.setattr(st, "admin_password", "Teacher-pass-1")
    auth._fails.clear()
    yield
    with Session(engine()) as s:  # 页面上改过的邀请码不能带到别的测试
        row = s.get(AppSetting, auth.INVITE_KEY)
        if row:
            s.delete(row)
            s.commit()


def new_client():
    return TestClient(app)


def register(c, username, password="abc12345", invite="class-2026"):
    return c.post("/api/auth/register", json={"username": username, "password": password, "invite_code": invite})


def test_login_required_and_registration(auth_on):
    with new_client() as c:
        me = c.get("/api/auth/me").json()
        assert me == {"enabled": True, "user": None, "registration": True}
        assert c.get("/api/strategies").status_code == 401
        assert c.get("/api/health").status_code == 200
        assert c.get("/").status_code == 200  # 登录页本身不需要登录

        assert register(c, "学生甲", invite="wrong").json()["detail"] == "邀请码不正确"
        assert "字母和数字" in register(c, "学生甲", password="abcdefgh").json()["detail"]
        assert "8 到 64" in register(c, "学生甲", password="a1").json()["detail"]
        assert "用户名" in register(c, "a").json()["detail"]
        r = register(c, "学生甲")
        assert r.status_code == 200 and r.json()["user"]["role"] == "user"
        cookie = r.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert c.get("/api/auth/me").json()["user"]["username"] == "学生甲"
        assert c.get("/api/strategies").status_code == 200
        assert register(new_client(), "学生甲").json()["detail"] == "这个用户名已经被注册了"

        c.post("/api/auth/logout")
        assert c.get("/api/strategies").status_code == 401


def test_registration_closed_without_invite_code(auth_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "invite_code", "")
    with new_client() as c:
        assert c.get("/api/auth/me").json()["registration"] is False
        r = register(c, "路人", invite="")
        assert r.status_code == 403 and "未开放注册" in r.json()["detail"]


def test_data_isolated_between_users(auth_on):
    with new_client() as a, new_client() as b:
        register(a, "隔离甲")
        register(b, "隔离乙")
        rid = a.post("/api/backtests", json={"strategy": "dual_ma_stock", "config": PERIOD}).json()["id"]
        assert [r["id"] for r in a.get("/api/backtests").json()] == [rid]
        assert b.get("/api/backtests").json() == []
        assert b.delete(f"/api/backtests/{rid}").status_code == 404  # 不能删别人的记录
        assert b.get(f"/api/backtests/{rid}").status_code == 200  # 报告链接可以分享查看

        uid_a = a.get("/api/auth/me").json()["user"]["id"]
        with Session(engine()) as s:
            s.add(ChatSession(id="sess_of_a", title="甲的对话", user_id=uid_a))
            s.commit()
        assert [x["id"] for x in a.get("/api/chat/sessions").json()] == ["sess_of_a"]
        assert b.get("/api/chat/sessions").json() == []
        assert b.get("/api/chat/sessions/sess_of_a").status_code == 404
        assert b.delete("/api/chat/sessions/sess_of_a").status_code == 404
        assert a.get("/api/chat/sessions/sess_of_a").status_code == 200


def test_only_admin_changes_model_settings_and_users(auth_on):
    with new_client() as stu, new_client() as adm:
        register(stu, "普通学生")
        assert stu.get("/api/llm/lock").json() == {"locked": True, "mode": "role"}
        body = {"name": "x", "base_url": "https://x.example.com", "api_key": "sk-xxxxxxxxxxxx"}
        assert stu.post("/api/llm/providers", json=body).status_code == 403
        assert stu.get("/api/llm/providers").status_code == 200
        assert all(x["api_key_masked"] in ("已设置", "") for x in stu.get("/api/llm/providers").json())
        assert stu.get("/api/auth/users").status_code == 403

        r = adm.post("/api/auth/login", json={"username": "teacher", "password": "Teacher-pass-1"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
        assert adm.get("/api/llm/lock").json() == {"locked": False, "mode": "role"}
        pid = adm.post("/api/llm/providers", json=body).json()["id"]
        adm.delete(f"/api/llm/providers/{pid}")

        users = {u["username"]: u for u in adm.get("/api/auth/users").json()}
        sid = users["普通学生"]["id"]
        assert adm.patch(f"/api/auth/users/{users['teacher']['id']}", json={"disabled": True}).status_code == 400
        assert adm.patch(f"/api/auth/users/{sid}", json={"disabled": True}).json()["disabled"] is True
        assert stu.get("/api/strategies").status_code == 401  # 停用后立即失效
        r = stu.post("/api/auth/login", json={"username": "普通学生", "password": "abc12345"})
        assert r.status_code == 403 and "停用" in r.json()["detail"]
        assert adm.delete(f"/api/auth/users/{sid}").json() == {"ok": True}


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
        assert c.post("/api/auth/password", json={"old": "bad", "new": "newpass123"}).status_code == 400
        assert c.post("/api/auth/password", json={"old": "abc12345", "new": "newpass123"}).json() == {"ok": True}
        c.post("/api/auth/logout")
        assert c.post("/api/auth/login", json={"username": "改密学生", "password": "abc12345"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "改密学生", "password": "newpass123"}).status_code == 200


def test_password_hash_is_salted_scrypt():
    h1, h2 = auth.hash_password("abc12345"), auth.hash_password("abc12345")
    assert h1 != h2 and h1.startswith("scrypt$") and "abc12345" not in h1
    assert auth.verify_password("abc12345", h1) and not auth.verify_password("abc12346", h1)


def test_admin_changes_invite_code_on_page(auth_on):
    """管理员在页面上修改邀请码后立即生效：旧码失效、新码可注册；关闭后不开放注册；学生无权查看。"""
    with new_client() as adm, new_client() as stu:
        adm.post("/api/auth/login", json={"username": "teacher", "password": "Teacher-pass-1"})
        assert adm.get("/api/auth/invite").json() == {"code": "class-2026", "enabled": True, "source": "env"}
        assert adm.put("/api/auth/invite", json={"code": "ab", "enabled": True}).status_code == 400
        r = adm.put("/api/auth/invite", json={"code": "spring-2027", "enabled": True})
        assert r.json() == {"code": "spring-2027", "enabled": True, "source": "db"}
        assert register(new_client(), "旧码同学").json()["detail"] == "邀请码不正确"
        assert register(stu, "新码同学", invite="spring-2027").status_code == 200
        assert stu.get("/api/auth/invite").status_code == 403
        assert stu.put("/api/auth/invite", json={"code": "hack-0000", "enabled": True}).status_code == 403

        adm.put("/api/auth/invite", json={"code": "spring-2027", "enabled": False})
        assert new_client().get("/api/auth/me").json()["registration"] is False
        assert register(new_client(), "关闭后", invite="spring-2027").status_code == 403
