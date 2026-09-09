"""LateBump job routes."""
from __future__ import annotations

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import helpers as H

def register_jobs(app, _parse_bump_form, _log_and_mark):
    @app.get("/")
    def index():
        jobs = H.list_active_jobs()
        bumps = H.list_recent_bumps(20)
        return render_template(
            "index.html",
            jobs=jobs,
            bumps=bumps,
            today=H.board_today(),
        )

    @app.route("/jobs/new", methods=["GET", "POST"])
    def new_job():
        if request.method == "GET":
            return render_template("new_job.html", form=None, errors=None)

        customer_name = (request.form.get("customer_name") or "").strip()
        customer_phone = (request.form.get("customer_phone") or "").strip() or None
        customer_email = (request.form.get("customer_email") or "").strip() or None
        title = (request.form.get("title") or "").strip() or None
        job_ref = (request.form.get("job_ref") or "").strip() or None
        scheduled_window = (request.form.get("scheduled_window") or "").strip() or None
        site_label = (request.form.get("site_label") or "").strip() or None
        notes = (request.form.get("notes") or "").strip() or None

        errors: list[str] = []
        if not customer_name:
            errors.append("Customer name is required.")

        form = {
            "customer_name": customer_name,
            "customer_phone": customer_phone or "",
            "customer_email": customer_email or "",
            "title": title or "",
            "job_ref": job_ref or "",
            "scheduled_window": scheduled_window or "",
            "site_label": site_label or "",
            "notes": notes or "",
        }
        if errors:
            return render_template("new_job.html", form=form, errors=errors), 400

        job_id = H.insert_job(
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            title=title,
            job_ref=job_ref,
            scheduled_window=scheduled_window,
            site_label=site_label,
            notes=notes,
        )
        flash("Job created.", "ok")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.get("/jobs/<int:job_id>")
    def job_detail(job_id: int):
        job = H.get_job(job_id)
        if not job:
            abort(404)

        delay_q = H.parse_delay_minutes(request.args.get("delay"))
        custom_eta = (request.args.get("custom_eta") or "").strip() or None
        offer = request.args.get("offer") in {"1", "on", "true", "yes"}
        show_draft = delay_q is not None or custom_eta or request.args.get("draft") == "1"

        draft = None
        new_eta_text = None
        delay_minutes = delay_q
        if show_draft or session.get(f"draft_{job_id}"):
            sess = session.pop(f"draft_{job_id}", None) or {}
            delay_minutes = sess.get("delay_minutes", delay_minutes)
            new_eta_text = sess.get("new_eta_text") or (
                H.compute_new_eta(delay_minutes, custom_eta) if (delay_minutes or custom_eta) else None
            )
            offer = bool(sess.get("offer_reschedule", offer))
            body = sess.get("body") or (
                H.draft_body(job["customer_name"], new_eta_text, offer) if new_eta_text else ""
            )
            if new_eta_text and body:
                draft = {
                    "delay_minutes": delay_minutes,
                    "new_eta_text": new_eta_text,
                    "offer_reschedule": offer,
                    "body": body,
                }

        bumps = H.list_job_bumps(job_id)
        can_sms = H.sms_configured() and bool(job["customer_phone"])
        can_email = H.smtp_configured() and bool(job["customer_email"])
        return render_template(
            "job_detail.html",
            job=job,
            draft=draft,
            bumps=bumps,
            can_sms=can_sms,
            can_email=can_email,
            selected_delay=delay_minutes,
            offer_reschedule=offer,
            custom_eta=custom_eta or "",
        )

    @app.post("/jobs/<int:job_id>/bump")
    def bump_draft(job_id: int):
        """Create / refresh an editable delay draft (session), then show job detail."""
        job = H.get_job(job_id)
        if not job:
            abort(404)

        delay_minutes = H.parse_delay_minutes(request.form.get("delay_minutes"))
        custom_eta = (request.form.get("custom_eta") or "").strip() or None
        offer = request.form.get("offer_reschedule") in {"1", "on", "true", "yes"}

        if delay_minutes is None and not custom_eta:
            flash("Pick a delay preset (+15/+30/...) or enter a custom new ETA.", "error")
            return redirect(url_for("job_detail", job_id=job_id))

        new_eta_text = H.compute_new_eta(delay_minutes, custom_eta)
        body = H.draft_body(job["customer_name"], new_eta_text, offer)
        session[f"draft_{job_id}"] = {
            "delay_minutes": delay_minutes,
            "new_eta_text": new_eta_text,
            "offer_reschedule": offer,
            "body": body,
        }
        return redirect(url_for("job_detail", job_id=job_id, draft=1))
