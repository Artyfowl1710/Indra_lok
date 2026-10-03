from types import SimpleNamespace

import pytest

from agent.agent_init import _enforce_minimum_context
from agent.model_metadata import MINIMUM_CONTEXT_LENGTH


def test_explicit_laptop_window_is_accepted_but_smaller_windows_are_rejected():
    agent = SimpleNamespace(
        model="local-model", provider="custom",
        _config_context_length=MINIMUM_CONTEXT_LENGTH,
        context_compressor=SimpleNamespace(context_length=MINIMUM_CONTEXT_LENGTH),
    )
    _enforce_minimum_context(agent)
    agent.context_compressor.context_length = MINIMUM_CONTEXT_LENGTH // 2
    with pytest.raises(ValueError, match="below the minimum"):
        _enforce_minimum_context(agent)
