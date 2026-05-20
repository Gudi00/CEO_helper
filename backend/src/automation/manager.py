"""Engine lifecycle manager. Owns running engines keyed by session_id and
plumbs engine events through to the WS broadcaster + persistence.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.ai.base import AIProvider
from src.automation.browser import Browser
from src.automation.engine import Engine, EngineEvent
from src.automation.session import Mode, SessionState, Status
from src.moodle.types import NormalizedQuestion
from src.persistence import Answer, Question, Session, get_session

logger = logging.getLogger(__name__)

# Factory signatures so tests can inject FakeBrowser / StubAI.
BrowserFactory = Callable[[str, int], Awaitable[Browser]]
AIFactory = Callable[[], AIProvider]
Broadcast = Callable[[UUID, dict[str, Any]], Awaitable[None]]


class EngineAlreadyRunning(RuntimeError):
    pass


class EngineNotRunning(LookupError):
    pass


class EngineManager:
    def __init__(
        self,
        *,
        browser_factory: BrowserFactory,
        ai_factory: AIFactory,
        broadcast: Broadcast,
        engine_sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._browser_factory = browser_factory
        self._ai_factory = ai_factory
        self._broadcast = broadcast
        self._engine_sleep = engine_sleep
        self._engines: dict[UUID, Engine] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        # Most-recent question per session, captured at `question_loaded`
        # and reused at `answer_suggested` for persistence.
        self._pending_question: dict[UUID, NormalizedQuestion] = {}

    async def start(
        self,
        *,
        session_id: UUID,
        cmid: str,
        access_strategy: str,
        cdp_port: int,
    ) -> None:
        if session_id in self._engines:
            raise EngineAlreadyRunning(str(session_id))

        browser = await self._browser_factory(access_strategy, cdp_port)
        ai = self._ai_factory()

        async def on_event(event: EngineEvent) -> None:
            await self._handle_event(session_id, event)

        engine_kwargs: dict[str, Any] = {
            "browser": browser,
            "ai": ai,
            "cmid": cmid,
            "on_event": on_event,
        }
        if self._engine_sleep is not None:
            engine_kwargs["sleep"] = self._engine_sleep
        engine = Engine(**engine_kwargs)
        state = SessionState(
            id=session_id,
            mode=Mode.FULL_AUTO,
            cmid=cmid,
            status=Status.RUNNING,
        )

        self._engines[session_id] = engine
        self._tasks[session_id] = asyncio.create_task(
            self._run(engine, state), name=f"engine-{session_id}"
        )

    async def stop(self, session_id: UUID) -> None:
        engine = self._engines.get(session_id)
        if engine is None:
            raise EngineNotRunning(str(session_id))
        await engine.stop()
        task = self._tasks.get(session_id)
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    async def wait_for(
        self, session_id: UUID, *, timeout: float = 30.0
    ) -> None:
        """Block until the engine task for this session completes.

        Mainly intended for integration tests; production paths use the WS
        event stream to learn when the attempt is finished.
        """
        task = self._tasks.get(session_id)
        if task is None:
            return
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
            return

    def is_running(self, session_id: UUID) -> bool:
        return session_id in self._engines

    async def _run(self, engine: Engine, state: SessionState) -> None:
        try:
            await engine.run(state)
        except Exception:
            logger.exception("engine task crashed")
        finally:
            self._engines.pop(state.id, None)
            self._tasks.pop(state.id, None)
            await self._persist_state(state)

    async def _handle_event(
        self, session_id: UUID, event: EngineEvent
    ) -> None:
        payload = event.payload
        if event.type == "question_loaded":
            raw_q = payload.get("question")
            if raw_q is not None:
                self._pending_question[session_id] = NormalizedQuestion(
                    **raw_q
                )
            payload = {k: v for k, v in payload.items() if k != "question"}
        message = {"type": event.type, **payload}
        await self._broadcast(session_id, message)
        if event.type == "answer_suggested":
            await self._persist_answer(session_id, payload)
        elif event.type == "attempt_completed":
            await self._persist_completion(session_id, event.payload)

    async def _persist_answer(
        self, session_id: UUID, payload: dict[str, Any]
    ) -> None:
        question = self._pending_question.pop(session_id, None)
        if question is None:
            logger.warning(
                "answer_suggested without prior question_loaded for %s",
                session_id,
            )
            return

        async with get_session() as db:
            existing = await db.get(Question, question.hash)
            if existing is None:
                db.add(
                    Question(
                        hash=question.hash,
                        text=question.text,
                        options_json=[o.model_dump() for o in question.options],
                        q_type=question.type,
                    )
                )
            else:
                existing.times_seen += 1

            session = await db.get(Session, session_id)
            if session is not None:
                session.attempt_id = question.metadata.attempt_id

            db.add(
                Answer(
                    session_id=session_id,
                    question_hash=question.hash,
                    answer_indices_json=payload["answer_indices"],
                    confidence=payload["confidence"],
                    reasoning=payload.get("reasoning"),
                    provider=payload["provider"],
                    from_cache=payload.get("from_cache", False),
                )
            )

    async def _persist_completion(
        self, session_id: UUID, payload: dict[str, Any]
    ) -> None:
        async with get_session() as db:
            session = await db.get(Session, session_id)
            if session is None:
                logger.warning(
                    "completion for unknown session %s", session_id
                )
                return
            session.status = "completed"
            session.finished_at = datetime.now(UTC)
            session.score = payload.get("score")
            session.max_score = payload.get("max_score")
            logger.info(
                "persisted completion: session=%s score=%s/%s",
                session_id,
                session.score,
                session.max_score,
            )

    async def _persist_state(self, state: SessionState) -> None:
        if state.status is Status.COMPLETED:
            return  # already updated via attempt_completed event
        async with get_session() as db:
            session = await db.get(Session, state.id)
            if session is None:
                return
            session.status = state.status.value
            session.finished_at = datetime.now(UTC)
