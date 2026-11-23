import json
import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.core.database import SessionFactory
from resume_ai.message_queue.publisher import publisher
from resume_ai.models.candidate import CandidateProfile
from resume_ai.models.research import ResumeResearch
from resume_ai.models.resume import Resume
from resume_ai.providers.base import SourceResult
from resume_ai.providers.registry import provider_registry
from resume_ai.research.discovery import discover_urls

logger = logging.getLogger(__name__)

RESEARCH_QUEUE = "resume.research"

MANUAL_TEXT_LIMIT = 8000
SUPPLEMENTARY_LIMIT = 1500


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _result_to_dict(result: SourceResult) -> dict:
    return _jsonable(asdict(result))


def _github_highlights(evidence: list[dict]) -> dict:
    highlights: dict = {}
    for item in evidence:
        try:
            data = json.loads(item.get("content") or "")
        except ValueError:
            continue

        if isinstance(data, dict):
            for key in ("name", "bio", "public_repositories", "followers"):
                if key in data and key not in highlights:
                    highlights[key] = data[key]
            if "stars" in data and "top_repositories" not in highlights:
                # Single repository URL.
                highlights["top_repositories"] = [_repo_summary(data)]
        elif isinstance(data, list):
            repos = [repo for repo in data if isinstance(repo, dict)]
            languages = Counter(repo["language"] for repo in repos if repo.get("language"))
            highlights["top_languages"] = [name for name, _ in languages.most_common(5)]
            ranked = sorted(repos, key=lambda repo: repo.get("stars") or 0, reverse=True)
            highlights["top_repositories"] = [_repo_summary(repo) for repo in ranked[:5]]
    return highlights


def _repo_summary(repo: dict) -> dict:
    return {
        "name": repo.get("name"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "stars": repo.get("stars"),
        "url": repo.get("url"),
    }


def _source_entry(result: dict) -> dict:
    source_type = result.get("source_type")
    evidence = result.get("evidence") or []
    first = evidence[0] if evidence else {}
    highlights: dict = {}
    title = first.get("title")

    if result.get("status") == "completed":
        if result.get("metadata_manual") or (first.get("metadata") or {}).get("provided_by"):
            highlights = {"excerpt": (first.get("content") or "")[:400]}
        elif source_type == "github":
            highlights = _github_highlights(evidence)
        elif source_type == "website":
            metadata = first.get("metadata") or {}
            highlights = {
                "title": title,
                "description": metadata.get("description"),
                "excerpt": (first.get("content") or "")[:400],
            }
        elif evidence:
            highlights = {"excerpt": (first.get("content") or "")[:400]}

    return {
        "source_type": source_type,
        "url": result.get("url"),
        "status": result.get("status"),
        "error": result.get("error"),
        "title": title,
        "highlights": highlights,
    }


def _overall_status(results: list[dict]) -> str:
    statuses = [r.get("status") for r in results if r.get("status") != "skipped"]
    if not statuses:
        return "completed"
    completed = sum(1 for status in statuses if status == "completed")
    if completed == len(statuses):
        return "completed"
    if completed == 0 and all(status == "failed" for status in statuses):
        return "failed"
    return "partial"


def _build_report(results: list[dict]) -> dict:
    sources = [_source_entry(result) for result in results]
    status = _overall_status(results)
    counts = Counter(source["status"] for source in sources)

    if not sources:
        summary = "No supported profile URLs were found in the resume."
    else:
        parts = [f"{counts[name]} {name}" for name in ("completed", "failed", "skipped") if counts[name]]
        summary = f"Researched {len(sources)} source(s): {', '.join(parts)}."

    return {"status": status, "summary": summary, "sources": sources}


class ResearchService:
    async def schedule(
        self,
        resume_id: UUID,
        extracted_text: str,
        extra_urls: Iterable[str] = (),
    ) -> ResumeResearch:
        discovered_urls = [
            asdict(discovered_url)
            for discovered_url in discover_urls(extracted_text, extra_urls)
        ]

        # 2. Create a research run.
        no_sources_found = not discovered_urls
        manual_results = await self._manual_results(resume_id) if no_sources_found else []

        research = ResumeResearch(
            resume_id=resume_id,
            status="completed" if no_sources_found else "queued",
            discovered_urls=discovered_urls,
            source_results=manual_results,
            report=(
                _build_report(manual_results)
                if manual_results
                else {
                    "status": "no_sources",
                    "summary": "No supported profile URLs were found in the resume.",
                    "sources": [],
                }
                if no_sources_found
                else None
            ),
            completed_at=datetime.now(UTC) if no_sources_found else None,
        )

        async with SessionFactory() as db:
            db.add(research)
            await db.commit()
            await db.refresh(research)

        logger.info(
            "Research run %s created for resume %s; URLs found: %d",
            research.id,
            resume_id,
            len(discovered_urls),
        )

        # No URLs means the research lifecycle is already complete.
        if no_sources_found:
            return research

        # 3. Enqueue the independent research job.
        try:
            await publisher.publish_message(
                RESEARCH_QUEUE,
                {
                    "research_id": str(research.id),
                    "resume_id": str(resume_id),
                },
            )
        except Exception as error:
            logger.exception(
                "Could not enqueue research run %s",
                research.id,
            )

            async with SessionFactory() as db:
                await db.execute(
                    update(ResumeResearch)
                    .where(ResumeResearch.id == research.id)
                    .values(
                        status="failed",
                        error_message=str(error)[:1000],
                    )
                )
                await db.commit()

            research.status = "failed"
            research.error_message = str(error)[:1000]

        return research

    async def run(self, research_id: UUID) -> None:
        async with SessionFactory() as db:
            result = await db.execute(
                update(ResumeResearch)
                .where(
                    ResumeResearch.id == research_id,
                    ResumeResearch.status == "queued",
                )
                .values(
                    status="processing",
                    started_at=datetime.now(UTC),
                    error_message=None,
                )
                .returning(ResumeResearch.discovered_urls, ResumeResearch.resume_id)
            )
            row = result.first()
            await db.commit()

        if row is None:
            logger.info("Skipping research %s: not queued or already claimed", research_id)
            return

        discovered_urls: list[dict] = row[0] or []
        resume_id: UUID = row[1]

        try:
            results: list[dict] = []

            for entry in discovered_urls:
                results.append(await self._fetch_source(entry))

            # Keep recruiter-pasted profiles (e.g. LinkedIn text) across runs.
            results.extend(await self._manual_results(resume_id))

            report = _build_report(results)

            async with SessionFactory() as db:
                await db.execute(
                    update(ResumeResearch)
                    .where(ResumeResearch.id == research_id)
                    .values(
                        source_results=results,
                        report=report,
                        status=report["status"],
                        completed_at=datetime.now(UTC),
                    )
                )
                await db.commit()

            logger.info("Research run %s finished: %s", research_id, report["status"])

        except Exception as error:
            logger.exception("Research run %s failed", research_id)
            async with SessionFactory() as db:
                await db.execute(
                    update(ResumeResearch)
                    .where(ResumeResearch.id == research_id)
                    .values(
                        status="failed",
                        error_message=str(error)[:1000],
                        completed_at=datetime.now(UTC),
                    )
                )
                await db.commit()

    async def _fetch_source(self, entry: dict) -> dict:
        source_type = str(entry.get("source_type") or "")
        url = str(entry.get("normalized_url") or entry.get("original_url") or "")
        provider = provider_registry.get(source_type)

        if provider is None:
            return _result_to_dict(
                SourceResult(
                    source_type=source_type,
                    url=url,
                    status="skipped",
                    error=f"No provider is available for source type: {source_type}",
                )
            )

        try:
            return _result_to_dict(await provider.fetch(url))
        except Exception as error:
            logger.exception("Provider %s failed for %s", source_type, url)
            return _result_to_dict(
                SourceResult(
                    source_type=source_type,
                    url=url,
                    status="failed",
                    error=f"Provider error: {error}"[:500],
                )
            )

    async def _manual_results(self, resume_id: UUID) -> list[dict]:
        """Latest recruiter-provided entry per source type, from any run."""
        async with SessionFactory() as db:
            rows = await db.execute(
                select(ResumeResearch.source_results)
                .where(ResumeResearch.resume_id == resume_id)
                .order_by(ResumeResearch.created_at.asc(), ResumeResearch.id.asc())
            )
            latest: dict[str, dict] = {}
            for source_results in rows.scalars().all():
                for result in source_results or []:
                    if _is_manual(result):
                        latest[str(result.get("source_type"))] = result
        return list(latest.values())

    async def rerun(self, resume_id: UUID) -> ResumeResearch:
        async with SessionFactory() as db:
            resume = await db.get(Resume, resume_id)

            if resume is None:
                raise LookupError("Resume not found")

            if not resume.extracted_text:
                raise ValueError("Resume has no extracted text to research")

            extracted_text = resume.extracted_text
            profile = await db.get(CandidateProfile, resume_id)
            links = (profile.links if profile else None) or []

        extra_urls = [link["url"] for link in links if link.get("url")]
        return await self.schedule(resume_id, extracted_text, extra_urls=extra_urls)

    async def add_manual_profile(
        self,
        resume_id: UUID,
        source_type: str,
        url: str | None,
        text: str,
    ) -> ResumeResearch:
        source_type = source_type.lower().strip()
        now = datetime.now(UTC)
        manual = _result_to_dict(
            SourceResult(
                source_type=source_type,
                url=url or "",
                status="completed",
                evidence=[
                    _make_manual_evidence(url or "", source_type, text, now),
                ],
            )
        )

        async with SessionFactory() as db:
            if await db.get(Resume, resume_id) is None:
                raise LookupError("Resume not found")

            run = await self.get_latest(db, resume_id)

            if run is None:
                run = ResumeResearch(
                    resume_id=resume_id,
                    status="completed",
                    discovered_urls=[],
                    source_results=[],
                    completed_at=now,
                )
                db.add(run)

            kept = [
                result
                for result in (run.source_results or [])
                if not (
                    result.get("source_type") == source_type
                    and _is_manual(result)
                )
            ]
            results = [*kept, manual]
            run.source_results = results
            run.report = _build_report(results)
            if run.status in {"completed", "partial", "failed"}:
                run.status = run.report["status"]
                run.completed_at = run.completed_at or now

            await db.commit()
            await db.refresh(run)
            return run

    async def get_latest(
        self,
        db: AsyncSession,
        resume_id: UUID,
    ) -> ResumeResearch | None:
        result = await db.execute(
            select(ResumeResearch)
            .where(ResumeResearch.resume_id == resume_id)
            .order_by(ResumeResearch.created_at.desc(), ResumeResearch.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def supplementary_text(
        self,
        db: AsyncSession,
        resume_ids: list[str],
    ) -> dict[str, str]:
        texts: dict[str, str] = {}

        for resume_id in resume_ids:
            try:
                run = await self.get_latest(db, UUID(str(resume_id)))
            except ValueError:
                continue

            if run is None or not run.report:
                continue

            text = _compact_text(run.report, run.source_results or [])
            if text:
                texts[str(resume_id)] = text[:SUPPLEMENTARY_LIMIT]

        return texts

    def serialize_research(self, run: ResumeResearch) -> dict:
        return serialize_research(run)


def _make_manual_evidence(url: str, source_type: str, text: str, now: datetime):
    from resume_ai.providers.base import SourceEvidence

    return SourceEvidence(
        url=url,
        title=f"{source_type.capitalize()} profile (pasted by recruiter)",
        content=text[:MANUAL_TEXT_LIMIT],
        retrieved_at=now,
        metadata={"provided_by": "recruiter"},
    )


def _is_manual(result: dict) -> bool:
    evidence = result.get("evidence") or []
    return bool(evidence) and (evidence[0].get("metadata") or {}).get("provided_by") == "recruiter"


def _display_url(url: str | None) -> str:
    return (url or "").split("://", 1)[-1].removeprefix("www.")


def _compact_text(report: dict, source_results: list[dict]) -> str:
    lines: list[str] = []
    manual_by_url = {(r.get("source_type"), r.get("url")): r for r in source_results}

    for source in report.get("sources") or []:
        if source.get("status") != "completed":
            continue

        highlights = source.get("highlights") or {}
        source_type = source.get("source_type")
        result = manual_by_url.get((source_type, source.get("url"))) or {}

        if _is_manual(result):
            excerpt = (result["evidence"][0].get("content") or "")[:800]
            label = {"linkedin": "LinkedIn"}.get(source_type, str(source_type).capitalize())
            if excerpt:
                lines.append(f"{label} (pasted by recruiter): {excerpt}")
        elif source_type == "github":
            parts = []
            if highlights.get("top_languages"):
                parts.append("languages " + ", ".join(highlights["top_languages"]))
            repos = [
                f"{repo['name']} (\u2605{repo.get('stars') or 0}"
                + (f", {repo['language']}" if repo.get("language") else "")
                + ")"
                for repo in highlights.get("top_repositories") or []
                if repo.get("name")
            ]
            if repos:
                parts.append("repos: " + ", ".join(repos))
            if highlights.get("bio"):
                parts.append(f"bio: {highlights['bio']}")
            if parts:
                lines.append(f"GitHub {_display_url(source.get('url'))}: " + "; ".join(parts))
        elif source_type == "website":
            title = highlights.get("title") or ""
            excerpt = highlights.get("excerpt") or ""
            if title or excerpt:
                lines.append(f"Website: {title} \u2014 {excerpt}".strip(" \u2014"))
        elif highlights.get("excerpt"):
            lines.append(f"{source_type}: {highlights['excerpt']}")

    return "\n".join(lines)


def serialize_research(run: ResumeResearch) -> dict:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    return {
        "id": str(run.id),
        "resume_id": str(run.resume_id),
        "status": run.status,
        "discovered_urls": run.discovered_urls or [],
        "source_results": run.source_results or [],
        "report": run.report,
        "error_message": run.error_message,
        "created_at": iso(run.created_at),
        "started_at": iso(run.started_at),
        "completed_at": iso(run.completed_at),
    }


research_service = ResearchService()