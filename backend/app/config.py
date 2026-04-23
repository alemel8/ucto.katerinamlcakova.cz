from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    IMAP_HOST: str = "imap-216992.m92.wedos.net"
    IMAP_PORT: int = 993
    EMAIL_ADDRESS: str = "fakturace@katerinamlcakova.cz"
    EMAIL_PASSWORD: str = ""

    FRONTEND_USERNAME: str = "fakturace@katerinamlcakova.cz"
    FRONTEND_PASSWORD: str = ""

    PDF_STORAGE_PATH: str = "./pdfs"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
