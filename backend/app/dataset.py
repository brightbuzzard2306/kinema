"""MovieLens download, safe extraction and schema validation.

Nothing here fabricates data: if the files are missing or malformed we raise
``DatasetError`` with a message that explains how to fix it.
"""

from __future__ import annotations

import io
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd

DATASET_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
DATASET_FOLDER = "ml-latest-small"

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "movies.csv": ["movieId", "title", "genres"],
    "ratings.csv": ["userId", "movieId", "rating", "timestamp"],
    "tags.csv": ["userId", "movieId", "tag", "timestamp"],
    "links.csv": ["movieId", "imdbId", "tmdbId"],
}


class DatasetError(RuntimeError):
    """Raised when the dataset is missing, incomplete or malformed."""


@dataclass(frozen=True)
class RawData:
    movies: pd.DataFrame
    ratings: pd.DataFrame
    tags: pd.DataFrame
    links: pd.DataFrame


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract while rejecting any member that would escape ``destination`` (zip-slip)."""
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if destination != target and destination not in target.parents:
            raise DatasetError(f"Refusing to extract unsafe path from archive: {member.filename}")
    archive.extractall(destination)


def download_dataset(data_dir: Path, url: str = DATASET_URL, timeout: float = 60.0, attempts: int = 4, retry_wait: float = 3.0) -> Path:
    """Download and extract MovieLens ml-latest-small into ``data_dir``; returns the folder."""
    data_dir.mkdir(parents=True, exist_ok=True)
    response = None
    for attempt in range(1, attempts + 1):  # build servers have flaky networks: retry before giving up
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            break
        except httpx.HTTPError as exc:
            if attempt == attempts:
                raise DatasetError(
                    f"Could not download MovieLens from {url} ({exc.__class__.__name__}). "
                    f"Download it manually and unzip it into {data_dir}/{DATASET_FOLDER}/."
                ) from exc
            time.sleep(retry_wait * attempt)
    assert response is not None
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            _safe_extract(archive, data_dir)
    except zipfile.BadZipFile as exc:
        raise DatasetError("Downloaded file is not a valid zip archive.") from exc
    folder = data_dir / DATASET_FOLDER
    validate_folder(folder)
    return folder


def validate_folder(folder: Path) -> None:
    """Check that every expected file exists and has the expected columns."""
    if not folder.is_dir():
        raise DatasetError(
            f"Dataset folder not found: {folder}. Run `python -m scripts.setup_data` from backend/."
        )
    for filename, columns in REQUIRED_COLUMNS.items():
        path = folder / filename
        if not path.is_file():
            raise DatasetError(f"Missing dataset file: {path}")
        try:
            header = pd.read_csv(path, nrows=0).columns.tolist()
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
            raise DatasetError(f"Could not parse {path.name}: {exc}") from exc
        missing = [c for c in columns if c not in header]
        if missing:
            raise DatasetError(f"{filename} is missing required columns: {missing}")


def load_raw(folder: Path) -> RawData:
    """Load and type-check the four MovieLens tables."""
    validate_folder(folder)
    try:
        movies = pd.read_csv(folder / "movies.csv", dtype={"movieId": "int64"})
        ratings = pd.read_csv(
            folder / "ratings.csv",
            dtype={"userId": "int64", "movieId": "int64", "rating": "float64", "timestamp": "int64"},
        )
        tags = pd.read_csv(folder / "tags.csv", dtype={"userId": "int64", "movieId": "int64"})
        links = pd.read_csv(folder / "links.csv", dtype={"movieId": "int64"})
    except (ValueError, pd.errors.ParserError) as exc:
        raise DatasetError(f"Dataset contains malformed values: {exc}") from exc

    if movies.empty or ratings.empty:
        raise DatasetError("movies.csv or ratings.csv is empty.")
    if not ratings["rating"].between(0.5, 5.0).all():
        raise DatasetError("ratings.csv contains values outside the 0.5-5.0 range.")
    if movies["movieId"].duplicated().any():
        raise DatasetError("movies.csv contains duplicate movieId values.")

    ratings = ratings[ratings["movieId"].isin(movies["movieId"])].reset_index(drop=True)
    tags = tags[tags["movieId"].isin(movies["movieId"])].reset_index(drop=True)
    return RawData(movies=movies, ratings=ratings, tags=tags, links=links)
