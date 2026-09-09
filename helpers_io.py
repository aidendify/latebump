"""LateBump helpers IO: job/bump writes and Twilio/SMTP."""
from __future__ import annotations

import base64
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from helpers_core import (
    DELAY_PRESETS,
    _env,
    get_db,
    mask_destination,
    smtp_configured,
    utc_now_iso,
)

def get_job(job_id: int):
    return get_db().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def list_active_jobs():
    """Open + delayed jobs for the board (today's active work)."""
    return get_db().execute(
        """
        SELECT * FROM jobs
        WHERE status IN ('open', 'delayed')
        ORDER BY
          CASE status WHEN 'delayed' THEN 0 WHEN 'open' THEN 1 ELSE 2 END,
          id DESC
        """
    ).fetchall()


def list_recent_bumps(limit: int = 20):
    return get_db().execute(
        """
        SELECT b.*, j.customer_name, j.title, j.job_ref
        FROM bumps b
        JOIN jobs j ON j.id = b.job_id
        ORDER BY b.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def list_job_bumps(job_id: int):
    return get_db().execute(
        "SELECT * FROM bumps WHERE job_id = ? ORDER BY id DESC",
        (job_id,),
    ).fetchall()


def get_bump(bump_id: int):
    return get_db().execute("SELECT * FROM bumps WHERE id = ?", (bump_id,)).fetchone()


def insert_job(
    *,
    customer_name: str,
    customer_phone: str | None,
    customer_email: str | None,
    title: str | None,
    job_ref: str | None,
    scheduled_window: str | None,
    site_label: str | None,
    notes: str | None,
) -> int:
    now = utc_now_iso()
    cur = get_db().execute(
        """
        INSERT INTO jobs (
            customer_name, customer_phone, customer_email, title, job_ref,
            scheduled_window, site_label, notes, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """,
        (
            customer_name,
            customer_phone,
            customer_email,
            title,
            job_ref,
            scheduled_window,
            site_label,
            notes,
            now,
            now,
        ),
    )
    get_db().commit()
    return int(cur.lastrowid)


def set_job_status(job_id: int, status: str) -> None:
    get_db().execute(
        "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
        (status, utc_now_iso(), job_id),
    )
    get_db().commit()


def mark_delayed_if_open(job_id: int) -> None:
    job = get_job(job_id)
    if job and job["status"] == "open":
        set_job_status(job_id, "delayed")


def insert_bump(
    *,
    job_id: int,
    delay_minutes: int | None,
    new_eta_text: str,
    offer_reschedule: bool,
    body: str,
    channel: str,
    destination: str | None,
    ok: bool,
    error: str | None = None,
) -> int:
    masked = mask_destination(destination or "", channel) if destination else None
    cur = get_db().execute(
        """
        INSERT INTO bumps (
            job_id, delay_minutes, new_eta_text, offer_reschedule, body,
            channel, destination, ok, error, at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            delay_minutes,
            new_eta_text,
            1 if offer_reschedule else 0,
            body,
            channel,
            masked,
            1 if ok else 0,
            error,
            utc_now_iso(),
        ),
    )
    get_db().commit()
    return int(cur.lastrowid)


def parse_delay_minutes(raw: str | None) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        mins = int(value)
    except ValueError:
        return None
    if mins in DELAY_PRESETS:
        return mins
    if mins > 0:
        return mins
    return None


def send_smtp(to_email: str, subject: str, body: str) -> None:
    host = _env("SMTP_HOST")
    if not host:
        raise RuntimeError("SMTP is not configured.")
    from_email = _env("FROM_EMAIL")
    if not from_email:
        raise RuntimeError("FROM_EMAIL is required to send mail.")
    port = int(_env("SMTP_PORT") or "587")
    user = _env("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD", "")
    tls_raw = _env("SMTP_TLS") or "true"
    use_tls = tls_raw.lower() in {"1", "true", "yes", "on"}
    from_name = _env("FROM_NAME")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to_email
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)


def send_twilio_sms(to_phone: str, body: str) -> None:
    sid = _env("TWILIO_ACCOUNT_SID")
    token = _env("TWILIO_AUTH_TOKEN")
    from_number = _env("TWILIO_FROM_NUMBER")
    if not (sid and token and from_number):
        raise RuntimeError("Twilio is not configured.")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode(
        {"To": to_phone, "From": from_number, "Body": body}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    credentials = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"Twilio HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Twilio HTTP {exc.code}") from exc


def maybe_notify_owner(app, body: str, job) -> None:
    notify = _env("OWNER_NOTIFY_EMAIL")
    if not notify or not smtp_configured():
        return
    try:
        subject = f"LateBump: delay sent for {job['customer_name']}"
        send_smtp(notify, subject, body)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Owner notify failed: %s", type(exc).__name__)
