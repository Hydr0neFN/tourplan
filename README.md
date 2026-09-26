**English** · [繁體中文](README.zh-TW.md)

# 揪日子 tourplan

**A tiny self-hosted date-picking app for group trips — built for families, including the least tech-savvy members.**
<img width="503" height="861" alt="image" src="https://github.com/user-attachments/assets/d457e1fe-2d1f-4dbe-b010-eb2190a90c7d" />

<img width="867" height="866" alt="image" src="https://github.com/user-attachments/assets/b54eff93-ca3a-41a1-b8a5-8751dbc59c90" />

一個超輕量的「揪團選日子」網頁app：主辦人開一個規劃、圈出可選的日期範圍，家人朋友點開連結、點日期表達「可以／不行」，主辦人一眼看出哪天最多人有空。專為手機與長輩設計。

Think Doodle/When2meet, but: reversed defaults (every day starts as *available*, you tap to *deny*), binary votes only, emoji avatars instead of accounts, and simple enough for grandparents.

## Features

- **Tap to toggle** — every plannable day starts green (可以). Tap it once → red (不行). Tap again → back. No forms, no drag-select, nothing to get lost in.
- **No visitor accounts** — visitors optionally enter a name (or skip). Identity is a signed cookie; returning visitors keep their votes. Nameless visitors get an emoji nickname from a 24-icon pool (小花 🌸, 小蛙 🐸, …).
- **Glanceable aggregates** — each day cell shows who *can* attend as a tiny emoji row (`🐸+2` overflow); who can't is deliberately kept out of the cells (mixed rows confused elderly testers) and lives in the participant list instead.
- **Per-person summary** — participant list shows each person's "not OK" dates as compressed ranges (`8/11、14–15`); tap to expand full detail. Designed so a mis-tap never changes state — elderly-safe.
- **Multi-month calendars** — range can span months; they stack vertically (2-up on desktop).
- **Multiple concurrent plans** — each plan gets an unguessable link (`/t/<slug>`); host runs as many as needed.
- **Voting deadline (截止收單)** — optional per-plan cutoff date (Taiwan time, inclusive); voting locks automatically, plus a manual close/reopen toggle.
- **Anonymity switch** — per-plan: show real names, or show everyone as emoji nicknames (host results always show real names).
- **Multi-host** — multiple admin accounts on one instance; each host sees and manages only their own plans. Hosts can remove a participant (and their votes) straight from the results table — handy for phantom identities created by incognito windows or cleared cookies.
- **First-visit tutorial** — 3-step overlay, replayable via the `?` button.
- **Bilingual** — 繁體中文（台灣）default, English toggle, per-user cookie.
- **Near-realtime** — 5-second polling + instant refresh when the tab regains focus; all responses `Cache-Control: no-store` so mobile browsers never show stale votes.

## Stack

FastAPI · SQLite (WAL) · Jinja2 · vanilla JS. No build step, no Node, no accounts database — one `pip install`, ~50 MB RAM. Runs happily on a Raspberry Pi.

Passwords are scrypt-hashed (stdlib), sessions and visitor tokens are HMAC-signed cookies, admin forms are CSRF-protected, and login/join endpoints are rate-limited. The app binds to loopback only — put a reverse proxy or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) in front of it.

## Quickstart

```bash
git clone https://github.com/<you>/tourplan && cd tourplan
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m uvicorn app.main:app --port 8100   # first start: see below
```

There is no default login. On the first start (no admin exists yet) the app refuses to start unless `TOURPLAN_ADMIN_PASSWORD` (≥ 8 chars; optionally `TOURPLAN_ADMIN_USER`, default `admin`) is set, and creates that admin from it:

```bash
TOURPLAN_ADMIN_PASSWORD='something-long' .venv/bin/python -m uvicorn app.main:app --port 8100
```

Open `http://127.0.0.1:8100/admin`, log in, create a plan, copy its link, share it. Later starts ignore the variable once an admin exists — drop it.

## Deploy (Raspberry Pi / any Debian-ish box + Cloudflare Tunnel)

```bash
# on the box
sudo apt install -y python3-venv sqlite3
git clone https://github.com/<you>/tourplan /root/tourplan
cd /root/tourplan
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# service user + permissions for the hardened unit (see "Hardened service" below)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin tourplan
mkdir -p data && sudo chmod -R go+rX,go-w /root/tourplan
sudo chown -R tourplan:tourplan data && sudo chmod 700 data && sudo chmod -f 600 data/*

# first-start admin credentials, root-only
printf 'TOURPLAN_ADMIN_PASSWORD=%s\n' 'something-long' | sudo install -m 600 /dev/stdin /etc/tourplan.env

# systemd
sudo cp deploy/tourplan.service /etc/systemd/system/
sudo nano /etc/systemd/system/tourplan.service   # set TOURPLAN_BASE_URL + paths for your box
sudo systemctl daemon-reload && sudo systemctl enable --now tourplan
```

**Hardened service.** The unit runs as the unprivileged `tourplan` user with no capabilities, a read-only OS, and `/root` + `/home` hidden behind an empty tmpfs: only the app directory is mapped back (read-only) and only `data/` is writable. An exploit in the app therefore cannot read other services' secrets on a shared box (e.g. `/root/.env`) or touch the rest of the host. After changing the code on the box, re-run the `chmod go+rX` line so the service user can read it.

Cloudflare Tunnel ingress (above the catch-all in `/etc/cloudflared/config.yml`):

```yaml
- hostname: plan.example.com
  service: http://localhost:8100
```

Recommended hardening: add a Cloudflare WAF rule geo-restricting `/admin*` to your country.

Nightly backup (SQLite online backup, 7 rotating copies):

```cron
15 4 * * * sqlite3 /root/tourplan/data/tourplan.db ".backup /root/backups/tourplan-$(date +\%a).db"
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `TOURPLAN_BASE_URL` | request-derived | Public base URL used by the admin "copy link" button; an `https://` value also turns on `Secure` cookies and HSTS |
| `TOURPLAN_ADMIN_PASSWORD` | — | First start only: password for the initial admin (≥ 8 chars). Required while no admin exists |
| `TOURPLAN_ADMIN_USER` | `admin` | First start only: username for the initial admin |
| `TOURPLAN_MAX_VISITORS` | `60` | Max participants per plan |

All state lives in `data/`: `tourplan.db` (SQLite) and `secret.key` (cookie-signing key — losing it logs everyone out; leaking it lets anyone forge sessions).

## Design notes

- **Deny-only storage** — joining a plan means "all days OK"; only denials are stored. The common case (most people free most days) is zero rows.
- **No highlight mode** — tapping a participant never restyles the calendar (an earlier design did; it confused elderly testers when mis-tapped). Availability detail renders as plain text ranges instead.
- **Timezone** — deadlines evaluate against UTC+8 (Taiwan) regardless of server timezone.

## License

MIT — see [LICENSE](LICENSE).
