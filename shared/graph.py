"""Граф мыслей: PostgreSQL (nodes, edges), CRUD."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from shared.db import get_conn

EDGE_TYPES = ("continuation", "new_topic", "refinement", "question_answer")


@dataclass
class Node:
    id: str
    user_id: int
    content: str
    summary: Optional[str]
    source_message_id: Optional[int]
    created_at: str
    updated_at: str


def init_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    source_message_id BIGINT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nodes_user_id ON nodes(user_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nodes_created_at ON nodes(created_at DESC);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (from_node_id, to_node_id),
                    FOREIGN KEY (from_node_id) REFERENCES nodes(id),
                    FOREIGN KEY (to_node_id) REFERENCES nodes(id)
                );
            """)


def create_node(
    user_id: int,
    content: str,
    source_message_id: Optional[int] = None,
    summary: Optional[str] = None,
) -> str:
    now = datetime.now(timezone.utc)
    node_id = uuid.uuid4().hex
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO nodes (id, user_id, content, summary, source_message_id, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (node_id, user_id, content.strip(), summary, source_message_id, now, now),
            )
    return node_id


def create_edge(from_node_id: str, to_node_id: str, edge_type: str = "continuation") -> None:
    if edge_type not in EDGE_TYPES:
        edge_type = "continuation"
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO edges (from_node_id, to_node_id, edge_type, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (from_node_id, to_node_id) DO NOTHING""",
                (from_node_id, to_node_id, edge_type, now),
            )


def get_last_nodes(user_id: int, limit: int = 5) -> list[Node]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, user_id, content, summary, source_message_id, created_at, updated_at
                   FROM nodes WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
    return [
        Node(
            id=r[0],
            user_id=r[1],
            content=r[2] or "",
            summary=r[3],
            source_message_id=r[4],
            created_at=str(r[5]),
            updated_at=str(r[6]),
        )
        for r in rows
    ]
