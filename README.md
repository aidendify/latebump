# LateBump

Free, self-hosted running-late pings for local service owners. Job runs long — tap delay, draft the customer SMS with a new ETA, send or copy, keep an audit log.

No signup. No license. One Docker Compose service and a SQLite file. About 15 minutes on a 1GB VPS.

## What it does

- Create a lightweight job (customer name, optional phone/email, title/ref, scheduled window, site, notes)
- Job detail: big **Running late** — presets +15/+30/+45/+60/+90 or a custom new ETA
- Optional **Offer reschedule** line (BUSINESS_PHONE or “reply to this message”)
- Template draft (no LLM); owner edits before send — edits are what get logged/sent
- **Copy SMS / Copy email** always (clipboard + audit). Optional BYO Twilio SMS and/or SMTP email
- Mark job `delayed` on first successful send or explicit copy / mark-delayed
- Append-only bump audit (channel `sms`|`email`|`copy`, masked destination, ok/fail)
- `GET /health` → HTTP 200 `{"status":"ok","smtp_configured":false,"sms_configured":false}` even when SMTP/Twilio unset
- No GPS, no FSM/CRM, no appointment-reminder drips, no customer magic status page

Without SMTP or Twilio you still draft and copy the delay message. Product is fully usable via Copy alone.

## Privacy

Self-hosted. You run the box; the owner is the data controller for customer contact fields. No Stripe, no bundled SMS numbers, no third-party analytics SaaS. Data lives in your SQLite file on the Compose volume. Secrets are never logged.

## 15-minute Ubuntu VPS install

Documented on **Ubuntu 22.04 / 24.04**. About 15 minutes.

**Debian 13:** do **not** run the Ubuntu `docker-ce` recipe below on Debian. Use the distro packages instead:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker "$USER"
```

Log out and back in (or `newgrp docker`). On Debian, start the stack with `docker-compose` (hyphen) if `docker compose` is not available.

**Amazon Linux:** not documented yet. Use Ubuntu or Debian.

### 1. Install Docker Engine and the Compose plugin (Ubuntu only)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo ${UBUNTU_CODENAME:-$VERSION_CODENAME}) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and back in (or run `newgrp docker`) so `docker` works without `sudo`.

### 2. Clone, configure, start

```bash
git clone https://github.com/aidendify/latebump.git
cd latebump
cp .env.example .env
```

Edit `.env` and set at least `BUSINESS_NAME`, `PUBLIC_BASE_URL`, `SECRET_KEY`, and `OWNER_PASSWORD`. Leave `SMTP_*`, Twilio, and `MARKETING_URL` empty unless configured. Set `OWNER_PASSWORD` on any VPS reachable from the internet (empty means the admin UI is open).

```bash
docker compose up --build -d
```

(On Debian, `docker-compose up --build -d` if the Compose plugin is not installed.)

The app binds `0.0.0.0:8080` in the container. Compose maps host `8080:8080`. SQLite lives on the `latebump-data` volume at `/data/latebump.db`.

### 3. Smoke test

Use this `.env` for a first pass (Verifier values). Production should use a real `SECRET_KEY` and `OWNER_PASSWORD`. Do not bake these test passwords as production defaults.

```
OWNER_PASSWORD=testpass
BUSINESS_NAME=Harbor HVAC
PUBLIC_BASE_URL=http://localhost:8080
MARKETING_URL=
SECRET_KEY=change-me
TZ=UTC
```

Leave all `SMTP_*` and Twilio vars unset.

1. Healthcheck:

   ```bash
   curl -sf http://localhost:8080/health
   ```

   Expected: JSON containing `"status":"ok"`, `"smtp_configured":false`, `"sms_configured":false`, HTTP 200.

2. Open http://localhost:8080, log in with `testpass`, create a job (e.g. Jordan Smith — furnace tune-up, window 1–3pm).

3. On the job detail page, tap **Running late**, pick **+30**, **Draft message**. Confirm the draft includes the customer first name, Harbor HVAC, and a new ETA. Optionally enable **Offer reschedule**.

4. Tap **Copy SMS · Mark delayed**. Confirm a bump appears in the audit with `channel=copy` and ok. Send SMS / Send email controls are disabled without Twilio/SMTP — no crash.

## Configuration

Copy `.env.example` to `.env` before `docker compose up`. Variables:

| Variable | Purpose |
| --- | --- |
| `PORT` | Documented as 8080. The container always binds gunicorn to `0.0.0.0:8080`. |
| `DATABASE_PATH` | SQLite file. Compose overrides this to `/data/latebump.db`. |
| `SECRET_KEY` | Flask session key. Change it on a public VPS. |
| `OWNER_PASSWORD` | Admin login. Empty = open admin (local/dev). Set this on any internet-reachable VPS. |
| `BUSINESS_NAME` | Used in the delay draft template. |
| `BUSINESS_PHONE` | Optional; used in the reschedule offer line. |
| `PUBLIC_BASE_URL` | No trailing slash. Optional links / email footers, e.g. `http://localhost:8080`. |
| `TZ` | Default `UTC`. Used when computing “now + N minutes” for ETA text. |
| `FROM_NAME`, `FROM_EMAIL` | SMTP From / email sign-off. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS` | Optional email send. |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | Optional SMS. |
| `OWNER_NOTIFY_EMAIL` | Optional owner copy when a bump is sent (needs SMTP). |
| `MARKETING_URL` | Optional footer “Powered by LateBump”. Empty = no footer. |

Never commit `.env`. Never log secrets.

## Local tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
OWNER_PASSWORD=testpass BUSINESS_NAME="Harbor HVAC" PUBLIC_BASE_URL=http://localhost:8080 MARKETING_URL= SECRET_KEY=test DATABASE_PATH=/tmp/latebump-pytest.db python -m unittest test_app.py -v
```

## License

MIT — free to self-host and modify.
