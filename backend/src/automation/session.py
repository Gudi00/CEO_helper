"""Session state machine across all execution modes. See ADR 0006."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4


class Mode(StrEnum):
    ASSIST = "assist"
    FULL_AUTO = "full_auto"
    STEP_BY_STEP = "step_by_step"


class Status(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass
class SessionState:
    id: UUID = field(default_factory=uuid4)
    mode: Mode = Mode.ASSIST
    cmid: str = ""
    attempt_id: str | None = None
    status: Status = Status.RUNNING
    current_page: int = 0
    questions_answered: int = 0

    def advance_page(self) -> None:
        self.current_page += 1

    def mark_answered(self) -> None:
        self.questions_answered += 1

    def complete(self) -> None:
        self.status = Status.COMPLETED

    def abort(self) -> None:
        self.status = Status.ABORTED

    def fail(self) -> None:
        self.status = Status.FAILED
