import functools

from pydantic import Field
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
    login_grant_minutes: int = Field(default=1, ge=0, le=4_294_967_295)
    reservation_grace_period_minutes: int = 15
    reservation_sweep_interval_seconds: int = 60
    billing_reconciliation_interval_seconds: int = 60
    kafka_bootstrap_servers: str | None = None
    pyroscope_server_address: str | None = None
    pyroscope_application_name: str = "gameclub-backend-http"
    pyroscope_sample_rate: int = 100
    v2_snapshot_signing_key_id: str | None = None
    v2_snapshot_signing_private_key_b64: str | None = None
    v2_snapshot_policy_version: str = "v2-local-ledger-1"
    v2_observability_enabled: bool = False
    v2_metrics_port: int = 9108
    v2_client_facts_metrics_port: int = 9109
    v2_confirmed_analytics_metrics_port: int = 9110
    otel_exporter_otlp_endpoint: str | None = None


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
