"""LateBump: running-late pings for local service owners."""

from __future__ import annotations

import secrets

from flask import (
    Flask,
    redirect,
    request,
    session,
    url_for,
)

import helpers as H

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
app.secret_key = __import__("os").environ.get("SECRET_KEY", "latebump-self-hosted-change-me")

app.teardown_appcontext(H.close_db)


def init_db() -> None:
    with app.app_context():
        H.init_schema(H.get_db())


@app.context_processor
def inject_globals() -> dict:
    return {
        "marketing_url": H._env("MARKETING_URL"),
        "smtp_configured": H.smtp_configured(),
        "sms_configured": H.sms_configured(),
        "business_name": H.business_name(),
        "business_phone": H.business_phone(),
        "owner_locked": bool(H.owner_password()),
        "logged_in": bool(session.get("owner")) or not H.owner_password(),
        "status_label": H.status_label,
        "first_name": H.first_name,
        "DELAY_PRESETS": H.DELAY_PRESETS,
    }


@app.before_request
def protect_owner_routes():
    if request.endpoint in H.OPEN_ENDPOINTS or request.endpoint is None:
        return None
    if not H.owner_password():
        return None
    if session.get("owner"):
        return None
    nxt = request.path if request.method == "GET" else "/"
    return redirect(url_for("login", next=nxt))


def _safe_next(val: str | None) -> str:
    raw = (val or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return url_for("index")


def _parse_bump_form(job) -> tuple[int | None, str, bool, str, list[str]]:
    """Return delay_minutes, new_eta_text, offer_reschedule, body, errors."""
    errors: list[str] = []
    delay_minutes = H.parse_delay_minutes(request.form.get("delay_minutes"))
    custom_eta = (request.form.get("custom_eta") or "").strip() or None
    offer = request.form.get("offer_reschedule") in {"1", "on", "true", "yes"}
    body = (request.form.get("body") or "").strip()

    if delay_minutes is None and not custom_eta:
        new_eta = (request.form.get("new_eta_text") or "").strip()
        if not new_eta and not body:
            errors.append("Pick a delay preset or enter a new ETA.")
        new_eta_text = new_eta or custom_eta or ""
    else:
        new_eta_text = H.compute_new_eta(delay_minutes, custom_eta)

    if not new_eta_text:
        new_eta_text = (request.form.get("new_eta_text") or "").strip()

    if not body:
        body = H.draft_body(job["customer_name"], new_eta_text or "soon", offer)

    if not new_eta_text:
        errors.append("New ETA is required.")
    if not body:
        errors.append("Message body is required.")

    return delay_minutes, new_eta_text, offer, body, errors


def _log_and_mark(
    job,
    *,
    channel: str,
    destination: str | None,
    ok: bool,
    error: str | None,
    delay_minutes: int | None,
    new_eta_text: str,
    offer_reschedule: bool,
    body: str,
) -> int:
    bid = H.insert_bump(
        job_id=job["id"],
        delay_minutes=delay_minutes,
        new_eta_text=new_eta_text,
        offer_reschedule=offer_reschedule,
        body=body,
        channel=channel,
        destination=destination,
        ok=ok,
        error=error,
    )
    if ok:
        H.mark_delayed_if_open(job["id"])
        H.maybe_notify_owner(app, body, job)
    return bid


from views_auth import register_auth
from views_jobs import register_jobs
from views_send import register_send

register_auth(app, _safe_next)
register_jobs(app, _parse_bump_form, _log_and_mark)
register_send(app, _parse_bump_form, _log_and_mark)

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8080")), debug=True)
