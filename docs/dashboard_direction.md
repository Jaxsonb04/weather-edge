# Dashboard Direction

The dashboard should feel like an operational instrument for a student quant
weather project, not a marketing page.

For full future redesign procedure, including required skills, safe refactor
steps, browser screenshot commands, and mobile verification gotchas, see
[design_redesign_playbook.md](design_redesign_playbook.md).

## First Screen

Prioritize:

- today/tomorrow toggle
- current headline forecast
- confidence/source disagreement
- observed high so far for today
- Google budget status
- direct explanation of whether the number is today or tomorrow

Avoid:

- burying the target date
- large decorative hero sections
- unclear "ultimate success" wording without sample count

## Detail Sections

Use expandable or lower-page sections for:

- source-by-source blend
- backtest success charts
- station observation details
- model comparison charts
- Google API cache/debug metadata

## Visual Tone

Use a quiet operations-dashboard style:

- dense but readable information
- restrained color
- clear status badges
- no decorative gradients as the main design idea
- charts and tables that support decisions

## UI Architecture

Data preparation and HTML/CSS rendering are now separated:

- `forecaster/dashboard_payload.py` builds the data context (token replacements
  and injected `__DATA_VARS__`).
- `forecaster/templates/landing.html` and `forecaster/templates/details.html`
  hold the markup, styles, and client JS.
- `forecaster/build_dashboard.py` only reads the templates, substitutes tokens,
  and writes `index.html` / `details.html`.

### Design system

A "meteorological instrument" aesthetic, intentionally distinct from generic
defaults: Fraunces (display) + IBM Plex Sans (body) + IBM Plex Mono (data),
a cold-blue / warm-amber temperature axis on a cool paper background, and
restrained atmosphere (soft glows + a faint chart grid) rather than decorative
gradients as the main idea. Shared design tokens live in each template's
`:root`. The landing leads with the today/tomorrow forecast as a single
instrument; details is a numbered field report (live forecast → how it's built →
model proof → diagnostics → track record → market research).

### Next steps

Keep the two `:root` token blocks in sync when adjusting the palette, and
consider extracting the shared CSS variables into one partial if a third page
is added.
