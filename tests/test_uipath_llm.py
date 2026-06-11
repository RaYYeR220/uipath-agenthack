"""Tests for UiPathLLM — the LLM Gateway client.

All HTTP is intercepted via httpx.MockTransport — NO real network.
Mirrors the style of test_uipath_agent.py.
"""
import json
import os

import httpx
import pytest

from sentinel.llm import LLMClient
from sentinel.uipath_agent import UiPathConfig, UiPathLLM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_URL = "https://cloud.uipath.com/acme/tenant/orchestrator_"
IDENTITY_URL = "https://cloud.uipath.com/identity_"


def _make_config(**overrides) -> UiPathConfig:
    defaults = dict(
        base_url=BASE_URL,
        identity_url=IDENTITY_URL,
        client_id="cid",
        client_secret="secret",
        folder_path="Shared/LoanAdvisor",
    )
    defaults.update(overrides)
    return UiPathConfig(**defaults)


def _make_llm(handler, model: str | None = None, **config_overrides) -> UiPathLLM:
    cfg = _make_config(**config_overrides)
    transport = httpx.MockTransport(handler)
    return UiPathLLM(cfg, model=model, http=httpx.Client(transport=transport))


def _token_handler(content: str = "The loan APR is 5%."):
    """Returns a handler that serves token + LLM completions."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "llm-tok"})
        if "/llm/api/chat/completions" in str(request.url):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": content}}]
            })
        raise AssertionError(f"unexpected request: {request.url}")
    return handler


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------

def test_token_fetched_once_across_two_complete_calls():
    token_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            token_calls["n"] += 1
            return httpx.Response(200, json={"access_token": "cached-llm-tok"})
        if "/llm/api/chat/completions" in str(request.url):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "answer"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler)
    llm.complete("sys", "user1")
    llm.complete("sys", "user2")
    assert token_calls["n"] == 1


# ---------------------------------------------------------------------------
# URL, headers, body
# ---------------------------------------------------------------------------

def test_complete_posts_to_correct_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["url"] = str(request.url)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler)
    llm.complete("sys", "user msg")

    assert "/llm/api/chat/completions" in seen["url"]
    assert "api-version=2024-08-01-preview" in seen["url"]


def test_complete_sends_model_name_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["model_header"] = request.headers.get(
                "x-uipath-llmgateway-normalizedapi-modelname"
            )
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler, model="gpt-4o-mini")
    llm.complete("system prompt", "user prompt")
    assert seen["model_header"] == "gpt-4o-mini"


def test_complete_sends_required_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["auth"] = request.headers.get("authorization")
            seen["content_type"] = request.headers.get("content-type")
            seen["streaming"] = request.headers.get("x-uipath-streaming-enabled")
            seen["product"] = request.headers.get("x-uipath-llmgateway-requestingproduct")
            seen["feature"] = request.headers.get("x-uipath-llmgateway-requestingfeature")
            seen["allow_4xx"] = request.headers.get("x-uipath-llmgateway-allowfull4xxresponse")
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler)
    llm.complete("sys", "usr")

    assert seen["auth"] == "Bearer tok"
    assert seen["content_type"] == "application/json"
    assert seen["streaming"] == "false"
    assert seen["product"] == "sentinel"
    assert seen["feature"] == "judge"
    assert seen["allow_4xx"] == "true"


def test_complete_sends_correct_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "reply"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler, model="gpt-4o")
    llm.complete("You are a judge.", "Rate this response.")

    body = seen["body"]
    assert body["messages"] == [
        {"role": "system", "content": "You are a judge."},
        {"role": "user", "content": "Rate this response."},
    ]
    assert body["max_tokens"] == 1024
    assert body["temperature"] == 0


def test_complete_sends_custom_max_tokens_and_temperature():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "reply"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    cfg = _make_config()
    transport = httpx.MockTransport(handler)
    llm = UiPathLLM(cfg, http=httpx.Client(transport=transport), max_tokens=512, temperature=0.7)
    llm.complete("sys", "usr")

    assert seen["body"]["max_tokens"] == 512
    assert seen["body"]["temperature"] == 0.7


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

def test_complete_returns_choices_0_message_content():
    handler = _token_handler("Approved with 5% APR.")
    llm = _make_llm(handler)
    result = llm.complete("You are a loan advisor.", "Should I approve?")
    assert result == "Approved with 5% APR."


# ---------------------------------------------------------------------------
# Default model resolution
# ---------------------------------------------------------------------------

def test_default_model_is_gpt_4_1_mini(monkeypatch):
    monkeypatch.delenv("UIPATH_LLM_MODEL", raising=False)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["model_header"] = request.headers.get(
                "x-uipath-llmgateway-normalizedapi-modelname"
            )
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler, model=None)
    llm.complete("sys", "usr")
    assert seen["model_header"] == "gpt-4.1-mini-2025-04-14"


def test_model_from_env_var(monkeypatch):
    monkeypatch.setenv("UIPATH_LLM_MODEL", "gpt-4o-2024-08-06")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["model_header"] = request.headers.get(
                "x-uipath-llmgateway-normalizedapi-modelname"
            )
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler, model=None)
    llm.complete("sys", "usr")
    assert seen["model_header"] == "gpt-4o-2024-08-06"


def test_explicit_model_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("UIPATH_LLM_MODEL", "gpt-4o-2024-08-06")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/llm/api/chat/completions" in str(request.url):
            seen["model_header"] = request.headers.get(
                "x-uipath-llmgateway-normalizedapi-modelname"
            )
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        raise AssertionError(f"unexpected {request.url}")

    llm = _make_llm(handler, model="gpt-4-turbo-2024-04-09")
    llm.complete("sys", "usr")
    assert seen["model_header"] == "gpt-4-turbo-2024-04-09"


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_uipath_llm_satisfies_llm_client_protocol():
    handler = _token_handler()
    llm = _make_llm(handler)
    assert isinstance(llm, LLMClient)
