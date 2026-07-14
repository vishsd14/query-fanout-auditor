#!/usr/bin/env python3
"""
Query Fan-Out Auditor
Multi-model fan-out query generator + page coverage scorer
GitHub: github.com/vishsd14/query-fanout-auditor
"""

import os
import json
import argparse
import sys
from datetime import datetime
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY")

MAX_PAGE_CHARS = 8000  # truncate long pages before sending to LLM


# ─────────────────────────────────────────────
# STEP 1: FETCH PAGE CONTENT
# ─────────────────────────────────────────────

def fetch_page_content(url: str) -> str:
    """Fetch and extract clean text from a URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; QueryFanOutAuditor/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove nav, footer, scripts
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Truncate to avoid token overload
        return text[:MAX_PAGE_CHARS]
    except Exception as e:
        return f"ERROR_FETCHING_URL: {e}"


def extract_content_from_image(image_path: str) -> str:
    """
    Extract page text content from a screenshot using Claude's vision.

    Useful for bot-protected sites where automated URL fetching fails (403).
    Accepts PNG, JPG, WebP, or GIF. For long pages, use a full-page screenshot
    tool (e.g. Chrome's 'Capture full size screenshot' in DevTools) rather than
    a viewport-only capture to maximise content coverage.
    """
    import base64
    import mimetypes
    import io

    if not ANTHROPIC_KEY:
        print("[Image extraction] ANTHROPIC_API_KEY required.")
        return ""

    try:
        with open(image_path, "rb") as f:
            raw_bytes = f.read()
    except Exception as e:
        print(f"[Image extraction] Could not read file: {e}")
        return ""

    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        mime_type = "image/png"

    # ── Compress if image exceeds the 10MB API limit ──────────────────────────
    # Base64 adds ~33% overhead, so target 7MB file = ~9.3MB encoded (safe margin)
    MAX_BYTES = 7 * 1024 * 1024

    if len(raw_bytes) > MAX_BYTES:
        if not HAS_PIL:
            print(f"   ⚠️  Screenshot is {len(raw_bytes)/1024/1024:.1f}MB — exceeds the 10MB API limit.")
            print("   ⚠️  Install Pillow for automatic compression: pip install Pillow --break-system-packages")
            print("   ⚠️  Or capture a viewport-only screenshot instead of a full-page one.")
            return ""

        print(f"   ℹ️  Screenshot is {len(raw_bytes)/1024/1024:.1f}MB — compressing for API (10MB limit)...")
        try:
            img = PILImage.open(io.BytesIO(raw_bytes))

            # Convert to RGB — PNG with alpha or palette mode can't be saved as JPEG
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")

            # Resize width to max 1440px — plenty of resolution for text extraction
            MAX_WIDTH = 1440
            if img.width > MAX_WIDTH:
                ratio = MAX_WIDTH / img.width
                new_size = (MAX_WIDTH, int(img.height * ratio))
                img = img.resize(new_size, PILImage.LANCZOS)

            # Compress iteratively until under limit
            compressed = None
            for quality in [85, 75, 65, 55, 45]:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                if buf.tell() <= MAX_BYTES:
                    compressed = buf.getvalue()
                    print(f"   ✅ Compressed to {len(compressed)/1024/1024:.1f}MB (JPEG q={quality}, {img.width}×{img.height}px)")
                    break

            if compressed is None:
                print("   ⚠️  Could not compress screenshot under 7MB even at lowest quality.")
                print("   ⚠️  Try a viewport-only screenshot or use --page-file instead.")
                return ""

            raw_bytes = compressed
            mime_type = "image/jpeg"

        except Exception as e:
            print(f"   ⚠️  Compression failed: {e}")
            return ""

    image_data = base64.standard_b64encode(raw_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": """Extract all meaningful text content from this webpage screenshot for SEO content analysis.

Include:
- All visible headings (H1, H2, H3 and equivalents)
- All body paragraphs, sentences, and text content
- Navigation labels and menu items
- Call-to-action text and button labels
- Statistics, numbers, data points, and percentages
- Testimonial or case study text
- Footer text if visible

Exclude:
- Pure layout/design elements with no text
- Decorative separators or visual-only components

Preserve the heading hierarchy using plain text section breaks.
Output ONLY the extracted page content — no preamble, no commentary."""
                    }
                ]
            }]
        )
        return message.content[0].text.strip()[:MAX_PAGE_CHARS]
    except Exception as e:
        print(f"[Image extraction] Claude vision error: {e}")
        return ""


# ─────────────────────────────────────────────
# STEP 2: GENERATE FAN-OUT QUERIES PER MODEL
# ─────────────────────────────────────────────

FAN_OUT_PROMPT = """You are an AI search engine about to answer the query: "{keyword}"

A user in {market} ({persona}) typed this query.

Before giving your final answer, you would internally generate sub-queries to research this topic thoroughly. These are called "fan-out queries."

Generate exactly {n} specific fan-out sub-queries you would search for to fully answer this question.

Cover these intent types (not all need equal representation):
- Definition: what is / what does X mean
- Specification: limits, numbers, thresholds, recommended values
- Comparison: X vs Y, best X for Y
- How-to: steps to do X, how to fix X
- Tool/Resource: tools to check X, checkers for X
- Edge Case: what happens if X is too long/short/wrong
- Entity Expansion: what does [authority/brand] say about X

Return ONLY a valid JSON array of strings. No preamble, no explanation, no markdown.
Example: ["sub-query 1", "sub-query 2", "sub-query 3"]"""


def generate_fanouts_claude(keyword: str, market: str, persona: str, n: int) -> list:
    """Generate fan-out queries using Claude."""
    if not ANTHROPIC_KEY:
        return []
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = FAN_OUT_PROMPT.format(keyword=keyword, market=market, persona=persona, n=n)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[Claude fan-out error] {e}")
        return []


def generate_fanouts_openai(keyword: str, market: str, persona: str, n: int) -> list:
    """Generate fan-out queries using GPT-4o."""
    if not OPENAI_KEY:
        return []
    client = OpenAI(api_key=OPENAI_KEY)
    prompt = FAN_OUT_PROMPT.format(keyword=keyword, market=market, persona=persona, n=n)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.7
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[GPT-4o fan-out error] {e}")
        return []


def generate_fanouts_perplexity(keyword: str, market: str, persona: str, n: int) -> list:
    """Generate fan-out queries using Perplexity (sonar-pro model)."""
    if not PERPLEXITY_KEY:
        return []
    prompt = FAN_OUT_PROMPT.format(keyword=keyword, market=market, persona=persona, n=n)
    try:
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sonar-pro",  # updated from deprecated llama-3.1-sonar-large-128k-online
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.7
        }
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers, json=payload, timeout=30
        )
        resp.raise_for_status()  # surface HTTP errors (401, 429, 500) clearly
        resp_json = resp.json()

        # Guard: check response structure before indexing
        if "choices" not in resp_json:
            print(f"[Perplexity fan-out error] Unexpected response structure: {resp_json}")
            return []

        raw = resp_json["choices"][0]["message"]["content"].strip()

        # Strip markdown fences (```json ... ``` or ``` ... ```)
        if "```" in raw:
            parts = raw.split("```")
            # parts[1] is the content inside fences
            raw = parts[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        # Find the JSON array even if there's preamble text
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            raw = raw[start:end]

        return json.loads(raw)

    except requests.exceptions.HTTPError as e:
        print(f"[Perplexity fan-out error] HTTP {e.response.status_code}: {e.response.text[:200]}")
        return []
    except json.JSONDecodeError as e:
        print(f"[Perplexity fan-out error] JSON parse failed: {e} | Raw: {raw[:200]}")
        return []
    except Exception as e:
        print(f"[Perplexity fan-out error] {e}")
        return []


# ─────────────────────────────────────────────
# STEP 2b: USER-INTENT FILTER
# ─────────────────────────────────────────────

def filter_user_intent_queries(raw_results: dict, keyword: str) -> dict:
    """
    Remove queries that don't read like genuine user searches.

    LLMs occasionally generate queries that describe page content or site
    structure rather than what a user would actually type — e.g.
    "2027 sailings on Southampton page" or "destinations tab cruise site".
    This pass removes them before clustering so they don't pollute consensus.

    Runs once per model output. Skipped if ANTHROPIC_KEY is unavailable.
    """
    if not ANTHROPIC_KEY:
        return raw_results

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    filtered = {}

    for model_name, queries in raw_results.items():
        if not queries:
            filtered[model_name] = queries
            continue

        filter_prompt = f"""You are quality-checking a list of AI-generated fan-out queries for the keyword: "{keyword}"

Your job: remove any query that does NOT sound like something a real person would type into Google, ChatGPT, or Perplexity.

REMOVE queries that:
- Describe page content or site structure rather than a user question ("2027 sailings on Southampton page", "destinations from Southampton tab", "cruise collection page 2027")
- Use internal/editorial language a content strategist would use, not a searcher ("content covering X", "section about Y", "page listing Z")
- Reference UI elements or navigation ("see X section", "filter by X", "search results for X on site")
- Are meta-descriptions masquerading as queries ("cruises departing Southampton in 2027 itinerary listing")
- Duplicate the seed keyword almost verbatim with no additional intent ("cruises from Southampton 2027" when the keyword is already "cruises from Southampton 2027")

KEEP queries that:
- Sound like a genuine user question or search ("how far in advance should I book a 2027 cruise?")
- Use natural conversational language ("what's included in a P&O cruise package?")
- Express a real information need ("best time of year to cruise from Southampton")
- Represent comparisons, how-tos, or decisions a user would actually make
- Could plausibly appear in Google Search Console as a real query

INPUT QUERIES (from model: {model_name}):
{json.dumps(queries, indent=2)}

Return ONLY a valid JSON array of the queries to KEEP. No preamble, no explanation, no markdown."""

        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": filter_prompt}]
            )
            raw = message.content[0].text.strip()

            # Strip markdown fences if present
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            # Extract JSON array defensively
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                raw = raw[start:end]

            kept = json.loads(raw)
            removed = len(queries) - len(kept)
            if removed > 0:
                print(f"     🧹 {model_name}: removed {removed} non-user-intent quer{'y' if removed == 1 else 'ies'} ({len(kept)} kept)")
            filtered[model_name] = kept

        except Exception as e:
            print(f"     [Filter warning] {model_name}: {e} — using unfiltered queries")
            filtered[model_name] = queries  # fail safe: keep originals if filter errors

    return filtered


# ─────────────────────────────────────────────
# STEP 3: CONSENSUS SCORING
# ─────────────────────────────────────────────

def compute_consensus(results: dict) -> list:
    """
    Merge fan-outs from all models.
    Score by how many models generated a similar query.
    Returns list of dicts: {query, models, consensus_count}
    """
    if not ANTHROPIC_KEY:
        print("ERROR: ANTHROPIC_API_KEY is required.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    all_queries_raw = []
    model_map = {}

    for model_name, queries in results.items():
        for q in queries:
            all_queries_raw.append(q)
            model_map[q] = model_map.get(q, []) + [model_name]

    # Use Claude to cluster semantically similar queries
    cluster_prompt = f"""You are given a list of fan-out queries generated by multiple AI models for the same keyword.

Many queries are semantically similar (same intent, different phrasing). Your job is to:
1. Group queries by semantic intent into clusters
2. For each cluster, provide a canonical query label (the clearest phrasing)
3. List which original queries fall into this cluster
4. List which models contributed to this cluster

INPUT QUERIES (with source model):
{json.dumps(model_map, indent=2)}

Return ONLY a valid JSON array. Each item:
{{
  "canonical": "the clearest phrasing of this intent",
  "intent_type": "Definition|Specification|Comparison|How-to|Tool|Edge Case|Entity Expansion",
  "variants": ["query 1", "query 2"],
  "models": ["claude", "gpt4o"],
  "consensus_count": 2
}}

Return ONLY the JSON array. No preamble."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,  # increased: 60 raw queries clustering into ~20 objects needs headroom
            messages=[{"role": "user", "content": cluster_prompt}]
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        # Find JSON array bounds defensively
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
        clusters = json.loads(raw.strip())
        # Sort by consensus count descending
        clusters.sort(key=lambda x: x.get("consensus_count", 0), reverse=True)
        return clusters
    except Exception as e:
        print(f"[Consensus clustering error] {e}")
        # Fallback: return flat list without clustering
        return [{"canonical": q, "intent_type": "Unknown",
                 "variants": [q], "models": model_map.get(q, []),
                 "consensus_count": len(model_map.get(q, []))}
                for q in set(all_queries_raw)]


# ─────────────────────────────────────────────
# STEP 4: PAGE COVERAGE SCORING
# ─────────────────────────────────────────────

def score_page_coverage(page_content: str, clusters: list) -> list:
    """
    Score each fan-out cluster against the page content.
    Batches clusters in groups of 10 to avoid max_tokens truncation
    when cluster counts are high (20+).
    """
    if not ANTHROPIC_KEY:
        return clusters

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    # Build scored map — accumulate across batches
    score_map = {}

    # Split into batches of 10
    BATCH_SIZE = 10
    query_list = [{"id": i, "query": c["canonical"], "intent": c.get("intent_type", "Unknown")}
                  for i, c in enumerate(clusters)]
    batches = [query_list[i:i + BATCH_SIZE] for i in range(0, len(query_list), BATCH_SIZE)]

    for batch_num, batch in enumerate(batches):
        scoring_prompt = f"""You are auditing whether a web page adequately covers a set of AI fan-out queries.

PAGE CONTENT (truncated to {MAX_PAGE_CHARS} chars):
---
{page_content}
---

FAN-OUT QUERIES TO SCORE (batch {batch_num + 1} of {len(batches)}):
{json.dumps(batch, indent=2)}

For each query, score coverage:
- "COVERED": Page directly and specifically answers this query with dedicated content
- "PARTIAL": Page mentions the topic but doesn't clearly or completely answer this sub-query
- "MISSING": Page does not address this query at all

Return ONLY a valid JSON array — one object per query in this batch:
[
  {{
    "id": 0,
    "coverage": "COVERED|PARTIAL|MISSING",
    "reason": "one sentence explanation",
    "recommended_fix": "specific suggestion if PARTIAL or MISSING, else null"
  }}
]

Be strict. "Mentioned in passing" = PARTIAL, not COVERED.
Return ONLY the JSON array. No preamble, no explanation."""

        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,  # increased: 10 clusters * ~150 tokens each = ~1500, 4096 gives headroom
                messages=[{"role": "user", "content": scoring_prompt}]
            )
            raw = message.content[0].text.strip()

            # Strip markdown fences
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            # Find JSON array bounds
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                raw = raw[start:end]

            batch_scores = json.loads(raw)
            for s in batch_scores:
                score_map[s["id"]] = s

        except json.JSONDecodeError as e:
            print(f"[Coverage scoring error] Batch {batch_num + 1} JSON parse failed: {e}")
            print(f"  Raw response (first 300 chars): {raw[:300]}")
            # Mark this batch as UNKNOWN — don't fail the whole run
            for item in batch:
                score_map[item["id"]] = {
                    "coverage": "UNKNOWN",
                    "reason": f"Scoring failed for this batch: {e}",
                    "recommended_fix": None
                }
        except Exception as e:
            print(f"[Coverage scoring error] Batch {batch_num + 1}: {e}")
            for item in batch:
                score_map[item["id"]] = {
                    "coverage": "UNKNOWN",
                    "reason": f"Scoring error: {e}",
                    "recommended_fix": None
                }

    # Merge all batch scores back into clusters
    for i, cluster in enumerate(clusters):
        score = score_map.get(i, {})
        cluster["coverage"] = score.get("coverage", "UNKNOWN")
        cluster["reason"] = score.get("reason", "")
        cluster["recommended_fix"] = score.get("recommended_fix", None)

    return clusters


# ─────────────────────────────────────────────
# STEP 5: PRIORITY ASSIGNMENT
# ─────────────────────────────────────────────

PRIORITY_MATRIX = {
    ("MISSING", 3): ("🔴 P1", "Fix immediately"),
    ("MISSING", 2): ("🟠 P2", "Fix this sprint"),
    ("PARTIAL", 3): ("🟠 P2", "Strengthen section"),
    ("MISSING", 1): ("🟡 P3", "Consider adding"),
    ("PARTIAL", 2): ("🟡 P3", "Minor improvement"),
    ("PARTIAL", 1): ("🟡 P3", "Minor improvement"),
    ("COVERED", 3): ("✅ OK", "Keep — no action"),
    ("COVERED", 2): ("✅ OK", "Keep — no action"),
    ("COVERED", 1): ("✅ OK", "Keep — no action"),
    # UNKNOWN = page could not be fetched; treat consensus gaps as high-priority
    # so the report is still useful even without coverage scoring
    ("UNKNOWN", 3): ("🔴 P1*", "Coverage unscored — consensus gap, treat as P1"),
    ("UNKNOWN", 2): ("🟠 P2*", "Coverage unscored — consensus gap, treat as P2"),
    ("UNKNOWN", 1): ("🟡 P3*", "Coverage unscored — single-model gap"),
}

def assign_priority(cluster: dict) -> dict:
    coverage  = cluster.get("coverage", "UNKNOWN")
    consensus = min(cluster.get("consensus_count", 1), 3)
    key = (coverage, consensus)
    priority, action = PRIORITY_MATRIX.get(key, ("⚪ N/A", "Review manually"))
    cluster["priority"]        = priority
    cluster["priority_action"] = action
    return cluster


# ─────────────────────────────────────────────
# STEP 5b: IMPROVEMENT FORECAST
# ─────────────────────────────────────────────

def generate_improvement_forecast(clusters: list) -> dict:
    """
    Deterministic score projection across three fix scenarios.
    No LLM call — uses the same scoring formula as generate_report.

    Scenario A: Fix P1 only  (Missing P1 → Covered)
    Scenario B: Fix P1 + P2  (all P1/P2 → Covered)
    Scenario C: Fix all gaps  (P1 + P2 + P3 → Covered)
    """
    import copy

    total = len(clusters)
    if total == 0:
        return {}

    def calc_score(cl):
        cov = sum(1 for c in cl if c.get("coverage") == "COVERED")
        par = sum(1 for c in cl if c.get("coverage") == "PARTIAL")
        return round((cov * 1.0 + par * 0.5) / len(cl) * 100)

    def simulate(cl, fix_priorities):
        """Return a deep-copied cluster list with target priorities moved to COVERED."""
        sim = copy.deepcopy(cl)
        for c in sim:
            for prefix in fix_priorities:
                if c.get("priority", "").startswith(prefix):
                    c["coverage"] = "COVERED"
        return sim

    p1_gaps = [c for c in clusters if c.get("priority", "").startswith("🔴")]
    p2_gaps = [c for c in clusters if c.get("priority", "").startswith("🟠")]
    p3_gaps = [c for c in clusters if c.get("priority", "").startswith("🟡")]

    current  = calc_score(clusters)
    p1_only  = calc_score(simulate(clusters, ["🔴"]))
    p1_p2    = calc_score(simulate(clusters, ["🔴", "🟠"]))
    all_gaps = calc_score(simulate(clusters, ["🔴", "🟠", "🟡"]))

    return {
        "current":   current,
        "p1_only":   p1_only,
        "p1_p2":     p1_p2,
        "all_gaps":  all_gaps,
        "p1_count":  len(p1_gaps),
        "p2_count":  len(p2_gaps),
        "p3_count":  len(p3_gaps),
        "delta_p1":        p1_only  - current,
        "delta_p1_p2":     p1_p2    - current,
        "delta_all":       all_gaps - current,
    }


# ─────────────────────────────────────────────
# STEP 5c: CONTENT OUTLINE GENERATOR
# ─────────────────────────────────────────────

def generate_content_outlines(clusters: list, keyword: str, url: str,
                               market: str, persona: str,
                               depth: str = "lean") -> list:
    """
    Generate content outlines for P1 and P2 gaps.

    depth='lean'  → H2/H3 structure, key questions, word count, schema (batched, fast)
    depth='full'  → lean + actual draft paragraphs per section (one gap at a time)
    """
    if not ANTHROPIC_KEY:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    target = [c for c in clusters
              if c.get("priority", "").startswith("🔴") or
                 c.get("priority", "").startswith("🟠")]

    if not target:
        return []

    outlines = []

    if depth == "lean":
        # Batch 4 gaps per API call
        BATCH = 4
        batches = [target[i:i + BATCH] for i in range(0, len(target), BATCH)]

        for batch_num, batch in enumerate(batches):
            gaps_payload = [
                {
                    "id": i,
                    "query":    c.get("canonical", ""),
                    "intent":   c.get("intent_type", ""),
                    "coverage": c.get("coverage", ""),
                    "priority": c.get("priority", ""),
                    "reason":   c.get("reason", ""),
                    "fix_hint": c.get("recommended_fix", "")
                }
                for i, c in enumerate(batch)
            ]

            prompt = f"""You are a senior SEO content strategist generating content outlines to close AI search visibility gaps.

AUDIT CONTEXT:
- Keyword: {keyword}
- URL audited: {url}
- Market: {market}
- Persona: {persona}

GAPS TO OUTLINE:
{json.dumps(gaps_payload, indent=2)}

For each gap decide:
- "update_existing_page": adding a section to the current URL fully closes this gap
- "create_new_page": the intent is distinct enough to need its own URL

Return ONLY a valid JSON array — one object per gap, in the same order:
[
  {{
    "id": 0,
    "query": "the fan-out query being addressed",
    "priority": "P1 or P2",
    "action": "update_existing_page" or "create_new_page",
    "page_target": "existing URL path, or suggested new slug e.g. /blog/ai-vs-manual-construction",
    "rationale": "one sentence: why update vs new page",
    "h2": "Exact H2 heading — phrased as the user question or a direct answer, not a vague label",
    "h3s": ["Subheading 1", "Subheading 2", "Subheading 3"],
    "key_questions": ["Specific question this section must answer 1", "Q2", "Q3"],
    "word_count": "150–300",
    "schema": "FAQPage|HowTo|Article|Table|None",
    "schema_rationale": "one sentence explaining why this schema type"
  }}
]

Be specific to the keyword, market, and persona. H2 and H3s should be direct and concrete — not generic content labels.
Return ONLY the JSON array. No preamble."""

            try:
                message = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw = message.content[0].text.strip()
                if "```" in raw:
                    parts = raw.split("```")
                    raw = parts[1].strip()
                    if raw.startswith("json"):
                        raw = raw[4:].strip()
                start = raw.find("[")
                end   = raw.rfind("]") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]
                batch_out = json.loads(raw)
                for i, outline in enumerate(batch_out):
                    if i < len(batch):
                        outline["intent_type"] = batch[i].get("intent_type", "")
                    outlines.append(outline)
                print(f"   ✅ Outlines batch {batch_num + 1}/{len(batches)} done ({len(batch_out)} gaps)")
            except Exception as e:
                print(f"   [Outline error — lean batch {batch_num + 1}] {e}")

    else:  # full depth — one gap at a time
        for idx, c in enumerate(target):
            prompt = f"""You are a senior SEO content strategist and writer generating a detailed content outline with draft copy.

AUDIT CONTEXT:
- Keyword: {keyword}
- URL audited: {url}
- Market: {market}
- Persona: {persona}

GAP TO ADDRESS:
- Fan-out query: {c.get("canonical", "")}
- Intent type:   {c.get("intent_type", "")}
- Coverage:      {c.get("coverage", "")}
- Priority:      {c.get("priority", "")}
- Gap reason:    {c.get("reason", "")}
- Fix hint:      {c.get("recommended_fix", "")}

Return ONLY a valid JSON object:
{{
  "query":        "{c.get("canonical", "")}",
  "priority":     "P1 or P2",
  "action":       "update_existing_page" or "create_new_page",
  "page_target":  "URL to update or new URL slug",
  "rationale":    "one sentence",
  "h2":           "Exact H2 heading text",
  "sections": [
    {{
      "h3":    "Subheading text",
      "draft": "3–5 sentences of specific, expert draft content. Written for the {persona} persona in the {market} market. Concrete and direct — not placeholder copy."
    }}
  ],
  "key_questions":    ["Q1", "Q2", "Q3"],
  "word_count":       "300–500",
  "schema":           "FAQPage|HowTo|Article|Table|None",
  "schema_rationale": "one sentence"
}}

Return ONLY the JSON object."""

            try:
                message = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw = message.content[0].text.strip()
                if "```" in raw:
                    parts = raw.split("```")
                    raw = parts[1].strip()
                    if raw.startswith("json"):
                        raw = raw[4:].strip()
                start = raw.find("{")
                end   = raw.rfind("}") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]
                outline = json.loads(raw)
                outline["intent_type"] = c.get("intent_type", "")
                outlines.append(outline)
                label = c.get("canonical", "")[:55]
                print(f"   ✅ [{idx + 1}/{len(target)}] {label}...")
            except Exception as e:
                print(f"   [Outline error — full #{idx + 1}] {e}")

    return outlines


# ─────────────────────────────────────────────
# STEP 6: GENERATE REPORT
# ─────────────────────────────────────────────

def generate_report(keyword: str, url: str, clusters: list, models_used: list,
                    market: str, persona: str,
                    forecast: dict = None, outlines: list = None) -> str:
    """Generate the markdown Fan-Out Coverage Brief."""

    total = len(clusters)
    covered = sum(1 for c in clusters if c.get("coverage") == "COVERED")
    partial = sum(1 for c in clusters if c.get("coverage") == "PARTIAL")
    missing = sum(1 for c in clusters if c.get("coverage") == "MISSING")
    consensus_2plus = sum(1 for c in clusters if c.get("consensus_count", 0) >= 2)

    # Simple coverage score: weighted
    score = round((covered * 1.0 + partial * 0.5) / total * 100) if total > 0 else 0

    p1 = [c for c in clusters if c.get("priority", "").startswith("🔴")]
    p2 = [c for c in clusters if c.get("priority", "").startswith("🟠")]
    p3 = [c for c in clusters if c.get("priority", "").startswith("🟡")]
    ok = [c for c in clusters if c.get("priority", "").startswith("✅")]

    lines = []
    lines.append(f"# Query Fan-Out Coverage Brief")
    lines.append(f"")
    lines.append(f"**Keyword:** {keyword}  ")
    lines.append(f"**URL:** {url}  ")
    lines.append(f"**Market / Persona:** {market} / {persona}  ")
    lines.append(f"**Models used:** {', '.join(models_used)}  ")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}  ")
    lines.append(f"")

    # Warn if coverage scoring was skipped (all UNKNOWN)
    unscored = sum(1 for c in clusters if c.get("coverage") == "UNKNOWN")
    if unscored == total and total > 0:
        lines.append(f"> ⚠️ **Coverage scoring incomplete** — the page could not be fetched automatically "
                     f"(bot protection / 403). Fan-out clusters and priority assignments are based on "
                     f"consensus scoring only. Priorities marked with `*` are estimated. "
                     f"Rerun with `--page-file page_content.txt` to score coverage accurately.")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Coverage Summary")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Total fan-out clusters | {total} |")
    lines.append(f"| Consensus queries (2+ models) | {consensus_2plus} |")
    lines.append(f"| Fully Covered | {covered} |")
    lines.append(f"| Partial | {partial} |")
    lines.append(f"| Missing | {missing} |")
    lines.append(f"| **Coverage Score** | **{score} / 100** |")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # P1 + P2 gaps
    lines.append(f"## Priority Gaps (P1 + P2)")
    lines.append(f"")
    for c in p1 + p2:
        lines.append(f"### {c['priority']} — {c['canonical']}")
        lines.append(f"- **Intent type:** {c.get('intent_type', 'Unknown')}")
        lines.append(f"- **Appears in:** {', '.join(c.get('models', []))} ({c.get('consensus_count', 1)}/3 models)")
        lines.append(f"- **Coverage:** {c.get('coverage', '?')}")
        lines.append(f"- **Why:** {c.get('reason', '')}")
        if c.get("recommended_fix"):
            lines.append(f"- **Fix:** {c['recommended_fix']}")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # Full scorecard
    lines.append(f"## Full Coverage Scorecard")
    lines.append(f"")
    lines.append(f"| Priority | Fan-Out Query | Intent | Models | Coverage |")
    lines.append(f"|---|---|---|---|---|")
    for c in clusters:
        models_str = " / ".join(c.get("models", []))
        lines.append(f"| {c.get('priority','?')} | {c['canonical']} | {c.get('intent_type','?')} | {models_str} | {c.get('coverage','?')} |")

    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # Action plan
    lines.append(f"## Recommended Actions")
    lines.append(f"")

    if p1:
        lines.append(f"### 🔴 P1 — Fix Immediately")
        for c in p1:
            fix = c.get('recommended_fix') or f"Add dedicated section addressing: {c['canonical']}"
            lines.append(f"- **{c['canonical']}** → {fix}")
        lines.append(f"")

    if p2:
        lines.append(f"### 🟠 P2 — Fix This Sprint")
        for c in p2:
            fix = c.get('recommended_fix') or f"Expand or add section for: {c['canonical']}"
            lines.append(f"- **{c['canonical']}** → {fix}")
        lines.append(f"")

    if p3:
        lines.append(f"### 🟡 P3 — Consider Adding")
        for c in p3:
            lines.append(f"- **{c['canonical']}** ({c.get('intent_type','')})")
        lines.append(f"")

    if ok:
        lines.append(f"### ✅ Already Well Covered")
        for c in ok:
            lines.append(f"- {c['canonical']}")
        lines.append(f"")

    # ── Improvement Forecast
    if forecast:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Improvement Forecast")
        lines.append(f"")
        lines.append(f"> Scores are deterministic projections based on the coverage formula — "
                     f"not traffic estimates. They show AI citation coverage potential if gaps are closed.")
        lines.append(f"")
        lines.append(f"| Scenario | Gaps fixed | Projected score | Δ vs current |")
        lines.append(f"|---|---|---|---|")
        lines.append(f"| **Current state** | — | **{forecast['current']}/100** | — |")
        lines.append(f"| Fix P1 only | {forecast['p1_count']} gaps | **{forecast['p1_only']}/100** | +{forecast['delta_p1']} pts |")
        lines.append(f"| Fix P1 + P2 | {forecast['p1_count'] + forecast['p2_count']} gaps | **{forecast['p1_p2']}/100** | +{forecast['delta_p1_p2']} pts |")
        lines.append(f"| Fix all gaps | {forecast['p1_count'] + forecast['p2_count'] + forecast['p3_count']} gaps | **{forecast['all_gaps']}/100** | +{forecast['delta_all']} pts |")
        lines.append(f"")

    # ── Content Outlines
    if outlines:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Content Outlines")
        lines.append(f"")
        lines.append(f"Structured briefs for every P1 and P2 gap. Each outline is shaped by the "
                     f"specific fan-out sub-query the AI engine is asking — not generic content suggestions.")
        lines.append(f"")

        for i, o in enumerate(outlines, 1):
            priority  = o.get("priority", "")
            action    = o.get("action", "")
            target_pg = o.get("page_target", "")
            h2        = o.get("h2", "")
            h3s       = o.get("h3s", [])
            sections  = o.get("sections", [])  # full depth only
            questions = o.get("key_questions", [])
            wc        = o.get("word_count", "")
            schema    = o.get("schema", "None")
            schema_r  = o.get("schema_rationale", "")
            rationale = o.get("rationale", "")
            query     = o.get("query", "")

            action_label = "✏️ Update existing page" if action == "update_existing_page" else "🆕 Create new page"

            lines.append(f"### {i}. {query}")
            lines.append(f"")
            lines.append(f"**Priority:** {priority} &nbsp;|&nbsp; **Action:** {action_label}  ")
            lines.append(f"**Target:** `{target_pg}`  ")
            if rationale:
                lines.append(f"**Why:** {rationale}  ")
            lines.append(f"")
            lines.append(f"**Suggested H2:** {h2}")
            lines.append(f"")

            if sections:
                # Full depth — H3 + draft
                for s in sections:
                    lines.append(f"#### {s.get('h3', '')}")
                    lines.append(f"")
                    lines.append(f"{s.get('draft', '')}")
                    lines.append(f"")
            elif h3s:
                # Lean depth — H3 list only
                lines.append(f"**Structure:**")
                for h3 in h3s:
                    lines.append(f"- {h3}")
                lines.append(f"")

            if questions:
                lines.append(f"**Must answer:**")
                for q in questions:
                    lines.append(f"- {q}")
                lines.append(f"")

            lines.append(f"**Word count:** {wc} &nbsp;|&nbsp; **Schema:** `{schema}`")
            if schema_r and schema != "None":
                lines.append(f"*{schema_r}*")
            lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*Generated by [query-fanout-auditor](https://github.com/vishsd14/query-fanout-auditor)*")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Multi-model fan-out query auditor for AI search visibility"
    )
    parser.add_argument("--keyword", required=True, help="Primary keyword to audit")
    parser.add_argument("--url", required=True, help="Target page URL")
    parser.add_argument("--market", default="Global", help="Target market/country")
    parser.add_argument("--persona", default="general user", help="Simulated user persona")
    parser.add_argument("--fanouts", type=int, default=20, help="Fan-outs per model")
    parser.add_argument("--output", default=None, help="Save report to file (e.g. report.md)")
    parser.add_argument("--no-filter", action="store_true", dest="no_filter",
                        help="Skip user-intent filter and keep all raw queries")
    parser.add_argument("--outline-depth", choices=["lean", "full"], default="lean",
                        dest="outline_depth",
                        help="Content outline depth: lean=structure only, full=with draft copy (default: lean)")
    parser.add_argument("--no-outline", action="store_true", dest="no_outline",
                        help="Skip content outline generation entirely")
    parser.add_argument("--page-file", default=None, dest="page_file",
                        help="Path to a .txt or .html file containing the page content "
                             "(use when the site blocks automated fetches)")
    parser.add_argument("--page-image", default=None, dest="page_image",
                        help="Path to a screenshot (.png/.jpg/.webp) of the page — "
                             "Claude extracts the content via vision "
                             "(use when the site blocks automated fetches)")
    args = parser.parse_args()

    # ── Validate setup
    if not ANTHROPIC_KEY:
        print("ERROR: ANTHROPIC_API_KEY not found in .env — this is required.")
        sys.exit(1)

    models_used = ["claude"]
    if OPENAI_KEY and HAS_OPENAI:
        models_used.append("gpt4o")
    if PERPLEXITY_KEY:
        models_used.append("perplexity")

    print(f"\n🔍 Query Fan-Out Auditor")
    print(f"   Keyword : {args.keyword}")
    print(f"   URL     : {args.url}")
    print(f"   Market  : {args.market} | Persona: {args.persona}")
    print(f"   Models  : {', '.join(models_used)}")
    print(f"\n{'─'*50}\n")

    # ── Step 1: Fetch page
    # Priority order: --page-image → --page-file → URL fetch
    page_content = ""

    if args.page_image:
        print(f"📄 Extracting page content from screenshot: {args.page_image}")
        page_content = extract_content_from_image(args.page_image)
        if page_content:
            word_count = len(page_content.split())
            print(f"   ✅ {word_count} words extracted via Claude vision")
        else:
            print("   ⚠️  Image extraction returned no content — check the file path and format")

    elif args.page_file:
        try:
            with open(args.page_file, "r", encoding="utf-8") as f:
                raw_file = f.read()
            soup = BeautifulSoup(raw_file, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            page_content = soup.get_text(separator="\n", strip=True)[:MAX_PAGE_CHARS]
            word_count = len(page_content.split())
            print(f"📄 Page content loaded from file: {args.page_file}")
            print(f"   ✅ {word_count} words extracted")
        except Exception as e:
            print(f"📄 Failed to read --page-file: {e}")
            print("   Continuing without page content (coverage scoring will be skipped)")

    else:
        print("📄 Fetching page content...")
        page_content = fetch_page_content(args.url)
        if page_content.startswith("ERROR"):
            print(f"   ⚠️  {page_content}")
            print("")
            print("   ── The site is blocking automated fetches (common with bot protection).")
            print("   ── Provide the page content via one of these options:")
            print(f"   ──")
            print(f"   ──   Option A — Screenshot (easiest):")
            print(f"   ──   Chrome DevTools → Cmd+Shift+P → 'Capture full size screenshot' → save as page.png")
            print(f"   ──   python3 fanout_audit.py ... --page-image page.png")
            print(f"   ──")
            print(f"   ──   Option B — Text file:")
            print(f"   ──   DevTools Console → copy(document.body.innerText) → paste into page.txt")
            print(f"   ──   python3 fanout_audit.py ... --page-file page.txt")
            print("")
            print("   Continuing with fan-out generation only (no coverage scoring)...")
            page_content = ""
        else:
            word_count = len(page_content.split())
            print(f"   ✅ Page fetched ({word_count} words extracted)")

    # ── Step 2: Generate fan-outs
    raw_results = {}

    print("\n🤖 Generating fan-out queries...")

    print("   → Claude...")
    claude_fanouts = generate_fanouts_claude(args.keyword, args.market, args.persona, args.fanouts)
    if claude_fanouts:
        raw_results["claude"] = claude_fanouts
        print(f"     ✅ {len(claude_fanouts)} queries")

    if "gpt4o" in models_used:
        print("   → GPT-4o...")
        openai_fanouts = generate_fanouts_openai(args.keyword, args.market, args.persona, args.fanouts)
        if openai_fanouts:
            raw_results["gpt4o"] = openai_fanouts
            print(f"     ✅ {len(openai_fanouts)} queries")

    if "perplexity" in models_used:
        print("   → Perplexity...")
        pplx_fanouts = generate_fanouts_perplexity(args.keyword, args.market, args.persona, args.fanouts)
        if pplx_fanouts:
            raw_results["perplexity"] = pplx_fanouts
            print(f"     ✅ {len(pplx_fanouts)} queries")

    total_raw = sum(len(v) for v in raw_results.values())
    print(f"\n   Total raw queries: {total_raw} across {len(raw_results)} model(s)")

    # ── Step 2b: User-intent filter
    if not args.no_filter:
        print("\n🧹 Filtering non-user-intent queries...")
        raw_results = filter_user_intent_queries(raw_results, args.keyword)
        total_filtered = sum(len(v) for v in raw_results.values())
        kept = total_raw - total_filtered
        if kept > 0:
            print(f"   ✅ {total_filtered} queries kept ({kept} removed)")
        else:
            print(f"   ✅ All {total_filtered} queries passed — none removed")
    else:
        print("\n   ⏭️  User-intent filter skipped (--no-filter)")

    # ── Step 3: Consensus clustering
    print("\n🔗 Clustering by semantic intent...")
    clusters = compute_consensus(raw_results)
    print(f"   ✅ {len(clusters)} unique clusters identified")

    # ── Step 4: Coverage scoring
    if page_content:
        print("\n📊 Scoring page coverage...")
        clusters = score_page_coverage(page_content, clusters)
        print(f"   ✅ Coverage scored")
    else:
        print("\n⚠️  Skipping coverage scoring (no page content)")
        for c in clusters:
            c["coverage"] = "UNKNOWN"
            c["reason"] = "Page could not be fetched"
            c["recommended_fix"] = None

    # ── Step 5: Assign priorities
    clusters = [assign_priority(c) for c in clusters]

    # ── Step 5b: Improvement forecast (deterministic — no API call)
    print("\n📈 Calculating improvement forecast...")
    forecast = generate_improvement_forecast(clusters)
    if forecast:
        print(f"   Current: {forecast['current']}/100 → "
              f"P1 fix: {forecast['p1_only']} → "
              f"P1+P2: {forecast['p1_p2']} → "
              f"All: {forecast['all_gaps']}")

    # ── Step 5c: Content outlines
    outlines = []
    if not args.no_outline:
        p1_count = forecast.get("p1_count", 0)
        p2_count = forecast.get("p2_count", 0)
        gap_count = p1_count + p2_count
        depth_label = f"{args.outline_depth} depth"
        print(f"\n✍️  Generating content outlines ({gap_count} gaps · {depth_label})...")
        outlines = generate_content_outlines(
            clusters=clusters,
            keyword=args.keyword,
            url=args.url,
            market=args.market,
            persona=args.persona,
            depth=args.outline_depth
        )
        print(f"   ✅ {len(outlines)} outlines generated")
    else:
        print("\n   ⏭️  Content outlines skipped (--no-outline)")

    # ── Step 6: Generate report
    print("\n📝 Generating report...")
    report = generate_report(
        keyword=args.keyword,
        url=args.url,
        clusters=clusters,
        models_used=models_used,
        market=args.market,
        persona=args.persona,
        forecast=forecast,
        outlines=outlines
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"   ✅ Report saved to: {args.output}")
    else:
        print("\n" + "═"*60 + "\n")
        print(report)

    # Always save raw JSON for Claude Code to read
    raw_json_path = args.output.replace(".md", "_raw.json") if args.output else "fanout_raw.json"
    with open(raw_json_path, "w") as f:
        json.dump({"keyword": args.keyword, "url": args.url,
                   "models": models_used, "clusters": clusters}, f, indent=2)
    print(f"\n   📁 Raw data saved to: {raw_json_path}")
    print(f"\n{'═'*60}\n✅ Done.\n")


if __name__ == "__main__":
    main()
