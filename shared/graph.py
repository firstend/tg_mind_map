"""Граф мыслей: PostgreSQL (nodes, edges), CRUD."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from shared.db import get_conn

EDGE_TYPES = ("continuation", "new_topic", "refinement", "question_answer", "sub_topic", "note")
SOURCE_TYPES = ("user", "ai")
NODE_TYPES = ("thought", "request", "suggestion", "topic", "note")
STATUSES = ("idea", "in_progress", "accepted", "rejected", "deferred", "done")


@dataclass
class Node:
    id: str
    user_id: int
    content: str
    summary: Optional[str]
    source_message_id: Optional[int]
    created_at: str
    updated_at: str
    source_type: str = "user"
    node_type: str = "thought"
    status: str = "idea"


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
                    updated_at TIMESTAMPTZ NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'user',
                    node_type TEXT NOT NULL DEFAULT 'thought',
                    status TEXT NOT NULL DEFAULT 'idea'
                );
            """)
            _migrate_nodes_columns(cur)
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_state (
                    user_id BIGINT PRIMARY KEY,
                    active_node_id TEXT REFERENCES nodes(id) ON DELETE SET NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                );
            """)


def create_node(
    user_id: int,
    content: str,
    source_message_id: Optional[int] = None,
    summary: Optional[str] = None,
    source_type: str = "user",
    node_type: str = "thought",
    status: str = "idea",
) -> str:
    if source_type not in SOURCE_TYPES:
        source_type = "user"
    if node_type not in NODE_TYPES:
        node_type = "thought"
    if status not in STATUSES:
        status = "idea"
    now = datetime.now(timezone.utc)
    node_id = uuid.uuid4().hex
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO nodes (id, user_id, content, summary, source_message_id, created_at, updated_at, source_type, node_type, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (node_id, user_id, content.strip(), summary, source_message_id, now, now, source_type, node_type, status),
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


def _migrate_nodes_columns(cur) -> None:
    """Добавляет колонки source_type, node_type, status если их нет."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='nodes' AND column_name='source_type'"
    )
    if cur.fetchone() is None:
        cur.execute("ALTER TABLE nodes ADD COLUMN source_type TEXT NOT NULL DEFAULT 'user'")
        cur.execute("ALTER TABLE nodes ADD COLUMN node_type TEXT NOT NULL DEFAULT 'thought'")
        cur.execute("ALTER TABLE nodes ADD COLUMN status TEXT NOT NULL DEFAULT 'idea'")


def _row_to_node(r: tuple) -> Node:
    return Node(
        id=r[0],
        user_id=r[1],
        content=r[2] or "",
        summary=r[3],
        source_message_id=r[4],
        created_at=str(r[5]),
        updated_at=str(r[6]),
        source_type=r[7] if len(r) > 7 else "user",
        node_type=r[8] if len(r) > 8 else "thought",
        status=r[9] if len(r) > 9 else "idea",
    )


def get_map(user_id: int, limit: int = 30) -> tuple[list[Node], list[tuple[str, str, str]]]:
    """Узлы и рёбра пользователя для отображения карты. Рёбра: (from_id, to_id, edge_type)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, user_id, content, summary, source_message_id, created_at, updated_at, source_type, node_type, status
                   FROM nodes WHERE user_id = %s ORDER BY created_at ASC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
    nodes = [_row_to_node(r) for r in rows]
    node_ids = {n.id for n in nodes}
    if not node_ids:
        return nodes, []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT from_node_id, to_node_id, edge_type FROM edges
                   WHERE from_node_id = ANY(%s) AND to_node_id = ANY(%s)""",
                (list(node_ids), list(node_ids)),
            )
            edges = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    return nodes, edges


def get_last_nodes(user_id: int, limit: int = 5) -> list[Node]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, user_id, content, summary, source_message_id, created_at, updated_at, source_type, node_type, status
                   FROM nodes WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
    return [_row_to_node(r) for r in rows]


def get_node_by_prefix(user_id: int, prefix: str) -> Optional[Node]:
    """Находит узел по префиксу id (минимум 4 символа). Возвращает None если не найден или несколько совпадений."""
    prefix = (prefix or "").strip().lower()
    if len(prefix) < 4:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, user_id, content, summary, source_message_id, created_at, updated_at, source_type, node_type, status
                   FROM nodes WHERE user_id = %s AND id LIKE %s""",
                (user_id, prefix + "%"),
            )
            rows = cur.fetchall()
    if len(rows) != 1:
        return None
    return _row_to_node(rows[0])


def set_active_node(user_id: int, node_id: str) -> None:
    """Устанавливает активную тему пользователя."""
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO user_state (user_id, active_node_id, updated_at)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET active_node_id = %s, updated_at = %s""",
                (user_id, node_id, now, node_id, now),
            )


def get_active_node(user_id: int) -> Optional[Node]:
    """Возвращает активный узел пользователя или None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT n.id, n.user_id, n.content, n.summary, n.source_message_id, n.created_at, n.updated_at, n.source_type, n.node_type, n.status
                   FROM user_state us
                   JOIN nodes n ON n.id = us.active_node_id AND n.user_id = us.user_id
                   WHERE us.user_id = %s""",
                (user_id,),
            )
            row = cur.fetchone()
    return _row_to_node(row) if row else None


def get_children(user_id: int, parent_id: str) -> list[Node]:
    """Дети узла (рёбра from parent_id)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT n.id, n.user_id, n.content, n.summary, n.source_message_id, n.created_at, n.updated_at, n.source_type, n.node_type, n.status
                   FROM edges e
                   JOIN nodes n ON n.id = e.to_node_id AND n.user_id = %s
                   WHERE e.from_node_id = %s
                   ORDER BY e.created_at ASC""",
                (user_id, parent_id),
            )
            rows = cur.fetchall()
    return [_row_to_node(r) for r in rows]


def get_node(user_id: int, node_id: str) -> Optional[Node]:
    """Получить узел по id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, user_id, content, summary, source_message_id, created_at, updated_at, source_type, node_type, status
                   FROM nodes WHERE user_id = %s AND id = %s""",
                (user_id, node_id),
            )
            row = cur.fetchone()
    return _row_to_node(row) if row else None


def update_node(
    user_id: int,
    node_id: str,
    content: Optional[str] = None,
    summary: Optional[str] = None,
    status: Optional[str] = None,
) -> bool:
    """Обновить узел. Возвращает True если обновлён."""
    node = get_node(user_id, node_id)
    if not node:
        return False
    now = datetime.now(timezone.utc)
    new_content = content if content is not None else node.content
    new_summary = summary if summary is not None else node.summary
    new_status = status if status is not None else node.status
    if new_status not in STATUSES:
        new_status = node.status
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE nodes SET content = %s, summary = %s, status = %s, updated_at = %s
                   WHERE id = %s AND user_id = %s""",
                (new_content, new_summary, new_status, now, node_id, user_id),
            )
            return cur.rowcount > 0


def delete_node(user_id: int, node_id: str, recursive: bool = False) -> bool:
    """Удаляет узел и связанные рёбра. recursive=True — удаляет детей и их потомков. Возвращает True если удалён."""
    node = get_node_by_prefix(user_id, node_id)
    if not node:
        return False
    nid = node.id
    if recursive:
        children = get_children(user_id, nid)
        for c in children:
            delete_node(user_id, c.id, recursive=True)
    from shared.rag import delete_chunks_by_source_node
    delete_chunks_by_source_node(user_id, nid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM edges WHERE from_node_id = %s OR to_node_id = %s", (nid, nid))
            cur.execute(
                "UPDATE user_state SET active_node_id = NULL WHERE user_id = %s AND active_node_id = %s",
                (user_id, nid),
            )
            cur.execute("DELETE FROM nodes WHERE id = %s AND user_id = %s", (nid, user_id))
            deleted = cur.rowcount > 0
    return deleted


