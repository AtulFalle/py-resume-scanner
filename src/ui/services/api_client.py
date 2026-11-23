import os
from typing import Any

import httpx


class DuplicateResumeError(RuntimeError):
    """Raised when the uploaded file already exists (HTTP 409)."""


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if detail is None:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(detail, str):
        return detail
    return str(detail)


class ResumeApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

    def _request(self, method: str, path: str, timeout: float = 30, **kwargs: Any) -> Any:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                timeout=timeout,
                headers={"accept": "application/json"},
                **kwargs,
            )
        except httpx.HTTPError as error:
            raise RuntimeError(f"Cannot reach the API at {self.base_url}: {error}") from error

        if response.status_code == 409:
            raise DuplicateResumeError(_detail(response))
        if not response.is_success:
            raise RuntimeError(_detail(response))
        return response

    def upload_resume(self, filename: str, content: bytes, content_type: str) -> dict:
        response = self._request(
            "POST",
            "/resumes/upload",
            timeout=120,
            files={"file": (filename, content, content_type)},
        )
        return response.json()

    def list_resumes(
        self,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        category: str | None = None,
        q: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if q:
            params["q"] = q
        return self._request("GET", "/resumes", params=params).json()

    def get_stats(self) -> dict:
        return self._request("GET", "/resumes/stats").json()

    def get_resume(self, resume_id: str) -> dict:
        return self._request("GET", f"/resumes/{resume_id}").json()

    def get_resume_file(self, resume_id: str) -> bytes:
        return self._request("GET", f"/resumes/{resume_id}/file", timeout=60).content

    def reprocess_resume(self, resume_id: str) -> dict:
        return self._request("POST", f"/resumes/{resume_id}/reprocess").json()

    def reprocess_failed(self) -> dict:
        return self._request("POST", "/resumes/reprocess-failed", timeout=60).json()

    def run_research(self, resume_id: str) -> dict:
        return self._request("POST", f"/resumes/{resume_id}/research", timeout=180).json()

    def submit_manual_research(
        self, resume_id: str, text: str, url: str | None = None, source_type: str = "linkedin"
    ) -> dict:
        payload = {"source_type": source_type, "url": url or None, "text": text}
        return self._request(
            "POST", f"/resumes/{resume_id}/research/manual", timeout=180, json=payload
        ).json()

    def search_candidates(
        self,
        query: str,
        limit: int | None = None,
        min_score: int | None = None,
        required_skills: list[str] | None = None,
        categories: list[str] | None = None,
        min_years: float | None = None,
        include_unknown_experience: bool = True,
    ) -> dict:
        payload = {
            "query": query,
            "limit": limit,
            "min_score": min_score,
            "required_skills": required_skills or None,
            "categories": categories or None,
            "min_years": min_years,
            "include_unknown_experience": include_unknown_experience,
        }
        result = self._request("POST", "/search", timeout=3600, json=payload).json()
        if not isinstance(result, dict) or "candidates" not in result:
            raise RuntimeError("Unexpected candidate search response.")
        return result

    def list_categories(self) -> list[str]:
        result = self._request("GET", "/search/categories").json()
        return list(result) if isinstance(result, list) else []


resume_api = ResumeApiClient()
