from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_file_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    company_info: Mapped[str] = mapped_column(Text, nullable=False)
    additional_info: Mapped[str] = mapped_column(Text, nullable=True, default="")
    feedback: Mapped[str] = mapped_column(Text, nullable=True, default="")

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    user: Mapped["User"] = relationship(back_populates="sessions")

    stages: Mapped[list["Stage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    @property
    def cv_file_path(self) -> str:
        return f"media/cv_files/{self.cv_file_name}"


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_name: Mapped[str] = mapped_column(String(100), nullable=False)
    stage_description: Mapped[str] = mapped_column(Text, nullable=False)
    interviewer_persona: Mapped[str] = mapped_column(Text, nullable=False)
    questions_and_answers: Mapped[str] = mapped_column(Text, nullable=False)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )

    session: Mapped["Session"] = relationship(back_populates="stages")

    practice_attempts: Mapped[list["PracticeAttempt"]] = relationship(
        back_populates="stage",
        cascade="all, delete-orphan",
    )


class PracticeAttempt(Base):
    __tablename__ = "practice_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    stage_id: Mapped[int] = mapped_column(
        ForeignKey("stages.id"),
        nullable=False,
        index=True,
    )
    
    room_url: Mapped[str] = mapped_column(Text, nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="STARTED",
        nullable=False,
    )
    @property
    def md_results_path(self) -> str:
        return f"media/reports/practice_{self.id}.md"
    @property
    def pdf_results_path(self) -> str:
        return f"media/reports/practice_{self.id}.pdf"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    stage: Mapped["Stage"] = relationship(back_populates="practice_attempts")

    answers: Mapped[list["Answer"]] = relationship(
        back_populates="practice_attempt",
        cascade="all, delete-orphan",
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    practice_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("practice_attempts.id"),
        nullable=False,
        index=True,
    )

    question_order: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    behaviour: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)

    practice_attempt: Mapped["PracticeAttempt"] = relationship(
        back_populates="answers"
    )