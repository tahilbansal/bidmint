from sqlalchemy import (
    Column, String, DateTime, Boolean,
    Text, Float, Integer, ForeignKey, Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

Base = declarative_base()


class Supplier(Base):
    __tablename__ = "suppliers"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    whatsapp    = Column(String(15), unique=True, nullable=False)
    name        = Column(String(100), nullable=True)
    district    = Column(String(50), nullable=False)
    categories  = Column(Text, nullable=False)  # "rice,wheat,pulses"
    active      = Column(Boolean, default=True)
    joined_at   = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tender(Base):
    __tablename__ = "tenders"

    id               = Column(String(50), primary_key=True)  # GeM bid number
    source           = Column(String(20))                    # gem|cppp|punjab_state
    title            = Column(Text)
    title_hindi      = Column(Text)
    department       = Column(String(200))
    location         = Column(String(100))
    category         = Column(String(50))
    quantity         = Column(String(100))
    quantity_kg      = Column(Float, nullable=True)
    deadline         = Column(DateTime, nullable=True)
    tender_url       = Column(String(500), nullable=True)   # direct link to tender detail page
    whatsapp_summary = Column(Text)
    ai_confidence    = Column(String(10))                    # HIGH|MEDIUM|LOW
    red_flags        = Column(Text, default="[]")            # JSON array
    scraped_at       = Column(DateTime, default=datetime.utcnow)
    alerted_count    = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_tenders_scraped_at", "scraped_at"),
        Index("ix_tenders_category", "category"),
        Index("ix_tenders_source", "source"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id  = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    tender_id    = Column(String(50), ForeignKey("tenders.id"))
    match_score  = Column(Integer)
    sent_at      = Column(DateTime, default=datetime.utcnow)
    response     = Column(String(10), nullable=True)         # YES|NO|None
    responded_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_alerts_sent_at", "sent_at"),
        Index("ix_alerts_supplier_id", "supplier_id"),
        Index("ix_alerts_tender_id", "tender_id"),
    )


class RunLog(Base):
    """Scheduler execution history — one row per job invocation."""
    __tablename__ = "run_logs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name     = Column(String(50), nullable=False)   # daily_scrape | morning_prices
    started_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at  = Column(DateTime, nullable=True)
    status       = Column(String(20), default="running")  # running | success | error
    scraped      = Column(Integer, default=0)
    new_tenders  = Column(Integer, default=0)
    alerts_sent  = Column(Integer, default=0)
    errors       = Column(Integer, default=0)
    error_detail = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_run_logs_started_at", "started_at"),
        Index("ix_run_logs_job_name", "job_name"),
    )


class PriceLog(Base):
    """Populated in Phase 2 — create table now to avoid migration pain."""
    __tablename__ = "price_logs"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commodity     = Column(String(50))
    mandi         = Column(String(100))
    price_modal   = Column(Float)
    price_min     = Column(Float)
    price_max     = Column(Float)
    recorded_date = Column(DateTime)
