import uuid
from datetime import datetime, date

from sqlalchemy import String, Text, Boolean, Integer, Float, Date, DateTime, ForeignKey, JSON, UniqueConstraint, BigInteger, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger(), unique=True, index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    image_credits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_clients: Mapped[list["ApiClient"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    identities: Mapped[list["UserIdentity"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    perception_records: Mapped[list["UserPerceptionRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserIdentity(Base):
    """Links a User to an external platform identity (telegram, ok, vk, web, whatsapp)."""
    __tablename__ = "user_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_identity_provider_external"),
    )


class ApiClient(Base):
    __tablename__ = "api_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    rate_limit_daily: Mapped[int] = mapped_column(Integer, default=1000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="api_clients")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    share_card_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="tasks")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    usage_date: Mapped[date] = mapped_column(Date, default=date.today)
    count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="usage_logs")

    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_usage_user_date"),
    )


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="credit_transactions")


class UserPerceptionRecord(Base):
    """Best perception scores per user/mode/style combination."""
    __tablename__ = "user_perception_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    style: Mapped[str] = mapped_column(String(100), nullable=False)
    warmth: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    presence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    appeal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    authenticity: Mapped[float] = mapped_column(Float, nullable=False, default=9.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="perception_records")

    __table_args__ = (
        UniqueConstraint("user_id", "mode", "style", name="uq_perception_user_mode_style"),
    )
