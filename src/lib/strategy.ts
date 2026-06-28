import { useResource } from "./data";

export interface ClosedPosition {
  id: number;
  ticker: string;
  label: string;
  side: string;
  contracts: number;
  entry_price: number;
  exit_price: number | null;
  realized_pnl: number;
  realized_roi: number | null;
  quality_score: number;
  risk_profile: string;
  target_date: string;
  closed_at: string;
  position_status_label?: string;
  position_status_tone?: string;
  outcome_reason?: string | null;
}

export interface DayRow {
  date: string;
  cumulative_realized: number;
  realized_pnl?: number;
  trades_opened?: number;
  opened?: number;
  closed?: number;
}

export interface WinnerLoser {
  label: string;
  side: string;
  ticker: string;
  target_date: string;
  realized_pnl: number;
  quality_score: number;
}

export interface StrategyLab {
  available: boolean;
  mode: string;
  disclaimer?: string;
  generated_at?: string;
  paper_trading: {
    available: boolean;
    summary: {
      realized_pnl: number;
      roi: number;
      hit_rate: number;
      closed_positions: number;
      win_count: number;
      loss_count: number;
      capital_at_risk: number;
      open_positions: number;
    };
    closed_positions: ClosedPosition[];
  };
  daily_summary: {
    available: boolean;
    current_equity: number;
    starting_bankroll: number;
    window_days?: number;
    totals: {
      cumulative_realized_pnl: number;
      hit_rate: number;
      roi: number;
      wins: number;
      losses: number;
      trades_closed: number;
      mean_abs_forecast_error_f: number;
    };
    days: DayRow[];
    biggest_winners: WinnerLoser[];
    biggest_losers: WinnerLoser[];
    learnings: string[];
    recommended_changes: string[];
  };
  backtest_summary: {
    available: boolean;
    counts: Record<string, number>;
  };
  research_notes: { term: string; note: string }[];
}

export const useStrategyLab = () => useResource<StrategyLab>("strategy_research.json");

/** Equity curve across the reporting window: starting bankroll + cumulative realized. */
export function equitySeries(s: StrategyLab) {
  const start = s.daily_summary?.starting_bankroll ?? 1000;
  return [...(s.daily_summary?.days ?? [])]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => ({
      date: d.date.slice(5), // MM-DD
      equity: Math.round((start + d.cumulative_realized) * 100) / 100,
      pnl: d.cumulative_realized,
    }));
}

/** Most-recent closed paper trades. */
export function recentTrades(s: StrategyLab, limit = 12): ClosedPosition[] {
  return [...(s.paper_trading?.closed_positions ?? [])]
    .sort((a, b) => (b.closed_at ?? "").localeCompare(a.closed_at ?? ""))
    .slice(0, limit);
}
