# Spec: RAG Search & Semantic Debug API Endpoints

**Version:** 1.0
**Date:** 2026-02-17
**Status:** Implemented
**Affects:** nexus (server), nexus-plugin (consumer)

## Summary

Three new API endpoints expose NEXUS's RAG knowledge base and semantic debug capabilities to external consumers (primarily the nexus-plugin's `debug-investigate` and `semantic-search` skills).

## Motivation

NEXUS already has a full RAG pipeline (`src/ml/rag.py`) with cosine similarity search, domain pre-filtering, chunk-type weighting, and recency boosting. However, this was only accessible internally via Python imports. The nexus-plugin needs HTTP access to power its new Cursor-style skills for debugging and knowledge search.

ThePrimeagen/99's `skills-v2` branch demonstrated how context-aware operations (treesitter function detection, directory walks, agent rules) dramatically improve AI code assistance. We adapted these patterns for NEXUS's debugging workflow — combining structural context with semantic memory search.

## Endpoints

### POST /ml/rag/search

Semantic search over the RAG knowledge base.

**Request:**
```json
{
  "query": "rate limiter middleware",
  "mode": "all",          // all | errors | tasks | code | conversations
  "domain": "backend",    // frontend | backend | devops | security | testing | ""
  "top_k": 5,
  "threshold": 0.35
}
```

**Response:**
```json
{
  "query": "rate limiter middleware",
  "mode": "all",
  "results": [
    {
      "content": "Task: Implement API rate limiting...",
      "chunk_type": "task_outcome",
      "source_id": "task:dir_abc/task_1",
      "score": 0.8723,
      "raw_similarity": 0.7930,
      "metadata": {"agent_id": "senior_engineer_3", "outcome": "complete"}
    }
  ],
  "count": 3
}
```

**Mode-to-chunk-type mapping:**
| Mode | Chunk Types |
|------|------------|
| `all` | All types (no filter) |
| `errors` | `error_resolution` |
| `tasks` | `task_outcome` |
| `code` | `code_change` |
| `conversations` | `conversation` |

### GET /ml/rag/status

Knowledge base health check.

**Response:**
```json
{
  "total_chunks": 142,
  "by_type": {
    "error_resolution": 23,
    "task_outcome": 56,
    "conversation": 41,
    "code_change": 22
  },
  "ready": true
}
```

### POST /ml/debug

Semantic debug investigation — multi-phase search correlating errors with past resolutions and code changes.

**Request:**
```json
{
  "error": "ML router returning wrong agents for frontend tasks",
  "file_path": "src/ml/router.py",
  "domain": "backend"
}
```

**Response:**
```json
{
  "error": "ML router returning wrong agents...",
  "file_path": "src/ml/router.py",
  "domain": "backend",
  "past_errors": [...],           // error_resolution chunks, threshold 0.30
  "related_tasks": [...],         // task_outcome chunks, threshold 0.35
  "recent_code_changes": [...],   // code_change chunks, threshold 0.30
  "directive_analysis": {
    "similar_directives": [...],
    "cost_estimate": {...},
    "risk": "medium",
    "risk_factors": [...],
    "agent_recommendations": {...},
    "has_precedent": true
  },
  "has_proven_fix": true,         // true if any error match >= 70% similarity
  "proven_fix": {...}             // the highest-confidence past resolution
}
```

**Investigation phases:**
1. Search `error_resolution` chunks (threshold 0.30, top_k 5) — wider net for debugging
2. Search `task_outcome` chunks (threshold 0.35, top_k 3) — related historical tasks
3. Search `code_change` chunks (threshold 0.30, top_k 3) — recent modifications to affected files
4. Run `analyze_new_directive()` — directive-level similarity with cost/risk estimation

## Architecture

```
nexus-plugin                         nexus server (:4200)
┌──────────────────┐                ┌─────────────────────────┐
│ /nexus-debug     │──HTTP POST────▶│ POST /ml/debug          │
│ /nexus-search    │──HTTP POST────▶│ POST /ml/rag/search     │
│                  │                │                         │
│ debug-investigate│                │ src/ml/rag.py           │
│ semantic-search  │                │   ├── retrieve()        │
│ context-rules    │                │   ├── ingest()          │
└──────────────────┘                │   └── build_rag_context()│
                                    │                         │
                                    │ src/ml/similarity.py    │
                                    │   └── analyze_new_dir() │
                                    │                         │
                                    │ src/ml/knowledge_store  │
                                    │   └── ~/.nexus/knowledge│
                                    └─────────────────────────┘
```

## Chunk Weights & Retrieval Strategy

| Chunk Type | Weight | Retention | Use Case |
|-----------|--------|-----------|----------|
| `error_resolution` | 1.3x | Permanent | Proven fixes — never repeat mistakes |
| `task_outcome` | 1.1x | 90 days | What worked and what failed |
| `conversation` | 1.0x | 30 days | Prior Q&A exchanges |
| `code_change` | 0.9x | 30 days | What code was modified |
| `directive_summary` | 0.8x | 90 days | High-level directive outcomes |

Recency boost: up to 10% bonus for chunks < 90 days old.

## Security

- All endpoints are behind the existing auth gate middleware (session cookie or Bearer token)
- No new authentication surface — uses existing `verify_session()` / `verify_token_hash()`
- Search queries are not logged to external services
- Knowledge base is local SQLite (`~/.nexus/knowledge.db`), no cloud egress

## Testing

- Endpoints reuse existing `retrieve()` and `analyze_new_directive()` which have coverage in the test suite
- Integration test: `POST /ml/rag/search` with empty knowledge base returns `{"count": 0, "results": []}`
- Integration test: `POST /ml/debug` with empty knowledge base returns all empty arrays + `has_proven_fix: false`

## Source Attribution

Patterns adapted from:
- **ThePrimeagen/99 `skills-v2`**: SKILL.md file discovery, agent rules as context blocks, directory context walk
- **ThePrimeagen/99 `visual-selection`**: Range-scoped operations concept for file:line targeting
- **Cursor IDE `.mdc` rules**: YAML frontmatter with description/triggers/globs/alwaysApply
