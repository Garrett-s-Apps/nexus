"""
Feedback Loop — Closes the gap between execution and learning.

Called after every task completion/failure to record the outcome and
trigger model retraining when sufficient new data accumulates.

Also handles directive-level feedback: when a directive completes,
store its embedding + total cost for similarity search.
"""

import logging

from src.ml.store import ml_store

logger = logging.getLogger("nexus.ml.feedback")

_outcomes_since_train = 0
RETRAIN_THRESHOLD = 10  # retrain after N new outcomes


def record_task_outcome(
    directive_id: str,
    task_id: str,
    agent_id: str,
    task_description: str,
    outcome: str,
    specialty: str = "",
    cost_usd: float = 0,
    duration_sec: float = 0,
    defect_count: int = 0,
    qa_cycles: int = 0,
    model: str = "",
):
    """Record a completed/failed task for ML training.

    Call this after every task_board status change to complete or failed.
    """
    global _outcomes_since_train

    ml_store.record_outcome(
        directive_id=directive_id,
        task_id=task_id,
        agent_id=agent_id,
        task_description=task_description,
        outcome=outcome,
        specialty=specialty,
        cost_usd=cost_usd,
        duration_sec=duration_sec,
        defect_count=defect_count,
        qa_cycles=qa_cycles,
        model=model,
    )

    # Ingest into RAG knowledge base
    try:
        from src.ml.rag import ingest_task_outcome
        ingest_task_outcome(
            directive_id=directive_id, task_id=task_id,
            agent_id=agent_id, description=task_description,
            outcome=outcome, defect_count=defect_count, cost_usd=cost_usd,
        )
    except Exception:
        pass  # RAG ingestion is best-effort

    _outcomes_since_train += 1
    logger.debug(
        "Recorded outcome: %s by %s → %s (cost=$%.4f, defects=%d)",
        task_id, agent_id, outcome, cost_usd, defect_count,
    )


def record_directive_complete(
    directive_id: str,
    directive_text: str,
    total_cost: float = 0,
    total_tasks: int = 0,
    total_duration_sec: float = 0,
    outcome: str = "complete",
):
    """Record a completed directive with its embedding for similarity search.

    Call this when a directive reaches 'complete' status.
    """
    try:
        from src.ml.embeddings import embedding_to_bytes, encode

        embedding = encode(directive_text)
        ml_store.store_embedding(
            directive_id=directive_id,
            directive_text=directive_text,
            embedding=embedding_to_bytes(embedding),
            total_cost=total_cost,
            total_tasks=total_tasks,
            total_duration_sec=total_duration_sec,
            outcome=outcome,
        )
        logger.info("Stored directive embedding for %s", directive_id)
    except Exception as e:
        logger.warning("Failed to store directive embedding: %s", e)


def find_similar_directives(directive_text: str, top_k: int = 5) -> list[dict]:
    """Find past directives similar to the given text.

    Returns list of similar directives with their cost/outcome history.
    """
    try:
        from src.ml.embeddings import encode, find_similar

        query_embedding = encode(directive_text)
        stored = ml_store.get_all_embeddings()

        if not stored:
            return []

        return find_similar(query_embedding, stored, top_k=top_k)
    except Exception as e:
        logger.warning("Similarity search failed: %s", e)
        return []


def record_circuit_event(
    agent_id: str,
    event_type: str,
    failure_count: int = 0,
    model: str = "",
    task_type: str = "",
    recovery_time_sec: float = 0,
):
    """Persist a circuit breaker event for reliability modeling."""
    ml_store.record_circuit_event(
        agent_id=agent_id,
        event_type=event_type,
        failure_count=failure_count,
        model=model,
        task_type=task_type,
        recovery_time_sec=recovery_time_sec,
    )


def record_escalation(
    agent_id: str,
    from_model: str,
    to_model: str | None = None,
    reason: str = "",
    task_type: str = "",
):
    """Persist an escalation event for escalation prediction."""
    ml_store.record_escalation(
        agent_id=agent_id,
        from_model=from_model,
        to_model=to_model,
        reason=reason,
        task_type=task_type,
    )


def get_learning_status() -> dict:
    """Get overall ML learning system status."""
    from src.ml.predictor import predictor_status
    from src.ml.rag import rag_status
    from src.ml.router import router_status

    data = ml_store.get_training_data_count()
    return {
        "data": data,
        "router": router_status(),
        "predictors": predictor_status(),
        "rag": rag_status(),
        "outcomes_since_retrain": _outcomes_since_train,
        "retrain_threshold": RETRAIN_THRESHOLD,
    }


def should_retrain() -> bool:
    """Check if enough outcomes have accumulated to warrant retraining."""
    return _outcomes_since_train >= RETRAIN_THRESHOLD


def do_retrain():
    """Retrain all models with new data. Called by BackgroundScheduler."""
    global _outcomes_since_train

    if not should_retrain():
        return

    logger.info("Triggering ML model retrain (%d new outcomes)", _outcomes_since_train)
    _outcomes_since_train = 0

    try:
        from src.ml.predictor import train_all
        from src.ml.router import train

        router_result = train(force=True)
        predictor_results = train_all(force=True)
        logger.info(
            "Retrain complete — router: %s, predictors: %s",
            router_result.get("status"), {k: v.get("status") for k, v in predictor_results.items()},
        )
    except Exception as e:
        logger.error("Retrain failed: %s", e)


def _trigger_retrain():
    """Legacy wrapper — kept for backward compatibility."""
    do_retrain()
