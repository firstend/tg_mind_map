"""
Worker: забирает из incoming, пайплайн (граф → RAG → агент), кладёт ответ в outgoing.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import IncomingMessage, OutgoingMessage
from shared.queues import pop_incoming, push_outgoing
from shared.graph import init_schema as init_graph, create_node, create_edge, get_last_nodes, get_map, delete_node, get_node_by_prefix, set_active_node, get_active_node
from shared.rag import init_schema as init_rag, add_chunk, search as rag_search, delete_chunks_by_source_node
from shared.llm import get_embedding, classify_topic, extract_theme, infer_status, universal_assistant
from planner import run_planner
from planner.run_multistep import run_planner_multistep

USE_PLANNER_AUTO = os.environ.get("USE_PLANNER_AUTO", "false").lower() == "true"
USE_MULTISTEP_PLANNER = os.environ.get("USE_MULTISTEP_PLANNER", "false").lower() == "true"
USE_DEBUG = os.environ.get("USE_DEBUG", "false").lower() == "true"

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def _send_debug_messages(chat_id: int, text: str, reply_to_message_id: int | None = None) -> None:
    """Отправляет целиковый текст в Telegram, разрезая на части при необходимости."""
    if not text:
        return
    offset = 0
    while offset < len(text):
        chunk = text[offset : offset + TELEGRAM_MAX_MESSAGE_LENGTH]
        push_outgoing(OutgoingMessage(
            chat_id=chat_id,
            text=chunk,
            reply_to_message_id=reply_to_message_id,
        ))
        offset += TELEGRAM_MAX_MESSAGE_LENGTH


def _run_planner_if_needed(
    query: str,
    graph_ctx: list[dict],
    user_id: int,
    debug_callback: Optional[Callable[[str], None]] = None,
) -> str | None:
    """Запуск planner. debug_callback(text) — при USE_DEBUG отправит план в Telegram."""
    if USE_MULTISTEP_PLANNER:
        return run_planner_multistep(
            query, [], graph_ctx, role="universal", user_id=user_id, debug_callback=debug_callback
        )
    return run_planner(
        query, [], graph_ctx, role="universal", user_id=user_id, debug_callback=debug_callback
    )


def _format_map(user_id: int) -> str:
    """Форматирует карту мыслей в текст с ID для /del."""
    nodes, edges = get_map(user_id, limit=50)
    if not nodes:
        return "Карта пуста. Пиши боту мысли — они появятся здесь."
    node_by_id = {n.id: n for n in nodes}
    # Корни: узлы, в которые нет входящих рёбер
    children_of = {n.id: [] for n in nodes}
    has_parent = set()
    for from_id, to_id, etype in edges:
        if from_id in node_by_id and to_id in node_by_id:
            children_of[from_id].append((to_id, etype))
            has_parent.add(to_id)
    roots = [n for n in nodes if n.id not in has_parent]
    order = {n.id: i for i, n in enumerate(nodes)}
    roots.sort(key=lambda n: order.get(n.id, 0))
    for k in children_of:
        children_of[k].sort(key=lambda x: order.get(x[0], 0))

    STATUS_ICON = {"idea": "💡", "in_progress": "🔄", "accepted": "✅", "rejected": "❌", "deferred": "⏸", "done": "✔"}
    TYPE_BADGE = {"thought": "", "request": "❓", "suggestion": "💬"}
    SOURCE_BADGE = {"user": "", "ai": "🤖"}

    def short_id(n) -> str:
        return (n.id or "")[:8]

    def display_label(n) -> str:
        s = (n.summary or n.content or "").replace("\n", " ").strip()
        s = s[:100] + "…" if len(s) > 100 else s
        icon = STATUS_ICON.get(getattr(n, "status", "idea"), "💡")
        badge = TYPE_BADGE.get(getattr(n, "node_type", "thought"), "") or SOURCE_BADGE.get(getattr(n, "source_type", "user"), "")
        prefix = f"{icon} " if icon else ""
        suffix = f" {badge}" if badge else ""
        return f"[{short_id(n)}] {prefix}{s}{suffix}"

    lines = ["🗺 Карта мыслей (/del <id>):\n"]
    seen = set()

    def add_node(n, indent: int, prefix: str = ""):
        if n.id in seen:
            return
        seen.add(n.id)
        line = "  " * indent + f"{prefix}{display_label(n)}"
        lines.append(line)
        for child_id, etype in children_of.get(n.id, []):
            if child_id in node_by_id and child_id not in seen:
                add_node(node_by_id[child_id], indent + 1, "├ ")

    for r in roots:
        add_node(r, 0, "• ")
    result = "\n".join(lines)
    return result[:4000] if len(result) > 4000 else result


def process_message(incoming: IncomingMessage) -> OutgoingMessage:
    """Пайплайн: классификация → граф → RAG → агент → ответ."""
    text = (incoming.text or "").strip()
    user_id = incoming.user_id

    if text.lower() == "/map":
        return OutgoingMessage(
            chat_id=incoming.chat_id,
            text=_format_map(user_id),
            reply_to_message_id=incoming.message_id,
        )

    if text.lower() == "/topic":
        active = get_active_node(user_id)
        if not active:
            return OutgoingMessage(
                chat_id=incoming.chat_id,
                text="Активная тема не задана. Напиши боту мысль или идею.",
                reply_to_message_id=incoming.message_id,
            )
        summary = (active.summary or active.content or "").replace("\n", " ").strip()
        summary = summary[:200] + "…" if len(summary) > 200 else summary
        return OutgoingMessage(
            chat_id=incoming.chat_id,
            text=f"📍 Активная тема: {summary}",
            reply_to_message_id=incoming.message_id,
        )

    if text.lower() == "/help":
        help_text = "Команды:\n• /map — карта мыслей (с ID)\n• /topic — текущая активная тема\n• /tools <запрос> — выполнить запрос через MCP (файлы, папки)\n• /del <id> — удалить по ID (4+ символа)\n• /del last — удалить последнюю запись"
        if USE_PLANNER_AUTO:
            help_text += "\n\nМожешь написать «прочитай файл X», «найди про Y», «создай тему Заработка» — planner сработает автоматически."
        return OutgoingMessage(
            chat_id=incoming.chat_id,
            text=help_text,
            reply_to_message_id=incoming.message_id,
        )

    low = text.lower()
    if low.startswith("/tools ") or low == "/tools":
        tools_query = text[7:].strip() if len(text) > 7 else ""
        if not tools_query:
            return OutgoingMessage(
                chat_id=incoming.chat_id,
                text="Напиши: /tools <запрос>, например: /tools прочитай /tmp/readme.txt",
                reply_to_message_id=incoming.message_id,
            )
        last_nodes = get_last_nodes(user_id, limit=5)
        graph_ctx = [{"content": n.summary or n.content} for n in last_nodes]
        debug_cb = None
        if USE_DEBUG:
            def _on_debug(msg: str):
                _send_debug_messages(incoming.chat_id, msg, incoming.message_id)
            debug_cb = _on_debug
        try:
            reply_text = _run_planner_if_needed(tools_query, graph_ctx, user_id, debug_callback=debug_cb)
        except Exception as e:
            reply_text = f"Ошибка planner: {e}"
        if not reply_text:
            try:
                reply_text = universal_assistant(tools_query, user_id, [], graph_ctx)
            except Exception as e:
                reply_text = f"Временная ошибка, попробуй позже. ({type(e).__name__})"
        return OutgoingMessage(
            chat_id=incoming.chat_id,
            text=reply_text or "Не удалось выполнить запрос.",
            reply_to_message_id=incoming.message_id,
        )

    low = text.lower()
    if low.startswith("/del "):
        arg = text[5:].strip()
        cb_id = incoming.callback_query_id
        if not arg:
            return OutgoingMessage(chat_id=incoming.chat_id, text="Укажи ID узла: /del <id> или /del last", reply_to_message_id=incoming.message_id, callback_query_id=cb_id)
        node_id = None
        if arg.lower() == "last":
            last = get_last_nodes(user_id, limit=1)
            if not last:
                return OutgoingMessage(chat_id=incoming.chat_id, text="Нет записей для удаления.", reply_to_message_id=incoming.message_id, callback_query_id=cb_id)
            node_id = last[0].id
        else:
            node = get_node_by_prefix(user_id, arg)
            if not node:
                return OutgoingMessage(chat_id=incoming.chat_id, text="Узел не найден. Проверь ID в /map.", reply_to_message_id=incoming.message_id, callback_query_id=cb_id)
            node_id = node.id
        delete_chunks_by_source_node(user_id, node_id)
        if delete_node(user_id, node_id):
            return OutgoingMessage(chat_id=incoming.chat_id, text="Удалено.", reply_to_message_id=incoming.message_id, callback_query_id=cb_id)
        return OutgoingMessage(chat_id=incoming.chat_id, text="Ошибка удаления.", reply_to_message_id=incoming.message_id, callback_query_id=cb_id)

    if not text and incoming.voice_file_id:
        return OutgoingMessage(
            chat_id=incoming.chat_id,
            text="Пока принимаю только текст. Голос — позже.",
            reply_to_message_id=incoming.message_id,
        )
    if not text:
        return OutgoingMessage(
            chat_id=incoming.chat_id,
            text="Напиши текст сообщения.",
            reply_to_message_id=incoming.message_id,
        )

    # Phase 5: USE_PLANNER_AUTO — planner всегда вызывается первым
    # Если planner нашёл нужные tools и вернул ответ — отдаём его
    # Если planner вернул None (tools не нужны) — продолжаем обычный пайплайн
    if USE_PLANNER_AUTO:
        last_nodes = get_last_nodes(user_id, limit=5)
        graph_ctx = [{"content": n.summary or n.content} for n in last_nodes]
        debug_cb = None
        if USE_DEBUG:
            def _on_debug(msg: str):
                _send_debug_messages(incoming.chat_id, msg, incoming.message_id)
            debug_cb = _on_debug
        try:
            planner_reply = _run_planner_if_needed(text, graph_ctx, user_id, debug_callback=debug_cb)
        except Exception as e:
            planner_reply = f"Ошибка planner: {e}"
        if planner_reply:
            # Planner справился — возвращаем ответ
            return OutgoingMessage(
                chat_id=incoming.chat_id,
                text=planner_reply,
                reply_to_message_id=incoming.message_id,
            )
        # planner_reply is None — tools не нужны, продолжаем обычный пайплайн

    # Шаг 1: извлечение темы
    extracted = extract_theme(text)
    context_type = extracted.get("context_type") or "project"
    theme = extracted.get("theme") or text[:80]
    key_parts = extracted.get("key_parts", "")
    action_type = extracted.get("action_type") or "new_thought"
    parent_hint = extracted.get("parent_hint")
    project_switch = extracted.get("project_switch", False)
    suggested_role = extracted.get("suggested_role") or "universal"

    # Болтовня — только ответ, без узла и RAG
    if context_type == "chitchat":
        last_nodes = get_last_nodes(user_id, limit=5)
        graph_context = [{"content": n.summary or n.content} for n in last_nodes]
        try:
            reply_text = universal_assistant(text, user_id, [], graph_context, role=suggested_role)
        except Exception as e:
            reply_text = f"Временная ошибка, попробуй позже. ({type(e).__name__})"
        return OutgoingMessage(chat_id=incoming.chat_id, text=reply_text, reply_to_message_id=incoming.message_id)

    # Шаг 2: классификация — родитель и тип связи
    last_nodes = get_last_nodes(user_id, limit=7)
    parent_node_id, edge_type = classify_topic(theme, last_nodes, parent_hint)
    if project_switch:
        parent_node_id = None  # явное переключение → новый корень

    # Маппинг action_type → node_type, статус
    node_type = "request" if action_type == "request" else "thought"
    status = infer_status(text, action_type)

    # Шаг 3: создание узла (content=полный текст, summary=тема)
    node_id = create_node(
        user_id=user_id,
        content=text,
        source_message_id=incoming.message_id,
        summary=theme or None,
        source_type="user",
        node_type=node_type,
        status=status,
    )
    if parent_node_id:
        create_edge(parent_node_id, node_id, edge_type=edge_type)
    set_active_node(user_id, node_id)

    # Шаг 4: RAG — тема + ключевая часть
    rag_text = f"{theme}\n{key_parts}".strip() if key_parts else theme
    try:
        embedding = get_embedding(rag_text)
        add_chunk(user_id=user_id, text=rag_text, embedding=embedding, source_node_id=node_id)
        rag_context = rag_search(user_id, embedding, top_k=5)
    except Exception:
        rag_context = []
    graph_context = [{"content": n.summary or n.content} for n in last_nodes]

    try:
        reply_text = universal_assistant(text, user_id, rag_context, graph_context, role=suggested_role)
    except Exception as e:
        reply_text = f"Временная ошибка, попробуй позже. ({type(e).__name__})"

    return OutgoingMessage(
        chat_id=incoming.chat_id,
        text=reply_text,
        reply_to_message_id=incoming.message_id,
    )


def run_worker() -> None:
    level = getattr(logging, (os.environ.get("LOG_LEVEL") or "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger = logging.getLogger("worker")
    for name in ("mcp_hub", "planner"):
        logging.getLogger(name).setLevel(level)
    logger.info("Worker starting...")
    init_graph()
    init_rag()
    logger.info("Worker ready, waiting for messages")
    while True:
        msg = pop_incoming(timeout_seconds=30)
        if msg is None:
            continue
        logger.info("Processing message from chat_id=%s: %s", msg.chat_id, msg.text[:100] if msg.text else "")
        try:
            out = process_message(msg)
            push_outgoing(out)
            logger.info("Message processed, reply sent")
        except Exception as e:
            push_outgoing(
                OutgoingMessage(
                    chat_id=msg.chat_id,
                    text=f"Ошибка обработки: {e}",
                    reply_to_message_id=msg.message_id,
                )
            )


if __name__ == "__main__":
    run_worker()
