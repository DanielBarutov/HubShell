import pytest


@pytest.mark.api
@pytest.mark.asyncio
async def test_analytics_v2_dashboard_exposes_blocks_filters_and_explicit_states(
    api_context,
) -> None:
    """Проверяет блоки dashboard v2, фильтры и явные состояния данных."""
    response = await api_context.client.get(
        "/api/v2/analytics/dashboard",
        headers=api_context.headers,
        params={
            "start_at": "2026-09-20T00:00:00Z",
            "end_at": "2026-09-22T00:00:00Z",
            "category_key": "drinks",
            "payment_method_key": "cash",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v2"
    assert payload["timezone"] == "Europe/Moscow"
    assert set(payload["blocks"]) >= {
        "finance",
        "occupancy",
        "clients",
        "workstations",
        "tariffs",
        "products",
        "deposits",
    }
    assert payload["filters"]["category_key"] == "drinks"
    assert payload["blocks"]["products"]["state"] == "empty"
    assert payload["blocks"]["products"]["metrics"]["returns_cents"]["state"] == "not_available"


@pytest.mark.api
@pytest.mark.asyncio
async def test_analytics_v2_drill_down_is_permission_aware(api_context) -> None:
    """Проверяет permission-aware доступ к операторской детализации."""
    response = await api_context.client.get(
        "/api/v2/analytics/drill-down",
        headers=api_context.headers,
        params={
            "start_at": "2026-09-20T00:00:00Z",
            "end_at": "2026-09-22T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "empty"
    assert response.json()["items"] == []
