from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify
)
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, datetime, timedelta
from models import (
    db, ChurchService, AttendanceRecord,
    Member, Visitor, Church
)

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARDS
# ─────────────────────────────────────────────────────────────────────────────

def _full_access():
    return current_user.role in ("pastor", "secretary", "super_admin")

def _mark_access():
    return current_user.role in ("pastor", "secretary", "usher", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE LIST
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/")
@login_required
def service_list():
    if not _full_access():
        return "Access denied", 403

    cid      = current_user.church_id
    page     = request.args.get("page", 1, type=int)
    per_page = 20

    # Filters
    service_type = request.args.get("type", "")
    month        = request.args.get("month", "")

    query = ChurchService.query.filter_by(church_id=cid)

    if service_type:
        query = query.filter_by(service_type=service_type)

    if month:
        try:
            year_val  = int(month[:4])
            month_val = int(month[5:7])
            query = query.filter(
                func.extract("year",  ChurchService.service_date) == year_val,
                func.extract("month", ChurchService.service_date) == month_val,
            )
        except (ValueError, IndexError):
            pass

    query      = query.order_by(ChurchService.service_date.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    services   = pagination.items

    # Attach attendance count to each service
    service_data = []
    for service in services:
        count = AttendanceRecord.query.filter_by(
            service_id=service.id,
            church_id=cid,
            status="Present"
        ).count()
        service_data.append({
            "service": service,
            "count":   count,
        })

    return render_template("Attendance/service_list.html",
        service_data = service_data,
        pagination   = pagination,
        service_type = service_type,
        month        = month,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CREATE SERVICE
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/service/create", methods=["GET", "POST"])
@login_required
def create_service():
    if not _full_access():
        return "Access denied", 403

    if request.method == "POST":
        cid = current_user.church_id

        date_str     = request.form.get("service_date", "").strip()
        service_date = date.today()
        if date_str:
            try:
                service_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format.", "warning")
                return redirect(url_for("attendance.create_service"))

        service_type = request.form.get("service_type", "Sunday")
        # Auto-generate a name if none provided
        name = request.form.get("name", "").strip()
        if not name:
            name = f"{service_type} Service — {service_date.strftime('%B %d, %Y')}"

        service = ChurchService(
            church_id    = cid,
            created_by   = current_user.id,
            name         = name,
            service_type = service_type,
            service_date = service_date,
        )
        db.session.add(service)
        db.session.commit()

        flash(f'"{service.name}" created. You can now mark attendance.', "success")
        return redirect(url_for("attendance.mark_attendance", service_id=service.id))

    return render_template("Attendance/create_service.html")


# ─────────────────────────────────────────────────────────────────────────────
# MARK ATTENDANCE  —  full desktop view
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/service/<int:service_id>", methods=["GET", "POST"])
@login_required
def mark_attendance(service_id):
    if not _mark_access():
        return "Access denied", 403

    cid     = current_user.church_id
    service = ChurchService.query.filter_by(
        id=service_id, church_id=cid
    ).first_or_404()

    if request.method == "POST":
        # Collect all member IDs that were marked present
        present_ids = request.form.getlist("present_member_ids")
        present_ids = {int(i) for i in present_ids if i}

        # All active members for this church
        all_members = Member.query.filter_by(
            church_id=cid, status="Active"
        ).all()

        for member in all_members:
            status = "Present" if member.id in present_ids else "Absent"

            existing = AttendanceRecord.query.filter_by(
                service_id=service_id,
                member_id=member.id,
            ).first()

            if existing:
                existing.status    = status
                existing.marked_by = current_user.id
            else:
                db.session.add(AttendanceRecord(
                    church_id  = cid,
                    service_id = service_id,
                    member_id  = member.id,
                    status     = status,
                    marked_by  = current_user.id,
                ))

        db.session.commit()
        flash("Attendance saved.", "success")
        return redirect(url_for("attendance.service_detail", service_id=service_id))

    # GET — load existing records to pre-fill checkboxes
    all_members = Member.query.filter_by(
        church_id=cid, status="Active"
    ).order_by(Member.full_name).all()

    existing_records = AttendanceRecord.query.filter_by(
        service_id=service_id, church_id=cid
    ).all()
    marked_present = {r.member_id for r in existing_records if r.status == "Present"}

    return render_template("Attendance/mark_attendance.html",
        service        = service,
        all_members    = all_members,
        marked_present = marked_present,
    )


# ─────────────────────────────────────────────────────────────────────────────
# USHER VIEW  —  mobile-optimised attendance marking
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/usher")
@login_required
def usher_view():
    if not _mark_access():
        return "Access denied", 403

    cid = current_user.church_id

    # Show the most recent service by default, or one selected by the usher
    service_id = request.args.get("service_id", type=int)

    if service_id:
        service = ChurchService.query.filter_by(
            id=service_id, church_id=cid
        ).first_or_404()
    else:
        service = ChurchService.query.filter_by(
            church_id=cid
        ).order_by(ChurchService.service_date.desc()).first()

    # Recent services for the dropdown
    recent_services = ChurchService.query.filter_by(
        church_id=cid
    ).order_by(ChurchService.service_date.desc()).limit(10).all()

    members = []
    marked_present = set()

    if service:
        members = Member.query.filter_by(
            church_id=cid, status="Active"
        ).order_by(Member.full_name).all()

        existing_records = AttendanceRecord.query.filter_by(
            service_id=service.id, church_id=cid
        ).all()
        marked_present = {r.member_id for r in existing_records if r.status == "Present"}

    return render_template("Attendance/usher_view.html",
        service         = service,
        recent_services = recent_services,
        members         = members,
        marked_present  = marked_present,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MARK SINGLE MEMBER  —  AJAX endpoint for usher tap-to-mark
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/service/<int:service_id>/mark", methods=["POST"])
@login_required
def mark_single(service_id):
    if not _mark_access():
        return jsonify({"error": "Access denied"}), 403

    cid     = current_user.church_id
    service = ChurchService.query.filter_by(
        id=service_id, church_id=cid
    ).first_or_404()

    data      = request.get_json()
    member_id = data.get("member_id")
    status    = data.get("status", "Present")   # Present or Absent

    if not member_id:
        return jsonify({"error": "member_id required"}), 400

    member = Member.query.filter_by(id=member_id, church_id=cid).first()
    if not member:
        return jsonify({"error": "Member not found"}), 404

    existing = AttendanceRecord.query.filter_by(
        service_id=service_id,
        member_id=member_id,
    ).first()

    if existing:
        existing.status    = status
        existing.marked_by = current_user.id
    else:
        db.session.add(AttendanceRecord(
            church_id  = cid,
            service_id = service_id,
            member_id  = member_id,
            status     = status,
            marked_by  = current_user.id,
        ))

    db.session.commit()
    return jsonify({"success": True, "status": status, "member_id": member_id})


# ─────────────────────────────────────────────────────────────────────────────
# CAPTURE VISITOR DURING SERVICE
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/service/<int:service_id>/visitor", methods=["POST"])
@login_required
def capture_visitor(service_id):
    if not _mark_access():
        return "Access denied", 403

    cid     = current_user.church_id
    service = ChurchService.query.filter_by(
        id=service_id, church_id=cid
    ).first_or_404()

    full_name = request.form.get("full_name", "").strip()
    phone     = request.form.get("phone", "").strip() or None

    if not full_name:
        flash("Visitor name is required.", "warning")
        return redirect(url_for("attendance.service_detail", service_id=service_id))

    # Create visitor record
    visitor = Visitor(
        church_id  = cid,
        full_name  = full_name,
        phone      = phone,
        visit_date = service.service_date,
        converted  = False,
    )
    db.session.add(visitor)
    db.session.flush()

    # Mark them present in this service
    db.session.add(AttendanceRecord(
        church_id  = cid,
        service_id = service_id,
        visitor_id = visitor.id,
        status     = "Present",
        marked_by  = current_user.id,
    ))
    db.session.commit()

    flash(f"{full_name} captured as a visitor and marked present.", "success")
    return redirect(url_for("attendance.service_detail", service_id=service_id))


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE DETAIL  —  read-only summary after marking
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/service/<int:service_id>/detail")
@login_required
def service_detail(service_id):
    if not _mark_access():
        return "Access denied", 403

    cid     = current_user.church_id
    service = ChurchService.query.filter_by(
        id=service_id, church_id=cid
    ).first_or_404()

    records = AttendanceRecord.query.filter_by(
        service_id=service_id, church_id=cid
    ).all()

    present_members  = [r for r in records if r.member_id and r.status == "Present"]
    absent_members   = [r for r in records if r.member_id and r.status == "Absent"]
    present_visitors = [r for r in records if r.visitor_id and r.status == "Present"]

    total_present = len(present_members) + len(present_visitors)
    total_absent  = len(absent_members)

    return render_template("Attendance/service_detail.html",
        service          = service,
        present_members  = present_members,
        absent_members   = absent_members,
        present_visitors = present_visitors,
        total_present    = total_present,
        total_absent     = total_absent,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE SERVICE
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/service/<int:service_id>/delete", methods=["POST"])
@login_required
def delete_service(service_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    cid     = current_user.church_id
    service = ChurchService.query.filter_by(
        id=service_id, church_id=cid
    ).first_or_404()

    name = service.name
    db.session.delete(service)
    db.session.commit()

    flash(f'"{name}" and all attendance records deleted.', "success")
    return redirect(url_for("attendance.service_list"))


# ─────────────────────────────────────────────────────────────────────────────
# ABSENTEE REPORT
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/absentees")
@login_required
def absentee_report():
    if not _full_access():
        return "Access denied", 403

    cid         = current_user.church_id
    today       = date.today()
    weeks       = request.args.get("weeks", 3, type=int)
    cutoff_date = today - timedelta(weeks=weeks)

    recent_services = ChurchService.query.filter(
        ChurchService.church_id    == cid,
        ChurchService.service_date >= cutoff_date,
    ).all()

    recent_service_ids = [s.id for s in recent_services]

    if recent_service_ids:
        attended_ids = db.session.query(
            AttendanceRecord.member_id
        ).filter(
            AttendanceRecord.church_id  == cid,
            AttendanceRecord.service_id.in_(recent_service_ids),
            AttendanceRecord.status     == "Present",
            AttendanceRecord.member_id  != None,
        ).distinct().all()

        attended_ids = {row[0] for row in attended_ids}

        absentees = Member.query.filter(
            Member.church_id == cid,
            Member.status    == "Active",
            Member.id.notin_(attended_ids),
        ).order_by(Member.full_name).all()
    else:
        absentees = []

    return render_template("Attendance/absentee_report.html",
        absentees       = absentees,
        weeks           = weeks,
        cutoff_date     = cutoff_date,
        recent_services = recent_services,
        today           = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# WEEKLY REPORT
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/reports/weekly")
@login_required
def weekly_report():
    if not _full_access():
        return "Access denied", 403

    cid        = current_user.church_id
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end   = week_start + timedelta(days=6)

    services = ChurchService.query.filter(
        ChurchService.church_id    == cid,
        ChurchService.service_date >= week_start,
        ChurchService.service_date <= week_end,
    ).order_by(ChurchService.service_date).all()

    report = []
    for service in services:
        present = AttendanceRecord.query.filter_by(
            service_id=service.id, church_id=cid, status="Present"
        ).count()
        absent = AttendanceRecord.query.filter_by(
            service_id=service.id, church_id=cid, status="Absent"
        ).count()
        report.append({
            "service": service,
            "present": present,
            "absent":  absent,
            "total":   present + absent,
        })

    return render_template("Attendance/weekly_report.html",
        report     = report,
        week_start = week_start,
        week_end   = week_end,
        today      = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY REPORT
# ─────────────────────────────────────────────────────────────────────────────

@attendance_bp.route("/reports/monthly")
@login_required
def monthly_report():
    if not _full_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    # Allow selecting a month via query param e.g. ?month=2026-03
    month_str = request.args.get("month", today.strftime("%Y-%m"))
    try:
        year_val  = int(month_str[:4])
        month_val = int(month_str[5:7])
    except (ValueError, IndexError):
        year_val  = today.year
        month_val = today.month

    month_start = date(year_val, month_val, 1)

    # Last day of month
    if month_val == 12:
        month_end = date(year_val + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year_val, month_val + 1, 1) - timedelta(days=1)

    services = ChurchService.query.filter(
        ChurchService.church_id    == cid,
        ChurchService.service_date >= month_start,
        ChurchService.service_date <= month_end,
    ).order_by(ChurchService.service_date).all()

    report = []
    total_present_month = 0
    total_absent_month  = 0

    for service in services:
        present = AttendanceRecord.query.filter_by(
            service_id=service.id, church_id=cid, status="Present"
        ).count()
        absent = AttendanceRecord.query.filter_by(
            service_id=service.id, church_id=cid, status="Absent"
        ).count()
        total_present_month += present
        total_absent_month  += absent
        report.append({
            "service": service,
            "present": present,
            "absent":  absent,
            "total":   present + absent,
        })

    return render_template("Attendance/monthly_report.html",
        report              = report,
        month_start         = month_start,
        month_end           = month_end,
        month_str           = month_str,
        total_present_month = total_present_month,
        total_absent_month  = total_absent_month,
        today               = today,
    )