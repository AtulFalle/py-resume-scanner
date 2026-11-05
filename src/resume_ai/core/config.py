from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Resume AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "resume_ai"
    s3_secret_key: str = "change-this-secret"
    s3_bucket: str = "resumes"
    s3_region: str = "us-east-1"
    ai_llm_base_url: str = "http://localhost:8080/v1"
    ai_llm_timeout: int = 120
    ai_resume_extraction_model: str = "resume-extractor"
    database_url: str
    rabbitmq_url: str
    qdrant_url: str = "http://localhost:6333"
    ai_embedding_base_url: str
    ai_embedding_model: str
    ai_embedding_dimensions: int = 768

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
