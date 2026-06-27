from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify
)
from flask_login import login_required, current_user
from datetime import date, datetime
from models import db, Visitor, VisitorFollowUp, Member

visitors_bp = Blueprint("visitors", __name__, url_prefix="/visitors")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _visitors_access():
    return current_user.role in ("pastor", "secretary", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# VISITOR LIST
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/")
@login_required
def visitor_list():
    if not _visitors_access():
        return "Access denied", 403

    cid      = current_user.church_id
    page     = request.args.get("page", 1, type=int)
    per_page = 25

    # Filters
    search    = request.args.get("q", "").strip()
    converted = request.args.get("converted", "")

    query = Visitor.query.filter_by(church_id=cid)

    if search:
        query = query.filter(
            Visitor.full_name.ilike(f"%{search}%") |
            Visitor.phone.ilike(f"%{search}%")
        )

    if converted == "yes":
        query = query.filter_by(converted=True)
    elif converted == "no":
        query = query.filter_by(converted=False)

    query      = query.order_by(Visitor.visit_date.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    visitors   = pagination.items

    return render_template("Visitors/visitor_list.html",
        visitors   = visitors,
        pagination = pagination,
        search     = search,
        converted  = converted,
    )


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER VISITOR
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_visitor():
    if not _visitors_access():
        return "Access denied", 403

    if request.method == "POST":
        cid = current_user.church_id

        visit_str  = request.form.get("visit_date", "").strip()
        visit_date = date.today()
        if visit_str:
            try:
                visit_date = datetime.strptime(visit_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        visitor = Visitor(
            church_id  = cid,
            full_name  = request.form.get("full_name", "").strip(),
            phone      = request.form.get("phone", "").strip()      or None,
            visit_date = visit_date,
            invited_by = request.form.get("invited_by", "").strip() or None,
            converted  = False,
        )
        db.session.add(visitor)
        db.session.commit()

        flash(f"{visitor.full_name} registered as a visitor.", "success")
        return redirect(url_for("visitors.visitor_list"))

    return render_template("Visitors/add_visitor.html")


# ─────────────────────────────────────────────────────────────────────────────
# VISITOR PROFILE  —  details + follow-up history
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/<int:visitor_id>")
@login_required
def visitor_profile(visitor_id):
    if not _visitors_access():
        return "Access denied", 403

    visitor = Visitor.query.filter_by(
        id=visitor_id, church_id=current_user.church_id
    ).first_or_404()

    follow_ups = VisitorFollowUp.query.filter_by(
        visitor_id=visitor_id
    ).order_by(VisitorFollowUp.follow_up_date.desc()).all()

    return render_template("Visitors/visitor_profile.html",
        visitor    = visitor,
        follow_ups = follow_ups,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADD FOLLOW-UP
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/<int:visitor_id>/followup", methods=["POST"])
@login_required
def add_followup(visitor_id):
    if not _visitors_access():
        return "Access denied", 403

    visitor = Visitor.query.filter_by(
        id=visitor_id, church_id=current_user.church_id
    ).first_or_404()

    date_str      = request.form.get("follow_up_date", "").strip()
    follow_up_date = date.today()
    if date_str:
        try:
            follow_up_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    follow_up = VisitorFollowUp(
        visitor_id     = visitor.id,
        church_id      = current_user.church_id,
        done_by        = current_user.id,
        follow_up_date = follow_up_date,
        method         = request.form.get("method", "Called"),
        # Method: Called / Visited / Prayed With
        notes          = request.form.get("notes", "").strip() or None,
    )
    db.session.add(follow_up)
    db.session.commit()

    flash("Follow-up recorded.", "success")
    return redirect(url_for("visitors.visitor_profile", visitor_id=visitor_id))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE FOLLOW-UP
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/followup/<int:followup_id>/delete", methods=["POST"])
@login_required
def delete_followup(followup_id):
    if not _visitors_access():
        return "Access denied", 403

    follow_up = VisitorFollowUp.query.filter_by(
        id=followup_id, church_id=current_user.church_id
    ).first_or_404()

    visitor_id = follow_up.visitor_id
    db.session.delete(follow_up)
    db.session.commit()

    flash("Follow-up removed.", "success")
    return redirect(url_for("visitors.visitor_profile", visitor_id=visitor_id))


# ─────────────────────────────────────────────────────────────────────────────
# CONVERT VISITOR TO MEMBER
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/<int:visitor_id>/convert", methods=["POST"])
@login_required
def convert_to_member(visitor_id):
    if current_user.role not in ("pastor", "secretary", "super_admin"):
        return "Access denied", 403

    cid     = current_user.church_id
    visitor = Visitor.query.filter_by(
        id=visitor_id, church_id=cid
    ).first_or_404()

    if visitor.converted:
        flash(f"{visitor.full_name} has already been converted to a member.", "warning")
        return redirect(url_for("visitors.visitor_profile", visitor_id=visitor_id))

    # Parse join date from form — default to today
    join_str  = request.form.get("join_date", "").strip()
    join_date = date.today()
    if join_str:
        try:
            join_date = datetime.strptime(join_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Create the Member record from visitor data
    member = Member(
        church_id  = cid,
        full_name  = visitor.full_name,
        phone      = visitor.phone,
        join_date  = join_date,
        status     = "Active",
    )
    db.session.add(member)

    # Mark visitor as converted
    visitor.converted    = True
    visitor.converted_at = datetime.utcnow()

    db.session.commit()

    flash(
        f"{visitor.full_name} has been converted to a member. "
        f"You can complete their profile in the Members section.",
        "success"
    )
    return redirect(url_for("members.member_profile", member_id=member.id))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE VISITOR
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/<int:visitor_id>/delete", methods=["POST"])
@login_required
def delete_visitor(visitor_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    visitor = Visitor.query.filter_by(
        id=visitor_id, church_id=current_user.church_id
    ).first_or_404()

    name = visitor.full_name
    db.session.delete(visitor)
    db.session.commit()

    flash(f"{name} removed from visitors.", "success")
    return redirect(url_for("visitors.visitor_list"))


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION REPORT
# ─────────────────────────────────────────────────────────────────────────────

@visitors_bp.route("/report")
@login_required
def conversion_report():
    if not _visitors_access():
        return "Access denied", 403

    cid   = current_user.church_id
    today = date.today()

    total_visitors  = Visitor.query.filter_by(church_id=cid).count()
    total_converted = Visitor.query.filter_by(church_id=cid, converted=True).count()
    total_pending   = Visitor.query.filter_by(church_id=cid, converted=False).count()

    conversion_rate = round(
        (total_converted / total_visitors * 100) if total_visitors > 0 else 0, 1
    )

    # Visitors with no follow-up at all
    visited_ids = db.session.query(
        VisitorFollowUp.visitor_id
    ).filter_by(church_id=cid).distinct().all()

    visited_ids = {row[0] for row in visited_ids}

    no_followup = Visitor.query.filter(
        Visitor.church_id == cid,
        Visitor.converted == False,
        Visitor.id.notin_(visited_ids)
    ).order_by(Visitor.visit_date.desc()).all()

    # Recently converted
    recently_converted = Visitor.query.filter(
        Visitor.church_id == cid,
        Visitor.converted == True,
    ).order_by(Visitor.converted_at.desc()).limit(10).all()

    return render_template("Visitors/conversion_report.html",
        total_visitors     = total_visitors,
        total_converted    = total_converted,
        total_pending      = total_pending,
        conversion_rate    = conversion_rate,
        no_followup        = no_followup,
        recently_converted = recently_converted,
        today              = today,
    )