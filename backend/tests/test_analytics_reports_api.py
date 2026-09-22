import uuid

import pytest

from gameclub_backend.modules.auth.domain import Principal, SubjectType


@pytest.mark.asyncio
async def test_report_api_creates_job_and_downloads_protected_csv(api_context) -> None:
    """Проверяет постановку отчёта в очередь и скачивание защищённого CSV."""
    response = await api_context.client.post(
        "/api/v2/analytics/reports",
        headers=api_context.headers,
        json={
            "report_name": "daily",
            "export_format": "csv",
            "idempotency_key": "api-report-1",
            "include_pii": False,
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["download_url"] is not None

    job_id = payload["id"]
    job = await api_context.application.state.report_jobs.complete_job(
        uuid.UUID(job_id),
        b"metric,value\nrevenue_cents,1000\n",
        "text/csv",
    )
    assert job.status.value == "succeeded"

    artifact = await api_context.client.get(
        payload["download_url"],
        headers=api_context.headers,
    )
    assert artifact.status_code == 200
    assert artifact.text == "metric,value\nrevenue_cents,1000\n"
    assert artifact.headers["etag"] == job.artifact_sha256


@pytest.mark.asyncio
async def test_report_api_rejects_pii_without_special_permission(api_context) -> None:
    """Проверяет отказ отчёта с PII без специального разрешения."""
    token_service = api_context.application.state.jwt_service
    assert token_service is not None
    limited = Principal(
        subject_id="limited-operator",
        subject_type=SubjectType.OPERATOR,
        roles=frozenset({"operator"}),
        permissions=frozenset({"analytics.read", "analytics.export"}),
    )
    token, _ = token_service.issue_access_token(limited)
    response = await api_context.client.post(
        "/api/v2/analytics/reports",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "report_name": "clients",
            "export_format": "csv",
            "idempotency_key": "api-report-pii-1",
            "include_pii": True,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_report_api_returns_404_for_unknown_artifact(api_context) -> None:
    """Проверяет, что неизвестная ссылка на артефакт не раскрывает детали."""
    response = await api_context.client.get(
        "/api/v2/analytics/reports/00000000-0000-0000-0000-000000000000/artifact?token=bad",
        headers=api_context.headers,
    )
    assert response.status_code == 404
