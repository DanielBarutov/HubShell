def test_analytics_report_actor_is_registered_on_shared_broker() -> None:
    """Проверяет регистрацию фонового отчёта в общем брокере."""
    from gameclub_backend.jobs.reports import generate_analytics_report

    assert generate_analytics_report.queue_name == "analytics-reports"
    assert generate_analytics_report.actor_name.endswith("generate_analytics_report")
