"""Item-item collaborative filtering on the user x movie rating matrix.

Similarity (default ``liked``): cosine between two movies' "who rated it >= 4" indicator vectors, so
only positive evidence says two movies go together. ``binary`` (rated at all) and ``adjusted``
(cosine on ratings centred by each user's mean) are also supported; the choice is made on a
validation split, see reports/evaluation.md.
Both are shrunk by co-rating support, ``sim * n / (n + lambda)``, so two movies that share only a
couple of raters cannot look identical, and only the top-K positive neighbours per movie are kept.

Prediction (item-based top-N, Deshpande & Karypis): every movie i the user has a signal w_i for
"votes" for its K most similar movies j with strength S[i,j] * w_i. The app uses w = +1 for liked
movies, +1.5 for "more like this" anchors and -1 for disliked movies.

    score_j = sum_i S[i,j] * w_i  /  (sum_i S[i,j] + damping)      over the user's items i

``support_j`` is the denominator's sum; candidates that no rated movie votes for are reported
as ``available=False`` so the hybrid can redistribute that component's weight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse


class ItemKNN:
    def __init__(
        self,
        ratings: pd.DataFrame,
        id_to_idx: dict[int, int],
        k: int = 100,
        shrinkage: float = 10.0,
        damping: float = 0.5,
        min_item_ratings: int = 2,
        chunk: int = 25,  # rows of the dense similarity block built at a time; small = low peak memory (identical result)
        similarity: str = "liked",
        like_threshold: float = 4.0,
    ) -> None:
        self.n_items = len(id_to_idx)
        self.k, self.shrinkage, self.damping = k, shrinkage, damping

        if similarity == "liked":  # only positive ratings count as evidence that two movies go together
            ratings = ratings[ratings["rating"] >= like_threshold]
        df = ratings[["userId", "movieId", "rating"]].copy()
        df["item"] = df["movieId"].map(id_to_idx)
        df = df.dropna(subset=["item"])
        df["item"] = df["item"].astype(int)
        users = df["userId"].astype("category")
        user_idx = users.cat.codes.to_numpy()
        n_users = len(users.cat.categories)

        user_mean = df.groupby("userId")["rating"].transform("mean").to_numpy()
        centred = (df["rating"].to_numpy() - user_mean).astype(np.float32)
        # a rating equal to the user's mean would be stored as 0 and vanish; nudge it so co-support survives
        centred[centred == 0] = 1e-3
        if similarity in ("binary", "liked"):  # implicit-feedback cosine on "rated" / "rated highly"
            centred = np.ones_like(centred)
        elif similarity != "adjusted":
            raise ValueError(f"unknown similarity: {similarity}")

        item_idx = df["item"].to_numpy()
        self.centred = sparse.csr_matrix((centred, (user_idx, item_idx)), shape=(n_users, self.n_items))
        binary = sparse.csr_matrix((np.ones_like(centred), (user_idx, item_idx)), shape=(n_users, self.n_items))

        counts = np.asarray(binary.sum(axis=0)).ravel()
        keep = counts >= min_item_ratings
        norms = np.sqrt(np.asarray(self.centred.multiply(self.centred).sum(axis=0)).ravel())
        norms[norms == 0] = 1.0
        scaled = self.centred @ sparse.diags(1.0 / norms)  # unit-length item columns
        scaled_t, binary_t = scaled.T.tocsr(), binary.T.tocsr()

        rows, cols, vals = [], [], []
        for start in range(0, self.n_items, chunk):
            stop = min(start + chunk, self.n_items)
            sims = (scaled_t[start:stop] @ scaled).toarray()
            co = (binary_t[start:stop] @ binary).toarray()
            sims *= co / (co + shrinkage)
            sims[~keep[start:stop], :] = 0
            sims[:, ~keep] = 0
            for r in range(stop - start):  # no self-similarity
                sims[r, start + r] = 0
            sims[sims < 0] = 0  # positive evidence only
            kk = min(k, self.n_items - 1)
            top = np.argpartition(-sims, kk, axis=1)[:, :kk]
            picked = np.take_along_axis(sims, top, axis=1)
            mask = picked > 0
            r_idx = np.repeat(np.arange(start, stop), kk).reshape(-1, kk)
            rows.append(r_idx[mask])
            cols.append(top[mask])
            vals.append(picked[mask])
        self.sim = sparse.csr_matrix(
            (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
            shape=(self.n_items, self.n_items),
            dtype=np.float32,
        )

    # ---------- prediction ----------
    def predict(self, signals: dict[int, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (score, support, available) over all items for the given signals."""
        if not signals:
            z = np.zeros(self.n_items)
            return z, z, np.zeros(self.n_items, dtype=bool)
        idx = np.fromiter(signals.keys(), dtype=int)
        w = np.zeros(self.n_items, dtype=np.float32)
        w[idx] = np.fromiter(signals.values(), dtype=np.float32)
        mask = np.zeros(self.n_items, dtype=np.float32)
        mask[idx] = 1.0
        numerator = self.sim.T @ w
        support = self.sim.T @ mask
        score = numerator / (support + self.damping)
        return score, support, support > 1e-6

    def top_neighbours(self, candidate: int, signals: dict[int, float], limit: int = 3) -> list[tuple[int, float]]:
        """The user's own items that most influenced this candidate (for explanations)."""
        if not hasattr(self, "_sim_csc"):
            self._sim_csc = self.sim.tocsc()
        col = self._sim_csc.getcol(candidate)
        pairs = [(int(i), float(s)) for i, s in zip(col.indices, col.data) if i in signals and signals[i] > 0]
        return sorted(pairs, key=lambda p: -p[1] * signals[p[0]])[:limit]
