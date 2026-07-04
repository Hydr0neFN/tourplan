"""tourplan — family tour date-picking app (FastAPI + SQLite)."""
import datetime
import os
import pathlib
import secrets
import sqlite3

from fastapi import Body, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, db, icons
from .i18n import MONTH_NAMES_EN, STRINGS, pick_lang

BASE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="tourplan", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

MAX_RANGE_DAYS = 370
MAX_NAME_LEN = 20
VISITOR_COOKIE_DAYS = 180
MAX_VISITORS_PER_TOUR = int(os.environ.get("TOURPLAN_MAX_VISITORS", "60"))


def client_ip(request: Request) -> str:
    """Real client IP behind cloudflared (app binds loopback, headers trustworthy)."""
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "?")
    )


def external_base_url(request: Request) -> str:
    return os.environ.get("TOURPLAN_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")


TW_TZ = datetime.timezone(datetime.timedelta(hours=8))


def tour_open_now(tour: sqlite3.Row) -> bool:
    """Open = manual status open AND deadline (inclusive, Taiwan time) not passed."""
    if tour["status"] != "open":
        return False
    deadline = tour["deadline"]
    if deadline:
        return datetime.datetime.now(TW_TZ).date().isoformat() <= deadline
    return True


def jresp(data: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status_code, headers={"Cache-Control": "no-store"})


@app.on_event("startup")
def startup() -> None:
    db.init()
    con = db.connect()
    try:
        if con.execute("SELECT COUNT(*) c FROM admins").fetchone()["c"] == 0:
            con.execute(
                "INSERT INTO admins(username, pw_hash, must_change) VALUES(?,?,1)",
                ("admin", auth.hash_password("admin")),
            )
            con.commit()
    finally:
        con.close()


def lang_of(request: Request) -> str:
    return pick_lang(request.query_params.get("lang") or request.cookies.get("lang"))


def with_lang_cookie(request: Request, response: Response) -> Response:
    q = request.query_params.get("lang")
    if q:
        response.set_cookie("lang", pick_lang(q), max_age=365 * 86400, samesite="lax")
    return response


def page(request: Request, template: str, ctx: dict, status_code: int = 200) -> Response:
    lang = lang_of(request)
    ctx = {"request": request, "t": STRINGS[lang], "lang": lang, **ctx}
    resp = templates.TemplateResponse(request, template, ctx, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"
    return with_lang_cookie(request, resp)


# ---------------------------------------------------------------- visitor side

def month_name_en(m: int) -> str:
    return MONTH_NAMES_EN[m]


def parse_date(s: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def get_tour(con: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM tours WHERE slug=?", (slug,)).fetchone()


def get_visitor(con: sqlite3.Connection, tour_id: int, request: Request) -> sqlite3.Row | None:
    token = auth.signer.unsign(request.cookies.get(f"tpv_{tour_id}"))
    if not token:
        return None
    return con.execute(
        "SELECT * FROM visitors WHERE tour_id=? AND token=?", (tour_id, token)
    ).fetchone()


def visitor_labels(con: sqlite3.Connection, tour: sqlite3.Row) -> dict[int, dict]:
    """id -> {label_zh, label_en, icon} honoring show_names + anon icon-name numbering."""
    rows = con.execute(
        "SELECT * FROM visitors WHERE tour_id=? ORDER BY id", (tour["id"],)
    ).fetchall()
    seen: dict[int, int] = {}
    out: dict[int, dict] = {}
    for r in rows:
        anonymous_display = (not r["name"]) or (not tour["show_names"])
        if anonymous_display:
            seen[r["icon_idx"]] = seen.get(r["icon_idx"], 0) + 1
            ordinal = seen[r["icon_idx"]]
            label_zh = icons.anon_label(r["icon_idx"], ordinal, "zh")
            label_en = icons.anon_label(r["icon_idx"], ordinal, "en")
        else:
            label_zh = label_en = r["name"]
        out[r["id"]] = {
            "label_zh": label_zh,
            "label_en": label_en,
            "icon": icons.POOL[r["icon_idx"] % len(icons.POOL)]["emoji"],
        }
    return out


def tour_state(con: sqlite3.Connection, tour: sqlite3.Row, me: sqlite3.Row | None) -> dict:
    labels = visitor_labels(con, tour)
    denies: dict[int, list[str]] = {}
    for row in con.execute(
        "SELECT d.visitor_id, d.date FROM denies d "
        "JOIN visitors v ON v.id=d.visitor_id WHERE v.tour_id=? ORDER BY d.date",
        (tour["id"],),
    ):
        denies.setdefault(row["visitor_id"], []).append(row["date"])
    participants = [
        {
            "id": vid,
            "icon": info["icon"],
            "label_zh": info["label_zh"],
            "label_en": info["label_en"],
            "is_me": bool(me) and vid == me["id"],
            "denies": denies.get(vid, []),
        }
        for vid, info in labels.items()
    ]
    me_out = None
    if me:
        me_out = {
            "id": me["id"],
            "name": me["name"],
            "icon": icons.POOL[me["icon_idx"] % len(icons.POOL)]["emoji"],
            "denies": denies.get(me["id"], []),
        }
    return {
        "tour": {
            "slug": tour["slug"],
            "title": tour["title"],
            "description": tour["description"],
            "date_start": tour["date_start"],
            "date_end": tour["date_end"],
            "show_names": bool(tour["show_names"]),
            "status": tour["status"],
            "deadline": tour["deadline"],
            "open_now": tour_open_now(tour),
        },
        "me": me_out,
        "participants": participants,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(request, "index.html", {})


@app.get("/t/{slug}", response_class=HTMLResponse)
def tour_page(request: Request, slug: str):
    con = db.connect()
    try:
        tour = get_tour(con, slug)
        if not tour:
            return page(request, "not_found.html", {}, status_code=404)
        me = get_visitor(con, tour["id"], request)
        state = tour_state(con, tour, me)
    finally:
        con.close()
    return page(request, "tour.html", {"state": state, "icon_pool": icons.POOL})


@app.post("/t/{slug}/api/join")
def join(request: Request, slug: str, body: dict = Body(default={})):
    ip = client_ip(request)
    if not auth.join_throttle.allow(ip):
        return jresp({"error": "throttled"}, status_code=429)
    name = (str(body.get("name") or "")).strip()[:MAX_NAME_LEN] or None
    con = db.connect()
    try:
        tour = get_tour(con, slug)
        if not tour:
            return jresp({"error": "not_found"}, status_code=404)
        if not tour_open_now(tour):
            return jresp({"error": "closed"}, status_code=403)
        me = get_visitor(con, tour["id"], request)
        if not me:
            count = con.execute(
                "SELECT COUNT(*) c FROM visitors WHERE tour_id=?", (tour["id"],)
            ).fetchone()["c"]
            if count >= MAX_VISITORS_PER_TOUR:
                return jresp({"error": "full"}, status_code=403)
            auth.join_throttle.record(ip)
            used = {
                r["icon_idx"]
                for r in con.execute(
                    "SELECT icon_idx FROM visitors WHERE tour_id=?", (tour["id"],)
                )
            }
            free = [i for i in range(len(icons.POOL)) if i not in used]
            icon_idx = secrets.choice(free) if free else secrets.randbelow(len(icons.POOL))
            token = secrets.token_urlsafe(24)
            cur = con.execute(
                "INSERT INTO visitors(tour_id, name, icon_idx, token) VALUES(?,?,?,?)",
                (tour["id"], name, icon_idx, token),
            )
            con.commit()
            me = con.execute(
                "SELECT * FROM visitors WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        state = tour_state(con, tour, me)
    finally:
        con.close()
    resp = jresp(state)
    resp.set_cookie(
        f"tpv_{tour['id']}",
        auth.signer.sign(me["token"]),
        max_age=VISITOR_COOKIE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path=f"/t/{tour['slug']}",
    )
    return resp


@app.post("/t/{slug}/api/vote")
def vote(request: Request, slug: str, body: dict = Body(default={})):
    date = parse_date(str(body.get("date", "")))
    deny = bool(body.get("deny"))
    con = db.connect()
    try:
        tour = get_tour(con, slug)
        if not tour:
            return jresp({"error": "not_found"}, status_code=404)
        if not tour_open_now(tour):
            return jresp({"error": "closed"}, status_code=403)
        me = get_visitor(con, tour["id"], request)
        if not me:
            return jresp({"error": "not_joined"}, status_code=401)
        if (
            not date
            or date < datetime.date.fromisoformat(tour["date_start"])
            or date > datetime.date.fromisoformat(tour["date_end"])
        ):
            return jresp({"error": "bad_date"}, status_code=400)
        if deny:
            con.execute(
                "INSERT OR REPLACE INTO denies(visitor_id, date) VALUES(?,?)",
                (me["id"], date.isoformat()),
            )
        else:
            con.execute(
                "DELETE FROM denies WHERE visitor_id=? AND date=?",
                (me["id"], date.isoformat()),
            )
        con.commit()
        state = tour_state(con, tour, me)
    finally:
        con.close()
    return jresp(state)


@app.get("/t/{slug}/api/state")
def state(request: Request, slug: str):
    con = db.connect()
    try:
        tour = get_tour(con, slug)
        if not tour:
            return jresp({"error": "not_found"}, status_code=404)
        me = get_visitor(con, tour["id"], request)
        return jresp(tour_state(con, tour, me))
    finally:
        con.close()


# ---------------------------------------------------------------- admin side

def current_admin(request: Request) -> sqlite3.Row | None:
    admin_id = auth.read_admin_session(request.cookies.get("admsess"))
    if admin_id is None:
        return None
    con = db.connect()
    try:
        return con.execute("SELECT * FROM admins WHERE id=?", (admin_id,)).fetchone()
    finally:
        con.close()


def _session_nonce(request: Request) -> str:
    value = auth.signer.unsign(request.cookies.get("admsess")) or ""
    parts = value.split(":")
    return parts[3] if len(parts) == 4 else ""


def csrf_token(request: Request, admin_id: int) -> str:
    return auth.signer.sign(f"csrf:{admin_id}:{_session_nonce(request)}")


def csrf_ok(request: Request, admin_id: int, token: str | None) -> bool:
    value = auth.signer.unsign(token)
    return bool(value) and value == f"csrf:{admin_id}:{_session_nonce(request)}"


def admin_guard(request: Request) -> sqlite3.Row | RedirectResponse:
    admin = current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login", status_code=303)
    if admin["must_change"] and request.url.path != "/admin/password":
        return RedirectResponse("/admin/password", status_code=303)
    return admin


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if current_admin(request):
        return RedirectResponse("/admin", status_code=303)
    return page(request, "admin_login.html", {"error": None})


@app.post("/admin/login")
def admin_login(request: Request, username: str = Form(""), password: str = Form("")):
    ip = client_ip(request)
    if not auth.login_throttle.allow(ip):
        return page(request, "admin_login.html", {"error": "throttled"}, status_code=429)
    con = db.connect()
    try:
        row = con.execute(
            "SELECT * FROM admins WHERE username=?", (username.strip(),)
        ).fetchone()
    finally:
        con.close()
    if not row or not auth.verify_password(password, row["pw_hash"]):
        auth.login_throttle.record(ip)
        return page(request, "admin_login.html", {"error": "bad"}, status_code=401)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        "admsess",
        auth.make_admin_session(row["id"]),
        max_age=auth.ADMIN_SESSION_HOURS * 3600,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return resp


@app.post("/admin/logout")
def admin_logout(request: Request, csrf: str = Form("")):
    admin = current_admin(request)
    if admin and not csrf_ok(request, admin["id"], csrf):
        return RedirectResponse("/admin", status_code=303)
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie("admsess", path="/")
    return resp


@app.get("/admin/password", response_class=HTMLResponse)
def admin_password_page(request: Request):
    admin = current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login", status_code=303)
    return page(
        request,
        "admin_password.html",
        {"admin": admin, "csrf": csrf_token(request, admin["id"]), "error": None},
    )


@app.post("/admin/password")
def admin_password(
    request: Request,
    csrf: str = Form(""),
    new_password: str = Form(""),
    confirm: str = Form(""),
):
    admin = current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login", status_code=303)
    if not csrf_ok(request, admin["id"], csrf):
        return RedirectResponse("/admin/password", status_code=303)
    if len(new_password) < 8 or new_password != confirm or new_password == "admin":
        return page(
            request,
            "admin_password.html",
            {"admin": admin, "csrf": csrf_token(request, admin["id"]), "error": "weak"},
            status_code=400,
        )
    con = db.connect()
    try:
        con.execute(
            "UPDATE admins SET pw_hash=?, must_change=0 WHERE id=?",
            (auth.hash_password(new_password), admin["id"]),
        )
        con.commit()
    finally:
        con.close()
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin
    con = db.connect()
    try:
        tours = con.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM visitors v WHERE v.tour_id=t.id) n "
            "FROM tours t ORDER BY t.id DESC"
        ).fetchall()
    finally:
        con.close()
    base_url = external_base_url(request)
    return page(
        request,
        "admin_tours.html",
        {"admin": admin, "tours": tours, "csrf": csrf_token(request, admin["id"]),
         "base_url": base_url, "error": request.query_params.get("error")},
    )


@app.post("/admin/tours/create")
def admin_create_tour(
    request: Request,
    csrf: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    date_start: str = Form(""),
    date_end: str = Form(""),
    deadline: str = Form(""),
    show_names: str = Form("1"),
):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin
    if not csrf_ok(request, admin["id"], csrf):
        return RedirectResponse("/admin", status_code=303)
    title = title.strip()[:60]
    d0, d1 = parse_date(date_start), parse_date(date_end)
    if not title or not d0 or not d1 or d0 > d1 or (d1 - d0).days > MAX_RANGE_DAYS:
        return RedirectResponse("/admin?error=tour", status_code=303)
    dl = parse_date(deadline) if deadline.strip() else None
    con = db.connect()
    try:
        while True:
            slug = secrets.token_urlsafe(5)
            if not con.execute("SELECT 1 FROM tours WHERE slug=?", (slug,)).fetchone():
                break
        con.execute(
            "INSERT INTO tours(slug, title, description, date_start, date_end, show_names, deadline)"
            " VALUES(?,?,?,?,?,?,?)",
            (slug, title, description.strip()[:200], d0.isoformat(), d1.isoformat(),
             1 if show_names == "1" else 0, dl.isoformat() if dl else None),
        )
        con.commit()
    finally:
        con.close()
    return RedirectResponse("/admin", status_code=303)


def _tour_post(request: Request, tour_id: int, csrf: str):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin, None
    if not csrf_ok(request, admin["id"], csrf):
        return RedirectResponse("/admin", status_code=303), None
    return admin, tour_id


@app.post("/admin/tours/{tour_id}/toggle-status")
def admin_toggle_status(request: Request, tour_id: int, csrf: str = Form("")):
    admin, tid = _tour_post(request, tour_id, csrf)
    if isinstance(admin, RedirectResponse):
        return admin
    con = db.connect()
    try:
        con.execute(
            "UPDATE tours SET status = CASE status WHEN 'open' THEN 'closed' ELSE 'open' END"
            " WHERE id=?",
            (tid,),
        )
        con.commit()
    finally:
        con.close()
    return RedirectResponse(request.headers.get("referer") or "/admin", status_code=303)


@app.post("/admin/tours/{tour_id}/toggle-names")
def admin_toggle_names(request: Request, tour_id: int, csrf: str = Form("")):
    admin, tid = _tour_post(request, tour_id, csrf)
    if isinstance(admin, RedirectResponse):
        return admin
    con = db.connect()
    try:
        con.execute("UPDATE tours SET show_names = 1 - show_names WHERE id=?", (tid,))
        con.commit()
    finally:
        con.close()
    return RedirectResponse(request.headers.get("referer") or "/admin", status_code=303)


@app.post("/admin/tours/{tour_id}/delete")
def admin_delete_tour(request: Request, tour_id: int, csrf: str = Form("")):
    admin, tid = _tour_post(request, tour_id, csrf)
    if isinstance(admin, RedirectResponse):
        return admin
    con = db.connect()
    try:
        con.execute("DELETE FROM tours WHERE id=?", (tid,))
        con.commit()
    finally:
        con.close()
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/tours/{tour_id}", response_class=HTMLResponse)
def admin_tour_detail(request: Request, tour_id: int):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin
    con = db.connect()
    try:
        tour = con.execute("SELECT * FROM tours WHERE id=?", (tour_id,)).fetchone()
        if not tour:
            return RedirectResponse("/admin", status_code=303)
        visitors = con.execute(
            "SELECT * FROM visitors WHERE tour_id=? ORDER BY id", (tour_id,)
        ).fetchall()
        denies = {
            (r["visitor_id"], r["date"])
            for r in con.execute(
                "SELECT d.visitor_id, d.date FROM denies d "
                "JOIN visitors v ON v.id=d.visitor_id WHERE v.tour_id=?",
                (tour_id,),
            )
        }
    finally:
        con.close()
    lang = lang_of(request)
    seen: dict[int, int] = {}
    vis = []
    for v in visitors:
        if v["name"]:
            label = v["name"]
        else:
            seen[v["icon_idx"]] = seen.get(v["icon_idx"], 0) + 1
            label = icons.anon_label(v["icon_idx"], seen[v["icon_idx"]], lang)
        vis.append({
            "id": v["id"],
            "label": label,
            "emoji": icons.POOL[v["icon_idx"] % len(icons.POOL)]["emoji"],
        })
    d0 = datetime.date.fromisoformat(tour["date_start"])
    d1 = datetime.date.fromisoformat(tour["date_end"])
    days = []
    best = -1
    cur = d0
    while cur <= d1:
        iso = cur.isoformat()
        oks = [v["id"] for v in vis if (v["id"], iso) not in denies]
        best = max(best, len(oks))
        days.append({"iso": iso, "date": cur, "ok_ids": set(oks), "count": len(oks)})
        cur += datetime.timedelta(days=1)
    base_url = external_base_url(request)
    return page(
        request,
        "admin_tour_detail.html",
        {"admin": admin, "tour": tour, "visitors": vis, "days": days, "best": best,
         "csrf": csrf_token(request, admin["id"]), "base_url": base_url},
    )


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin
    con = db.connect()
    try:
        users = con.execute("SELECT id, username, created_at FROM admins ORDER BY id").fetchall()
    finally:
        con.close()
    return page(
        request,
        "admin_users.html",
        {"admin": admin, "users": users, "csrf": csrf_token(request, admin["id"]),
         "error": request.query_params.get("error")},
    )


@app.post("/admin/users/create")
def admin_create_user(
    request: Request,
    csrf: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin
    if not csrf_ok(request, admin["id"], csrf):
        return RedirectResponse("/admin/users", status_code=303)
    username = username.strip()[:30]
    if not username or len(password) < 8:
        return RedirectResponse("/admin/users?error=weak", status_code=303)
    con = db.connect()
    try:
        try:
            con.execute(
                "INSERT INTO admins(username, pw_hash, must_change) VALUES(?,?,0)",
                (username, auth.hash_password(password)),
            )
            con.commit()
        except sqlite3.IntegrityError:
            return RedirectResponse("/admin/users?error=dup", status_code=303)
    finally:
        con.close()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/delete")
def admin_delete_user(request: Request, user_id: int, csrf: str = Form("")):
    admin = admin_guard(request)
    if isinstance(admin, RedirectResponse):
        return admin
    if not csrf_ok(request, admin["id"], csrf) or user_id == admin["id"]:
        return RedirectResponse("/admin/users", status_code=303)
    con = db.connect()
    try:
        if con.execute("SELECT COUNT(*) c FROM admins").fetchone()["c"] > 1:
            con.execute("DELETE FROM admins WHERE id=?", (user_id,))
            con.commit()
    finally:
        con.close()
    return RedirectResponse("/admin/users", status_code=303)
