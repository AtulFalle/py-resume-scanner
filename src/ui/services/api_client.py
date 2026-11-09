import os

import httpx


class ResumeApiClient:
    def __init__(self):
        self.base_url = os.getenv(
            "API_BASE_URL",
            "http://localhost:8000",
        ).rstrip("/")

    def upload_resume(self, filename: str, content: bytes, content_type: str):
        response = httpx.post(
            f"{self.base_url}/resumes/upload",
            files={
                "file": (filename, content, content_type),
            },
            timeout=120,
        )

        if not response.is_success:
            raise RuntimeError(f"Upload failed ({response.status_code}): {response.text}")

        return response.json()

    def list_resumes(self) -> list[dict]:
        response = httpx.get(
            f"{self.base_url}/search",
            headers={"accept": "application/json"},
            timeout=30,
        )

        if not response.is_success:
            raise RuntimeError(f"Failed to fetch resumes ({response.status_code}): {response.text}")

        result = response.json()

        if not isinstance(result, list):
            raise RuntimeError("Unexpected response: expected a list of resumes.")

        return result

    def search_candidates(self, query: str, limit: int = 50) -> dict:
        response = httpx.post(
            f"{self.base_url}/search",
            json={
                "query": query,
                "limit": limit,
            },
            headers={"accept": "application/json"},
            timeout=300,
        )

        if not response.is_success:
            raise RuntimeError(f"Candidate search failed ({response.status_code}): {response.text}")

        result = response.json()

        if not isinstance(result, dict) or "candidates" not in result:
            raise RuntimeError("Unexpected candidate search response.")

        return result


resume_api = ResumeApiClient()
