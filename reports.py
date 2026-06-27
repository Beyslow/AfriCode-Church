from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, datetime, timedelta
from models import (
    db, Member, Visitor, VisitorFollowUp,
    ChurchService, AttendanceRecord,
    ChurchIncome, ChurchExpense,
    IncomeCategory, ExpenseCategory,
    Ministry, MinistryMember
)

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _reports_access():
    return current_user.role in ("pastor", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# REPORTS HOME
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/")
@login_required
def reports_home():
    if not _reports_access():
        return "Access denied", 403

    return render_template("Reports/reports_home.html")


# ─────────────────────────────────────────────────────────────────────────────
# MEMBERSHIP GROWTH REPORT
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/membership")
@login_required
def membership_report():
    if not _reports_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    total_active   = Member.query.filter_by(church_id=cid, status="Active").count()
    total_inactive = Member.query.filter_by(church_id=cid, status="Inactive").count()
    total_transfer = Member.query.filter_by(church_id=cid, status="Transfer").count()
    total_all      = total_active + total_inactive + total_transfer

    # Monthly new members — last 12 months
    monthly_growth = []
    for i in range(11, -1, -1):
        # Work backwards from current month
        if today.month - i <= 0:
            month_val = today.month - i + 12
            year_val  = today.year - 1
        else:
            month_val = today.month - i
            year_val  = today.year

        month_start = date(year_val, month_val, 1)
        if month_val == 12:
            month_end = date(year_val + 1, 1, 1)
        else:
            month_end = date(year_val, month_val + 1, 1)

        count = Member.query.filter(
            Member.church_id == cid,
            Member.join_date >= month_start,
            Member.join_date <  month_end,
        ).count()

        monthly_growth.append({
            "label": month_start.strftime("%b %Y"),
            "count": count,
        })

    # Gender breakdown
    male_count   = Member.query.filter_by(church_id=cid, status="Active", gender="Male").count()
    female_count = Member.query.filter_by(church_id=cid, status="Active", gender="Female").count()
    other_count  = total_active - male_count - female_count

    # Marital status breakdown
    marital_counts = db.session.query(
        Member.marital_status,
        func.count(Member.id)
    ).filter(
        Member.church_id == cid,
        Member.status    == "Active",
    ).group_by(Member.marital_status).all()

    marital_breakdown = [
        {"status": row[0] or "Not specified", "count": row[1]}
        for row in marital_counts
    ]

    # Birthdays this month
    birthdays_this_month = []
    all_members = Member.query.filter(
        Member.church_id     == cid,
        Member.status        == "Active",
        Member.date_of_birth != None,
    ).all()
    for m in all_members:
        if m.date_of_birth.month == today.month:
            birthdays_this_month.append(m)
    birthdays_this_month.sort(key=lambda m: m.date_of_birth.day)

    return render_template("Reports/membership_report.html",
        total_active          = total_active,
        total_inactive        = total_inactive,
        total_transfer        = total_transfer,
        total_all             = total_all,
        monthly_growth        = monthly_growth,
        male_count            = male_count,
        female_count          = female_count,
        other_count           = other_count,
        marital_breakdown     = marital_breakdown,
        birthdays_this_month  = birthdays_this_month,
        today                 = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE TRENDS REPORT
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/attendance")
@login_required
def attendance_report():
    if not _reports_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    # Last 8 Sunday services
    recent_services = ChurchService.query.filter(
        ChurchService.church_id    == cid,
        ChurchService.service_type == "Sunday",
    ).order_by(ChurchService.service_date.desc()).limit(8).all()
    recent_services.reverse()

    sunday_trend = []
    for service in recent_services:
        present = AttendanceRecord.query.filter_by(
            service_id=service.id,
            church_id=cid,
            status="Present",
        ).count()
        sunday_trend.append({
            "label":   service.service_date.strftime("%b %d"),
            "present": present,
            "service": service,
        })

    # Average attendance this month
    this_month    = today.replace(day=1)
    month_services = ChurchService.query.filter(
        ChurchService.church_id    == cid,
        ChurchService.service_date >= this_month,
        ChurchService.service_date <= today,
    ).all()

    month_totals = []
    for s in month_services:
        count = AttendanceRecord.query.filter_by(
            service_id=s.id, church_id=cid, status="Present"
        ).count()
        month_totals.append(count)

    avg_attendance = round(
        sum(month_totals) / len(month_totals), 1
    ) if month_totals else 0

    # Attendance by service type — all time
    service_type_stats = db.session.query(
        ChurchService.service_type,
        func.count(ChurchService.id).label("service_count"),
    ).filter(
        ChurchService.church_id == cid,
    ).group_by(ChurchService.service_type).all()

    by_service_type = [
        {"type": row[0], "count": row[1]}
        for row in service_type_stats
    ]

    # Top 5 best-attended services
    all_services = ChurchService.query.filter_by(church_id=cid).all()
    service_attendance = []
    for s in all_services:
        count = AttendanceRecord.query.filter_by(
            service_id=s.id, church_id=cid, status="Present"
        ).count()
        service_attendance.append({"service": s, "count": count})

    top_services = sorted(
        service_attendance, key=lambda x: x["count"], reverse=True
    )[:5]

    return render_template("Reports/attendance_report.html",
        sunday_trend    = sunday_trend,
        avg_attendance  = avg_attendance,
        by_service_type = by_service_type,
        top_services    = top_services,
        today           = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GIVING TRENDS REPORT
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/giving")
@login_required
def giving_report():
    if not _reports_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    # Monthly giving — last 12 months
    monthly_giving = []
    for i in range(11, -1, -1):
        if today.month - i <= 0:
            month_val = today.month - i + 12
            year_val  = today.year - 1
        else:
            month_val = today.month - i
            year_val  = today.year

        month_start = date(year_val, month_val, 1)
        if month_val == 12:
            month_end = date(year_val + 1, 1, 1)
        else:
            month_end = date(year_val, month_val + 1, 1)

        total = db.session.query(
            func.coalesce(func.sum(ChurchIncome.amount_usd), 0)
        ).filter(
            ChurchIncome.church_id == cid,
            ChurchIncome.date      >= month_start,
            ChurchIncome.date      <  month_end,
        ).scalar()

        monthly_giving.append({
            "label": month_start.strftime("%b %Y"),
            "total": round(float(total), 2),
        })

    # Income by category — all time
    income_categories = IncomeCategory.query.filter_by(
        church_id=cid, is_active=True
    ).all()

    by_category = []
    for cat in income_categories:
        total = db.session.query(
            func.coalesce(func.sum(ChurchIncome.amount_usd), 0)
        ).filter(
            ChurchIncome.church_id   == cid,
            ChurchIncome.category_id == cat.id,
        ).scalar()
        if float(total) > 0:
            by_category.append({
                "name":  cat.name,
                "total": round(float(total), 2),
            })

    # Monthly expenses — last 12 months
    monthly_expenses = []
    for i in range(11, -1, -1):
        if today.month - i <= 0:
            month_val = today.month - i + 12
            year_val  = today.year - 1
        else:
            month_val = today.month - i
            year_val  = today.year

        month_start = date(year_val, month_val, 1)
        if month_val == 12:
            month_end = date(year_val + 1, 1, 1)
        else:
            month_end = date(year_val, month_val + 1, 1)

        total = db.session.query(
            func.coalesce(func.sum(ChurchExpense.amount), 0)
        ).filter(
            ChurchExpense.church_id == cid,
            ChurchExpense.date      >= month_start,
            ChurchExpense.date      <  month_end,
        ).scalar()

        monthly_expenses.append({
            "label": month_start.strftime("%b %Y"),
            "total": round(float(total), 2),
        })

    # Net position per month
    net_by_month = []
    for income, expense in zip(monthly_giving, monthly_expenses):
        net_by_month.append({
            "label": income["label"],
            "net":   round(income["total"] - expense["total"], 2),
        })

    total_income_all  = sum(m["total"] for m in monthly_giving)
    total_expense_all = sum(m["total"] for m in monthly_expenses)
    net_all           = round(total_income_all - total_expense_all, 2)

    return render_template("Reports/giving_report.html",
        monthly_giving   = monthly_giving,
        monthly_expenses = monthly_expenses,
        net_by_month     = net_by_month,
        by_category      = by_category,
        total_income_all = round(total_income_all, 2),
        total_expense_all= round(total_expense_all, 2),
        net_all          = net_all,
        today            = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# VISITOR CONVERSION REPORT
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/visitors")
@login_required
def visitor_report():
    if not _reports_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    total_visitors  = Visitor.query.filter_by(church_id=cid).count()
    total_converted = Visitor.query.filter_by(church_id=cid, converted=True).count()
    total_pending   = Visitor.query.filter_by(church_id=cid, converted=False).count()

    conversion_rate = round(
        (total_converted / total_visitors * 100) if total_visitors > 0 else 0, 1
    )

    # Monthly visitor registrations — last 6 months
    monthly_visitors = []
    for i in range(5, -1, -1):
        if today.month - i <= 0:
            month_val = today.month - i + 12
            year_val  = today.year - 1
        else:
            month_val = today.month - i
            year_val  = today.year

        month_start = date(year_val, month_val, 1)
        if month_val == 12:
            month_end = date(year_val + 1, 1, 1)
        else:
            month_end = date(year_val, month_val + 1, 1)

        count = Visitor.query.filter(
            Visitor.church_id  == cid,
            Visitor.visit_date >= month_start,
            Visitor.visit_date <  month_end,
        ).count()

        monthly_visitors.append({
            "label": month_start.strftime("%b %Y"),
            "count": count,
        })

    # Follow-up method breakdown
    followup_methods = db.session.query(
        VisitorFollowUp.method,
        func.count(VisitorFollowUp.id),
    ).filter(
        VisitorFollowUp.church_id == cid,
    ).group_by(VisitorFollowUp.method).all()

    followup_breakdown = [
        {"method": row[0], "count": row[1]}
        for row in followup_methods
    ]

    # Visitors with no follow-up
    visited_ids = db.session.query(
        VisitorFollowUp.visitor_id
    ).filter_by(church_id=cid).distinct().all()
    visited_ids = {row[0] for row in visited_ids}

    no_followup = Visitor.query.filter(
        Visitor.church_id == cid,
        Visitor.converted == False,
        Visitor.id.notin_(visited_ids),
    ).order_by(Visitor.visit_date.desc()).limit(20).all()

    return render_template("Reports/visitor_report.html",
        total_visitors     = total_visitors,
        total_converted    = total_converted,
        total_pending      = total_pending,
        conversion_rate    = conversion_rate,
        monthly_visitors   = monthly_visitors,
        followup_breakdown = followup_breakdown,
        no_followup        = no_followup,
        today              = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MINISTRY HEALTH REPORT
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/ministry")
@login_required
def ministry_report():
    if not _reports_access():
        return "Access denied", 403

    cid = current_user.church_id

    ministries = Ministry.query.filter_by(
        church_id=cid
    ).order_by(Ministry.name).all()

    ministry_health = []
    for ministry in ministries:
        member_count = MinistryMember.query.filter_by(
            ministry_id=ministry.id, church_id=cid
        ).count()

        leader = MinistryMember.query.filter_by(
            ministry_id=ministry.id, church_id=cid, role="Leader"
        ).first()

        ministry_health.append({
            "ministry":     ministry,
            "member_count": member_count,
            "leader":       leader.member if leader else None,
            "has_leader":   leader is not None,
            "health":       "Good" if leader and member_count >= 3 else
                            "Needs Attention" if not leader else "Growing",
        })

    # Overall ministry stats
    total_ministries       = len(ministries)
    ministries_with_leader = sum(1 for m in ministry_health if m["has_leader"])
    largest_ministry       = max(
        ministry_health, key=lambda m: m["member_count"]
    ) if ministry_health else None

    return render_template("Reports/ministry_report.html",
        ministry_health        = ministry_health,
        total_ministries       = total_ministries,
        ministries_with_leader = ministries_with_leader,
        largest_ministry       = largest_ministry,
    )