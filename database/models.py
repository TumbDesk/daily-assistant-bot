import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Mapped, foreign, mapped_column, relationship


class Base(DeclarativeBase):
    pass


event_flags = Table(
    "event_flags",
    Base.metadata,
    Column("event_id", ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("flag_id", ForeignKey("flags.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    home_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    home_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    home_location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    report_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    report_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    include_events: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    include_birthdays: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    include_weather: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_report_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    locale: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    identities: Mapped[list["UserIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Category.user_id",
        primaryjoin="and_(User.id == foreign(Category.user_id), Category.user_id.isnot(None))",
    )
    flags: Mapped[list["Flag"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(back_populates="owner")
    birthdays: Mapped[list["Birthday"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    travel_trips: Mapped[list["TravelTrip"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_identity_platform"),
        Index("ix_identity_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship(back_populates="identities")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_category_user_name"),
        Index(
            "uq_category_global_name",
            "name",
            unique=True,
            sqlite_where=text("user_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User | None"] = relationship(
        back_populates="categories",
        foreign_keys=[user_id],
    )
    events: Mapped[list["Event"]] = relationship(back_populates="category")


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_flag_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship(back_populates="flags")
    events: Mapped[list["Event"]] = relationship(
        secondary=event_flags, back_populates="flags"
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_context_start", "context_chat_id", "start_datetime"),
        Index("ix_events_owner_start", "owner_id", "start_datetime"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminder_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rrule: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    context_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="events")
    category: Mapped["Category | None"] = relationship(back_populates="events")
    flags: Mapped[list["Flag"]] = relationship(
        secondary=event_flags, back_populates="events"
    )
    exceptions: Mapped[list["EventException"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventException(Base):
    __tablename__ = "event_exceptions"
    __table_args__ = (
        UniqueConstraint("event_id", "original_start", name="uq_event_exception_occ"),
        Index("ix_event_exceptions_event", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    original_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exception_type: Mapped[str] = mapped_column(String(16), nullable=False)
    new_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    new_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="exceptions")


class Birthday(Base):
    __tablename__ = "birthdays"
    __table_args__ = (
        UniqueConstraint("user_id", "name", "birth_date", name="uq_birthday_user_name_date"),
        Index("ix_birthdays_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped["User"] = relationship(back_populates="birthdays")


class TravelTrip(Base):
    __tablename__ = "travel_trips"
    __table_args__ = (
        Index("ix_travel_trips_user_dates", "user_id", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped["User"] = relationship(back_populates="travel_trips")


class BotChat(Base):
    __tablename__ = "bot_chats"

    context_chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class UserChatMembership(Base):
    __tablename__ = "user_chat_memberships"
    __table_args__ = (
        UniqueConstraint(
            "platform_user_id",
            "context_chat_id",
            name="uq_user_chat_membership",
        ),
        Index("ix_user_chat_membership_user", "platform_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    context_chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bot_chats.context_chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
