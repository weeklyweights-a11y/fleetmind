"""LLM Call 2: response synthesis with streaming."""

from __future__ import annotations

import json

from app.chat.dispatch import build_tools_used, results_for_synthesis
from app.chat.prompts import load_prompt
from app.chat.schemas import ChatGraphState, ToolsUsedEntry
from app.chat.streaming import WsStreamCallback
from app.services.gemini_client import generate_text, stream_text


def build_synthesis_prompt(state: ChatGraphState) -> str:
    base = load_prompt("response_synthesis.txt")
    qu = state.get("query_understanding")
    profile = state.get("operator_profile")
    dashboard = state.get("dashboard_context")
    results = results_for_synthesis(state.get("sub_agent_results") or {})
    ctx = state.get("conversation_context")
    proactive = state.get("proactive_alerts")
    if proactive is None and ctx is not None:
        proactive = getattr(ctx, "proactive_alerts", None) or []
    proactive = proactive or []
    return "\n\n".join(
        [
            base,
            f"Operator message: {state.get('message', '')}",
            f"Intent: {qu.intent if qu else ''}",
            f"Entities: {json.dumps([e.model_dump(mode='json') for e in (qu.entities if qu else [])], indent=2)}",
            f"Response guidance: {qu.response_guidance if qu else ''}",
            f"Operator style: {profile.preferred_response_style if profile else 'balanced'}",
            f"Dashboard: {dashboard.model_dump(mode='json') if dashboard else {}}",
            f"Proactive alerts: {json.dumps(proactive, indent=2)}",
            f"Sub-agent results:\n{json.dumps(results, indent=2)}",
        ]
    )


def fallback_markdown(results: dict) -> str:
    lines = ["Here is what I found from the data:"]
    for name, res in (results or {}).items():
        status = res.status if hasattr(res, "status") else res.get("status")
        if status == "error":
            lines.append(f"- **{name}**: unavailable ({getattr(res, 'error', res.get('error'))})")
        else:
            lines.append(f"- **{name}**: see data below")
            payload = res.result if hasattr(res, "result") else res.get("result")
            lines.append(f"```\n{json.dumps(payload, indent=2)[:1500]}\n```")
    return "\n".join(lines)


async def synthesize_and_stream(state: ChatGraphState, callback: WsStreamCallback) -> tuple[str, list[ToolsUsedEntry]]:
    qu = state.get("query_understanding")
    plan = qu.dispatch_plan if qu else []
    results = state.get("sub_agent_results") or {}
    tools = build_tools_used(plan, results)
    prompt = build_synthesis_prompt(state)
    buffer = ""
    try:
        async for delta in stream_text(prompt):
            buffer += delta
            await callback.send_delta(delta)
    except Exception:
        buffer = fallback_markdown(results)
        await callback.send_delta(buffer)
    tools_payload = [t.model_dump(mode="json") for t in tools]
    await callback.send_done(tools_payload)
    return buffer, tools
