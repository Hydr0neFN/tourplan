"""SQLite storage layer."""
import pathlib
import sqlite3

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "tourplan.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins(
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL,
  must_change INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tours(
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  date_start TEXT NOT NULL,
  date_end TEXT NOT NULL,
  show_names INTEGER NOT NULL DEFAULT 1,
  require_name INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  owner_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS visitors(
  id INTEGER PRIMARY KEY,
  tour_id INTEGER NOT NULL REFERENCES tours(id) ON DELETE CASCADE,
  name TEXT,
  icon_idx INTEGER NOT NULL,
  token TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_visitors_tour ON visitors(tour_id);
CREATE TABLE IF NOT EXISTS denies(
  visitor_id INTEGER NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY(visitor_id, date)
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init() -> None:
    con = connect()
    try:
        con.executescript(SCHEMA)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(tours)")}
        if "deadline" not in cols:
            con.execute("ALTER TABLE tours ADD COLUMN deadline TEXT")
        if "owner_id" not in cols:
            con.execute("ALTER TABLE tours ADD COLUMN owner_id INTEGER")
        if "require_name" not in cols:
            con.execute("ALTER TABLE tours ADD COLUMN require_name INTEGER NOT NULL DEFAULT 0")
        con.commit()
    finally:
        con.close()
