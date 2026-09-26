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


def pw_tag(pw_hash: str) -> str:
    """Short fingerprint of an admin's current pw_hash, bound into the session."""
    return hashlib.sha256(pw_hash.encode()).hexdigest()[:16]


def make_admin_session(admin_id: int, pw_hash: str) -> str:
    return signer.sign(
        f"adm:{admin_id}:{int(time.time())}:{secrets.token_hex(8)}:{pw_tag(pw_hash)}"
    )


def read_admin_session(cookie: str | None) -> tuple[int, str] | None:
    value = signer.unsign(cookie)
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 5 or parts[0] != "adm":
        return None
    try:
        admin_id = int(parts[1])
        issued = int(parts[2])
    except ValueError:
        return None
    if time.time() - issued > ADMIN_SESSION_HOURS * 3600:
        return None
    return admin_id, parts[4]


class Throttle:
    """Sliding-window per-key attempt limiter (in-memory).

    Keys are client IPs checked before any auth or slug lookup, so every distinct
    address would otherwise stay in memory forever: aged-out keys are dropped, and
    past MAX_KEYS the table is swept (then trimmed oldest-first) on insert."""

    MAX_KEYS = 10_000

    def __init__(self, max_attempts: int = 5, window_sec: int = 300) -> None:
        self.max = max_attempts
        self.window = window_sec
        self.hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        lst = [t for t in self.hits.get(key, []) if now - t < self.window]
        if lst:
            self.hits[key] = lst
        else:
            self.hits.pop(key, None)
        return len(lst) < self.max

    def record(self, key: str) -> None:
        if key not in self.hits and len(self.hits) >= self.MAX_KEYS:
            self._sweep()
        self.hits.setdefault(key, []).append(time.time())

    def _sweep(self) -> None:
        now = time.time()
        for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= self.window]:
            del self.hits[k]
        while len(self.hits) >= self.MAX_KEYS:  # all still live: drop the oldest keys
            del self.hits[next(iter(self.hits))]


login_throttle = Throttle()
join_throttle = Throttle(max_attempts=10, window_sec=300)
