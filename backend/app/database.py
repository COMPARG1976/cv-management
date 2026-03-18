from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://cv_user:cv_password@localhost:5433/cv_management"
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 720
    auth_provider: str = "fake"
    default_password: str = "Demo123!"
    cors_origins: str = "http://localhost:8082"
    ai_service_url: str = "http://ai-services:8000"
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 10

    # ── Microsoft Entra ID (Azure AD) ─────────────────────────────────────────
    entra_tenant_id: Optional[str] = None
    entra_client_id: Optional[str] = None
    entra_client_secret: Optional[str] = None
    entra_audience: Optional[str] = None       # default: api://<client_id>
    entra_redirect_uri: str = "http://localhost:8082/auth/callback"

    # ── SharePoint / Microsoft Graph ───────────────────────────────────────────
    sharepoint_site_url: str = ""          # es. https://mashfroggroup.sharepoint.com/sites/ENT_SOLUTION_M4P_STAFF
    sharepoint_drive_name: str = "Documenti"
    sharepoint_root_folder: str = "STAFF_DATA_AND_DOCUMENTS"

    @property
    def entra_enabled(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_client_id and self.entra_client_secret)

    @property
    def sharepoint_enabled(self) -> bool:
        return bool(self.entra_enabled and self.sharepoint_site_url)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
