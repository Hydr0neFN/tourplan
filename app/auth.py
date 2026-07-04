"""Password hashing (stdlib scrypt), HMAC cookie signing, login throttling."""
import base64
import hashlib
import hmac
import secrets
import time

from . import db

_SCRYPT = {"n": 16384, "r": 8, "p": 1}


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, **_SCRYPT)
    return base64.b64encode(salt).decode() + ":" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        s, h = stored.split(":")
        salt = base64.b64decode(s)
        want = base64.b64decode(h)
        got = hashlib.scrypt(pw.encode(), salt=salt, **_SCRYPT)
        return hmac.compare_digest(want, got)
    except Exception:
        return False


def _load_secret() -> bytes:
    db.DATA_DIR.mkdir(exist_ok=True)
    path = db.DATA_DIR / "secret.key"
    if path.exists():
        return path.read_bytes()
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    return key


class Signer:
    def __init__(self) -> None:
        self.key = _load_secret()

    def sign(self, value: str) -> str:
        mac = hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()
        return f"{value}.{mac}"

    def unsign(self, signed: str | None) -> str | None:
        if not signed or "." not in signed:
            return None
        value, mac = signed.rsplit(".", 1)
        want = hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()
        return value if hmac.compare_digest(mac, want) else None


signer = Signer()

ADMIN_SESSION_HOURS = 12


def make_admin_session(admin_id: int) -> str:
    return signer.sign(f"adm:{admin_id}:{int(time.time())}:{secrets.token_hex(8)}")


def read_admin_session(cookie: str | None) -> int | None:
    value = signer.unsign(cookie)
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "adm":
        return None
    try:
        admin_id = int(parts[1])
        issued = int(parts[2])
    except ValueError:
        return None
    if time.time() - issued > ADMIN_SESSION_HOURS * 3600:
        return None
    return admin_id


class Throttle:
    """Sliding-window per-key attempt limiter (in-memory)."""

    def __init__(self, max_attempts: int = 5, window_sec: int = 300) -> None:
        self.max = max_attempts
        self.window = window_sec
        self.hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        lst = [t for t in self.hits.get(key, []) if now - t < self.window]
        self.hits[key] = lst
        return len(lst) < self.max

    def record(self, key: str) -> None:
        self.hits.setdefault(key, []).append(time.time())


login_throttle = Throttle()
join_throttle = Throttle(max_attempts=10, window_sec=300)
