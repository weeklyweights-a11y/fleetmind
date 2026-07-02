from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://fleetmind:fleetmind@localhost:5432/fleetmind"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    document_storage_path: str = "./document_storage"
    sunflower_dataset_path: str = "./data/sunflower/Buildathon_data_track_files"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    max_upload_bytes: int = 52_428_800
    default_page_limit: int = 50
    default_page_offset: int = 0
    max_page_limit: int = 200

    embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2"
    gemini_model_name: str = "gemini-2.5-flash"
    confidence_review_threshold: float = 0.7
    max_correction_attempts_per_field: int = 3
    chunk_size_chars: int = 500
    chunk_overlap_chars: int = 100
    worker_concurrency: int = 5
    neo4j_write_max_retries: int = 3
    document_max_retries: int = 5
    document_stuck_timeout_sec: int = 300
    document_processing_timeout_sec: int = 600
    document_pipeline_max_wait_sec: int = 3600
    skip_embeddings: bool = False

    db_pool_size: int = 20
    db_max_overflow: int = 30
    neo4j_max_connection_pool_size: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
