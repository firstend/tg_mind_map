"""Роутинг запросов: tools_request / new_thought / chitchat."""

import os

PLANNER_KEYWORDS = [
    # Filesystem
    "прочитай", "прочти", "открой файл", "посмотри файл", "покажи файл",
    "read file", "list dir", "посмотри папку", "содержимое папки", "list directory",
    "создай файл", "запиши в файл", "write file", "запиши файл",
    "открой папку", "покажи папку",
    # Web search
    "найди в интернете", "поищи в интернете", "загугли", "найди информацию",
    "search for", "find online", "поиск в сети", "что пишут про",
    "найди про", "найди сайт", "поищи про", "поиск про", "найди новости",
    "что нового про", "узнай про", "информация про",
    # Fetch URL
    "открой ссылку", "загрузи страницу", "fetch url", "прочитай url",
    "что на сайте", "содержимое страницы", "открой url",
    # Time
    "который час", "сколько времени", "текущее время", "какой сейчас час",
    "current time", "what time", "время в", "время сейчас",
]


def route_request(text: str) -> str:
    """
    Классифицирует запрос пользователя.

    Returns:
        "tools_request" — нужен planner (MCP tools: файлы, папки)
        "new_thought" — обычная мысль/идея → пайплайн граф+RAG
        "chitchat" — болтовня (приветствие, благодарность)
    """
    t = (text or "").strip().lower()
    if not t:
        return "chitchat"

    router = os.environ.get("USE_PLANNER_AUTO_ROUTER", "keywords").lower()
    if router == "llm":
        return _route_via_llm(t)
    return _route_via_keywords(t)


def _route_via_keywords(text: str) -> str:
    """Роутинг по ключевым словам."""
    for kw in PLANNER_KEYWORDS:
        if kw in text:
            return "tools_request"
    # Простые приветствия/болтовня
    chitchat_starts = ("привет", "здравствуй", "хай", "спасибо", "благодарю", "ок", "окей")
    if any(text.startswith(s) for s in chitchat_starts) and len(text.split()) <= 3:
        return "chitchat"
    return "new_thought"


def _route_via_llm(text: str) -> str:
    """Роутинг через LLM (более точный)."""
    try:
        from shared.llm import USE_LLM_SERVICE
        if USE_LLM_SERVICE:
            from llm_service.client import submit_json_extract, LLMError
            prompt = f"""Классифицируй запрос пользователя в один из типов:
- tools_request: пользователь просит прочитать/записать файл, посмотреть папку, найти что-то в интернете, загрузить URL, узнать время
- chitchat: приветствие, благодарность, общий вопрос без конкретной задачи
- new_thought: идея, мысль, вопрос по карте идей (не требует внешних инструментов)

Запрос: {text}

Ответь JSON: {{"type": "tools_request"}} или {{"type": "chitchat"}} или {{"type": "new_thought"}}"""
            result = submit_json_extract(prompt, schema_hint='{"type": "string"}', max_tokens=50)
            t = (result.get("type") or "new_thought").lower()
            if t in ("tools_request", "chitchat", "new_thought"):
                return t
            return "new_thought"
        # Fallback: без llm_service — keywords
    except Exception:
        pass
    return _route_via_keywords(text)
