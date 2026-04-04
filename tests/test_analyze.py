#!/usr/bin/env python3
"""Test harness for analyze_task pipeline.

Runs prompts with expected outcomes through the system and reports:
- Element detection accuracy
- Complexity classification accuracy
- Reasoning level accuracy
- Tool match relevance
- Gap detection

Usage:
    python3 test_analyze.py             # summary only
    python3 test_analyze.py --verbose   # show every check
    python3 test_analyze.py --failures  # show only failures
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.analyzer import derive_system_model, classify_complexity, classify_reasoning_level, score_tool
from lib.discovery import build_index

# ── Test Cases ─────────────────────────────────────────────────────────
# Each case: prompt, expected complexity, expected reasoning, expected element types,
#            expected tool categories (at least one tool should be from these categories),
#            optional: expected_subsystems, expected_flow_count

TEST_CASES = [
    # ── Web/Frontend ──────────────────────────────────────────────────
    {
        "prompt": "create a react dashboard with charts showing real-time sensor data",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["frontend", "data_source"],
        "expect_tool_categories": ["development/frontend"],
    },
    {
        "prompt": "redesign this ui and make it more user friendly",
        "expect_complexity": "FULL",
        "expect_reasoning": "opus",
        "expect_elements": ["frontend"],
        "expect_tool_categories": ["development/frontend"],
    },
    {
        "prompt": "fix the CSS padding on the login button",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "haiku",
        "expect_elements": ["frontend"],
        "expect_tool_categories": [],  # too simple for tool matching
    },
    {
        "prompt": "build a responsive landing page with tailwind and dark mode toggle",
        "expect_complexity": "LIGHT",
        "expect_reasoning": "sonnet",
        "expect_elements": ["frontend"],
        "expect_tool_categories": ["development/frontend"],
    },

    # ── Backend/API ───────────────────────────────────────────────────
    {
        "prompt": "create an index thats more efficient and wire it up to an api so it can talk to my front end server",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["database", "service", "frontend"],
        "expect_tool_categories": ["infra/web", "development/backend", "data/database"],
    },
    {
        "prompt": "add a REST API endpoint for user registration with JWT authentication",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "sonnet",
        "expect_elements": ["service"],
        "expect_tool_categories": ["development/backend"],
    },
    {
        "prompt": "design the microservices architecture for our payment processing system",
        "expect_complexity": "FULL",
        "expect_reasoning": "opus",
        "expect_elements": ["service"],
        "expect_tool_categories": [],
    },

    # ── Data/Scraping ─────────────────────────────────────────────────
    {
        "prompt": "create a system that finds all italian restaurants near me and notifies me when there is a special on",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["data_source", "notifier"],
        "expect_tool_categories": ["data/scraping"],
    },
    {
        "prompt": "scrape product prices from amazon and store them in a database",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["data_source", "database"],
        "expect_tool_categories": ["data/scraping", "data/database"],
    },
    {
        "prompt": "analyze this CSV file and show me the top 10 customers by revenue",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "sonnet",
        "expect_elements": ["file"],
        "expect_tool_categories": ["data/analysis"],
    },

    # ── Security ──────────────────────────────────────────────────────
    {
        "prompt": "scan the network for open ports and identify running services",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["network", "service"],
        "expect_tool_categories": ["security/scanning"],
    },
    {
        "prompt": "perform a full security audit of the web application",
        "expect_complexity": "FULL",
        "expect_reasoning": "opus",
        "expect_elements": ["service", "code"],
        "expect_tool_categories": ["security/scanning", "security/web"],
    },
    {
        "prompt": "check if fail2ban is blocking the right IPs",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "haiku",
        "expect_elements": [],
        "expect_tool_categories": ["security/defense"],
    },

    # ── Infrastructure ────────────────────────────────────────────────
    {
        "prompt": "set up a docker compose stack with postgres, redis, and nginx reverse proxy",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["container", "database", "network"],
        "expect_tool_categories": ["infra/"],
    },
    {
        "prompt": "deploy this app to a kubernetes cluster with auto-scaling",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["container"],
        "expect_tool_categories": ["infra/containers"],
    },

    # ── Mobile ────────────────────────────────────────────────────────
    {
        "prompt": "debug why the android app crashes on startup",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "haiku",
        "expect_elements": ["code"],
        "expect_tool_categories": ["development/android"],
    },

    # ── ML/Data Science ───────────────────────────────────────────────
    {
        "prompt": "fine-tune a language model on our customer support tickets",
        "expect_complexity": "FULL",
        "expect_reasoning": "opus",
        "expect_elements": ["data_source"],
        "expect_tool_categories": [],
    },
    {
        "prompt": "create a RAG pipeline that answers questions from our documentation",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["database", "file"],
        "expect_tool_categories": [],
    },

    # ── Simple/Trivial ────────────────────────────────────────────────
    {
        "prompt": "rename variable foo to bar",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "haiku",
        "expect_elements": ["code"],
        "expect_tool_categories": [],
    },
    {
        "prompt": "add an import for datetime at the top of utils.py",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "sonnet",
        "expect_elements": ["file"],
        "expect_tool_categories": [],
    },
    {
        "prompt": "run the test suite and fix any failures",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "sonnet",
        "expect_elements": ["code"],
        "expect_tool_categories": ["development/testing"],
    },

    # ── Edge Cases ────────────────────────────────────────────────────
    {
        "prompt": "",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "sonnet",
        "expect_elements": [],
        "expect_tool_categories": [],
    },
    {
        "prompt": "do the thing",
        "expect_complexity": "DIRECT",
        "expect_reasoning": "sonnet",
        "expect_elements": [],
        "expect_tool_categories": [],
    },
    {
        "prompt": "build a complete e-commerce platform from scratch with user accounts, product catalog, shopping cart, payment processing via Stripe, email notifications, admin dashboard, and deploy it to AWS with CI/CD",
        "expect_complexity": "FULL",
        "expect_reasoning": "opus",
        "expect_elements": ["frontend", "database", "service", "notifier"],
        "expect_tool_categories": [],
    },

    # ── Scheduling/Notification ───────────────────────────────────────
    {
        "prompt": "set up a cron job that sends a daily email report of system health",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["scheduler", "notifier"],
        "expect_tool_categories": ["infra/scheduling", "infra/notification"],
    },
    {
        "prompt": "create a slack bot that alerts when the build fails",
        "expect_complexity": "FULL",
        "expect_reasoning": "sonnet",
        "expect_elements": ["notifier"],
        "expect_tool_categories": [],
    },
]


# ── Runner ─────────────────────────────────────────────────────────────

def run_test(case: dict) -> dict:
    """Run a single test case and return results."""
    prompt = case["prompt"]
    model = derive_system_model(prompt)
    elements = model["elements"]
    # v2 uses "actions" (not "actions_needed"); each action has "verb" and "matched_keywords"
    actions = model["actions"]
    # v2 returns flows directly; no subsystems field
    flows = model.get("flows", [])
    # v2 has no subsystems — pass empty list to classify_complexity
    subsystems: list[str] = []

    complexity = classify_complexity(prompt, elements, actions, subsystems, flows)
    reasoning = classify_reasoning_level(prompt)

    detected_types = [e["type"] for e in elements]

    # Score tools — for each action × element type combo, find top tools.
    # This mirrors what analyze_task does: match tools per element, not just per action.
    index = build_index()
    tool_categories_found: list[str] = []
    etypes_to_check = detected_types if detected_types else [""]
    verbs_to_check = [a.get("verb", "") for a in actions] if actions else [""]

    for verb in verbs_to_check:
        for elem_type in etypes_to_check:
            query = f"{verb} {elem_type} {prompt[:50]}"
            scored = sorted(
                [(s, c) for c in index if (s := score_tool(c, query, verb, elem_type)) > 0],
                key=lambda x: -x[0],
            )[:3]
            for _, c in scored:
                cat = c.get("category", "") or (c.get("categories") or [""])[0]
                if cat:
                    tool_categories_found.append(cat)

    # Check results
    checks = {}

    # Complexity
    checks["complexity"] = complexity == case["expect_complexity"]

    # Reasoning
    checks["reasoning"] = reasoning == case["expect_reasoning"]

    # Elements: every expected type should be detected
    for etype in case["expect_elements"]:
        checks[f"element:{etype}"] = etype in detected_types

    # Tool categories: at least one expected category should appear in top-3 tools
    for cat_prefix in case.get("expect_tool_categories", []):
        found = any(tc.startswith(cat_prefix.rstrip("/")) for tc in tool_categories_found)
        checks[f"tool_cat:{cat_prefix}"] = found

    return {
        "prompt": prompt[:60] + ("..." if len(prompt) > 60 else ""),
        "checks": checks,
        "details": {
            "complexity": complexity,
            "reasoning": reasoning,
            "elements": detected_types,
            "subsystems": subsystems,
            "tool_categories": list(set(tool_categories_found)),
            "flows": len(flows),
        },
        "expected": {
            "complexity": case["expect_complexity"],
            "reasoning": case["expect_reasoning"],
            "elements": case["expect_elements"],
        },
    }


def main():
    verbose = "--verbose" in sys.argv
    failures_only = "--failures" in sys.argv

    results = [run_test(case) for case in TEST_CASES]

    total_checks = 0
    passed_checks = 0
    total_cases = len(results)
    passed_cases = 0
    failures = []

    for r in results:
        case_pass = all(r["checks"].values())
        case_checks = len(r["checks"])
        case_passed = sum(1 for v in r["checks"].values() if v)
        total_checks += case_checks
        passed_checks += case_passed

        if case_pass:
            passed_cases += 1

        if verbose or (failures_only and not case_pass) or (not failures_only and not verbose):
            if not case_pass or verbose:
                status = "PASS" if case_pass else "FAIL"
                print(f"\n{'v' if case_pass else 'x'} [{status}] {r['prompt']}")
                if not case_pass or verbose:
                    d = r["details"]
                    print(f"    Got:      complexity={d['complexity']}  reasoning={d['reasoning']}  "
                          f"elements={d['elements']}  flows={d['flows']}  subsystems={d['subsystems']}")
                    print(f"    Expected: complexity={r['expected']['complexity']}  "
                          f"reasoning={r['expected']['reasoning']}  elements={r['expected']['elements']}")
                    if d["tool_categories"]:
                        print(f"    Tools:    {d['tool_categories']}")
                    for check_name, check_result in r["checks"].items():
                        if not check_result:
                            print(f"    FAILED:   {check_name}")

        if not case_pass:
            failures.append(r)

    print(f"\n{'='*60}")
    print(f"CASES:  {passed_cases}/{total_cases} passed ({100*passed_cases/total_cases:.0f}%)")
    print(f"CHECKS: {passed_checks}/{total_checks} passed ({100*passed_checks/total_checks:.0f}%)")

    if failures:
        print(f"\nFAILED CASES ({len(failures)}):")
        for f in failures:
            failed = [k for k, v in f["checks"].items() if not v]
            print(f"  x {f['prompt']}")
            print(f"    Failed: {', '.join(failed)}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
