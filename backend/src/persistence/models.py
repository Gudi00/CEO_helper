from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mode: Mapped[str] = mapped_column(String(32))
    access_strategy: Mapped[str] = mapped_column(String(32))
    cmid: Mapped[str] = mapped_column(String(64), index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_provider_primary: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)

    answers: Mapped[list[Answer]] = relationship(back_populates="session", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(String)
    options_json: Mapped[list[dict]] = mapped_column(JSON)
    q_type: Mapped[str] = mapped_column(String(32))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    times_seen: Mapped[int] = mapped_column(Integer, default=1)

    answers: Mapped[list[Answer]] = relationship(back_populates="question")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    question_hash: Mapped[str] = mapped_column(ForeignKey("questions.hash"), index=True)
    answer_indices_json: Mapped[list[int]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    was_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[Session] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="answers")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[Session] = relationship(back_populates="events")
