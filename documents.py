import os
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from models import db, ChurchDocument

documents_bp = Blueprint("documents", __name__, url_prefix="/documents")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

UPLOAD_FOLDER    = os.path.join("static", "uploads", "documents")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _documents_access():
    return current_user.role in ("pastor", "secretary", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT LIST
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/")
@login_required
def document_list():
    if not _documents_access():
        return "Access denied", 403

    cid  = current_user.church_id
    page = request.args.get("page", 1, type=int)

    # Filters
    search   = request.args.get("q", "").strip()
    category = request.args.get("category", "")

    query = ChurchDocument.query.filter_by(church_id=cid)

    if search:
        query = query.filter(
            ChurchDocument.title.ilike(f"%{search}%")
        )
    if category:
        query = query.filter_by(category=category)

    pagination = query.order_by(
        ChurchDocument.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return render_template("Documents/document_list.html",
        documents  = pagination.items,
        pagination = pagination,
        search     = search,
        category   = category,
        categories = _document_categories(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload_document():
    if not _documents_access():
        return "Access denied", 403

    if request.method == "POST":
        cid   = current_user.church_id
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        file  = request.files.get("file")

        if not title:
            flash("Document title is required.", "warning")
            return redirect(url_for("documents.upload_document"))

        if not file or not file.filename:
            flash("Please select a file to upload.", "warning")
            return redirect(url_for("documents.upload_document"))

        if not _allowed_file(file.filename):
            flash(
                "File type not allowed. Accepted: PDF, Word, Excel, JPG, PNG.",
                "warning"
            )
            return redirect(url_for("documents.upload_document"))

        # Build a safe unique filename
        ext       = file.filename.rsplit(".", 1)[1].lower()
        safe_name = secure_filename(title.replace(" ", "_"))
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename  = f"{cid}_{timestamp}_{safe_name}.{ext}"

        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)

        document = ChurchDocument(
            church_id   = cid,
            uploaded_by = current_user.id,
            title       = title,
            category    = category or "General",
            filename    = filename,
        )
        db.session.add(document)
        db.session.commit()

        flash(f'"{title}" uploaded successfully.', "success")
        return redirect(url_for("documents.document_list"))

    return render_template("Documents/upload_document.html",
        categories=_document_categories()
    )


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/<int:document_id>/download")
@login_required
def download_document(document_id):
    if not _documents_access():
        return "Access denied", 403

    document = ChurchDocument.query.filter_by(
        id=document_id, church_id=current_user.church_id
    ).first_or_404()

    return send_from_directory(
        directory = UPLOAD_FOLDER,
        path      = document.filename,
        as_attachment = True,
        download_name = document.title + "." + document.filename.rsplit(".", 1)[-1],
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_document(document_id):
    if current_user.role not in ("pastor", "super_admin"):
        return "Access denied", 403

    document = ChurchDocument.query.filter_by(
        id=document_id, church_id=current_user.church_id
    ).first_or_404()

    # Remove file from disk
    file_path = os.path.join(UPLOAD_FOLDER, document.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    title = document.title
    db.session.delete(document)
    db.session.commit()

    flash(f'"{title}" deleted.', "success")
    return redirect(url_for("documents.document_list"))


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _document_categories():
    return [
        "Minutes",
        "Constitution",
        "Financial",
        "Event",
        "Report",
        "General",
    ]