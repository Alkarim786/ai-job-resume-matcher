"""Embedders behind one interface: embed(list[str]) -> (n, 384) L2-normalised float32 array."""

import re
import zlib
from functools import lru_cache
from typing import Protocol

import numpy as np

DIM = 384
_TOKEN = re.compile(r"[a-z0-9+#./]+")
_STOP = frozenset(
    "a an the and or of to in for with on at by as is are was were be been this that these those from it its our we you your their "
    "will can may must should have has had not no but if then than into over under about across per via using use used".split()
)


class Embedder(Protocol):
    name: str
    # Cosine range that maps onto the 0..1 "semantic score". Fixed a priori per model, never tuned on the eval set.
    calibration: tuple[float, float]

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    """Signed feature-hashing of unigrams+bigrams into 384 dims, sublinear tf. No model download, deterministic.

    A lexical baseline: it measures word overlap, not meaning. Used for tests and as an offline fallback.
    """

    name = "hash"
    calibration = (0.0, 0.45)

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
            feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
            counts: dict[str, int] = {}
            for f in feats:
                counts[f] = counts.get(f, 0) + 1
            for f, c in counts.items():
                h = zlib.crc32(f.encode())
                out[i, h % DIM] += (1.0 if (h >> 16) & 1 else -1.0) * (1.0 + np.log(c))
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


class MiniLMEmbedder:
    """sentence-transformers/all-MiniLM-L6-v2 (384-d). Lazy-loaded; weights are downloaded on first use."""

    name = "minilm"
    calibration = (0.10, 0.60)

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device="cpu")

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False).astype(np.float32)


@lru_cache
def get_embedder(name: str) -> Embedder:
    if name == "minilm":
        return MiniLMEmbedder()
    if name == "hash":
        return HashEmbedder()
    raise ValueError(f"unknown embedder {name!r}")


def cosine_to_unit(cos: float, calibration: tuple[float, float]) -> float:
    lo, hi = calibration
    return float(min(1.0, max(0.0, (cos - lo) / (hi - lo))))
