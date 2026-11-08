"""MOCK EMBEDDER - TEST-ONLY. THIS IS NOT A REAL MODEL.

It mimics the tiny part of the sentence-transformers API that app/rag/embeddings.py calls, using
hashed character trigrams. It is deterministic, so tests can verify plumbing: prefixes, normalisation,
batching, chunk storage, ownership scoping, deletion, failure handling.

It says NOTHING about retrieval quality, and certainly nothing about English or Hinglish semantics.
Real-model verification: scripts/verify_real_embeddings.py (run locally).
"""
import hashlib
import threading

import numpy as np


class MockSentenceTransformer:
    DIM = 384

    def __init__(self, block: threading.Event | None = None, fail: bool = False):
        self.block = block  # if set, encode() waits for it (simulates a slow model)
        self.fail = fail
        self.seen_texts: list[str] = []  # every text passed to encode(), prefixes included

    def get_embedding_dimension(self) -> int:
        return self.DIM

    def encode(self, inputs, batch_size=32, show_progress_bar=None, convert_to_numpy=True,
               normalize_embeddings=False, **kwargs):
        if self.block is not None:
            self.block.wait(timeout=60)
        if self.fail:
            raise RuntimeError("mock encode failure")
        texts = [inputs] if isinstance(inputs, str) else list(inputs)
        self.seen_texts.extend(texts)
        matrix = np.vstack([self._vector(t) for t in texts]).astype(np.float32)
        if normalize_embeddings:
            matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
        return matrix

    @classmethod
    def _vector(cls, text: str) -> np.ndarray:
        for prefix in ("query: ", "passage: "):  # keep prefixes out of the hashed content
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = " ".join(text.lower().split())
        vec = np.zeros(cls.DIM, dtype=np.float64)
        padded = f"  {text}  "
        for i in range(len(padded) - 2):
            digest = hashlib.md5(padded[i:i + 3].encode("utf-8")).digest()
            vec[int.from_bytes(digest[:4], "little") % cls.DIM] += 1.0
        return vec


def install(model: MockSentenceTransformer | None = None) -> MockSentenceTransformer:
    """Make app.rag.embeddings use the mock instead of loading a real model."""
    import app.rag.embeddings as embeddings

    model = model or MockSentenceTransformer()
    embeddings._embedder = None
    embeddings._load_model = lambda model_name: model
    return model
