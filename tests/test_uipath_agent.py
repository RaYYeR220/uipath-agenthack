"""Tests for UiPathAgentClient and UiPathTargetAgent.

All HTTP is intercepted via httpx.MockTransport — NO real network.
Mirrors the style of test_orchestrator_client.py.
"""
import json
import os

import httpx
import pytest

from sentinel.uipath_agent import UiPathAgentClient, UiPathConfig, UiPathTargetAgent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_URL = "https://cloud.uipath.com/acme/tenant/orchestrator_"
IDENTITY_URL = "https://cloud.uipath.com/identity_"
FOLDER = "Shared/LoanAdvisor"
PROCESS_KEY = "LoanAdvisor"
RELEASE_KEY = "release-uuid-1234"
JOB_ID = 99


def _make_config(**overrides) -> UiPathConfig:
    defaults = dict(
        base_url=BASE_URL,
        identity_url=IDENTITY_URL,
        client_id="cid",
        client_secret="secret",
        folder_path=FOLDER,
    )
    defaults.update(overrides)
    return UiPathConfig(**defaults)


def _make_client(handler, **config_overrides) -> UiPathAgentClient:
    cfg = _make_config(**config_overrides)
    transport = httpx.MockTransport(handler)
    return UiPathAgentClient(cfg, http=httpx.Client(transport=transport))


# ---------------------------------------------------------------------------
# UiPathConfig.from_env
# ---------------------------------------------------------------------------

_REQUIRED_VARS = {
    "UIPATH_BASE_URL": BASE_URL,
    "UIPATH_CLIENT_ID": "cid",
    "UIPATH_CLIENT_SECRET": "secret",
    "UIPATH_FOLDER_PATH": FOLDER,
}


def test_from_env_reads_all_vars(monkeypatch):
    for k, v in _REQUIRED_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("UIPATH_IDENTITY_URL", IDENTITY_URL)
    monkeypatch.setenv("UIPATH_SCOPE", "OR.Jobs")

    cfg = UiPathConfig.from_env()
    assert cfg.base_url == BASE_URL
    assert cfg.identity_url == IDENTITY_URL
    assert cfg.client_id == "cid"
    assert cfg.client_secret == "secret"
    assert cfg.folder_path == FOLDER
    assert cfg.scope == "OR.Jobs"


def test_from_env_uses_default_identity_url(monkeypatch):
    for k, v in _REQUIRED_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("UIPATH_IDENTITY_URL", raising=False)
    monkeypatch.delenv("UIPATH_SCOPE", raising=False)

    cfg = UiPathConfig.from_env()
    assert "identity_" in cfg.identity_url


def test_from_env_raises_on_missing_required(monkeypatch):
    # Clear all relevant vars
    for k in list(_REQUIRED_VARS) + ["UIPATH_IDENTITY_URL", "UIPATH_SCOPE"]:
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        UiPathConfig.from_env()
    msg = str(exc_info.value)
    # Should list the missing variable name(s)
    assert "UIPATH_BASE_URL" in msg or "UIPATH_CLIENT_ID" in msg or "UIPATH_CLIENT_SECRET" in msg or "UIPATH_FOLDER_PATH" in msg


def test_from_env_raises_names_each_missing_var(monkeypatch):
    # Only provide BASE_URL, omit the rest
    monkeypatch.setenv("UIPATH_BASE_URL", BASE_URL)
    for k in ["UIPATH_CLIENT_ID", "UIPATH_CLIENT_SECRET", "UIPATH_FOLDER_PATH",
              "UIPATH_IDENTITY_URL", "UIPATH_SCOPE"]:
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        UiPathConfig.from_env()
    msg = str(exc_info.value)
    assert "UIPATH_CLIENT_ID" in msg
    assert "UIPATH_CLIENT_SECRET" in msg
    assert "UIPATH_FOLDER_PATH" in msg


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------

def test_token_fetched_once_and_cached():
    token_call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            token_call_count["n"] += 1
            return httpx.Response(200, json={"access_token": "cached-tok"})
        # Releases endpoint — always return something valid
        if "Releases" in str(request.url):
            return httpx.Response(200, json={"value": [{"Key": RELEASE_KEY}]})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    # Two calls that each need auth headers
    client.get_release_key(PROCESS_KEY)
    client.get_release_key(PROCESS_KEY)  # second call reuses cached key but does hit releases again
    # Token must only have been fetched once
    assert token_call_count["n"] == 1


# ---------------------------------------------------------------------------
# get_release_key
# ---------------------------------------------------------------------------

def test_get_release_key_parses_value_0_key():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "Releases" in str(request.url):
            assert "LoanAdvisor" in str(request.url)
            return httpx.Response(200, json={"value": [{"Key": RELEASE_KEY}]})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    key = client.get_release_key(PROCESS_KEY)
    assert key == RELEASE_KEY


def test_get_release_key_sends_folder_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "Releases" in str(request.url):
            seen["folder"] = request.headers.get("x-uipath-folderpath")
            return httpx.Response(200, json={"value": [{"Key": RELEASE_KEY}]})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.get_release_key(PROCESS_KEY)
    assert seen["folder"] == FOLDER


# ---------------------------------------------------------------------------
# start_job
# ---------------------------------------------------------------------------

def test_start_job_sends_input_arguments_as_json_string():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "StartJobs" in str(request.url):
            body = json.loads(request.content)
            seen["start_info"] = body["startInfo"]
            seen["folder"] = request.headers.get("x-uipath-folderpath")
            return httpx.Response(200, json={"value": [{"Id": JOB_ID}]})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    input_args = {"customer_message": "hi"}
    job_id = client.start_job(RELEASE_KEY, input_args)

    assert job_id == JOB_ID
    # InputArguments must be a STRING (double-serialised), not a dict
    ia = seen["start_info"]["InputArguments"]
    assert isinstance(ia, str), f"InputArguments should be str, got {type(ia)}"
    assert ia == json.dumps(input_args)
    assert seen["folder"] == FOLDER


def test_start_job_sends_correct_release_key_and_strategy():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "StartJobs" in str(request.url):
            body = json.loads(request.content)
            seen["start_info"] = body["startInfo"]
            return httpx.Response(200, json={"value": [{"Id": JOB_ID}]})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.start_job(RELEASE_KEY, {"x": 1})
    si = seen["start_info"]
    assert si["ReleaseKey"] == RELEASE_KEY
    assert si["Strategy"] == "JobsCount"
    assert si["JobsCount"] == 1


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------

def test_get_job_returns_job_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"Jobs({JOB_ID})" in str(request.url):
            return httpx.Response(200, json={
                "State": "Successful",
                "OutputArguments": json.dumps({"content": "hello"}),
                "Info": "",
            })
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    job = client.get_job(JOB_ID)
    assert job["State"] == "Successful"
    assert isinstance(job["OutputArguments"], str)


# ---------------------------------------------------------------------------
# wait_job
# ---------------------------------------------------------------------------

def test_wait_job_polls_until_successful():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"Jobs({JOB_ID})" in str(request.url):
            call_count["n"] += 1
            state = "Running" if call_count["n"] < 3 else "Successful"
            return httpx.Response(200, json={
                "State": state,
                "OutputArguments": json.dumps({"content": "done"}) if state == "Successful" else None,
                "Info": "",
            })
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    job = client.wait_job(JOB_ID, poll_seconds=0, timeout_seconds=60)
    assert job["State"] == "Successful"
    assert call_count["n"] == 3


def test_wait_job_terminal_on_faulted():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"Jobs({JOB_ID})" in str(request.url):
            return httpx.Response(200, json={"State": "Faulted", "OutputArguments": None, "Info": "boom"})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    job = client.wait_job(JOB_ID, poll_seconds=0, timeout_seconds=60)
    assert job["State"] == "Faulted"


def test_wait_job_raises_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"Jobs({JOB_ID})" in str(request.url):
            return httpx.Response(200, json={"State": "Running", "OutputArguments": None, "Info": ""})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    with pytest.raises(TimeoutError):
        client.wait_job(JOB_ID, poll_seconds=0, timeout_seconds=0)


# ---------------------------------------------------------------------------
# run_agent
# ---------------------------------------------------------------------------

def _full_flow_handler(states: list[str], output_args: str | None):
    """Returns a handler that drives the full token→releases→startjobs→jobs flow."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "Releases" in str(request.url):
            return httpx.Response(200, json={"value": [{"Key": RELEASE_KEY}]})
        if "StartJobs" in str(request.url):
            return httpx.Response(200, json={"value": [{"Id": JOB_ID}]})
        if f"Jobs({JOB_ID})" in str(request.url):
            call_count["n"] += 1
            idx = min(call_count["n"] - 1, len(states) - 1)
            state = states[idx]
            oa = output_args if state == "Successful" else None
            return httpx.Response(200, json={"State": state, "OutputArguments": oa, "Info": "details"})
        raise AssertionError(f"unexpected {request.url}")

    return handler


def test_run_agent_happy_path_returns_parsed_output():
    output = json.dumps({"content": "approved"})
    handler = _full_flow_handler(["Running", "Successful"], output)
    client = _make_client(handler)
    result = client.run_agent({"customer_message": "loan?"}, PROCESS_KEY)
    assert result == {"content": "approved"}


def test_run_agent_faulted_raises_runtime_error():
    handler = _full_flow_handler(["Faulted"], None)
    client = _make_client(handler)
    with pytest.raises(RuntimeError) as exc_info:
        client.run_agent({"customer_message": "loan?"}, PROCESS_KEY)
    assert "Faulted" in str(exc_info.value)


def test_run_agent_stopped_raises_runtime_error():
    handler = _full_flow_handler(["Stopped"], None)
    client = _make_client(handler)
    with pytest.raises(RuntimeError) as exc_info:
        client.run_agent({}, PROCESS_KEY)
    assert "Stopped" in str(exc_info.value)


def test_run_agent_none_output_arguments_returns_empty_dict():
    """Successful job with null OutputArguments → {}."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "Releases" in str(request.url):
            return httpx.Response(200, json={"value": [{"Key": RELEASE_KEY}]})
        if "StartJobs" in str(request.url):
            return httpx.Response(200, json={"value": [{"Id": JOB_ID}]})
        if f"Jobs({JOB_ID})" in str(request.url):
            return httpx.Response(200, json={"State": "Successful", "OutputArguments": None, "Info": ""})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.run_agent({}, PROCESS_KEY)
    assert result == {}


def test_run_agent_caches_release_key():
    """Second call with same process_key must NOT re-hit /Releases."""
    releases_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "Releases" in str(request.url):
            releases_calls["n"] += 1
            return httpx.Response(200, json={"value": [{"Key": RELEASE_KEY}]})
        if "StartJobs" in str(request.url):
            return httpx.Response(200, json={"value": [{"Id": JOB_ID}]})
        if f"Jobs({JOB_ID})" in str(request.url):
            return httpx.Response(200, json={"State": "Successful", "OutputArguments": json.dumps({}), "Info": ""})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.run_agent({}, PROCESS_KEY)
    client.run_agent({}, PROCESS_KEY)
    assert releases_calls["n"] == 1


# ---------------------------------------------------------------------------
# UiPathTargetAgent (protocol compliance)
# ---------------------------------------------------------------------------

def test_uipath_target_agent_ask_returns_content_string():
    output = json.dumps({"content": "hello from agent"})
    handler = _full_flow_handler(["Successful"], output)
    cfg = _make_config()
    transport = httpx.MockTransport(handler)
    underlying = UiPathAgentClient(cfg, http=httpx.Client(transport=transport))
    agent = UiPathTargetAgent(underlying, process_key=PROCESS_KEY)

    reply = agent.ask("give me a loan")
    assert reply == "hello from agent"


def test_uipath_target_agent_uses_custom_keys():
    output = json.dumps({"response": "custom output"})
    handler = _full_flow_handler(["Successful"], output)
    cfg = _make_config()
    transport = httpx.MockTransport(handler)
    underlying = UiPathAgentClient(cfg, http=httpx.Client(transport=transport))
    agent = UiPathTargetAgent(
        underlying, process_key=PROCESS_KEY,
        input_key="user_query", output_key="response"
    )

    # Verify what input_key gets sent (by checking via start_job path)
    reply = agent.ask("query text")
    assert reply == "custom output"


def test_uipath_target_agent_missing_output_key_returns_empty_string():
    output = json.dumps({"other_key": "value"})
    handler = _full_flow_handler(["Successful"], output)
    cfg = _make_config()
    transport = httpx.MockTransport(handler)
    underlying = UiPathAgentClient(cfg, http=httpx.Client(transport=transport))
    agent = UiPathTargetAgent(underlying, process_key=PROCESS_KEY, output_key="content")

    reply = agent.ask("hi")
    assert reply == ""


def test_uipath_target_agent_satisfies_protocol():
    from sentinel.target import TargetAgent
    output = json.dumps({"content": "ok"})
    handler = _full_flow_handler(["Successful"], output)
    cfg = _make_config()
    transport = httpx.MockTransport(handler)
    underlying = UiPathAgentClient(cfg, http=httpx.Client(transport=transport))
    agent = UiPathTargetAgent(underlying, process_key=PROCESS_KEY)

    assert isinstance(agent, TargetAgent)
