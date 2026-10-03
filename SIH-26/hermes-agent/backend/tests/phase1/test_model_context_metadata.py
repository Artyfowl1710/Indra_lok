from types import SimpleNamespace

from server.api.routes.models import _alias_payload, _openai_model_payload
from server.core.model_routing import PUBLIC_MODEL_ALIASES, alias_target


def _row(model_id):
    return SimpleNamespace(
        id=model_id,
        backend="llamaswap",
        model_type="text",
        task_tags="[]",
        status="idle",
        vram_mb=0,
        pinned=False,
    )


def test_physical_models_advertise_configured_context_window():
    for model_id in ("qwen3.5-4b", "gemma-2-2b-it", "qwen2-vl-ocr-2b-instruct"):
        assert _openai_model_payload(_row(model_id))["context_length"] == 32768


def test_aliases_inherit_target_context_window():
    for alias in PUBLIC_MODEL_ALIASES:
        target = _row(alias_target(alias))
        assert _alias_payload(alias, target)["context_length"] == 32768


def test_unknown_model_keeps_conservative_fallback():
    assert _openai_model_payload(_row("unconfigured-model"))["context_length"] == 16384
