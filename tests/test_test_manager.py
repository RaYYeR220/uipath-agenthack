"""Tests for TestManagerClient and publish_audit.

All HTTP is intercepted via httpx.MockTransport — NO real network.
Mirrors the style of test_uipath_agent.py and test_uipath_llm.py.
"""
import json
import os

import httpx
import pytest

from sentinel.uipath_agent import UiPathConfig
from sentinel.test_manager import TestManagerClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_URL = "https://cloud.uipath.com/acme/tenant/orchestrator_"
IDENTITY_URL = "https://cloud.uipath.com/identity_"
PROJECT_ID = "proj-uuid-1234"


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


def _make_client(handler, **config_overrides) -> TestManagerClient:
    cfg = _make_config(**config_overrides)
    transport = httpx.MockTransport(handler)
    return TestManagerClient(cfg, http=httpx.Client(transport=transport))


def _always_token(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/connect/token"):
        return httpx.Response(200, json={"access_token": "tm-tok"})
    raise AssertionError(f"unexpected request: {request.url}")


# ---------------------------------------------------------------------------
# Construction / base URL derivation
# ---------------------------------------------------------------------------

def test_base_url_derives_testmanager_from_orchestrator(monkeypatch):
    """orchestrator_ in base_url must become testmanager_ for TM calls."""
    monkeypatch.delenv("UIPATH_TM_BASE_URL", raising=False)
    cfg = _make_config()
    client = TestManagerClient(cfg, http=httpx.Client(transport=httpx.MockTransport(_always_token)))
    assert "/testmanager_" in client._base
    assert "/orchestrator_" not in client._base


def test_base_url_env_override(monkeypatch):
    """UIPATH_TM_BASE_URL env var overrides the derived URL."""
    monkeypatch.setenv("UIPATH_TM_BASE_URL", "https://custom.example.com/t/testmanager_")
    cfg = _make_config()
    client = TestManagerClient(cfg, http=httpx.Client(transport=httpx.MockTransport(_always_token)))
    assert client._base == "https://custom.example.com/t/testmanager_"


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------

def test_token_fetched_once_and_cached():
    """Token is fetched only once even across multiple API calls."""
    token_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            token_calls["n"] += 1
            return httpx.Response(200, json={"access_token": "cached-tm-tok"})
        if "/api/v2/projects" in str(request.url):
            return httpx.Response(200, json={"data": [], "paging": {}})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.find_project_id("Foo")
    client.find_project_id("Bar")
    assert token_calls["n"] == 1


# ---------------------------------------------------------------------------
# find_project_id
# ---------------------------------------------------------------------------

def test_find_project_id_returns_matching_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/api/v2/projects" in str(request.url):
            return httpx.Response(200, json={
                "data": [
                    {"id": "pid-1", "name": "OtherProject", "prefix": "OTH"},
                    {"id": "pid-2", "name": "SentinelTests", "prefix": "SEN"},
                ],
                "paging": {}
            })
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.find_project_id("SentinelTests")
    assert result == "pid-2"


def test_find_project_id_returns_none_if_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "/api/v2/projects" in str(request.url):
            return httpx.Response(200, json={"data": [], "paging": {}})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.find_project_id("NonExistent")
    assert result is None


# ---------------------------------------------------------------------------
# create_test_case
# ---------------------------------------------------------------------------

def test_create_test_case_posts_correct_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/api/v2/{PROJECT_ID}/testcases" in str(request.url):
            seen["body"] = json.loads(request.content)
            seen["url"] = str(request.url)
            return httpx.Response(201, json={
                "id": "tc-uuid-1",
                "objKey": "SEN:1",
                "name": "[hallucination] probe-1",
                "projectId": PROJECT_ID,
            })
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.create_test_case(PROJECT_ID, "[hallucination] probe-1", "What is the APR?")

    assert seen["body"]["name"] == "[hallucination] probe-1"
    assert seen["body"]["description"] == "What is the APR?"
    assert seen["body"]["projectId"] == PROJECT_ID
    assert seen["body"]["version"] == "1.0"
    assert result["id"] == "tc-uuid-1"
    assert result["objKey"] == "SEN:1"


def test_create_test_case_uses_correct_url_and_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "auth-tok"})
        if f"/api/v2/{PROJECT_ID}/testcases" in str(request.url):
            seen["auth"] = request.headers.get("authorization")
            seen["content_type"] = request.headers.get("content-type")
            return httpx.Response(201, json={"id": "tc-1", "objKey": "SEN:1"})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.create_test_case(PROJECT_ID, "name", "desc")
    assert seen["auth"] == "Bearer auth-tok"
    assert seen["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# create_execution
# ---------------------------------------------------------------------------

def test_create_execution_sends_source_and_source_details():
    """CRITICAL: sourceDetails is required when source=ThirdParty."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/api/v2/{PROJECT_ID}/testexecutions" in str(request.url):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "exec-uuid-1"})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    exec_id = client.create_execution(PROJECT_ID, "Audit Run 1", ["tc-uuid-1", "tc-uuid-2"])

    assert seen["body"]["source"] == "ThirdParty"
    assert seen["body"]["sourceDetails"] == "Sentinel"
    assert seen["body"]["projectId"] == PROJECT_ID
    assert seen["body"]["name"] == "Audit Run 1"
    assert seen["body"]["testCaseIds"] == ["tc-uuid-1", "tc-uuid-2"]
    assert exec_id == "exec-uuid-1"


def test_create_execution_uses_description():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/api/v2/{PROJECT_ID}/testexecutions" in str(request.url):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "exec-1"})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.create_execution(PROJECT_ID, "Run", ["tc-1"], description="some description")
    assert seen["body"]["description"] == "some description"


# ---------------------------------------------------------------------------
# create_test_case_log
# ---------------------------------------------------------------------------

def test_create_test_case_log_posts_correct_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/api/v2/{PROJECT_ID}/testcaselogs" in str(request.url) and "override-result" not in str(request.url):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "log-uuid-1"})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    log_id = client.create_test_case_log(PROJECT_ID, "tc-uuid-1", "exec-uuid-1")

    assert seen["body"]["testCaseId"] == "tc-uuid-1"
    assert seen["body"]["testExecutionId"] == "exec-uuid-1"
    assert seen["body"]["projectId"] == PROJECT_ID
    assert log_id == "log-uuid-1"


# ---------------------------------------------------------------------------
# set_result
# ---------------------------------------------------------------------------

def test_set_result_passed_sends_Passed():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "override-result" in str(request.url):
            seen["body"] = json.loads(request.content)
            seen["url"] = str(request.url)
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.set_result(PROJECT_ID, "log-uuid-1", passed=True, reason="All checks passed")

    assert seen["body"]["currentResult"] == "Passed"
    assert seen["body"]["reason"] == "All checks passed"
    assert f"{PROJECT_ID}/testcaselogs/log-uuid-1/override-result" in seen["url"]


def test_set_result_failed_sends_Failed():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "override-result" in str(request.url):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.set_result(PROJECT_ID, "log-uuid-1", passed=False, reason="Hallucinated a rate")

    assert seen["body"]["currentResult"] == "Failed"


# ---------------------------------------------------------------------------
# finish_execution
# ---------------------------------------------------------------------------

def test_finish_execution_posts_to_correct_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if "finish" in str(request.url):
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content) if request.content else {}
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    client.finish_execution(PROJECT_ID, "exec-uuid-1")
    assert f"{PROJECT_ID}/testexecutions/exec-uuid-1/finish" in seen["url"]


# ---------------------------------------------------------------------------
# publish_audit — helpers
# ---------------------------------------------------------------------------

def _make_probe_results(n: int) -> list:
    """Create n fake ProbeResults for testing."""
    from sentinel.models import Dimension, ProbeResult, Severity
    return [
        ProbeResult(
            probe_id=f"probe-{i}",
            dimension=Dimension.HALLUCINATION,
            input=f"Question {i}?",
            responses=["some response"],
            severity=Severity.MEDIUM,
            passed=(i % 2 == 0),
            rationale=f"Rationale {i}",
        )
        for i in range(n)
    ]


def _full_publish_handler(project_id: str, n_probes: int, exec_status: int = 200):
    """Returns a handler that serves the full happy-path publish_audit flow."""
    tc_counter = {"n": 0}
    log_counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        path = request.url.path
        url = str(request.url)
        # GET testcases — no existing matches (all will be created fresh)
        if f"/{project_id}/testcases" in url and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        if path.endswith(f"/{project_id}/testcases") and request.method == "POST":
            tc_counter["n"] += 1
            return httpx.Response(201, json={
                "id": f"tc-{tc_counter['n']}",
                "objKey": f"SEN:{tc_counter['n']}",
            })
        if path.endswith(f"/{project_id}/testexecutions"):
            return httpx.Response(exec_status,
                                  json={"id": "exec-1"} if exec_status < 400 else {"error": "boom"})
        if path.endswith(f"/{project_id}/testcaselogs") and "override" not in path:
            log_counter["n"] += 1
            return httpx.Response(200, json={"id": f"log-{log_counter['n']}"})
        if "override-result" in path:
            return httpx.Response(200, json={})
        if "finish" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.url}")

    return handler


# ---------------------------------------------------------------------------
# publish_audit — happy path
# ---------------------------------------------------------------------------

def test_publish_audit_happy_path_returns_summary():
    from sentinel.test_manager import publish_audit

    n = 3
    results = _make_probe_results(n)
    handler = _full_publish_handler(PROJECT_ID, n, exec_status=200)
    client = _make_client(handler)

    summary = publish_audit(client, PROJECT_ID, "Audit Run", results)

    assert summary["test_cases_created"] == n
    assert summary["execution_id"] == "exec-1"
    assert summary["results_logged"] is True
    assert summary["warning"] is None


def test_publish_audit_creates_n_test_cases():
    from sentinel.test_manager import publish_audit

    n = 4
    results = _make_probe_results(n)
    tc_calls = {"n": 0}
    log_counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        path = request.url.path
        url = str(request.url)
        if f"/{PROJECT_ID}/testcases" in url and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        if path.endswith(f"/{PROJECT_ID}/testcases") and request.method == "POST":
            tc_calls["n"] += 1
            return httpx.Response(201, json={"id": f"tc-{tc_calls['n']}", "objKey": f"SEN:{tc_calls['n']}"})
        if path.endswith(f"/{PROJECT_ID}/testexecutions"):
            return httpx.Response(200, json={"id": "exec-1"})
        if path.endswith(f"/{PROJECT_ID}/testcaselogs") and "override" not in path:
            log_counter["n"] += 1
            return httpx.Response(200, json={"id": f"log-{log_counter['n']}"})
        if "override-result" in path or "finish" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    summary = publish_audit(client, PROJECT_ID, "Audit Run", results)
    assert tc_calls["n"] == n
    assert summary["test_cases_created"] == n


# ---------------------------------------------------------------------------
# publish_audit — graceful degradation when execution POST returns 500
# ---------------------------------------------------------------------------

def test_publish_audit_degrades_gracefully_on_execution_500():
    """When testexecutions POST returns 500, summary has results_logged=False,
    warning is set, test_cases_created==N, and no exception is raised."""
    from sentinel.test_manager import publish_audit

    n = 2
    results = _make_probe_results(n)
    handler = _full_publish_handler(PROJECT_ID, n, exec_status=500)
    client = _make_client(handler)

    # Must NOT raise
    summary = publish_audit(client, PROJECT_ID, "Audit Run", results)

    assert summary["test_cases_created"] == n
    assert summary["results_logged"] is False
    assert summary["execution_id"] is None
    assert summary["warning"] is not None
    assert "500" in summary["warning"]


def test_publish_audit_degradation_warning_mentions_test_cases_created():
    """The warning message must say how many test cases were still created."""
    from sentinel.test_manager import publish_audit

    n = 3
    results = _make_probe_results(n)
    handler = _full_publish_handler(PROJECT_ID, n, exec_status=500)
    client = _make_client(handler)

    summary = publish_audit(client, PROJECT_ID, "Audit Run", results)
    assert str(n) in summary["warning"]


def test_publish_audit_degradation_warning_is_ascii_clean():
    """The warning string must contain only ASCII characters (no em-dash mojibake)."""
    from sentinel.test_manager import publish_audit

    n = 1
    results = _make_probe_results(n)
    handler = _full_publish_handler(PROJECT_ID, n, exec_status=500)
    client = _make_client(handler)

    summary = publish_audit(client, PROJECT_ID, "Run", results)
    assert summary["warning"] is not None
    # Will raise UnicodeEncodeError if non-ASCII chars are present
    summary["warning"].encode("ascii")


# ---------------------------------------------------------------------------
# find_test_case_id
# ---------------------------------------------------------------------------

def test_find_test_case_id_returns_id_of_matching_name():
    """Returns the id of the test case whose name matches exactly."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/{PROJECT_ID}/testcases" in str(request.url):
            return httpx.Response(200, json={"data": [
                {"id": "tc-10", "name": "[hallucination] probe-0"},
                {"id": "tc-11", "name": "[hallucination] probe-1"},
            ]})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.find_test_case_id(PROJECT_ID, "[hallucination] probe-1")
    assert result == "tc-11"


def test_find_test_case_id_returns_none_when_not_found():
    """Returns None when no test case with that name exists."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/{PROJECT_ID}/testcases" in str(request.url):
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.find_test_case_id(PROJECT_ID, "nonexistent")
    assert result is None


def test_find_test_case_id_tolerates_bare_list():
    """Tolerates a bare JSON list (no 'data' wrapper) in the response."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if f"/{PROJECT_ID}/testcases" in str(request.url):
            # Bare list, no {"data": ...} wrapper
            return httpx.Response(200, json=[
                {"id": "tc-20", "name": "my-probe"},
            ])
        raise AssertionError(f"unexpected {request.url}")

    client = _make_client(handler)
    result = client.find_test_case_id(PROJECT_ID, "my-probe")
    assert result == "tc-20"


# ---------------------------------------------------------------------------
# publish_audit — idempotent reuse (no duplicate test cases)
# ---------------------------------------------------------------------------

def test_publish_audit_reuses_existing_test_case_no_post():
    """When find_test_case_id returns an id, no POST to /testcases is made for that probe."""
    from sentinel.test_manager import publish_audit

    results = _make_probe_results(1)
    probe_name = f"[{results[0].dimension.value}] {results[0].probe_id}"
    post_testcase_calls = {"n": 0}
    get_testcases_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        path = request.url.path
        url = str(request.url)
        # GET testcases — return a match
        if f"/{PROJECT_ID}/testcases" in url and request.method == "GET":
            get_testcases_calls["n"] += 1
            return httpx.Response(200, json={"data": [
                {"id": "existing-tc-id", "name": probe_name},
            ]})
        # POST testcases — must NOT be called
        if f"/{PROJECT_ID}/testcases" in url and request.method == "POST":
            post_testcase_calls["n"] += 1
            return httpx.Response(201, json={"id": "new-tc-id", "objKey": "SEN:1"})
        if path.endswith(f"/{PROJECT_ID}/testexecutions"):
            return httpx.Response(200, json={"id": "exec-1"})
        if path.endswith(f"/{PROJECT_ID}/testcaselogs") and "override" not in path:
            return httpx.Response(200, json={"id": "log-1"})
        if "override-result" in path or "finish" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    client = _make_client(handler)
    summary = publish_audit(client, PROJECT_ID, "Run", results)

    assert post_testcase_calls["n"] == 0, "must NOT POST testcases when one already exists"
    assert summary["test_cases_reused"] == 1
    assert summary["test_cases_created"] == 0


def test_publish_audit_creates_when_no_existing_match():
    """When find_test_case_id returns None, a new test case is POSTed."""
    from sentinel.test_manager import publish_audit

    results = _make_probe_results(1)
    post_testcase_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        path = request.url.path
        url = str(request.url)
        if f"/{PROJECT_ID}/testcases" in url and request.method == "GET":
            return httpx.Response(200, json={"data": []})  # no match
        if f"/{PROJECT_ID}/testcases" in url and request.method == "POST":
            post_testcase_calls["n"] += 1
            return httpx.Response(201, json={"id": "new-tc-id", "objKey": "SEN:1"})
        if path.endswith(f"/{PROJECT_ID}/testexecutions"):
            return httpx.Response(200, json={"id": "exec-1"})
        if path.endswith(f"/{PROJECT_ID}/testcaselogs") and "override" not in path:
            return httpx.Response(200, json={"id": "log-1"})
        if "override-result" in path or "finish" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    client = _make_client(handler)
    summary = publish_audit(client, PROJECT_ID, "Run", results)

    assert post_testcase_calls["n"] == 1
    assert summary["test_cases_created"] == 1
    assert summary["test_cases_reused"] == 0


def test_publish_audit_mixed_reuse_and_create():
    """2 probes: one already exists (reused), one new (created)."""
    from sentinel.test_manager import publish_audit

    results = _make_probe_results(2)
    probe_name_0 = f"[{results[0].dimension.value}] {results[0].probe_id}"
    # probe_name_1 has no match
    post_testcase_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        path = request.url.path
        url = str(request.url)
        if f"/{PROJECT_ID}/testcases" in url and request.method == "GET":
            # Only probe-0 has an existing test case
            return httpx.Response(200, json={"data": [
                {"id": "existing-tc-id", "name": probe_name_0},
            ]})
        if f"/{PROJECT_ID}/testcases" in url and request.method == "POST":
            post_testcase_calls["n"] += 1
            return httpx.Response(201, json={"id": f"new-tc-{post_testcase_calls['n']}", "objKey": "SEN:X"})
        if path.endswith(f"/{PROJECT_ID}/testexecutions"):
            return httpx.Response(200, json={"id": "exec-1"})
        if path.endswith(f"/{PROJECT_ID}/testcaselogs") and "override" not in path:
            return httpx.Response(200, json={"id": "log-1"})
        if "override-result" in path or "finish" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    client = _make_client(handler)
    summary = publish_audit(client, PROJECT_ID, "Run", results)

    assert summary["test_cases_created"] == 1
    assert summary["test_cases_reused"] == 1


def test_publish_audit_summary_has_reused_key_in_happy_path():
    """The returned summary always includes 'test_cases_reused' key."""
    from sentinel.test_manager import publish_audit

    results = _make_probe_results(2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        path = request.url.path
        url = str(request.url)
        if f"/{PROJECT_ID}/testcases" in url and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        if f"/{PROJECT_ID}/testcases" in url and request.method == "POST":
            return httpx.Response(201, json={"id": "tc-1", "objKey": "SEN:1"})
        if path.endswith(f"/{PROJECT_ID}/testexecutions"):
            return httpx.Response(200, json={"id": "exec-1"})
        if path.endswith(f"/{PROJECT_ID}/testcaselogs") and "override" not in path:
            return httpx.Response(200, json={"id": "log-1"})
        if "override-result" in path or "finish" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    client = _make_client(handler)
    summary = publish_audit(client, PROJECT_ID, "Run", results)

    assert "test_cases_reused" in summary
    assert "test_cases_created" in summary
