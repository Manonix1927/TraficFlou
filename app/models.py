from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    credits = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    projects = relationship("Project", back_populates="user")
    transactions = relationship("CreditTransaction", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    site_url = Column(String, nullable=False)
    ga_tid = Column(String, nullable=False)           # G-XXXXXXXX
    gtm_id = Column(String, nullable=True)            # GTM container ID

    # Traffic config
    daily_hits = Column(Integer, default=100)         # хитов в день
    device = Column(JSON, default=lambda: {"desktop": 100})  # {desktop: %, mobile: %, tablet: %}
    sources = Column(JSON, default=lambda: {          # % по источникам
        "google_organic": 60,
        "instagram": 20,
        "direct": 10,
        "facebook": 10,
    })
    geo = Column(JSON, default=lambda: {              # % по странам
        "UA": 100,
    })

    # Status
    status = Column(String, default="paused")         # active | paused | finished
    hits_sent = Column(Integer, default=0)
    hits_total = Column(Integer, default=0)           # лимит, 0 = безлимит пока есть кредиты

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="projects")
    hit_logs = relationship("HitLog", back_populates="project")


class HitLog(Base):
    __tablename__ = "hit_logs"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    country = Column(String)
    source = Column(String)
    medium = Column(String)
    status = Column(Integer)                          # HTTP status code
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="hit_logs")


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)          # + пополнение, - списание
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="transactions")
