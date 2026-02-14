"""NEXUS Orchestrator — LangGraph-primary orchestration (ARCH-001).

Primary path: LangGraph graph (graph.py) via OrchestrationFacade (engine.py)
Fast path:    Executor (executor.py) for lightweight directives
Meta path:    MetaOrchestrator (meta_orchestrator.py) for multi-service directives (ARCH-014)
"""
__all__ = ["engine", "executor", "graph", "meta_orchestrator", "state"]
