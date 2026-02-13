"""
ML Agent Router — Replaces keyword-based _match() with learned routing.

Training data comes from task_outcomes: which agent was assigned to which
task description, and whether the outcome was successful.

Uses TF-IDF + RandomForestClassifier when enough data exists (>=20 samples).
Falls back to keyword routing when training data is insufficient.

The model retrains automatically when new outcome data arrives.
"""

import logging
import time

import numpy as np

from src.ml.store import ml_store

logger = logging.getLogger("nexus.ml.router")

MODEL_NAME = "agent_router"
MIN_TRAINING_SAMPLES = 20
RETRAIN_INTERVAL = 3600  # retrain at most once per hour

_last_train_time: float = 0
_router_pipeline: object | None = None
_label_classes: list[str] = []


def predict_best_agent(
    task_description: str,
    available_agents: list[str],
) -> str | None:
    """Predict the best agent for a task based on historical outcomes.

    Returns the agent_id with highest predicted success probability,
    or None if the ML model isn't ready (caller should fall back to keywords).
    """
    pipeline = _get_or_train_pipeline()
    if pipeline is None:
        return None

    try:
        probas = pipeline.predict_proba([task_description])[0]
        # Build agent -> probability map
        agent_scores: dict[str, float] = {}
        for i, agent_id in enumerate(_label_classes):
            if agent_id in available_agents:
                agent_scores[agent_id] = probas[i]

        if not agent_scores:
            return None

        best = max(agent_scores, key=agent_scores.get)  # type: ignore[arg-type]
        confidence = agent_scores[best]
        logger.debug("ML router: %s (%.2f confidence) for: %s", best, confidence, task_description[:60])
        return best
    except Exception as e:
        logger.warning("ML router prediction failed: %s", e)
        return None


def get_agent_scores(task_description: str) -> dict[str, float]:
    """Get predicted success probability for all agents given a task."""
    pipeline = _get_or_train_pipeline()
    if pipeline is None:
        return {}

    try:
        probas = pipeline.predict_proba([task_description])[0]
        return {agent: round(float(prob), 4) for agent, prob in zip(_label_classes, probas, strict=False)}
    except Exception:
        return {}


def train(force: bool = False) -> dict:
    """Train (or retrain) the agent routing model from task_outcomes.

    Returns training metrics or an error message.
    """
    global _last_train_time, _router_pipeline, _label_classes

    if not force and (time.time() - _last_train_time) < RETRAIN_INTERVAL:
        return {"status": "skipped", "reason": "retrain interval not elapsed"}

    outcomes = ml_store.get_outcomes(limit=5000)
    # Only train on successful outcomes — learn what works
    successful = [o for o in outcomes if o["outcome"] == "complete"]

    if len(successful) < MIN_TRAINING_SAMPLES:
        return {
            "status": "insufficient_data",
            "samples": len(successful),
            "required": MIN_TRAINING_SAMPLES,
        }

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.model_selection import cross_val_score
        from sklearn.pipeline import Pipeline

        texts = [o["task_description"] for o in successful]
        labels = [o["agent_id"] for o in successful]

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=500, ngram_range=(1, 2))),
            ("clf", RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                class_weight="balanced",
            )),
        ])

        pipeline.fit(texts, labels)
        _label_classes = list(pipeline.classes_)

        # Cross-validation score (if enough data)
        cv_score = 0.0
        if len(successful) >= 50:
            scores = cross_val_score(pipeline, texts, labels, cv=min(5, len(set(labels))))
            cv_score = float(np.mean(scores))

        _router_pipeline = pipeline
        _last_train_time = time.time()

        metrics = {
            "accuracy_cv": round(cv_score, 4),
            "training_samples": len(successful),
            "unique_agents": len(set(labels)),
            "classes": _label_classes,
        }

        # Persist the trained model
        ml_store.save_model(MODEL_NAME, pipeline, metrics=metrics,
                           training_samples=len(successful))

        logger.info("Agent router trained: %d samples, %.2f CV accuracy", len(successful), cv_score)
        return {"status": "trained", **metrics}

    except ImportError:
        logger.warning("scikit-learn not installed, ML router unavailable")
        return {"status": "error", "reason": "scikit-learn not installed"}
    except Exception as e:
        logger.error("Router training failed: %s", e)
        return {"status": "error", "reason": str(e)}


def _get_or_train_pipeline():
    """Load cached pipeline, or load from disk, or train fresh."""
    global _router_pipeline, _label_classes, _last_train_time

    if _router_pipeline is not None:
        return _router_pipeline

    # Try loading from persistent store
    stored = ml_store.load_model(MODEL_NAME)
    if stored is not None:
        try:
            _router_pipeline = stored
            _label_classes = list(stored.classes_)
            _last_train_time = time.time()
            logger.info("Loaded agent router from ml.db (classes: %s)", _label_classes)
            return _router_pipeline
        except Exception as e:
            logger.warning("Failed to load stored router: %s", e)

    # Train fresh
    result = train(force=True)
    if result.get("status") == "trained":
        return _router_pipeline

    return None


def router_status() -> dict:
    """Get current status of the ML router."""
    info = ml_store.get_model_info(MODEL_NAME)
    data_count = ml_store.get_training_data_count()
    return {
        "model_loaded": _router_pipeline is not None,
        "model_info": info,
        "training_data": data_count,
        "min_samples_required": MIN_TRAINING_SAMPLES,
        "ready": _router_pipeline is not None,
    }
