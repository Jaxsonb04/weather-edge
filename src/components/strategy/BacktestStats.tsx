import { Card } from "@heroui/react";
import { Stat } from "../ui/Stat";
import type { StrategyLab } from "../../lib/strategy";

const fmt = (n: number | undefined) => (n == null ? "—" : n.toLocaleString());

/** The dedup funnel: hundreds of thousands of 15-min scans → unique → approved. */
export function BacktestStats({ s }: { s: StrategyLab }) {
  const c = s.backtest_summary?.counts ?? {};
  const tiles = [
    { label: "Raw scans", value: fmt(c.raw_signals) },
    { label: "Pre-resolution", value: fmt(c.pre_resolution_signals) },
    { label: "Deduped", value: fmt(c.deduped_signals) },
    { label: "Approved", value: fmt(c.approved_signals) },
    { label: "Settled", value: fmt(c.settled_signals) },
  ];
  return (
    <Card className="rounded-2xl">
      <Card.Header>
        <Card.Title className="text-base">Backtest coverage</Card.Title>
        <Card.Description className="text-sm text-muted">
          Every 15-minute scan is counted once per target/market/side, using the entry snapshot.
        </Card.Description>
      </Card.Header>
      <Card.Content className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {tiles.map((t) => (
          <Stat key={t.label} label={t.label} value={t.value} />
        ))}
      </Card.Content>
    </Card>
  );
}
