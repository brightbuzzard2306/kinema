"""Shared fixtures: a tiny synthetic dataset in MovieLens format with known taste clusters.

Clusters: movies 1-12 Sci-Fi, 13-24 Romance, 25-34 Horror, 35-40 Comedy.
Users 1-20 love Sci-Fi, 21-40 love Romance, 41-50 love Horror, 51-60 love Comedy + Romance.
"""

from __future__ import annotations

import shutil

import numpy as np
import pandas as pd
import pytest

from app.catalog import Catalog
from app.config import Settings
from app.dataset import RawData, load_raw
from app.engine.recommender import Recommender

CLUSTERS = {
    "Sci-Fi": range(1, 13),
    "Romance": range(13, 25),
    "Horror": range(25, 35),
    "Comedy": range(35, 41),
}
NAMES = ["Alpha", "Bravo", "Cobalt", "Delta", "Ember", "Flux", "Garnet", "Helix", "Ivory", "Jade", "Krypton", "Kinema",
         "Mirage", "Nimbus", "Onyx", "Prism", "Quartz", "Radiant", "Sable", "Tundra", "Umbra", "Vertex", "Willow", "Xenon",
         "Yonder", "Zephyr", "Ashen", "Birch", "Cinder", "Dusk", "Eclipse", "Fable", "Gale", "Haven", "Iris", "Juniper",
         "Kestrel", "Lotus", "Marble", "Nova"]


def _build_frames(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    movie_rows, link_rows, tag_rows = [], [], []
    cluster_of: dict[int, str] = {}
    for genre, ids in CLUSTERS.items():
        for mid in ids:
            cluster_of[mid] = genre
            genres = genre if genre != "Comedy" else "Comedy|Romance" if mid % 2 else "Comedy"
            movie_rows.append({"movieId": mid, "title": f"{NAMES[mid - 1]} Story ({1980 + mid})", "genres": genres})
            link_rows.append({"movieId": mid, "imdbId": 1000 + mid, "tmdbId": 5000 + mid})
            tag_rows.append({"userId": 1, "movieId": mid, "tag": genre.lower() + " vibes", "timestamp": 1_000_000 + mid})
            tag_rows.append({"userId": 2, "movieId": mid, "tag": genre.lower() + " vibes", "timestamp": 1_000_100 + mid})
    movie_rows.append({"movieId": 99, "title": "Genreless Oddity (2001)", "genres": "(no genres listed)"})
    link_rows.append({"movieId": 99, "imdbId": 1099, "tmdbId": None})
    rating_rows = []
    for user in range(1, 61):
        loved = "Sci-Fi" if user <= 20 else "Romance" if user <= 40 else "Horror" if user <= 50 else "Comedy"
        extra = {"Romance"} if user > 50 else set()
        seen = rng.choice(np.arange(1, 41), size=24, replace=False)
        for t, mid in enumerate(sorted(seen)):
            g = cluster_of[int(mid)]
            high = g == loved or g in extra
            rating = rng.choice([4.0, 4.5, 5.0]) if high else rng.choice([1.0, 1.5, 2.0, 2.5])
            rating_rows.append({"userId": user, "movieId": int(mid), "rating": float(rating), "timestamp": 2_000_000 + user * 1000 + t})
    return {
        "movies": pd.DataFrame(movie_rows),
        "ratings": pd.DataFrame(rating_rows),
        "tags": pd.DataFrame(tag_rows),
        "links": pd.DataFrame(link_rows),
    }


def write_dataset(folder, frames: dict[str, pd.DataFrame] | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    frames = frames or _build_frames()
    for name, df in frames.items():
        df.to_csv(folder / f"{name}.csv", index=False)


@pytest.fixture(scope="session")
def frames():
    return _build_frames()


@pytest.fixture(scope="session")
def dataset_dir(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data") / "ml-latest-small"
    write_dataset(folder)
    return folder


@pytest.fixture(scope="session")
def raw(dataset_dir) -> RawData:
    return load_raw(dataset_dir)


@pytest.fixture(scope="session")
def catalog(raw) -> Catalog:
    return Catalog.build(raw)


@pytest.fixture(scope="session")
def recommender(catalog, raw) -> Recommender:
    return Recommender(catalog, raw.ratings, knn_params={"k": 30, "shrinkage": 2.0})


@pytest.fixture()
def settings(tmp_path, dataset_dir) -> Settings:
    """Per-test data dir (own copy of the dataset) so persisted sessions/caches never leak between tests."""
    data_dir = tmp_path / "data"
    shutil.copytree(dataset_dir, data_dir / "ml-latest-small")
    return Settings(
        _env_file=None,
        data_dir=data_dir,
        reports_dir=tmp_path / "reports",
        anthropic_api_key=None,
        tmdb_api_key=None,
    )
