"""LateBump helpers core: env, db, schema, draft template, masking."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import g

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = APP_ROOT / "latebump.db"

OPEN_ENDPOINTS = {
    "health",
    "login",
    "logout",
    "static",
}

STATUSES = ("open", "delayed", "done", "cancelled")
DELAY_PRESETS = (15, 30, 45, 60, 90)

STATUS_LABELS = {
    "open": "Open",
    "delayed": "Delayed",
    "done": "Done",
    "cancelled": "Cancelled",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def database_path() -> str:
    raw = _env("DATABASE_PATH")
    return raw if raw else str(DEFAULT_DB)


def smtp_configured() -> bool:
    return bool(_env("SMTP_HOST"))


def sms_configured() -> bool:
    return bool(
        _env("TWILIO_ACCOUNT_SID")
        and _env("TWILIO_AUTH_TOKEN")
        and _env("TWILIO_FROM_NUMBER")
    )


def owner_password() -> str:
    return os.environ.get("OWNER_PASSWORD", "").strip()


def public_base_url() -> str:
    return _env("PUBLIC_BASE_URL").rstrip("/")


def business_name() -> str:
    return _env("BUSINESS_NAME") or "LateBump"


def business_phone() -> str:
    return _env("BUSINESS_PHONE")


def app_tz() -> ZoneInfo:
    name = _env("TZ") or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return to_iso(utc_now())


def local_now() -> datetime:
    return utc_now().astimezone(app_tz())


def board_today() -> str:
    return local_now().date().isoformat()


def first_name(full: str) -> str:
    parts = (full or "").strip().split()
    return parts[0] if parts else ""


def status_label(key: str) -> str:
    return STATUS_LABELS.get(key, key)


def format_clock(dt: datetime) -> str:
    """Friendly local clock text, e.g. 3:45 PM."""
    h = dt.strftime("%I").lstrip("0") or "12"
    return f"{h}:{dt.strftime('%M')} {dt.strftime('%p')}"


def compute_new_eta(delay_minutes: int | None, custom_eta: str | None) -> str:
    custom = (custom_eta or "").strip()
    if custom:
        return custom
    if delay_minutes is None:
        return format_clock(local_now())
    eta = local_now() + timedelta(minutes=int(delay_minutes))
    return format_clock(eta)


def reschedule_line() -> str:
    phone = business_phone()
    if phone:
        return f"If you need to reschedule, call us at {phone}."
    return "If you need to reschedule, reply to this message."


def draft_body(customer_name: str, new_eta: str, offer_reschedule: bool) -> str:
    fname = first_name(customer_name) or (customer_name or "there").strip() or "there"
    lines = [
        f"Hi {fname} -- this is {business_name()}. We're running behind and now expect to arrive around {new_eta}. Sorry for the wait.",
    ]
    if offer_reschedule:
        lines.append("")
        lines.append(reschedule_line())
    return "\n".join(lines)


def mask_destination(dest: str, channel: str) -> str:
    raw = (dest or "").strip()
    if not raw:
        return "***"
    if channel == "email":
        if "@" in raw:
            local, _, domain = raw.partition("@")
            keep = local[:2] if len(local) > 2 else local[:1]
            return f"{keep}***@{domain}"
        return "***"
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"


def connect_db() -> sqlite3.Connection:
    path = database_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    db = sqlite3.connect(path, timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def get_db() -> sqlite3.Connection:
    db = getattr(g, "_db", None)
    if db is None:
        db = connect_db()
        g._db = db
    return db


def close_db(_exc: BaseException | None = None) -> None:
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_phone TEXT,
            customer_email TEXT,
            title TEXT,
            job_ref TEXT,
            scheduled_window TEXT,
            site_label TEXT,
            notes TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bumps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            delay_minutes INTEGER,
            new_eta_text TEXT NOT NULL,
            offer_reschedule INTEGER NOT NULL DEFAULT 0,
            body TEXT NOT NULL,
            channel TEXT NOT NULL,
            destination TEXT,
            ok INTEGER NOT NULL,
            error TEXT,
            at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
        CREATE INDEX IF NOT EXISTS idx_bumps_job_id ON bumps(job_id);
        CREATE INDEX IF NOT EXISTS idx_bumps_at ON bumps(at);
        """
    )
    db.commit()
