-- 002_persona_memory_vector_1024.sql
--
-- Resize persona_memory.embedding from VECTOR(1536) → VECTOR(1024) to
-- match Voyage AI's voyage-3.5-lite output dimension. We chose Voyage
-- over OpenAI for two reasons:
--   1. Anthropic ecosystem alignment (Voyage is Anthropic-recommended)
--   2. Cost: $0.02/1M tokens; the pilot uses ~$0.0003/month — free tier
--      covers indefinitely.
--
-- VECTOR(1536) was the original spec from when we anticipated OpenAI
-- text-embedding-3-small. No data lives in this table yet (the column
-- was defined but no writer existed pre-PR #41), so the resize is
-- destructive-safe: DROP + ADD instead of attempting a lossy conversion.
--
-- The ivfflat index is dropped + recreated against the new column.

-- Drop the index that depends on the column
DROP INDEX IF EXISTS persona_memory_embedding_idx;

-- Drop + re-add the column with the new dimension
ALTER TABLE persona_memory DROP COLUMN IF EXISTS embedding;
ALTER TABLE persona_memory ADD COLUMN embedding VECTOR(1024);

-- Recreate the cosine-similarity index
-- NOTE: NOT NULL constraint relaxed — embedding writer is best-effort
-- (if Voyage API call fails, we still persist the thesis row in
-- analyst_reports + persona_memory; just no embedding for that row).
-- fetch_memory_recall handles NULL embeddings gracefully.
CREATE INDEX IF NOT EXISTS persona_memory_embedding_idx
    ON persona_memory USING ivfflat (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;
