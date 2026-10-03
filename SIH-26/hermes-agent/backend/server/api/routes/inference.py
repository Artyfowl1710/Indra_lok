"""
Chat completions + embeddings — OpenAI-compatible.

Routes requests to the correct backend based on the model registry.
"""
from __future__ import annotations

import logging
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from server.backends import llamaswap as ls_driver
from server.backends import vllm_driver, onnx_driver
from server.core.auth import require_admin
from server.core.lifecycle import lifecycle
from server.core.model_routing import (
    apply_role_instruction,
    is_identity_question,
    prepare_messages_for_latest_turn,
    prepare_gemma_messages,
    resolve_requested_model,
)
from server.core.schemas import ChatCompletionRequest, EmbeddingRequest
from server.db import ApiKey, ModelRecord, get_db

log = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])

_INDRA_IDENTITY_REPLY = (
    "I'm INDRA AI, a private local AI agent by CodersByChance, built to help "
    "with reasoning, writing, coding, document work, and image analysis."
)


def _identity_stream(model: str):
    created = int(time.time())
    first = {
        "id": "chatcmpl-indra-identity",
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": _INDRA_IDENTITY_REPLY},
            "finish_reason": None,
        }],
    }
    final = {
        "id": "chatcmpl-indra-identity",
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(first)}\n\n".encode()
    yield f"data: {json.dumps(final)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def _get_model_or_404(model_id: str, db: Session) -> ModelRecord:
    m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()

    if m is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model {model_id!r} not registered",
        )

    return m


# ── chat completions ──────────────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    log.info("Chat request received: model=%s stream=%s", req.model, req.stream)

    body = req.model_dump(exclude_none=True)
    decision = resolve_requested_model(req.model, body.get("messages", []))
    routed_model = decision.routed_model
    m = _get_model_or_404(routed_model, db)

    # Identity is a product-level contract. Handle it here so every physical
    # model and professional alias gives exactly the same branded answer.
    if is_identity_question(body.get("messages", [])):
        if req.stream:
            return StreamingResponse(
                _identity_stream(req.model),
                media_type="text/event-stream",
                headers={
                    "X-Workbench-Requested-Model": req.model,
                    "X-Workbench-Routed-Model": routed_model,
                    "X-Workbench-Route": decision.role,
                },
            )
        return {
            "id": "chatcmpl-indra-identity",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": _INDRA_IDENTITY_REPLY},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    if routed_model != req.model:
        log.info(
            "Model route selected: requested=%s routed=%s role=%s reason=%s",
            req.model,
            routed_model,
            decision.role,
            decision.reason,
        )

    log.info(
        "Model resolved: id=%s backend=%s status=%s",
        m.id,
        m.backend,
        m.status,
    )

    # Ensure model is loaded and mark this request as active.
    async with lifecycle.track_request(routed_model):
        log.info("Lifecycle acquired: model=%s", routed_model)

        body["model"] = routed_model
        prepare_messages_for_latest_turn(body.get("messages", []))
        apply_role_instruction(body.get("messages", []), decision.role)
        if routed_model == "gemma-2-2b-it":
            body["messages"] = prepare_gemma_messages(body["messages"])
            body.pop("tools", None)
            body.pop("tool_choice", None)
            body.pop("parallel_tool_calls", None)
        if m.backend == "llamaswap":
            # Keep auxiliary callers within the laptop's output and latency budget.
            body.setdefault("max_tokens", 4096)
            body.setdefault("chat_template_kwargs", {"enable_thinking": False})

            # The bundled Phi-4 GGUF has a known llama.cpp chat-template quirk:
            # supplying an OpenAI ``system`` message makes it fall into a
            # repetitive, unrelated completion.  Phi-4-instruct still answers
            # correctly with a plain user turn, so keep only the latest user
            # message and omit unsupported tool metadata for this model.
            # Qwen and Gemma keep their full prompt, tools, and history.
            if routed_model == "phi-4-mini-instruct":
                user_messages = [
                    msg for msg in body.get("messages", [])
                    if msg.get("role") == "user"
                ]
                body["messages"] = user_messages[-1:] or [
                    {"role": "user", "content": ""}
                ]
                # Keep the small Q2 model concise and deterministic on a 4 GB
                # GPU; long free-running generations are prone to repetition.
                body.pop("tools", None)
                body.pop("tool_choice", None)
                body.pop("parallel_tool_calls", None)
                body["max_tokens"] = min(int(body.get("max_tokens") or 256), 256)
                body["temperature"] = min(float(body.get("temperature") or 0.2), 0.2)

        log.info(
            "Forwarding request: backend=%s model=%s",
            m.backend,
            routed_model,
        )

        try:
            if m.backend == "llamaswap":
                resp = await ls_driver.proxy_chat(body)

            elif m.backend == "vllm":
                resp = await vllm_driver.proxy_chat(req.model, body)

            elif m.backend == "onnxruntime":
                text = " ".join(
                    msg["content"]
                    for msg in body.get("messages", [])
                    if isinstance(msg.get("content"), str)
                )

                resp = await onnx_driver.proxy_infer(
                    req.model,
                    {
                        "inputs": {
                            "input_text": [text],
                        }
                    },
                )

            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Backend {m.backend!r} does not support "
                        "chat completions"
                    ),
                )

        except HTTPException:
            raise

        except Exception as exc:
            log.exception(
                "Backend request failed: model=%s backend=%s",
                routed_model,
                m.backend,
            )

            raise HTTPException(
                status_code=502,
                detail=f"Backend request failed: {exc}",
            ) from exc

        log.info(
            "Backend response received: status=%s model=%s",
            resp.status_code,
            routed_model,
        )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=resp.text,
            )

        if req.stream:
            log.info("Returning streaming response: model=%s", routed_model)

            return StreamingResponse(
                resp.aiter_bytes(),
                media_type="text/event-stream",
                headers={
                    "X-Workbench-Requested-Model": req.model,
                    "X-Workbench-Routed-Model": routed_model,
                    "X-Workbench-Route": decision.role,
                },
            )

        log.info("Returning JSON response: model=%s", routed_model)

        payload = resp.json()
        return payload


# ── embeddings ────────────────────────────────────────────────────────────────

@router.post("/v1/embeddings")
async def embeddings(
    req: EmbeddingRequest,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    log.info("Embedding request received: model=%s", req.model)

    m = _get_model_or_404(req.model, db)

    log.info(
        "Model resolved: id=%s backend=%s status=%s",
        m.id,
        m.backend,
        m.status,
    )

    async with lifecycle.track_request(req.model):
        log.info("Lifecycle acquired: model=%s", req.model)

        body = req.model_dump(exclude_none=True)

        try:
            if m.backend == "llamaswap":
                resp = await ls_driver.proxy_embeddings(body)

            elif m.backend == "vllm":
                resp = await vllm_driver.proxy_embeddings(
                    req.model,
                    body,
                )

            elif m.backend == "onnxruntime":
                inputs = (
                    req.input
                    if isinstance(req.input, list)
                    else [req.input]
                )

                resp = await onnx_driver.proxy_infer(
                    req.model,
                    {
                        "inputs": {
                            "input_text": inputs,
                        }
                    },
                )

            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Backend {m.backend!r} does not support "
                        "embeddings"
                    ),
                )

        except HTTPException:
            raise

        except Exception as exc:
            log.exception(
                "Embedding backend request failed: model=%s backend=%s",
                req.model,
                m.backend,
            )

            raise HTTPException(
                status_code=502,
                detail=f"Backend request failed: {exc}",
            ) from exc

        log.info(
            "Embedding backend response received: status=%s model=%s",
            resp.status_code,
            req.model,
        )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=resp.text,
            )

        payload = resp.json()
        if routed_model != req.model and isinstance(payload, dict):
            payload["workbench_routing"] = {
                "requested_model": req.model,
                "selected_model": routed_model,
                "role": decision.role,
                "reason": decision.reason,
            }
        return payload
