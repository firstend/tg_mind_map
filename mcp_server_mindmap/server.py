"""MCP Server: Mindmap — tools для дерева тем."""

import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mindmap")


def _get_user_id(args: dict) -> int:
    uid = args.get("user_id")
    if uid is None:
        raise ValueError("user_id required for all mindmap tools")
    return int(uid)


def _node_to_dict(n) -> dict:
    return {
        "id": n.id,
        "title": n.summary or n.content[:80] if n.content else "",
        "content": n.content or "",
        "node_type": n.node_type,
        "status": n.status,
    }


@mcp.tool()
def mindmap_get_tree(user_id: int) -> str:
    """Дерево тем пользователя: корни и их дети. user_id — Telegram user_id."""
    from shared.graph import get_map, get_children

    nodes, edges = get_map(user_id, limit=100)
    node_by_id = {n.id: n for n in nodes}
    children_of = {n.id: [] for n in nodes}
    has_parent = set()
    for from_id, to_id, _ in edges:
        if from_id in node_by_id and to_id in node_by_id:
            children_of[from_id].append(to_id)
            has_parent.add(to_id)
    roots = [n for n in nodes if n.id not in has_parent]

    def format_node(n, indent: int) -> str:
        lines = ["  " * indent + f"- [{n.id[:8]}] {n.summary or n.content[:60] or '?'} ({n.node_type})"]
        for cid in children_of.get(n.id, []):
            if cid in node_by_id:
                lines.append(format_node(node_by_id[cid], indent + 1))
        return "\n".join(lines)

    result = []
    for r in roots:
        result.append(format_node(r, 0))
    return "\n".join(result) if result else "Карта пуста."


@mcp.tool()
def mindmap_get_active(user_id: int) -> str:
    """Активная тема пользователя. user_id — Telegram user_id."""
    from shared.graph import get_active_node

    n = get_active_node(user_id)
    if not n:
        return "Активная тема не задана."
    return json.dumps(_node_to_dict(n), ensure_ascii=False)


@mcp.tool()
def mindmap_set_active(user_id: int, topic_id: str) -> str:
    """Установить активную тему. user_id, topic_id — id темы (полный или префикс ≥4 символа)."""
    from shared.graph import get_node_by_prefix, set_active_node

    node = get_node_by_prefix(user_id, topic_id)
    if not node:
        return f"Тема с id {topic_id} не найдена."
    set_active_node(user_id, node.id)
    return json.dumps({"ok": True, "topic_id": node.id, "title": node.summary or node.content[:60]})


@mcp.tool()
def mindmap_create_topic(
    user_id: int,
    title: str,
    description: str = "",
    parent_id: str = "",
) -> str:
    """Создать тему (корневую или подтему). user_id, title — обязательны. parent_id — для подтемы."""
    from shared.graph import create_node, create_edge, set_active_node, get_node_by_prefix

    summary = (title or "").strip()[:200]
    content = (description or title or "").strip()
    if not summary:
        return "title не может быть пустым."
    node_id = create_node(
        user_id=user_id,
        content=content,
        summary=summary,
        node_type="topic",
        source_type="user",
    )
    if parent_id:
        parent = get_node_by_prefix(user_id, parent_id)
        if parent:
            create_edge(parent.id, node_id, edge_type="sub_topic")
    set_active_node(user_id, node_id)
    return json.dumps({"topic_id": node_id, "title": summary}, ensure_ascii=False)


@mcp.tool()
def mindmap_add_subtopic(
    user_id: int,
    parent_id: str,
    title: str,
    description: str = "",
) -> str:
    """Добавить подтему к существующей теме. user_id, parent_id, title — обязательны."""
    from shared.graph import get_node_by_prefix, create_node, create_edge, set_active_node

    parent = get_node_by_prefix(user_id, parent_id)
    if not parent:
        return f"Родительская тема {parent_id} не найдена."
    summary = (title or "").strip()[:200]
    content = (description or title or "").strip()
    node_id = create_node(
        user_id=user_id,
        content=content,
        summary=summary,
        node_type="topic",
        source_type="user",
    )
    create_edge(parent.id, node_id, edge_type="sub_topic")
    set_active_node(user_id, node_id)
    return json.dumps({"topic_id": node_id, "title": summary, "parent_id": parent.id}, ensure_ascii=False)


@mcp.tool()
def mindmap_update_topic(
    user_id: int,
    topic_id: str,
    title: str = "",
    description: str = "",
    status: str = "",
) -> str:
    """Обновить тему. topic_id — id темы. title, description, status — опционально."""
    from shared.graph import get_node_by_prefix, update_node

    node = get_node_by_prefix(user_id, topic_id)
    if not node:
        return f"Тема {topic_id} не найдена."
    new_summary = title.strip()[:200] if title else None
    new_content = description.strip() if description else None
    new_status = status.strip() if status else None
    ok = update_node(user_id, node.id, content=new_content, summary=new_summary, status=new_status)
    return json.dumps({"ok": ok, "topic_id": node.id})


@mcp.tool()
def mindmap_add_note(
    user_id: int,
    topic_id: str,
    content: str,
    source: str = "user",
) -> str:
    """Добавить заметку к теме. content — текст заметки. source — user или ai."""
    from shared.graph import get_node_by_prefix, create_node, create_edge

    topic = get_node_by_prefix(user_id, topic_id)
    if not topic:
        return f"Тема {topic_id} не найдена."
    src = source if source in ("user", "ai") else "user"
    note_id = create_node(
        user_id=user_id,
        content=(content or "").strip(),
        summary=None,
        node_type="note",
        source_type=src,
    )
    create_edge(topic.id, note_id, edge_type="note")
    return json.dumps({"note_id": note_id, "topic_id": topic.id}, ensure_ascii=False)


@mcp.tool()
def mindmap_search(user_id: int, query: str, limit: int = 10) -> str:
    """Поиск по темам и заметкам (RAG). user_id, query — обязательны."""
    from shared.llm import get_embedding
    from shared.rag import search

    if not query.strip():
        return "query не может быть пустым."
    try:
        emb = get_embedding(query.strip())
        results = search(user_id, emb, top_k=limit)
    except Exception as e:
        return f"Ошибка поиска: {e}"
    if not results:
        return "Ничего не найдено."
    lines = [f"- {r.get('text', '')[:200]}" for r in results]
    return "\n".join(lines)


@mcp.tool()
def mindmap_get_context(user_id: int, topic_id: str = "") -> str:
    """Контекст для планирования: тема + её дети + последние заметки. topic_id — опционально, иначе активная."""
    from shared.graph import get_active_node, get_node_by_prefix, get_children

    if topic_id:
        topic = get_node_by_prefix(user_id, topic_id)
    else:
        topic = get_active_node(user_id)
    if not topic:
        return "Тема не задана. Укажи topic_id или установи активную тему."
    children = get_children(user_id, topic.id)
    parts = [
        f"Тема: {topic.summary or topic.content}",
        f"Описание: {topic.content}",
        "",
        "Подтемы:",
    ]
    for c in children:
        if c.node_type == "topic":
            parts.append(f"  - {c.summary or c.content[:60]}")
        else:
            parts.append(f"  [заметка] {c.content[:100]}")
    return "\n".join(parts)


@mcp.tool()
def mindmap_delete_topic(user_id: int, topic_id: str) -> str:
    """Удалить тему и её подтемы рекурсивно. topic_id — id темы (полный или префикс ≥4 символа)."""
    from shared.graph import delete_node, get_node_by_prefix

    node = get_node_by_prefix(user_id, topic_id)
    if not node:
        return f"Тема {topic_id} не найдена."
    ok = delete_node(user_id, node.id, recursive=True)
    return json.dumps({"ok": ok, "deleted_id": node.id})
