"""RAG: pgvector — добавление чанков, поиск по эмбеддингу."""

import uuid
from typing import Optional

import numpy as np

from shared.db import get_conn

# text-embedding-3-small → 1536 dimensions
EMBEDDING_DIM = 1536


def init_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    text TEXT NOT NULL,
                    embedding vector({EMBEDDING_DIM}) NOT NULL,
                    source_node_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_user_id ON chunks(user_id);")
            # HNSW индекс для быстрого поиска по косинусному расстоянию
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks
                USING hnsw (embedding vector_cosine_ops);
            """)


def add_chunk(
    user_id: int,
    text: str,
    embedding: list[float],
    source_node_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
) -> str:
    cid = chunk_id or uuid.uuid4().hex
    vec = np.array(embedding, dtype=np.float32)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO chunks (id, user_id, text, embedding, source_node_id)
                   VALUES (%s, %s, %s, %s, %s)""",
                (cid, user_id, text, vec, source_node_id),
            )
    return cid


def search(
    user_id: int,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Возвращает список {text, source_node_id?} для пользователя user_id."""
    vec = np.array(query_embedding, dtype=np.float32)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT text, source_node_id FROM chunks
                   WHERE user_id = %s
                   ORDER BY embedding <=> %s
                   LIMIT %s""",
                (user_id, vec, top_k),
            )
            rows = cur.fetchall()
    return [{"text": r[0] or "", "source_node_id": r[1]} for r in rows]


def delete_chunks_by_source_node(user_id: int, source_node_id: str) -> int:
    """Удаляет чанки, привязанные к узлу. Возвращает количество удалённых."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chunks WHERE user_id = %s AND source_node_id = %s",
                (user_id, source_node_id),
            )
            return cur.rowcount
