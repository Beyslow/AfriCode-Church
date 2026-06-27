import csv
import io
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, stream_with_context
)
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, datetime
from models import (
    db, ChurchIncome, ChurchExpense,
    IncomeCategory, ExpenseCategory, Church
)

finance_bp = Blueprint("finance", __name__, url_prefix="/finance")


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS GUARD
# ─────────────────────────────────────────────────────────────────────────────

def _finance_access():
    return current_user.role in ("treasurer", "pastor", "super_admin")


# ─────────────────────────────────────────────────────────────────────────────
# FINANCE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/")
@login_required
def finance_dashboard():
    if not _finance_access():
        return "Access denied", 403

    cid        = current_user.church_id
    today      = date.today()
    this_month = today.replace(day=1)

    church = Church.query.get(cid)

    # ── Monthly totals ────────────────────────────────────────────────────────
    total_income_month = db.session.query(
        func.coalesce(func.sum(ChurchIncome.amount_usd), 0)
    ).filter(
        ChurchIncome.church_id == cid,
        ChurchIncome.date      >= this_month,
        ChurchIncome.date      <= today,
    ).scalar()

    total_expenses_month = db.session.query(
        func.coalesce(func.sum(ChurchExpense.amount), 0)
    ).filter(
        ChurchExpense.church_id == cid,
        ChurchExpense.date      >= this_month,
        ChurchExpense.date      <= today,
    ).scalar()

    net_income_month = round(
        float(total_income_month) - float(total_expenses_month), 2
    )

    # ── Income breakdown by category this month ───────────────────────────────
    income_categories = IncomeCategory.query.filter_by(
        church_id=cid, is_active=True
    ).all()

    income_by_category = []
    for cat in income_categories:
        total = db.session.query(
            func.coalesce(func.sum(ChurchIncome.amount_usd), 0)
        ).filter(
            ChurchIncome.church_id   == cid,
            ChurchIncome.category_id == cat.id,
            ChurchIncome.date        >= this_month,
            ChurchIncome.date        <= today,
        ).scalar()
        if float(total) > 0:
            income_by_category.append({
                "name":  cat.name,
                "total": round(float(total), 2),
            })

    # ── Recent transactions ───────────────────────────────────────────────────
    recent_income = ChurchIncome.query.filter_by(
        church_id=cid
    ).order_by(ChurchIncome.date.desc()).limit(5).all()

    recent_expenses = ChurchExpense.query.filter_by(
        church_id=cid
    ).order_by(ChurchExpense.date.desc()).limit(5).all()

    return render_template("Finance/finance_dashboard.html",
        church               = church,
        today                = today,
        total_income_month   = round(float(total_income_month), 2),
        total_expenses_month = round(float(total_expenses_month), 2),
        net_income_month     = net_income_month,
        income_by_category   = income_by_category,
        recent_income        = recent_income,
        recent_expenses      = recent_expenses,
    )


# ─────────────────────────────────────────────────────────────────────────────
# INCOME LIST
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/income")
@login_required
def income_list():
    if not _finance_access():
        return "Access denied", 403

    cid      = current_user.church_id
    page     = request.args.get("page", 1, type=int)
    per_page = 25

    # Filters
    category_id = request.args.get("category_id", "")
    month       = request.args.get("month", "")

    query = ChurchIncome.query.filter_by(church_id=cid)

    if category_id:
        query = query.filter_by(category_id=int(category_id))

    if month:
        try:
            year_val  = int(month[:4])
            month_val = int(month[5:7])
            query = query.filter(
                func.extract("year",  ChurchIncome.date) == year_val,
                func.extract("month", ChurchIncome.date) == month_val,
            )
        except (ValueError, IndexError):
            pass

    query      = query.order_by(ChurchIncome.date.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    incomes    = pagination.items

    total_filtered = db.session.query(
        func.coalesce(func.sum(ChurchIncome.amount_usd), 0)
    ).filter(
        ChurchIncome.church_id == cid,
        *([ChurchIncome.category_id == int(category_id)] if category_id else []),
    ).scalar()

    categories = IncomeCategory.query.filter_by(
        church_id=cid, is_active=True
    ).order_by(IncomeCategory.name).all()

    return render_template("Finance/income_list.html",
        incomes        = incomes,
        pagination     = pagination,
        categories     = categories,
        total_filtered = round(float(total_filtered), 2),
        f_category_id  = category_id,
        f_month        = month,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RECORD INCOME
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/income/add", methods=["POST"])
@login_required
def add_income():
    if not _finance_access():
        return "Access denied", 403

    cid    = current_user.church_id
    church = Church.query.get(cid)

    date_str     = request.form.get("date", "").strip()
    income_date  = date.today()
    if date_str:
        try:
            income_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    category_id = request.form.get("category_id", type=int)
    currency    = request.form.get("currency", "USD").strip().upper()
    raw_amount  = float(request.form.get("amount", 0))

    # Dual currency handling — same pattern as school system
    exchange_rate = church.exchange_rate if church else 1.0
    if currency != "USD":
        amount_usd = round(raw_amount / exchange_rate, 2)
    else:
        amount_usd    = raw_amount
        exchange_rate = 1.0

    income = ChurchIncome(
        church_id          = cid,
        category_id        = category_id,
        recorded_by        = current_user.id,
        amount             = raw_amount,
        currency           = currency,
        amount_usd         = amount_usd,
        exchange_rate_used = exchange_rate,
        date               = income_date,
        notes              = request.form.get("notes", "").strip() or None,
    )
    db.session.add(income)
    db.session.commit()

    flash(
        f"Income recorded: "
        f"{'$' if currency == 'USD' else ''}{raw_amount:,.2f} {currency}"
        + (f" (= ${amount_usd:,.2f} USD)" if currency != "USD" else ""),
        "success"
    )
    return redirect(url_for("finance.income_list"))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE INCOME
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/income/<int:income_id>/delete", methods=["POST"])
@login_required
def delete_income(income_id):
    if not _finance_access():
        return "Access denied", 403

    income = ChurchIncome.query.filter_by(
        id=income_id, church_id=current_user.church_id
    ).first_or_404()

    db.session.delete(income)
    db.session.commit()

    flash("Income record deleted.", "success")
    return redirect(url_for("finance.income_list"))


# ─────────────────────────────────────────────────────────────────────────────
# EXPENSE LIST
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/expenses")
@login_required
def expense_list():
    if not _finance_access():
        return "Access denied", 403

    cid      = current_user.church_id
    page     = request.args.get("page", 1, type=int)
    per_page = 25

    # Filters
    category_id = request.args.get("category_id", "")
    month       = request.args.get("month", "")

    query = ChurchExpense.query.filter_by(church_id=cid)

    if category_id:
        query = query.filter_by(category_id=int(category_id))

    if month:
        try:
            year_val  = int(month[:4])
            month_val = int(month[5:7])
            query = query.filter(
                func.extract("year",  ChurchExpense.date) == year_val,
                func.extract("month", ChurchExpense.date) == month_val,
            )
        except (ValueError, IndexError):
            pass

    query      = query.order_by(ChurchExpense.date.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    expenses   = pagination.items

    total_filtered = db.session.query(
        func.coalesce(func.sum(ChurchExpense.amount), 0)
    ).filter(
        ChurchExpense.church_id == cid,
        *([ChurchExpense.category_id == int(category_id)] if category_id else []),
    ).scalar()

    categories = ExpenseCategory.query.filter_by(
        church_id=cid, is_active=True
    ).order_by(ExpenseCategory.name).all()

    return render_template("Finance/expense_list.html",
        expenses       = expenses,
        pagination     = pagination,
        categories     = categories,
        total_filtered = round(float(total_filtered), 2),
        f_category_id  = category_id,
        f_month        = month,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RECORD EXPENSE
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/expenses/add", methods=["POST"])
@login_required
def add_expense():
    if not _finance_access():
        return "Access denied", 403

    cid = current_user.church_id

    date_str     = request.form.get("date", "").strip()
    expense_date = date.today()
    if date_str:
        try:
            expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    amount = float(request.form.get("amount", 0))

    expense = ChurchExpense(
        church_id   = cid,
        category_id = request.form.get("category_id", type=int),
        recorded_by = current_user.id,
        amount      = amount,
        description = request.form.get("description", "").strip(),
        paid_by     = request.form.get("paid_by", "").strip() or None,
        date        = expense_date,
    )
    db.session.add(expense)
    db.session.commit()

    flash(f"Expense of ${amount:,.2f} recorded.", "success")
    return redirect(url_for("finance.expense_list"))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE EXPENSE
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/expenses/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete_expense(expense_id):
    if not _finance_access():
        return "Access denied", 403

    expense = ChurchExpense.query.filter_by(
        id=expense_id, church_id=current_user.church_id
    ).first_or_404()

    db.session.delete(expense)
    db.session.commit()

    flash("Expense deleted.", "success")
    return redirect(url_for("finance.expense_list"))


# ─────────────────────────────────────────────────────────────────────────────
# MANAGE INCOME CATEGORIES
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/categories/income", methods=["GET", "POST"])
@login_required
def income_categories():
    if not _finance_access():
        return "Access denied", 403

    cid = current_user.church_id

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "warning")
        else:
            existing = IncomeCategory.query.filter_by(
                church_id=cid, name=name
            ).first()
            if existing:
                flash(f'"{name}" already exists.', "warning")
            else:
                db.session.add(IncomeCategory(
                    church_id=cid, name=name, is_active=True
                ))
                db.session.commit()
                flash(f'"{name}" added.', "success")
        return redirect(url_for("finance.income_categories"))

    categories = IncomeCategory.query.filter_by(
        church_id=cid
    ).order_by(IncomeCategory.name).all()

    return render_template("Finance/income_categories.html",
        categories=categories
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE INCOME CATEGORY
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/categories/income/<int:cat_id>/delete", methods=["POST"])
@login_required
def delete_income_category(cat_id):
    if not _finance_access():
        return "Access denied", 403

    cat = IncomeCategory.query.filter_by(
        id=cat_id, church_id=current_user.church_id
    ).first_or_404()

    if cat.incomes:
        flash(
            f'Cannot delete "{cat.name}" — it has existing income records.',
            "warning"
        )
        return redirect(url_for("finance.income_categories"))

    db.session.delete(cat)
    db.session.commit()
    flash(f'"{cat.name}" deleted.', "success")
    return redirect(url_for("finance.income_categories"))


# ─────────────────────────────────────────────────────────────────────────────
# MANAGE EXPENSE CATEGORIES
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/categories/expenses", methods=["GET", "POST"])
@login_required
def expense_categories():
    if not _finance_access():
        return "Access denied", 403

    cid = current_user.church_id

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "warning")
        else:
            existing = ExpenseCategory.query.filter_by(
                church_id=cid, name=name
            ).first()
            if existing:
                flash(f'"{name}" already exists.', "warning")
            else:
                db.session.add(ExpenseCategory(
                    church_id=cid, name=name, is_active=True
                ))
                db.session.commit()
                flash(f'"{name}" added.', "success")
        return redirect(url_for("finance.expense_categories"))

    categories = ExpenseCategory.query.filter_by(
        church_id=cid
    ).order_by(ExpenseCategory.name).all()

    return render_template("Finance/expense_categories.html",
        categories=categories
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE EXPENSE CATEGORY
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/categories/expenses/<int:cat_id>/delete", methods=["POST"])
@login_required
def delete_expense_category(cat_id):
    if not _finance_access():
        return "Access denied", 403

    cat = ExpenseCategory.query.filter_by(
        id=cat_id, church_id=current_user.church_id
    ).first_or_404()

    if cat.expenses:
        flash(
            f'Cannot delete "{cat.name}" — it has existing expense records.',
            "warning"
        )
        return redirect(url_for("finance.expense_categories"))

    db.session.delete(cat)
    db.session.commit()
    flash(f'"{cat.name}" deleted.', "success")
    return redirect(url_for("finance.expense_categories"))


# ─────────────────────────────────────────────────────────────────────────────
# DAILY REPORT
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/reports/daily")
@login_required
def daily_report():
    if not _finance_access():
        return "Access denied", 403

    cid      = current_user.church_id
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        report_date = date.today()

    incomes = ChurchIncome.query.filter_by(
        church_id=cid, date=report_date
    ).order_by(ChurchIncome.category_id).all()

    expenses = ChurchExpense.query.filter_by(
        church_id=cid, date=report_date
    ).order_by(ChurchExpense.category_id).all()

    total_income  = sum(i.amount_usd or 0 for i in incomes)
    total_expense = sum(e.amount for e in expenses)
    net           = round(total_income - total_expense, 2)

    return render_template("Finance/daily_report.html",
        report_date   = report_date,
        incomes       = incomes,
        expenses      = expenses,
        total_income  = round(total_income, 2),
        total_expense = round(total_expense, 2),
        net           = net,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY REPORT
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/reports/monthly")
@login_required
def monthly_report():
    if not _finance_access():
        return "Access denied", 403

    cid       = current_user.church_id
    today     = date.today()
    month_str = request.args.get("month", today.strftime("%Y-%m"))

    try:
        year_val  = int(month_str[:4])
        month_val = int(month_str[5:7])
    except (ValueError, IndexError):
        year_val  = today.year
        month_val = today.month

    month_start = date(year_val, month_val, 1)
    if month_val == 12:
        month_end = date(year_val + 1, 1, 1)
    else:
        month_end = date(year_val, month_val + 1, 1)

    incomes = ChurchIncome.query.filter(
        ChurchIncome.church_id == cid,
        ChurchIncome.date      >= month_start,
        ChurchIncome.date      <  month_end,
    ).order_by(ChurchIncome.date).all()

    expenses = ChurchExpense.query.filter(
        ChurchExpense.church_id == cid,
        ChurchExpense.date      >= month_start,
        ChurchExpense.date      <  month_end,
    ).order_by(ChurchExpense.date).all()

    # Income breakdown by category
    income_categories = IncomeCategory.query.filter_by(
        church_id=cid, is_active=True
    ).all()

    income_by_category = []
    for cat in income_categories:
        cat_total = sum(
            i.amount_usd or 0 for i in incomes if i.category_id == cat.id
        )
        if cat_total > 0:
            income_by_category.append({
                "name":  cat.name,
                "total": round(cat_total, 2),
            })

    # Expense breakdown by category
    expense_categories = ExpenseCategory.query.filter_by(
        church_id=cid, is_active=True
    ).all()

    expense_by_category = []
    for cat in expense_categories:
        cat_total = sum(
            e.amount for e in expenses if e.category_id == cat.id
        )
        if cat_total > 0:
            expense_by_category.append({
                "name":  cat.name,
                "total": round(cat_total, 2),
            })

    total_income  = round(sum(i.amount_usd or 0 for i in incomes), 2)
    total_expense = round(sum(e.amount for e in expenses), 2)
    net           = round(total_income - total_expense, 2)

    return render_template("Finance/monthly_report.html",
        month_start         = month_start,
        month_end           = month_end,
        month_str           = month_str,
        incomes             = incomes,
        expenses            = expenses,
        income_by_category  = income_by_category,
        expense_by_category = expense_by_category,
        total_income        = total_income,
        total_expense       = total_expense,
        net                 = net,
        today               = today,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT CSV
# ─────────────────────────────────────────────────────────────────────────────

@finance_bp.route("/export/csv")
@login_required
def export_csv():
    if not _finance_access():
        return "Access denied", 403

    cid      = current_user.church_id
    export   = request.args.get("type", "income")  # income or expenses

    if export == "income":
        rows = ChurchIncome.query.filter_by(
            church_id=cid
        ).order_by(ChurchIncome.date.desc()).all()

        headers = ["Date", "Category", "Amount", "Currency", "Amount (USD)", "Notes"]

        def generate():
            buf = io.StringIO()
            w   = csv.writer(buf)
            w.writerow(headers)
            for r in rows:
                w.writerow([
                    r.date,
                    r.category.name if r.category else "",
                    r.amount,
                    r.currency,
                    r.amount_usd or r.amount,
                    r.notes or "",
                ])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

        filename = "church_income.csv"

    else:
        rows = ChurchExpense.query.filter_by(
            church_id=cid
        ).order_by(ChurchExpense.date.desc()).all()

        headers = ["Date", "Category", "Description", "Amount", "Paid By"]

        def generate():
            buf = io.StringIO()
            w   = csv.writer(buf)
            w.writerow(headers)
            for r in rows:
                w.writerow([
                    r.date,
                    r.category.name if r.category else "",
                    r.description,
                    r.amount,
                    r.paid_by or "",
                ])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

        filename = "church_expenses.csv"

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )