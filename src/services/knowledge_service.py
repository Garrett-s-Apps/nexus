"""SSoT service for RAG knowledge base."""

from dataclasses import dataclass, field

from src.ml.rag import build_rag_context, rag_status


@dataclass
class KnowledgeStatus:
    total_chunks: int = 0
    chunks_by_type: dict = field(default_factory=dict)
    ready: bool = False


class KnowledgeService:
    """Unified access to RAG knowledge base."""

    def get_status(self) -> KnowledgeStatus:
        """Get knowledge base health."""
        status = rag_status()
        return KnowledgeStatus(
            total_chunks=status.get("total_chunks", 0),
            chunks_by_type=status.get("by_type", {}),
            ready=status.get("ready", False),
        )

    def get_context(self, query: str, exclude_source_ids: set[str] | None = None) -> str:
        """Get RAG context for a query."""
        return build_rag_context(query, exclude_source_ids=exclude_source_ids)


knowledge_service = KnowledgeService()
