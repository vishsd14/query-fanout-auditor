# Changelog

All notable changes to query-fanout-auditor are documented here.

---

## [0.2.0] — 2026-07-14

### Added

**User-intent query filter (`--no-filter` to skip)**
After fan-out generation, a validation pass removes queries that read like content descriptions rather than real user searches — e.g. "2027 sailings on Southampton page" vs "what cruises depart from Southampton in 2027". Runs automatically; use `--no-filter` to see the raw unfiltered output.

**Bot-protected site support**
Two new input methods for sites that block automated fetches (403):
- `--page-image <path>`: pass a full-page screenshot — Claude extracts the content via vision. Accepts PNG, JPG, WebP. Images over 7MB are automatically compressed using Pillow before sending to the API.
- `--page-file <path>`: pass a saved HTML or text file. Both produce fully scored reports equivalent to a live URL fetch.

**Improvement forecast**
Every report now includes a deterministic score projection table across three fix scenarios: P1 only, P1+P2, and all gaps. Calculated using the same scoring formula as the main audit — not an estimate. Adds zero API cost.

**Content outline generator (`--outline-depth`, `--no-outline`)**
Generates structured content briefs for every P1 and P2 gap automatically.
- `--outline-depth lean` (default): H2/H3 structure, key questions to answer, recommended word count, schema markup recommendation
- `--outline-depth full`: lean structure + draft paragraph copy per section, written to the target market and persona
- `--no-outline`: skip outline generation for quick audit runs

**UNKNOWN coverage handling**
When page content can't be fetched, clusters are now assigned estimated priorities based on consensus count (P1*/P2*/P3*) rather than falling back to ⚪ N/A — keeping the report usable even without coverage scoring. A warning banner in the report makes the limitation explicit.

**SPA detection hint**
When the automated fetch returns very low word count (likely a JavaScript-rendered SPA returning near-empty markup), the terminal prints a specific warning and suggests `--page-image` or `--page-file` as alternatives.

### Changed

- Coverage scoring batched into groups of 10 clusters — fixes JSON truncation errors on pages with 20+ clusters (`max_tokens` was previously 2048, now 4096 per batch)
- Consensus clustering `max_tokens` increased from 2048 to 4096
- Perplexity model updated from deprecated `llama-3.1-sonar-large-128k-online` to `sonar-pro`
- Perplexity error handling improved: HTTP status codes, response structure mismatches, and JSON parse failures all surface descriptive messages rather than a generic exception string

---

## [0.1.0] — 2026-07-01

### Initial release

- Multi-model fan-out query generation: Claude (required), GPT-4o (optional), Perplexity (optional)
- Semantic clustering with cross-model consensus scoring
- Page coverage scoring: Covered / Partial / Missing per cluster
- Priority assignment: P1/P2/P3 based on coverage × consensus matrix
- Markdown report output + raw JSON export
- Claude Code skill (`SKILL.md`) for use within Claude Code sessions
- `--keyword`, `--url`, `--market`, `--persona`, `--fanouts`, `--output` flags
- Tested against: Packfora (packaging procurement, India market), P&O Cruises (Mediterranean cruise holidays, UK market)
