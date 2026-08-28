"""Planner: план → выполнение MCP tools → синтез ответа."""

import asyncio
import json
import logging
import re

logger = logging.getLogger("planner")


from typing import Any, Callable

from shared.llm import MAX_REPLY_CHARS, _ROLE_SYSTEM_ADDITIONS

from planner.prompts import build_plan_prompt, build_synthesize_system, build_synthesize_user


PLAN_MAX_TOKENS = 2000


def _call_llm_json(prompt: str, max_tokens: int = PLAN_MAX_TOKENS) -> dict:
    """Вызов LLM для JSON (через llm_service или напрямую)."""
    from shared.llm import USE_LLM_SERVICE
    if USE_LLM_SERVICE:
        from llm_service.client import submit_json_extract, LLMError
        try:
            return submit_json_extract(prompt, max_tokens=max_tokens)
        except LLMError as e:
            raise RuntimeError(str(e)) from e
    from shared.llm import _client, _chat_model
    r = _client().chat.completions.create(
        model=_chat_model(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    raw = (r.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


def _call_llm_chat(system: str, user: str, max_tokens: int = 1500) -> str:
    """Вызов LLM для чата."""
    from shared.llm import USE_LLM_SERVICE
    if USE_LLM_SERVICE:
        from llm_service.client import submit_chat, LLMError
        try:
            return submit_chat(system, user, max_tokens=max_tokens)
        except LLMError as e:
            raise RuntimeError(str(e)) from e
    from shared.llm import _client, _chat_model
    r = _client().chat.completions.create(
        model=_chat_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    return (r.choices[0].message.content or "").strip()


async def _run_planner_async(
    query: str,
    rag_context: list[dict],
    graph_context: list[dict],
    role: str = "universal",
    user_id: int | None = None,
    debug_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Async core: MCP + plan + execute + synthesize."""
    from mcp_hub import MCPHub, get_tools_catalog

    hub = MCPHub()
    if not hub.server_names:
        logger.warning("planner: no MCP servers configured, hub.server_names=%s", hub.server_names)
        return None
    try:
        catalog = await get_tools_catalog(hub)
    except Exception as e:
        logger.exception("planner: get_tools_catalog failed: %s", e)
        return None
    if not catalog:
        logger.warning("planner: empty catalog, fallback to assistant")
        return None

    plan_prompt = build_plan_prompt(query, catalog, user_id=user_id)
    if debug_callback:
        try:
            debug_callback(plan_prompt)
        except Exception:
            pass

    plan_data = None
    for attempt in range(3):
        try:
            plan_data = _call_llm_json(plan_prompt, max_tokens=PLAN_MAX_TOKENS)
            break
        except (RuntimeError, json.JSONDecodeError) as e:
            logger.warning("planner: LLM plan attempt %d failed: %s", attempt + 1, e)
            if attempt == 2:
                logger.exception("planner: LLM plan failed after 3 attempts")
                return None

    if not plan_data:
        return None

    calls = plan_data.get("calls") or []
    if not calls:
        logger.info("planner: no tool calls in plan, fallback")
        return None

    logger.info("planner: executing %d tool calls: %s", len(calls[:20]), [f"{c.get('server')}.{c.get('tool')}" for c in calls[:20]])
    tool_results: list[dict[str, Any]] = []
    for call in calls[:20]:  # макс 20 вызовов
        server = call.get("server")
        tool = call.get("tool")
        args = dict(call.get("arguments") or {})
        if not server or not tool:
            continue
        if server == "mindmap" and user_id is not None:
            args["user_id"] = user_id
        try:
            await hub.connect(server)
            result = await hub.call_tool(server, tool, args)
            tool_results.append({"tool": f"{server}.{tool}", "result": result})
        except Exception as e:
            logger.warning("planner: call_tool %s.%s failed: %s", server, tool, e)
            tool_results.append({"tool": f"{server}.{tool}", "result": f"Ошибка: {e}"})

    await hub.disconnect()

    if not tool_results:
        return None

    rag_block = "\n".join(
        f"- {x.get('text', '').strip()}" for x in rag_context if x.get("text")
    )
    graph_block = "\n".join(
        f"- {n.get('content', '').strip()}" for n in graph_context
    )
    role_add = _ROLE_SYSTEM_ADDITIONS.get(role, "") or _ROLE_SYSTEM_ADDITIONS["universal"]
    system = build_synthesize_system(role_add or "Ты помощник.")
    user_msg = build_synthesize_user(query, tool_results, rag_block, graph_block)

    try:
        reply = _call_llm_chat(system, user_msg, max_tokens=1500)
        return (reply or "Результаты получены.")[:MAX_REPLY_CHARS]
    except Exception:
        return None


def run_planner(
    query: str,
    rag_context: list[dict],
    graph_context: list[dict],
    role: str = "universal",
    user_id: int | None = None,
    debug_callback: Callable[[str], None] | None = None,
) -> str | None:
    """
    Запуск planner: MCP tools + LLM план + выполнение + синтез.
    user_id — для mindmap tools. debug_callback(text) — при USE_DEBUG отправит план в Telegram.
    """
    try:
        return asyncio.run(_run_planner_async(query, rag_context, graph_context, role, user_id, debug_callback))
    except Exception:
        return None
