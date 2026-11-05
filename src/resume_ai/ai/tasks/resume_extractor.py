from resume_ai.ai.registry import model_registry
from resume_ai.ai.runtime import llm_runtime
from resume_ai.schemas.resume_schema import ResumeExtraction


class ResumeExtractionTask:
    async def execute(self, document_text: str) -> ResumeExtraction:
        model = model_registry.get("resume_extraction")

        messages = [
            {
                "role": "system",
                "content": """
                    You are a resume information extraction engine.

                    Extract information strictly from the supplied resume.

                    Rules:
                    - Never invent or assume candidate information.
                    - Use null for missing scalar values.
                    - Use empty arrays for missing collections.
                    - Preserve company names, designations and dates.
                    - Extract technical and professional skills.
                    - Do not confuse projects with employment history.
                    - Calculate total experience only when dates support it.
                    - Return only information supported by the resume.
                    """,
            },
            {
                "role": "user",
                "content": f"Extract candidate information from this resume:\n\n{document_text}",
            },
        ]

        content = await llm_runtime.generate(
            model=model,
            messages=messages,
            response_schema=ResumeExtraction.model_json_schema(),
        )

        return ResumeExtraction.model_validate_json(content)


resume_extraction_task = ResumeExtractionTask()
