from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash
)
from flask_login import login_required, current_user
from models import db, Ministry, MinistryMember, Member

ministries_bp = Blueprint("ministries", __name__, url_prefix="/ministries")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _ministries_access():
    return current_user.role in ("pastor", "secretary", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# MINISTRY LIST
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/")
@login_required
def ministry_list():
    if not _ministries_access():
        return "Access denied", 403

    cid        = current_user.church_id
    ministries = Ministry.query.filter_by(church_id=cid).order_by(Ministry.name).all()

    # Attach member count to each ministry
    ministry_data = []
    for ministry in ministries:
        member_count = MinistryMember.query.filter_by(
            ministry_id=ministry.id, church_id=cid
        ).count()
        leader = MinistryMember.query.filter_by(
            ministry_id=ministry.id, church_id=cid, role="Leader"
        ).first()
        ministry_data.append({
            "ministry":     ministry,
            "member_count": member_count,
            "leader":       leader.member if leader else None,
        })

    return render_template("Ministries/ministry_list.html",
        ministry_data = ministry_data,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADD MINISTRY
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_ministry():
    if not _ministries_access():
        return "Access denied", 403

    if request.method == "POST":
        cid  = current_user.church_id
        name = request.form.get("name", "").strip()

        if not name:
            flash("Ministry name is required.", "warning")
            return redirect(url_for("ministries.add_ministry"))

        existing = Ministry.query.filter_by(church_id=cid, name=name).first()
        if existing:
            flash(f'A ministry named "{name}" already exists.', "warning")
            return redirect(url_for("ministries.add_ministry"))

        ministry = Ministry(
            church_id    = cid,
            name         = name,
            description  = request.form.get("description", "").strip() or None,
            meeting_day  = request.form.get("meeting_day", "").strip()  or None,
            meeting_time = request.form.get("meeting_time", "").strip() or None,
        )
        db.session.add(ministry)
        db.session.commit()

        flash(f'Ministry "{name}" created.', "success")
        return redirect(url_for("ministries.ministry_detail", ministry_id=ministry.id))

    return render_template("Ministries/add_ministry.html")


# ─────────────────────────────────────────────────────────────────────────────
# MINISTRY DETAIL  —  members list + assignment form
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/<int:ministry_id>")
@login_required
def ministry_detail(ministry_id):
    if not _ministries_access():
        return "Access denied", 403

    cid      = current_user.church_id
    ministry = Ministry.query.filter_by(
        id=ministry_id, church_id=cid
    ).first_or_404()

    # Current ministry members with their roles
    memberships = MinistryMember.query.filter_by(
        ministry_id=ministry_id, church_id=cid
    ).order_by(MinistryMember.role.desc()).all()
    # desc() puts "Leader" before "Member" alphabetically

    # All active church members not yet in this ministry
    assigned_member_ids = {mm.member_id for mm in memberships}
    available_members   = Member.query.filter(
        Member.church_id == cid,
        Member.status    == "Active",
        Member.id.notin_(assigned_member_ids)
    ).order_by(Member.full_name).all()

    return render_template("Ministries/ministry_detail.html",
        ministry          = ministry,
        memberships       = memberships,
        available_members = available_members,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EDIT MINISTRY
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/<int:ministry_id>/edit", methods=["GET", "POST"])
@login_required
def edit_ministry(ministry_id):
    if not _ministries_access():
        return "Access denied", 403

    cid      = current_user.church_id
    ministry = Ministry.query.filter_by(
        id=ministry_id, church_id=cid
    ).first_or_404()

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Ministry name is required.", "warning")
            return redirect(url_for("ministries.edit_ministry", ministry_id=ministry_id))

        # Check name uniqueness excluding self
        existing = Ministry.query.filter(
            Ministry.church_id == cid,
            Ministry.name      == name,
            Ministry.id        != ministry_id
        ).first()
        if existing:
            flash(f'A ministry named "{name}" already exists.', "warning")
            return redirect(url_for("ministries.edit_ministry", ministry_id=ministry_id))

        ministry.name         = name
        ministry.description  = request.form.get("description", "").strip() or None
        ministry.meeting_day  = request.form.get("meeting_day", "").strip()  or None
        ministry.meeting_time = request.form.get("meeting_time", "").strip() or None

        db.session.commit()
        flash(f'"{ministry.name}" updated.', "success")
        return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))

    return render_template("Ministries/edit_ministry.html", ministry=ministry)


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGN MEMBER TO MINISTRY
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/<int:ministry_id>/assign", methods=["POST"])
@login_required
def assign_member(ministry_id):
    if not _ministries_access():
        return "Access denied", 403

    cid      = current_user.church_id
    ministry = Ministry.query.filter_by(
        id=ministry_id, church_id=cid
    ).first_or_404()

    member_id = request.form.get("member_id", type=int)
    role      = request.form.get("role", "Member")  # Leader or Member

    if not member_id:
        flash("Please select a member.", "warning")
        return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))

    # Verify member belongs to this church
    member = Member.query.filter_by(id=member_id, church_id=cid).first()
    if not member:
        flash("Member not found.", "warning")
        return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))

    # Check not already assigned
    existing = MinistryMember.query.filter_by(
        ministry_id=ministry_id, member_id=member_id
    ).first()
    if existing:
        flash(f"{member.full_name} is already in this ministry.", "warning")
        return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))

    # If assigning a new Leader, demote any existing leader to Member
    if role == "Leader":
        current_leader = MinistryMember.query.filter_by(
            ministry_id=ministry_id, church_id=cid, role="Leader"
        ).first()
        if current_leader:
            current_leader.role = "Member"

    db.session.add(MinistryMember(
        ministry_id = ministry_id,
        member_id   = member_id,
        church_id   = cid,
        role        = role,
    ))
    db.session.commit()

    flash(f"{member.full_name} added to {ministry.name} as {role}.", "success")
    return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE MEMBER ROLE WITHIN MINISTRY
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/<int:ministry_id>/member/<int:membership_id>/role", methods=["POST"])
@login_required
def change_member_role(ministry_id, membership_id):
    if not _ministries_access():
        return "Access denied", 403

    cid        = current_user.church_id
    membership = MinistryMember.query.filter_by(
        id=membership_id, ministry_id=ministry_id, church_id=cid
    ).first_or_404()

    new_role = request.form.get("role", "Member")

    # If promoting to Leader, demote current leader first
    if new_role == "Leader":
        current_leader = MinistryMember.query.filter(
            MinistryMember.ministry_id == ministry_id,
            MinistryMember.church_id   == cid,
            MinistryMember.role        == "Leader",
            MinistryMember.id          != membership_id
        ).first()
        if current_leader:
            current_leader.role = "Member"

    membership.role = new_role
    db.session.commit()

    flash(f"Role updated to {new_role}.", "success")
    return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))


# ─────────────────────────────────────────────────────────────────────────────
# REMOVE MEMBER FROM MINISTRY
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/<int:ministry_id>/remove/<int:membership_id>", methods=["POST"])
@login_required
def remove_member(ministry_id, membership_id):
    if not _ministries_access():
        return "Access denied", 403

    cid        = current_user.church_id
    membership = MinistryMember.query.filter_by(
        id=membership_id, ministry_id=ministry_id, church_id=cid
    ).first_or_404()

    member_name = membership.member.full_name
    db.session.delete(membership)
    db.session.commit()

    flash(f"{member_name} removed from ministry.", "success")
    return redirect(url_for("ministries.ministry_detail", ministry_id=ministry_id))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE MINISTRY
# ─────────────────────────────────────────────────────────────────────────────

@ministries_bp.route("/<int:ministry_id>/delete", methods=["POST"])
@login_required
def delete_ministry(ministry_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    cid      = current_user.church_id
    ministry = Ministry.query.filter_by(
        id=ministry_id, church_id=cid
    ).first_or_404()

    name = ministry.name
    db.session.delete(ministry)
    db.session.commit()

    flash(f'"{name}" deleted.', "success")
    return redirect(url_for("ministries.ministry_list"))