# SUG/SRC e-Voting System

A secure online voting system for Student Union Government (SUG) and Students' Representative Council (SRC) elections. Voters sign in with their matric number and a one-time PIN, vote from a browser or the mobile app, and the election committee monitors turnout and results live from an admin dashboard.

## Features

- **Voter web app**: matric number + PIN login, one ballot per position, confirmation receipt
- **Admin dashboard**: settings and branding, positions and candidates, voter CSV import and PIN list, live monitor, analytics
- **Mobile app** (Flutter): voter login and ballot, served by its own API
- **Election lifecycle**: `draft` → `open` → `closed`, with the ballot locked once voting starts
- **Branding**: institution name, election title, logo and theme colour are configurable from the dashboard

## How integrity is enforced

- `vote_receipts.voter_id` is `UNIQUE`, so a double vote is rejected by the database itself, even under concurrent requests.
- The receipt and the votes are written in a single transaction. The `votes` table has no voter column, which keeps the ballot secret.
- The ballot (positions and candidates) locks once the election leaves `draft`.
- Voter PINs are hashed with bcrypt and shown only once, when generated.
- JWTs carry an audience (`web` or `mobile`) and a role (`voter` or `admin`). A mobile token is rejected by the web API and the other way round.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy, PyJWT, bcrypt |
| Database | MySQL 8 (recommended here) or PostgreSQL |
| Web | React 18, Vite, Bootstrap 5, Recharts |
| Mobile | Flutter |
| Deployment | Docker, Docker Compose, nginx |

## Project structure

```
evoting/
├── backend/
│   ├── core/          Shared: database models, voting rules, JWT helpers (no HTTP routes)
│   ├── api_web/       WEB API    -> /api/web/*     voters + admin dashboard   (port 8001)
│   ├── api_mobile/    MOBILE API -> /api/mobile/*  voters only                (port 8002)
│   ├── seed.py        Creates tables, the first admin, and optional demo data
│   ├── requirements.txt
│   └── Dockerfile
├── web/               React + Vite app (voter site and admin dashboard)
│   ├── Dockerfile
│   └── nginx.conf
├── mobile/            Flutter app (see mobile/README.md)
├── docker-compose.yml
├── .env.example       Settings for Docker Compose
└── evoting.sql        Optional database backup (not committed to Git)
```

The web and mobile APIs are separate but share one database, so anything the admin changes in the dashboard (institution name, positions, candidates, election status) appears in both apps immediately.

---

## 1. Clone the repository

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

Replace the URL with your own repository. If you received the project as a zip file, extract it and open a terminal in the extracted folder instead.

---

## 2. Run locally (without Docker)

### Prerequisites

- Python 3.11 or newer
- Node.js 18 or newer
- MySQL 8 (or MariaDB, or XAMPP/WAMP), or PostgreSQL

### Step 1: Create the database

Create an empty database. Tables are created automatically on first run.

```sql
CREATE DATABASE evoting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Step 2: Set up the backend

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

| Terminal | Command |
|---|---|
| Git Bash (Windows) | `source .venv/Scripts/activate` |
| PowerShell | `.venv\Scripts\Activate.ps1` |
| Command Prompt | `.venv\Scripts\activate` |
| macOS / Linux | `source .venv/bin/activate` |

Install the dependencies and create your settings file:

```bash
pip install -r requirements.txt
pip install cryptography        # needed by some MySQL 8 login setups
cp .env.example .env            # Windows Command Prompt: copy .env.example .env
```

Edit `backend/.env`:

```env
# MySQL (user root with no password, e.g. XAMPP default)
DATABASE_URL=mysql+pymysql://root:@localhost:3306/evoting

# MySQL with a password
# DATABASE_URL=mysql+pymysql://root:yourpassword@localhost:3306/evoting

# PostgreSQL
# DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/evoting

# Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=paste-a-long-random-string-here
WEB_JWT_MINUTES=60
MOBILE_JWT_MINUTES=120
CORS_ORIGINS=http://localhost:5173

ADMIN_USERNAME=admin
ADMIN_PASSWORD=ChooseAStrongPassword
```

If your database password contains special characters such as `@` or `#`, URL-encode them (`@` becomes `%40`).

If you use MySQL only, you can delete the `psycopg2-binary` line from `requirements.txt` if it fails to install.

Create the tables, the admin account and (optionally) demo data:

```bash
python seed.py --demo
```

`--demo` adds sample positions, candidates and five voters (`DEMO/001` to `DEMO/005`). **Their PINs are printed once, so write them down.** Run `python seed.py` without `--demo` for a clean database with only the admin account.

Start the web API:

```bash
uvicorn api_web.main:app --port 8001 --reload
```

Check it at http://localhost:8001/docs. If `uvicorn` is not found, use `python -m uvicorn api_web.main:app --port 8001 --reload`.

The mobile API is only needed for the Flutter app. Start it in a second terminal (with the virtual environment active):

```bash
uvicorn api_mobile.main:app --port 8002 --reload
```

### Step 3: Run the web app

In a new terminal:

```bash
cd web
npm install
npm run dev
```

| Page | URL |
|---|---|
| Voter login | http://localhost:5173/ |
| Admin login | http://localhost:5173/admin/login |

In development, Vite forwards `/api/web` requests to the web API on port 8001.

### Step 4: Mobile app (optional)

See [`mobile/README.md`](mobile/README.md).

---

## 3. Run with Docker

Docker runs the database, the API and the web app together, with nothing else to install.

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine with the Compose plugin (Linux)
- Check with `docker --version` and `docker compose version`

### Step 1: Create the settings file

From the project root:

```bash
cp .env.example .env            # Windows Command Prompt: copy .env.example .env
```

Edit `.env` and change at least these values:

| Variable | Purpose |
|---|---|
| `MYSQL_PASSWORD` | Password for the app's database user. Use letters and digits only. |
| `MYSQL_ROOT_PASSWORD` | MySQL root password. Use letters and digits only. |
| `JWT_SECRET` | Long random string used to sign login tokens |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | First admin account |
| `SEED_ARGS` | Set to `--demo` to load sample candidates and demo voters |

### Step 2: Build and start

```bash
docker compose up -d --build
```

The first build takes a few minutes. On startup the API container creates the tables and the admin account, then starts the server.

### Step 3: Open the app

| What | URL |
|---|---|
| Voter site | http://localhost:8080/ |
| Admin dashboard | http://localhost:8080/admin/login |
| API docs | http://localhost:8001/docs |

### Step 4: Get the demo voter PINs

If you set `SEED_ARGS=--demo`, the PINs appear in the API logs on first start:

```bash
docker compose logs api_web
```

### Include the mobile API

```bash
docker compose --profile mobile up -d --build
```

The mobile API is then available on port 8002.

### Common Docker commands

```bash
docker compose ps                  # see running services
docker compose logs -f api_web     # follow API logs
docker compose restart api_web     # restart one service
docker compose down                # stop everything (data is kept)
docker compose down -v             # stop AND delete the database volume (all data lost)
```

Database data is stored in the `db_data` Docker volume and survives restarts and `docker compose down`.

---

## Restore from a SQL backup (`evoting.sql`)

Use this to load an existing database dump, for example your working demo, instead of running `seed.py`. The dump restores the tables and data, including the admin account, positions, candidates and voters.

### Local MySQL

Create the empty `evoting` database first (see section 2, Step 1), then run from the folder containing `evoting.sql`:

```bash
mysql -u root evoting < evoting.sql
```

With a password, use `mysql -u root -p evoting < evoting.sql`.

- If `mysql` is not recognized (common with XAMPP/WAMP), use the full path, for example `/c/xampp/mysql/bin/mysql -u root evoting < evoting.sql` in Git Bash.
- Or use **phpMyAdmin**: select the `evoting` database, open **Import**, choose `evoting.sql`, and click **Go**.
- If the dump has no `DROP TABLE` statements and tables already exist, drop them first or import into a fresh database.

Then start the API and web app as usual. You do not need to run `seed.py` again.

### Docker

1. Put `evoting.sql` in the project root, next to `docker-compose.yml`.
2. In `docker-compose.yml`, under the `db` service `volumes`, uncomment the `evoting.sql` line:

   ```yaml
   volumes:
     - db_data:/var/lib/mysql
     - ./evoting.sql:/docker-entrypoint-initdb.d/evoting.sql:ro
   ```

3. Start from an empty database volume:

   ```bash
   docker compose down -v
   docker compose up -d --build
   ```

MySQL imports the file only on the first start, when the volume is empty, which is why `down -v` is needed. **This deletes any data already in the Docker database.** Leave `SEED_ARGS` empty in `.env` so the demo seed does not add duplicate data.

Keep the line commented out if `evoting.sql` is not in the project root, otherwise Docker creates an empty folder with that name.

### Notes

- **Admin login:** the admin password is the one stored in the dump, not `ADMIN_PASSWORD` from `.env`. That variable is only used when the admin account does not exist yet.
- **Voter PINs:** PINs are hashed in the dump and cannot be recovered. Regenerate them from the admin dashboard if they are lost.
- **Database name:** if the dump contains `CREATE DATABASE` or `USE` for a name other than `evoting`, edit that line or change `DATABASE_URL` to match.
- **Privacy:** a dump with real student data must never be public. `evoting.sql` is listed in `.gitignore`; keep it there.
- **Making a backup:** `mysqldump -u root evoting > evoting.sql` (Docker: `docker compose exec db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" evoting' > evoting.sql`).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | PostgreSQL on localhost | SQLAlchemy connection string |
| `JWT_SECRET` | `dev-only-secret-change-me` | Token signing key. **Always change it.** |
| `WEB_JWT_MINUTES` | `60` | Web login lifetime |
| `MOBILE_JWT_MINUTES` | `120` | Mobile login lifetime |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed browser origins |
| `ADMIN_USERNAME` | `admin` | Used by `seed.py` |
| `ADMIN_PASSWORD` | `ChangeMe123!` | Used by `seed.py` |
| `VITE_API_URL` | empty | Web build only: full URL of the web API when it is on a different host |

---

## Running an election

1. **Settings**: sign in as admin and set the institution name, election title, logo and colour.
2. **Positions and candidates**: add positions and aspirants. This is only possible while the election is in `draft`.
3. **Voters**: import a CSV with the columns `matric_no, full_name, email, department, level`, then download the generated PIN list and distribute the PINs securely.
4. **Open voting**: go to Settings and click **Open voting**. Voters cannot log in before this. Watch the **Live monitor** (refreshes every 3 seconds) and **Analytics**.
5. **Close voting**: click **Close voting** when the election ends. Optionally tick "show final results to voters" for the mobile app.

Before the real election, run a dry run with a few real students, then use **Settings → Clear all votes**.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `bash: .venvScriptsactivate: command not found` | In Git Bash use forward slashes: `source .venv/Scripts/activate` |
| `ModuleNotFoundError: No module named 'sqlalchemy'` | Activate the virtual environment, then run `pip install -r requirements.txt` |
| `uvicorn: command not found` | Run `python -m uvicorn api_web.main:app --port 8001 --reload` |
| `Can't connect to MySQL server` | MySQL is not running. Start it (XAMPP/WAMP/Services) or check the host and port. |
| `Unknown database 'evoting'` | Create the database, or fix the name in `DATABASE_URL`. |
| `Access denied for user 'root'` | Check the password in `DATABASE_URL`. |
| `cryptography package is required` | Run `pip install cryptography`. |
| Backend tries to reach PostgreSQL | `backend/.env` is missing or `DATABASE_URL` is not set. |
| Voters cannot log in | The election is still in `draft`. Click **Open voting** in Settings. |
| Docker: web API unreachable | Run `docker compose logs api_web`. The database may still be starting. |
| Docker: changed `.env` has no effect | Run `docker compose up -d --force-recreate`. |
| Docker: `evoting.sql` was not imported | It only imports into an empty volume. Run `docker compose down -v`, then start again. |
| Docker: forgot to save demo PINs | Run `docker compose down -v` and start again to reseed. This deletes all data. |

---

## Before real use

- Serve the site over **HTTPS** (nginx, Caddy or your host's TLS) and set a strong `JWT_SECRET`.
- Do not use a passwordless database root account outside your own machine. Use a dedicated database user with a strong password.
- Add **login rate limiting** (for example `slowapi` or nginx `limit_req`). It is not built in yet.
- Restrict `CORS_ORIGINS` to your real domain.
- Change the default `ADMIN_PASSWORD` and back up the database regularly.
