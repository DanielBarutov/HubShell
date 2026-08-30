import functools

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GAMECLUB_",
        env_file=".env",
        extra="ignore",
    )

    environment: str = "dev"
    postgres_dsn: str | None = None
    redis_url: str | None = None
    http_host: str = "127.0.0.1"
    http_port: int = 8100
    grpc_host: str = "127.0.0.1"
    grpc_port: int = 51051
    grpc_tls_cert_file: str | None = None
    grpc_tls_key_file: str | None = None
    grpc_tls_client_ca_file: str | None = None
    grpc_tls_require_client_certificate: bool = False
    jwt_secret: str | None = None
    jwt_issuer: str = "gameclub-backend"
    jwt_audience: str = "gameclub-clients"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 7_776_000
    dev_operator_username: str | None = None
    dev_operator_password: str | None = None
    device_bootstrap_token: str | None = None
    workstation_command_ttl_seconds: int = 120
    workstation_stale_after_seconds: int = 45
    workstation_offline_after_seconds: int = 120
    reservation_grace_period_minutes: int = 15
    reservation_sweep_interval_seconds: int = 60
    billing_reconciliation_interval_seconds: int = 60


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
