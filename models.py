from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

now = datetime.utcnow


# ─────────────────────────────────────────────────────────────────────────────
# CHURCH MODEL  (Root tenant object)
# ─────────────────────────────────────────────────────────────────────────────

class Church(db.Model):
    __tablename__ = "church"

    id                = db.Column(db.Integer, primary_key=True)
    church_code       = db.Column(db.String(60),  unique=True, nullable=False, index=True)
    name              = db.Column(db.String(120),  nullable=False)
    email             = db.Column(db.String(120),  nullable=True)
    phone             = db.Column(db.String(30),   nullable=True)
    address           = db.Column(db.String(200),  nullable=True)
    logo_filename     = db.Column(db.String(255),  nullable=True)
    pastor_name       = db.Column(db.String(120),  nullable=True)
    is_active         = db.Column(db.Boolean,      default=True,    nullable=False)
    subscription_plan = db.Column(db.String(20),   default="trial", nullable=False)
    trial_ends_at     = db.Column(db.DateTime,     nullable=True)
    base_currency     = db.Column(db.String(10),   default="USD",   nullable=False)
    local_currency    = db.Column(db.String(10),   default="LRD",   nullable=False)
    exchange_rate     = db.Column(db.Float,        default=1.0,     nullable=False)
    created_at        = db.Column(db.DateTime,     default=now)
    updated_at        = db.Column(db.DateTime,     default=now,     onupdate=now)

    # ── Cascade relationships ─────────────────────────────────────────────────
    users             = db.relationship("ChurchUser",      back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    members           = db.relationship("Member",          back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    visitors          = db.relationship("Visitor",         back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    ministries        = db.relationship("Ministry",        back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    services          = db.relationship("ChurchService",   back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    income_categories = db.relationship("IncomeCategory",  back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    incomes           = db.relationship("ChurchIncome",    back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    expense_categories= db.relationship("ExpenseCategory", back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    expenses          = db.relationship("ChurchExpense",   back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    announcements     = db.relationship("Announcement",    back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    sms_logs          = db.relationship("SmsLog",          back_populates="church", cascade="all, delete-orphan", passive_deletes=True)
    documents         = db.relationship("ChurchDocument",  back_populates="church", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<Church {self.church_code}>"


# ─────────────────────────────────────────────────────────────────────────────
# CHURCH USER MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ChurchUser(UserMixin, db.Model):
    __tablename__ = "church_user"

    id                      = db.Column(db.Integer, primary_key=True)
    church_id               = db.Column(db.Integer, db.ForeignKey("church.id", ondelete="CASCADE"), nullable=True, index=True)
    username                = db.Column(db.String(100), nullable=False)
    password                = db.Column(db.String(255), nullable=False)
    email                   = db.Column(db.String(120), nullable=True)
    phone                   = db.Column(db.String(30),  nullable=True)
    role                    = db.Column(db.String(20),  nullable=False)
    # Roles: super_admin / pastor / treasurer / secretary / usher
    must_change_credentials = db.Column(db.Boolean, default=True)
    created_at              = db.Column(db.DateTime, default=now)

    church = db.relationship("Church", back_populates="users")

    __table_args__ = (
        db.UniqueConstraint("church_id", "username", name="uq_church_username"),
    )

    @property
    def is_super_admin(self):
        return self.role == "super_admin"

    def __repr__(self):
        return f"<ChurchUser {self.username} church={self.church_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# MEMBER MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Member(db.Model):
    __tablename__ = "member"

    id                = db.Column(db.Integer, primary_key=True)
    church_id         = db.Column(db.Integer, db.ForeignKey("church.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name         = db.Column(db.String(120), nullable=False)
    phone             = db.Column(db.String(30),  nullable=True)
    email             = db.Column(db.String(120), nullable=True)
    gender            = db.Column(db.String(10),  nullable=True)   # Male / Female
    date_of_birth     = db.Column(db.Date,        nullable=True)
    address           = db.Column(db.String(200), nullable=True)
    marital_status    = db.Column(db.String(20),  nullable=True)   # Single / Married / Widowed / Divorced
    occupation        = db.Column(db.String(100), nullable=True)
    emergency_contact = db.Column(db.String(100), nullable=True)
    join_date         = db.Column(db.Date,        default=date.today)
    status            = db.Column(db.String(20),  default="Active", nullable=False)
    # Status: Active / Inactive / Transfer
    created_at        = db.Column(db.DateTime, default=now)
    updated_at        = db.Column(db.DateTime, default=now, onupdate=now)

    church             = db.relationship("Church", back_populates="members")
    ministry_members   = db.relationship("MinistryMember",  back_populates="member",  cascade="all, delete-orphan", passive_deletes=True)
    attendance_records = db.relationship("AttendanceRecord", back_populates="member",  cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<Member {self.full_name}>"


# ─────────────────────────────────────────────────────────────────────────────
# VISITOR MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Visitor(db.Model):
    __tablename__ = "visitor"

    id           = db.Column(db.Integer, primary_key=True)
    church_id    = db.Column(db.Integer, db.ForeignKey("church.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name    = db.Column(db.String(120), nullable=False)
    phone        = db.Column(db.String(30),  nullable=True)
    visit_date   = db.Column(db.Date,        default=date.today)
    invited_by   = db.Column(db.String(120), nullable=True)
    converted    = db.Column(db.Boolean,     default=False)
    converted_at = db.Column(db.DateTime,    nullable=True)
    created_at   = db.Column(db.DateTime,    default=now)

    church      = db.relationship("Church",          back_populates="visitors")
    follow_ups  = db.relationship("VisitorFollowUp", back_populates="visitor", cascade="all, delete-orphan", passive_deletes=True)
    attendance_records = db.relationship("AttendanceRecord", back_populates="visitor", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<Visitor {self.full_name}>"


# ─────────────────────────────────────────────────────────────────────────────
# VISITOR FOLLOW-UP MODEL
# ─────────────────────────────────────────────────────────────────────────────

class VisitorFollowUp(db.Model):
    __tablename__ = "visitor_follow_up"

    id             = db.Column(db.Integer, primary_key=True)
    visitor_id     = db.Column(db.Integer, db.ForeignKey("visitor.id",      ondelete="CASCADE"), nullable=False, index=True)
    church_id      = db.Column(db.Integer, db.ForeignKey("church.id",       ondelete="CASCADE"), nullable=False, index=True)
    done_by        = db.Column(db.Integer, db.ForeignKey("church_user.id",  ondelete="SET NULL"), nullable=True)
    follow_up_date = db.Column(db.Date,    default=date.today)
    method         = db.Column(db.String(30),  nullable=False)
    # Method: Called / Visited / Prayed With
    notes          = db.Column(db.Text,        nullable=True)
    created_at     = db.Column(db.DateTime,    default=now)

    visitor  = db.relationship("Visitor",     back_populates="follow_ups")
    staff    = db.relationship("ChurchUser",  foreign_keys=[done_by])

    def __repr__(self):
        return f"<VisitorFollowUp visitor={self.visitor_id} method={self.method}>"


# ─────────────────────────────────────────────────────────────────────────────
# MINISTRY MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Ministry(db.Model):
    __tablename__ = "ministry"

    id           = db.Column(db.Integer, primary_key=True)
    church_id    = db.Column(db.Integer, db.ForeignKey("church.id", ondelete="CASCADE"), nullable=False, index=True)
    name         = db.Column(db.String(100), nullable=False)
    description  = db.Column(db.Text,        nullable=True)
    meeting_day  = db.Column(db.String(20),  nullable=True)   # Monday / Sunday etc.
    meeting_time = db.Column(db.String(20),  nullable=True)   # e.g. "10:00 AM"
    created_at   = db.Column(db.DateTime,    default=now)

    church          = db.relationship("Church",         back_populates="ministries")
    ministry_members= db.relationship("MinistryMember", back_populates="ministry", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint("church_id", "name", name="uq_church_ministry_name"),
    )

    def __repr__(self):
        return f"<Ministry {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# MINISTRY MEMBER MODEL  (Many-to-many: Member ↔ Ministry)
# ─────────────────────────────────────────────────────────────────────────────

class MinistryMember(db.Model):
    __tablename__ = "ministry_member"

    id          = db.Column(db.Integer, primary_key=True)
    ministry_id = db.Column(db.Integer, db.ForeignKey("ministry.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id   = db.Column(db.Integer, db.ForeignKey("member.id",   ondelete="CASCADE"), nullable=False, index=True)
    church_id   = db.Column(db.Integer, db.ForeignKey("church.id",   ondelete="CASCADE"), nullable=False, index=True)
    role        = db.Column(db.String(20), default="Member", nullable=False)
    # Role: Leader / Member
    joined_at   = db.Column(db.DateTime, default=now)

    ministry = db.relationship("Ministry", back_populates="ministry_members")
    member   = db.relationship("Member",   back_populates="ministry_members")

    __table_args__ = (
        db.UniqueConstraint("ministry_id", "member_id", name="uq_ministry_member"),
    )

    def __repr__(self):
        return f"<MinistryMember member={self.member_id} ministry={self.ministry_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# CHURCH SERVICE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ChurchService(db.Model):
    __tablename__ = "church_service"

    id           = db.Column(db.Integer, primary_key=True)
    church_id    = db.Column(db.Integer, db.ForeignKey("church.id",      ondelete="CASCADE"), nullable=False, index=True)
    created_by   = db.Column(db.Integer, db.ForeignKey("church_user.id", ondelete="SET NULL"), nullable=True)
    name         = db.Column(db.String(150), nullable=False)   # e.g. "Sunday Service — June 15"
    service_type = db.Column(db.String(30),  nullable=False)
    # Type: Sunday / Midweek / Cell Group / Special Event
    service_date = db.Column(db.Date,        default=date.today)
    created_at   = db.Column(db.DateTime,    default=now)

    church             = db.relationship("Church",      back_populates="services")
    creator            = db.relationship("ChurchUser",  foreign_keys=[created_by])
    attendance_records = db.relationship("AttendanceRecord", back_populates="service", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<ChurchService {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE RECORD MODEL
# ─────────────────────────────────────────────────────────────────────────────

class AttendanceRecord(db.Model):
    __tablename__ = "attendance_record"

    id         = db.Column(db.Integer, primary_key=True)
    church_id  = db.Column(db.Integer, db.ForeignKey("church.id",      ondelete="CASCADE"), nullable=False, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey("church_service.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id  = db.Column(db.Integer, db.ForeignKey("member.id",      ondelete="CASCADE"), nullable=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitor.id",     ondelete="CASCADE"), nullable=True)
    marked_by  = db.Column(db.Integer, db.ForeignKey("church_user.id", ondelete="SET NULL"), nullable=True)
    status     = db.Column(db.String(20), default="Present", nullable=False)
    # Status: Present / Absent
    # Either member_id or visitor_id is populated — never both
    created_at = db.Column(db.DateTime, default=now)

    service = db.relationship("ChurchService",  back_populates="attendance_records")
    member  = db.relationship("Member",         back_populates="attendance_records")
    visitor = db.relationship("Visitor",        back_populates="attendance_records")
    usher   = db.relationship("ChurchUser",     foreign_keys=[marked_by])

    __table_args__ = (
        # A member can only be marked once per service
        db.UniqueConstraint("service_id", "member_id",  name="uq_service_member_attendance"),
        # A visitor can only be marked once per service
        db.UniqueConstraint("service_id", "visitor_id", name="uq_service_visitor_attendance"),
    )

    def __repr__(self):
        return f"<AttendanceRecord service={self.service_id} member={self.member_id} visitor={self.visitor_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# INCOME CATEGORY MODEL
# ─────────────────────────────────────────────────────────────────────────────

class IncomeCategory(db.Model):
    __tablename__ = "income_category"

    id        = db.Column(db.Integer, primary_key=True)
    church_id = db.Column(db.Integer, db.ForeignKey("church.id", ondelete="CASCADE"), nullable=False, index=True)
    name      = db.Column(db.String(100), nullable=False)
    # Examples: Tithes / Offerings / Donations / Building Fund / Project Fund
    is_active = db.Column(db.Boolean, default=True)

    church  = db.relationship("Church",        back_populates="income_categories")
    incomes = db.relationship("ChurchIncome",  back_populates="category", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint("church_id", "name", name="uq_church_income_category"),
    )

    def __repr__(self):
        return f"<IncomeCategory {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# CHURCH INCOME MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ChurchIncome(db.Model):
    __tablename__ = "church_income"

    id                 = db.Column(db.Integer, primary_key=True)
    church_id          = db.Column(db.Integer, db.ForeignKey("church.id",          ondelete="CASCADE"), nullable=False, index=True)
    category_id        = db.Column(db.Integer, db.ForeignKey("income_category.id", ondelete="CASCADE"), nullable=False)
    recorded_by        = db.Column(db.Integer, db.ForeignKey("church_user.id",     ondelete="SET NULL"), nullable=True)
    amount             = db.Column(db.Float,   nullable=False)
    currency           = db.Column(db.String(10), default="USD", nullable=False)
    # currency: USD or local (e.g. LRD, XAF)
    amount_usd         = db.Column(db.Float,   nullable=True)
    exchange_rate_used = db.Column(db.Float,   nullable=True)
    date               = db.Column(db.Date,    default=date.today)
    notes              = db.Column(db.Text,    nullable=True)
    created_at         = db.Column(db.DateTime, default=now)

    church    = db.relationship("Church",          back_populates="incomes")
    category  = db.relationship("IncomeCategory",  back_populates="incomes")
    recorder  = db.relationship("ChurchUser",      foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<ChurchIncome {self.amount} {self.currency} date={self.date}>"


# ─────────────────────────────────────────────────────────────────────────────
# EXPENSE CATEGORY MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ExpenseCategory(db.Model):
    __tablename__ = "expense_category"

    id        = db.Column(db.Integer, primary_key=True)
    church_id = db.Column(db.Integer, db.ForeignKey("church.id", ondelete="CASCADE"), nullable=False, index=True)
    name      = db.Column(db.String(100), nullable=False)
    # Examples: Utilities / Fuel / Maintenance / Salaries / Miscellaneous
    is_active = db.Column(db.Boolean, default=True)

    church   = db.relationship("Church",         back_populates="expense_categories")
    expenses = db.relationship("ChurchExpense",  back_populates="category", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        db.UniqueConstraint("church_id", "name", name="uq_church_expense_category"),
    )

    def __repr__(self):
        return f"<ExpenseCategory {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# CHURCH EXPENSE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ChurchExpense(db.Model):
    __tablename__ = "church_expense"

    id          = db.Column(db.Integer, primary_key=True)
    church_id   = db.Column(db.Integer, db.ForeignKey("church.id",           ondelete="CASCADE"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_category.id", ondelete="CASCADE"), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey("church_user.id",      ondelete="SET NULL"), nullable=True)
    amount      = db.Column(db.Float,       nullable=False)
    description = db.Column(db.String(200), nullable=False)
    paid_by     = db.Column(db.String(100), nullable=True)
    date        = db.Column(db.Date,        default=date.today)
    created_at  = db.Column(db.DateTime,    default=now)

    church    = db.relationship("Church",          back_populates="expenses")
    category  = db.relationship("ExpenseCategory", back_populates="expenses")
    recorder  = db.relationship("ChurchUser",      foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<ChurchExpense {self.description} {self.amount}>"


# ─────────────────────────────────────────────────────────────────────────────
# ANNOUNCEMENT MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Announcement(db.Model):
    __tablename__ = "announcement"

    id            = db.Column(db.Integer, primary_key=True)
    church_id     = db.Column(db.Integer, db.ForeignKey("church.id",      ondelete="CASCADE"), nullable=False, index=True)
    created_by    = db.Column(db.Integer, db.ForeignKey("church_user.id", ondelete="SET NULL"), nullable=True)
    title         = db.Column(db.String(150), nullable=False)
    body          = db.Column(db.Text,        nullable=False)
    scheduled_for = db.Column(db.DateTime,    nullable=True)
    is_sent       = db.Column(db.Boolean,     default=False)
    created_at    = db.Column(db.DateTime,    default=now)

    church  = db.relationship("Church",     back_populates="announcements")
    author  = db.relationship("ChurchUser", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Announcement {self.title}>"


# ─────────────────────────────────────────────────────────────────────────────
# SMS LOG MODEL
# ─────────────────────────────────────────────────────────────────────────────

class SmsLog(db.Model):
    __tablename__ = "sms_log"

    id             = db.Column(db.Integer, primary_key=True)
    church_id      = db.Column(db.Integer, db.ForeignKey("church.id",      ondelete="CASCADE"), nullable=False, index=True)
    sent_by        = db.Column(db.Integer, db.ForeignKey("church_user.id", ondelete="SET NULL"), nullable=True)
    recipient_name = db.Column(db.String(120), nullable=False)
    phone          = db.Column(db.String(30),  nullable=False)
    message        = db.Column(db.Text,        nullable=False)
    status         = db.Column(db.String(20),  default="pending", nullable=False)
    # Status: pending / sent / failed
    sent_at        = db.Column(db.DateTime,    default=now)

    church = db.relationship("Church",     back_populates="sms_logs")
    sender = db.relationship("ChurchUser", foreign_keys=[sent_by])

    def __repr__(self):
        return f"<SmsLog to={self.phone} status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# CHURCH DOCUMENT MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ChurchDocument(db.Model):
    __tablename__ = "church_document"

    id          = db.Column(db.Integer, primary_key=True)
    church_id   = db.Column(db.Integer, db.ForeignKey("church.id",      ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("church_user.id", ondelete="SET NULL"), nullable=True)
    title       = db.Column(db.String(150), nullable=False)
    category    = db.Column(db.String(50),  nullable=False)
    # Category: Minutes / Constitution / Financial / Event / Report
    filename    = db.Column(db.String(255), nullable=False)
    created_at  = db.Column(db.DateTime,   default=now)

    church   = db.relationship("Church",     back_populates="documents")
    uploader = db.relationship("ChurchUser", foreign_keys=[uploaded_by])

    def __repr__(self):
        return f"<ChurchDocument {self.title}>"