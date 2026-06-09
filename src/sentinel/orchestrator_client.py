import time

import httpx


class OrchestratorClient:
    """Minimal UiPath Orchestrator Test Automation API client.

    Endpoints per spec §4.3:
      - OAuth2 client_credentials at {identity_url}/connect/token
      - POST {base}/api/TestAutomation/StartTestSetExecution?testSetId=...
      - GET  {base}/odata/TestSetExecutions?$filter=Id eq ...&$expand=TestCaseExecutions
    Folder context via header X-UIPATH-OrganizationUnitId.
    """

    def __init__(self, base_url: str, identity_url: str, client_id: str,
                 client_secret: str, folder_id: str, http: httpx.Client | None = None):
        self._base = base_url.rstrip("/")
        self._identity = identity_url.rstrip("/")
        self._cid = client_id
        self._secret = client_secret
        self._folder = folder_id
        self._http = http or httpx.Client(timeout=60)
        self._token: str | None = None

    def _auth_header(self) -> dict:
        if self._token is None:
            resp = self._http.post(
                f"{self._identity}/connect/token",
                data={"grant_type": "client_credentials", "client_id": self._cid,
                      "client_secret": self._secret, "scope": "OR.Execution OR.TestSets"},
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}",
                "X-UIPATH-OrganizationUnitId": self._folder}

    def start_test_set_execution(self, test_set_id: int) -> int:
        resp = self._http.post(
            f"{self._base}/api/TestAutomation/StartTestSetExecution",
            params={"testSetId": test_set_id, "triggerType": "ExternalTool"},
            headers=self._auth_header(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_results(self, execution_id: int) -> dict:
        resp = self._http.get(
            f"{self._base}/odata/TestSetExecutions",
            params={"$filter": f"Id eq {execution_id}", "$expand": "TestCaseExecutions"},
            headers=self._auth_header(),
        )
        resp.raise_for_status()
        return resp.json()["value"][0]

    def wait(self, execution_id: int, poll_seconds: int = 20,
             timeout_seconds: int = 1800) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            result = self.get_results(execution_id)
            if result.get("Status") in {"Passed", "Failed", "Cancelled"}:
                return result
            time.sleep(poll_seconds)
        raise TimeoutError(f"execution {execution_id} did not finish in {timeout_seconds}s")
