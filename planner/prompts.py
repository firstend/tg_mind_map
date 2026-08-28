"""Промпты для planner: plan (выбор tools) и synthesize (итоговый ответ)."""


def build_plan_prompt(query: str, tools_catalog: list[dict], user_id: int | None = None) -> str:
    """Промпт для LLM: решить, какие tools вызвать."""
    tools_desc = "\n".join(
        f"- server={t['server']}, tool={t['name']}: {t.get('description', '')}"
        for t in tools_catalog
    )
    user_hint = ""
    if user_id is not None:
        user_hint = f"\nuser_id текущего пользователя: {user_id}. Для всех mindmap_* tools (server=mindmap) ОБЯЗАТЕЛЬНО добавляй \"user_id\": {user_id} в arguments.\n"
    return f"""Доступные инструменты (tools):
{tools_desc}

Запрос пользователя: «{query[:500]}»
{user_hint}
Если для ответа нужны инструменты — верни JSON-план вызовов.
Формат: {{"calls": [{{"server": "имя_сервера", "tool": "имя_tool", "arguments": {{...}}}}, ...]}}

Важно для аргументов:
- timezone: используй IANA формат (Europe/Moscow, Asia/Tokyo, America/New_York, Europe/London)
- url: полный URL с протоколом (https://example.com)
- path: абсолютный путь к файлу (/tmp/file.txt)

Если инструменты не нужны — верни {{"calls": []}}

Ответ СТРОГО JSON, без markdown."""


def build_plan_step_prompt(
    state: "StepState",
    tools_catalog: list[dict],
    max_result_chars: int = 2500,
    user_id: int | None = None,
) -> str:
    """Промпт для одного шага мультишагового планирования."""
    tools_desc = "\n".join(
        f"- server={t['server']}, tool={t['name']}: {t.get('description', '')}"
        for t in tools_catalog
    )

    results_block = "(пока нет)"
    if state.results:
        parts = []
        for i, r in enumerate(state.results, 1):
            label = f"{r.server}.{r.tool}"
            if r.refined_prompt:
                parts.append(f"{i}. {label} (refined: {r.refined_prompt})")
            else:
                parts.append(f"{i}. {label}")
            text = (r.result or "")[:max_result_chars]
            if len(r.result or "") > max_result_chars:
                text += "\n[... обрезано ...]"
            parts.append(f"   Результат: {text}")
        results_block = "\n".join(parts)

    remaining = state.remaining_goal or "всё выполнено"
    if not state.results:
        remaining = state.original_query

    user_hint = ""
    if user_id is not None:
        user_hint = f"\nuser_id текущего пользователя: {user_id}. Для mindmap_* tools добавляй \"user_id\": {user_id} в arguments.\n"

    return f"""Ты планировщик задач. Запрос пользователя: «{state.original_query[:400]}»
{user_hint}

Результаты предыдущих шагов:
{results_block}

Что осталось сделать: {remaining}

Доступные инструменты:
{tools_desc}

Твоя задача:
1. Решить: нужен ли ещё один вызов инструмента? Если всё сделано — верни action: "done"
2. Если нужен вызов — планируй ОДИН вызов за шаг (server, tool, arguments)
3. УЛУЧШЬ аргументы: преврати в профессиональный промпт, сохраняя суть. Примеры:
   - "найди про X" → query: "X: определение, применение, последние исследования"
   - content для write_file: используй результат предыдущего шага, структурируй и сократи

Формат ответа (JSON):
{{"action": "call" или "done", "reasoning": "краткое обоснование", "remaining_goal": "что осталось",
 "call": {{"server": "...", "tool": "...", "arguments": {{...}}, "refined_prompt": "описание улучшения"}}}}

При action: "done" поле call не указывай.

Важно: timezone=Europe/Moscow; url=https://...; path=/tmp/...

Ответ СТРОГО JSON, без markdown."""


def build_synthesize_system(role_add: str) -> str:
    return f"""{role_add}

Ты помощник по карте идей. Пользователь задал вопрос, ты получил результаты вызова инструментов (tools).
Сформируй краткий ответ на русском на основе этих результатов. До 1000 символов."""


def build_synthesize_user(
    query: str,
    tool_results: list[dict],
    rag_block: str,
    graph_block: str,
) -> str:
    parts = [
        f"Запрос пользователя: {query}",
        "",
        "Результаты инструментов:",
    ]
    for i, r in enumerate(tool_results, 1):
        parts.append(f"{i}. {r.get('tool', '?')} → {r.get('result', str(r))[:500]}")
    parts.extend([
        "",
        "Релевантные мысли из базы:",
        rag_block or "(нет)",
        "",
        "Недавние темы:",
        graph_block or "(нет)",
        "",
        "Дай итоговый ответ пользователю:",
    ])
    return "\n".join(parts)
