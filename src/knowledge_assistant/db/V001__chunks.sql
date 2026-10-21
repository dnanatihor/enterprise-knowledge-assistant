-- Role filter is part of the retrieval predicate, not a post-filter.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id UUID PRIMARY KEY,
    document_id UUID NOT NULL,
    tenant_id TEXT NOT NULL,
    section TEXT NOT NULL,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

CREATE TABLE IF NOT EXISTS chunk_acl (
    chunk_id UUID NOT NULL REFERENCES chunks (chunk_id),
    role_name TEXT NOT NULL,
    PRIMARY KEY (chunk_id, role_name)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);
