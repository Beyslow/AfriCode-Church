from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, ChurchUser, Church

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    if request.method == "POST":
        church_code = request.form.get("church_code", "").strip().lower()
        username    = request.form.get("username", "").strip()
        password    = request.form.get("password", "")

        # ── Super admin path ──────────────────────────────────────────────────
        # Super admin leaves church_code blank
        if not church_code:
            user = ChurchUser.query.filter_by(
                username = username,
                role     = "super_admin"
            ).first()

            if not user or not check_password_hash(user.password, password):
                return render_template("login.html",
                    error="Invalid credentials.")

            login_user(user)
            return redirect(url_for("dashboard.super_admin_dashboard"))

        # ── Church-level path ─────────────────────────────────────────────────

        # Step 1: Find the church by code
        church = Church.query.filter_by(church_code=church_code).first()
        if not church:
            return render_template("login.html",
                error="Church code not found. Please check and try again.")

        # Step 2: Check if church is active
        if not church.is_active:
            return render_template("login.html",
                error="This church account is currently inactive. Contact support.")

        # Step 3: Find the user within this church only
        user = ChurchUser.query.filter_by(
            username  = username,
            church_id = church.id
        ).first()

        if not user:
            return render_template("login.html",
                error="Invalid username or password.")

        # Step 4: Validate password
        if not check_password_hash(user.password, password):
            return render_template("login.html",
                error="Invalid username or password.")

        # Step 5: Log in and redirect by role
        login_user(user)

        # Step 6: Force credential change if required
        if user.must_change_credentials:
            return redirect(url_for("auth.change_credentials"))

        return _redirect_by_role(user.role)

    return render_template("login.html")


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE CREDENTIALS  —  forced on first login
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/change-credentials", methods=["GET", "POST"])
@login_required
def change_credentials():
    if request.method == "POST":
        new_password     = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password:
            flash("Password cannot be empty.", "warning")
            return redirect(url_for("auth.change_credentials"))

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "warning")
            return redirect(url_for("auth.change_credentials"))

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.change_credentials"))

        user                         = db.session.get(ChurchUser, current_user.id)
        user.password                = generate_password_hash(new_password)
        user.must_change_credentials = False
        db.session.commit()

        flash("Password updated successfully.", "success")
        return _redirect_by_role(current_user.role)

    return render_template("Auth/change_credentials.html")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _redirect_by_role(role):
    if role == "super_admin":
        return redirect(url_for("dashboard.super_admin_dashboard"))
    elif role == "pastor":
        return redirect(url_for("dashboard.pastor_dashboard"))
    elif role == "treasurer":
        return redirect(url_for("finance.finance_dashboard"))
    elif role == "secretary":
        return redirect(url_for("dashboard.secretary_dashboard"))
    elif role == "usher":
        return redirect(url_for("attendance.usher_view"))
    return redirect(url_for("auth.login"))