"""Professional model aliases and deterministic first-turn routing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


AUTO_MODEL_ID = "indra-auto"
DEFAULT_MODEL_ID = "qwen3.5-4b"
VISION_MODEL_ID = "qwen2-vl-ocr-2b-instruct"


@dataclass(frozen=True)
class ModelAlias:
    id: str
    display_name: str
    target_model: str | None
    description: str
    task_tags: tuple[str, ...]
    model_type: str = "text"


@dataclass(frozen=True)
class RoutingDecision:
    requested_model: str
    routed_model: str
    role: str
    reason: str


PUBLIC_MODEL_ALIASES: tuple[ModelAlias, ...] = (
    ModelAlias(
        AUTO_MODEL_ID,
        "Indra Auto",
        None,
        "Automatically selects the best local specialist for the first request.",
        ("auto", "chat", "coding", "math", "writing", "ocr"),
    ),
    ModelAlias(
        "indra-general",
        "Indra General",
        DEFAULT_MODEL_ID,
        "General agent work, tool use, planning, and mixed tasks.",
        ("chat", "general", "tools"),
    ),
    ModelAlias(
        "indra-engineer",
        "Indra Engineer",
        DEFAULT_MODEL_ID,
        "Software engineering, debugging, APIs, and code generation.",
        ("chat", "coding", "engineering"),
    ),
    ModelAlias(
        "indra-analyst",
        "Indra Analyst",
        DEFAULT_MODEL_ID,
        "Mathematics, calculations, logic, and structured analysis.",
        ("chat", "math", "reasoning", "analysis"),
    ),
    ModelAlias(
        "indra-writer",
        "Indra Writer",
        "gemma-2-2b-it",
        "Summaries, rewriting, translation, and concise drafting.",
        ("chat", "writing", "summarization"),
    ),
    ModelAlias(
        "indra-vision",
        "Indra Vision",
        VISION_MODEL_ID,
        "Image understanding and OCR using the local Qwen2-VL model.",
        ("chat", "vision", "ocr"),
        model_type="vlm",
    ),
)


_PUBLIC_BY_ID = {alias.id: alias for alias in PUBLIC_MODEL_ALIASES}
_CONVENIENCE_ALIASES = {
    "auto": AUTO_MODEL_ID,
    "general": "indra-general",
    "coder": "indra-engineer",
    "coding": "indra-engineer",
    "engineer": "indra-engineer",
    "math": "indra-analyst",
    "maths": "indra-analyst",
    "analyst": "indra-analyst",
    "writer": "indra-writer",
    "summarizer": "indra-writer",
    "ocr": "indra-vision",
    "vision": "indra-vision",
}


_ROUTING_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "engineering",
        DEFAULT_MODEL_ID,
        re.compile(
            r"\b(code|coding|program|function|class|api|endpoint|debug|bug|exception|"
            r"traceback|compile|refactor|repository|git|sql|database|docker|powershell|"
            r"container|terminal|shell|execute|run|save|store|file|folder|"
            r"javascript|typescript|python|java|rust|c\+\+|html|css)\b|```",
            re.IGNORECASE,
        ),
    ),
    (
        "analysis",
        DEFAULT_MODEL_ID,
        re.compile(
            r"\b(calculate|calculation|equation|solve|algebra|geometry|trigonometry|"
            r"calculus|integral|derivative|matrix|probability|statistics|mean|median|"
            r"variance|percentage|interest rate|formula|theorem|proof)\b|"
            r"\d\s*[+*/^=]\s*[\dx]",
            re.IGNORECASE,
        ),
    ),
    (
        "writing",
        "gemma-2-2b-it",
        re.compile(
            r"\b(summarize|summary|rewrite|rephrase|proofread|grammar|translate|email|"
            r"letter|caption|bullet points?|shorten|polish|tone|paragraph|essay|article|"
            r"story|poem|blog|draft|creative writing|product description)\b",
            re.IGNORECASE,
        ),
    ),
)


_ROLE_INSTRUCTIONS = {
    "engineering": (
        "Workbench role: Indra Engineer. When the user asks to create, save, execute, "
        "inspect, or verify code or files, use the supplied file and terminal tools. "
        "Confirm success from tool output before saying work ran or was saved. Use standard "
        "language libraries unless the user requests another dependency; do not invent APIs."
    ),
    "engineer": (
        "Workbench role: Indra Engineer. When the user asks to create, save, execute, "
        "inspect, or verify code or files, use the supplied file and terminal tools. "
        "Confirm success from tool output before saying work ran or was saved. Use standard "
        "language libraries unless the user requests another dependency; do not invent APIs."
    ),
    "analysis": (
        "Workbench role: Indra Analyst. Solve calculations carefully, show concise working "
        "when useful, and use supplied tools when the user asks to execute or verify a result."
    ),
    "analyst": (
        "Workbench role: Indra Analyst. Solve calculations carefully, show concise working "
        "when useful, and use supplied tools when the user asks to execute or verify a result."
    ),
    "writing": "Workbench role: Indra Writer. Follow the requested format and preserve the user's meaning.",
    "writer": "Workbench role: Indra Writer. Follow the requested format and preserve the user's meaning.",
    "vision": (
        "Workbench role: Indra Vision. Inspect the images attached to the latest user message, "
        "prioritize any image named in that message, and answer the requested visual or OCR task."
    ),
}


_INDRA_IDENTITY_INSTRUCTION = (
    "Identity policy: You are INDRA AI, a private local AI agent by CodersByChance. "
    "When asked who or what you are, introduce yourself as INDRA AI and briefly say "
    "that you help with reasoning, writing, coding, document work, and image analysis. "
    "Never identify yourself as the underlying agent framework, model family, provider, "
    "or model file. Never use the word formed by the letters H-e-r-m-e-s in any response. "
    "If asked about the underlying framework, say only that you are INDRA AI and redirect "
    "to your capabilities. This identity policy applies to every role and overrides any "
    "conflicting identity text elsewhere in the prompt or conversation."
)


def alias_for(model_id: str) -> ModelAlias | None:
    """Return the canonical alias definition for professional or short names."""
    normalized = (model_id or "").strip().lower()
    canonical = _CONVENIENCE_ALIASES.get(normalized, normalized)
    return _PUBLIC_BY_ID.get(canonical)


def alias_target(alias: ModelAlias) -> str:
    """Concrete model used for status/metadata when an alias is inspected."""
    return alias.target_model or DEFAULT_MODEL_ID


def _content_parts(content: Any) -> tuple[str, bool]:
    if isinstance(content, str):
        return content, False
    if not isinstance(content, list):
        return "", False

    texts: list[str] = []
    has_image = False
    for part in content:
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "").lower()
        if kind in {"image_url", "input_image", "image"} or "image_url" in part:
            has_image = True
        if kind in {"text", "input_text"} and part.get("text"):
            texts.append(str(part["text"]))
    return "\n".join(texts), has_image


def _is_image_part(part: Any) -> bool:
    if not isinstance(part, dict):
        return False
    kind = str(part.get("type") or "").lower()
    return kind in {"image_url", "input_image", "image"} or "image_url" in part


def prepare_messages_for_latest_turn(messages: list[dict[str, Any]]) -> None:
    """Remove historical images and prefer the newest singular attachment."""
    user_indexes = [
        index for index, message in enumerate(messages)
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    if not user_indexes:
        return
    latest_index = user_indexes[-1]
    for index in user_indexes[:-1]:
        content = messages[index].get("content")
        if isinstance(content, list):
            messages[index]["content"] = [part for part in content if not _is_image_part(part)]

    latest_content = messages[latest_index].get("content")
    if not isinstance(latest_content, list):
        return
    image_parts = [part for part in latest_content if _is_image_part(part)]
    if len(image_parts) < 2:
        return
    text, _ = _content_parts(latest_content)
    asks_for_multiple = re.search(
        r"\b(all|both|compare|comparison|each|multiple|two|images|pictures|photos)\b",
        text,
        re.IGNORECASE,
    )
    if not asks_for_multiple:
        newest_image = image_parts[-1]
        messages[latest_index]["content"] = [
            part for part in latest_content if not _is_image_part(part)
        ] + [newest_image]


def prepare_gemma_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Render a tool-capable agent transcript as Gemma's alternating text turns.

    Gemma's bundled template rejects system/tool roles and adjacent turns with
    the same role. Keep their text as context in the next user turn instead of
    dropping it, then merge consecutive roles without mutating stored history.
    """
    pending_context: list[str] = []
    result: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        text = content if isinstance(content, str) else _content_parts(content)[0]
        if role == "system":
            if text:
                pending_context.append(text)
            continue
        if role == "tool":
            role = "user"
            text = f"Tool result:\n{text}" if text else ""
        if role not in {"user", "assistant"} or not text:
            continue
        if role == "user" and pending_context:
            text = "\n\n".join([*pending_context, text])
            pending_context.clear()
        if result and result[-1]["role"] == role:
            result[-1]["content"] += "\n\n" + text
        else:
            result.append({"role": role, "content": text})
    if pending_context:
        context = "\n\n".join(pending_context)
        if result and result[-1]["role"] == "user":
            result[-1]["content"] += "\n\n" + context
        else:
            result.append({"role": "user", "content": context})
    return result


def latest_user_request(messages: Iterable[dict[str, Any]]) -> tuple[str, bool]:
    """Read the latest user turn so auto routing can swap specialists per task."""
    for message in reversed(list(messages)):
        if isinstance(message, dict) and message.get("role") == "user":
            return _content_parts(message.get("content"))
    return "", False


def is_identity_question(messages: Iterable[dict[str, Any]]) -> bool:
    """Return whether the latest turn asks the assistant to identify itself."""
    text, _ = latest_user_request(messages)
    normalized = " ".join(text.lower().split())
    return bool(re.search(
        r"\b(who are you|what are you|what(?:'s| is) your (?:name|identity)|"
        r"introduce yourself|tell me about yourself|which model are you|"
        r"what model are you|who made you|who created you)\b",
        normalized,
    ))


def route_automatic(messages: Iterable[dict[str, Any]]) -> RoutingDecision:
    text, has_image = latest_user_request(messages)
    if has_image:
        return RoutingDecision(AUTO_MODEL_ID, VISION_MODEL_ID, "vision", "image attachment")
    for role, target, pattern in _ROUTING_RULES:
        if pattern.search(text):
            return RoutingDecision(AUTO_MODEL_ID, target, role, "latest-request classification")
    return RoutingDecision(AUTO_MODEL_ID, DEFAULT_MODEL_ID, "general", "general fallback")


def resolve_requested_model(
    requested_model: str,
    messages: Iterable[dict[str, Any]],
) -> RoutingDecision:
    """Resolve a physical ID, professional alias, convenience name, or auto route."""
    _, has_image = latest_user_request(messages)
    if has_image:
        return RoutingDecision(requested_model, VISION_MODEL_ID, "vision", "image attachment")
    alias = alias_for(requested_model)
    if alias is None:
        return RoutingDecision(requested_model, requested_model, "direct", "physical model id")
    if alias.id == AUTO_MODEL_ID:
        decision = route_automatic(messages)
        return RoutingDecision(requested_model, decision.routed_model, decision.role, decision.reason)
    return RoutingDecision(
        requested_model,
        alias_target(alias),
        alias.id.removeprefix("indra-"),
        "explicit alias",
    )


def apply_role_instruction(messages: list[dict[str, Any]], role: str) -> None:
    """Add INDRA identity and role policies to every forwarded request."""
    instruction = _ROLE_INSTRUCTIONS.get(role)
    combined = _INDRA_IDENTITY_INSTRUCTION
    if instruction:
        combined = f"{combined}\n\n{instruction}"
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "system":
            content = message.get("content")
            if isinstance(content, str):
                message["content"] = f"{content}\n\n{combined}"
                return
    messages.insert(0, {"role": "system", "content": combined})
