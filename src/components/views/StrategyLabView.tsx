import { Icon } from "@iconify/react";
import { useStrategyLab } from "../../lib/strategy";
import { PageHeader } from "../ui/PageHeader";
import { SectionHeading } from "../ui/SectionHeading";
import { Reveal } from "../ui/Reveal";
import { PnlHeader } from "../strategy/PnlHeader";
import { EquityCurve } from "../strategy/EquityCurve";
import { TradesTable } from "../strategy/TradesTable";
import { MoversCard } from "../strategy/MoversCard";
import { Learnings } from "../strategy/Learnings";
import { BacktestStats } from "../strategy/BacktestStats";
import { ResearchNotes } from "../strategy/ResearchNotes";

export default function StrategyLabView() {
  const { data: s, error } = useStrategyLab();

  return (
    <>
      <PageHeader
        icon="solar:test-tube-bold"
        eyebrow="Strategy Lab"
        title="The paper book, with nothing hidden"
        sub="Realized P&L, every closed position, what the latest window taught the engine, and the changes it recommends to itself — published straight from the runtime."
      />
      <main className="mx-auto w-full max-w-6xl px-5 pb-28 sm:px-8 pt-10">
        {error && (
          <div role="alert" className="grid h-48 place-items-center text-sm text-muted">Could not load the lab — {error}</div>
        )}
        {!error && !s && (
          <div role="status" aria-live="polite" className="flex h-48 items-center justify-center gap-2 text-muted">
            <Icon icon="solar:refresh-linear" className="size-4 animate-spin" aria-hidden="true" />
            <span className="text-sm">Loading paper-trading research…</span>
          </div>
        )}
        {s && (
          <>
            <Reveal immediate className="mb-6 flex items-center gap-2 rounded-xl bg-warning-soft px-4 py-2.5 text-sm text-foreground ring-1 ring-warning/25">
              <Icon icon="solar:shield-keyhole-bold" className="size-4 shrink-0 text-warning" />
              <span>{s.disclaimer ?? "Paper-trading research only — no live orders are ever placed."}</span>
            </Reveal>

            <PnlHeader s={s} />

            <section className="scroll-mt-24">
              <SectionHeading index="01" eyebrow="Track record" title="Paper equity over the window" sub="Cumulative realized P&L against the starting bankroll." />
              <Reveal>
                <EquityCurve s={s} />
              </Reveal>
              <Reveal className="mt-5">
                <MoversCard s={s} />
              </Reveal>
            </section>

            <section className="scroll-mt-24">
              <SectionHeading index="02" eyebrow="Ledger" title="Recent closed positions" sub="The most recent settled paper trades, newest first." />
              <Reveal>
                <TradesTable s={s} />
              </Reveal>
            </section>

            <section className="scroll-mt-24">
              <SectionHeading index="03" eyebrow="Self-critique" title="What the window taught the engine" sub="Auto-generated learnings and the changes the strategy recommends to itself." />
              <Reveal>
                <Learnings s={s} />
              </Reveal>
            </section>

            <section className="scroll-mt-24">
              <SectionHeading index="04" eyebrow="Backtest" title="From raw scans to approved trades" sub="The dedup funnel behind the metrics, plus a glossary for reading them honestly." />
              <Reveal className="mb-5">
                <BacktestStats s={s} />
              </Reveal>
              <Reveal>
                <ResearchNotes s={s} />
              </Reveal>
            </section>
          </>
        )}
      </main>
    </>
  );
}
