from __future__ import annotations

from dataclasses import replace

from .config import StrategyConfig
from .db import PaperStore
from .fees import (
    contracts_for_budget,
    quadratic_fee_average_per_contract,
)
from .models import TradeDecision


class PaperTrader:
    def __init__(
        self,
        store: PaperStore,
        config: StrategyConfig | None = None,
        *,
        risk_profile: str | None = None,
    ) -> None:
        self.store = store
        self.config = config or StrategyConfig()
        self.risk_profile = risk_profile

    def with_paper_stake(self, decision: TradeDecision, stake_dollars: float | None) -> TradeDecision:
        if stake_dollars is None or not decision.approved:
            return decision
        if stake_dollars <= 0:
            raise ValueError("paper stake must be greater than zero")
        if decision.ask <= 0:
            return decision
        contracts = contracts_for_budget(decision.ask, stake_dollars)
        contracts = min(contracts, self.config.max_contracts_per_market)
        if decision.ask_size > 0:
            contracts = min(contracts, decision.ask_size)
        if not self.config.allow_fractional_contracts:
            contracts = float(int(contracts))
        fee_per_contract = quadratic_fee_average_per_contract(decision.ask, contracts)
        cost_per_contract = decision.ask + fee_per_contract
        edge = decision.probability - cost_per_contract
        edge_lcb = decision.probability_lcb - cost_per_contract
        return replace(
            decision,
            fee_per_contract=fee_per_contract,
            cost_per_contract=cost_per_contract,
            edge=edge,
            edge_lcb=edge_lcb,
            recommended_contracts=contracts,
            expected_profit=edge * contracts,
        )

    def with_paper_stakes(
        self,
        decisions: list[TradeDecision],
        stake_dollars: float | None,
    ) -> list[TradeDecision]:
        return [self.with_paper_stake(decision, stake_dollars) for decision in decisions]

    def with_daily_budget(
        self,
        decisions: list[TradeDecision],
        daily_budget: float | None,
    ) -> list[TradeDecision]:
        if daily_budget is None:
            return decisions
        if daily_budget < 0:
            raise ValueError("daily budget cannot be negative")
        approved = [
            decision
            for decision in decisions
            if decision.approved and decision.cost_per_contract > 0
        ]
        if not approved:
            return decisions
        if daily_budget == 0:
            approved_keys = {_decision_key(decision) for decision in approved}
            return [
                replace(decision, recommended_contracts=0.0, expected_profit=0.0)
                if _decision_key(decision) in approved_keys
                else decision
                for decision in decisions
            ]
        total_risk_spend = sum(
            decision.recommended_contracts * decision.cost_per_contract
            for decision in approved
        )
        if total_risk_spend <= daily_budget:
            return decisions
        scale = daily_budget / total_risk_spend
        approved_keys = {_decision_key(decision) for decision in approved}
        adjusted: list[TradeDecision] = []
        for decision in decisions:
            if _decision_key(decision) in approved_keys:
                contracts = decision.recommended_contracts * scale
                adjusted.append(
                    replace(
                        decision,
                        recommended_contracts=contracts,
                        expected_profit=decision.edge * contracts,
                    )
                )
            else:
                adjusted.append(decision)
        return adjusted

    def place_approved(
        self,
        target_date: str,
        decisions: list[TradeDecision],
        *,
        stake_dollars: float | None = None,
        daily_budget: float | None = None,
        bankroll: float | None = None,
    ) -> list[int]:
        if stake_dollars is not None and daily_budget is not None:
            raise ValueError("use either paper stake or daily budget, not both")
        if daily_budget is not None:
            decisions = self.with_daily_budget(decisions, daily_budget)
        exposure_remaining = self._target_exposure_remaining(target_date, bankroll)
        order_ids = []
        for decision in decisions:
            adjusted = self.with_paper_stake(decision, stake_dollars)
            if not adjusted.approved or adjusted.recommended_contracts <= 0:
                continue
            adjusted = self._normalize_contracts(adjusted)
            if adjusted is None:
                continue
            if adjusted.cost_per_contract >= 1.0 or adjusted.cost_per_contract <= 0:
                continue
            # Deliberately side-agnostic: one open position per market. Holding
            # YES and NO on the same bucket locks in the combined entry costs
            # plus fees, so an open position blocks the opposite side too; the
            # monitor's exit rules manage the existing leg instead.
            if self.store.has_open_paper_position(
                target_date,
                adjusted.ticker,
                risk_profile=self.risk_profile,
            ):
                continue
            entries = self.store.entries_for_market_side(
                target_date,
                adjusted.ticker,
                adjusted.side,
                risk_profile=self.risk_profile,
            )
            if entries >= self.config.max_entries_per_market_side:
                continue
            if exposure_remaining is not None:
                adjusted = self._fit_to_exposure(adjusted, exposure_remaining)
                if adjusted is None:
                    continue
            order_ids.append(
                self.store.record_paper_order(
                    target_date,
                    adjusted,
                    risk_profile=self.risk_profile,
                )
            )
            if exposure_remaining is not None:
                exposure_remaining -= adjusted.recommended_contracts * adjusted.cost_per_contract
        return order_ids

    def _target_exposure_remaining(self, target_date: str, bankroll: float | None) -> float | None:
        """Cumulative per-target risk cap, persisted across scans via the DB.

        With no daily paper budget, this is the guard that keeps repeated
        15-minute scans from stacking unbounded exposure onto one settlement
        date.
        """

        if bankroll is None or bankroll <= 0:
            return None
        cap = bankroll * self.config.max_target_exposure_pct
        if cap <= 0:
            return None
        spent = self.store.paper_spend_for_target(target_date, risk_profile=self.risk_profile)
        return max(0.0, cap - spent)

    def _normalize_contracts(self, decision: TradeDecision) -> TradeDecision | None:
        """Round paper orders down to whole contracts like the live exchange.

        Event-cap scaling can leave fractional sizes even when the evaluator
        floors; fractional dust also breaks the ceil-to-cent fee model.
        """

        if self.config.allow_fractional_contracts:
            return decision
        contracts = float(int(decision.recommended_contracts))
        if contracts < 1:
            return None
        if contracts == decision.recommended_contracts:
            return decision
        return replace(
            decision,
            recommended_contracts=contracts,
            expected_profit=decision.edge * contracts,
        )

    def _fit_to_exposure(
        self,
        decision: TradeDecision,
        exposure_remaining: float,
    ) -> TradeDecision | None:
        cost = decision.cost_per_contract
        spend = decision.recommended_contracts * cost
        if spend <= exposure_remaining + 1e-9:
            return decision
        contracts = exposure_remaining / cost
        if not self.config.allow_fractional_contracts:
            contracts = float(int(contracts))
        if contracts <= 0:
            return None
        return replace(
            decision,
            recommended_contracts=contracts,
            expected_profit=decision.edge * contracts,
        )


def _decision_key(decision: TradeDecision) -> tuple[str, str]:
    return (decision.ticker, decision.side)
