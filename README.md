# query-fanout-auditor

**Multi-model AI search visibility auditor for SEO and GEO.**

AI engines — Google AI Overviews, ChatGPT, Perplexity — don't just retrieve one result. They generate 15–20 sub-queries in the background ("fan-out"), retrieve answers to each, and synthesise a response. If your page doesn't answer those sub-queries, it won't be cited — even if it ranks well.

This tool audits a page against the sub-queries three AI models would generate for a given keyword, scores coverage across every cluster, and produces a prioritised content brief with an improvement forecast.

Most tools in this space use a single LLM. This one queries **Claude, GPT-4o, and Perplexity** simultaneously. Gaps that appear across all three are the ones worth fixing first.

---

## What it produces

```
📄 Fetching page content...
   ✅ Page fetched (1087 words extracted)

🤖 Generating fan-out queries...
   → Claude...     ✅ 20 queries
   → GPT-4o...     ✅ 20 queries
   → Perplexity... ✅ 20 queries

🧹 Filtering non-user-intent queries...
   ✅ 54 queries kept (6 removed)

🔗 Clustering by semantic intent...
   ✅ 21 unique clusters identified

📊 Scoring page coverage...
   ✅ Coverage scored

📈 Calculating improvement forecast...
   Current: 41/100 → P1 fix: 58 → P1+P2: 74 → All: 86

✍️  Generating content outlines (6 gaps · lean depth)...
   ✅ 6 outlines generated

📝 Generating report...
   ✅ Report saved to: report.md
```

**Every report includes:**
- Coverage score (0–100), weighted by cross-model consensus
- Full cluster scorecard: Covered / Partial / Missing per fan-out query
- P1/P2/P3 priority gaps with specific content fixes
- Improvement forecast across three fix scenarios
- Content outlines for every P1 and P2 gap

See [`sample_output/`](./sample_output/) for a full example report.

---

## Quick start

```bash
git clone https://github.com/vishsd14/query-fanout-auditor
cd query-fanout-auditor

pip install -r requirements.txt

cp .env.example .env
# Add your API keys to .env

python3 fanout_audit.py \
  --keyword "packaging procurement" \
  --url https://yoursite.com/page \
  --output report.md
```

---

## API keys

| Key | Required | Where to get |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Yes | [console.anthropic.com](https://console.anthropic.com) |
| `OPENAI_API_KEY` | ❌ Optional | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `PERPLEXITY_API_KEY` | ❌ Optional | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |

The tool runs with the Anthropic key only. Each additional model adds an independent perspective — consensus across 2–3 models is what drives the priority matrix.

---

## All flags

| Flag | Default | Description |
|---|---|---|
| `--keyword` | required | Primary keyword to audit |
| `--url` | required | Target page URL |
| `--market` | `Global` | Target market / country |
| `--persona` | `general user` | Simulated user persona |
| `--fanouts` | `20` | Fan-out queries per model |
| `--output` | stdout | Save report to a `.md` file |
| `--page-image` | — | Path to a page screenshot — Claude extracts content via vision |
| `--page-file` | — | Path to a saved `.html` or `.txt` file of the page |
| `--outline-depth` | `lean` | `lean` = structure only · `full` = with draft copy |
| `--no-outline` | — | Skip outline generation (faster runs) |
| `--no-filter` | — | Skip the user-intent query filter |

---

## Handling bot-protected sites

Many enterprise sites block automated fetches (HTTP 403). Two workarounds:

**Option A — Screenshot**

```bash
# Chrome: DevTools → Cmd+Shift+P → "Capture full size screenshot"

python3 fanout_audit.py \
  --keyword "your keyword" \
  --url https://yoursite.com \
  --page-image ~/Downloads/yoursite.png \
  --output report.md
```

Claude reads the screenshot via vision. Images over 7MB are automatically compressed — no manual resizing needed.

**Option B — Saved file**

```bash
# Chrome DevTools console: copy(document.body.innerText) → paste into page.txt

python3 fanout_audit.py \
  --keyword "your keyword" \
  --url https://yoursite.com \
  --page-file page.txt \
  --output report.md
```

---

## As a Claude Code skill

```bash
mkdir -p ~/.claude/skills/query-fanout-auditor
cp SKILL.md fanout_audit.py requirements.txt .env.example \
   ~/.claude/skills/query-fanout-auditor/
cd ~/.claude/skills/query-fanout-auditor
cp .env.example .env  # add your keys
pip install -r requirements.txt
```

Then in a Claude Code session: *"Run a fan-out audit for 'packaging procurement' on https://yoursite.com"*

---

## Priority matrix

| Coverage | Consensus | Priority |
|---|---|---|
| Missing | 3 models | 🔴 P1 — fix immediately |
| Missing | 2 models | 🟠 P2 — fix this sprint |
| Partial | 3 models | 🟠 P2 — strengthen section |
| Missing | 1 model | 🟡 P3 — consider adding |
| Partial | 1–2 models | 🟡 P3 — minor improvement |
| Covered | any | ✅ Keep — no action |

---

## The 7 intent cluster types

| Type | What AI engines ask | How AI answers |
|---|---|---|
| Definition | "What is X?" | Short paragraph |
| Specification | "What are the limits / numbers?" | Table or specific value |
| Comparison | "X vs Y" | Comparison table |
| How-to | "How do I do X?" | Numbered list |
| Tool/Resource | "Best tool for X?" | Named list |
| Edge Case | "What if X goes wrong?" | Conditional answer |
| Entity Expansion | "What do [authority] say about X?" | Named citations |

---

## Improvement forecast

Every report includes a deterministic projection — not an estimate. Uses the same scoring formula as the audit itself.

| Scenario | Projected score | Δ |
|---|---|---|
| Current state | 41/100 | — |
| Fix P1 only | 58/100 | +17 |
| Fix P1 + P2 | 74/100 | +33 |
| Fix all gaps | 86/100 | +45 |

This is an AI citation coverage projection, not a traffic or ranking forecast.

---

## Roadmap

- [ ] Schema markup analysis — present vs missing schema per gap
- [ ] Multi-keyword batch mode — `--keywords-file` flag
- [ ] SPA detection — warn when fetched content is suspiciously low
- [ ] Web interface — browser-based, no CLI required

---

## Companion tool

[gsc-anomaly-detector](https://github.com/vishsd14/gsc-anomaly-detector) — diagnose GSC traffic drops. The anomaly detector flags *what happened*, the fan-out auditor identifies *what to build* to recover AI visibility.

---

Built by [@seowithvishnu](https://linkedin.com/in/seowithvishnu) · MIT licence
