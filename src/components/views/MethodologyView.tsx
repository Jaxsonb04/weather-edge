import { Icon } from "@iconify/react";
import type { DashboardData } from "../../lib/data";
import { useDiagnostics } from "../../lib/diagnostics";
import { PageHeader } from "../ui/PageHeader";
import { SectionHeading } from "../ui/SectionHeading";
import { Reveal } from "../ui/Reveal";
import { ModelCompareChart } from "../charts/ModelCompareChart";
import { FeatureImportanceChart } from "../charts/FeatureImportanceChart";
import { HeldOutScatter } from "../charts/HeldOutScatter";
import { ABSignificance } from "../methodology/ABSignificance";
import { ClimatologyChart } from "../charts/ClimatologyChart";
import { HistogramChart } from "../charts/HistogramChart";
import { CalibrationChart } from "../charts/CalibrationChart";
import { CohortChart } from "../charts/CohortChart";

export default function MethodologyView({ data }: { data: DashboardData }) {
  const { forecast, story, signal } = data;
  const { data: diag, error: diagError } = useDiagnostics();

  return (
    <>
      <PageHeader
        icon="solar:graph-up-bold"
        eyebrow="Methodology & diagnostics"
        title="How the forecast earns its trust"
        sub="A decade of KSFO observations, two models held out-of-sample, and the calibration that turns a temperature distribution into honest probabilities."
      />
      <main className="mx-auto w-full max-w-6xl px-5 pb-28 sm:px-8">
        <section className="scroll-mt-24">
          <SectionHeading
            index="01"
            eyebrow="Model proof"
            title="LSTM in production, held out-of-sample"
            sub="Compared against an XGBoost challenger and a naive persistence baseline on days neither model trained on."
          />
          {diag ? (
            <div className="space-y-5">
              <div className="grid gap-5 lg:grid-cols-2">
                <Reveal delay={0.04}>
                  <ModelCompareChart diag={diag} />
                </Reveal>
                <Reveal delay={0.08}>
                  <FeatureImportanceChart diag={diag} />
                </Reveal>
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                <Reveal delay={0.04}>
                  <ABSignificance diag={diag} />
                </Reveal>
                <Reveal delay={0.08}>
                  <HeldOutScatter diag={diag} />
                </Reveal>
              </div>
            </div>
          ) : diagError ? (
            <div role="alert" className="flex h-48 items-center justify-center text-sm text-muted">
              Couldn't load diagnostics — {diagError}
            </div>
          ) : (
            <div role="status" aria-live="polite" className="flex h-48 items-center justify-center gap-2 text-muted">
              <Icon icon="solar:refresh-linear" className="size-4 animate-spin" aria-hidden="true" />
              <span className="text-sm">Loading diagnostics…</span>
            </div>
          )}
        </section>

        <section className="scroll-mt-24">
          <SectionHeading
            index="02"
            eyebrow="Forecast accuracy"
            title="Ten years of KSFO, distilled"
            sub={`${forecast.n_days_observed.toLocaleString()} observed days across ${forecast.n_years} years anchor the climatology, post-processing, and calibration.`}
          />
          <Reveal className="mb-5">
            <ClimatologyChart forecast={forecast} />
          </Reveal>
          <div className="grid gap-5 lg:grid-cols-2">
            <Reveal delay={0.05}>
              <HistogramChart story={story} forecast={forecast} />
            </Reveal>
            <Reveal delay={0.1}>
              <CalibrationChart signal={signal} />
            </Reveal>
          </div>
          <Reveal className="mt-5">
            <CohortChart signal={signal} />
          </Reveal>
        </section>
      </main>
    </>
  );
}
