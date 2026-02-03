"""
Worker: забирает из incoming, пайплайн (граф → RAG → агент), кладёт ответ в outgoing.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import IncomingMessage, OutgoingMessage
from shared.queues import pop_incoming, push_outgoing
from shared.graph import init_schema as init_graph, create_node, create_edge, get_last_nodes
from shared.rag import init_schema as init_rag, add_chunk, search as rag_search
from shared.llm import get_embedding, classify_topic, universal_assistant


def process_message(incoming: IncomingMessage) -> OutgoingMessage:
    """Пайплайн: классификация → граф → RAG → агент → ответ."""
    text = (incoming.text or "").strip()
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

    user_id = incoming.user_id
    # Шаг 1: классификация (заглушка: всегда новая тема)
    last_nodes = get_last_nodes(user_id, limit=3)
    is_new_topic, parent_node_id = classify_topic(user_id, text, last_nodes)

    # Шаг 2: граф — создать узел и ребро к родителю
    node_id = create_node(
        user_id=user_id,
        content=text,
        source_message_id=incoming.message_id,
    )
    if parent_node_id:
        create_edge(parent_node_id, node_id, edge_type="continuation")

    # Шаг 3: RAG — один эмбеддинг для добавления чанка и для поиска контекста
    try:
        embedding = get_embedding(text)
        add_chunk(user_id=user_id, text=text, embedding=embedding, source_node_id=node_id)
        rag_context = rag_search(user_id, embedding, top_k=5)
    except Exception:
        rag_context = []
    graph_context = [{"content": n.content} for n in last_nodes]

    try:
        reply_text = universal_assistant(text, user_id, rag_context, graph_context)
    except Exception as e:
        reply_text = f"Временная ошибка, попробуй позже. ({type(e).__name__})"

    return OutgoingMessage(
        chat_id=incoming.chat_id,
        text=reply_text,
        reply_to_message_id=incoming.message_id,
    )


def run_worker() -> None:
    init_graph()
    init_rag()
    while True:
        msg = pop_incoming(timeout_seconds=30)
        if msg is None:
            continue
        try:
            out = process_message(msg)
            push_outgoing(out)
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
