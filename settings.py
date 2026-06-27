import os
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash
)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, Church, ChurchUser

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

LOGO_FOLDER    = os.path.join("static", "uploads", "logos")
ALLOWED_LOGOS  = {"png", "jpg", "jpeg", "svg"}

os.makedirs(LOGO_FOLDER, exist_ok=True)


def _allowed_logo(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_LOGOS
    )


# ─────────────────────────────────────────────────────────────────────────────
# SETTINGS HOME
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/")
@login_required
def settings_home():
    if current_user.role not in ("pastor", "treasurer", "secretary", "super_admin"):
        return "Access denied", 403

    cid    = current_user.church_id
    church = Church.query.get(cid)
    users  = ChurchUser.query.filter(
        ChurchUser.church_id == cid,
        ChurchUser.role      != "super_admin",
    ).order_by(ChurchUser.role, ChurchUser.username).all()

    section = request.args.get("section", "profile")

    return render_template("Settings/settings.html",
        church  = church,
        users   = users,
        section = section,
    )


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE CHURCH PROFILE
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/church", methods=["POST"])
@login_required
def update_church():
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    cid    = current_user.church_id
    church = Church.query.get_or_404(cid)

    church.name        = request.form.get("name", "").strip()       or church.name
    church.email       = request.form.get("email", "").strip()      or None
    church.phone       = request.form.get("phone", "").strip()      or None
    church.address     = request.form.get("address", "").strip()    or None
    church.pastor_name = request.form.get("pastor_name", "").strip() or None

    # Logo upload — local storage, no Cloudinary
    logo = request.files.get("logo")
    if logo and logo.filename:
        if _allowed_logo(logo.filename):
            ext       = logo.filename.rsplit(".", 1)[1].lower()
            filename  = f"church_{cid}_logo.{ext}"
            save_path = os.path.join(LOGO_FOLDER, filename)
            logo.save(save_path)
            church.logo_filename = filename
        else:
            flash("Invalid logo format. Use PNG, JPG, or SVG.", "warning")
            return redirect(url_for("settings.settings_home") + "?section=profile")

    db.session.commit()
    flash("Church profile updated.", "success")
    return redirect(url_for("settings.settings_home") + "?section=profile")


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE EXCHANGE RATE
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/exchange-rate", methods=["POST"])
@login_required
def update_exchange_rate():
    if current_user.role not in ("pastor", "treasurer", "super_admin"):
        return "Access denied", 403

    cid    = current_user.church_id
    church = Church.query.get_or_404(cid)

    try:
        rate = float(request.form.get("exchange_rate", 1.0))
        if rate <= 0:
            flash("Exchange rate must be greater than zero.", "warning")
            return redirect(url_for("settings.settings_home") + "?section=finance")

        local_currency = request.form.get("local_currency", "").strip().upper()
        if local_currency:
            church.local_currency = local_currency

        church.exchange_rate = rate
        db.session.commit()
        flash(
            f"Exchange rate updated: "
            f"1 USD = {rate:,.2f} {church.local_currency}.",
            "success"
        )
    except ValueError:
        flash("Invalid exchange rate value.", "warning")

    return redirect(url_for("settings.settings_home") + "?section=finance")


# ─────────────────────────────────────────────────────────────────────────────
# ADD STAFF USER
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/users/add", methods=["POST"])
@login_required
def add_user():
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    cid      = current_user.church_id
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    role     = request.form.get("role", "").strip()

    valid_roles = ["pastor", "treasurer", "secretary", "usher"]
    if role not in valid_roles:
        flash("Invalid role selected.", "warning")
        return redirect(url_for("settings.settings_home") + "?section=users")

    if not username or not password:
        flash("Username and password are required.", "warning")
        return redirect(url_for("settings.settings_home") + "?section=users")

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "warning")
        return redirect(url_for("settings.settings_home") + "?section=users")

    existing = ChurchUser.query.filter_by(
        church_id=cid, username=username
    ).first()
    if existing:
        flash(f'Username "{username}" is already taken in this church.', "warning")
        return redirect(url_for("settings.settings_home") + "?section=users")

    db.session.add(ChurchUser(
        church_id               = cid,
        username                = username,
        password                = generate_password_hash(password),
        role                    = role,
        must_change_credentials = True,
    ))
    db.session.commit()

    flash(
        f'User "{username}" created as {role.title()}. '
        f'They will be prompted to change their password on first login.',
        "success"
    )
    return redirect(url_for("settings.settings_home") + "?section=users")


# ─────────────────────────────────────────────────────────────────────────────
# RESET USER PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
def reset_user_password(user_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    user = ChurchUser.query.filter_by(
        id=user_id, church_id=current_user.church_id
    ).first_or_404()

    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        flash("New password must be at least 6 characters.", "warning")
        return redirect(url_for("settings.settings_home") + "?section=users")

    user.password                = generate_password_hash(new_password)
    user.must_change_credentials = True
    db.session.commit()

    flash(
        f'Password reset for "{user.username}". '
        f'They will be prompted to change it on next login.',
        "success"
    )
    return redirect(url_for("settings.settings_home") + "?section=users")


# ─────────────────────────────────────────────────────────────────────────────
# DELETE STAFF USER
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    user = ChurchUser.query.filter_by(
        id=user_id, church_id=current_user.church_id
    ).first_or_404()

    # Prevent self-deletion
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("settings.settings_home") + "?section=users")

    username = user.username
    db.session.delete(user)
    db.session.commit()

    flash(f'User "{username}" removed.', "success")
    return redirect(url_for("settings.settings_home") + "?section=users")


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE OWN PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/account/password", methods=["POST"])
@login_required
def change_password():
    current_pw  = request.form.get("current_password", "")
    new_pw      = request.form.get("new_password", "").strip()
    confirm_pw  = request.form.get("confirm_password", "").strip()

    if not check_password_hash(current_user.password, current_pw):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("settings.settings_home") + "?section=account")

    if new_pw != confirm_pw:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("settings.settings_home") + "?section=account")

    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "warning")
        return redirect(url_for("settings.settings_home") + "?section=account")

    user          = db.session.get(ChurchUser, current_user.id)
    user.password = generate_password_hash(new_pw)
    user.must_change_credentials = False
    db.session.commit()

    flash("Password changed successfully.", "success")
    return redirect(url_for("settings.settings_home") + "?section=account")


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE OWN CONTACT INFO
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/account/contact", methods=["POST"])
@login_required
def update_contact():
    user       = db.session.get(ChurchUser, current_user.id)
    user.email = request.form.get("email", "").strip() or None
    user.phone = request.form.get("phone", "").strip() or None
    db.session.commit()

    flash("Contact information updated.", "success")
    return redirect(url_for("settings.settings_home") + "?section=account")


# ─────────────────────────────────────────────────────────────────────────────
# SUPER ADMIN — ADD CHURCH
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/churches/add", methods=["GET", "POST"])
@login_required
def add_church():
    if current_user.role != "super_admin":
        return "Access denied", 403

    if request.method == "POST":
        church_code    = request.form.get("church_code", "").strip().lower()
        name           = request.form.get("name", "").strip()
        pastor_name    = request.form.get("pastor_name", "").strip() or None
        email          = request.form.get("email", "").strip() or None
        phone          = request.form.get("phone", "").strip() or None
        address        = request.form.get("address", "").strip() or None
        admin_username = request.form.get("admin_username", "").strip()
        admin_password = request.form.get("admin_password", "").strip()

        if not church_code or not name or not admin_username or not admin_password:
            flash("Church code, name, pastor username and password are all required.", "warning")
            return redirect(url_for("settings.add_church"))

        if Church.query.filter_by(church_code=church_code).first():
            flash(f'Church code "{church_code}" is already taken.', "warning")
            return redirect(url_for("settings.add_church"))

        try:
            church = Church(
                church_code       = church_code,
                name              = name,
                pastor_name       = pastor_name,
                email             = email,
                phone             = phone,
                address           = address,
                is_active         = True,
                subscription_plan = "trial",
                base_currency     = "USD",
                local_currency    = request.form.get("local_currency", "LRD").strip().upper(),
                exchange_rate     = float(request.form.get("exchange_rate", 1.0)),
            )
            db.session.add(church)
            db.session.flush()

            # Create the pastor account
            db.session.add(ChurchUser(
                church_id               = church.id,
                username                = admin_username,
                password                = generate_password_hash(admin_password),
                role                    = "pastor",
                must_change_credentials = True,
            ))

            # Seed default income categories
            from models import IncomeCategory, ExpenseCategory
            for name_cat in ["Tithes", "Offerings", "Donations", "Building Fund", "Project Fund"]:
                db.session.add(IncomeCategory(
                    church_id=church.id, name=name_cat, is_active=True
                ))
            for name_cat in ["Utilities", "Fuel", "Maintenance", "Salaries", "Miscellaneous"]:
                db.session.add(ExpenseCategory(
                    church_id=church.id, name=name_cat, is_active=True
                ))

            db.session.commit()
            flash(
                f'Church "{church.name}" created. '
                f'Pastor login: {admin_username} / {admin_password}',
                "success"
            )
            return redirect(url_for("dashboard.super_admin_dashboard"))

        except Exception as e:
            db.session.rollback()
            flash(f"Could not create church: {e}", "danger")
            return redirect(url_for("settings.add_church"))

    return render_template("Settings/add_church.html")


# ─────────────────────────────────────────────────────────────────────────────
# SUPER ADMIN — TOGGLE CHURCH ACTIVE
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route("/churches/<int:church_id>/toggle", methods=["POST"])
@login_required
def toggle_church(church_id):
    if current_user.role != "super_admin":
        return "Access denied", 403

    church            = Church.query.get_or_404(church_id)
    church.is_active  = not church.is_active
    db.session.commit()

    status = "activated" if church.is_active else "deactivated"
    flash(f'"{church.name}" has been {status}.', "success")
    return redirect(url_for("dashboard.super_admin_dashboard"))