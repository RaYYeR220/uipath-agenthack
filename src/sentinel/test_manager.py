"""UiPath Test Manager v2 client and audit-publishing orchestration.

Syncs Sentinel audit results into UiPath Test Cloud via the Test Manager API.
Mirrors the style of UiPathLLM in uipath_agent.py: injectable httpx.Client,
cached OAuth token via _fetch_token, env-override for base URL.
"""
import json
import logging
import os

import httpx

from .models import ProbeResult
from .uipath_agent import UiPathConfig, _fetch_token

logger = logging.getLogger(__name__)


class TestManagerClient:
    """Client for UiPath Test Manager v2 API."""

    def __init__(self, config: UiPathConfig, http: httpx.Client | None = None):
        self._config = config
        self._base = (
            os.environ.get("UIPATH_TM_BASE_URL", "").rstrip("/")
            or config.base_url.rstrip("/").replace("/orchestrator_", "/testmanager_")
        )
        self._http = http or httpx.Client(timeout=60)
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token is None:
            self._token = _fetch_token(
                self._http,
                self._config.identity_url,
                self._config.client_id,
                self._config.client_secret,
                self._config.scope,
            )
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def find_project_id(self, name: str) -> str | None:
        """GET /api/v2/projects; return id of project matching name, or None."""
        resp = self._http.get(
            f"{self._base}/api/v2/projects",
            headers=self._headers(),
        )
        resp.raise_for_status()
        for project in resp.json().get("data", []):
            if project.get("name") == name:
                return project["id"]
        return None

    def create_test_case(self, project_id: str, name: str, description: str,
                         version: str = "1.0") -> dict:
        """POST /api/v2/{projectId}/testcases; returns the created test case dict."""
        resp = self._http.post(
            f"{self._base}/api/v2/{project_id}/testcases",
            headers=self._headers(),
            content=json.dumps({
                "name": name,
                "description": description,
                "projectId": project_id,
                "version": version,
            }),
        )
        resp.raise_for_status()
        return resp.json()

    def create_execution(self, project_id: str, name: str, test_case_ids: list[str],
                         description: str = "") -> str:
        """POST /api/v2/{projectId}/testexecutions; returns the execution id."""
        resp = self._http.post(
            f"{self._base}/api/v2/{project_id}/testexecutions",
            headers=self._headers(),
            content=json.dumps({
                "projectId": project_id,
                "source": "ThirdParty",
                "sourceDetails": "Sentinel",
                "name": name,
                "description": description,
                "testCaseIds": test_case_ids,
            }),
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def create_test_case_log(self, project_id: str, test_case_id: str,
                             execution_id: str) -> str:
        """POST /api/v2/{projectId}/testcaselogs; returns the log id."""
        resp = self._http.post(
            f"{self._base}/api/v2/{project_id}/testcaselogs",
            headers=self._headers(),
            content=json.dumps({
                "testCaseId": test_case_id,
                "testExecutionId": execution_id,
                "projectId": project_id,
            }),
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def set_result(self, project_id: str, log_id: str, passed: bool, reason: str) -> None:
        """POST /api/v2/{projectId}/testcaselogs/{logId}/override-result."""
        resp = self._http.post(
            f"{self._base}/api/v2/{project_id}/testcaselogs/{log_id}/override-result",
            headers=self._headers(),
            content=json.dumps({
                "currentResult": "Passed" if passed else "Failed",
                "reason": reason,
            }),
        )
        resp.raise_for_status()

    def finish_execution(self, project_id: str, execution_id: str) -> None:
        """POST /api/v2/{projectId}/testexecutions/{executionId}/finish."""
        resp = self._http.post(
            f"{self._base}/api/v2/{project_id}/testexecutions/{execution_id}/finish",
            headers=self._headers(),
            content=json.dumps({}),
        )
        resp.raise_for_status()


def publish_audit(
    client: TestManagerClient,
    project_id: str,
    audit_name: str,
    results: list[ProbeResult],
) -> dict:
    """Sync a list of ProbeResults into UiPath Test Manager.

    Creates one test case per ProbeResult, then attempts to create an execution,
    log each result, and finish the execution.  If the execution flow fails
    (e.g. HTTP 500 on staging), the function does NOT raise — it logs a clear
    warning and returns a summary dict that includes the failure details.

    Returns a dict with keys:
        test_cases_created: int
        execution_id: str | None
        results_logged: bool
        warning: str | None
    """
    # Step 1 — create a test case per ProbeResult
    test_case_pairs: list[tuple[ProbeResult, str]] = []
    for r in results:
        name = f"[{r.dimension.value}] {r.probe_id}"
        tc = client.create_test_case(project_id, name, r.input)
        test_case_pairs.append((r, tc["id"]))

    n = len(test_case_pairs)
    tc_ids = [tc_id for _, tc_id in test_case_pairs]

    # Step 2 — attempt execution flow; degrade gracefully on any HTTP error
    execution_id: str | None = None
    results_logged = False
    warning: str | None = None

    try:
        execution_id = client.create_execution(project_id, audit_name, tc_ids)
        for r, tc_id in test_case_pairs:
            log_id = client.create_test_case_log(project_id, tc_id, execution_id)
            client.set_result(
                project_id, log_id,
                passed=bool(r.passed),
                reason=r.rationale or "(no rationale)",
            )
        client.finish_execution(project_id, execution_id)
        results_logged = True
    except httpx.HTTPStatusError as exc:
        msg = (
            f"Test Manager execution logging failed "
            f"(HTTP {exc.response.status_code} — known staging limitation); "
            f"{n} test case(s) were still created."
        )
        logger.warning(msg)
        print(f"WARNING: {msg}")
        warning = msg
    except httpx.RequestError as exc:
        msg = (
            f"Test Manager execution logging failed "
            f"(network error: {exc}); "
            f"{n} test case(s) were still created."
        )
        logger.warning(msg)
        print(f"WARNING: {msg}")
        warning = msg

    return {
        "test_cases_created": n,
        "execution_id": execution_id,
        "results_logged": results_logged,
        "warning": warning,
    }
