"""Authentication blueprint using Gatekeeper magic-link auth."""

import functools
from collections.abc import Callable
from typing import Any

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.wrappers import Response

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.before_app_request
def load_logged_in_user() -> None:
    """Load user from Gatekeeper cookie before each request.

    If Gatekeeper is not configured, g.user remains None and the
    login_required decorator is a no-op (open access).
    """
    if not hasattr(g, "user"):
        g.user = None


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that redirects anonymous users to the login page.

    When Gatekeeper is not configured, all requests pass through
    (open access). Returns 401 for HTMX requests instead of redirecting.
    """

    @functools.wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        # If gatekeeper is not configured, allow all requests
        if not current_app.config.get("GATEKEEPER_CLIENT"):
            return view(*args, **kwargs)
        if g.get("user") is None:
            if _is_htmx():
                return "", 401
            return redirect(url_for("auth.login", next=request.url))
        return view(*args, **kwargs)

    return wrapped_view


@bp.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    """Login page with magic link form."""
    if g.get("user"):
        return redirect(url_for("index"))

    gk = current_app.config.get("GATEKEEPER_CLIENT")
    if not gk:
        return render_template("auth/login.html", gatekeeper_configured=False)

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        if not identifier:
            flash("Please enter your username or email.", "error")
            return render_template("auth/login.html", gatekeeper_configured=True)

        callback_url = url_for("auth.verify", _external=True)
        next_url = request.form.get("next", "/")

        if gk.send_magic_link(
            identifier, callback_url, redirect_url=next_url, app_name="SharePoint Mirror"
        ):
            return render_template("auth/login_sent.html", identifier=identifier)
        else:
            flash("User not found or email could not be sent.", "error")

    return render_template(
        "auth/login.html",
        gatekeeper_configured=True,
        next=request.args.get("next", "/"),
    )


@bp.route("/verify")
def verify() -> Response:
    """Verify magic link token from Gatekeeper."""
    gk = current_app.config.get("GATEKEEPER_CLIENT")
    if not gk:
        flash("Authentication is not configured.", "error")
        return redirect(url_for("index"))

    token = request.args.get("token", "")
    result = gk.verify_magic_link(token)

    if not result:
        flash("Invalid or expired login link. Please request a new one.", "error")
        return redirect(url_for("auth.login"))

    user, redirect_url = result

    auth_token = gk.create_auth_token(user)
    response = redirect(redirect_url or url_for("index"))
    response.set_cookie(
        "gk_session",
        auth_token,
        max_age=86400 * 365,
        httponly=True,
        secure=not current_app.config.get("DEBUG", False),
        samesite="Lax",
    )

    flash(f"Welcome, {user.fullname or user.username}!", "success")
    return response


@bp.route("/logout")
def logout() -> Response:
    """Log out the current user."""
    response = redirect(url_for("auth.login"))
    response.delete_cookie("gk_session")
    flash("You have been logged out.", "info")
    return response
