# Design Redesign Playbook

This playbook preserves the redesign workflow from the recap so future
WeatherEdge dashboard work follows the same careful process.

The core idea: read the code to find fragile parts, refactor only when it can be
proved identical, redesign with a clear WeatherEdge-specific direction, then
verify with the browser by driving the UI and reading values back.

## Required Skills

The recap used these local skills:

- `frontend-design`: commit to a distinct aesthetic direction and avoid generic
  dashboard UI.
- `ui-ux-pro-max`: query design-system, palette, typography, accessibility,
  layout, chart, and responsive recommendations.
- `web-design-guidelines`: fetch the latest Vercel Web Interface Guidelines
  before UI review.
- `agent-browser`: verify local pages with screenshots, viewport emulation, DOM
  reads, and interactions.

If a future machine is missing them, install the same four skills:

```bash
npx --yes skills add <frontend-design-skill-source> --skill frontend-design
npx --yes skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines
npx --yes skills add https://github.com/nextlevelbuilder/ui-ux-pro-max-skill --skill ui-ux-pro-max
npx --yes skills add https://github.com/vercel-labs/agent-browser --skill agent-browser
```

For `agent-browser`, the bare binary may not be on PATH. The known-good
invocation here is:

```bash
npx --yes agent-browser skills get core
```

Use the full reference when debugging viewport, screenshot, or selector issues:

```bash
npx --yes agent-browser skills get core --full
```

## Design Direction

WeatherEdge should feel like an operational instrument for station-aligned SFO
forecasting and Kalshi paper-trading research.

Use this direction unless the user explicitly changes it:

- Concept: meteorological instrument, field report, station-aware forecast desk.
- Typography: distinctive display face plus data-friendly sans/mono. The current
  dashboard direction uses Fraunces, IBM Plex Sans, and IBM Plex Mono.
- Color: cool paper background, cold-blue to warm-amber temperature axis, restrained
  source/status colors, high-contrast text.
- Density: data-dense but readable. Prioritize scanability, current forecast,
  target date, confidence, source disagreement, observed high, and budget status.
- Avoid: generic SaaS cards everywhere, purple gradients, decorative hero pages,
  vague success claims, oversized marketing sections, and visuals that bury the
  forecast target date.

The `ui-ux-pro-max` query used in the recap:

```bash
ui-ux-pro-max search \
  "weather forecast data dashboard analytics quant operational instrument clean minimal"
```

That query recommended a data-dense dashboard direction, blue data with amber
highlights, and dashboard-focused typography. Use it as input, not as a command
to copy blindly.

## Phase 0: Recon Before Edits

Before touching UI, map the generation pipeline.

Recommended commands:

```bash
rg --files
sed -n '1,240p' forecaster/build_dashboard.py
sed -n '1,240p' forecaster/dashboard_payload.py
```

Answer these before editing:

- Which files are generated artifacts and which files are source templates?
- Where are token substitutions performed?
- Which element IDs are read or written by JavaScript?
- Which charts, toggles, tables, and forecast fields depend on exact selectors?
- Which deployment or sync script ships the generated assets?

Current architecture to preserve:

- `forecaster/dashboard_payload.py` prepares dashboard data and token values.
- `forecaster/templates/landing.html` and `forecaster/templates/details.html`
  hold markup, CSS, and client JS.
- `forecaster/build_dashboard.py` reads templates, substitutes tokens, and writes
  `forecaster/index.html` and `forecaster/details.html`.

Runtime data authority:

- Local ignored runtime files may be stale MacBook data:
  `forecaster/weather.db`, `forecaster/google_weather_cache.json`,
  `forecaster/trading_signal.json`, `forecaster/strategy_research.json`,
  `forecaster/strategy_research.protected.json`,
  `forecaster/index.html`, `forecaster/details.html`,
  `forecaster/strategy-lab.html`, and `trading/data/`.
- After sync and refresh, live API/cache/dashboard state is AWS-side. Do not
  infer production data bugs from those local files.
- Before design smoke tests, clear local runtime state from the repository root:

```bash
python3 scripts/clear_local_runtime_state.py --confirm
```

The cleanup writes AWS-runtime placeholder JSON for local cache/signal files so
the page does not silently consume old data.

## Phase 1: Protect Fragile Hooks

The old redesign found that the danger zone was the interactive JavaScript that
reads and writes exact IDs, renders Chart.js charts, and consumes injected data.

Rules:

- Preserve every JS hook unless intentionally updating the matching JS.
- Do not rename IDs, `data-*` hooks, canvas IDs, or injected token names casually.
- Keep `__DATA_VARS__` and other replacement tokens intact until the generator
  substitutes them.
- If moving sections, move the markup around the hooks rather than rewriting the
  behavior.

Useful checks:

```bash
rg "__[A-Z_]+__" forecaster/templates forecaster/*.html
rg "getElementById|querySelector|canvas|Chart" forecaster/templates
```

## Phase 2: Refactor Safely

When splitting large embedded HTML strings or changing the source of generated
HTML, prove the refactor changes nothing before redesigning.

The recap's pattern:

```bash
cd forecaster
python3 build_dashboard.py
cd ..
cp forecaster/index.html /tmp/orig_index.html
cp forecaster/details.html /tmp/orig_details.html
cd forecaster
python3 build_dashboard.py
cd ..
diff -q /tmp/orig_index.html forecaster/index.html
diff -q /tmp/orig_details.html forecaster/details.html
```

Only proceed to visual changes after the identity diff is clean. If the diff is
not clean, inspect and fix the refactor before continuing.

## Phase 3: Redesign Pages

Landing-page guidance:

- The first viewport should expose the current forecast instrument, today/tomorrow
  switch, target date, confidence/source disagreement, observed high, and budget
  status.
- If the landing JS is self-contained, it can be redesigned as a unit, but still
  keep forecast state and token replacement intact.

Details-page guidance:

- Preserve the original script tail when possible.
- Reorder content into a numbered, decision-oriented narrative rather than a
  decorative gallery.
- Keep sections usable for source blend, backtest proof, station observations,
  diagnostics, track record, and market research.

Chart guidance:

- Update chart palettes consistently, preferably through shared color tokens and
  `Chart.defaults`.
- Check every old hex token is removed when replacing a palette.
- Use tabular figures and accessible contrast for tables, labels, and chart text.

## Phase 4: Static QA

Run these before browser verification:

```bash
cd forecaster
python3 build_dashboard.py
cd ..
python3 -m compileall forecaster/build_dashboard.py forecaster/dashboard_payload.py
rg "__[A-Z_]+__" forecaster/index.html forecaster/details.html
rg "#1d5f99|#f0b429" forecaster/templates forecaster/*.html
```

Adjust the hex grep for whatever old palette is being replaced.

Contrast and accessibility checks:

- Normal text should meet at least WCAG AA 4.5:1 contrast.
- Muted labels still need readable contrast; the previous pass darkened muted
  label text after finding it was below AA.
- Use visible focus states, `font-display: swap`, `color-scheme`, tabular numbers,
  `prefers-reduced-motion`, and `aria-live` where relevant.

For `web-design-guidelines`, fetch fresh rules before a review:

```bash
curl -L https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
```

## Phase 5: Browser Verification

Use `file://` to verify generated static HTML without a dev server.

Set a reusable command variable in your shell:

```bash
AB="npx --yes agent-browser"
```

Desktop capture loop:

```bash
$AB open "file://$PWD/forecaster/index.html"
$AB set viewport 1366 768 2
$AB screenshot /tmp/weatheredge-index-desktop.png
```

Full-page and element captures:

```bash
$AB screenshot --full /tmp/weatheredge-details-full.png
$AB screenshot ".instrument" /tmp/weatheredge-instrument.png
```

Element screenshots may sometimes come back blank even when the DOM is correct.
Diagnose with text, count, and box reads:

```bash
$AB get count "section"
$AB get box "#proof"
$AB get text "#proof"
$AB get text "#selectedTempNumber"
```

If element capture is blank, scroll the target into view and use a normal
viewport screenshot:

```bash
$AB scrollintoview "#proof"
$AB screenshot /tmp/weatheredge-proof-viewport.png
```

Real mobile verification must use `set viewport`, not `resize`.

```bash
$AB open "file://$PWD/forecaster/index.html"
$AB set viewport 390 844 2
$AB eval "window.innerWidth"
$AB screenshot --full /tmp/weatheredge-index-mobile.png
```

The expected `window.innerWidth` is `390`. If it reports a desktop width such as
`1280`, mobile CSS is not actually being tested.

Verify behavior, not just screenshots:

```bash
$AB eval "document.getElementById('forecastTemp').textContent"
$AB find text "Today" click
$AB eval "document.getElementById('forecastDate').textContent"
$AB eval "setActiveForecastDay('today')"
$AB eval "document.getElementById('selectedTempNumber').textContent"
$AB eval "document.querySelectorAll('canvas').length"
```

For the current details page, all Chart.js canvases should render; the prior
redesign expected 9 canvases.

Close sessions when done:

```bash
$AB close --all
```

## Phase 6: Deployment Awareness

Before declaring the design complete, confirm generated sources and templates
will ship wherever the dashboard is deployed.

Checks:

```bash
rg "rsync|forecaster|templates" -n .
git status --short
```

If a sync script copies the whole `forecaster/` directory, the templates should
ship automatically. If deployment copies only specific files, update that list.

## Acceptance Checklist

Use this checklist for future WeatherEdge frontend work:

- Recon completed: generator, payload, templates, tokens, and JS hooks understood.
- Required design skills consulted for substantial UI work.
- WeatherEdge instrument direction preserved or intentionally updated.
- Risky refactors proved byte-identical before visual edits.
- Generated HTML rebuilt successfully.
- No unresolved template tokens remain in generated files.
- Old palette tokens removed when replacing visual direction.
- Python compile check passes for touched generator/payload modules.
- Desktop screenshot reviewed.
- Real mobile screenshot reviewed with `window.innerWidth` confirming mobile width.
- Interactions tested by clicking/toggling or calling page JS.
- DOM state read back after interactions.
- Chart canvas count checked.
- Contrast, focus, motion, and responsive behavior reviewed.
- Deployment/sync path checked for new template or asset files.
