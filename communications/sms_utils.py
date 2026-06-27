# ─────────────────────────────────────────────────────────────────────────────
# SMS UTILITY — SHELL VERSION
# All SMS sending in the Church ERP goes through send_sms().
# When Orange API credentials are obtained, only the marked block changes.
# ─────────────────────────────────────────────────────────────────────────────

from models import db, SmsLog, Member, Visitor, ChurchUser
from datetime import datetime


def send_sms(
    phone:          str,
    message:        str,
    recipient_name: str,
    church_id:      int,
    sent_by:        int,   # ChurchUser.id
) -> bool:
    """
    Send an SMS to a single recipient.

    Parameters:
        phone          — recipient phone number e.g. "+231770123456"
        message        — message body (keep under 160 chars for single SMS)
        recipient_name — display name for the log e.g. "James Kollie"
        church_id      — church scoping for the log
        sent_by        — ChurchUser.id of the staff member sending

    Returns:
        True if sent (or logged as pending in shell mode), False on failure.

    ── SHELL MODE ────────────────────────────────────────────────────────────
    Logs every message as 'pending' without making any API call.
    To activate real sending, replace the block marked REPLACE THIS with
    your Orange API call, then set status to 'sent' or 'failed' based
    on the API response.
    ── ───────────────────────────────────────────────────────────────────────
    """

    # Sanitize phone number
    phone = phone.replace(" ", "").replace("-", "").strip() if phone else ""

    if not phone:
        _log(church_id, sent_by, recipient_name, phone, message, "failed")
        return False

    # ── REPLACE THIS when Orange API credentials are ready ────────────────
    #
    # import requests
    #
    # API_KEY    = os.environ.get("ORANGE_API_KEY")
    # SENDER_ID  = os.environ.get("ORANGE_SENDER_ID")
    # API_URL    = "https://api.orange.com/smsmessaging/v1/outbound/{sender}/requests"
    #
    # try:
    #     response = requests.post(
    #         API_URL.format(sender=SENDER_ID),
    #         headers={
    #             "Authorization": f"Bearer {API_KEY}",
    #             "Content-Type":  "application/json",
    #         },
    #         json={
    #             "outboundSMSMessageRequest": {
    #                 "address":            f"tel:{phone}",
    #                 "senderAddress":      f"tel:{SENDER_ID}",
    #                 "outboundSMSTextMessage": {"message": message},
    #             }
    #         },
    #         timeout=10,
    #     )
    #     status = "sent" if response.status_code in (200, 201) else "failed"
    # except Exception:
    #     status = "failed"
    #
    # ── END REPLACE ───────────────────────────────────────────────────────

    # Shell mode — log as pending, no real API call made
    status = "pending"

    _log(church_id, sent_by, recipient_name, phone, message, status)
    return True


def send_sms_bulk(
    recipients: list,
    message:    str,
    church_id:  int,
    sent_by:    int,
) -> dict:
    """
    Send the same message to multiple recipients.

    Parameters:
        recipients — list of dicts: [{"phone": "...", "name": "..."}, ...]
        message    — message body
        church_id  — church scoping
        sent_by    — ChurchUser.id of sender

    Returns:
        dict with keys: sent (int), failed (int), skipped (int)
    """
    sent    = 0
    failed  = 0
    skipped = 0

    for r in recipients:
        phone = r.get("phone", "").strip()
        name  = r.get("name", "Unknown")

        if not phone:
            skipped += 1
            continue

        success = send_sms(
            phone          = phone,
            message        = message,
            recipient_name = name,
            church_id      = church_id,
            sent_by        = sent_by,
        )

        if success:
            sent += 1
        else:
            failed += 1

    db.session.commit()
    return {"sent": sent, "failed": failed, "skipped": skipped}


def get_sms_recipients(church_id: int) -> dict:
    """
    Builds the full recipient list for a church, grouped by audience type.
    Used by the communications compose page to populate targeting options.

    Returns:
    {
        "all_members":   [{"name": ..., "phone": ...}, ...],
        "by_ministry":   {ministry_name: [{"name": ..., "phone": ...}, ...]},
        "visitors":      [{"name": ..., "phone": ...}, ...],
    }
    """
    from models import Ministry, MinistryMember

    # ── All active members with a phone number ────────────────────────────────
    members = Member.query.filter(
        Member.church_id == church_id,
        Member.status    == "Active",
        Member.phone     != None,
    ).order_by(Member.full_name).all()

    all_members = [
        {"name": m.full_name, "phone": m.phone}
        for m in members
    ]

    # ── Members grouped by ministry ───────────────────────────────────────────
    ministries = Ministry.query.filter_by(church_id=church_id).order_by(Ministry.name).all()
    by_ministry = {}

    for ministry in ministries:
        memberships = MinistryMember.query.filter_by(
            ministry_id=ministry.id, church_id=church_id
        ).all()
        group = []
        for mm in memberships:
            if mm.member and mm.member.phone:
                group.append({
                    "name":  mm.member.full_name,
                    "phone": mm.member.phone,
                })
        if group:
            by_ministry[ministry.name] = group

    # ── Unconverted visitors with a phone number ──────────────────────────────
    raw_visitors = Visitor.query.filter(
        Visitor.church_id == church_id,
        Visitor.converted == False,
        Visitor.phone     != None,
    ).order_by(Visitor.full_name).all()

    visitors = [
        {"name": v.full_name, "phone": v.phone}
        for v in raw_visitors
    ]

    return {
        "all_members": all_members,
        "by_ministry": by_ministry,
        "visitors":    visitors,
    }


def _log(
    church_id:      int,
    sent_by:        int,
    recipient_name: str,
    phone:          str,
    message:        str,
    status:         str,
):
    """
    Internal helper — writes one row to sms_log.
    Caller is responsible for db.session.commit().
    """
    db.session.add(SmsLog(
        church_id      = church_id,
        sent_by        = sent_by,
        recipient_name = recipient_name,
        phone          = phone,
        message        = message,
        status         = status,
        sent_at        = datetime.utcnow(),
    ))