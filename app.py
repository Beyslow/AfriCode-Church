import os
import json
from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_compress import Compress
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from datetime import datetime, date

load_dotenv()

from models import db, ChurchUser, Church

# ── Blueprint imports ─────────────────────────────────────────────────────────
from auth import auth_bp
from dashboard import dashboard_bp
from members import members_bp
from visitors import visitors_bp
from ministries import ministries_bp
from attendance import attendance_bp
from finance import finance_bp
from communications.routes import communications_bp
from reports import reports_bp
from documents import documents_bp
from settings import settings_bp

# ─────────────────────────────────────────────────────────────────────────────
# APP FACTORY
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"]        = os.environ.get("DATABASE_URL")
app.config["SECRET_KEY"]                     = os.environ.get("SECRET_KEY")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"]             = 16 * 1024 * 1024  # 16 MB upload limit

# ── Compression ───────────────────────────────────────────────────────────────
app.config["COMPRESS_MIMETYPES"] = [
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
]
app.config["COMPRESS_LEVEL"]    = 6
app.config["COMPRESS_MIN_SIZE"] = 500

# ── Extensions ────────────────────────────────────────────────────────────────
db.init_app(app)
migrate  = Migrate(app, db)
compress = Compress(app)

# ── Login Manager ─────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(ChurchUser, int(user_id))

# ─────────────────────────────────────────────────────────────────────────────
# BEFORE REQUEST GUARDS
# ─────────────────────────────────────────────────────────────────────────────

@app.before_request
def check_church_access():
    """
    Block access if a church has been deactivated by the super admin.
    Super admin is never blocked.
    Static files and logout are always allowed through.
    """
    from flask import request

    if not current_user.is_authenticated:
        return None

    if current_user.role == "super_admin":
        return None

    if request.path.startswith("/auth/logout"):
        return None

    if request.path.startswith("/static"):
        return None

    if not current_user.church_id:
        return None

    church = db.session.get(Church, current_user.church_id)

    if not church:
        return None

    if not church.is_active:
        return render_template("suspended.html")

    return None


@app.before_request
def force_credential_setup():
    """
    If a user has must_change_credentials = True, redirect them to the
    change credentials page before they can access anything else.
    """
    from flask import request

    if not current_user.is_authenticated:
        return None

    if not getattr(current_user, "must_change_credentials", False):
        return None

    allowed_endpoints = [
        "auth.change_credentials",
        "auth.logout",
        "static",
    ]

    if request.endpoint not in allowed_endpoints:
        return redirect(url_for("auth.change_credentials"))

    return None

# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT PROCESSOR
# ─────────────────────────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """
    Injects church settings into every template automatically.
    Templates can use {{ church.name }}, {{ church.logo_filename }} etc.
    without needing to pass it in every render_template() call.
    """
    church = None

    if current_user.is_authenticated and current_user.church_id:
        church = db.session.get(Church, current_user.church_id)

    return {
        "church":   church,
        "now":      datetime.utcnow(),
        "today":    date.today(),
    }

# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILE CACHING
# ─────────────────────────────────────────────────────────────────────────────

@app.after_request
def add_cache_headers(response):
    from flask import request
    if request.path.startswith("/static/"):
        response.cache_control.max_age = 31536000  # 1 year
        response.cache_control.public  = True
        response.headers["Vary"]       = "Accept-Encoding"
    return response

# ─────────────────────────────────────────────────────────────────────────────
# HOME ROUTE
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    if current_user.is_authenticated:
        return _redirect_by_role()
    return redirect(url_for("auth.login"))


def _redirect_by_role():
    """Route each role to their correct landing page after login."""
    role = current_user.role
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

# ─────────────────────────────────────────────────────────────────────────────
# BLUEPRINT REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(members_bp)
app.register_blueprint(visitors_bp)
app.register_blueprint(ministries_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(finance_bp)
app.register_blueprint(communications_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(documents_bp)
app.register_blueprint(settings_bp)

# ─────────────────────────────────────────────────────────────────────────────
# SETUP ROUTE  —  creates all tables (run once)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/setup-africode-church-2025")
def setup_db():
    db.create_all()
    return "Church ERP tables created!"

# ─────────────────────────────────────────────────────────────────────────────
# SEED ROUTE  —  creates super admin + demo church (run once)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/seed-africode-church-2025")
def seed_db():
    # ── Step 1: Super admin (no church_id) ───────────────────────────────────
    if not ChurchUser.query.filter_by(role="super_admin").first():
        db.session.add(ChurchUser(
            username                = "superadmin",
            password                = generate_password_hash("super123"),
            role                    = "super_admin",
            church_id               = None,
            must_change_credentials = False,
        ))
        db.session.flush()

    # ── Step 2: Demo church ───────────────────────────────────────────────────
    church = Church.query.filter_by(church_code="grace-chapel-demo").first()
    if not church:
        church = Church(
            church_code       = "grace-chapel-demo",
            name              = "Grace Chapel Demo",
            email             = "admin@gracechapel.com",
            phone             = "+231770000000",
            pastor_name       = "Pastor Demo",
            is_active         = True,
            subscription_plan = "trial",
            base_currency     = "USD",
            local_currency    = "LRD",
            exchange_rate     = 196.0,
        )
        db.session.add(church)
        db.session.flush()

    # ── Step 3: Pastor account for demo church ────────────────────────────────
    if not ChurchUser.query.filter_by(role="pastor", church_id=church.id).first():
        db.session.add(ChurchUser(
            username                = "pastor",
            password                = generate_password_hash("pastor123"),
            role                    = "pastor",
            church_id               = church.id,
            must_change_credentials = False,
        ))

    # ── Step 4: Treasurer account ─────────────────────────────────────────────
    if not ChurchUser.query.filter_by(role="treasurer", church_id=church.id).first():
        db.session.add(ChurchUser(
            username                = "treasurer",
            password                = generate_password_hash("treasurer123"),
            role                    = "treasurer",
            church_id               = church.id,
            must_change_credentials = False,
        ))

    # ── Step 5: Secretary account ─────────────────────────────────────────────
    if not ChurchUser.query.filter_by(role="secretary", church_id=church.id).first():
        db.session.add(ChurchUser(
            username                = "secretary",
            password                = generate_password_hash("secretary123"),
            role                    = "secretary",
            church_id               = church.id,
            must_change_credentials = False,
        ))

    # ── Step 6: Usher account ─────────────────────────────────────────────────
    if not ChurchUser.query.filter_by(role="usher", church_id=church.id).first():
        db.session.add(ChurchUser(
            username                = "usher",
            password                = generate_password_hash("usher123"),
            role                    = "usher",
            church_id               = church.id,
            must_change_credentials = False,
        ))

    # ── Step 7: Default income categories ────────────────────────────────────
    from models import IncomeCategory
    default_income = ["Tithes", "Offerings", "Donations", "Building Fund", "Project Fund"]
    for name in default_income:
        if not IncomeCategory.query.filter_by(church_id=church.id, name=name).first():
            db.session.add(IncomeCategory(
                church_id = church.id,
                name      = name,
                is_active = True,
            ))

    # ── Step 8: Default expense categories ───────────────────────────────────
    from models import ExpenseCategory
    default_expenses = ["Utilities", "Fuel", "Maintenance", "Salaries", "Miscellaneous"]
    for name in default_expenses:
        if not ExpenseCategory.query.filter_by(church_id=church.id, name=name).first():
            db.session.add(ExpenseCategory(
                church_id = church.id,
                name      = name,
                is_active = True,
            ))

    db.session.commit()
    return "Church ERP seeded successfully!"

# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # ── Auto-seed if database is empty ────────────────────────────────────
        from models import IncomeCategory, ExpenseCategory

        if not ChurchUser.query.filter_by(role="super_admin").first():

            # Super admin
            db.session.add(ChurchUser(
                username                = "superadmin",
                password                = generate_password_hash("super123"),
                role                    = "super_admin",
                church_id               = None,
                must_change_credentials = False,
            ))
            db.session.flush()

            # Demo church
            church = Church(
                church_code       = "grace-chapel-demo",
                name              = "Grace Chapel Demo",
                email             = "admin@gracechapel.com",
                phone             = "+231770000000",
                pastor_name       = "Pastor Demo",
                is_active         = True,
                subscription_plan = "trial",
                base_currency     = "USD",
                local_currency    = "LRD",
                exchange_rate     = 196.0,
            )
            db.session.add(church)
            db.session.flush()

            # Staff accounts
            for username, role, password in [
                ("pastor",    "pastor",    "pastor123"),
                ("treasurer", "treasurer", "treasurer123"),
                ("secretary", "secretary", "secretary123"),
                ("usher",     "usher",     "usher123"),
            ]:
                db.session.add(ChurchUser(
                    username                = username,
                    password                = generate_password_hash(password),
                    role                    = role,
                    church_id               = church.id,
                    must_change_credentials = False,
                ))

            # Default categories
            for name in ["Tithes", "Offerings", "Donations", "Building Fund", "Project Fund"]:
                db.session.add(IncomeCategory(church_id=church.id, name=name, is_active=True))

            for name in ["Utilities", "Fuel", "Maintenance", "Salaries", "Miscellaneous"]:
                db.session.add(ExpenseCategory(church_id=church.id, name=name, is_active=True))

            db.session.commit()
            print("✅ Database seeded — superadmin / super123")

    app.run(debug=True)