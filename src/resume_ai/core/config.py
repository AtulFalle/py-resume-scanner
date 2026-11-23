from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Resume AI"
    app_version: str = "0.2.0"
    environment: str = "development"
    debug: bool = True

    # --- Object storage (RustFS / any S3) ---
    # host:port only, no scheme (MinIO client requirement).
    s3_endpoint_url: str = "localhost:9000"
    s3_access_key: str = "resume_ai"
    s3_secret_key: str = "change-this-secret"
    s3_bucket: str = "resumes"
    s3_region: str = "us-east-1"
    s3_secure: bool = False

    # --- Infrastructure ---
    database_url: str
    rabbitmq_url: str
    qdrant_url: str = "http://localhost:6333"

    # --- Generation models ---
    ai_llm_base_url: str = "http://localhost:8080/v1"
    ai_llm_timeout: int = 1200
    ai_resume_extraction_model: str = "resume-extractor"
    # Optional smaller/faster models for the cheap tasks. Empty = reuse the extraction model.
    ai_query_parsing_model: str = ""
    ai_candidate_evaluation_model: str = ""

    # --- Embedding model ---
    ai_embedding_base_url: str
    ai_embedding_model: str
    ai_embedding_dimensions: int = 768
    ai_embedding_timeout: int = 1200

    # --- Search tuning ---
    # Candidates scoring below this are never returned.
    search_min_match_score: int = 60
    # How many candidates (after filtering) are sent to the LLM for evaluation.
    search_shortlist_size: int = 10
    # How many resume chunks to pull from Qdrant before grouping by candidate.
    search_retrieval_limit: int = 200
    # Parallel LLM evaluations. Keep 1 for a llama.cpp server started with --parallel 1.
    search_evaluation_concurrency: int = 1

    # --- Profile research ---
    github_token: str = ""
    research_http_timeout: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
