from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash
)
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Announcement, SmsLog, Member, Visitor
from communications.sms_utils import send_sms_bulk, get_sms_recipients

communications_bp = Blueprint("communications", __name__, url_prefix="/communications")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _comms_access():
    return current_user.role in ("pastor", "secretary", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSE PAGE  —  SMS + Announcement hub
# ─────────────────────────────────────────────────────────────────────────────

@communications_bp.route("/")
@login_required
def compose():
    if not _comms_access():
        return "Access denied", 403

    cid        = current_user.church_id
    recipients = get_sms_recipients(cid)

    # Coverage warnings — members and visitors with no phone number
    total_members      = Member.query.filter_by(church_id=cid, status="Active").count()
    members_no_phone   = Member.query.filter(
        Member.church_id == cid,
        Member.status    == "Active",
        Member.phone     == None,
    ).count()

    total_visitors     = Visitor.query.filter_by(church_id=cid, converted=False).count()
    visitors_no_phone  = Visitor.query.filter(
        Visitor.church_id == cid,
        Visitor.converted == False,
        Visitor.phone     == None,
    ).count()

    warnings = {
        "members_no_phone":  members_no_phone,
        "visitors_no_phone": visitors_no_phone,
    }

    # Recent SMS log
    recent_sms = SmsLog.query.filter_by(
        church_id=cid
    ).order_by(SmsLog.sent_at.desc()).limit(10).all()

    # Recent announcements
    recent_announcements = Announcement.query.filter_by(
        church_id=cid
    ).order_by(Announcement.created_at.desc()).limit(5).all()

    return render_template("Communications/compose.html",
        recipients           = recipients,
        warnings             = warnings,
        recent_sms           = recent_sms,
        recent_announcements = recent_announcements,
        total_members        = total_members,
        total_visitors       = total_visitors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SEND SMS
# ─────────────────────────────────────────────────────────────────────────────

@communications_bp.route("/send/sms", methods=["POST"])
@login_required
def send_sms():
    if not _comms_access():
        return "Access denied", 403

    cid     = current_user.church_id
    message = request.form.get("message", "").strip()
    group   = request.form.get("group", "")
    # Group options:
    #   all_members
    #   ministry_<ministry_name>
    #   visitors
    #   everyone

    if not message:
        flash("Message cannot be empty.", "warning")
        return redirect(url_for("communications.compose"))

    if len(message) > 160:
        flash("Message exceeds 160 characters. Please shorten it.", "warning")
        return redirect(url_for("communications.compose"))

    all_recipients = get_sms_recipients(cid)
    recipients     = []

    if group == "all_members":
        recipients = all_recipients["all_members"]

    elif group.startswith("ministry_"):
        # e.g. group = "ministry_Choir"
        ministry_name = group[len("ministry_"):]
        recipients    = all_recipients["by_ministry"].get(ministry_name, [])

    elif group == "visitors":
        recipients = all_recipients["visitors"]

    elif group == "everyone":
        # All members + all visitors, deduplicated by phone
        seen     = set()
        combined = all_recipients["all_members"] + all_recipients["visitors"]
        for r in combined:
            if r["phone"] not in seen:
                seen.add(r["phone"])
                recipients.append(r)

    else:
        flash("Invalid recipient group selected.", "warning")
        return redirect(url_for("communications.compose"))

    if not recipients:
        flash(
            "No recipients found for the selected group. "
            "Check that phone numbers are on file.",
            "warning"
        )
        return redirect(url_for("communications.compose"))

    result = send_sms_bulk(
        recipients = recipients,
        message    = message,
        church_id  = cid,
        sent_by    = current_user.id,
    )

    flash(
        f"SMS queued — {result['sent']} sent, "
        f"{result['skipped']} skipped (no number), "
        f"{result['failed']} failed.",
        "success" if result["failed"] == 0 else "warning",
    )
    return redirect(url_for("communications.compose"))


# ─────────────────────────────────────────────────────────────────────────────
# CREATE ANNOUNCEMENT
# ─────────────────────────────────────────────────────────────────────────────

@communications_bp.route("/announcement", methods=["POST"])
@login_required
def create_announcement():
    if not _comms_access():
        return "Access denied", 403

    cid   = current_user.church_id
    title = request.form.get("title", "").strip()
    body  = request.form.get("body", "").strip()

    if not title or not body:
        flash("Title and body are required.", "warning")
        return redirect(url_for("communications.compose"))

    # Optional schedule
    scheduled_str = request.form.get("scheduled_for", "").strip()
    scheduled_for = None
    if scheduled_str:
        try:
            scheduled_for = datetime.strptime(scheduled_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    announcement = Announcement(
        church_id     = cid,
        created_by    = current_user.id,
        title         = title,
        body          = body,
        scheduled_for = scheduled_for,
        is_sent       = False,
    )
    db.session.add(announcement)
    db.session.commit()

    flash(f'Announcement "{title}" created.', "success")
    return redirect(url_for("communications.announcements"))


# ─────────────────────────────────────────────────────────────────────────────
# ALL ANNOUNCEMENTS
# ─────────────────────────────────────────────────────────────────────────────

@communications_bp.route("/announcements")
@login_required
def announcements():
    if not _comms_access():
        return "Access denied", 403

    cid  = current_user.church_id
    page = request.args.get("page", 1, type=int)

    pagination = Announcement.query.filter_by(
        church_id=cid
    ).order_by(
        Announcement.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return render_template("Communications/announcements.html",
        pagination    = pagination,
        announcements = pagination.items,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE ANNOUNCEMENT
# ─────────────────────────────────────────────────────────────────────────────

@communications_bp.route("/announcements/<int:announcement_id>/delete", methods=["POST"])
@login_required
def delete_announcement(announcement_id):
    if not _comms_access():
        return "Access denied", 403

    announcement = Announcement.query.filter_by(
        id=announcement_id, church_id=current_user.church_id
    ).first_or_404()

    title = announcement.title
    db.session.delete(announcement)
    db.session.commit()

    flash(f'"{title}" deleted.', "success")
    return redirect(url_for("communications.announcements"))


# ─────────────────────────────────────────────────────────────────────────────
# SMS LOG  —  full history
# ─────────────────────────────────────────────────────────────────────────────

@communications_bp.route("/log")
@login_required
def sms_log():
    if not _comms_access():
        return "Access denied", 403

    cid  = current_user.church_id
    page = request.args.get("page", 1, type=int)

    # Filters
    status = request.args.get("status", "")

    query = SmsLog.query.filter_by(church_id=cid)
    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(
        SmsLog.sent_at.desc()
    ).paginate(page=page, per_page=30, error_out=False)

    return render_template("Communications/sms_log.html",
        pagination = pagination,
        logs       = pagination.items,
        f_status   = status,
    )