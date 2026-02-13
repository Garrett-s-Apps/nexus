"""
ML Predictors — Cost estimation, quality prediction, escalation risk.

Three models trained from NEXUS operational data:

1. CostPredictor: directive text → estimated total cost
2. QualityPredictor: agent + task features → P(first-pass approval)
3. EscalationPredictor: agent + model + task → P(escalation needed)

All use scikit-learn with TF-IDF text features + numeric features.
Gracefully degrade when training data is insufficient.
"""

import logging
import time

import numpy as np

from src.ml.store import ml_store

logger = logging.getLogger("nexus.ml.predictor")

MIN_SAMPLES = 15
RETRAIN_INTERVAL = 3600

# Cached models
_cost_model: object | None = None
_quality_model: object | None = None
_escalation_model: object | None = None
_last_train: dict[str, float] = {}


def predict_cost(directive_text: str) -> dict:
    """Predict the total cost for a directive before execution.

    Returns predicted cost with confidence interval, or None if model isn't ready.
    """
    model = _get_model("cost_predictor", _train_cost_model)
    if model is None:
        return {"predicted": None, "reason": "insufficient training data"}

    try:
        # RandomForest can give per-tree predictions for confidence interval
        pipeline = model
        tfidf = pipeline.named_steps["tfidf"]
        regressor = pipeline.named_steps["reg"]

        X = tfidf.transform([directive_text])
        prediction = float(pipeline.predict([directive_text])[0])

        # Per-tree predictions for confidence interval
        tree_predictions = [tree.predict(X.toarray())[0] for tree in regressor.estimators_]
        std = float(np.std(tree_predictions))

        return {
            "predicted": round(max(0, prediction), 4),
            "std": round(std, 4),
            "confidence_low": round(max(0, prediction - 2 * std), 4),
            "confidence_high": round(prediction + 2 * std, 4),
        }
    except Exception as e:
        logger.warning("Cost prediction failed: %s", e)
        return {"predicted": None, "reason": str(e)}


def predict_quality(agent_id: str, task_description: str) -> dict:
    """Predict probability of first-pass quality approval.

    Returns P(success), P(defects > 0), and suggested action.
    """
    model = _get_model("quality_predictor", _train_quality_model)
    if model is None:
        return {"p_success": None, "reason": "insufficient training data"}

    try:
        # Features: agent_id + task text combined
        feature_text = f"[{agent_id}] {task_description}"
        proba = model.predict_proba([feature_text])[0]
        classes = list(model.classes_)

        p_success = float(proba[classes.index("clean")]) if "clean" in classes else 0.5
        p_defects = 1.0 - p_success

        suggestion = "proceed"
        if p_success < 0.5:
            suggestion = "consider_upgrade"
        elif p_success < 0.3:
            suggestion = "assign_reviewer"

        return {
            "p_success": round(p_success, 4),
            "p_defects": round(p_defects, 4),
            "suggestion": suggestion,
        }
    except Exception as e:
        logger.warning("Quality prediction failed: %s", e)
        return {"p_success": None, "reason": str(e)}


def predict_escalation(agent_id: str, model_tier: str, task_description: str) -> dict:
    """Predict probability that a task will need escalation.

    Returns P(escalation), P(circuit_trip), and suggested preemptive action.
    """
    model = _get_model("escalation_predictor", _train_escalation_model)
    if model is None:
        # Fall back to historical rate
        stats = ml_store.get_agent_reliability(agent_id)
        if stats["circuit_trips"] > 0:
            return {
                "p_escalation": None,
                "historical_trips": stats["circuit_trips"],
                "avg_recovery_sec": stats["avg_recovery_sec"],
                "suggestion": "monitor" if stats["circuit_trips"] < 3 else "pre_upgrade",
            }
        return {"p_escalation": None, "reason": "insufficient data"}

    try:
        feature_text = f"[{agent_id}:{model_tier}] {task_description}"
        proba = model.predict_proba([feature_text])[0]
        classes = list(model.classes_)

        p_escalation = float(proba[classes.index("escalated")]) if "escalated" in classes else 0.0

        suggestion = "proceed"
        if p_escalation > 0.5:
            suggestion = "pre_upgrade"
        elif p_escalation > 0.3:
            suggestion = "monitor"

        return {
            "p_escalation": round(p_escalation, 4),
            "suggestion": suggestion,
        }
    except Exception as e:
        logger.warning("Escalation prediction failed: %s", e)
        return {"p_escalation": None, "reason": str(e)}


def train_all(force: bool = False) -> dict:
    """Train all prediction models."""
    return {
        "cost": _train_cost_model(force),
        "quality": _train_quality_model(force),
        "escalation": _train_escalation_model(force),
    }


def _get_model(name: str, trainer):
    """Load or train a named model."""
    cache = {"cost_predictor": "_cost_model", "quality_predictor": "_quality_model",
             "escalation_predictor": "_escalation_model"}
    cached = globals().get(cache.get(name, ""))
    if cached is not None:
        return cached

    stored = ml_store.load_model(name)
    if stored is not None:
        globals()[cache[name]] = stored
        return stored

    result = trainer(force=True)
    if result.get("status") == "trained":
        return globals().get(cache.get(name, ""))
    return None


def _train_cost_model(force: bool = False) -> dict:
    """Train cost prediction: directive text → total cost."""
    global _cost_model
    name = "cost_predictor"

    if not force and (time.time() - _last_train.get(name, 0)) < RETRAIN_INTERVAL:
        return {"status": "skipped"}

    outcomes = ml_store.get_outcomes(limit=5000)
    # Group by directive to get total cost per directive
    directive_costs: dict[str, dict] = {}
    for o in outcomes:
        did = o["directive_id"]
        if did not in directive_costs:
            directive_costs[did] = {"text": o["task_description"], "cost": 0, "tasks": 0}
        directive_costs[did]["cost"] += o.get("cost_usd", 0)
        directive_costs[did]["tasks"] += 1

    samples = [v for v in directive_costs.values() if v["cost"] > 0]
    if len(samples) < MIN_SAMPLES:
        return {"status": "insufficient_data", "samples": len(samples)}

    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import Pipeline

        texts = [s["text"] for s in samples]
        costs = [s["cost"] for s in samples]

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=300, ngram_range=(1, 2))),
            ("reg", RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42)),
        ])
        pipeline.fit(texts, costs)
        _cost_model = pipeline
        _last_train[name] = time.time()

        ml_store.save_model(name, pipeline, metrics={"samples": len(samples)},
                           training_samples=len(samples))
        return {"status": "trained", "samples": len(samples)}
    except ImportError:
        return {"status": "error", "reason": "scikit-learn not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _train_quality_model(force: bool = False) -> dict:
    """Train quality prediction: agent + task → P(clean outcome)."""
    global _quality_model
    name = "quality_predictor"

    if not force and (time.time() - _last_train.get(name, 0)) < RETRAIN_INTERVAL:
        return {"status": "skipped"}

    outcomes = ml_store.get_outcomes(limit=5000)
    if len(outcomes) < MIN_SAMPLES:
        return {"status": "insufficient_data", "samples": len(outcomes)}

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import Pipeline

        texts = [f"[{o['agent_id']}] {o['task_description']}" for o in outcomes]
        labels = ["clean" if o["defect_count"] == 0 else "defective" for o in outcomes]

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=300, ngram_range=(1, 2))),
            ("clf", GradientBoostingClassifier(
                n_estimators=50, max_depth=5, random_state=42)),
        ])
        pipeline.fit(texts, labels)
        _quality_model = pipeline
        _last_train[name] = time.time()

        ml_store.save_model(name, pipeline, metrics={"samples": len(outcomes)},
                           training_samples=len(outcomes))
        return {"status": "trained", "samples": len(outcomes)}
    except ImportError:
        return {"status": "error", "reason": "scikit-learn not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _train_escalation_model(force: bool = False) -> dict:
    """Train escalation prediction: agent + model + task → P(escalation)."""
    global _escalation_model
    name = "escalation_predictor"

    if not force and (time.time() - _last_train.get(name, 0)) < RETRAIN_INTERVAL:
        return {"status": "skipped"}

    # Build training data from task outcomes + escalation events
    outcomes = ml_store.get_outcomes(limit=5000)
    if len(outcomes) < MIN_SAMPLES:
        return {"status": "insufficient_data", "samples": len(outcomes)}

    # Check which tasks had escalation events
    escalated_agents: set[str] = set()
    try:
        c = ml_store._db.cursor()
        rows = c.execute("SELECT DISTINCT agent_id FROM escalation_events").fetchall()
        escalated_agents = {r[0] for r in rows}
    except Exception:
        pass

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import Pipeline

        texts = [f"[{o['agent_id']}:{o['model']}] {o['task_description']}" for o in outcomes]
        # Label: escalated if agent has escalation history AND task failed
        labels = [
            "escalated" if (o["agent_id"] in escalated_agents and o["outcome"] != "complete")
            else "normal"
            for o in outcomes
        ]

        # Need at least 2 classes
        if len(set(labels)) < 2:
            return {"status": "insufficient_data", "reason": "only one class present"}

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=200)),
            ("clf", GradientBoostingClassifier(
                n_estimators=30, max_depth=4, random_state=42)),
        ])
        pipeline.fit(texts, labels)
        _escalation_model = pipeline
        _last_train[name] = time.time()

        ml_store.save_model(name, pipeline, metrics={"samples": len(outcomes)},
                           training_samples=len(outcomes))
        return {"status": "trained", "samples": len(outcomes)}
    except ImportError:
        return {"status": "error", "reason": "scikit-learn not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def predictor_status() -> dict:
    """Get status of all prediction models."""
    return {
        name: ml_store.get_model_info(name) or {"status": "not_trained"}
        for name in ["cost_predictor", "quality_predictor", "escalation_predictor"]
    }
