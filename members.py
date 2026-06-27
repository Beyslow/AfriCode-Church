import csv
import io
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, stream_with_context
)
from flask_login import login_required, current_user
from datetime import date, datetime
from models import db, Member, Ministry, MinistryMember

members_bp = Blueprint("members", __name__, url_prefix="/members")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _members_access():
    return current_user.role in ("pastor", "secretary", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# MEMBER LIST
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/")
@login_required
def member_list():
    if not _members_access():
        return "Access denied", 403

    cid      = current_user.church_id
    page     = request.args.get("page", 1, type=int)
    per_page = 25

    # Filters
    search   = request.args.get("q", "").strip()
    status   = request.args.get("status", "")
    gender   = request.args.get("gender", "")

    query = Member.query.filter_by(church_id=cid)

    if search:
        query = query.filter(
            Member.full_name.ilike(f"%{search}%") |
            Member.phone.ilike(f"%{search}%")
        )
    if status:
        query = query.filter_by(status=status)
    if gender:
        query = query.filter_by(gender=gender)

    query      = query.order_by(Member.full_name)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    members    = pagination.items

    return render_template("Members/member_list.html",
        members    = members,
        pagination = pagination,
        search     = search,
        status     = status,
        gender     = gender,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADD MEMBER
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_member():
    if not _members_access():
        return "Access denied", 403

    if request.method == "POST":
        cid = current_user.church_id

        # Parse date of birth safely
        dob_str = request.form.get("date_of_birth", "").strip()
        dob     = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date of birth format.", "warning")
                return redirect(url_for("members.add_member"))

        # Parse join date — default to today
        join_str  = request.form.get("join_date", "").strip()
        join_date = date.today()
        if join_str:
            try:
                join_date = datetime.strptime(join_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        member = Member(
            church_id         = cid,
            full_name         = request.form.get("full_name", "").strip(),
            phone             = request.form.get("phone", "").strip() or None,
            email             = request.form.get("email", "").strip() or None,
            gender            = request.form.get("gender", "").strip() or None,
            date_of_birth     = dob,
            address           = request.form.get("address", "").strip() or None,
            marital_status    = request.form.get("marital_status", "").strip() or None,
            occupation        = request.form.get("occupation", "").strip() or None,
            emergency_contact = request.form.get("emergency_contact", "").strip() or None,
            join_date         = join_date,
            status            = request.form.get("status", "Active"),
        )
        db.session.add(member)
        db.session.commit()

        flash(f"{member.full_name} added successfully.", "success")
        return redirect(url_for("members.member_list"))

    return render_template("Members/add_member.html")


# ─────────────────────────────────────────────────────────────────────────────
# MEMBER PROFILE
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/<int:member_id>")
@login_required
def member_profile(member_id):
    if not _members_access():
        return "Access denied", 403

    member = Member.query.filter_by(
        id=member_id, church_id=current_user.church_id
    ).first_or_404()

    # Ministries this member belongs to
    ministry_memberships = MinistryMember.query.filter_by(
        member_id=member_id, church_id=current_user.church_id
    ).all()

    return render_template("Members/member_profile.html",
        member               = member,
        ministry_memberships = ministry_memberships,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EDIT MEMBER
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/<int:member_id>/edit", methods=["GET", "POST"])
@login_required
def edit_member(member_id):
    if not _members_access():
        return "Access denied", 403

    member = Member.query.filter_by(
        id=member_id, church_id=current_user.church_id
    ).first_or_404()

    if request.method == "POST":
        dob_str = request.form.get("date_of_birth", "").strip()
        dob     = member.date_of_birth
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date of birth format.", "warning")
                return redirect(url_for("members.edit_member", member_id=member_id))

        join_str = request.form.get("join_date", "").strip()
        if join_str:
            try:
                member.join_date = datetime.strptime(join_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        member.full_name         = request.form.get("full_name", "").strip()
        member.phone             = request.form.get("phone", "").strip() or None
        member.email             = request.form.get("email", "").strip() or None
        member.gender            = request.form.get("gender", "").strip() or None
        member.date_of_birth     = dob
        member.address           = request.form.get("address", "").strip() or None
        member.marital_status    = request.form.get("marital_status", "").strip() or None
        member.occupation        = request.form.get("occupation", "").strip() or None
        member.emergency_contact = request.form.get("emergency_contact", "").strip() or None
        member.status            = request.form.get("status", member.status)

        db.session.commit()
        flash(f"{member.full_name} updated successfully.", "success")
        return redirect(url_for("members.member_profile", member_id=member_id))

    return render_template("Members/edit_member.html", member=member)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE MEMBER
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/<int:member_id>/delete", methods=["POST"])
@login_required
def delete_member(member_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    member = Member.query.filter_by(
        id=member_id, church_id=current_user.church_id
    ).first_or_404()

    name = member.full_name
    db.session.delete(member)
    db.session.commit()

    flash(f"{name} removed from the system.", "success")
    return redirect(url_for("members.member_list"))


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH  —  JSON endpoint for live search / autocomplete
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/search/json")
@login_required
def search_json():
    from flask import jsonify

    cid   = current_user.church_id
    query = request.args.get("q", "").strip()

    if len(query) < 2:
        return jsonify([])

    members = Member.query.filter(
        Member.church_id  == cid,
        Member.full_name.ilike(f"%{query}%")
    ).limit(8).all()

    return jsonify([{
        "id":     m.id,
        "name":   m.full_name,
        "phone":  m.phone or "—",
        "status": m.status,
        "url":    url_for("members.member_profile", member_id=m.id),
    } for m in members])


# ─────────────────────────────────────────────────────────────────────────────
# BIRTHDAYS
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/birthdays")
@login_required
def birthdays():
    if not _members_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    all_members = Member.query.filter(
        Member.church_id     == cid,
        Member.status        == "Active",
        Member.date_of_birth != None
    ).order_by(Member.full_name).all()

    # Sort by upcoming birthday within the year
    upcoming = []
    for m in all_members:
        try:
            bday_this_year = m.date_of_birth.replace(year=today.year)
        except ValueError:
            continue
        if bday_this_year < today:
            # Push to next year
            bday_this_year = m.date_of_birth.replace(year=today.year + 1)
        upcoming.append((bday_this_year, m))

    upcoming.sort(key=lambda x: x[0])
    sorted_members = [m for _, m in upcoming]

    return render_template("Members/birthdays.html",
        members = sorted_members,
        today   = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT CSV
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/export/csv")
@login_required
def export_csv():
    if not _members_access():
        return "Access denied", 403

    cid     = current_user.church_id
    members = Member.query.filter_by(church_id=cid).order_by(Member.full_name).all()

    headers = [
        "Full Name", "Phone", "Email", "Gender",
        "Date of Birth", "Address", "Marital Status",
        "Occupation", "Emergency Contact", "Join Date", "Status"
    ]

    def generate():
        buf = io.StringIO()
        w   = csv.writer(buf)
        w.writerow(headers)
        for m in members:
            w.writerow([
                m.full_name,
                m.phone             or "",
                m.email             or "",
                m.gender            or "",
                m.date_of_birth     or "",
                m.address           or "",
                m.marital_status    or "",
                m.occupation        or "",
                m.emergency_contact or "",
                m.join_date         or "",
                m.status,
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=members.csv"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# IMPORT CSV
# ─────────────────────────────────────────────────────────────────────────────

@members_bp.route("/import/csv", methods=["GET", "POST"])
@login_required
def import_csv():
    if not _members_access():
        return "Access denied", 403

    if request.method == "POST":
        cid  = current_user.church_id
        file = request.files.get("csv_file")

        if not file or not file.filename.endswith(".csv"):
            flash("Please upload a valid .csv file.", "warning")
            return redirect(url_for("members.import_csv"))

        stream  = io.StringIO(file.stream.read().decode("utf-8"), newline=None)
        reader  = csv.DictReader(stream)
        added   = 0
        skipped = []

        for row in reader:
            full_name = row.get("Full Name", "").strip()
            if not full_name:
                skipped.append("Row skipped — missing Full Name.")
                continue

            # Parse date of birth
            dob = None
            dob_str = row.get("Date of Birth", "").strip()
            if dob_str:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                    try:
                        dob = datetime.strptime(dob_str, fmt).date()
                        break
                    except ValueError:
                        continue

            # Parse join date
            join_date = date.today()
            join_str  = row.get("Join Date", "").strip()
            if join_str:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                    try:
                        join_date = datetime.strptime(join_str, fmt).date()
                        break
                    except ValueError:
                        continue

            member = Member(
                church_id         = cid,
                full_name         = full_name,
                phone             = row.get("Phone", "").strip()             or None,
                email             = row.get("Email", "").strip()             or None,
                gender            = row.get("Gender", "").strip()            or None,
                date_of_birth     = dob,
                address           = row.get("Address", "").strip()           or None,
                marital_status    = row.get("Marital Status", "").strip()    or None,
                occupation        = row.get("Occupation", "").strip()        or None,
                emergency_contact = row.get("Emergency Contact", "").strip() or None,
                join_date         = join_date,
                status            = row.get("Status", "Active").strip()      or "Active",
            )
            db.session.add(member)
            added += 1

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Import failed: {e}", "danger")
            return redirect(url_for("members.import_csv"))

        for msg in skipped:
            flash(msg, "warning")

        flash(f"{added} member(s) imported successfully.", "success")
        return redirect(url_for("members.member_list"))

    return render_template("Members/import_csv.html")