from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, timedelta
from models import (db, Church, ChurchUser, Member, Visitor, Ministry, ChurchService, AttendanceRecord, ChurchIncome, ChurchExpense, Announcement
)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_dashboard_data(church_id):
    """
    Builds all the data shared across pastor and secretary dashboards.
    Returns a single dict so both routes stay clean.
    """
    today      = date.today()
    this_month = today.replace(day=1)

    # ── Cards ─────────────────────────────────────────────────────────────────
    total_members = Member.query.filter_by(
        church_id=church_id, status="Active"
    ).count()

    first_time_visitors = Visitor.query.filter(
        Visitor.church_id  == church_id,
        Visitor.visit_date >= this_month,
        Visitor.converted  == False
    ).count()

    # Attendance this week (Monday → today)
    week_start = today - timedelta(days=today.weekday())
    services_this_week = ChurchService.query.filter(
        ChurchService.church_id    == church_id,
        ChurchService.service_date >= week_start,
        ChurchService.service_date <= today
    ).all()

    service_ids_this_week = [s.id for s in services_this_week]
    attendance_this_week  = 0
    if service_ids_this_week:
        attendance_this_week = AttendanceRecord.query.filter(
            AttendanceRecord.church_id  == church_id,
            AttendanceRecord.service_id.in_(service_ids_this_week),
            AttendanceRecord.status     == "Present"
        ).count()

    # Total giving this month (USD equivalent)
    total_giving_this_month = db.session.query(
        func.coalesce(func.sum(ChurchIncome.amount_usd), 0)
    ).filter(
        ChurchIncome.church_id == church_id,
        ChurchIncome.date      >= this_month,
        ChurchIncome.date      <= today
    ).scalar()

    # Total expenses this month
    total_expenses_this_month = db.session.query(
        func.coalesce(func.sum(ChurchExpense.amount), 0)
    ).filter(
        ChurchExpense.church_id == church_id,
        ChurchExpense.date      >= this_month,
        ChurchExpense.date      <= today
    ).scalar()

    net_income = round(
        float(total_giving_this_month) - float(total_expenses_this_month), 2
    )

    # ── Absentee Alert ────────────────────────────────────────────────────────
    # Members not seen in any service in the last 3 weeks
    three_weeks_ago = today - timedelta(weeks=3)

    recent_services = ChurchService.query.filter(
        ChurchService.church_id    == church_id,
        ChurchService.service_date >= three_weeks_ago
    ).all()

    recent_service_ids = [s.id for s in recent_services]

    if recent_service_ids:
        attended_member_ids = db.session.query(
            AttendanceRecord.member_id
        ).filter(
            AttendanceRecord.church_id  == church_id,
            AttendanceRecord.service_id.in_(recent_service_ids),
            AttendanceRecord.status     == "Present",
            AttendanceRecord.member_id  != None
        ).distinct().all()

        attended_ids = {row[0] for row in attended_member_ids}

        absentees = Member.query.filter(
            Member.church_id == church_id,
            Member.status    == "Active",
            Member.id.notin_(attended_ids)
        ).order_by(Member.full_name).limit(10).all()
    else:
        absentees = []

    # ── Birthdays This Week ───────────────────────────────────────────────────
    # Compare month and day only — ignore year
    week_end = today + timedelta(days=6)

    all_active_members = Member.query.filter(
        Member.church_id    == church_id,
        Member.status       == "Active",
        Member.date_of_birth != None
    ).all()

    birthdays_this_week = []
    for member in all_active_members:
        bday = member.date_of_birth
        # Replace birth year with current year for comparison
        try:
            this_year_bday = bday.replace(year=today.year)
        except ValueError:
            # Feb 29 on a non-leap year — skip
            continue
        if today <= this_year_bday <= week_end:
            birthdays_this_week.append(member)

    # ── Upcoming Announcements ────────────────────────────────────────────────
    upcoming_announcements = Announcement.query.filter(
        Announcement.church_id == church_id,
    ).order_by(Announcement.created_at.desc()).limit(5).all()

    # ── Quick stats ───────────────────────────────────────────────────────────
    total_ministries = Ministry.query.filter_by(church_id=church_id).count()
    total_visitors   = Visitor.query.filter_by(
        church_id=church_id, converted=False
    ).count()

    return {
        "total_members":            total_members,
        "first_time_visitors":      first_time_visitors,
        "attendance_this_week":     attendance_this_week,
        "total_giving_this_month":  round(float(total_giving_this_month), 2),
        "total_expenses_this_month":round(float(total_expenses_this_month), 2),
        "net_income":               net_income,
        "absentees":                absentees,
        "birthdays_this_week":      birthdays_this_week,
        "upcoming_announcements":   upcoming_announcements,
        "total_ministries":         total_ministries,
        "total_visitors":           total_visitors,
        "today":                    today,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PASTOR DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/pastor")
@login_required
def pastor_dashboard():
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    cid  = current_user.church_id
    data = _get_dashboard_data(cid)

    return render_template("Dashboard/pastor_dashboard.html", **data)


# ─────────────────────────────────────────────────────────────────────────────
# SECRETARY DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/secretary")
@login_required
def secretary_dashboard():
    if current_user.role not in ("secretary", "super_admin"):
        return "Access denied", 403

    cid  = current_user.church_id
    data = _get_dashboard_data(cid)

    # Secretary doesn't see finance data — remove it
    data.pop("total_giving_this_month")
    data.pop("total_expenses_this_month")
    data.pop("net_income")

    return render_template("Dashboard/secretary_dashboard.html", **data)


# ─────────────────────────────────────────────────────────────────────────────
# SUPER ADMIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/superadmin")
@login_required
def super_admin_dashboard():
    if current_user.role != "super_admin":
        return "Access denied", 403

    # Platform-wide stats across all churches
    total_churches  = Church.query.count()
    active_churches = Church.query.filter_by(is_active=True).count()
    total_members   = Member.query.count()
    total_users     = ChurchUser.query.filter(
        ChurchUser.role != "super_admin"
    ).count()

    # All churches with their member counts
    churches = Church.query.order_by(Church.created_at.desc()).all()
    church_stats = []
    for church in churches:
        member_count = Member.query.filter_by(church_id=church.id).count()
        pastor       = ChurchUser.query.filter_by(
            church_id=church.id, role="pastor"
        ).first()
        church_stats.append({
            "church":       church,
            "member_count": member_count,
            "pastor":       pastor,
        })

    return render_template("Dashboard/superadmin_dashboard.html",
        total_churches  = total_churches,
        active_churches = active_churches,
        total_members   = total_members,
        total_users     = total_users,
        church_stats    = church_stats,
        today           = date.today(),
    )