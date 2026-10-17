# HomeServer - Flat Expenses

Small self-hosted app to track shared flat expenses and settle up. FastAPI + SQLite, plain HTML/JS frontend, ships as a Docker image.

## Features
- **Quick add**: amount → what → category → done. Defaults: today, you paid, split equally between everyone
- Multiple payers, custom splits, one person can both pay and consume
- **Settle up**: see who pays whom, record a payment with one click
- All expenses with search, filters (category, month, person) and **CSV export**
- Profile with balance, settlements, expenses and a **stats** tab (your share by month/quarter and category)
- Admin: add flatmates (temporary password, they pick their own at first login), deactivate, reset passwords, app settings (settlement mode, currency)
- Session cookies (httponly, 30-day rolling), login throttling, security headers (CSP)
- Daily automatic SQLite backups, health check, auto-restart in Docker
- Mobile-first UI with bottom tab bar, light/dark mode

Admin is a manager role, not a flatmate: admins never take part in expenses or balances.

## Run with Docker (recommended)

```bash
git clone <repo-url> flat-expenses && cd flat-expenses
cp .env.example .env          # optional: set ADMIN_PASSWORD, PORT, TZ ...
docker compose up -d --build
```

Open `http://<server-ip>:8000` and log in as `admin` / `changeme` (or your `ADMIN_PASSWORD`). Without `ADMIN_PASSWORD` you must pick a new password at first login. Then add flatmates under **Admin**.

The container:
- restarts automatically after crashes and server reboots (`restart: unless-stopped`)
- reports its state via a health check (`docker ps` shows `healthy`)
- keeps the database and backups in the named volume `data` (survives rebuilds/updates)
- runs as an unprivileged user, logs are rotated (3 × 10 MB)

### Ubuntu server setup

```bash
# Docker Engine + compose plugin (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # log out and back in afterwards

git clone <repo-url> ~/flat-expenses && cd ~/flat-expenses
cp .env.example .env && nano .env
docker compose up -d --build
```

Docker's service starts on boot, so the app comes back after a reboot.

### Everyday commands

| What | Command |
|---|---|
| Status / health | `docker compose ps` |
| Logs | `docker compose logs -f` |
| Update to latest code | `git pull && docker compose up -d --build` |
| Stop / start | `docker compose stop` / `docker compose start` |
| Copy backups to the host | `docker compose cp app:/data/backups ./backups` |

### Backups & restore

A copy of the database is written to `/data/backups/expenses-YYYY-MM-DD.db` at startup and every 24 h. The last `BACKUP_KEEP` (default 14) are kept. Copy them off the server now and then (see table above).

Restore a backup:

```bash
docker compose stop
docker run --rm -v flat-expenses_data:/data -v "$PWD/backups":/restore alpine sh -c \
  "cp /restore/expenses-2026-01-31.db /data/expenses.db && rm -f /data/expenses.db-wal /data/expenses.db-shm && chown 1000:1000 /data/expenses.db"
docker compose start
```

The volume is named `<folder>_data` (check with `docker volume ls`).

> `docker compose down -v` **deletes the volume with all data**. Use `docker compose down` (no `-v`) to just remove the container.

### HTTPS (optional)

To use it outside your LAN, put a reverse proxy in front, e.g. [Caddy](https://caddyserver.com/):

```
expenses.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then set `COOKIE_SECURE=true` and `FORWARDED_ALLOW_IPS=*` in `.env`, and publish the port only locally (`PORT=127.0.0.1:8000`).

## Configuration

All settings are environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Host port (compose only) |
| `TZ` | `Europe/Berlin` | Timezone for logs and backup names |
| `ADMIN_USERNAME` | `admin` | Initial admin name (first start only) |
| `ADMIN_PASSWORD` | – | Initial admin password; unset = `changeme` + forced change |
| `COOKIE_SECURE` | `false` | `true` when served over HTTPS |
| `SESSION_TTL_DAYS` | `30` | Login lifetime, extended on use |
| `BACKUP_KEEP` | `14` | Daily backups to keep, `0` disables |
| `LOGIN_MAX_FAILURES` / `LOGIN_WINDOW_SECONDS` | `5` / `900` | Login throttling |
| `DATA_DIR` | project root (`/data` in Docker) | Where `expenses.db` and `backups/` live |
| `DATABASE_URL` | `sqlite:///$DATA_DIR/expenses.db` | Override the database location |

Currency and settlement mode are set in the app under **Admin → Settings**.

## Local development

Requires Python 3.13.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
uvicorn app.main:app --reload
pytest -q
```

Pages: `/` home, `/expenses` list, `/expenses/new` quick add, `/expenses/{id}` detail/edit, `/users/{id}` profile + stats, `/users/{id}/settings` account, `/admin`. API docs at `/docs`.

The schema is migrated automatically at startup (new columns are added to existing databases).

## API overview

All endpoints except `POST /api/auth/login` and `GET /api/health` require a session cookie.

### Auth
- `POST /api/auth/login` — log in, sets session cookie (429 after too many failures)
- `POST /api/auth/logout` — log out, clears session cookie

### Users
- `POST /api/users/` — create flatmate (**admin**), starts with `must_change_password`
- `GET /api/users/` — list users
- `GET /api/users/me` — current user
- `GET /api/users/{id}` — get user (admin or self)
- `PATCH /api/users/{id}` — name/password (admin or self; own password needs `current_password`), `is_admin` / `is_active` (**admin**)
- `DELETE /api/users/{id}` — **admin**; refused for users with expenses (deactivate them instead), self, or the last admin

### Expenses
- `POST /api/expenses/` — create expense (currency defaults to the app setting)
- `GET /api/expenses/?user_id=` — list, newest first (admin sees all, others their own)
- `GET /api/expenses/categories` — distinct categories
- `GET /api/expenses/{id}` — get (admin or participant)
- `PATCH /api/expenses/{id}` — partial update (admin or payer); nothing is saved if validation fails
- `DELETE /api/expenses/{id}` — delete (admin or payer)

### Balances & settings
- `GET /api/balances/` — net balance per flatmate
- `GET /api/balances/settlements/?mode=simplified|full` — who pays whom (mode defaults to the app setting)
- `GET /api/settings/`, `PATCH /api/settings/` (**admin**) — `settlement_mode`, `currency`
- `GET /api/health` — health check

## Expense model
Shares are signed: negative = paid, positive = consumed. They must sum to 0, positives must equal the cost. Amounts are rounded to cents.

```json
{
  "date": "2026-01-03",
  "description": "Pizza",
  "category": "Food",
  "cost": 75.0,
  "shares": [
    {"user_id": 1, "share": 10.0},
    {"user_id": 2, "share": 15.0},
    {"user_id": 3, "share": 15.0},
    {"user_id": 4, "share": 15.0},
    {"user_id": 5, "share": 20.0},
    {"user_id": 3, "share": -40.0},
    {"user_id": 5, "share": -35.0}
  ]
}
```

A settlement payment is stored as an expense with category `Settlement` (payer −amount, receiver +amount).
