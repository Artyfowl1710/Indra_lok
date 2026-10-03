from __future__ import annotations

import json

from tools import lazy_deps
from tools.environments import local


def test_offline_policy_uses_only_wheelhouse(tmp_path, monkeypatch):
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    monkeypatch.setattr(
        lazy_deps,
        "_dependency_policy",
        lambda: {
            "mode": "offline",
            "wheelhouse": str(wheelhouse),
            "artifactory_url": "",
            "request_missing": True,
        },
    )

    args, error = lazy_deps._dependency_source_args()

    assert error is None
    assert args == ["--no-index", "--find-links", str(wheelhouse)]


def test_artifactory_policy_has_no_public_fallback(monkeypatch):
    monkeypatch.setattr(
        lazy_deps,
        "_dependency_policy",
        lambda: {
            "mode": "artifactory",
            "wheelhouse": "",
            "artifactory_url": "https://packages.internal.example/api/pypi/python/simple",
            "request_missing": True,
        },
    )

    args, error = lazy_deps._dependency_source_args()

    assert error is None
    assert args == ["--index-url", "https://packages.internal.example/api/pypi/python/simple"]
    assert "--extra-index-url" not in args


def test_artifactory_rejects_credentials_in_url(monkeypatch):
    monkeypatch.setattr(
        lazy_deps,
        "_dependency_policy",
        lambda: {
            "mode": "artifactory",
            "wheelhouse": "",
            "artifactory_url": "https://user:secret@packages.internal/simple",
            "request_missing": True,
        },
    )

    args, error = lazy_deps._dependency_source_args()

    assert args == []
    assert "without embedded credentials" in error


def test_missing_dependency_writes_deduplicated_operator_request(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lazy_deps,
        "_dependency_policy",
        lambda: {"mode": "offline", "wheelhouse": "", "artifactory_url": "", "request_missing": True},
    )
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)

    first = lazy_deps._write_dependency_request("tool.pdf", ("pypdf==6.0.0",), "not mirrored")
    second = lazy_deps._write_dependency_request("tool.pdf", ("pypdf==6.0.0",), "not mirrored")

    assert first == second
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    assert payload["feature"] == "tool.pdf"
    assert payload["packages"] == ["pypdf==6.0.0"]
    assert "secret" not in json.dumps(payload).lower()


def test_terminal_children_inherit_offline_package_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "security": {
                "dependency_policy": {
                    "mode": "offline",
                    "wheelhouse": str(tmp_path / "wheelhouse"),
                }
            }
        },
    )
    env = {
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "PIP_EXTRA_INDEX_URL": "https://untrusted.example/simple",
        "UV_INDEX_URL": "https://pypi.org/simple",
    }

    local._apply_dependency_source_policy(env)

    assert env["PIP_NO_INDEX"] == "1"
    assert env["UV_NO_INDEX"] == "1"
    assert env["PIP_FIND_LINKS"] == str(tmp_path / "wheelhouse")
    assert env["UV_FIND_LINKS"] == str(tmp_path / "wheelhouse")
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert "UV_INDEX_URL" not in env
