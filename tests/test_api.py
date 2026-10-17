import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.auth import get_current_user, get_db, hash_password
from app.routers.api import auth, balances, expenses, settings, users


def _make_app(session_factory, current_user_id: int) -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(users.router, prefix="/api/users")
    app.include_router(expenses.router, prefix="/api/expenses")
    app.include_router(balances.router, prefix="/api/balances")
    app.include_router(settings.router, prefix="/api/settings")

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user():
        db = session_factory()
        user = db.query(models.User).filter(models.User.id == current_user_id).first()
        db.close()
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return app


def _make_db():
    _ = models
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_factory


@pytest.fixture()
def client():
    session_factory = _make_db()
    db = session_factory()
    admin = models.User(name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    admin_id = admin.id
    db.close()

    app = _make_app(session_factory, admin_id)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def non_admin_client():
    session_factory = _make_db()
    db = session_factory()
    admin = models.User(name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True)
    regular = models.User(name="TestUser", password_hash=hash_password("testpass"), is_admin=False)
    other = models.User(name="OtherUser", password_hash=hash_password("testpass"), is_admin=False)
    db.add(admin)
    db.add(regular)
    db.add(other)
    db.commit()
    db.refresh(regular)
    regular_id = regular.id
    db.close()

    app = _make_app(session_factory, regular_id)
    with TestClient(app) as test_client:
        yield test_client


def _user_id(client: TestClient, name: str) -> int:
    return next(u["id"] for u in client.get("/api/users/").json() if u["name"] == name)


def create_user(client: TestClient, name: str) -> int:
    res = client.post("/api/users/", json={"name": name, "password": "password123"})
    assert res.status_code == 201
    return res.json()["id"]


def test_create_and_list_users(client: TestClient):
    user_id = create_user(client, "Alice")

    res = client.get("/api/users/")
    assert res.status_code == 200
    data = res.json()

    names = [u["name"] for u in data]
    assert "Alice" in names
    alice = next(u for u in data if u["name"] == "Alice")
    assert alice["id"] == user_id


def test_new_user_is_not_admin(client: TestClient):
    user_id = create_user(client, "RegularUser")
    res = client.get(f"/api/users/{user_id}")
    assert res.status_code == 200
    assert res.json()["is_admin"] is False


def test_create_user_requires_admin(non_admin_client: TestClient):
    res = non_admin_client.post("/api/users/", json={"name": "NewUser", "password": "password123"})
    assert res.status_code == 403


def test_login_success(client: TestClient):
    create_user(client, "LoginUser")
    res = client.post("/api/auth/login", json={"name": "LoginUser", "password": "password123"})
    assert res.status_code == 200
    assert res.json()["name"] == "LoginUser"


def test_login_invalid_credentials(client: TestClient):
    create_user(client, "LoginUser2")
    res = client.post("/api/auth/login", json={"name": "LoginUser2", "password": "wrongpass"})
    assert res.status_code == 401


def test_logout(client: TestClient):
    create_user(client, "LogoutUser")
    login_res = client.post("/api/auth/login", json={"name": "LogoutUser", "password": "password123"})
    assert login_res.status_code == 200
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 204


def test_update_user_rename(client: TestClient):
    user_id = create_user(client, "UserA")
    res = client.patch(f"/api/users/{user_id}", json={"name": "UserA-renamed"})
    assert res.status_code == 200
    assert res.json()["name"] == "UserA-renamed"


def test_update_user_rename_duplicate_returns_409(client: TestClient):
    create_user(client, "UserA")
    user_b_id = create_user(client, "UserB")
    res = client.patch(f"/api/users/{user_b_id}", json={"name": "UserA"})
    assert res.status_code == 409


def test_update_user_toggle_admin(client: TestClient):
    user_id = create_user(client, "PromotedUser")
    res = client.patch(f"/api/users/{user_id}", json={"is_admin": True})
    assert res.status_code == 200
    assert res.json()["is_admin"] is True

    res = client.patch(f"/api/users/{user_id}", json={"is_admin": False})
    assert res.status_code == 200
    assert res.json()["is_admin"] is False


def test_update_user_toggle_admin_requires_admin(non_admin_client: TestClient):
    res = non_admin_client.patch("/api/users/1", json={"is_admin": True})
    assert res.status_code == 403


def test_delete_user(client: TestClient):
    user_id = create_user(client, "DeleteMe")
    res = client.delete(f"/api/users/{user_id}")
    assert res.status_code == 204

    res = client.get("/api/users/")
    names = [u["name"] for u in res.json()]
    assert "DeleteMe" not in names


def test_delete_user_requires_admin(non_admin_client: TestClient):
    res = non_admin_client.delete("/api/users/1")
    assert res.status_code == 403


def test_delete_self_forbidden(client: TestClient):
    res = client.get("/api/users/me")
    admin_id = res.json()["id"]
    res = client.delete(f"/api/users/{admin_id}")
    assert res.status_code == 403


def test_delete_last_admin_forbidden(client: TestClient):
    res = client.get("/api/users/me")
    admin_id = res.json()["id"]
    create_user(client, "NonAdmin")
    res = client.patch(f"/api/users/{admin_id}", json={"is_admin": False})
    assert res.status_code == 409


def test_create_expense_valid_shares(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")

    payload = {
        "date": "2026-01-01",
        "description": "Groceries",
        "category": "Food",
        "cost": 30.0,
        "currency": "EUR",
        "comment": "",
        "shares": [
            {"user_id": alice_id, "share": -30.0},
            {"user_id": bob_id, "share": 30.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["cost"] == 30.0
    assert len(data["shares"]) == 2


def test_create_expense_invalid_shares(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")

    payload = {
        "date": "2026-01-01",
        "description": "Dinner",
        "category": "Food",
        "cost": 25.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": alice_id, "share": -25.0},
            {"user_id": bob_id, "share": 20.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 400


def test_create_expense_invalid_user_id(client: TestClient):
    alice_id = create_user(client, "Alice")

    payload = {
        "date": "2026-01-01",
        "description": "Ghost Expense",
        "category": "Food",
        "cost": 10.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": alice_id, "share": -10.0},
            {"user_id": 99999, "share": 10.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 400


def test_balances_with_multiple_payers(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")
    carol_id = create_user(client, "Carol")

    payload = {
        "date": "2026-01-02",
        "description": "Supplies",
        "category": "House",
        "cost": 30.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": alice_id, "share": -10.0},
            {"user_id": bob_id, "share": -20.0},
            {"user_id": carol_id, "share": 30.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201

    res = client.get("/api/balances/")
    assert res.status_code == 200
    balances_data = {b["name"]: b["balance"] for b in res.json()}

    assert balances_data["Alice"] == 10.0
    assert balances_data["Bob"] == 20.0
    assert balances_data["Carol"] == -30.0


def test_get_categories_admin_sees_all(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")

    for cat, payer, consumer in [("Food", alice_id, bob_id), ("House", bob_id, alice_id), ("Food", alice_id, bob_id)]:
        client.post("/api/expenses/", json={
            "date": "2026-01-01", "description": "x", "category": cat,
            "cost": 10.0, "currency": "EUR", "comment": None,
            "shares": [{"user_id": payer, "share": -10.0}, {"user_id": consumer, "share": 10.0}],
        })

    res = client.get("/api/expenses/categories")
    assert res.status_code == 200
    assert res.json() == ["Food", "House"]


def test_get_categories_non_admin_sees_own(non_admin_client: TestClient):
    me_id = non_admin_client.get("/api/users/me").json()["id"]
    other_id = _user_id(non_admin_client, "OtherUser")

    # expense involving me → should appear in categories
    non_admin_client.post("/api/expenses/", json={
        "date": "2026-01-01", "description": "shared", "category": "Food",
        "cost": 20.0, "currency": "EUR", "comment": None,
        "shares": [{"user_id": other_id, "share": -20.0}, {"user_id": me_id, "share": 20.0}],
    })
    # expense NOT involving me → should not appear
    non_admin_client.post("/api/expenses/", json={
        "date": "2026-01-01", "description": "other only", "category": "Travel",
        "cost": 10.0, "currency": "EUR", "comment": None,
        "shares": [{"user_id": other_id, "share": -10.0}, {"user_id": other_id, "share": 10.0}],
    })

    res = non_admin_client.get("/api/expenses/categories")
    assert res.status_code == 200
    assert res.json() == ["Food"]


def test_balances_pizza_cash_split(client: TestClient):
    p1_id = create_user(client, "Person 1")
    p2_id = create_user(client, "Person 2")
    p3_id = create_user(client, "Person 3")
    p4_id = create_user(client, "Person 4")
    p5_id = create_user(client, "Person 5")

    payload = {
        "date": "2026-01-03",
        "description": "Pizza",
        "category": "Food",
        "cost": 75.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": p1_id, "share": 10.0},
            {"user_id": p2_id, "share": 15.0},
            {"user_id": p3_id, "share": 15.0},
            {"user_id": p4_id, "share": 15.0},
            {"user_id": p5_id, "share": 20.0},
            {"user_id": p3_id, "share": -40.0},
            {"user_id": p5_id, "share": -35.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201

    res = client.get("/api/balances/")
    assert res.status_code == 200
    balances_data = {b["name"]: b["balance"] for b in res.json()}

    assert balances_data["Person 1"] == -10.0
    assert balances_data["Person 2"] == -15.0
    assert balances_data["Person 3"] == 25.0
    assert balances_data["Person 4"] == -15.0
    assert balances_data["Person 5"] == 15.0

    payload = {
        "date": "2026-01-04",
        "description": "Drinks",
        "category": "Food",
        "cost": 15.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": p2_id, "share": 10.0},
            {"user_id": p4_id, "share": 5.0},
            {"user_id": p2_id, "share": -15.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201

    res = client.get("/api/balances/")
    assert res.status_code == 200
    balances_data = {b["name"]: b["balance"] for b in res.json()}

    assert balances_data["Person 1"] == -10.0
    assert balances_data["Person 2"] == -10.0
    assert balances_data["Person 3"] == 25.0
    assert balances_data["Person 4"] == -20.0
    assert balances_data["Person 5"] == 15.0


# --- helpers for the tests below ---------------------------------------------

@pytest.fixture(autouse=True)
def _reset_login_throttle():
    auth.login_throttle._failures.clear()
    yield
    auth.login_throttle._failures.clear()


def post_expense(client: TestClient, shares, cost=None, **fields):
    cost = cost if cost is not None else sum(s for _, s in shares if s > 0)
    payload = {
        "date": "2026-01-01", "description": "Thing", "category": "Food", "cost": cost,
        "shares": [{"user_id": u, "share": s} for u, s in shares],
        **fields,
    }
    return client.post("/api/expenses/", json=payload)


def balances_by_name(client: TestClient) -> dict[str, float]:
    return {b["name"]: b["balance"] for b in client.get("/api/balances/").json()}


# --- users -------------------------------------------------------------------

def test_delete_user_with_expenses_is_refused_and_balances_survive(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    assert post_expense(client, [(alice, -10), (alice, 5), (bob, 5)]).status_code == 201

    res = client.delete(f"/api/users/{bob}")
    assert res.status_code == 409
    assert balances_by_name(client) == {"Alice": 5.0, "Bob": -5.0}


def test_deactivated_user_cannot_log_in_or_join_new_expenses(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    expense_id = post_expense(client, [(alice, -10), (bob, 10)]).json()["id"]

    res = client.patch(f"/api/users/{bob}", json={"is_active": False})
    assert res.status_code == 200 and res.json()["is_active"] is False

    assert client.post("/api/auth/login", json={"name": "Bob", "password": "password123"}).status_code == 401
    assert post_expense(client, [(alice, -4), (bob, 4)]).status_code == 400
    # Existing expense stays editable with the deactivated user still in it.
    res = client.patch(f"/api/expenses/{expense_id}", json={"shares": [
        {"user_id": alice, "share": -12}, {"user_id": bob, "share": 12}], "cost": 12})
    assert res.status_code == 200
    # Open balance keeps the deactivated user visible.
    assert balances_by_name(client)["Bob"] == -12.0


def test_cannot_deactivate_self(client: TestClient):
    me = client.get("/api/users/me").json()["id"]
    assert client.patch(f"/api/users/{me}", json={"is_active": False}).status_code == 403


def test_new_user_must_change_password(client: TestClient):
    user_id = create_user(client, "Fresh")
    assert client.get(f"/api/users/{user_id}").json()["must_change_password"] is True


def test_change_own_password_requires_current_password(non_admin_client: TestClient):
    me = non_admin_client.get("/api/users/me").json()["id"]
    res = non_admin_client.patch(f"/api/users/{me}", json={"password": "newpassword1"})
    assert res.status_code == 400
    res = non_admin_client.patch(f"/api/users/{me}", json={"password": "newpassword1", "current_password": "wrong"})
    assert res.status_code == 400
    res = non_admin_client.patch(f"/api/users/{me}", json={"password": "newpassword1", "current_password": "testpass"})
    assert res.status_code == 200
    assert res.json()["must_change_password"] is False
    login = non_admin_client.post("/api/auth/login", json={"name": "TestUser", "password": "newpassword1"})
    assert login.status_code == 200


def test_short_password_rejected(client: TestClient):
    assert client.post("/api/users/", json={"name": "Shorty", "password": "short"}).status_code == 422


def test_non_admin_cannot_deactivate(non_admin_client: TestClient):
    other = _user_id(non_admin_client, "OtherUser")
    assert non_admin_client.patch(f"/api/users/{other}", json={"is_active": False}).status_code == 403


# --- auth --------------------------------------------------------------------

def test_login_is_throttled_after_repeated_failures(client: TestClient):
    create_user(client, "Target")
    for _ in range(5):
        assert client.post("/api/auth/login", json={"name": "Target", "password": "nope"}).status_code == 401
    res = client.post("/api/auth/login", json={"name": "Target", "password": "password123"})
    assert res.status_code == 429
    assert "Retry-After" in res.headers


def test_logout_clears_cookie(client: TestClient):
    create_user(client, "LogoutUser")
    client.post("/api/auth/login", json={"name": "LogoutUser", "password": "password123"})
    res = client.post("/api/auth/logout")
    assert res.status_code == 204
    assert "session_id=" in res.headers.get("set-cookie", "")
    assert "Max-Age=0" in res.headers.get("set-cookie", "")


# --- expenses ----------------------------------------------------------------

def test_failed_update_changes_nothing(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    expense_id = post_expense(client, [(alice, -10), (bob, 10)], description="Original").json()["id"]

    res = client.patch(f"/api/expenses/{expense_id}", json={
        "description": "CHANGED",
        "shares": [{"user_id": alice, "share": -10}, {"user_id": 99999, "share": 10}],
    })
    assert res.status_code == 400
    assert client.get(f"/api/expenses/{expense_id}").json()["description"] == "Original"


def test_partial_update_without_other_fields(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    expense_id = post_expense(client, [(alice, -10), (bob, 10)], comment="note").json()["id"]
    res = client.patch(f"/api/expenses/{expense_id}", json={"description": "Renamed"})
    assert res.status_code == 200
    assert res.json()["description"] == "Renamed"
    assert res.json()["comment"] == "note"


def test_update_keeps_multiple_payers(client: TestClient):
    a, b, c = create_user(client, "A"), create_user(client, "B"), create_user(client, "C")
    expense_id = post_expense(client, [(a, -10), (b, -20), (c, 30)]).json()["id"]
    res = client.patch(f"/api/expenses/{expense_id}", json={"cost": 60, "shares": [
        {"user_id": a, "share": -20}, {"user_id": b, "share": -40}, {"user_id": c, "share": 60}]})
    assert res.status_code == 200
    assert sorted(s["share"] for s in res.json()["shares"]) == [-40, -20, 60]


def test_admin_cannot_take_part_in_expenses(client: TestClient):
    admin = client.get("/api/users/me").json()["id"]
    alice = create_user(client, "Alice")
    assert post_expense(client, [(admin, -10), (alice, 10)]).status_code == 400


def test_currency_defaults_to_app_setting(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    assert client.patch("/api/settings/", json={"currency": "chf"}).json()["currency"] == "CHF"
    assert post_expense(client, [(alice, -10), (bob, 10)]).json()["currency"] == "CHF"


def test_expense_validation(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    assert post_expense(client, [(alice, -10), (bob, 10)], description="  ").status_code == 422
    assert post_expense(client, [(alice, 0), (bob, 0)], cost=0).status_code == 422
    assert post_expense(client, [(alice, -10), (bob, 10)], currency="EURO").status_code == 422


def test_shares_are_rounded_to_cents(client: TestClient):
    alice, bob = create_user(client, "Alice"), create_user(client, "Bob")
    res = post_expense(client, [(alice, -10.004), (bob, 10.004)], cost=10.004)
    assert res.status_code == 201
    assert res.json()["cost"] == 10.0


def test_list_expenses_user_filter(client: TestClient):
    a, b, c = create_user(client, "A"), create_user(client, "B"), create_user(client, "C")
    post_expense(client, [(a, -10), (b, 10)])
    post_expense(client, [(c, -10), (b, 10)])
    assert len(client.get("/api/expenses/").json()) == 2
    assert len(client.get(f"/api/expenses/?user_id={a}").json()) == 1
    assert len(client.get(f"/api/expenses/?user_id={b}").json()) == 2


def test_non_admin_cannot_list_other_users_expenses(non_admin_client: TestClient):
    other = _user_id(non_admin_client, "OtherUser")
    assert non_admin_client.get(f"/api/expenses/?user_id={other}").status_code == 403


def test_list_expenses_sorted_newest_first(client: TestClient):
    a, b = create_user(client, "A"), create_user(client, "B")
    post_expense(client, [(a, -1), (b, 1)], date="2026-01-01")
    post_expense(client, [(a, -1), (b, 1)], date="2026-03-01")
    dates = [e["date"] for e in client.get("/api/expenses/").json()]
    assert dates == ["2026-03-01", "2026-01-01"]


# --- balances & settings -----------------------------------------------------

def test_admin_not_in_balances_or_settlements(client: TestClient):
    a, b = create_user(client, "A"), create_user(client, "B")
    post_expense(client, [(a, -10), (b, 10)])
    assert "TestAdmin" not in balances_by_name(client)
    settlements = client.get("/api/balances/settlements/").json()
    assert settlements == [{"from_user_id": b, "from_name": "B", "to_user_id": a, "to_name": "A", "amount": 10.0}]


def test_settlements_default_to_setting(client: TestClient):
    a, b, c = create_user(client, "A"), create_user(client, "B"), create_user(client, "C")
    # A owes B 10, B owes C 10 -> simplified: A pays C 10; full: two transfers
    post_expense(client, [(b, -10), (a, 10)])
    post_expense(client, [(c, -10), (b, 10)])
    assert len(client.get("/api/balances/settlements/").json()) == 1
    client.patch("/api/settings/", json={"settlement_mode": "full"})
    assert len(client.get("/api/balances/settlements/").json()) == 2
    assert len(client.get("/api/balances/settlements/?mode=simplified").json()) == 1


def test_settings_update_requires_admin(non_admin_client: TestClient):
    assert non_admin_client.patch("/api/settings/", json={"currency": "USD"}).status_code == 403
    assert non_admin_client.get("/api/settings/").json() == {"settlement_mode": "simplified", "currency": "EUR"}


# --- schema migration & backups ----------------------------------------------

def test_migrate_adds_columns_to_old_database(tmp_path):
    import sqlite3
    from app.db_init import migrate

    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, "
                "password_hash VARCHAR NOT NULL, is_admin BOOLEAN NOT NULL)")
    con.execute("INSERT INTO users (name, password_hash, is_admin) VALUES ('old', 'x', 0)")
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{db_file}")
    migrate(engine)
    migrate(engine)  # idempotent
    engine.dispose()

    con = sqlite3.connect(db_file)
    row = con.execute("SELECT is_active, must_change_password FROM users WHERE name='old'").fetchone()
    version = con.execute("PRAGMA user_version").fetchone()[0]
    con.close()
    assert row == (1, 0)
    assert version >= 2


def test_backup_database_prunes_old_copies(tmp_path):
    import sqlite3
    from app.db_init import backup_database

    db_file = tmp_path / "live.db"
    sqlite3.connect(db_file).close()
    backups = tmp_path / "backups"
    backups.mkdir()
    for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
        (backups / f"expenses-{day}.db").write_bytes(b"")

    target = backup_database(db_file, backups, keep=2)
    assert target.exists()
    assert len(list(backups.glob("expenses-*.db"))) == 2


# --- real app (lifespan, pages, headers) ---------------------------------------

def test_real_app_boots_seeds_admin_and_serves_pages():
    from app.main import app as real_app

    with TestClient(real_app) as c:
        assert c.get("/api/health").json() == {"status": "ok"}

        page = c.get("/")
        assert page.status_code == 200
        assert "default-src 'self'" in page.headers["content-security-policy"]
        for path in ("/expenses", "/expenses/new", "/expenses/3", "/users/1", "/users/1/settings", "/admin"):
            assert c.get(path).status_code == 200, path

        login = c.post("/api/auth/login", json={"name": "admin", "password": "changeme"})
        assert login.status_code == 200
        assert login.json()["must_change_password"] is True
        assert c.get("/api/users/me").json()["name"] == "admin"
