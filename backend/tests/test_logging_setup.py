import uuid

from gameclub_backend.logging_setup import configure_stdout_logger


def test_application_info_logs_are_written_to_stdout(capsys) -> None:
    """Проверяет, что INFO-сообщения приложения доступны в docker logs."""
    logger = configure_stdout_logger(f"test.application.{uuid.uuid4()}")

    logger.info("diagnostic_event status=accepted")

    assert "diagnostic_event status=accepted" in capsys.readouterr().out
