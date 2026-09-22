from __future__ import annotations

import dataclasses
import datetime

from gameclub_backend.modules.analytics.application.ports import FinanceAnalyticsRepository
from gameclub_backend.modules.analytics.finance import (
    FINANCE_METRIC_INFO,
    AnalyticsDataState,
    ComparisonKind,
    FinanceFactsSnapshot,
    FinanceFilters,
    FinanceFlow,
    FinanceReport,
    FinanceTotals,
    MetricComparison,
    MetricResult,
    PeriodComparison,
    aggregate_finance_facts,
    aggregate_payment_methods,
    build_period_comparison,
    compare_metric,
)


class FinanceAnalyticsService:
    def __init__(self, repository: FinanceAnalyticsRepository) -> None:
        self._repository = repository

    async def finance(
        self,
        filters: FinanceFilters,
        now: datetime.datetime | None = None,
    ) -> FinanceReport:
        snapshot = await self._repository.snapshot()
        observed_at = now or datetime.datetime.now(datetime.UTC)
        comparison_period = build_period_comparison(filters, observed_at)
        previous_filters = dataclasses.replace(
            filters,
            start_at=comparison_period.previous_start_at,
            end_at=comparison_period.previous_end_at,
        )
        current_totals = self._aggregate(snapshot, filters)
        previous_totals = self._aggregate(snapshot, previous_filters)
        sources = self._source_states(snapshot)
        metrics = self._metrics(
            snapshot,
            current_totals,
            previous_totals,
            comparison_period,
        )
        return FinanceReport(
            period=filters,
            comparison_period=comparison_period,
            flow=FinanceFlow(
                payment_received_cents=(
                    current_totals.payment_received_cents
                    if snapshot.financial_facts is not None and current_totals is not None
                    else None
                ),
                direct_payment_cents=(
                    current_totals.payment_received_cents
                    if snapshot.financial_facts is not None and current_totals is not None
                    else None
                ),
                deposit_top_up_revenue_cents=(
                    current_totals.deposit_top_up_revenue_cents
                    if snapshot.wallet_facts is not None and current_totals is not None
                    else None
                ),
                wallet_debit_cents=(
                    current_totals.wallet_debit_cents
                    if snapshot.wallet_facts is not None and current_totals is not None
                    else None
                ),
                recognized_revenue_cents=(
                    current_totals.recognized_revenue_cents if current_totals is not None else None
                ),
                refunds_cents=(
                    current_totals.refunds_cents
                    if snapshot.financial_facts is not None
                    and snapshot.refunds_available
                    and current_totals is not None
                    else None
                ),
                adjustments_cents=None,
                net_cash_received_cents=(
                    current_totals.net_cash_received_cents if current_totals is not None else None
                ),
            ),
            metrics=metrics,
            sources=sources,
            payment_methods=aggregate_payment_methods(
                snapshot.financial_facts,
                snapshot.wallet_facts,
                filters,
            ),
        )

    @staticmethod
    def _aggregate(
        snapshot: FinanceFactsSnapshot,
        filters: FinanceFilters,
    ) -> FinanceTotals | None:
        if snapshot.financial_facts is None and snapshot.wallet_facts is None:
            return None
        return aggregate_finance_facts(snapshot.financial_facts, snapshot.wallet_facts, filters)

    @staticmethod
    def _source_states(snapshot: FinanceFactsSnapshot) -> dict[str, AnalyticsDataState]:
        return {
            "financial_facts": (
                AnalyticsDataState.AVAILABLE
                if snapshot.financial_facts is not None
                else AnalyticsDataState.NOT_AVAILABLE
            ),
            "wallet_facts": (
                AnalyticsDataState.AVAILABLE
                if snapshot.wallet_facts is not None
                else AnalyticsDataState.NOT_AVAILABLE
            ),
            "refunds": (
                AnalyticsDataState.AVAILABLE
                if snapshot.refunds_available
                else AnalyticsDataState.NOT_AVAILABLE
            ),
            "history": (
                AnalyticsDataState.AVAILABLE
                if snapshot.history_available
                else AnalyticsDataState.NOT_AVAILABLE
            ),
        }

    @staticmethod
    def _period_state(
        state: AnalyticsDataState,
        comparison_period: PeriodComparison,
    ) -> AnalyticsDataState:
        if (
            state is AnalyticsDataState.AVAILABLE
            and comparison_period.current_state is AnalyticsDataState.PARTIAL
        ):
            return AnalyticsDataState.PARTIAL
        return state

    @classmethod
    def _metrics(
        cls,
        snapshot: FinanceFactsSnapshot,
        current_totals,
        previous_totals,
        comparison_period: PeriodComparison,
    ) -> dict[str, MetricResult]:
        financial_available = snapshot.financial_facts is not None
        wallet_available = snapshot.wallet_facts is not None
        recognized_state = (
            AnalyticsDataState.NOT_AVAILABLE
            if not financial_available and not wallet_available
            else AnalyticsDataState.AVAILABLE
            if financial_available and wallet_available
            else AnalyticsDataState.PARTIAL
        )
        values: dict[str, tuple[int | None, int | None, AnalyticsDataState]] = {
            "cash_received_cents": (
                current_totals.payment_received_cents if financial_available else None,
                previous_totals.payment_received_cents if financial_available else None,
                AnalyticsDataState.AVAILABLE
                if financial_available
                else AnalyticsDataState.NOT_AVAILABLE,
            ),
            "refunds_cents": (
                current_totals.refunds_cents
                if financial_available and snapshot.refunds_available
                else None,
                previous_totals.refunds_cents
                if financial_available and snapshot.refunds_available
                else None,
                AnalyticsDataState.AVAILABLE
                if financial_available and snapshot.refunds_available
                else AnalyticsDataState.NOT_AVAILABLE,
            ),
            "deposit_top_up_revenue_cents": (
                current_totals.deposit_top_up_revenue_cents if wallet_available else None,
                previous_totals.deposit_top_up_revenue_cents if wallet_available else None,
                AnalyticsDataState.AVAILABLE
                if wallet_available
                else AnalyticsDataState.NOT_AVAILABLE,
            ),
            "wallet_debit_cents": (
                current_totals.wallet_debit_cents if wallet_available else None,
                previous_totals.wallet_debit_cents if wallet_available else None,
                AnalyticsDataState.AVAILABLE
                if wallet_available
                else AnalyticsDataState.NOT_AVAILABLE,
            ),
            "recognized_revenue_cents": (
                current_totals.recognized_revenue_cents if current_totals is not None else None,
                previous_totals.recognized_revenue_cents if previous_totals is not None else None,
                recognized_state,
            ),
        }
        if (
            current_totals is not None
            and financial_available
            and wallet_available
            and snapshot.refunds_available
        ):
            values["recognized_revenue_cents"] = (
                current_totals.recognized_revenue_cents,
                previous_totals.recognized_revenue_cents if previous_totals is not None else None,
                AnalyticsDataState.AVAILABLE,
            )

        metrics: dict[str, MetricResult] = {}
        for key, (current, previous, state) in values.items():
            state = cls._period_state(state, comparison_period)
            comparison: MetricComparison | None = None
            if current is not None or previous is not None:
                comparison = compare_metric(current, previous, kind=ComparisonKind.ABSOLUTE)
            metrics[key] = MetricResult(
                key=key,
                value_cents=current,
                state=state,
                metric_info=FINANCE_METRIC_INFO[key],
                comparison=comparison,
            )
        return metrics
