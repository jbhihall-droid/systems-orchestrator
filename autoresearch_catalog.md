# Autoresearch: Catalog Optimization

## Goal
Improve tool matching accuracy by optimizing catalog.json descriptions, 
use_when, and do_not_use_when fields. Measured by test_analyze.py pass rate.

## How to Run

```bash
cd ~/.claude/mcp-servers/systems-orchestrator
# Use the autoresearch-agent skill with:
#   target: catalog.json
#   eval:   python3 test_analyze.py 2>&1 | tail -1 | grep -oP '\d+/\d+' | head -1
#   metric: maximize the CHECKS passed count (currently 95/111)
```

## What the Eval Measures

test_analyze.py runs 26 prompts through the analyze_task pipeline and checks:
- Element detection accuracy (does the right element type get detected?)
- Complexity classification (DIRECT/LIGHT/FULL)
- Reasoning level (haiku/sonnet/opus)  
- Tool category matching (do top-3 tools include the expected category?)

## Optimization Surfaces (in priority order)

1. **use_when / do_not_use_when** — explicit routing hints that override keyword matching
   - Currently only 44/181 catalog entries have these fields
   - Adding them to the remaining 137 entries is the highest-value change
   
2. **description** — free text that feeds keyword matching in _score()
   - More specific descriptions = better word overlap with queries
   - Example: "network scanner" → "TCP/UDP port scanner for host discovery and service detection"

3. **capabilities** — array of capability strings, +4.0 per match in _score()
   - Should use specific terms from real queries, not abstract categories
   - Example: ["port-scan"] → ["port-scan", "open-port-detection", "service-fingerprint"]

4. **category** — controls element-type gating in _score()
   - Wrong category = tool gets 0.1x penalty for mismatched element types
   - Some tools have ambiguous categories (e.g., "development/general" matches everything weakly)

## Currently Failing Tool Matches (from test_analyze.py)

These are the specific tool_cat checks that fail — the catalog needs better entries in these categories:

| Expected Category | Failing Prompt | Issue |
|---|---|---|
| development/frontend | "react dashboard with real-time data" | Frontend tools don't rank for data_source elements |
| development/backend | "REST API endpoint" | Backend tools don't rank for service+host combo |
| data/scraping | "scrape product prices from amazon" | Scraping tools don't rank when complexity is DIRECT |
| data/analysis | "analyze this CSV file" | pandas/duckdb don't rank for file elements |
| security/scanning | "full security audit of web application" | Security scanners don't rank for frontend+code elements |
| security/defense | "check if fail2ban is blocking" | fail2ban doesn't rank for host elements |
| infra/ | "docker compose with postgres, redis, nginx" | Infra tools don't rank for container+database combo |
| development/android | "debug why android app crashes" | adb doesn't rank for code elements |
| infra/scheduling | "cron job that sends daily email" | cron/celery don't rank for scheduler elements |
| infra/notification | "cron job that sends daily email" | ntfy/nodemailer don't rank for notifier elements |

## Strategy

For each failing case:
1. Read the prompt and identify which tool SHOULD rank
2. Check if that tool has use_when matching the prompt's keywords
3. If not, add use_when phrases that match the query
4. Check if the tool's category matches the detected element type
5. If not, verify _ELEMENT_CATEGORIES in server.py maps the element type to that category
6. Run test_analyze.py to verify improvement
7. If score improved, keep. If not, revert.

## Guard Rails

- Do NOT change test_analyze.py expectations — the test is the source of truth
- Do NOT change server.py scoring logic — only change catalog data
- Do NOT remove existing use_when/do_not_use_when — only add new ones
- Each change should target ONE failing test case at a time
