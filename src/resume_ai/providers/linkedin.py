from resume_ai.providers.base import ResearchProvider, SourceResult

LINKEDIN_SKIP_MESSAGE = (
    "LinkedIn profiles are not fetched automatically because LinkedIn's terms "
    "prohibit scraping. Paste the profile text or the candidate's LinkedIn PDF "
    "export text on the candidate page."
)


class LinkedInProvider(ResearchProvider):
    source_type = "linkedin"

    async def fetch(self, url: str) -> SourceResult:
        return SourceResult(
            source_type=self.source_type,
            url=url,
            status="skipped",
            error=LINKEDIN_SKIP_MESSAGE,
        )
