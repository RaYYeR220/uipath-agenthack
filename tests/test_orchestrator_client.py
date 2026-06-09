import json
import httpx
from sentinel.orchestrator_client import OrchestratorClient


def _client_with(handler) -> OrchestratorClient:
    transport = httpx.MockTransport(handler)
    return OrchestratorClient(
        base_url="https://cloud.uipath.com/acme/tenant/orchestrator_",
        identity_url="https://cloud.uipath.com/identity_",
        client_id="cid", client_secret="secret", folder_id="42",
        http=httpx.Client(transport=transport),
    )


def test_auth_then_start_execution():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if "StartTestSetExecution" in str(request.url):
            seen["auth"] = request.headers.get("authorization")
            seen["folder"] = request.headers.get("x-uipath-organizationunitid")
            return httpx.Response(200, json=7)  # execution id
        raise AssertionError(f"unexpected {request.url}")

    client = _client_with(handler)
    exec_id = client.start_test_set_execution(test_set_id=123)
    assert exec_id == 7
    assert seen["auth"] == "Bearer tok"
    assert seen["folder"] == "42"


def test_get_results_returns_status_and_cases():
    payload = {"Status": "Passed",
               "TestCaseExecutions": [{"Name": "inj-1", "Status": "Failed"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(200, json={"value": [payload]})

    client = _client_with(handler)
    result = client.get_results(execution_id=7)
    assert result["Status"] == "Passed"
    assert result["TestCaseExecutions"][0]["Status"] == "Failed"
