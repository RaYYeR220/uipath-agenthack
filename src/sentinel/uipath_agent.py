"""UiPath Orchestrator Jobs-API client and TargetAgent adapter.

Invokes a deployed UiPath autonomous agent as an Orchestrator job and returns
its text output.  Mirrors the OrchestratorClient style (injectable httpx.Client,
cached OAuth token, no real network in tests).
"""
import json
import os
import time

import httpx
from pydantic import BaseModel

from .target import TargetAgent


class UiPathConfig(BaseModel):
    """Configuration for the UiPath Orchestrator Jobs API."""

    base_url: str
    identity_url: str = "https://cloud.uipath.com/identity_"
    client_id: str
    client_secret: str
    folder_path: str
    scope: str = "OR.Jobs OR.Execution OR.Folders"

    @classmethod
    def from_env(cls) -> "UiPathConfig":
        """Build config from environment variables.

        Required: UIPATH_BASE_URL, UIPATH_CLIENT_ID, UIPATH_CLIENT_SECRET,
                  UIPATH_FOLDER_PATH
        Optional: UIPATH_IDENTITY_URL, UIPATH_SCOPE
        """
        required = {
            "UIPATH_BASE_URL": "base_url",
            "UIPATH_CLIENT_ID": "client_id",
            "UIPATH_CLIENT_SECRET": "client_secret",
            "UIPATH_FOLDER_PATH": "folder_path",
        }
        missing = [var for var in required if var not in os.environ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )
        return cls(
            base_url=os.environ["UIPATH_BASE_URL"],
            identity_url=os.environ.get("UIPATH_IDENTITY_URL", "https://cloud.uipath.com/identity_"),
            client_id=os.environ["UIPATH_CLIENT_ID"],
            client_secret=os.environ["UIPATH_CLIENT_SECRET"],
            folder_path=os.environ["UIPATH_FOLDER_PATH"],
            scope=os.environ.get("UIPATH_SCOPE", "OR.Jobs OR.Execution OR.Folders"),
        )


class UiPathAgentClient:
    """Client that invokes a deployed UiPath autonomous agent via the Jobs API."""

    def __init__(self, config: UiPathConfig, http: httpx.Client | None = None):
        self._config = config
        self._base = config.base_url.rstrip("/")
        self._identity = config.identity_url.rstrip("/")
        self._http = http or httpx.Client(timeout=60)
        self._token: str | None = None
        self._release_key_cache: dict[str, str] = {}

    def _auth_headers(self) -> dict:
        """Fetch and cache the OAuth token; return Authorization + FolderPath headers."""
        if self._token is None:
            resp = self._http.post(
                f"{self._identity}/connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "scope": self._config.scope,
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return {
            "Authorization": f"Bearer {self._token}",
            "X-UIPATH-FolderPath": self._config.folder_path,
        }

    def get_release_key(self, process_key: str) -> str:
        """Resolve the Orchestrator release key for a given process key."""
        resp = self._http.get(
            f"{self._base}/odata/Releases",
            params={"$filter": f"ProcessKey eq '{process_key}'"},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()["value"][0]["Key"]

    def start_job(self, release_key: str, input_args: dict) -> int:
        """Start an Orchestrator job and return the job ID."""
        resp = self._http.post(
            f"{self._base}/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs",
            json={
                "startInfo": {
                    "ReleaseKey": release_key,
                    "JobsCount": 1,
                    "Strategy": "JobsCount",
                    # InputArguments must be a JSON-encoded STRING (double-serialised)
                    "InputArguments": json.dumps(input_args),
                }
            },
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()["value"][0]["Id"]

    def get_job(self, job_id: int) -> dict:
        """Fetch the current state of a job."""
        resp = self._http.get(
            f"{self._base}/odata/Jobs({job_id})",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def wait_job(self, job_id: int, poll_seconds: int = 3,
                 timeout_seconds: int = 600) -> dict:
        """Poll get_job until a terminal state; raise TimeoutError on deadline."""
        terminal = {"Successful", "Faulted", "Stopped"}
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            job = self.get_job(job_id)
            if job.get("State") in terminal:
                return job
            time.sleep(poll_seconds)
        raise TimeoutError(f"job {job_id} did not finish within {timeout_seconds}s")

    def run_agent(self, input_args: dict, process_key: str) -> dict:
        """Resolve release, start job, wait for completion, return parsed output.

        Caches the release key per process_key to avoid redundant Releases calls.
        Raises RuntimeError if the job does not reach Successful state.
        Returns {} if OutputArguments is None.
        """
        if process_key not in self._release_key_cache:
            self._release_key_cache[process_key] = self.get_release_key(process_key)
        release_key = self._release_key_cache[process_key]

        job_id = self.start_job(release_key, input_args)
        job = self.wait_job(job_id)

        state = job.get("State")
        if state != "Successful":
            info = job.get("Info", "")
            raise RuntimeError(f"agent job {state}: {info}")

        raw = job.get("OutputArguments")
        if raw is None:
            return {}
        return json.loads(raw)


class UiPathTargetAgent:
    """Adapts UiPathAgentClient to the TargetAgent protocol used by run_audit().

    Pass an instance of this as the `target` argument to run_audit(); it wraps
    any UiPath autonomous agent deployed in Orchestrator and maps a single text
    message to a single text reply via configurable argument keys.
    """

    def __init__(
        self,
        client: UiPathAgentClient,
        process_key: str,
        input_key: str = "customer_message",
        output_key: str = "content",
    ):
        self._client = client
        self._process_key = process_key
        self._input_key = input_key
        self._output_key = output_key

    def ask(self, message: str) -> str:
        out = self._client.run_agent(
            {self._input_key: message}, self._process_key
        )
        return str(out.get(self._output_key, ""))
