"""Мультишаговый planner: итеративное планирование с цепочкой tools."""

import asyncio
import json
import logging
import re
from typing import Any, Callable

from planner.state import StepState, ToolResult
from planner.prompts import build_plan_step_prompt, build_synthesize_system, build_synthesize_user
from shared.llm import MAX_REPLY_CHARS, _ROLE_SYSTEM_ADDITIONS

logger = logging.getLogger("planner")

PLAN_MAX_TOKENS = 2000


def _call_llm_json(prompt: str, max_tokens: int = PLAN_MAX_TOKENS) -> dict:
    """Вызов LLM для JSON."""
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


async def _run_multistep_async(
    query: str,
    rag_context: list[dict],
    graph_context: list[dict],
    role: str = "universal",
    max_steps: int = 20,
    user_id: int | None = None,
    debug_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Async: итеративное планирование → выполнение → синтез."""
    from mcp_hub import MCPHub, get_tools_catalog

    hub = MCPHub()
    if not hub.server_names:
        logger.warning("multistep: no MCP servers configured")
        return None
    try:
        catalog = await get_tools_catalog(hub)
    except Exception as e:
        logger.exception("multistep: get_tools_catalog failed: %s", e)
        return None
    if not catalog:
        logger.warning("multistep: empty catalog")
        return None

    state = StepState(
        original_query=query,
        results=[],
        remaining_goal=query,
        step_number=0,
        max_steps=max_steps,
    )

    while not state.is_done:
        state.step_number += 1
        prompt = build_plan_step_prompt(state, catalog, user_id=user_id)

        if debug_callback:
            try:
                debug_callback(prompt)
            except Exception:
                pass

        plan_data = None
        for attempt in range(3):
            try:
                plan_data = _call_llm_json(prompt, max_tokens=PLAN_MAX_TOKENS)
                break
            except (RuntimeError, json.JSONDecodeError) as e:
                logger.warning("multistep: step %d attempt %d failed: %s", state.step_number, attempt + 1, e)
                if attempt == 2:
                    logger.exception("multistep: LLM plan step %d failed after 3 attempts", state.step_number)
                    plan_data = {"action": "done"}
                    break
        if not plan_data:
            break

        action = (plan_data.get("action") or "done").lower()
        state.remaining_goal = (plan_data.get("remaining_goal") or "").strip()
        reasoning = plan_data.get("reasoning", "")

        if action == "done":
            logger.info("multistep: done at step %d, reasoning=%s", state.step_number, reasoning[:80])
            break

        call = plan_data.get("call")
        if not call or not isinstance(call, dict):
            logger.warning("multistep: action=call but no valid call, breaking")
            break

        server = call.get("server")
        tool = call.get("tool")
        args = dict(call.get("arguments") or {})
        refined_prompt = call.get("refined_prompt") or ""

        if not server or not tool:
            logger.warning("multistep: missing server/tool in call")
            continue
        if server == "mindmap" and user_id is not None:
            args["user_id"] = user_id

        logger.info(
            "multistep: step %d %s.%s args_keys=%s refined=%s",
            state.step_number, server, tool, list(args.keys()), refined_prompt[:60] if refined_prompt else "",
        )

        try:
            await hub.connect(server)
            result = await hub.call_tool(server, tool, args)
        except Exception as e:
            logger.warning("multistep: call_tool %s.%s failed: %s", server, tool, e)
            result = f"Ошибка: {e}"
        finally:
            await hub.disconnect()

        state.results.append(ToolResult(
            server=server,
            tool=tool,
            args_used=args,
            refined_prompt=refined_prompt or None,
            result=str(result) if result else "",
        ))

    if not state.results:
        logger.info("multistep: no tool results, fallback")
        return None

    tool_results = [
        {"tool": f"{r.server}.{r.tool}", "result": r.result}
        for r in state.results
    ]
    rag_block = "\n".join(
        f"- {x.get('text', '').strip()}" for x in rag_context if x.get("text")
    )
    graph_block = "\n".join(
        f"- {n.get('content', '').strip()}" for n in graph_context
    )
    role_add = _ROLE_SYSTEM_ADDITIONS.get(role, "") or _ROLE_SYSTEM_ADDITIONS["universal"]
    system = build_synthesize_system(role_add or "Ты помощник.")
    user_msg = build_synthesize_user(
        state.original_query, tool_results, rag_block, graph_block
    )

    try:
        reply = _call_llm_chat(system, user_msg, max_tokens=1500)
        return (reply or "Результаты получены.")[:MAX_REPLY_CHARS]
    except Exception as e:
        logger.exception("multistep: synthesize failed: %s", e)
        return None


def run_planner_multistep(
    query: str,
    rag_context: list[dict],
    graph_context: list[dict],
    role: str = "universal",
    max_steps: int = 20,
    user_id: int | None = None,
    debug_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Запуск мультишагового planner. debug_callback(text) — при USE_DEBUG отправит план в Telegram."""
    try:
        return asyncio.run(
            _run_multistep_async(query, rag_context, graph_context, role, max_steps, user_id, debug_callback)
        )
    except Exception:
        return None
