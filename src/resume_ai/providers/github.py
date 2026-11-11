
import json
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from resume_ai.research.providers.base import (
    ResearchProvider,
    SourceEvidence,
    SourceResult,
)

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
MAX_REPOSITORIES = 10


class GitHubProvider(ResearchProvider):
    source_type = "github"

    async def fetch(self, url: str) -> SourceResult:
        parsed = urlsplit(url)

        if parsed.scheme not in {"http", "https"}:
            return self._failed(url, "Unsupported URL scheme")

        hostname = (parsed.hostname or "").lower().removeprefix("www.")

        if hostname != "github.com":
            return self._failed(url, "URL is not a GitHub URL")

        path_parts = [
            part for part in parsed.path.strip("/").split("/") if part
        ]

        if not path_parts:
            return self._failed(url, "GitHub username or repository is missing")

        username = path_parts[0]

        if username.startswith(("-", ".")) or not username.replace("-", "").isalnum():
            return self._failed(url, "Invalid GitHub username")

        repository = path_parts[1] if len(path_parts) >= 2 else None

        if len(path_parts) > 2:
            return self._failed(url, "Unsupported GitHub URL format")

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ResumeResearch/1.0",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=False,
                headers=headers,
            ) as client:
                if repository:
                    evidence = await self._fetch_repository(
                        client,
                        username,
                        repository,
                    )
                else:
                    evidence = await self._fetch_profile(
                        client,
                        username,
                    )

            return SourceResult(
                source_type=self.source_type,
                url=url,
                status="completed",
                evidence=evidence,
            )

        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code

            if status_code == 404:
                message = "GitHub profile or repository was not found or is not public"
            elif status_code == 403:
                message = "GitHub API rate limit or access restriction"
            else:
                message = f"GitHub API returned HTTP {status_code}"

            logger.warning("GitHub research failed for %s: %s", url, message)
            return self._failed(url, message)

        except (httpx.RequestError, ValueError) as error:
            logger.exception("GitHub API request failed for %s", url)
            return self._failed(url, str(error))

    async def _fetch_profile(
        self,
        client: httpx.AsyncClient,
        username: str,
    ) -> list[SourceEvidence]:
        profile_response = await client.get(
            f"{GITHUB_API}/users/{username}",
        )
        profile_response.raise_for_status()
        profile = profile_response.json()

        profile_data = {
            "username": profile.get("login"),
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "blog": profile.get("blog"),
            "public_repositories": profile.get("public_repos"),
            "followers": profile.get("followers"),
            "following": profile.get("following"),
            "created_at": profile.get("created_at"),
            "profile_url": profile.get("html_url"),
        }

        repositories_response = await client.get(
            f"{GITHUB_API}/users/{username}/repos",
            params={
                "type": "owner",
                "sort": "updated",
                "per_page": MAX_REPOSITORIES,
            },
        )
        repositories_response.raise_for_status()

        repositories = [
            {
                "name": repo.get("name"),
                "description": repo.get("description"),
                "url": repo.get("html_url"),
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count"),
                "forks": repo.get("forks_count"),
                "updated_at": repo.get("updated_at"),
                "topics": repo.get("topics", []),
            }
            for repo in repositories_response.json()
        ]

        retrieved_at = datetime.now(UTC)

        return [
            SourceEvidence(
                url=profile.get("html_url", f"https://github.com/{username}"),
                title=f"GitHub profile: {username}",
                content=json.dumps(profile_data, ensure_ascii=False),
                retrieved_at=retrieved_at,
            ),
            SourceEvidence(
                url=f"https://github.com/{username}",
                title=f"Public repositories for {username}",
                content=json.dumps(repositories, ensure_ascii=False),
                retrieved_at=retrieved_at,
                metadata={"repository_count": len(repositories)},
            ),
        ]

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        username: str,
        repository: str,
    ) -> list[SourceEvidence]:
        response = await client.get(
            f"{GITHUB_API}/repos/{username}/{repository}",
        )
        response.raise_for_status()
        repo = response.json()

        repository_data = {
            "name": repo.get("full_name"),
            "description": repo.get("description"),
            "url": repo.get("html_url"),
            "language": repo.get("language"),
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "watchers": repo.get("watchers_count"),
            "created_at": repo.get("created_at"),
            "updated_at": repo.get("updated_at"),
            "topics": repo.get("topics", []),
            "license": (repo.get("license") or {}).get("spdx_id"),
        }

        return [
            SourceEvidence(
                url=repo.get("html_url", f"https://github.com/{username}/{repository}"),
                title=f"GitHub repository: {repo.get('full_name')}",
                content=json.dumps(repository_data, ensure_ascii=False),
                retrieved_at=datetime.now(UTC),
            )
        ]

    def _failed(self, url: str, message: str) -> SourceResult:
        return SourceResult(
            source_type=self.source_type,
            url=url,
            status="failed",
            error=message,
        )
