"""Content-based filtering: TF-IDF over genres, tags and title words + cosine similarity.

Each movie becomes one sparse vector made of three independently L2-normalised blocks
(genres, tags, title words). Normalising each block *before* weighting stops the block
with the most columns (tags) from drowning out the others; the weights below say how
much each block contributes to the final cosine similarity.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse import linalg as splinalg
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from ..catalog import Catalog

BLOCK_WEIGHTS = {"genres": 1.0, "tags": 0.6, "title": 0.25}


class ContentModel:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        genre_docs = [" ".join(g.replace("-", "").lower() for g in m.genres) or "nogenre" for m in catalog.movies]
        self.genre_vec = TfidfVectorizer(token_pattern=r"[a-z]+", lowercase=True)
        genre_block = self.genre_vec.fit_transform(genre_docs)

        # Tags: each distinct tag phrase is one token (so "time travel" stays together).
        self.tag_vec = TfidfVectorizer(
            tokenizer=lambda s: [t for t in s.split(" | ") if t],
            token_pattern=None,
            lowercase=False,
            min_df=2,
            sublinear_tf=True,
        )
        try:
            tag_block = self.tag_vec.fit_transform(catalog.tags_text)
        except ValueError:  # empty vocabulary (no tags)
            tag_block = sparse.csr_matrix((len(catalog), 0))

        self.title_vec = TfidfVectorizer(stop_words="english", min_df=2, token_pattern=r"[a-z]{3,}")
        try:
            title_block = self.title_vec.fit_transform([m.title.lower() for m in catalog.movies])
        except ValueError:
            title_block = sparse.csr_matrix((len(catalog), 0))

        self._blocks = {
            "genres": normalize(genre_block) * BLOCK_WEIGHTS["genres"],
            "tags": normalize(tag_block) * BLOCK_WEIGHTS["tags"],
            "title": normalize(title_block) * BLOCK_WEIGHTS["title"],
        }
        self.matrix = normalize(sparse.hstack(list(self._blocks.values()), format="csr"))
        self._genre_cols = genre_block.shape[1]
        self._n_cols = self.matrix.shape[1]
        self._genre_vocab = self.genre_vec.vocabulary_

    # ---------- profile building (Rocchio-style) ----------
    def genre_query(self, genres: list[str]) -> sparse.csr_matrix:
        """A query vector living in the genre block of the feature space."""
        row = np.zeros(self._n_cols, dtype=np.float32)
        idf = self.genre_vec.idf_
        for g in genres:
            col = self._genre_vocab.get(g.replace("-", "").lower())
            if col is not None:
                row[col] = idf[col]
        if not row.any():
            return sparse.csr_matrix((1, self._n_cols))
        return normalize(sparse.csr_matrix(row)) * BLOCK_WEIGHTS["genres"]

    def profile_vector(
        self,
        positive: dict[int, float],
        negative: dict[int, float],
        genres: list[str],
        genre_weight: float = 0.6,
        negative_weight: float = 0.5,
    ) -> sparse.csr_matrix | None:
        """q = centroid(liked) + a*genre_query - b*centroid(disliked).  ``None`` if no signal."""
        q = sparse.csr_matrix((1, self._n_cols))
        has_signal = False
        if positive:
            idx = np.fromiter(positive.keys(), dtype=int)
            w = np.fromiter(positive.values(), dtype=float)
            q = q + sparse.csr_matrix(w / w.sum()) @ self.matrix[idx]
            has_signal = True
        if genres:
            gq = self.genre_query(genres)
            if gq.nnz:
                q = q + genre_weight * gq
                has_signal = True
        if negative and has_signal:
            idx = np.fromiter(negative.keys(), dtype=int)
            w = np.fromiter(negative.values(), dtype=float)
            q = q - negative_weight * (sparse.csr_matrix(w / w.sum()) @ self.matrix[idx])
        return q if has_signal else None

    def scores(self, query: sparse.csr_matrix) -> np.ndarray:
        """Cosine similarity of the query to every movie (rows are unit length)."""
        norm = splinalg.norm(query)
        if norm == 0:
            return np.zeros(len(self.catalog))
        return np.asarray((self.matrix @ (query.T / norm)).todense()).ravel()

    def similar_to(self, idx: int) -> np.ndarray:
        return np.asarray((self.matrix @ self.matrix[idx].T).todense()).ravel()

    # ---------- explanation helpers ----------
    def shared_features(self, idx_a: int, idx_b: int, max_tags: int = 3) -> dict[str, list[str]]:
        """Actual genres/tags two movies have in common (used to ground explanations)."""
        a, b = self.catalog.movies[idx_a], self.catalog.movies[idx_b]
        genres = [g for g in a.genres if g in b.genres]
        tags_b = set(self.catalog.tags_of(idx_b, limit=50))
        tags = [t for t in self.catalog.tags_of(idx_a, limit=50) if t in tags_b][:max_tags]
        return {"genres": genres, "tags": tags}
