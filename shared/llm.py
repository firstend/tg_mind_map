"""ИИ: эмбеддинги и чат. Поддержка OpenAI и Qwen (DashScope). По умолчанию — Qwen."""

import json
import os
import re
from typing import Optional

from openai import OpenAI

USE_LLM_SERVICE = os.environ.get("USE_LLM_SERVICE", "false").lower() == "true"

_openai_client: Optional[OpenAI] = None
_qwen_client: Optional[OpenAI] = None

# Провайдер: qwen (по умолчанию) | openai
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "qwen").lower()

# Модели
OPENAI_EMBEDDING = "text-embedding-3-small"
OPENAI_CHAT = "gpt-4o-mini"
QWEN_EMBEDDING = "text-embedding-v4"  # 1536 dims (Singapore), совместимо с pgvector
QWEN_EMBEDDING_DIM = 1536
QWEN_CHAT = os.environ.get("QWEN_CHAT_MODEL", "qwen-plus")

RAG_TOP_K = 5
# Лимит Telegram — 4096, оставляем запас
MAX_REPLY_CHARS = 4000

# Singapore (international) — по умолчанию; China: dashscope.aliyuncs.com; US: dashscope-us.aliyuncs.com
DASHSCOPE_BASE = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY не задан (нужен для провайдера openai)")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def _get_qwen_client() -> OpenAI:
    global _qwen_client
    if _qwen_client is None:
        key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
        if not key:
            raise RuntimeError("QWEN_API_KEY или DASHSCOPE_API_KEY не задан (нужен для провайдера qwen)")
        _qwen_client = OpenAI(api_key=key, base_url=DASHSCOPE_BASE)
    return _qwen_client


def _client() -> OpenAI:
    if LLM_PROVIDER == "qwen":
        return _get_qwen_client()
    return _get_openai_client()


def _embedding_model() -> str:
    return QWEN_EMBEDDING if LLM_PROVIDER == "qwen" else OPENAI_EMBEDDING


def _chat_model() -> str:
    return QWEN_CHAT if LLM_PROVIDER == "qwen" else OPENAI_CHAT


def get_embedding(text: str) -> list[float]:
    if USE_LLM_SERVICE:
        from llm_service.client import submit_embedding
        dims = QWEN_EMBEDDING_DIM if LLM_PROVIDER == "qwen" else None
        return submit_embedding(text.strip() or "пусто", dimensions=dims)
    if not text.strip():
        text = "пусто"
    c = _client()
    kwargs = {"input": [text.strip()], "model": _embedding_model()}
    if LLM_PROVIDER == "qwen":
        kwargs["dimensions"] = QWEN_EMBEDDING_DIM
    r = c.embeddings.create(**kwargs)
    return r.data[0].embedding


ASSISTANT_ROLES = ("universal", "structuring", "clarifying", "critic", "generator", "synthesizer")


def _extract_theme_prompt(text: str) -> str:
    return f"""Сообщение пользователя: «{text[:600]}»

Извлеки:
1) context_type — chitchat | project
   - chitchat: приветствия («привет», «как дела»), мелкая болтовня, оффтоп, эмоции без идеи
   - project: идеи, планы, темы для обсуждения, запросы к боту
2) theme — краткая ТЕМА для карты идей (без «Отложим», «Продолжим», приветствий). Примеры: «План тренировок», «Автоматическая система написания книг».
3) key_parts — ключевые детали для поиска (1-2 предложения), если есть.
4) action_type: new_thought | request | continuation | defer
   - new_thought: новая идея/тема
   - request: запрос «предложи варианты», «помоги с планом» и т.п.
   - continuation: продолжение предыдущей темы
   - defer: отложить («отложим проект», «потом»)
5) is_continuation: true если явно продолжение («продолжим», «вернёмся к»).
6) parent_hint: тема родителя если понятна из текста, иначе null.
7) project_switch: true если пользователь явно переключается на другую тему («давай теперь про X», «перейдём к Y», «а вот по поводу Z»).
8) suggested_role — по намерению пользователя выбери роль ассистента:
   - generator: «предложи», «варианты», «идеи», «какие есть», «придумай», «сгенерируй»
   - critic: «проверь», «что не так», «критикуй», «риски», «подводные камни»
   - synthesizer: «подведи итог», «суммируй», «сформулируй кратко», «итог»
   - structuring: «разбей», «структура», «подтемы», «как связаны», «декомпозиция»
   - clarifying: «уточни», «что непонятно», «вопросы», «раскрой»
   - universal: иначе

Ответ СТРОГО JSON, без markdown:
{{"context_type": "chitchat|project", "theme": "...", "key_parts": "...", "action_type": "new_thought|request|continuation|defer", "is_continuation": false, "parent_hint": "..." или null, "project_switch": false, "suggested_role": "universal|..."}}
"""


def _parse_extract_theme_response(data: dict, text: str) -> dict:
    theme = (data.get("theme") or "").strip() or text[:80]
    key_parts = (data.get("key_parts") or "").strip()
    action_type = data.get("action_type") or "new_thought"
    if action_type not in ("new_thought", "request", "continuation", "defer"):
        action_type = "new_thought"
    is_continuation = bool(data.get("is_continuation"))
    parent_hint = data.get("parent_hint")
    if parent_hint is not None:
        parent_hint = str(parent_hint).strip() or None
    suggested_role = (data.get("suggested_role") or "universal").strip().lower()
    if suggested_role not in ASSISTANT_ROLES:
        suggested_role = "universal"
    context_type = (data.get("context_type") or "project").strip().lower()
    if context_type not in ("chitchat", "project"):
        context_type = "project"
    project_switch = bool(data.get("project_switch"))
    return {
        "context_type": context_type,
        "theme": theme,
        "key_parts": key_parts,
        "action_type": action_type,
        "is_continuation": is_continuation,
        "parent_hint": parent_hint,
        "project_switch": project_switch,
        "suggested_role": suggested_role,
    }


def extract_theme(text: str) -> dict:
    """
    Извлекает тему и метаданные из сообщения пользователя.
    Возвращает: theme, key_parts, action_type, is_continuation, parent_hint, suggested_role
    """
    text = (text or "").strip()
    if not text:
        return {"context_type": "chitchat", "theme": "", "key_parts": "", "action_type": "new_thought", "is_continuation": False, "parent_hint": None, "project_switch": False, "suggested_role": "universal"}
    if USE_LLM_SERVICE:
        from llm_service.client import submit_json_extract, LLMError
        try:
            data = submit_json_extract(_extract_theme_prompt(text), max_tokens=150)
            return _parse_extract_theme_response(data, text)
        except LLMError:
            return {"context_type": "project", "theme": text[:80], "key_parts": "", "action_type": "new_thought", "is_continuation": False, "parent_hint": None, "project_switch": False, "suggested_role": "universal"}
    c = _client()
    prompt = _extract_theme_prompt(text)
    try:
        r = c.chat.completions.create(
            model=_chat_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        raw = (r.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        data = json.loads(raw)
        return _parse_extract_theme_response(data, text)
    except Exception:
        return {"context_type": "project", "theme": text[:80], "key_parts": "", "action_type": "new_thought", "is_continuation": False, "parent_hint": None, "project_switch": False, "suggested_role": "universal"}


def _classify_topic_prompt(theme: str, last_nodes: list, parent_hint: Optional[str]) -> str:
    nodes_desc = "\n".join(
        f"- id={n.id}: {(n.summary or n.content or '')[:150]}"
        for n in last_nodes
    )
    hint = f"\nПодсказка из сообщения: родитель может быть «{parent_hint}»." if parent_hint else ""
    return f"""Карта мыслей (последние узлы, id нужен для ответа):
{nodes_desc}

Новая тема: «{theme[:300]}»{hint}

Определи:
1) Это НОВАЯ корневая тема — или продолжение/развитие одной из перечисленных?
2) Если связано — укажи parent_id (id узла) и edge_type: continuation | new_topic | refinement

Ответ JSON, без markdown:
{{"parent_id": "id или null", "edge_type": "continuation|new_topic|refinement"}}
"""


def _parse_classify_topic_response(data: dict, last_nodes: list) -> tuple[Optional[str], str]:
    parent_id = data.get("parent_id")
    if parent_id is None or parent_id == "null":
        return None, "continuation"
    edge_type = data.get("edge_type", "continuation")
    if edge_type not in ("continuation", "new_topic", "refinement"):
        edge_type = "continuation"
    valid_ids = {n.id for n in last_nodes}
    if parent_id not in valid_ids:
        return None, "continuation"
    return parent_id, edge_type


def classify_topic(
    theme: str,
    last_nodes: list,
    parent_hint: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """
    Определяет родителя и тип связи по теме.
    Возвращает (parent_node_id, edge_type).
    parent_hint — семантическая подсказка от extract_theme (тема родителя).
    """
    if not last_nodes:
        return None, "continuation"
    if USE_LLM_SERVICE:
        from llm_service.client import submit_json_extract, LLMError
        try:
            prompt = _classify_topic_prompt(theme, last_nodes, parent_hint)
            data = submit_json_extract(prompt, max_tokens=100)
            return _parse_classify_topic_response(data, last_nodes)
        except LLMError:
            return None, "continuation"
    c = _client()
    prompt = _classify_topic_prompt(theme, last_nodes, parent_hint)
    try:
        r = c.chat.completions.create(
            model=_chat_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
        )
        raw = (r.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        data = json.loads(raw)
        return _parse_classify_topic_response(data, last_nodes)
    except Exception:
        return None, "continuation"


def generate_summary(content: str, max_chars: int = 80) -> str:
    """Краткое обобщение мысли для отображения в карте."""
    content = (content or "").strip()
    if not content:
        return ""
    if len(content) <= max_chars:
        return content
    c = _client()
    try:
        r = c.chat.completions.create(
            model=_chat_model(),
            messages=[
                {
                    "role": "user",
                    "content": f"Обобщи в одном коротком предложении (до {max_chars} символов) для заголовка в карте идей:\n\n{content[:500]}",
                }
            ],
            max_tokens=50,
        )
        s = (r.choices[0].message.content or "").strip()
        return (s[:max_chars] if s else content[: max_chars - 2] + "…") or content[: max_chars - 2] + "…"
    except Exception:
        return content[: max_chars - 2] + "…"


def infer_status(text: str, action_type: str) -> str:
    """По контексту сообщения определяет статус узла. Пока простой маппинг."""
    text_lower = (text or "").lower()
    if "отлож" in text_lower or "потом" in text_lower or action_type == "defer":
        return "deferred"
    if "принят" in text_lower or "сделаем" in text_lower or "да, так" in text_lower:
        return "accepted"
    if "отклон" in text_lower or "не надо" in text_lower:
        return "rejected"
    if "в работе" in text_lower or "делаем" in text_lower:
        return "in_progress"
    return "idea"


_ROLE_SYSTEM_ADDITIONS = {
    "universal": "",
    "structuring": (
        "Роль: Структуризатор. Твоя задача — разбивать темы на подтемы, показывать связи, "
        "декомпозицию. Отвечай в виде списков, дерева или чёткой структуры."
    ),
    "clarifying": (
        "Роль: Уточняющий. Твоя задача — задавать проясняющие вопросы, выявлять неясности. "
        "Сформулируй 1–3 коротких вопроса, которые помогут лучше понять замысел пользователя."
    ),
    "critic": (
        "Роль: Критик. Твоя задача — проверить идею, найти риски, подводные камни, слабые места. "
        "Будь конструктивным, но честным. Укажи конкретные моменты для доработки."
    ),
    "generator": (
        "Роль: Генератор. Твоя задача — предлагать варианты, идеи, направления. "
        "Дай несколько конкретных предложений, не ограничивайся одним ответом."
    ),
    "synthesizer": (
        "Роль: Синтезатор. Твоя задача — подвести итог, суммировать, сформулировать кратко. "
        "Сведи разрозненное в единый вывод или тезис."
    ),
}


def universal_assistant(
    query: str,
    user_id: int,
    rag_context: list[dict],
    graph_context: list[dict],
    role: str = "universal",
) -> str:
    """Агент-помощник: ответ по запросу с учётом RAG и графа. role — suggested_role из extract_theme."""
    rag_block = "\n".join(
        f"- {x.get('text', '').strip()}" for x in rag_context if x.get("text")
    ) or "(нет релевантных записей)"
    graph_block = "\n".join(
        f"- {n.get('content', '').strip()}" for n in graph_context
    ) or "(нет недавних тем)"
    role_add = _ROLE_SYSTEM_ADDITIONS.get(role, "") or _ROLE_SYSTEM_ADDITIONS["universal"]
    base = (
        "Ты помощник по карте идей пользователя. Отвечай кратко и по делу, на русском. "
        f"Ограничь ответ {MAX_REPLY_CHARS} символами."
    )
    system = f"{role_add}\n\n{base}" if role_add else base
    user_msg = (
        "Релевантные мысли пользователя из базы:\n"
        f"{rag_block}\n\n"
        "Недавние темы пользователя:\n"
        f"{graph_block}\n\n"
        f"Сообщение пользователя: {query}"
    )
    if USE_LLM_SERVICE:
        from llm_service.client import submit_chat, LLMError
        try:
            reply = submit_chat(system, user_msg, max_tokens=1500, role_hint=role)
            return reply[:MAX_REPLY_CHARS] if reply else "Мысль принята, контекст учтён."
        except LLMError as e:
            return f"Временная ошибка, попробуй позже. ({type(e).__name__})"
    c = _client()
    try:
        r = c.chat.completions.create(
            model=_chat_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1500,
        )
        reply = (r.choices[0].message.content or "").strip()
        return reply[:MAX_REPLY_CHARS] if reply else "Мысль принята, контекст учтён."
    except Exception as e:
        return f"Временная ошибка, попробуй позже. ({type(e).__name__})"
