"""Lightweight per-browser session store (no accounts needed).

A session is created lazily from a client-generated random id. State lives in memory and is
mirrored to a JSON file so a backend restart does not wipe the demo profile. Sessions are
isolated from each other: every public method takes the session id and touches only that entry.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from .schemas import FeedbackAction, ProfileUpdate, TasteProfile

log = logging.getLogger("rs.sessions")

MAX_SESSIONS = 500
SESSION_TTL_SECONDS = 30 * 24 * 3600
MAX_HISTORY = 12
MAX_SHOWN = 400


class Turn(BaseModel):
    role: str
    text: str


class Session(BaseModel):
    session_id: str
    profile: TasteProfile = Field(default_factory=TasteProfile)
    shown_ids: list[int] = Field(default_factory=list)  # every movie already recommended in this conversation
    last_ids: list[int] = Field(default_factory=list)  # the most recent batch, in display order
    last_cards: list[dict] = Field(default_factory=list)  # cards exactly as shown (so 'why?' answers match the UI)
    history: list[Turn] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)


class SessionStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}
        self._load()

    # ---------------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self._path or not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text())
            now = time.time()
            for sid, payload in raw.items():
                try:
                    session = Session.model_validate(payload)
                except ValidationError:
                    continue  # skip malformed entries instead of crashing the app
                if now - session.updated_at < SESSION_TTL_SECONDS:
                    self._sessions[sid] = session
        except (OSError, json.JSONDecodeError, AttributeError):
            log.warning("session file unreadable; starting with an empty store")

    def _persist(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({k: v.model_dump() for k, v in self._sessions.items()})
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
            os.replace(tmp, self._path)
        except OSError:
            log.warning("could not persist sessions")

    # ---------------------------------------------------------------- access
    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                if len(self._sessions) >= MAX_SESSIONS:
                    oldest = min(self._sessions.values(), key=lambda s: s.updated_at)
                    del self._sessions[oldest.session_id]
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
            return session

    def save(self, session: Session) -> None:
        with self._lock:
            session.updated_at = time.time()
            session.shown_ids = session.shown_ids[-MAX_SHOWN:]
            session.history = session.history[-MAX_HISTORY:]
            self._sessions[session.session_id] = session
            self._persist()

    def reset(self, session_id: str, keep_profile: bool = True) -> Session:
        with self._lock:
            old = self.get(session_id)
            fresh = Session(session_id=session_id, profile=old.profile if keep_profile else TasteProfile())
            self.save(fresh)
            return fresh

    # ---------------------------------------------------------------- profile mutations
    def apply_update(self, session: Session, update: ProfileUpdate, valid_genres: set[str], valid_ids: set[int]) -> None:
        """Apply a partial profile update with validation; unknown genres/ids are dropped."""
        fields = update.model_fields_set
        p = session.profile
        if "genres" in fields and update.genres is not None:
            p.genres = [g for g in dict.fromkeys(update.genres) if g in valid_genres]
        if "excluded_genres" in fields and update.excluded_genres is not None:
            p.excluded_genres = [g for g in dict.fromkeys(update.excluded_genres) if g in valid_genres]
        p.genres = [g for g in p.genres if g not in p.excluded_genres]
        if "liked_ids" in fields and update.liked_ids is not None:
            p.liked_ids = [i for i in dict.fromkeys(update.liked_ids) if i in valid_ids]
            p.disliked_ids = [i for i in p.disliked_ids if i not in p.liked_ids]
        if "disliked_ids" in fields and update.disliked_ids is not None:
            p.disliked_ids = [i for i in dict.fromkeys(update.disliked_ids) if i in valid_ids]
            p.liked_ids = [i for i in p.liked_ids if i not in p.disliked_ids]
        for name in ("min_rating", "year_min", "year_max"):
            if name in fields:
                setattr(p, name, getattr(update, name))
        for name in ("novelty", "strategy", "result_count"):
            value = getattr(update, name)
            if name in fields and value is not None:
                setattr(p, name, value)
        if p.year_min and p.year_max and p.year_min > p.year_max:
            p.year_min, p.year_max = p.year_max, p.year_min

    @staticmethod
    def apply_feedback(session: Session, movie_id: int, action: FeedbackAction) -> None:
        """Idempotent: repeating the same feedback never double-counts."""
        p = session.profile
        p.liked_ids = [i for i in p.liked_ids if i != movie_id]
        p.disliked_ids = [i for i in p.disliked_ids if i != movie_id]
        if action == "like":
            p.liked_ids.append(movie_id)
        elif action == "dislike":
            p.disliked_ids.append(movie_id)
        p.liked_ids = p.liked_ids[-200:]
        p.disliked_ids = p.disliked_ids[-200:]
