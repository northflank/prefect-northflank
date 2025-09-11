import asyncio
from typing import Any, Dict, Optional

import httpx

from .schemas import JobCreationRequest  # type: ignore


class NorthflankClient:
    """
    Async HTTP client for interacting with the Northflank API.
    """

    def __init__(self, api_token: str, base_url: str = "https://api.northflank.com"):
        self.api_token = api_token
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with authentication headers."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle error responses by extracting and including response details."""
        if response.is_success:
            return

        error_details = ""
        try:
            error_body = response.json()
            error_details = f" Response: {error_body}"
        except Exception:
            try:
                error_details = f" Response: {response.text}"
            except Exception:
                pass

        raise httpx.HTTPStatusError(
            f"HTTP {response.status_code} {response.reason_phrase} for url '{response.url}'.{error_details}",
            request=response.request,
            response=response,
        )

    async def create_job(
        self,
        project_id: str,
        job_request: JobCreationRequest,
    ) -> str:
        """
        Create a new job in Northflank using structured job request.

        Args:
            project_id: The Northflank project ID
            job_request: Complete job creation request with all configuration

        Returns:
            str: The job ID
        """
        job_request.validate_deployment()

        job_data = job_request.to_api_dict()

        response = await self.client.post(
            f"/v1/projects/{project_id}/jobs", json=job_data
        )
        self._handle_error_response(response)
        result = response.json()
        return result["data"]["id"]

    async def start_job_run(
        self,
        project_id: str,
        job_id: str,
        runtime_env_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a job run.

        Returns:
            str: The run ID
        """
        run_data: Dict[str, Any] = {}
        if runtime_env_overrides:
            run_data["runtimeEnvironment"] = runtime_env_overrides

        response = await self.client.post(
            f"/v1/projects/{project_id}/jobs/{job_id}/runs", json=run_data
        )
        self._handle_error_response(response)
        result = response.json()
        return result["data"]["id"]

    async def get_job_run_status(
        self, project_id: str, job_id: str, run_id: str
    ) -> Dict[str, Any]:
        """Get the status of a job run."""
        response = await self.client.get(
            f"/v1/projects/{project_id}/jobs/{job_id}/runs/{run_id}"
        )
        self._handle_error_response(response)
        return response.json()["data"]

    async def wait_for_completion(
        self,
        project_id: str,
        job_id: str,
        run_id: str,
        poll_interval: int = 10,
        timeout: int = 3600,
    ) -> Dict[str, Any]:
        """
        Wait for a job run to complete.

        Returns:
            Dict containing the final job run status
        """
        elapsed = 0

        while elapsed < timeout:
            status = await self.get_job_run_status(project_id, job_id, run_id)

            if status.get("status") in ["SUCCESS", "FAILED"]:
                return status

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(
            f"Job run {run_id} did not complete within {timeout} seconds"
        )

    async def abort_job_run(self, project_id: str, job_id: str, run_id: str) -> None:
        """Cancel a job run."""
        response = await self.client.delete(
            f"/v1/projects/{project_id}/jobs/{job_id}/runs/{run_id}"
        )
        self._handle_error_response(response)

    async def delete_job(self, project_id: str, job_id: str) -> None:
        """Delete a job."""
        response = await self.client.delete(f"/v1/projects/{project_id}/jobs/{job_id}")
        self._handle_error_response(response)
