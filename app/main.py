import asyncio
import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import config
from app.database import SessionLocal, engine
from app.db_init import backup_database, migrate, seed, sqlite_path
from app.routers.api import auth, balances, expenses, settings as settings_router, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60


async def _backup_loop():
    db_path = sqlite_path(config.DATABASE_URL)
    if db_path is None or config.BACKUP_KEEP <= 0:
        return
    while True:
        try:
            target = await asyncio.to_thread(backup_database, db_path, config.BACKUP_DIR, config.BACKUP_KEEP)
            if target:
                log.info("Database backup written to %s", target)
        except Exception:
            log.exception("Database backup failed")
        await asyncio.sleep(_BACKUP_INTERVAL_SECONDS)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    migrate(engine)
    with SessionLocal() as db:
        seed(db)
    backup_task = asyncio.create_task(_backup_loop())
    yield
    backup_task.cancel()


app = FastAPI(title="Flat Expenses", lifespan=lifespan)

_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}
_DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        # Swagger UI at /docs loads its assets from a CDN and uses inline scripts.
        if name == "Content-Security-Policy" and request.url.path in _DOCS_PATHS:
            continue
        response.headers.setdefault(name, value)
    if request.url.path.startswith("/static/") or not request.url.path.startswith("/api/"):
        # Revalidate pages and assets so updates show up right after a deploy.
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["Expenses"])
app.include_router(balances.router, prefix="/api/balances", tags=["Balances"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])


@app.get("/api/health", tags=["Health"])
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


def _page(name: str):
    path = config.STATIC_DIR / name
    return lambda: FileResponse(path)


_PAGES = {
    "/": "index.html",
    "/expenses": "expenses.html",
    "/expenses/new": "expense-new.html",
    "/expenses/{expense_id:int}": "expense.html",
    "/users/{user_id:int}": "user.html",
    "/users/{user_id:int}/settings": "settings.html",
    "/admin": "admin.html",
}

for _route, _file in _PAGES.items():
    app.add_api_route(_route, _page(_file), methods=["GET"], include_in_schema=False)
