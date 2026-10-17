# SUG/SRC e-Voting System

A secure online voting system for Student Union Government (SUG) and Students' Representative Council (SRC) elections. Voters turn on their location, enter their matric number, receive a one-time code by email or SMS, and vote once from a browser or the mobile app. The election committee opens and closes voting, monitors turnout live, manages candidates and prints a forensic report from an admin dashboard.

## Features

- **Location gate**: the web and mobile apps ask the voter to turn location ON before anything else
- **OTP sign-in**: matric number, then a 6-digit code by **email or SMS** (the voter's choice), sent only to the contact already stored for that voter
- **One vote per voter**, enforced by the database
- **Voter web app** and **mobile app** (Flutter) run side by side, each with its own API on the same database
- **Admin dashboard**: **Email & SMS settings page** (SMTP, SMS provider, code rules, test buttons), open/close voting, live monitor and analytics, add/upload/delete candidates (with photo upload), voter CSV import, settings and branding with **school logo upload**
- **Forensic report**: every vote with voter details, IP address, latitude/longitude, device and OTP channel, with Print and CSV export
- **Security events log**: failed lookups, OTP sends and failures, votes cast, report views
- **Election lifecycle**: `draft` → `open` → `closed`, with the ballot locked once voting starts
- **Branding**: institution name, election title, logo and theme colour are configurable from the dashboard

## How integrity is enforced

- `vote_receipts.voter_id` is `UNIQUE`, so a double vote is rejected by the database itself, even under concurrent requests.
- The receipt and the votes are written in a single transaction. The `votes` table has no voter column, which keeps the ballot secret.
- The ballot (positions and candidates) locks once the election leaves `draft`.
- Sign-in codes are 6 digits, stored hashed (bcrypt), valid for 5 minutes, single use, with 5 wrong guesses allowed before the session locks.
- A code only works for the sign-in session that requested it. The voting token carries the session id, so it cannot be used by another voter, on the other app, or after the vote is cast.
- Code requests are rate limited per voter and per IP, and unknown matric numbers are limited per IP.
- **Forensic design (Option A):** the report proves who voted, when, from where and on which device. It never shows who they voted for: `votes` has no voter column and `vote_receipts` has no candidate column.
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
│   ├── core/
│   │   ├── models.py        Tables, including auth_sessions and audit_log
│   │   ├── services.py      Voting rules, results, voter and candidate import
│   │   ├── otp.py           Sign-in flow: lookup, send code, verify, session checks
│   │   ├── notify.py        Sends email (SMTP) and SMS (Termii / Africa's Talking / Twilio)
│   │   ├── delivery.py      Dashboard-managed SMTP/SMS/OTP settings, encrypted secrets, readiness
│   │   ├── geo.py           Coordinate validation and optional campus geofence
│   │   ├── audit.py         Audit log, client IP, forensic report queries
│   │   ├── voter_router.py  Voter routes shared by both APIs
│   │   ├── migrate.py       Adds new columns to older databases automatically
│   │   └── security.py, config.py, db.py, schemas.py, errors.py
│   ├── api_web/       WEB API    -> /api/web/*     voters + admin dashboard   (port 8001)
│   ├── api_mobile/    MOBILE API -> /api/mobile/*  voters only                (port 8002)
│   ├── tests/         pytest suite (OTP flow, limits, forensic report, imports)
│   ├── seed.py        Creates tables, the first admin, and optional demo data
│   ├── requirements.txt, requirements-dev.txt
│   └── Dockerfile
├── web/               React + Vite app (voter site and admin dashboard)
│   ├── src/lib/geo.js          Location permission gate and position reader
│   ├── src/pages/VoterLogin.jsx  4-step sign-in: location, matric, delivery, code
│   ├── src/admin/Forensics.jsx   Forensic report with print and CSV export
│   ├── src/admin/Delivery.jsx    Email & SMS settings page with test buttons
│   ├── Dockerfile
│   └── nginx.conf
├── mobile/            Flutter app (see mobile/README.md)
├── docker-compose.yml
├── .env.example       Settings for Docker Compose
└── evoting.sql        Optional database backup (not committed to Git) request for it
```

The web and mobile APIs are separate but share one database, so anything the admin changes in the dashboard (institution name, positions, candidates, election status) appears in both apps immediately.

---
## System Architecture
![Architecture](<E-Voting System Architecture and Process Flow.png>)

## Voter sign-in and voting flow

Same on web and mobile:

1. **Turn on location.** The app asks for permission and does not continue until it is granted. It reads latitude, longitude and accuracy. Browsers only allow this on HTTPS pages (`http://localhost` is exempt).
2. **Matric number.** The server checks that the voter exists, is active, has not voted, and that voting is **open**. It opens a sign-in session and returns the delivery options with masked contacts (for example `o***@gmail.com`, `+234*******111`). Only options for which the database holds a contact, and which are configured, are offered.
3. **Choose email or SMS.** A 6-digit code is sent to the email or phone already stored for the voter. The voter cannot type a different address.
4. **Enter the code.** It is checked against the same session. On success the app receives a short-lived voting token tied to that session.
5. **Vote.** The ballot loads, the voter reviews and submits. The receipt (with IP, position and device), the votes, and the session update commit in one transaction. A second attempt is refused.

```
Voter app --> /auth/lookup --> /auth/otp/send --> /auth/otp/verify --> /ballot --> /vote
 (location)    session id       code by email/SMS   token + session id   (guarded)   receipt + forensic data
```

If voting is not open, sign-in stops at step 2 with a clear message, so no SMS or email is wasted.

---

## 1. Clone the repository

```bash
git clone git pull origin main --allow-unrelated-histories --no-rebase --no-edit
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

# Print one-time codes in the API console instead of sending them (LOCAL TESTING ONLY)
OTP_DEV_MODE=true
```

All other settings (email, SMS, geofence, limits) are in `backend/.env.example`; see [Email and SMS delivery](#email-and-sms-delivery).

If your database password contains special characters such as `@` or `#`, URL-encode them (`@` becomes `%40`).

If you use MySQL only, you can delete the `psycopg2-binary` line from `requirements.txt` if it fails to install.

Create the tables, the admin account and (optionally) demo data:

```bash
python seed.py --demo
```

`--demo` adds sample positions, candidates and five voters (`DEMO/001` to `DEMO/005`, emails `demo1@example.com` to `demo5@example.com`, phones `08010000001` to `08010000005`). With `OTP_DEV_MODE=true` their one-time codes are printed in the API console (`[DEV OTP] DEMO/001 via email: 123456`). Run `python seed.py` without `--demo` for a clean database with only the admin account.

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
| `OTP_DEV_MODE` | `true` prints codes in the `api_web` logs (testing). Set `false` and fill the SMTP/SMS settings for a real election. |

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

### Step 4: Sign in as a demo voter

With `SEED_ARGS=--demo` and `OTP_DEV_MODE=true`, open the voter site, allow location, enter `DEMO/001`, choose Email, and read the code from the logs:

```bash
docker compose logs -f api_web
```

Open voting first (admin, Settings, Open voting). Over plain `http://` the browser only allows location on `localhost`; a phone or another PC needs HTTPS.

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
- **Older dumps:** a dump made before the OTP release has no `phone` column or forensic columns. They are added automatically when the API starts (see Upgrading an existing database). Then re-import your voter CSV with a `phone` column to fill in phone numbers.
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
| `LOCATION_REQUIRED` | `true` | Voters must share their location to sign in and vote |
| `GEOFENCE_LAT` / `GEOFENCE_LNG` / `GEOFENCE_RADIUS_M` | `0` | Optional campus area. Radius `0` switches it off. |
| `OTP_TTL_MINUTES` | `5` | How long a code stays valid |
| `OTP_MAX_ATTEMPTS` | `5` | Wrong codes before the session locks |
| `OTP_SEND_LIMIT` / `OTP_SEND_WINDOW_MINUTES` | `3` / `10` | Codes per voter per window |
| `OTP_IP_SEND_LIMIT` / `LOOKUP_FAIL_LIMIT` | `15` / `10` | Codes, and unknown matric numbers, per IP per window |
| `SESSION_MINUTES` / `VOTE_TOKEN_MINUTES` | `15` / `30` | Sign-in session and voting token lifetime |
| `OTP_DEV_MODE` | `false` | Print codes in the console instead of sending. **Never use in a real election.** |
| `TRUST_PROXY` | `false` | Read the voter IP from `X-Forwarded-For`. Only `true` behind your own nginx/proxy (Docker sets it for the web API). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | empty / `587` | Email delivery |
| `SMS_PROVIDER`, `SMS_API_KEY`, `SMS_USERNAME`, `SMS_SENDER_ID` | empty | SMS delivery |
| `DEFAULT_COUNTRY_CODE` | `234` | Turns `0801...` into `+234801...` |
| `UPLOAD_DIR` | `backend/uploads` | Where logo and candidate photos are stored (Docker: the `uploads` volume) |
| `MAX_UPLOAD_MB` | `2` | Largest accepted image |

---

## Email and SMS delivery

**Easiest: use the dashboard.** Sign in as admin and open **Email & SMS** in the menu. There you can:

- enter the SMTP details (host, port, username, password, from address, STARTTLS);
- choose the SMS provider (Termii, Africa's Talking or Twilio) and fill in its fields;
- set how long a code lasts, how many wrong tries lock a session, and how many codes a voter can request;
- switch **Test mode** on or off (codes are printed in the server console instead of being sent);
- press **Send test email** / **Send test SMS** to check the details before election day.

Changes apply immediately; no restart or `.env` edit is needed. Passwords and API keys are stored **encrypted** in the database (key derived from `JWT_SECRET`) and are never shown again. If you later change `JWT_SECRET`, enter the passwords and keys again. A value saved in the dashboard overrides the `.env` value; fields still using `.env` are marked "from .env". Channels that are not set up are not offered to voters.

**Alternative: `.env`.** The same settings can be given in `backend/.env` (see the table above); useful for the first start or for Docker deployments managed by a system administrator.

**Email (SMTP)** works with any provider that gives SMTP details (for example Brevo, SendGrid, Mailgun, a school mail server, or a Gmail app password):

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=apikey-or-username
SMTP_PASSWORD=secret
SMTP_FROM=votes@yourschool.edu.ng
```

**SMS** supports three providers:

| Provider | API key field | Username field | Sender field |
|---|---|---|---|
| Termii | API key | not used | approved sender ID |
| Africa's Talking | API key | app username | optional sender ID |
| Twilio | auth token | account SID | your Twilio number |

The gateway calls follow each provider's public API as I understand it; use **Send test SMS** to confirm your account works. Nigerian networks usually require a registered sender ID for SMS.

---

## Upgrading an existing database

If your database was created before this release (for example from `evoting.sql`), just start the API. On start-up it creates the new tables (`auth_sessions`, `audit_log`) and adds the new columns (`voters.phone` and the forensic columns on `vote_receipts`). Nothing is deleted and it is safe to run repeatedly.

After upgrading:

1. Re-import your voter CSV with the `phone` column. Existing voters keep their record and get their email/phone updated; new ones are added. Or edit a single voter with **Edit contact** on the Voters page.
2. The old PIN login is gone: voters now sign in with the OTP flow.
3. Votes cast before the upgrade have no IP or location, so they appear as **No location** in the forensic report.

---

## Logo and candidate photos

- **School logo:** Admin, **Settings**, School logo, choose an image. It shows on the voter pages and in the mobile app straight away. **Remove** puts the initial-letter placeholder back.
- **Candidate photos:** Admin, **Positions & candidates**, Add candidate or Edit, choose a photo. Photos can only be changed while the election is a draft, because they are part of the ballot.
- **Accepted:** PNG, JPG, GIF or WebP up to 2 MB (`MAX_UPLOAD_MB`). The type is checked from the file contents, so renaming a file does not get around it. SVG is refused because it can carry scripts.
- **Storage:** files are saved in `backend/uploads/` (Docker: the `uploads` volume, shared by both APIs) and served at `/api/web/uploads/...` and `/api/mobile/uploads/...`. The database stores only the path. Replacing or removing an image deletes the old file. Back up this folder with the database.
- **CSV:** `photo_url` in the candidate CSV still accepts a full web link. Uploaded images are added afterwards with the photo button.

---

## Forensic report

Admin dashboard, **Forensic report**. Each row is one vote receipt:

| Column | Meaning |
|---|---|
| Time, Receipt | When the vote was cast and the receipt code the voter saw |
| Matric no., Name, Dept, Level, Email, Phone | Voter details |
| App | `web` or `mobile` |
| OTP via | `email` or `sms` |
| IP address | Taken from the request (from `X-Forwarded-For` only if `TRUST_PROXY=true`) |
| Latitude, Longitude, Accuracy | Position reported by the voter's device when voting, with a link to the map |
| Device | Short id stored in the browser or app; the same device across several voters is flagged |
| Flags | **Shared IP**, **Shared device**, **No location** |

Use **Print report** (A4 landscape, with a header) or **Download CSV**. The **Security events** tab lists failed lookups, OTP sends and failures, votes cast and report views.

Notes:

- The report does **not** show who anyone voted for. That is deliberate (secret ballot). Linking a vote to a voter would be a different design with legal and trust consequences, so it is not included.
- Device location can be faked. Treat it as evidence to compare with the IP address, not proof. Several students on one campus network will legitimately share an IP, so **Shared IP** is a prompt to look, not proof of fraud.
- Location, IP and device are personal data. Tell voters (the sign-in screen has a notice), limit who has admin access, and delete the data when your retention period ends (**Settings, Clear all votes** also clears sessions and the audit log).

---

## CSV formats

**Voters** (`Voters` page, Import):

```csv
matric_no,full_name,email,phone,department,level
CSC/2024/001,Amina Yusuf,amina@example.com,08012345678,Computer Science,ND2
```

Phone numbers are normalised to international format (`08012345678` becomes `+2348012345678`). A voter needs an email, a phone, or both. Re-importing updates the email and phone of existing matric numbers.

**Candidates** (`Positions & candidates` page, Upload candidates; only before voting opens):

```csv
position,full_name,department,level,manifesto,photo_url
President,Amina Yusuf,Computer Science,ND2,Better welfare,
Vice President,Chidi Okafor,Accountancy,HND1,,
```

Positions that do not exist yet are created. Candidates already listed for a position are skipped.

---

## Tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

The suite uses a temporary SQLite database and captures codes in memory, so nothing is sent. It covers the full web and mobile flows, location and open-voting checks, masking, wrong/expired codes, session binding, rate limits, token separation, the forensic report, and the CSV imports. CI runs it on every pull request.

---

## Running an election

1. **Settings**: sign in as admin and set the institution name, election title, logo and colour.
2. **Positions and candidates**: add positions and aspirants. This is only possible while the election is in `draft`.
3. **Voters**: import a CSV with `matric_no, full_name, email, phone, department, level`. Check that every voter has an email or a phone; the Voters page marks missing contacts in red.
4. **Open voting**: go to Settings and click **Open voting**. Voters cannot sign in before this. Watch the **Live monitor** (refreshes every 3 seconds) and **Analytics**.
5. **Close voting**: click **Close voting** when the election ends. Optionally tick "show final results to voters" for the mobile app.
6. **Forensic report**: open **Forensic report** to review flags, then print it or download the CSV for the electoral committee.

Before the real election, run a dry run with a few real students (with real email/SMS delivery, not dev mode), then use **Settings → Clear all votes**.

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
| Voters cannot sign in | The election is still in `draft`. Click **Open voting** in Settings. |
| "Turn on location" never goes away | Allow location for the site (padlock beside the address). Browsers block location on plain `http://` except `localhost`; use HTTPS. |
| "No email or phone number is on record" | The voter really has neither. Import the CSV with `email` and `phone` columns, or use **Edit contact**. |
| "Code delivery (email/SMS) is not set up yet" | The voter has contacts but no sending service is set up. Open **Email & SMS** in the admin menu: switch on Test mode for local testing, or fill in SMTP / the SMS provider and use the test buttons. No restart needed. |
| Uploaded logo or photo does not show | Restart the web app after updating. In Docker, uploads are in the `uploads` volume; `docker compose down -v` deletes them. Behind nginx, `client_max_body_size` must be at least 3m (already set in `web/nginx.conf`). |
| The voter is only offered one of email/SMS | The other has no contact on record, or that channel is not configured (SMTP / SMS settings). |
| No code arrives | With `OTP_DEV_MODE=true` codes are only printed in the API console. Otherwise check `SMTP_*` / `SMS_*` and the API logs. |
| "Too many codes requested" | Limit is 3 per voter per 10 minutes (`OTP_SEND_LIMIT`). Wait, or raise it for a test. |
| Every vote shows the same IP | The API sees nginx's address. Set `TRUST_PROXY=true` (Docker does this for the web API). |
| Docker: web API unreachable | Run `docker compose logs api_web`. The database may still be starting. |
| Docker: changed `.env` has no effect | Run `docker compose up -d --force-recreate`. |
| Docker: `evoting.sql` was not imported | It only imports into an empty volume. Run `docker compose down -v`, then start again. |

---

## Before real use

- Serve the site over **HTTPS** (nginx, Caddy or your host's TLS) and set a strong `JWT_SECRET`.
- Do not use a passwordless database root account outside your own machine. Use a dedicated database user with a strong password.
- Set `OTP_DEV_MODE=false`, configure SMTP and/or SMS, and send yourself a test code. Test with a real phone on the networks your students use.
- Rate limits for codes and unknown matric numbers are built in; add nginx `limit_req` as well for the admin login, which has none.
- Restrict `CORS_ORIGINS` to your real domain.
- Change the default `ADMIN_PASSWORD` and back up the database regularly.
- Show voters a privacy notice: location, IP address and device are stored with each vote receipt (Nigeria Data Protection Act 2023). Keep admin access to the forensic report to the electoral committee.
