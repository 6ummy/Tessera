"""Voyage AI embeddings — thin wrapper for thesis similarity recall.

Why Voyage (not OpenAI / not self-hosted):
- Anthropic-recommended provider; keeps the stack in one ecosystem.
- $0.02 / 1M tokens (~$0.0003 / month at pilot scale — free tier
  covers indefinitely).
- Zero new ML deps (no torch / sentence-transformers).
- 1024-dim output matches our migrated persona_memory.embedding column.

Failure mode:
- All errors (network, rate-limit, malformed response, missing key) are
  caught and logged. `embed_thesis` returns None on failure. Callers
  treat None as "skip embedding for this row" — the thesis still
  persists, just without vector recall on that one row.
"""

from __future__ import annotations

from typing import Sequence

from tessera_worker.config import get_settings
from tessera_worker.logging import get_logger

log = get_logger(__name__)

EMBEDDING_DIM = 1024  # voyage-3.5-lite default; pinned via schema


def embed_thesis(text: str) -> list[float] | None:
    """One thesis → one 1024-dim embedding. None on any failure.

    Truncates input to ~32K chars before sending (Voyage's per-input
    token cap is 32K tokens; 1 token ≈ 4 chars in English, so 32K chars
    is a safe upper bound that avoids client-side token counting).
    """
    s = get_settings()
    if not s.voyage_api_key:
        # Quiet — this is the expected state during local dev / before
        # key is provisioned. The caller still persists the thesis.
        return None
    if not text or not text.strip():
        return None

    try:
        import voyageai  # imported lazily so missing dep doesn't break import-time
    except ImportError:
        log.warning("embeddings.voyage_not_installed",
                    note="pip install voyageai to enable similarity recall")
        return None

    try:
        client = voyageai.Client(api_key=s.voyage_api_key)
        result = client.embed(
            texts=[text[:32_000]],
            model=s.voyage_model,
            input_type="document",
        )
        vec = result.embeddings[0] if result.embeddings else None
        if vec is None or len(vec) != EMBEDDING_DIM:
            log.warning("embeddings.unexpected_dim",
                        got=len(vec) if vec else None, expected=EMBEDDING_DIM)
            return None
        return list(vec)
    except Exception as e:
        # Catch-all: network, auth, rate-limit, schema mismatch. Embedding
        # is best-effort; never block the persist path.
        log.warning("embeddings.failed", error=str(e), error_type=type(e).__name__)
        return None


def embed_query(text: str) -> list[float] | None:
    """Same as `embed_thesis` but uses input_type='query' for asymmetric
    retrieval (Voyage tunes query vs document embeddings differently)."""
    s = get_settings()
    if not s.voyage_api_key or not text or not text.strip():
        return None
    try:
        import voyageai
    except ImportError:
        return None
    try:
        client = voyageai.Client(api_key=s.voyage_api_key)
        result = client.embed(
            texts=[text[:32_000]],
            model=s.voyage_model,
            input_type="query",
        )
        vec = result.embeddings[0] if result.embeddings else None
        if vec is None or len(vec) != EMBEDDING_DIM:
            return None
        return list(vec)
    except Exception as e:
        # Common case: free-tier rate limit hit (3 RPM, 10K TPM) before
        # the user adds a billing method. Drop to debug-level so backtest
        # runs don't get a wall of warnings; recall falls back to recency.
        msg = str(e)
        if "rate limit" in msg.lower() or "RPM" in msg or "TPM" in msg:
            log.debug("embeddings.query_rate_limited", error=msg[:200])
        else:
            log.warning("embeddings.query_failed", error=msg)
        return None


def to_pgvector_literal(vec: Sequence[float]) -> str:
    """psycopg/sqlalchemy don't natively bind a pgvector; cast via the
    string literal form `'[v1,v2,…]'`. This helper keeps the format
    consistent across callers."""
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"
