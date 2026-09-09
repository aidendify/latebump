"""LateBump send/copy/done routes."""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, session, url_for

import helpers as H


def register_send(app, _parse_bump_form, _log_and_mark):
    @app.post("/jobs/<int:job_id>/copy")
    @app.post("/jobs/<int:job_id>/bumps/<int:bid>/copy")
    def copy_bump(job_id: int, bid: int | None = None):
        job = H.get_job(job_id)
        if not job:
            abort(404)

        existing = H.get_bump(bid) if bid is not None else None
        if existing and existing["job_id"] != job_id:
            abort(404)

        if existing and not (request.form.get("body") or "").strip():
            delay_minutes = existing["delay_minutes"]
            new_eta_text = existing["new_eta_text"]
            offer = bool(existing["offer_reschedule"])
            body = existing["body"]
            errors: list[str] = []
        else:
            delay_minutes, new_eta_text, offer, body, errors = _parse_bump_form(job)

        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("job_detail", job_id=job_id))

        _log_and_mark(
            job,
            channel="copy",
            destination=None,
            ok=True,
            error=None,
            delay_minutes=delay_minutes,
            new_eta_text=new_eta_text,
            offer_reschedule=offer,
            body=body,
        )
        session.pop(f"draft_{job_id}", None)
        flash("Copied -- logged as delayed bump (copy channel).", "ok")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.post("/jobs/<int:job_id>/send-sms")
    @app.post("/jobs/<int:job_id>/bumps/<int:bid>/send-sms")
    def send_sms(job_id: int, bid: int | None = None):
        job = H.get_job(job_id)
        if not job:
            abort(404)
        if bid is not None:
            existing = H.get_bump(bid)
            if not existing or existing["job_id"] != job_id:
                abort(404)

        delay_minutes, new_eta_text, offer, body, errors = _parse_bump_form(job)
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("job_detail", job_id=job_id))

        phone = (job["customer_phone"] or "").strip()
        if not H.sms_configured():
            flash("SMS is not configured (Twilio unset).", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        if not phone:
            flash("This job has no customer phone.", "error")
            return redirect(url_for("job_detail", job_id=job_id))

        try:
            H.send_twilio_sms(phone, body)
            _log_and_mark(
                job,
                channel="sms",
                destination=phone,
                ok=True,
                error=None,
                delay_minutes=delay_minutes,
                new_eta_text=new_eta_text,
                offer_reschedule=offer,
                body=body,
            )
            session.pop(f"draft_{job_id}", None)
            flash("SMS sent.", "ok")
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("SMS send failed for job_id=%s: %s", job_id, type(exc).__name__)
            _log_and_mark(
                job,
                channel="sms",
                destination=phone,
                ok=False,
                error=type(exc).__name__,
                delay_minutes=delay_minutes,
                new_eta_text=new_eta_text,
                offer_reschedule=offer,
                body=body,
            )
            flash("SMS failed to send. Nothing marked as success.", "error")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.post("/jobs/<int:job_id>/send-email")
    @app.post("/jobs/<int:job_id>/bumps/<int:bid>/send-email")
    def send_email(job_id: int, bid: int | None = None):
        job = H.get_job(job_id)
        if not job:
            abort(404)
        if bid is not None:
            existing = H.get_bump(bid)
            if not existing or existing["job_id"] != job_id:
                abort(404)

        delay_minutes, new_eta_text, offer, body, errors = _parse_bump_form(job)
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("job_detail", job_id=job_id))

        email = (job["customer_email"] or "").strip()
        if not H.smtp_configured():
            flash("Email is not configured (SMTP unset).", "error")
            return redirect(url_for("job_detail", job_id=job_id))
        if not email:
            flash("This job has no customer email.", "error")
            return redirect(url_for("job_detail", job_id=job_id))

        subject = f"Running late -- {H.business_name()}"
        try:
            H.send_smtp(email, subject, body)
            _log_and_mark(
                job,
                channel="email",
                destination=email,
                ok=True,
                error=None,
                delay_minutes=delay_minutes,
                new_eta_text=new_eta_text,
                offer_reschedule=offer,
                body=body,
            )
            session.pop(f"draft_{job_id}", None)
            flash("Email sent.", "ok")
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("Email send failed for job_id=%s: %s", job_id, type(exc).__name__)
            _log_and_mark(
                job,
                channel="email",
                destination=email,
                ok=False,
                error=type(exc).__name__,
                delay_minutes=delay_minutes,
                new_eta_text=new_eta_text,
                offer_reschedule=offer,
                body=body,
            )
            flash("Email failed to send. Nothing marked as success.", "error")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.post("/jobs/<int:job_id>/done")
    def mark_done(job_id: int):
        job = H.get_job(job_id)
        if not job:
            abort(404)
        H.set_job_status(job_id, "done")
        flash("Marked done.", "ok")
        return redirect(url_for("index"))

    @app.post("/jobs/<int:job_id>/cancel")
    def mark_cancel(job_id: int):
        job = H.get_job(job_id)
        if not job:
            abort(404)
        H.set_job_status(job_id, "cancelled")
        flash("Cancelled.", "ok")
        return redirect(url_for("index"))

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html", public=True), 404
