"""LateBump auth/health routes."""
from __future__ import annotations

import secrets

from flask import jsonify, redirect, render_template, request, session, url_for

import helpers as H

def register_auth(app, _safe_next):
    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "smtp_configured": H.smtp_configured(),
                "sms_configured": H.sms_configured(),
            }
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        nxt = _safe_next(request.values.get("next"))
        if not H.owner_password():
            return redirect(nxt)
        if session.get("owner"):
            return redirect(nxt)
        error = None
        if request.method == "POST":
            provided = (request.form.get("password") or "").encode("utf-8")
            expected = H.owner_password().encode("utf-8")
            ok = len(provided) == len(expected) and secrets.compare_digest(provided, expected)
            if ok:
                session["owner"] = True
                return redirect(nxt)
            error = "Incorrect password."
        return render_template("login.html", next=nxt, error=error, public=True)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
