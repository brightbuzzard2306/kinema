"""FastAPI application: thin HTTP layer over ChatService.

Run:  cd backend && .venv/bin/uvicorn app.main:app --port 8000
"""


import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .catalog import Catalog, normalize_text
from .config import Settings, get_settings
from .dataset import DatasetError, load_raw
from .engine.recommender import DEFAULT_WEIGHTS, Recommender
from .llm import ClaudeService
from .nlp.spell import MAX_TOKENS, tokenize
from .posters import PosterService
from .protect import BodyLimitMiddleware, DailyBudget, SecurityHeadersMiddleware, SlidingWindow, codes_match, derive_token
from .schemas import (
    ChatRequest,
    ChatResponse,
    CompareRequest,
    AccessRequest,
    CompareResponse,
    FeedbackRequest,
    ProfileUpdate,
    RecommendRequest,
    TasteProfile,
)
from .service import ChatService
from .sessions import SessionStore
from .streaming import SSE_HEADERS, event_stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# HTTP client libraries log full URLs at INFO, and TMDB's v3 key travels in the URL: keep those out of the logs
for _noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "anthropic"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger("rs.api")
HEAVY_PATHS = {"/chat", "/chat/stream", "/recommend", "/recommend/stream", "/compare"}  # each may cost a Claude call
OPEN_PATHS = {"/health", "/access/verify"}  # reachable without the access code (health is what uptime monitors ping)
MAX_FAILED_CODES = 8  # wrong access codes per visitor per 10 minutes before they are locked out for a while
MAX_FAILED_CODES_SITEWIDE = 60  # ...and across ALL visitors, because a visitor's address can be forged
SESSION_ID = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
PREFERENCE_WEIGHT = 0.15  # share of the hybrid reserved for explicit genre preferences


@dataclass
class AppState:
    settings: Settings
    ready: bool = False
    error: str | None = None
    catalog: Catalog | None = None
    service: ChatService | None = None
    posters: PosterService | None = None
    n_ratings: int = 0
    n_users: int = 0


class ApiProblem(Exception):
    """An expected, user-facing failure (wrong code, too many requests) with the app's usual error shape."""

    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def client_key(request: Request) -> str:
    """One bucket per visitor, taken from the headers the hosting edge sets itself.

    ``X-Forwarded-For`` is a list the visitor can start with anything, and only the LAST entry was added by our own proxy, so the
    first entry must never be trusted (forging it used to give every request a fresh, unlimited bucket).
    """
    for name in ("cf-connecting-ip", "true-client-ip"):  # set (and overwritten) by the CDN in front of the host
        value = request.headers.get(name, "").strip()
        if value:
            return value[:64]
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()[:64]
    return request.client.host if request.client else "unknown"


def _scaled(w: dict[str, float]) -> dict[str, float]:
    """Tuned weights cover content/collaborative/popularity; reserve a share for explicit genre preferences."""
    total = sum(w.get(k, 0) for k in ("content", "collaborative", "popularity")) or 1.0
    out = {k: round((1 - PREFERENCE_WEIGHT) * w.get(k, 0) / total, 4) for k in ("content", "collaborative", "popularity")}
    out["preference"] = PREFERENCE_WEIGHT
    return out


def _tuned_params(settings: Settings) -> tuple[dict | None, dict[str, float], dict[str, float] | None]:
    """Use the settings chosen on the validation split (reports/evaluation.json) when available."""
    path = settings.reports_dir / "evaluation.json"
    try:
        report = json.loads(path.read_text())
        chosen = report["chosen_config"]
        warm = _scaled(chosen["hybrid_weights"]) if chosen["hybrid_weights"] else dict(DEFAULT_WEIGHTS)
        thin_raw = (report.get("few_likes") or {}).get("chosen_weights")
        return chosen["knn"], warm, (_scaled(thin_raw) if thin_raw else None)
    except (OSError, KeyError, ValueError, TypeError):
        return None, dict(DEFAULT_WEIGHTS), None


def build_state(settings: Settings) -> AppState:
    state = AppState(settings=settings)
    try:
        raw = load_raw(settings.dataset_dir)
    except DatasetError as exc:
        state.error = str(exc)
        log.error("dataset unavailable: %s", exc)
        return state
    started = time.time()
    catalog = Catalog.build(raw)
    knn, weights, thin = _tuned_params(settings)
    recommender = Recommender(catalog, raw.ratings, knn_params=knn, hybrid_weights=weights, thin_weights=thin)
    state.catalog = catalog
    state.n_ratings = len(raw.ratings)
    state.n_users = int(raw.ratings["userId"].nunique())
    state.service = ChatService(
        catalog, recommender, SessionStore(settings.cache_dir / "sessions.json"),
        ClaudeService(settings, budget=DailyBudget(settings.claude_daily_limit)), settings.max_results
    )
    state.posters = PosterService(
        settings.tmdb_api_key.get_secret_value() if settings.tmdb_api_key else None, settings.cache_dir / "posters.json"
    )
    state.ready = True
    log.info("models ready in %.1fs (%d movies, %d ratings)", time.time() - started, len(catalog), state.n_ratings)
    return state


def create_app(settings: Settings | None = None, state: AppState | None = None) -> FastAPI:
    settings = settings or get_settings()
    if os.environ.get("RENDER") and not settings.access_code_value and not settings.allow_public:
        # fail closed: a hosted copy without its access code would be a public, Claude-spending website
        raise RuntimeError("ACCESS_CODE is not set on this hosted deployment. Set it, or set ALLOW_PUBLIC=true to run open on purpose.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.rs = state or build_state(settings)
        yield

    heavy = SlidingWindow(settings.rate_heavy_per_min)
    light = SlidingWindow(settings.rate_light_per_min)
    failed_codes = SlidingWindow(MAX_FAILED_CODES, window=600.0)
    failed_sitewide = SlidingWindow(MAX_FAILED_CODES_SITEWIDE, window=600.0)
    access_code = settings.access_code_value
    access_token = derive_token(access_code) if access_code else None  # what the browser keeps after a correct code

    async def guard(request: Request) -> None:
        """Runs before every route: access code first, then the per-visitor rate limit."""
        path = request.url.path
        if path in OPEN_PATHS:
            return
        # normal routes accept only the derived token, never the raw code: guessing the code is possible ONLY on /access/verify
        if access_token and not codes_match(request.headers.get("x-access-code", ""), access_token):
            raise ApiProblem(401, "access_denied", "This site is private. Enter the access code to continue.")
        ok, wait = (heavy if path in HEAVY_PATHS else light).hit(client_key(request))
        if not ok:
            raise ApiProblem(429, "rate_limited", f"You're going a little fast. Please wait {wait} s and try again.", {"Retry-After": str(wait)})

    app = FastAPI(title="RS Mini Project API", version="1.0.0", lifespan=lifespan, dependencies=[Depends(guard)],
        docs_url=None if access_code else "/docs", redoc_url=None if access_code else "/redoc", openapi_url=None if access_code else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.origins, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "X-Access-Code"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware)  # added last = outermost: oversized bodies are refused before anything reads them

    def get_state(request: Request) -> AppState:
        st: AppState = request.app.state.rs
        if not st.ready:
            raise HTTPException(503, detail=st.error or "The recommender is still starting up.")
        return st

    StateDep = Annotated[AppState, Depends(get_state)]

    # ------------------------------------------------------------ errors (consistent shape, no internals)
    def err(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

    @app.exception_handler(ApiProblem)
    async def api_problem(_: Request, exc: ApiProblem):
        res = err(exc.status, exc.code, exc.message)
        res.headers.update(exc.headers)
        return res

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return err(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
        return err(422, "validation_error", f"Invalid {where}: {first.get('msg', 'bad value')}")

    @app.exception_handler(KeyError)
    async def key_error(_: Request, exc: KeyError):
        return err(404, "not_found", "That movie does not exist in the catalogue.")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")  # stack trace stays in the server log only
        return err(500, "internal_error", "Something went wrong on our side. Please try again.")

    # ------------------------------------------------------------ routes
    @app.api_route("/health", methods=["GET", "HEAD"])  # HEAD: some uptime monitors use it
    def health(request: Request):
        st: AppState = request.app.state.rs
        return {
            "status": "ok" if st.ready else "unavailable",
            "dataset": {"ready": st.ready, "movies": len(st.catalog) if st.catalog else 0, "ratings": st.n_ratings, "users": st.n_users, "error": st.error},
            "llm": {"enabled": st.settings.llm_enabled, "model": st.settings.claude_model if st.settings.llm_enabled else None},
            "posters": {"enabled": st.settings.tmdb_enabled},
            "access": {"required": bool(access_code)},
        }

    @app.post("/access/verify")
    def verify_access(request: Request, body: AccessRequest):
        """Check an access code. Wrong guesses are counted per visitor so the code can't be brute-forced."""
        who = client_key(request)
        if not access_code:
            return {"ok": True, "required": False}
        if not (failed_codes.peek(who) and failed_sitewide.peek("all")):
            raise ApiProblem(429, "rate_limited", "Too many wrong codes. Please wait a few minutes and try again.", {"Retry-After": "600"})
        if codes_match(body.code, access_code):
            return {"ok": True, "required": True, "token": access_token}
        failed_codes.hit(who)
        failed_sitewide.hit("all")
        raise ApiProblem(401, "access_denied", "That code isn't right.")

    @app.get("/llm/status")
    def llm_status(st: StateDep):
        """Whether Claude really works right now (one cached test call). Never returns the key."""
        assert st.service
        claude = st.service.claude
        if not claude.enabled:
            return {"enabled": False, "ok": False, "reason": "No Anthropic API key configured.", "model": None}
        ok, reason = claude.check()
        return {"enabled": True, "ok": ok, "reason": reason, "model": st.settings.claude_model}

    @app.get("/meta")
    def meta(st: StateDep):
        assert st.catalog
        return {
            "genres": st.catalog.all_genres,
            "strategies": ["hybrid", "popular", "content", "collaborative"],
            "max_results": st.settings.max_results,
            "max_message_chars": st.settings.max_message_chars,
        }

    @app.get("/movies")
    def search_movies(st: StateDep, q: Annotated[str, Query(max_length=80)] = "", limit: Annotated[int, Query(ge=1, le=30)] = 10):
        assert st.catalog
        needle = normalize_text(q)
        movies = st.catalog.movies
        if needle:
            hits = [m for m in movies if needle in normalize_text(m.title)]
            hits.sort(key=lambda m: (not normalize_text(m.title).startswith(needle), -m.n_ratings))
        else:  # no query: the most-rated movies, handy for onboarding
            hits = sorted(movies, key=lambda m: -m.n_ratings)
        return {"results": [_movie_summary(m) for m in hits[:limit]]}

    @app.get("/movies/{movie_id}")
    def movie_detail(st: StateDep, movie_id: int):
        assert st.catalog
        m = st.catalog.get(movie_id)
        if m is None:
            raise KeyError(movie_id)
        return _movie_summary(m)

    @app.get("/posters")
    def posters(st: StateDep, ids: Annotated[str, Query(max_length=200)]):
        assert st.catalog and st.posters
        try:
            movie_ids = [int(x) for x in ids.split(",") if x.strip()][:24]
        except ValueError:
            raise HTTPException(422, "ids must be a comma-separated list of integers")
        mapping = {i: (st.catalog.get(i).tmdb_id if st.catalog.get(i) else None) for i in movie_ids}
        return {"enabled": st.posters.enabled, "posters": {str(k): v for k, v in st.posters.lookup(mapping).items()}}

    @app.post("/chat", response_model=ChatResponse)
    def chat(st: StateDep, body: ChatRequest):
        assert st.service
        if len(body.message) > st.settings.max_message_chars:
            raise HTTPException(422, f"Message is too long (max {st.settings.max_message_chars} characters).")
        return st.service.chat(body.session_id, body.message)

    @app.post("/chat/stream")
    def chat_stream(st: StateDep, body: ChatRequest):
        """Same turn as POST /chat, delivered as Server-Sent Events (see app/streaming.py)."""
        assert st.service
        if len(body.message) > st.settings.max_message_chars:
            raise HTTPException(422, f"Message is too long (max {st.settings.max_message_chars} characters).")
        service = st.service
        return StreamingResponse(
            event_stream(lambda emit: service.chat(body.session_id, body.message, emit)),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    @app.post("/recommend/stream")
    def recommend_stream(st: StateDep, body: RecommendRequest):
        assert st.service and st.catalog
        if body.anchor_movie_id is not None and st.catalog.get(body.anchor_movie_id) is None:
            raise KeyError(body.anchor_movie_id)  # a normal 404 before any streaming starts
        service = st.service
        return StreamingResponse(event_stream(lambda emit: service.recommend(body, emit)), media_type="text/event-stream", headers=SSE_HEADERS)

    @app.post("/recommend", response_model=ChatResponse)
    def recommend(st: StateDep, body: RecommendRequest):
        assert st.service
        return st.service.recommend(body)

    @app.post("/compare", response_model=CompareResponse)
    def compare(st: StateDep, body: CompareRequest):
        assert st.service
        result = st.service.compare(body.session_id, body.count, body.anchor_movie_id)
        try:  # real offline scores for the four methods, if an evaluation has been run
            metrics = json.loads((st.settings.reports_dir / "evaluation.json").read_text())["metrics"]
            result.offline_ndcg = {m: round(float(metrics[m]["ndcg"]), 4) for m in st.service.COMPARE_ORDER}
        except (OSError, KeyError, ValueError, TypeError):
            result.offline_ndcg = None
        return result

    @app.post("/feedback", response_model=TasteProfile)
    def feedback(st: StateDep, body: FeedbackRequest):
        assert st.service
        return st.service.feedback(body)

    @app.get("/sessions/{session_id}")
    def session_state(st: StateDep, session_id: Annotated[str, SESSION_ID]):
        assert st.service
        s = st.service.sessions.peek(session_id)  # read-only: a GET must not create (or evict) a session
        if s is None:
            return {"profile": TasteProfile(), "last_cards": [], "history": []}
        return {"profile": s.profile, "last_cards": s.last_cards, "history": [t.model_dump() for t in s.history]}

    @app.get("/sessions/{session_id}/profile", response_model=TasteProfile)
    def get_profile(st: StateDep, session_id: Annotated[str, SESSION_ID]):
        assert st.service
        s = st.service.sessions.peek(session_id)
        return s.profile if s else TasteProfile()

    @app.put("/sessions/{session_id}/profile", response_model=TasteProfile)
    def put_profile(st: StateDep, session_id: Annotated[str, SESSION_ID], body: ProfileUpdate):
        assert st.service
        return st.service.update_profile(session_id, body)

    @app.post("/sessions/{session_id}/reset", response_model=TasteProfile)
    def reset_session(st: StateDep, session_id: Annotated[str, SESSION_ID], keep_profile: bool = True):
        assert st.service
        return st.service.sessions.reset(session_id, keep_profile).profile

    # ------------------------------------------------------------ NLP Lab: spelling correction of movie titles (see app/nlp/spell.py)
    @app.get("/nlp/spell")
    def nlp_spell(st: StateDep, q: Annotated[str, Query(max_length=120)]):
        """Noisy-channel + bigram + Viterbi correction of a typed title; returns the whole candidate lattice so the UI can show the work."""
        assert st.catalog
        assert st.service
        result = st.service.spell.correct(tokenize(q)[:MAX_TOKENS])
        key = result["corrected"]
        ids: list[int] = []
        for variant in (key, key.removeprefix("the "), "the " + key):  # titles are indexed with and without a leading article
            ids = st.catalog._title_index.get(variant, [])
            if ids:
                break
        movies = [st.catalog.movies[i] for i in ids][:5]
        return {"query": q, **result, "matches": [{"movie_id": m.movie_id, "title": m.title, "year": m.year} for m in movies]}

    @app.get("/nlp/report")
    def nlp_report(request: Request):
        path = request.app.state.rs.settings.reports_dir / "nlp_spellcheck.json"
        if not path.is_file():
            raise HTTPException(404, "No NLP evaluation has been run yet. Run: python -m scripts.run_nlp_eval")
        return json.loads(path.read_text())

    @app.get("/evaluation")
    def evaluation(request: Request):
        path = request.app.state.rs.settings.reports_dir / "evaluation.json"
        if not path.is_file():
            raise HTTPException(404, "No evaluation has been run yet. Run: python -m scripts.run_evaluation")
        return json.loads(path.read_text())

    return app


def _movie_summary(m) -> dict:
    return {
        "movie_id": m.movie_id, "title": m.title, "year": m.year, "genres": list(m.genres),
        "mean_rating": round(m.mean_rating, 2) if m.mean_rating is not None else None, "n_ratings": m.n_ratings, "tmdb_id": m.tmdb_id,
    }


app = create_app()
