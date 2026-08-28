"""Тест LLM: эмбеддинг и чат. Запуск: python scripts/test_llm.py"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from shared.llm import (
    get_embedding,
    universal_assistant,
    LLM_PROVIDER,
    _chat_model,
    _embedding_model,
)


def main() -> None:
    print(f"Провайдер: {LLM_PROVIDER}")
    print(f"Embedding: {_embedding_model()}, Chat: {_chat_model()}")

    # Эмбеддинг
    emb = get_embedding("тестовая мысль")
    print(f"Embedding OK, dim={len(emb)}")

    # Чат
    reply = universal_assistant(
        query="Привет, это тест",
        user_id=0,
        rag_context=[],
        graph_context=[],
    )
    print(f"Reply: {reply}")


if __name__ == "__main__":
    main()
