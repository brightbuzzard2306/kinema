"""Optional TMDB poster lookup using the documented TMDB v3 API.

Disabled (returns nothing) unless TMDB_API_KEY is set. Results, including misses, are cached
on disk so each movie costs at most one request. The recommender never depends on this module.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

log = logging.getLogger("rs.posters")

TMDB_MOVIE_URL = "https://api.themoviedb.org/3/movie/{tmdb_id}"
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


class PosterService:
    def __init__(self, api_key: str | None, cache_path: Path, client: httpx.Client | None = None) -> None:
        self._key = (api_key or "").strip() or None
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._client = client
        self._cache: dict[str, str | None] = {}
        if cache_path.is_file():
            try:
                self._cache = json.loads(cache_path.read_text())
            except (OSError, json.JSONDecodeError):
                self._cache = {}

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def _persist(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache))
        except OSError:
            log.warning("could not persist poster cache")

    def _fetch(self, tmdb_id: int) -> tuple[str | None, bool]:
        """Return (url, cacheable). Transient failures are not cached."""
        assert self._key is not None
        headers, params = {}, {}
        if self._key.startswith("eyJ"):  # v4 read-access token
            headers["Authorization"] = f"Bearer {self._key}"
        else:
            params["api_key"] = self._key
        client = self._client or httpx.Client(timeout=6.0)
        try:
            resp = client.get(TMDB_MOVIE_URL.format(tmdb_id=tmdb_id), headers=headers, params=params)
        except httpx.HTTPError:
            return None, False
        finally:
            if self._client is None:
                client.close()
        if resp.status_code == 404:
            return None, True
        if resp.status_code != 200:
            return None, False
        path = resp.json().get("poster_path")
        return (f"{IMAGE_BASE}{path}" if path else None), True

    def lookup(self, tmdb_ids: dict[int, int | None]) -> dict[int, str | None]:
        """movie_id -> poster url (or None). ``tmdb_ids`` maps movie_id to its TMDB id."""
        out: dict[int, str | None] = {}
        todo: list[tuple[int, int]] = []
        for movie_id, tmdb_id in tmdb_ids.items():
            if not self.enabled or tmdb_id is None:
                out[movie_id] = None
            elif str(tmdb_id) in self._cache:
                out[movie_id] = self._cache[str(tmdb_id)]
            else:
                todo.append((movie_id, tmdb_id))
        if todo:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda pair: self._fetch(pair[1]), todo))
            with self._lock:
                for (movie_id, tmdb_id), (url, cacheable) in zip(todo, results):
                    out[movie_id] = url
                    if cacheable:
                        self._cache[str(tmdb_id)] = url
                self._persist()
        return out
