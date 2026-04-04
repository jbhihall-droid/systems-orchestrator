#!/usr/bin/env python3
"""Identifies catalog entries that need better use_when/do_not_use_when fields.

Runs test_analyze.py internally and maps failures to specific catalog entries
that should be updated. Use as input for autoresearch or manual optimization.

Usage: python3 optimize_catalog.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.analyzer import derive_system_model, classify_complexity, classify_reasoning_level, score_tool
from lib.discovery import build_index

# The failing tool_cat checks from test_analyze.py
FAILING_MATCHES = [
    {"query": "react dashboard real-time sensor data", "element_type": "frontend", "want_cat": "development/frontend"},
    {"query": "REST API endpoint user registration JWT", "element_type": "service", "want_cat": "development/backend"},
    {"query": "scrape product prices amazon store database", "element_type": "data_source", "want_cat": "data/scraping"},
    {"query": "analyze CSV file top customers revenue", "element_type": "file", "want_cat": "data/analysis"},
    {"query": "security audit web application", "element_type": "code", "want_cat": "security/scanning"},
    {"query": "fail2ban blocking IPs", "element_type": "host", "want_cat": "security/defense"},
    {"query": "docker compose postgres redis nginx", "element_type": "container", "want_cat": "infra/"},
    {"query": "android app crashes startup debug", "element_type": "code", "want_cat": "development/android"},
    {"query": "cron job daily email report", "element_type": "scheduler", "want_cat": "infra/scheduling"},
    {"query": "slack alert build fails notification", "element_type": "notifier", "want_cat": "infra/notification"},
]


def main():
    index = build_index()

    catalog_path = Path(__file__).parent / "catalog" / "catalog.json"
    if not catalog_path.exists():
        # Fallback to tool-catalog MCP catalog
        catalog_path = Path.home() / ".claude" / "mcp-servers" / "tool-catalog" / "catalog.json"

    if catalog_path.exists():
        with open(catalog_path) as f:
            raw = json.load(f)
        catalog = raw if isinstance(raw, list) else raw.get("tools", raw.get("entries", []))
    else:
        print(f"Warning: catalog not found at {catalog_path}, using index only")
        catalog = index

    catalog_by_name = {e["name"]: e for e in catalog}

    print("=== Catalog Optimization Report ===\n")

    for case in FAILING_MATCHES:
        query = case["query"]
        want_cat = case["want_cat"]
        elem_type = case["element_type"]

        # Find what currently ranks — v2 score_tool signature:
        #   score_tool(tool, query, action_verb="", element_type="", tool_outcomes=None)
        scored = sorted(
            [(s, c) for c in index if (s := score_tool(c, query, None, elem_type)) > 0],
            key=lambda x: -x[0]
        )[:5]

        # Find tools from the wanted category
        # v2 index uses "categories" (list); v1 catalog uses "category" (string)
        target_tools = [
            c for c in catalog
            if c.get("category", "").startswith(want_cat.rstrip("/"))
            or any(cat.startswith(want_cat.rstrip("/")) for cat in c.get("categories", []))
        ]

        print(f"Query: {query}")
        print(f"Want:  {want_cat} tools for element_type={elem_type}")
        print(f"Top 3: {[(c['name'], round(s,1), c.get('category') or (c.get('categories') or [''])[0]) for s, c in scored[:3]]}")

        # Check if any target tools have use_when
        missing_use_when = [t for t in target_tools if not t.get("use_when")]
        if missing_use_when:
            print(f"FIX:   {len(missing_use_when)} {want_cat} tools lack use_when: {[t['name'] for t in missing_use_when[:5]]}")

        # Check if target tools would score better with use_when
        best_target = None
        for t in target_tools:
            s = score_tool(t, query, None, elem_type)
            if best_target is None or s > best_target[0]:
                best_target = (s, t["name"])
        if best_target:
            print(f"Best target tool: {best_target[1]} scores {best_target[0]:.1f} (needs >= 8.0 for top-3)")

        print()


if __name__ == "__main__":
    main()
