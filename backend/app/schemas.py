"""Pydantic models shared by the API, session store and NLU layer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

StrategyName = Literal["hybrid", "popular", "content", "collaborative"]
Intent = Literal["recommend", "similar", "explain", "reject_last", "reset", "help", "chitchat"]
FeedbackAction = Literal["like", "dislike", "clear"]


class TasteProfile(BaseModel):
    """The user's editable taste profile (also what the profile drawer shows)."""

    liked_ids: list[int] = Field(default_factory=list, max_length=200)
    disliked_ids: list[int] = Field(default_factory=list, max_length=200)
    genres: list[str] = Field(default_factory=list, max_length=6)
    excluded_genres: list[str] = Field(default_factory=list, max_length=10)
    min_rating: float | None = Field(default=None, ge=0.5, le=5.0)
    year_min: int | None = Field(default=None, ge=1880, le=2100)
    year_max: int | None = Field(default=None, ge=1880, le=2100)
    novelty: float = Field(default=0.3, ge=0.0, le=1.0)
    strategy: StrategyName = "hybrid"
    result_count: int = Field(default=6, ge=1, le=12)


class ProfileUpdate(BaseModel):
    """Partial update; omitted fields are untouched, explicit null clears nullable fields."""

    liked_ids: list[int] | None = Field(default=None, max_length=200)
    disliked_ids: list[int] | None = Field(default=None, max_length=200)
    genres: list[str] | None = Field(default=None, max_length=6)
    excluded_genres: list[str] | None = Field(default=None, max_length=10)
    min_rating: float | None = Field(default=None, ge=0.5, le=5.0)
    year_min: int | None = Field(default=None, ge=1880, le=2100)
    year_max: int | None = Field(default=None, ge=1880, le=2100)
    novelty: float | None = Field(default=None, ge=0.0, le=1.0)
    strategy: StrategyName | None = None
    result_count: int | None = Field(default=None, ge=1, le=12)


class Preferences(BaseModel):
    """What the NLU layer (Claude or the rule parser) extracts from one user message."""

    intent: Intent = "recommend"
    genres: list[str] = Field(default_factory=list)
    excluded_genres: list[str] = Field(default_factory=list)
    liked_titles: list[str] = Field(default_factory=list)
    disliked_titles: list[str] = Field(default_factory=list)
    anchor_titles: list[str] = Field(default_factory=list)
    ordinal_reference: int | None = None
    mood: str | None = None
    min_rating: float | None = None
    max_runtime_minutes: int | None = None
    count: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    novelty: float | None = None
    unsupported: list[str] = Field(default_factory=list)  # requests the dataset cannot express (e.g. "less complicated")

    @field_validator("liked_titles", "disliked_titles", "anchor_titles", "genres", "excluded_genres", "unsupported", mode="before")
    @classmethod
    def _cap_lists(cls, v):
        return v[:10] if isinstance(v, list) else v


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=2000)


class RecommendRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    anchor_movie_id: int | None = None
    count: int | None = Field(default=None, ge=1, le=12)
    fresh: bool = Field(default=False, description="Ignore previously shown movies.")


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    movie_id: int
    action: FeedbackAction


class ReasonOut(BaseModel):
    kind: str
    text: str


class MovieCard(BaseModel):
    movie_id: int
    title: str
    year: int | None
    genres: list[str]
    mean_rating: float | None
    n_ratings: int
    score: float
    components: dict[str, float | None]
    weights_used: dict[str, float]
    reasons: list[ReasonOut]
    confidence: Literal["high", "medium", "low"]
    confidence_basis: str
    tmdb_id: int | None = None
    feedback: Literal["like", "dislike"] | None = None


class LLMStatus(BaseModel):
    mode: Literal["claude", "fallback"]
    reason: str | None = None  # why we are in fallback mode (never contains secrets)


class ChatResponse(BaseModel):
    reply: str
    intent: Intent
    recommendations: list[MovieCard]
    notes: list[str]
    suggestions: list[str]
    profile: TasteProfile
    strategy_used: str
    llm: LLMStatus
    unresolved_titles: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list, description="Profile changes caused by this message.")


class CompareRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    count: int = Field(default=5, ge=1, le=8)
    anchor_movie_id: int | None = Field(default=None, description="Compare the strategies for 'more like this movie'.")


class CompareColumn(BaseModel):
    strategy_used: str
    notes: list[str]
    regime: str | None = None  # hybrid only: cold | thin | blend | warm
    movies: list[MovieCard]


class CompareResponse(BaseModel):
    columns: dict[str, CompareColumn]
    signals: dict[str, int | list[str]]  # what the algorithms were given: liked movies, genres...
    offline_ndcg: dict[str, float] | None = None  # from reports/evaluation.json, when it exists


class AccessRequest(BaseModel):
    code: str = Field(default="", max_length=200)
