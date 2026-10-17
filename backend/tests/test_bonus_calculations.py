import pytest

from gameclub_backend.modules.clients.bonus import BonusAccrual, BonusPolicy, BonusSource


@pytest.mark.parametrize(
    ("limit", "available", "balance", "selected", "bonus", "money"),
    [
        (2000, 10_000, 40_000, True, 10_000, 40_000),
        (10_000, 50_000, 0, True, 50_000, 0),
        (0, 50_000, 50_000, True, 0, 50_000),
        (10_000, 300, 0, True, 300, 49_700),
        (2000, 10_000, -1, True, 0, 50_000),
        (2000, 10_000, 40_000, False, 0, 50_000),
    ],
)
def test_game_payment(limit, available, balance, selected, bonus, money):
    """Бонусная и денежная части соответствуют выбранному лимиту и остатку."""
    result = BonusPolicy(payment_limit_bps=limit).payment(
        50_000, available, balance, use_bonus=selected
    )
    assert (result.bonus_cents, result.money_cents) == (bonus, money)


def test_disabled_program_does_not_spend_or_earn():
    """Выключенная программа не начисляет и не списывает бонусы."""
    policy = BonusPolicy(enabled=False)
    assert policy.payment(1000, 1000, 1000, use_bonus=True).money_cents == 1000
    assert policy.rate(BonusSource.GAME) == policy.rate(BonusSource.PRODUCT) == 0


def test_payment_never_exceeds_fractional_limit():
    """Округление вниз не превышает разрешённую долю бонусной оплаты."""
    policy = BonusPolicy(payment_limit_bps=3333)
    for price in range(1001):
        quote = policy.payment(price, 10_000, 0, use_bonus=True)
        assert quote.bonus_cents * 10_000 <= price * 3333
        assert quote.bonus_cents + quote.money_cents == price


def test_only_money_part_earns_after_session():
    """Начисление только за денежную часть доступно после завершения сессии."""
    policy = BonusPolicy()
    quote = policy.payment(50_000, 10_000, 50_000, use_bonus=True)
    accrual = BonusAccrual(policy.rate(BonusSource.GAME)).record(
        quote.money_cents, quote.money_cents
    )
    assert accrual.pending_bonus_cents == 2000
    assert accrual.release(session_finished=False) == (accrual, 0)
    released, bonus = accrual.release(session_finished=True)
    assert bonus == 2000
    assert released.pending_bonus_cents == 0
    assert released.release(session_finished=True) == (released, 0)


def test_product_outside_session_is_available_immediately():
    """Бонусы за товар вне игры доступны сразу после оплаты."""
    accrual = BonusAccrual(BonusPolicy().rate(BonusSource.PRODUCT)).record(20_000, 20_000)
    released, bonus = accrual.release(session_finished=True)
    assert bonus == 400
    assert released.pending_bonus_cents == 0


def test_minute_fractions_accumulate_without_loss():
    """Доли копейки накапливаются между минутами без потери начисления."""
    accrual = BonusAccrual(500)
    for _ in range(100):
        accrual = accrual.record(1, 1)
    released, bonus = accrual.release(session_finished=True)
    assert bonus == 5
    assert released == BonusAccrual(500, money_cents=100, paid_cents=100, released_bonus_cents=5)


def test_debt_earnings_require_repayment_and_session_end():
    """Начисление за долг доступно по мере оплаты после окончания сессии."""
    accrual = BonusAccrual(500).record(10_000, 4000)
    assert accrual.pending_bonus_cents == 500
    assert accrual.release(session_finished=False)[1] == 0
    released, bonus = accrual.release(session_finished=True)
    assert bonus == 200
    assert released.pending_bonus_cents == 300
    partial, bonus = released.repay(1000).release(session_finished=True)
    assert bonus == 50
    final, bonus = partial.repay(5000).release(session_finished=True)
    assert bonus == 250
    assert final.pending_bonus_cents == 0


@pytest.mark.parametrize("value", [-1, 10_001, True, 0.5, "500"])
@pytest.mark.parametrize("field", ["game_rate_bps", "product_rate_bps", "payment_limit_bps"])
def test_invalid_rates_rejected(field, value):
    """Некорректные типы и значения процентов отклоняются."""
    with pytest.raises(ValueError):
        BonusPolicy(**{field: value})


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_invalid_amounts_rejected(value):
    """Расчёты отклоняют отрицательные и нецелые суммы."""
    with pytest.raises(ValueError):
        BonusPolicy().payment(value, 100, 0, use_bonus=True)
    with pytest.raises(ValueError):
        BonusAccrual(500).record(value, 0)


def test_overpayment_and_invalid_released_amount_rejected():
    """Переплата и завышенная выдача бонусов отклоняются."""
    with pytest.raises(ValueError):
        BonusAccrual(500).record(10, 11)
    with pytest.raises(ValueError):
        BonusAccrual(500, 100, 50).repay(51)
    with pytest.raises(ValueError):
        BonusAccrual(500, 100, 100, 6)


def test_policy_is_immutable_for_existing_session():
    """Изменение общей программы не меняет ранее сохранённые условия."""
    original = BonusPolicy()
    changed = BonusPolicy(game_rate_bps=1000, payment_limit_bps=10_000)
    accrual = BonusAccrual(original.rate(BonusSource.GAME)).record(10_000, 10_000)
    assert accrual.earned_bonus_cents == 500
    assert changed.rate(BonusSource.GAME) == 1000
    assert original.payment_limit_bps == 2000
