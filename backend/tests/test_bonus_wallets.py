import asyncio
import dataclasses
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.infrastructure.database import application_transaction
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_groups.domain import ClientGroup
from gameclub_backend.modules.client_groups.infrastructure.memory import (
    InMemoryClientGroupRepository,
)
from gameclub_backend.modules.clients.application.bonus import BonusCommand, BonusEarningCommand
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.bonus import BonusOperationKind as Kind
from gameclub_backend.modules.clients.bonus import BonusPolicy, BonusSource, BonusWallet
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository

OPERATOR = Principal(
    "operator", SubjectType.OPERATOR, frozenset({"operator"}), frozenset({"clients.manage"})
)


@pytest.fixture(
    params=[
        "memory",
        pytest.param("postgres", marks=[pytest.mark.postgres, pytest.mark.integration]),
    ]
)
async def wallet_context(request):
    engine = None
    if request.param == "postgres":
        dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for PostgreSQL checks")
        engine = create_async_engine(dsn)
        repository = PostgresClientRepository(lambda: engine)
    else:
        repository = InMemoryClientRepository()
    service = ClientService(repository)
    client = await service.create(f"Bonus{uuid.uuid4().hex[:20]}")
    try:
        yield repository, service, client, engine
    finally:
        if engine is not None:
            async with engine.begin() as connection:
                for table in (
                    "client_bonus_receipts",
                    "client_bonus_earnings",
                    "client_bonus_debits",
                    "client_bonus_sessions",
                    "client_bonus_operations",
                    "client_bonus_reservations",
                    "client_bonus_wallets",
                    "balance_operations",
                    "clients",
                ):
                    column = "id" if table == "clients" else "client_id"
                    await connection.execute(
                        text(f"DELETE FROM {table} WHERE {column} = :id"), {"id": client.id}
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM client_bonus_program_changes "
                        "WHERE idempotency_key LIKE :prefix"
                    ),
                    {"prefix": f"{client.id}:%"},
                )
            await engine.dispose()


def command(client_id, kind, amount=0, session=None, key=None):
    return BonusCommand(
        client_id,
        kind,
        amount,
        "operator",
        "Test bonus operation",
        key or uuid.uuid4().hex,
        session,
    )


async def test_reserve_consume_release_and_retry_keep_exact_journal(wallet_context):
    """Резерв, расход и освобождение сохраняют точные суммы и идемпотентность."""
    repository, service, client, _ = wallet_context
    await service.adjust_bonus(client.id, 10_055, OPERATOR, "Opening", "credit")
    session = uuid.uuid4()
    reserve = command(client.id, Kind.RESERVE, session=session)
    original = await service.apply_bonus_operation(reserve)
    assert original.wallet_after == BonusWallet(10_055, 10_055)
    consume = command(client.id, Kind.CONSUME, 305, session)
    spent = await service.apply_bonus_operation(consume)
    assert spent.wallet_after == BonusWallet(9750, 9750)
    release = command(client.id, Kind.RELEASE, session=session)
    result = await service.apply_bonus_operation(release)
    assert result.wallet_after == BonusWallet(9750, 0)
    assert await service.apply_bonus_operation(reserve) == original
    assert await service.apply_bonus_operation(consume) == spent
    assert await service.apply_bonus_operation(release) == result
    assert await service.get_bonus_wallet(client.id) == BonusWallet(9750, 0)
    assert (await service.get(client.id)).balance_bonus == 97
    journal = await service.list_bonus_operations(client.id)
    assert len(journal) == 4
    assert sum(op.total_delta_cents for op in journal) == 9750
    assert sum(op.reserved_delta_cents for op in journal) == 0
    assert all(op.command.actor_id and op.command.reason for op in journal)
    assert await repository.get_bonus_wallet(client.id) == BonusWallet(9750)


async def test_legacy_top_up_preserves_fraction_and_does_not_double_credit(wallet_context):
    """Старое пополнение сохраняет дробный остаток и не начисляет дважды."""
    _, service, client, _ = wallet_context
    await service.adjust_bonus(client.id, 55, OPERATOR, "Fraction", "fraction")
    arguments = dict(
        client_id=client.id,
        amount_cents=1000,
        bonus_amount=2,
        actor_id="operator",
        reason="Legacy top up",
        idempotency_key="legacy",
    )
    _, operation = await service.top_up(**arguments)
    _, repeated = await service.top_up(**arguments)
    assert repeated.id == operation.id
    assert await service.get_bonus_wallet(client.id) == BonusWallet(255)
    assert (await service.get(client.id)).balance_cents == 1000
    assert (await service.get(client.id)).balance_bonus == 2
    with pytest.raises(ApplicationError):
        await service.top_up(**{**arguments, "bonus_amount": 3})
    assert await service.get_bonus_wallet(client.id) == BonusWallet(255)


async def test_reserved_bonus_cannot_be_spent_elsewhere_or_manually_removed(wallet_context):
    """Зарезервированные бонусы нельзя потратить вне сессии или удалить."""
    _, service, client, _ = wallet_context
    await service.adjust_bonus(client.id, 1000, OPERATOR, "Opening", "credit")
    session = uuid.uuid4()
    await service.apply_bonus_operation(command(client.id, Kind.RESERVE, session=session))
    for rejected in (
        command(client.id, Kind.DEBIT, 1),
        command(client.id, Kind.ADJUST, -1),
        command(client.id, Kind.CONSUME, 1, uuid.uuid4()),
    ):
        with pytest.raises(ApplicationError):
            await service.apply_bonus_operation(rejected)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(1000, 1000)
    assert len(await service.list_bonus_operations(client.id)) == 2


async def test_debt_prevents_new_bonus_spend_but_allows_release(wallet_context):
    """Денежный долг запрещает бонусный расход, но не освобождение резерва."""
    repository, service, client, engine = wallet_context
    await service.adjust_bonus(client.id, 1000, OPERATOR, "Opening", "credit")
    session_id = uuid.uuid4()
    await service.apply_bonus_operation(command(client.id, Kind.RESERVE, session=session_id))
    # Seed an existing debt after reservation; group policy is outside this storage test.
    if engine is None:
        repository._items[client.id] = dataclasses.replace(
            await service.get(client.id), balance_cents=-100
        )
    else:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE clients SET balance_cents = -100 WHERE id = :id"), {"id": client.id}
            )
    for kind, amount, session in (
        (Kind.RESERVE, 0, uuid.uuid4()),
        (Kind.DEBIT, 1, None),
        (Kind.CONSUME, 1, uuid.uuid4()),
    ):
        with pytest.raises(ApplicationError, match="monetary debt"):
            await service.apply_bonus_operation(command(client.id, kind, amount, session))
    await service.apply_bonus_operation(command(client.id, Kind.RELEASE, session=session_id))
    assert await service.get_bonus_wallet(client.id) == BonusWallet(1000)


async def test_changed_retry_payload_is_rejected_without_mutation(wallet_context):
    """Повтор с изменённым содержимым отклоняется до изменения остатка."""
    _, service, client, _ = wallet_context
    original = command(client.id, Kind.ADJUST, 1000)
    await service.apply_bonus_operation(original)
    for changed in (
        dataclasses.replace(original, amount_cents=1001),
        dataclasses.replace(original, actor_id="other"),
        dataclasses.replace(original, reason="Other reason"),
        dataclasses.replace(original, kind=Kind.DEBIT),
    ):
        with pytest.raises(ApplicationError, match="Idempotency"):
            await service.apply_bonus_operation(changed)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(1000)


async def test_concurrent_reserve_and_spend_cannot_use_same_balance(wallet_context):
    """Конкурентный резерв и расход не используют один остаток дважды."""
    _, service, client, _ = wallet_context
    await service.adjust_bonus(client.id, 1000, OPERATOR, "Opening", "credit")
    outcomes = await asyncio.gather(
        service.apply_bonus_operation(command(client.id, Kind.RESERVE, session=uuid.uuid4())),
        service.apply_bonus_operation(command(client.id, Kind.DEBIT, 1000)),
        return_exceptions=True,
    )
    assert any(not isinstance(result, Exception) for result in outcomes)
    wallet = await service.get_bonus_wallet(client.id)
    assert wallet in (BonusWallet(1000, 1000), BonusWallet(0))
    journal = await service.list_bonus_operations(client.id)
    assert sum(op.total_delta_cents for op in journal) == wallet.total_cents
    assert sum(op.reserved_delta_cents for op in journal) == wallet.reserved_cents


async def test_concurrent_retries_create_one_operation(wallet_context):
    """Конкурентные повторы создают ровно одну запись и одно начисление."""
    _, service, client, _ = wallet_context
    same = command(client.id, Kind.ADJUST, 1000)
    results = await asyncio.gather(*(service.apply_bonus_operation(same) for _ in range(8)))
    assert len({result.id for result in results}) == 1
    assert await service.get_bonus_wallet(client.id) == BonusWallet(1000)
    assert len(await service.list_bonus_operations(client.id)) == 1


async def test_stale_profile_edit_does_not_overwrite_financial_balances(wallet_context):
    """Редактирование старой копии профиля не перезаписывает баланс."""
    repository, service, client, _ = wallet_context
    await service.adjust_bonus(client.id, 1000, OPERATOR, "Opening", "credit")
    updated = await repository.save(dataclasses.replace(client, nickname="Updated client"))
    assert updated.balance_bonus == 10
    assert await service.get_bonus_wallet(client.id) == BonusWallet(1000)
    assert (await service.get(client.id)).balance_bonus == 10


async def test_bonus_and_legacy_money_join_outer_transaction_and_rollback(wallet_context):
    """Внешний откат отменяет деньги, бонусы и оба журнала одной транзакцией."""
    _, service, client, engine = wallet_context
    if engine is None:
        pytest.skip("Only PostgreSQL supports application transactions")
    with pytest.raises(RuntimeError, match="rollback"):
        async with application_transaction(lambda: engine):
            await service.top_up(client.id, 1000, 2, "Opening", "operator", "outer-topup")
            await service.adjust_bonus(client.id, 55, OPERATOR, "Fraction", "outer-bonus")
            assert await service.get_bonus_wallet(client.id) == BonusWallet(255)
            raise RuntimeError("rollback")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(0)
    assert (await service.get(client.id)).balance_cents == 0
    assert await service.list_bonus_operations(client.id) == []


@pytest.mark.parametrize(
    "kind,amount,session",
    [
        (Kind.ADJUST, 0, None),
        (Kind.DEBIT, -1, None),
        (Kind.ADJUST, True, None),
        (Kind.RESERVE, 100, uuid.uuid4()),
        (Kind.RELEASE, 0, None),
        (Kind.DEBIT, 1, uuid.uuid4()),
    ],
)
def test_invalid_commands(kind, amount, session):
    """Некорректные команды не допускаются к хранилищу."""
    with pytest.raises(ValueError):
        command(uuid.uuid4(), kind, amount, session)


async def test_adjustment_supports_removal_and_rejects_overflow_atomically(wallet_context):
    """Корректировка снимает доступные бонусы и не допускает переполнение или частичный платёж."""
    _, service, client, _ = wallet_context
    await service.adjust_bonus(client.id, 155, OPERATOR, "Opening", "initial")
    await service.adjust_bonus(client.id, -55, OPERATOR, "Correction", "remove")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(100)
    with pytest.raises(ApplicationError):
        await service.top_up(
            client.id, 1000, 92_233_720_368_547_759, "Too large", "operator", "overflow"
        )
    assert await service.get_bonus_wallet(client.id) == BonusWallet(100)
    assert (await service.get(client.id)).balance_cents == 0
    assert len(await service.list_bonus_operations(client.id)) == 2


async def test_concurrent_changed_retry_commits_only_one_payload(wallet_context):
    """Два разных запроса с одним ключом создают только один финансовый эффект."""
    _, service, client, _ = wallet_context
    first = command(client.id, Kind.ADJUST, 100)
    changed = dataclasses.replace(first, amount_cents=200)
    results = await asyncio.gather(
        service.apply_bonus_operation(first),
        service.apply_bonus_operation(changed),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ApplicationError) for result in results) == 1
    assert (await service.get_bonus_wallet(client.id)).total_cents in (100, 200)
    assert len(await service.list_bonus_operations(client.id)) == 1


async def test_exact_wallet_and_legacy_projection_support_bigint_boundary(wallet_context):
    """Точный остаток и старая целая проекция сохраняются без 32-битного переполнения."""
    _, service, client, _ = wallet_context
    maximum = 9_223_372_036_854_775_807
    await service.adjust_bonus(client.id, maximum, OPERATOR, "Boundary", "max")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(maximum)
    assert (await service.get(client.id)).balance_bonus == maximum // 100
    with pytest.raises(ApplicationError):
        await service.adjust_bonus(client.id, 1, OPERATOR, "Overflow", "overflow")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(maximum)
    assert len(await service.list_bonus_operations(client.id)) == 1


@pytest.mark.parametrize(
    "subject,permissions",
    [
        (SubjectType.OPERATOR, frozenset()),
        (SubjectType.CLIENT, frozenset({"clients.manage"})),
    ],
)
async def test_adjustment_use_case_checks_operator_and_permission(
    wallet_context, subject, permissions
):
    """Сценарий корректировки сам проверяет тип субъекта и права без HTTP-обработчика."""
    _, service, client, _ = wallet_context
    principal = dataclasses.replace(OPERATOR, subject_type=subject, permissions=permissions)
    with pytest.raises(ApplicationError, match="not permitted"):
        await service.adjust_bonus(client.id, 100, principal, "Test", "denied")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(0)
    assert await service.list_bonus_operations(client.id) == []


def earning(client_id, source, policy, *, operation=None, session=None, external=0, key=None):
    return BonusEarningCommand(
        uuid.uuid4(),
        client_id,
        key or f"test-source:{uuid.uuid4()}",
        source,
        policy,
        (operation.id,) if operation else (),
        external,
        session,
    )


async def test_confirmed_game_earning_waits_for_session_and_is_idempotent(wallet_context):
    """Подтверждённая покупка начисляет только один раз после окончания сессии."""
    _, service, client, _ = wallet_context
    session = uuid.uuid4()
    policy = await service.begin_bonus_session(client.id, session)
    await service.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    _, debit = await service.debit(client.id, 10_000, "Game purchase", "operator", "purchase")
    receipt = earning(client.id, BonusSource.GAME, policy, operation=debit, session=session)
    await service.confirm_bonus_earning(receipt)
    assert await service.get_pending_bonus_cents(client.id) == 500
    assert await service.get_bonus_wallet(client.id) == BonusWallet(0)
    await service.finish_bonus_session(client.id, session)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(500)
    assert await service.get_pending_bonus_cents(client.id) == 0
    await service.confirm_bonus_earning(receipt)
    await service.finish_bonus_session(client.id, session)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(500)


async def test_product_earning_is_immediate_outside_game_and_pending_during_game(wallet_context):
    """Бонусы за товар сразу доступны вне игры и ожидают окончания активной сессии."""
    _, service, client, _ = wallet_context
    policy = await service.get_bonus_policy()
    await service.confirm_bonus_earning(
        earning(
            client.id,
            BonusSource.PRODUCT,
            policy,
            external=10_000,
        )
    )
    assert await service.get_bonus_wallet(client.id) == BonusWallet(200)
    session = uuid.uuid4()
    await service.begin_bonus_session(client.id, session)
    await service.confirm_bonus_earning(
        earning(
            client.id,
            BonusSource.PRODUCT,
            policy,
            external=5000,
            session=session,
        )
    )
    assert await service.get_bonus_wallet(client.id) == BonusWallet(200)
    assert await service.get_pending_bonus_cents(client.id) == 100
    await service.finish_bonus_session(client.id, session)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(300)


async def test_fifo_repayment_includes_older_non_earning_expenses(wallet_context):
    """Погашение сначала закрывает старые расходы без бонусов, затем оплачивает начисление."""
    repository, _, client, _ = wallet_context
    groups = InMemoryClientGroupRepository()
    await groups.save(ClientGroup("debt", "Debt", True, 100_000))
    service = ClientService(repository, groups=groups)
    await service.update(client.id, client.nickname, client_group_id="debt")
    await service.top_up(client.id, 1000, 0, "Deposit", "operator", "deposit")
    await service.debit(client.id, 2000, "Older expense", "operator", "older", True)
    _, debit = await service.debit(client.id, 1000, "Game", "operator", "game", True)
    receipt = earning(
        client.id, BonusSource.GAME, await service.get_bonus_policy(), operation=debit
    )
    await service.confirm_bonus_earning(receipt)
    assert await service.get_pending_bonus_cents(client.id) == 50
    await service.top_up(client.id, 1000, 0, "Old debt", "operator", "repay-old")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(0)
    await service.top_up(client.id, 400, 0, "Part of game", "operator", "repay-part")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(20)
    assert await service.get_pending_bonus_cents(client.id) == 30
    await service.top_up(client.id, 600, 0, "Rest of game", "operator", "repay-rest")
    await service.top_up(client.id, 600, 0, "Rest of game", "operator", "repay-rest")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(50)
    assert await service.get_pending_bonus_cents(client.id) == 0
    assert (await service.get(client.id)).balance_cents == 0


async def test_repayment_before_source_confirmation_is_not_lost(wallet_context):
    """Оплата долга до подтверждения покупки учитывается при последующем начислении."""
    repository, _, client, _ = wallet_context
    groups = InMemoryClientGroupRepository()
    await groups.save(ClientGroup("debt", "Debt", True, 100_000))
    service = ClientService(repository, groups=groups)
    await service.update(client.id, client.nickname, client_group_id="debt")
    _, debit = await service.debit(client.id, 1000, "Game", "operator", "game", True)
    await service.top_up(client.id, 1000, 0, "Repayment", "operator", "repayment")
    assert await service.get_bonus_wallet(client.id) == BonusWallet(0)
    await service.confirm_bonus_earning(
        earning(
            client.id,
            BonusSource.GAME,
            await service.get_bonus_policy(),
            operation=debit,
        )
    )
    assert await service.get_bonus_wallet(client.id) == BonusWallet(50)


async def test_reused_debit_and_changed_receipt_are_rejected(wallet_context):
    """Один денежный факт не даёт начисление повторно под новым идентификатором."""
    _, service, client, _ = wallet_context
    await service.top_up(client.id, 1000, 0, "Deposit", "operator", "deposit")
    _, debit = await service.debit(client.id, 1000, "Game", "operator", "game")
    receipt = earning(
        client.id, BonusSource.GAME, await service.get_bonus_policy(), operation=debit
    )
    await service.confirm_bonus_earning(receipt)
    for changed in (
        dataclasses.replace(receipt, receipt_id=uuid.uuid4()),
        dataclasses.replace(receipt, external_paid_cents=1000),
    ):
        with pytest.raises(ApplicationError):
            await service.confirm_bonus_earning(changed)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(50)


async def test_cumulative_minute_receipts_keep_fractional_bonus(wallet_context):
    """Малые подтверждённые списания накапливают бонусы по одному источнику сессии."""
    _, service, client, _ = wallet_context
    session = uuid.uuid4()
    policy = await service.begin_bonus_session(client.id, session)
    await service.top_up(client.id, 100, 0, "Deposit", "operator", "deposit")
    source_key = f"minutes:{session}"
    for minute in range(100):
        _, debit = await service.debit(client.id, 1, "Minute", "operator", f"minute:{minute}")
        await service.confirm_bonus_earning(
            earning(
                client.id,
                BonusSource.GAME,
                policy,
                operation=debit,
                session=session,
                key=source_key,
            )
        )
    assert await service.get_pending_bonus_cents(client.id) == 5
    await service.finish_bonus_session(client.id, session)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(5)


async def test_settings_change_does_not_rewrite_session_policy_or_retry(wallet_context):
    """Новые настройки не меняют снимок сессии, а повтор сохранения не откатывает новые условия."""
    _, service, client, _ = wallet_context
    admin = dataclasses.replace(OPERATOR, permissions=frozenset({"settings.manage"}))
    initial = await service.get_bonus_policy()
    session = uuid.uuid4()
    frozen = await service.begin_bonus_session(client.id, session)
    changed = BonusPolicy(game_rate_bps=1000, payment_limit_bps=10000)
    try:
        await service.update_bonus_policy(changed, admin, f"{client.id}:changed")
        assert await service.get_bonus_policy(client.id, session) == frozen
        assert await service.get_bonus_policy() == changed
        disabled = dataclasses.replace(changed, enabled=False)
        await service.update_bonus_policy(disabled, admin, f"{client.id}:disabled")
        assert await service.update_bonus_policy(changed, admin, f"{client.id}:changed") == changed
        assert await service.get_bonus_policy() == disabled
        with pytest.raises(ApplicationError):
            await service.update_bonus_policy(disabled, admin, f"{client.id}:changed")
    finally:
        await service.update_bonus_policy(initial, admin, f"{client.id}:restore")


async def test_unknown_old_session_does_not_adopt_current_bonus_program(wallet_context):
    """Старая сессия без снимка не принимает новые ставки ни при чтении, ни при повторном старте."""
    _, service, client, _ = wallet_context
    old_session = uuid.uuid4()
    old = await service.get_bonus_policy(client.id, old_session)
    assert not old.enabled
    assert await service.begin_bonus_session(client.id, old_session) == old
    fresh = await service.begin_bonus_session(client.id, uuid.uuid4())
    assert fresh == await service.get_bonus_policy()


async def test_concurrent_confirmed_receipts_issue_one_credit(wallet_context):
    """Повторная конкурентная доставка подтверждения выдаёт бонусы один раз."""
    _, service, client, _ = wallet_context
    receipt = earning(
        client.id, BonusSource.PRODUCT, await service.get_bonus_policy(), external=1000
    )
    await asyncio.gather(*(service.confirm_bonus_earning(receipt) for _ in range(8)))
    assert await service.get_bonus_wallet(client.id) == BonusWallet(20)
    assert len(await service.list_bonus_operations(client.id)) == 1


@pytest.fixture
async def bonus_commerce(wallet_context):
    import datetime

    from gameclub_backend.modules.catalog.application.service import CatalogService
    from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
    from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
    from gameclub_backend.modules.entitlements.application.service import EntitlementService
    from gameclub_backend.modules.entitlements.infrastructure.memory import (
        InMemoryEntitlementRepository,
    )
    from gameclub_backend.modules.entitlements.infrastructure.postgres import (
        PostgresEntitlementRepository,
    )
    from gameclub_backend.modules.sales.application.service import ProductSaleService
    from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
    from gameclub_backend.modules.sales.infrastructure.postgres import PostgresProductSaleRepository
    from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository

    _, clients, client, engine = wallet_context
    if engine is None:
        catalog_repository = InMemoryCatalogRepository()
        sale_repository = InMemoryProductSaleRepository(catalog_repository)
        entitlement_repository = InMemoryEntitlementRepository()
        transaction = None
    else:
        catalog_repository = PostgresCatalogRepository(lambda: engine)
        sale_repository = PostgresProductSaleRepository(lambda: engine)
        entitlement_repository = PostgresEntitlementRepository(lambda: engine)

        def transaction():
            return application_transaction(lambda: engine)

    catalog = CatalogService(catalog_repository)
    product = await catalog.create_product("Bonus product", "test", 1000, stock_quantity=10)
    tariff = await catalog.create_tariff(
        "Bonus game",
        None,
        60,
        10_000,
        datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        None,
    )
    active_sessions = InMemorySessionRepository()
    sales = ProductSaleService(
        sale_repository,
        catalog,
        clients,
        bonuses=clients,
        active_sessions=active_sessions,
        transaction=transaction,
    )
    entitlements = EntitlementService(
        entitlement_repository,
        catalog,
        clients,
        bonuses=clients,
        active_sessions=active_sessions,
        transaction=transaction,
    )
    try:
        yield (
            clients,
            client,
            sales,
            entitlements,
            product,
            tariff,
            engine,
            active_sessions,
            catalog,
        )
    finally:
        if engine is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM product_sales WHERE product_id = :id"), {"id": product.id}
                )
                await connection.execute(
                    text("DELETE FROM client_entitlements WHERE client_id = :id"), {"id": client.id}
                )
                await connection.execute(
                    text("DELETE FROM discount_rules WHERE category = :category"),
                    {"category": f"bonus-vip-{client.id}"},
                )
                await connection.execute(
                    text("DELETE FROM products WHERE id = :id"), {"id": product.id}
                )
                await connection.execute(
                    text("DELETE FROM tariffs WHERE id = :id"), {"id": tariff.id}
                )


async def test_real_purchase_services_earn_once_without_package_consumption_bonus(bonus_commerce):
    """Реальные продажи товара и пакета начисляют один раз с денежной оплаты."""
    clients, client, sales, entitlements, product, tariff, _, _, _ = bonus_commerce
    await clients.top_up(client.id, 20_000, 0, "Deposit", "operator", "deposit")
    sale = await sales.sell(product.id, 1, client.id, "balance", None, "operator", "sale")
    assert sale.bonus_rate_bps == 200
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(20)
    package = await entitlements.purchase(client.id, tariff.id, "operator", "package")
    assert package.bonus_rate_bps == 500
    assert package.purchase_actor_id == "operator"
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(520)
    await sales.sell(product.id, 1, client.id, "balance", None, "operator", "sale")
    await entitlements.purchase(client.id, tariff.id, "operator", "package")
    await entitlements.activate(package.id, client.id)
    await entitlements.consume(package.id, client.id, 10)
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(520)
    assert (await clients.get(client.id)).balance_cents == 9000


async def test_external_product_payment_earns_only_for_registered_client(bonus_commerce):
    """Подтверждённый перевод даёт бонусы зарегистрированному покупателю, но не гостю."""
    clients, client, sales, _, product, _, _, _, _ = bonus_commerce
    await sales.sell(product.id, 1, client.id, "transfer", None, "operator", "registered")
    await sales.sell(product.id, 1, None, "transfer", None, "operator", "guest")
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(20)
    assert len(await clients.list_bonus_operations(client.id)) == 1


async def test_entitlement_recovery_preserves_original_actor_and_earns_after_success(
    bonus_commerce,
):
    """Повтор settlement использует исходного автора и начисляет после успешного подтверждения."""
    clients, client, _, entitlements, _, tariff, engine, _, _ = bonus_commerce
    if engine is None:
        pytest.skip("Atomic cross-module settlement is verified with PostgreSQL")
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")

    class FailingBonus:
        async def get_bonus_policy(self, client_id=None, session_id=None):
            return await clients.get_bonus_policy(client_id, session_id)

        async def confirm_bonus_earning(self, command):
            await clients.confirm_bonus_earning(command)
            raise RuntimeError("bonus storage unavailable")

    entitlements._bonuses = FailingBonus()
    with pytest.raises(RuntimeError, match="bonus storage unavailable"):
        await entitlements.purchase(client.id, tariff.id, "original-operator", "package")
    pending = (await entitlements.list_for_client(client.id))[0]
    assert pending.settlement_status.value == "needs_review"
    assert (await clients.get(client.id)).balance_cents == 0
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(0)
    entitlements._bonuses = clients
    settled = await entitlements.retry_settlement_review(pending.id, "supervisor")
    assert settled.settlement_status.value == "settled"
    assert settled.purchase_actor_id == "original-operator"
    assert (await clients.get(client.id)).balance_cents == 0
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(500)


async def test_v2_owned_writer_earns_after_confirmed_stop_and_releases_reserve(wallet_context):
    """V2 writer начисляет по снимку сессии и освобождает резерв после подтверждённого stop."""
    import datetime

    from gameclub_backend.modules.clients.domain import BalanceOperation, BalanceOperationType
    from gameclub_backend.modules.clients.infrastructure.balance_transaction import (
        PostgresClientBalanceTransactionWriter,
    )

    _, service, client, engine = wallet_context
    if engine is None:
        pytest.skip("Cross-module V2 writer requires PostgreSQL")
    session_id = uuid.uuid4()
    await service.begin_bonus_session(client.id, session_id)
    await service.top_up(client.id, 1000, 2, "Deposit", "operator", "deposit")
    await service.apply_bonus_operation(command(client.id, Kind.RESERVE, session=session_id))
    operation = BalanceOperation(
        uuid.uuid4(),
        client.id,
        -1000,
        0,
        "Minute",
        "device",
        "v2-minute",
        datetime.datetime.now(datetime.UTC),
        BalanceOperationType.DEBIT,
    )
    writer = PostgresClientBalanceTransactionWriter()
    receipt_id = uuid.uuid4()
    async with application_transaction(lambda: engine) as transaction:
        assert await writer.apply(transaction, operation) is not None
        await writer.confirm_minute(
            transaction,
            client.id,
            session_id,
            operation.id,
            receipt_id,
            "device",
            operation.created_at,
        )
    assert await service.get_bonus_wallet(client.id) == BonusWallet(200, 200)
    assert await service.get_pending_bonus_cents(client.id) == 50
    async with application_transaction(lambda: engine) as transaction:
        await writer.finish_session(transaction, client.id, session_id, operation.created_at)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(250)
    assert await service.get_pending_bonus_cents(client.id) == 0
    async with application_transaction(lambda: engine) as transaction:
        await writer.apply(transaction, operation)
        await writer.confirm_minute(
            transaction,
            client.id,
            session_id,
            operation.id,
            receipt_id,
            "device",
            operation.created_at,
        )
        await writer.finish_session(transaction, client.id, session_id, operation.created_at)
    assert await service.get_bonus_wallet(client.id) == BonusWallet(250)


async def test_settings_use_case_requires_settings_permission(wallet_context):
    """Изменение бонусной программы требует settings.manage в самом сценарии приложения."""
    _, service, _, _ = wallet_context
    with pytest.raises(ApplicationError, match="not permitted"):
        await service.update_bonus_policy(BonusPolicy(enabled=False), OPERATOR, "denied")


async def test_purchase_earnings_during_game_wait_for_its_end(bonus_commerce):
    """Покупки товара и пакета во время игры ожидают завершения той же сессии."""
    import datetime

    from gameclub_backend.modules.sessions.domain import Session, SessionStatus

    clients, client, sales, entitlements, product, tariff, _, active_sessions, _ = bonus_commerce
    now = datetime.datetime.now(datetime.UTC)
    session = Session(
        id=uuid.uuid4(),
        workstation_id=uuid.uuid4(),
        client_id=client.id,
        guest_name=None,
        status=SessionStatus.ACTIVE,
        started_at=now,
        ended_at=None,
        source="local_ledger",
        created_by="operator",
        created_at=now,
    )
    await active_sessions.save(session)
    await clients.begin_bonus_session(client.id, session.id)
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    await sales.sell(product.id, 1, client.id, "transfer", None, "operator", "product")
    await entitlements.purchase(client.id, tariff.id, "operator", "package")
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(0)
    assert await clients.get_pending_bonus_cents(client.id) == 520
    await clients.finish_bonus_session(client.id, session.id)
    assert await clients.get_pending_bonus_cents(client.id) == 0
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(520)


async def test_concurrent_repayment_and_confirmation_do_not_lose_earning(wallet_context):
    """Гонка пополнения и подтверждения покупки не теряет и не удваивает начисление."""
    repository, _, client, _ = wallet_context
    groups = InMemoryClientGroupRepository()
    await groups.save(ClientGroup("debt", "Debt", True, 100_000))
    service = ClientService(repository, groups=groups)
    await service.update(client.id, client.nickname, client_group_id="debt")
    _, debit = await service.debit(client.id, 1000, "Game", "operator", "game", True)
    receipt = earning(
        client.id,
        BonusSource.GAME,
        await service.get_bonus_policy(),
        operation=debit,
    )
    await asyncio.gather(
        service.confirm_bonus_earning(receipt),
        service.top_up(client.id, 1000, 0, "Repayment", "operator", "repayment"),
    )
    assert await service.get_bonus_wallet(client.id) == BonusWallet(50)
    assert await service.get_pending_bonus_cents(client.id) == 0
    assert (await service.get(client.id)).balance_cents == 0


def confirmed_quote(quote):
    return {
        "use_bonus": True,
        "principal": OPERATOR,
        "expected_price_cents": quote.price_cents,
        "expected_bonus_cents": quote.bonus_cents,
        "expected_money_cents": quote.money_cents,
        "expected_earned_bonus_cents": quote.earned_bonus_cents,
    }


@pytest.mark.parametrize("limit", [2000, 10000])
async def test_package_payment_uses_confirmed_bonus_split_and_earns_only_on_money(
    bonus_commerce, limit
):
    """Пакет оплачивается в пределах 20/100%, начисление идёт только с денежной части."""
    clients, client, _, entitlements, _, tariff, _, _, _ = bonus_commerce
    admin = dataclasses.replace(OPERATOR, permissions=frozenset({"settings.manage"}))
    original = await clients.get_bonus_policy()
    try:
        await clients.update_bonus_policy(
            dataclasses.replace(original, payment_limit_bps=limit), admin, f"{client.id}:limit"
        )
        await clients.adjust_bonus(client.id, 10_000, OPERATOR, "Opening", "opening")
        money = 10_000 if limit == 2000 else 0
        if money:
            await clients.top_up(client.id, money, 0, "Deposit", "operator", "deposit")
        quote = await entitlements.quote_purchase(client.id, tariff.id, True)
        assert quote.can_pay
        assert quote.bonus_cents == (2000 if limit == 2000 else 10_000)
        package = await entitlements.purchase(
            client.id, tariff.id, "operator", "package", **confirmed_quote(quote)
        )
        assert package.bonus_requested
        assert package.bonus_amount_cents == quote.bonus_cents
        assert sum(p.amount_cents for p in package.payment_parts) == quote.money_cents
        assert (await clients.get(client.id)).balance_cents == money - quote.money_cents
        assert (await clients.get_bonus_wallet(client.id)).total_cents == (
            10_000 - quote.bonus_cents + quote.earned_bonus_cents
        )
        repeated = await entitlements.purchase(
            client.id, tariff.id, "operator", "package", **confirmed_quote(quote)
        )
        assert repeated.id == package.id
        assert len(await entitlements.list_for_client(client.id)) == 1
    finally:
        await clients.update_bonus_policy(original, admin, f"{client.id}:restore")


async def test_package_discount_is_applied_before_bonus_split(bonus_commerce):
    """Скидка категории применяется до лимита бонусной оплаты и базы начисления."""
    import datetime

    clients, client, _, entitlements, _, tariff, _, _, catalog = bonus_commerce
    category = f"bonus-vip-{client.id}"
    await clients.update(client.id, client.nickname, discount_category=category)
    await catalog.create_discount_rule(
        category, 5000, 1, datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC), None
    )
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    await clients.adjust_bonus(client.id, 1000, OPERATOR, "Opening", "opening")
    quote = await entitlements.quote_purchase(client.id, tariff.id, True)
    assert (quote.price_cents, quote.bonus_cents, quote.money_cents) == (5000, 1000, 4000)
    assert quote.earned_bonus_cents == 200
    package = await entitlements.purchase(
        client.id, tariff.id, "operator", "discount-package", **confirmed_quote(quote)
    )
    assert package.price_cents == 5000
    assert (await clients.get(client.id)).balance_cents == 6000
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(200)


async def test_stale_bonus_quote_never_silently_increases_money_payment(bonus_commerce):
    """Изменившийся бонусный остаток требует нового подтверждения, не увеличивая денежный платёж."""
    clients, client, _, entitlements, _, tariff, _, _, _ = bonus_commerce
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    await clients.adjust_bonus(client.id, 2000, OPERATOR, "Opening", "opening")
    quote = await entitlements.quote_purchase(client.id, tariff.id, True)
    await clients.adjust_bonus(client.id, -2000, OPERATOR, "Correction", "correction")
    with pytest.raises(ApplicationError, match="изменился"):
        await entitlements.purchase(
            client.id, tariff.id, "operator", "stale", **confirmed_quote(quote)
        )
    assert (await clients.get(client.id)).balance_cents == 10_000
    assert await entitlements.list_for_client(client.id) == []


async def test_concurrent_bonus_package_retries_return_one_purchase(bonus_commerce):
    """Конкурентный повтор подтверждённой покупки списывает бонусы и деньги один раз."""
    clients, client, _, entitlements, _, tariff, _, _, _ = bonus_commerce
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    await clients.adjust_bonus(client.id, 2000, OPERATOR, "Opening", "opening")
    quote = await entitlements.quote_purchase(client.id, tariff.id, True)
    results = await asyncio.gather(
        *(
            entitlements.purchase(
                client.id, tariff.id, "operator", "concurrent", **confirmed_quote(quote)
            )
            for _ in range(4)
        )
    )
    assert len({item.id for item in results}) == 1
    assert (await clients.get(client.id)).balance_cents == 2000
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(400)


async def test_two_different_bonus_purchases_cannot_spend_the_same_funds(bonus_commerce):
    """Две конкурентные покупки не могут повторно использовать один бонусный остаток."""
    clients, client, _, entitlements, _, tariff, _, _, _ = bonus_commerce
    admin = dataclasses.replace(OPERATOR, permissions=frozenset({"settings.manage"}))
    original = await clients.get_bonus_policy()
    try:
        await clients.update_bonus_policy(
            dataclasses.replace(original, payment_limit_bps=10000), admin, f"{client.id}:limit"
        )
        await clients.adjust_bonus(client.id, 10_000, OPERATOR, "Opening", "opening")
        quote = await entitlements.quote_purchase(client.id, tariff.id, True)
        results = await asyncio.gather(
            *(
                entitlements.purchase(
                    client.id, tariff.id, "operator", key, **confirmed_quote(quote)
                )
                for key in ("purchase-one", "purchase-two")
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(item, ApplicationError) for item in results) == 1
        assert len(await entitlements.list_for_client(client.id)) == 1
        assert await clients.get_bonus_wallet(client.id) == BonusWallet(0)
        assert (await clients.get(client.id)).balance_cents == 0
    finally:
        await clients.update_bonus_policy(original, admin, f"{client.id}:restore")


async def test_bonus_purchase_rollback_restores_money_bonus_and_entitlement(bonus_commerce):
    """Сбой после начисления откатывает обе части бонусной покупки и создание пакета."""
    clients, client, _, entitlements, _, tariff, engine, _, _ = bonus_commerce
    if engine is None:
        pytest.skip("Cross-module financial rollback requires PostgreSQL")
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    await clients.adjust_bonus(client.id, 2000, OPERATOR, "Opening", "opening")
    quote = await entitlements.quote_purchase(client.id, tariff.id, True)

    class FailingBonus:
        async def get_bonus_policy(self, client_id=None, session_id=None):
            return await clients.get_bonus_policy(client_id, session_id)

        async def quote_bonus_game(self, client_id, price, use_bonus, session_id=None):
            return await clients.quote_bonus_game(client_id, price, use_bonus, session_id)

        async def apply_bonus_operation(self, command):
            return await clients.apply_bonus_operation(command)

        async def confirm_bonus_earning(self, command):
            await clients.confirm_bonus_earning(command)
            raise RuntimeError("fail after earning")

    entitlements._bonuses = FailingBonus()
    with pytest.raises(RuntimeError, match="fail after earning"):
        await entitlements.purchase(
            client.id, tariff.id, "operator", "rollback", **confirmed_quote(quote)
        )
    assert (await clients.get(client.id)).balance_cents == 10_000
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(2000)
    assert await entitlements.list_for_client(client.id) == []
    assert len(await clients.list_bonus_operations(client.id)) == 1
    assert len(await clients.list_operations(client.id)) == 1


async def test_bonus_purchase_use_case_rejects_unscoped_actor(bonus_commerce):
    """Сам сценарий оплаты бонусами отклоняет запрос без прав или с подменой автора."""
    clients, client, _, entitlements, _, tariff, _, _, _ = bonus_commerce
    await clients.top_up(client.id, 10_000, 0, "Deposit", "operator", "deposit")
    await clients.adjust_bonus(client.id, 2000, OPERATOR, "Opening", "opening")
    quote = await entitlements.quote_purchase(client.id, tariff.id, True)
    for principal in (
        None,
        dataclasses.replace(OPERATOR, permissions=frozenset()),
        dataclasses.replace(
            OPERATOR, subject_type=SubjectType.CLIENT, subject_id=str(uuid.uuid4())
        ),
    ):
        arguments = {**confirmed_quote(quote), "principal": principal}
        with pytest.raises(ApplicationError, match="not authorized"):
            await entitlements.purchase(client.id, tariff.id, "operator", "denied", **arguments)
    assert await clients.get_bonus_wallet(client.id) == BonusWallet(2000)
    assert await entitlements.list_for_client(client.id) == []
