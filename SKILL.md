---
name: query-fanout-auditor
description: >
  Run this skill whenever the user wants to audit AI fan-out query coverage for a keyword and URL. Triggers: "fan-out audit", "query fan-out", "AI visibility audit", "what sub-queries does AI generate for [keyword]", "check my page for AI coverage", "fan-out coverage", "optimize for AI Overviews", "GEO audit for [keyword]", "what is AI asking about [topic]", "query gap analysis". This skill generates fan-out queries across multiple LLMs, scores your page's coverage of each query cluster, and produces a prioritised optimisation brief — new sections to add, H2s to create, or new pages to build.
---

# Query Fan-Out Auditor

Produces a **multi-model fan-out coverage brief** showing which AI sub-queries your page covers, which it partially covers, and which are missing — with prioritised recommendations.

---

## What This Skill Does

- Generates fan-out queries from **multiple LLMs** (Claude required; OpenAI + Perplexity optional)
- Identifies **cross-model consensus queries** (appear in 2+ models = high priority)
- Scores your page's coverage of each query cluster: **Covered / Partial / Missing**
- Outputs a **ranked action brief**: what to add, where, and whether to update the page or create new pages

---

## Setup (One-Time)

### Install dependencies
```bash
cd ~/.claude/skills/query-fanout-auditor
pip install -r requirements.txt
```

### Configure API keys
```bash
cp .env.example .env
# Edit .env — add your keys
```

**Required:**
- `ANTHROPIC_API_KEY` — Claude (you already have this if you're using Claude Code)

**Optional (better results):**
- `OPENAI_API_KEY` — GPT-4o fan-outs
- `PERPLEXITY_API_KEY` — Perplexity fan-outs (different retrieval model)

The script runs with only the Anthropic key. Each additional key adds a new model perspective and improves consensus scoring.

---

## How to Run

### Basic (Claude only)
```bash
python fanout_audit.py --keyword "seo title length" --url https://yoursite.com/page
```

### Full multi-model
```bash
python fanout_audit.py \
  --keyword "seo title length" \
  --url https://yoursite.com/page \
  --market "UK" \
  --persona "marketing manager" \
  --output report.md
```

### All flags
| Flag | Required | Default | Description |
|---|---|---|---|
| `--keyword` | ✅ | — | Primary keyword to audit |
| `--url` | ✅ | — | Target page URL |
| `--market` | ❌ | Global | Target market / country |
| `--persona` | ❌ | General user | Simulated user persona |
| `--fanouts` | ❌ | 20 | Number of fan-outs per model |
| `--output` | ❌ | stdout | Save report to file |

---

## Claude Code Workflow

When this skill triggers, Claude Code should:

### Step 1 — Gather Inputs
If not already provided, ask the user for:
1. **Primary keyword** (the query the target page ranks for or targets)
2. **Target URL** (the page to audit)
3. **Market / persona** (optional — improves persona-specific fan-out accuracy)

### Step 2 — Run the Script
```bash
python ~/.claude/skills/query-fanout-auditor/fanout_audit.py \
  --keyword "[keyword]" \
  --url "[url]" \
  --output fanout_raw.json
```

### Step 3 — Interpret the Raw Output
Claude reads `fanout_raw.json` and:
- Identifies the **top consensus clusters** (queries appearing across 2+ models)
- Highlights **Missing + High Consensus** gaps (= highest priority fixes)
- Groups gaps by intent type (definition, comparison, how-to, tool, specification, edge-case)

### Step 4 — Produce the Report
Output follows the **Fan-Out Coverage Brief** format below.

---

## Diagnostic Framework

### Intent Cluster Types
Classify every fan-out query into one of these:

| Cluster | Example | AI Answer Format |
|---|---|---|
| **Definition** | "what is X" | Short paragraph + key facts |
| **Specification** | "what is the limit/number/threshold for X" | Table or specific value |
| **Comparison** | "X vs Y", "best X for Y" | Comparison table |
| **How-to** | "how to do X", "steps to X" | Numbered list |
| **Tool/Resource** | "tool to check X", "checker for X" | List of tools |
| **Edge Case** | "what happens if X is too long/short" | Conditional answer |
| **Entity Expansion** | "Google's rule on X", "Yoast recommendation for X" | Authority citation |

### Coverage Scoring Rules
- **COVERED** — Page has a dedicated section/paragraph that directly answers this query
- **PARTIAL** — Page mentions the topic but doesn't answer the specific sub-question clearly
- **MISSING** — No mention of this topic on the page at all

### Priority Matrix
| Coverage | Consensus | Priority |
|---|---|---|
| Missing | 3 models | 🔴 P1 — Fix immediately |
| Missing | 2 models | 🟠 P2 — Fix this sprint |
| Partial | 3 models | 🟠 P2 — Strengthen section |
| Missing | 1 model | 🟡 P3 — Consider adding |
| Partial | 1-2 models | 🟡 P3 — Minor improvement |
| Covered | Any | ✅ Keep — no action |

---

## Output: Fan-Out Coverage Brief

---

**QUERY FAN-OUT COVERAGE BRIEF**
*Keyword: [keyword] | URL: [url] | Date: [date]*
*Models used: [Claude / GPT-4o / Perplexity] | Fan-outs generated: [n]*

---

### COVERAGE SUMMARY

| Metric | Value |
|---|---|
| Total fan-out queries generated | |
| Consensus queries (2+ models) | |
| Page coverage: Fully covered | |
| Page coverage: Partial | |
| Page coverage: Missing | |
| Overall coverage score | X / 100 |

---

### TOP CONSENSUS GAPS (P1 + P2)

For each gap:
```
Query cluster: [e.g. "character vs pixel width"]
Intent type: Specification
Appears in: Claude ✅ | GPT-4o ✅ | Perplexity ✅ (consensus: 3/3)
Coverage: MISSING
Recommended fix: Add a comparison table showing character count vs pixel width, desktop vs mobile limits
Action: Update existing page — add H2: "Characters vs Pixels: Which Limit Matters for Title Tags?"
```

---

### FULL COVERAGE SCORECARD

| Fan-out Query | Cluster | Models | Coverage | Priority |
|---|---|---|---|---|
| | | | | |

---

### RECOMMENDED ACTIONS

**Update existing page (add these sections):**
- H2: "..." → covers [cluster] gap
- H2: "..." → covers [cluster] gap

**Create new pages (separate intent):**
- "[title]" → targets [fan-out query cluster] — too distinct to add to current page

**Already well covered (no action):**
- [clusters] — keep as-is

---

### COVERAGE SCORE BREAKDOWN

| Intent Cluster | Covered | Partial | Missing |
|---|---|---|---|
| Definition | | | |
| Specification | | | |
| Comparison | | | |
| How-to | | | |
| Tool/Resource | | | |
| Edge Case | | | |
| Entity Expansion | | | |

---

## Edge Cases

**URL not accessible / paywalled:** Ask user to paste page content manually. Script will skip URL fetch and accept text input.

**Keyword returns zero consensus queries:** All three models diverged completely. Widen the keyword or try the head term. Flag this — it may mean the topic is highly personalised and AI answers will vary too much to optimise reliably.

**Page already covers everything:** Score 90+/100. Note it. Recommend monitoring AI citations via Bing Webmaster Grounding Queries for confirmation, not more content changes.

**Very long page (10,000+ words):** Script chunks the content. Claude scores each chunk independently, then merges. Flag to user if chunking was applied.

---

## Dependencies

- `anthropic` — required
- `openai` — optional
- `requests` — for URL fetching
- `beautifulsoup4` — for page content extraction
- `python-dotenv` — for `.env` key loading
- `rich` — for terminal output formatting
