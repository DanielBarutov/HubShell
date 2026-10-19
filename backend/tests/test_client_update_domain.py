"""Fleet deployment protects all-ready admission and independently verified success."""

import dataclasses
import datetime
import uuid

import pytest

from gameclub_backend.modules.client_updates.domain import (
    Deployment,
    DeploymentPhase,
    DeviceUpdateReport,
)

NOW = datetime.datetime(2026, 10, 19, tzinfo=datetime.UTC)
HASH = "a" * 64


def deployment() -> Deployment:
    return Deployment(
        uuid.uuid4(),
        uuid.uuid4(),
        "v2.4.0",
        HASH,
        {"pc-1": uuid.uuid4(), "pc-2": uuid.uuid4()},
        "operator",
        NOW,
    )


def report(item: Deployment, device: str, **changes) -> DeviceUpdateReport:
    previous = item.reports.get(device)
    return dataclasses.replace(
        DeviceUpdateReport(
            device,
            item.round_id,
            (previous.sequence + 1) if previous else 1,
            previous.instance_id if previous else uuid.uuid4(),
            NOW,
            False,
            0,
            True,
        ),
        **changes,
    )


def ready(item: Deployment) -> None:
    for device in item.targets:
        item.report(report(item, device))


def test_original_release_is_retained_across_final_round_and_installation():
    """Отчёт сохраняет исходную версию после сброса раунда и запуска нового клиента."""
    item = deployment()
    for device in item.targets:
        item.report(report(item, device, running_release_id="v-old"))
    item.begin_preparation(NOW)
    for device in item.targets:
        item.report(report(item, device, running_release_id="v-new"))
    assert item.old_releases == {"pc-1": "v-old", "pc-2": "v-old"}
    assert item.reports["pc-1"].running_release_id == "v-new"


def authorized() -> Deployment:
    item = deployment()
    ready(item)
    item.begin_preparation(NOW)
    ready(item)
    item.server_ready = True
    item.authorize(NOW)
    return item


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"ready": False}, "not_ready"),
        ({"active_session": True, "ready": False}, "active_session"),
        ({"pending_facts": 1}, "pending_facts"),
        ({"received_at": NOW - datetime.timedelta(seconds=31)}, "unreachable"),
        ({}, "ready"),
    ],
)
def test_device_status_never_labels_unready_or_stale_report_ready(changes, expected):
    """Статус оператора отличает готовность от отсутствия связи и локальных блокеров."""
    item = deployment()
    item.report(report(item, "pc-1", **changes))
    assert item.device_status("pc-1", NOW) == expected
    assert item.device_status("pc-2", NOW) == "unreachable"


def test_obsolete_round_cannot_count_as_success_in_status():
    """Подтверждение старого раунда не увеличивает число обновлённых PC."""
    item = deployment()
    item.reports["pc-1"] = report(
        item, "pc-1", round_id=uuid.uuid4(), stage="installed", installed_sha256=HASH
    )
    item.gui_confirmations["pc-1"] = item.release_id
    assert not item.device_succeeded("pc-1")
    assert item.device_status("pc-1", NOW) == "unreachable"


@pytest.mark.parametrize(
    "changes",
    [
        {"active_session": True},
        {"pending_facts": 1},
        {"ready": False},
        {"received_at": NOW - datetime.timedelta(seconds=31)},
    ],
)
def test_one_unready_pc_blocks_every_installation(changes):
    """Занятый, несверенный или давно ответивший ПК запрещает установку всем."""
    item = deployment()
    item.report(report(item, "pc-1"))
    item.report(report(item, "pc-2", **changes))
    with pytest.raises(ValueError, match="Every PC"):
        item.begin_preparation(NOW)
    assert not item.may_install("pc-1")


def test_offline_pc_and_reused_preliminary_reports_cannot_authorize():
    """Финальный раунд требует новых ответов каждого ПК под барьером."""
    item = deployment()
    old = report(item, "pc-1")
    item.report(old)
    with pytest.raises(ValueError):
        item.begin_preparation(NOW)
    item.report(report(item, "pc-2"))
    item.begin_preparation(NOW)
    item.server_ready = True
    with pytest.raises(ValueError, match="obsolete"):
        item.report(old)
    with pytest.raises(ValueError):
        item.authorize(NOW)


def test_pilot_requires_agent_hash_and_independent_gui_confirmation():
    """Копирования файла недостаточно для допуска остальных ПК без подтверждения GUI."""
    item = authorized()
    assert item.may_install("pc-1")
    assert not item.may_install("pc-2")
    item.report(report(item, "pc-1", stage="installed", installed_sha256=HASH))
    assert not item.may_install("pc-2")
    item.confirm_gui("pc-1", item.release_id)
    assert item.may_install("pc-2")
    with pytest.raises(ValueError):
        item.finish()
    item.report(report(item, "pc-2", stage="installed", installed_sha256=HASH))
    item.confirm_gui("pc-2", item.release_id)
    item.finish()
    assert item.phase is DeploymentPhase.COMPLETED


def test_failed_or_rolled_back_pc_keeps_the_whole_fleet_closed():
    """Откат считается ошибкой доставки и оставляет закрытым весь парк."""
    item = authorized()
    item.report(
        report(item, "pc-1", stage="rolled_back", error_code="startup_timeout", ready=False)
    )
    assert item.phase is DeploymentPhase.FAILED
    assert item.reports["pc-1"].error_code == "startup_timeout"
    assert not any(item.may_install(device) for device in item.targets)
    with pytest.raises(ValueError):
        item.finish()


def test_wrong_hash_identity_and_sequence_reuse_are_rejected():
    """Неверный хеш, чужое устройство и изменение повторного отчёта отклоняются."""
    item = authorized()
    with pytest.raises(ValueError, match="another device"):
        item.report(report(item, "unknown"))
    with pytest.raises(ValueError, match="does not match"):
        item.report(report(item, "pc-1", stage="installed", installed_sha256="b" * 64))
    previous = item.reports["pc-1"]
    item.report(dataclasses.replace(previous, received_at=NOW + datetime.timedelta(seconds=1)))
    with pytest.raises(ValueError, match="different contents"):
        item.report(dataclasses.replace(previous, active_session=True))
    item.report(report(item, "pc-1", stage="ready", instance_id=uuid.uuid4()))
    assert item.phase is DeploymentPhase.FAILED
    assert not item.may_install("pc-1")


def test_retry_keeps_fleet_closed_until_new_round_and_server_check():
    """Повтор после ошибки требует нового раунда и проверки сервера."""
    item = authorized()
    old_round = item.round_id
    item.report(report(item, "pc-1", stage="failed", error_code="copy_failed"))
    item.retry_preparation()
    assert item.round_id != old_round
    assert item.phase is DeploymentPhase.PREPARING
    assert not item.server_ready
    assert not any(item.may_install(device) for device in item.targets)
    with pytest.raises(ValueError):
        item.authorize(NOW)
