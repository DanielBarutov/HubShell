import sys
from types import ModuleType
from unittest.mock import Mock

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import _start_pyroscope


def test_pyroscope_is_disabled_without_server_address() -> None:
    """Проверяет, что профилировщик не запускается без адреса сервера."""
    assert _start_pyroscope(Settings()) is None


def test_pyroscope_configures_application_and_returns_shutdown(
    monkeypatch,
) -> None:
    """Проверяет конфигурацию профилей приложения и возврат функции остановки."""
    pyroscope = ModuleType("pyroscope")
    pyroscope.configure = Mock()
    pyroscope.shutdown = Mock()
    monkeypatch.setitem(sys.modules, "pyroscope", pyroscope)

    shutdown = _start_pyroscope(
        Settings(
            environment="test",
            pyroscope_server_address="http://pyroscope:4040",
            pyroscope_application_name="gameclub-backend-test",
            pyroscope_sample_rate=50,
        )
    )

    pyroscope.configure.assert_called_once_with(
        application_name="gameclub-backend-test",
        server_address="http://pyroscope:4040",
        sample_rate=50,
        tags={"environment": "test", "service": "backend-http"},
    )
    assert shutdown is pyroscope.shutdown


def test_pyroscope_configuration_failure_does_not_abort_startup(
    monkeypatch,
) -> None:
    """Проверяет, что недоступный профилировщик не прерывает запуск backend."""
    pyroscope = ModuleType("pyroscope")
    pyroscope.configure = Mock(side_effect=RuntimeError("server not ready"))
    pyroscope.shutdown = Mock()
    monkeypatch.setitem(sys.modules, "pyroscope", pyroscope)

    assert _start_pyroscope(
        Settings(pyroscope_server_address="http://pyroscope:4040")
    ) is None
