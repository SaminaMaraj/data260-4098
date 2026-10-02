from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .hw4_database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    sessions: Mapped[list["SessionToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="sessions",
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    route_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    operator: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    route_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    incidents: Mapped[list["IncidentRecord"]] = relationship(
        back_populates="route",
        passive_deletes=True,
    )


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    incident_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )
    incident_title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    route_line: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    submitter_email: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    passengers_affected: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    terms_accepted: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    submission_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    route: Mapped["Route"] = relationship(
        back_populates="incidents",
    )

    related_items: Mapped[list["IncidentRelatedData"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )


class IncidentRelatedData(Base):
    __tablename__ = "incident_related_data"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    related_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    related_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    incident: Mapped["IncidentRecord"] = relationship(
        back_populates="related_items",
    )
