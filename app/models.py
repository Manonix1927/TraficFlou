from sqlalchemy import Column, Integer, Numeric, String, Float, Boolean, DateTime, ForeignKey, JSON, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# Публічний ID користувача = внутрішній id + це зміщення. Показуємо його
# замість id у платіжних реквізитах, щоб перший реальний користувач мав
# номер 101, а не 1 — так виглядає, що сервісом уже хтось користується.
USER_PUBLIC_ID_OFFSET = 100


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    credits = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("CreditTransaction", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("PaymentOrder", back_populates="user", cascade="all, delete-orphan")

    @property
    def public_id(self) -> int:
        """ID, який бачить клієнт (у призначенні платежу тощо)."""
        return self.id + USER_PUBLIC_ID_OFFSET


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    site_url = Column(String, nullable=False)
    ga_tid = Column(String, nullable=False)           # G-XXXXXXXX
    gtm_id = Column(String, nullable=True)            # GTM container ID

    # Traffic config
    daily_hits = Column(Integer, default=100)         # хитов в день
    device = Column(JSON, default=lambda: {"desktop": 100}, nullable=True)  # {desktop: %, mobile: %, tablet: %}
    sources = Column(JSON, default=lambda: {          # % по источникам
        "google_organic": 60,
        "instagram": 20,
        "direct": 10,
        "facebook": 10,
    })
    geo = Column(JSON, default=lambda: {              # % по странам
        "UA": 100,
    })

    # Цільові сторінки — за замовчуванням вимкнено, хіти йдуть на site_url.
    # Коли увімкнено, для кожного хіта обирається сторінка з pages
    # (вага у %), і саме її бачить GA4 у звіті "Сторінки".
    pages_enabled = Column(Boolean, default=False)
    pages = Column(JSON, default=lambda: {})           # {"/path": %}

    # Status
    status = Column(String, default="paused")         # active | paused | finished
    hits_sent = Column(Integer, default=0)
    hits_total = Column(Integer, default=0)           # лимит, 0 = безлимит пока есть кредиты

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="projects")
    hit_logs = relationship("HitLog", back_populates="project", cascade="all, delete-orphan")

    @property
    def device_map(self) -> dict:
        """device всегда как {device: %} — колонка может вернуть строку."""
        from app.core.devices import normalize_device
        return normalize_device(self.device)

    @property
    def pages_map(self) -> dict:
        """pages завжди як {шлях: %}, навіть якщо в колонці None/сміття."""
        from app.core.pages import normalize_pages
        return normalize_pages(self.pages)


class HitLog(Base):
    __tablename__ = "hit_logs"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    country = Column(String)
    source = Column(String)
    medium = Column(String)
    status = Column(Integer)                          # HTTP status code
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="hit_logs")

    # Stats query filters by project_id + created_at on every page load
    __table_args__ = (
        Index("ix_hitlog_project_created", "project_id", "created_at"),
    )


class PaymentOrder(Base):
    """Замовлення на поповнення балансу — оплата на реквізити ФОП."""

    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_key = Column(String, nullable=False)
    plan_name = Column(String)
    credits = Column(Integer, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)     # у гривнях, може бути з копійками
    currency = Column(String, default="UAH")
    status = Column(String, default="pending")          # pending | paid | cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="orders")

    @property
    def purpose(self) -> str:
        """
        Призначення платежу — за ним звіряємо оплату. Має лишатись стабільним
        для конкретного користувача (не прив'язане до номера замовлення),
        інакше повторна оплата з тим самим призначенням не підхопиться.
        """
        public_id = self.user.public_id if self.user else self.user_id + USER_PUBLIC_ID_OFFSET
        return f"Оплата маркетингових послуг з залучення трафіку, ID {public_id}"


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)          # + пополнение, - списание
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="transactions")
