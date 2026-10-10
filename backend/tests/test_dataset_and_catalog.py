import io
import zipfile

import pandas as pd
import pytest

from app.catalog import Catalog, normalize_text, parse_title
from app.dataset import DatasetError, _safe_extract, load_raw, validate_folder

from .conftest import write_dataset


# ------------------------------------------------------------------ dataset loading
def test_loads_valid_dataset(raw):
    assert {"movieId", "title", "genres"} <= set(raw.movies.columns)
    assert len(raw.ratings) > 0 and raw.ratings["rating"].between(0.5, 5).all()


def test_missing_folder_gives_actionable_error(tmp_path):
    with pytest.raises(DatasetError, match="setup_data"):
        validate_folder(tmp_path / "nope")


def test_missing_file_is_reported(tmp_path, frames):
    write_dataset(tmp_path / "d", frames)
    (tmp_path / "d" / "links.csv").unlink()
    with pytest.raises(DatasetError, match="links.csv"):
        load_raw(tmp_path / "d")


def test_missing_column_is_reported(tmp_path, frames):
    write_dataset(tmp_path / "d", {**frames, "ratings": frames["ratings"].drop(columns=["timestamp"])})
    with pytest.raises(DatasetError, match="timestamp"):
        load_raw(tmp_path / "d")


def test_out_of_range_ratings_rejected(tmp_path, frames):
    bad = frames["ratings"].copy()
    bad.loc[0, "rating"] = 9.0
    write_dataset(tmp_path / "d", {**frames, "ratings": bad})
    with pytest.raises(DatasetError, match="outside"):
        load_raw(tmp_path / "d")


def test_malformed_values_rejected(tmp_path, frames):
    write_dataset(tmp_path / "d", frames)
    path = tmp_path / "d" / "ratings.csv"
    path.write_text(path.read_text().replace("2000", "abc", 1))
    with pytest.raises(DatasetError):
        load_raw(tmp_path / "d")


def test_duplicate_movie_ids_rejected(tmp_path, frames):
    dup = pd.concat([frames["movies"], frames["movies"].iloc[[0]]])
    write_dataset(tmp_path / "d", {**frames, "movies": dup})
    with pytest.raises(DatasetError, match="duplicate"):
        load_raw(tmp_path / "d")


def test_zip_slip_is_refused(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf, pytest.raises(DatasetError, match="unsafe"):
        _safe_extract(zf, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


# ------------------------------------------------------------------ catalog
def test_parse_title_handles_articles_years_and_aliases():
    assert parse_title("Dark Knight, The (2008)") == ("The Dark Knight", 2008, [])
    title, year, aliases = parse_title("City of Lost Children, The (Cité des enfants perdus, La) (1995)")
    assert title == "The City of Lost Children" and year == 1995 and aliases == ["La Cité des enfants perdus"]


def test_no_genres_movie_has_empty_genres(catalog):
    assert catalog.get(99).genres == ()


def test_imax_is_not_a_genre(raw):
    movies = pd.DataFrame([{"movieId": 1, "title": "X (2000)", "genres": "Sci-Fi|IMAX"}])
    cat = Catalog.build(type(raw)(movies, raw.ratings, raw.tags, raw.links))
    assert cat.get(1).genres == ("Sci-Fi",) and "IMAX" not in cat.all_genres


def test_stats_use_only_given_ratings(raw):
    train = raw.ratings.iloc[:50]
    cat = Catalog.build(raw, train)
    assert sum(m.n_ratings for m in cat.movies) == 50


def test_resolve_title_exact_fuzzy_and_unknown(catalog):
    assert catalog.resolve_title("alpha story").movie_id == 1
    assert catalog.resolve_title("Alpha Storey").movie_id == 1  # typo
    assert catalog.resolve_title("Totally Made Up Movie") is None
    assert catalog.resolve_title("") is None


def test_normalize_text_strips_accents_and_punctuation():
    assert normalize_text("Amélie!") == "amelie"


def test_find_titles_in_text(catalog):
    found = catalog.find_titles_in_text("I loved Alpha Story and Bravo Story")
    assert {m.movie_id for m in found} == {1, 2}


def test_download_retries_a_flaky_network_then_succeeds(tmp_path, dataset_dir, monkeypatch):
    import io
    import zipfile

    import httpx

    from app import dataset

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in dataset_dir.iterdir():
            z.write(f, f"ml-latest-small/{f.name}")
    calls = []

    def flaky_get(url, **kw):
        calls.append(url)
        if len(calls) < 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, content=buf.getvalue(), request=httpx.Request("GET", url))

    monkeypatch.setattr(dataset.httpx, "get", flaky_get)
    folder = dataset.download_dataset(tmp_path, retry_wait=0)
    assert len(calls) == 3 and (folder / "movies.csv").is_file()


def test_download_gives_up_with_a_clear_message(tmp_path, monkeypatch):
    import httpx
    import pytest

    from app import dataset

    monkeypatch.setattr(dataset.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    with pytest.raises(dataset.DatasetError, match="Could not download"):
        dataset.download_dataset(tmp_path, attempts=2, retry_wait=0)
