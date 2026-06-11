# WeatherEdge Agent Instructions

## Attribution Hygiene

Do not add AI-assistant signatures, generated-by notices, model/vendor
attribution, co-author trailers, or assistant identities to committed files,
contributors, release notes, PR text, generated artifacts, or metadata unless
the user explicitly asks for that attribution.

Keep authorship and contributor metadata human-owned or project-bot-owned. Treat
local assistant state directories and agent lockfiles as disposable workspace
state, not project source.

## Design And Redesign Memory

For any future WeatherEdge dashboard design, redesign, UI polish, or frontend
quality pass, read and follow `docs/design_redesign_playbook.md` before editing.

Required design workflow:

- Use the local skills `frontend-design`, `ui-ux-pro-max`,
  `web-design-guidelines`, and `agent-browser` for substantial UI work.
- Treat the dashboard as generated static HTML. Understand the Python generator,
  template files, token substitution, and dashboard payload before changing UI.
- Preserve JavaScript hooks, element IDs, template tokens, and chart/data wiring.
  For risky template refactors, prove the refactor is byte-identical before
  making visual changes.
- Keep the WeatherEdge visual direction: an operational meteorological
  instrument for a student quant weather project, not a marketing landing page.
- Verify desktop and real mobile layouts with browser screenshots, then verify
  behavior by driving the page and reading DOM state back.

Do not finish a frontend change with only static inspection. Build the generated
HTML, check for unresolved tokens, run the relevant Python verification, and use
browser automation when the page is meant to be viewed or interacted with.

## Runtime Data Authority

The local MacBook may contain stale ignored runtime artifacts. Treat these as
disposable unless you just regenerated them in the current task:

- `forecaster/weather.db`
- `forecaster/google_weather_cache.json`
- `forecaster/trading_signal.json`
- `forecaster/strategy_research.json`
- `forecaster/strategy_research.protected.json`
- `forecaster/index.html`
- `forecaster/details.html`
- `forecaster/strategy-lab.html`
- `trading/data/`

After sync and refresh, live API/cache/dashboard state is AWS-side, under the
Lightsail runtime paths documented in `docs/aws_lightsail.md`, and the public
dashboard is published from AWS-generated artifacts. Do not diagnose production
data problems from stale local ignored files.

Before local dashboard design verification, clear stale runtime state from the
repository root:

```bash
python3 scripts/clear_local_runtime_state.py --confirm
```

The cleanup writes explicit local placeholder JSON for the Google cache, trading
signal, and Strategy Lab research artifact saying the live data belongs on AWS
after sync. Then build from inside `forecaster/` before browser checks:

```bash
cd forecaster
python3 build_dashboard.py
```

## Conversation Queue

When the user prefixes a message with `Queue:`, `Parking lot:`, or `Later:`,
treat it as saved context only. Acknowledge it briefly, then continue the
active thread without steering toward the queued item.

Only switch to queued text when the user explicitly says `Switch to queue`,
`Use the queued item`, or similar.
