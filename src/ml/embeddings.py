"""
Directive Embedding Engine — Semantic similarity for past directives.

Uses sentence-transformers (all-MiniLM-L6-v2) to embed directive text,
enabling "we did something similar before" retrieval. Falls back to
TF-IDF if sentence-transformers isn't available.

Embeddings are stored in ml.db and retrieved via cosine similarity.
"""

import asyncio
import logging
import pickle
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

logger = logging.getLogger("nexus.ml.embeddings")

_model: Any = None
_fallback_vectorizer: Any = None
_embedding_dim: int = 384  # all-MiniLM-L6-v2 output dim
_embedding_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embedding")


def _get_model():
    """Lazy-load the sentence transformer model."""
    global _model, _embedding_dim
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _embedding_dim = 384
        logger.info("Loaded sentence-transformers model (all-MiniLM-L6-v2)")
        return _model
    except ImportError:
        logger.warning("sentence-transformers not installed, using TF-IDF fallback")
        return None


def _get_fallback_vectorizer():
    """TF-IDF fallback when sentence-transformers isn't available."""
    global _fallback_vectorizer, _embedding_dim
    if _fallback_vectorizer is not None:
        return _fallback_vectorizer
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        _fallback_vectorizer = TfidfVectorizer(max_features=384)
        _embedding_dim = 384
        return _fallback_vectorizer
    except ImportError:
        logger.error("Neither sentence-transformers nor scikit-learn available")
        return None


def encode(text: str) -> np.ndarray:
    """Encode a single text string into a dense embedding vector."""
    model = _get_model()
    if model is not None:
        embedding = model.encode(text, show_progress_bar=False)
        return np.array(embedding, dtype=np.float32)

    # TF-IDF fallback — returns sparse, we densify + pad/truncate to fixed dim
    vectorizer = _get_fallback_vectorizer()
    if vectorizer is not None:
        try:
            vec = vectorizer.transform([text]).toarray()[0]
        except Exception:
            # Vectorizer not fitted yet — fit on this text and return
            vec = vectorizer.fit_transform([text]).toarray()[0]
        result = np.zeros(_embedding_dim, dtype=np.float32)
        result[:min(len(vec), _embedding_dim)] = vec[:_embedding_dim]
        return result

    # Last resort: hash-based pseudo-embedding
    return _hash_embedding(text)


def encode_batch(texts: list[str]) -> np.ndarray:
    """Encode multiple texts into embedding vectors."""
    model = _get_model()
    if model is not None:
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
        return np.array(embeddings, dtype=np.float32)

    return np.array([encode(t) for t in texts], dtype=np.float32)


async def encode_async(text: str) -> np.ndarray:
    """Async encode a single text string into a dense embedding vector.

    Runs the encoding in a thread pool to avoid blocking the event loop.
    Prevents 50-100ms blocking periods during sentence-transformer inference.
    """
    loop = asyncio.get_event_loop()

    model = _get_model()
    if model is not None:
        # Run model.encode in thread pool
        embedding = await loop.run_in_executor(
            _embedding_executor,
            lambda: model.encode(text, show_progress_bar=False),
        )
        return np.array(embedding, dtype=np.float32)

    # TF-IDF fallback — returns sparse, we densify + pad/truncate to fixed dim
    vectorizer = _get_fallback_vectorizer()
    if vectorizer is not None:
        # Run vectorizer in thread pool
        def _vectorize(txt: str) -> np.ndarray:
            try:
                vec = vectorizer.transform([txt]).toarray()[0]
            except Exception:
                # Vectorizer not fitted yet — fit on this text and return
                vec = vectorizer.fit_transform([txt]).toarray()[0]
            result = np.zeros(_embedding_dim, dtype=np.float32)
            result[:min(len(vec), _embedding_dim)] = vec[:_embedding_dim]
            return result

        return await loop.run_in_executor(_embedding_executor, _vectorize, text)

    # Last resort: hash-based pseudo-embedding
    return _hash_embedding(text)


async def encode_batch_async(texts: list[str]) -> np.ndarray:
    """Async encode multiple texts into embedding vectors.

    Runs batch encoding in thread pool to prevent event loop blocking.
    """
    loop = asyncio.get_event_loop()

    model = _get_model()
    if model is not None:
        # Run model.encode in thread pool
        embeddings = await loop.run_in_executor(
            _embedding_executor,
            lambda: model.encode(texts, show_progress_bar=False, batch_size=32),
        )
        return np.array(embeddings, dtype=np.float32)

    # Fallback: encode each text async
    results = await asyncio.gather(*[encode_async(t) for t in texts])
    return np.array(results, dtype=np.float32)


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Serialize an embedding for SQLite storage."""
    return pickle.dumps(embedding)


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserialize an embedding from SQLite storage."""
    result: np.ndarray = pickle.loads(data)  # noqa: S301
    return result


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def find_similar(
    query_embedding: np.ndarray,
    stored_embeddings: list[dict],
    top_k: int = 5,
    threshold: float = 0.3,
) -> list[dict]:
    """Find the most similar past directives by cosine similarity.

    Args:
        query_embedding: The embedding vector to compare against.
        stored_embeddings: List of dicts with 'embedding' (bytes), 'directive_id',
                          'directive_text', 'total_cost', etc.
        top_k: Number of results to return.
        threshold: Minimum similarity score to include.

    Returns:
        List of dicts with similarity scores, sorted by relevance.
    """
    results = []
    for item in stored_embeddings:
        stored_vec = bytes_to_embedding(item["embedding"])
        score = cosine_similarity(query_embedding, stored_vec)
        if score >= threshold:
            results.append({
                "directive_id": item["directive_id"],
                "directive_text": item["directive_text"],
                "similarity": round(score, 4),
                "total_cost": item.get("total_cost", 0),
                "total_tasks": item.get("total_tasks", 0),
                "total_duration_sec": item.get("total_duration_sec", 0),
                "outcome": item.get("outcome", ""),
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def _hash_embedding(text: str) -> np.ndarray:
    """Deterministic pseudo-embedding from text hash. Last-resort fallback."""
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    # Expand hash bytes into a fixed-dim vector
    rng = np.random.RandomState(int.from_bytes(h[:4], "big"))  # noqa: NPY002
    return rng.randn(_embedding_dim).astype(np.float32)
