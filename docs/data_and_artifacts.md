# Data And Artifacts

## Local Artifacts

- Forecaster source scripts.
- Raw KSFO NOAA GHCNh station files from `2016-2026 weather data/`.
- Optional local `weather.db` forecast archive. Treat it as disposable runtime
  state unless it was just regenerated for the current task.
- Dashboard artifacts: `index.html`, `details.html`, `strategy-lab.html`,
  `forecast_data.json`, `weather_story_data.json`, optional `trading_signal.json`,
  optional `strategy_research.json`, optional `strategy_research.protected.json`,
  `ab_test_results.json`, `model_compare_results.json`.
- Trained model and prediction artifacts under `forecaster/models/`.
- EDA/evaluation plots under `forecaster/plots/`.
- Trading source package, tests, docs, AWS scripts, and small Kalshi research
  orderbook snapshots.

## Excluded From Git

- `.git`
- virtual environments
- `__pycache__`
- `.DS_Store`
- private `.env`
- Google usage ledger
- logs
- generated `combined_weather.csv`, `weather_features.csv`, and `output.csv`
- generated dashboard HTML, Google Weather cache, and public trading signal
- live Kalshi `paper_trading.db`

## Git Policy

The root `.gitignore` keeps large local data and live runtime state out of git by
default:

- `forecaster/weather.db`
- `forecaster/2016-2026 weather data/`
- `forecaster/google_weather_cache.json`
- `forecaster/trading_signal.json`
- `forecaster/strategy_research.json`
- `forecaster/strategy_research.protected.json`
- `forecaster/dataset_research.json` (written nightly by the dataset backfill;
  summarized into the Strategy Lab `dataset_research` section)
- `forecaster/index.html`
- `forecaster/details.html`
- `forecaster/strategy-lab.html`
- `trading/data/`

This keeps large local data, generated dashboard output, and runtime state out
of public commits unless they are intentionally published.

## Runtime Source Of Truth

For live dashboard/API/cache state, AWS is authoritative after sync and refresh.
Local ignored artifacts can be old MacBook leftovers, so local checks and smoke
tests must not treat them as production evidence.

AWS runtime paths are documented in `docs/aws_lightsail.md`, typically:

- `/opt/weatheredge/forecaster/weather.db`
- `/opt/weatheredge/forecaster/google_weather_cache.json`
- `/opt/weatheredge/forecaster/trading_signal.json`
- `/opt/weatheredge/forecaster/strategy_research.json`
- `/opt/weatheredge/forecaster/strategy_research.protected.json`
- `/opt/weatheredge/forecaster/index.html`
- `/opt/weatheredge/forecaster/details.html`
- `/opt/weatheredge/forecaster/strategy-lab.html`
- `/opt/weatheredge/trading/data/`

The initial Lightsail sync excludes these local runtime artifacts so stale local
state does not overwrite AWS-side refreshed state.

Before local dashboard design verification, run this from the repository root:

```bash
python3 scripts/clear_local_runtime_state.py --confirm
```

That removes local runtime DB/cache/generated dashboard files and writes
explicit AWS-runtime placeholder JSON for `forecaster/google_weather_cache.json`,
`forecaster/trading_signal.json`, `forecaster/strategy_research.json`, and
`forecaster/strategy_research.protected.json`. Use
`--no-placeholders` only when you want to test missing-file behavior.
