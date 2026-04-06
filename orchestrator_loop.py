#!/usr/bin/env python3
"""Systems Orchestrator v2 — Execution Loop

Polls unblocked tasks from the ledger and dispatches them through
the agent pipeline:

  DIRECT: executor only
  LIGHT:  executor → verifier
  FULL:   researcher → planner → executor → verifier → reviewer

Routes between Claude CLI (reasoning) and Codex CLI (code generation).
Max 2 rework cycles before escalation.

Usage:
    python3 orchestrator_loop.py [--project-dir DIR] [--poll SECONDS] [--dept DEPT] [--once]
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from lib.analyzer import (
    derive_system_model, classify_complexity, classify_reasoning_level,
    score_and_rank,
)
from lib.discovery import build_index
from lib.dispatch import (
    craft_worker_prompt, craft_qa_prompt, craft_researcher_prompt,
    craft_planner_prompt, craft_manager_prompt,
    execute_dispatch, route_task_to_model, QA_LEVEL_DOWN,
)
from lib.ledger import (
    get_unblocked_tasks, get_task, get_project_goal,
    submit_worker_report, submit_qa_report, submit_manager_review,
    record_tool_outcome, log_failure,
)

MAX_REWORK = 2
POLL_INTERVAL = 10


# ── Pipeline steps ───────────────────────────────────────────────────────

def _parse_json_safe(text: str) -> dict | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _step_researcher(project_dir: str, playbook_dir: str, task_id: str, task_content: str, goal: str) -> str:
    """Research phase: gather context for planning."""
    print(f"  [researcher] Dispatching research for {task_id}...")
    packet = craft_researcher_prompt(task_id, task_content, playbook_dir, goal)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [researcher] Done ({len(output)} chars)")
    return output


def _step_planner(project_dir: str, playbook_dir: str, task_id: str, task_content: str, goal: str) -> str:
    """Planning phase: create execution plan."""
    print(f"  [planner] Creating plan for {task_id}...")
    packet = craft_planner_prompt(task_id, task_content, playbook_dir, goal)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [planner] Done ({len(output)} chars)")
    return output


def _step_worker(project_dir: str, playbook_dir: str, task_id: str, task_content: str, reasoning_level: str) -> str:
    """Execution: do the work at the given reasoning level."""
    print(f"  [worker] Executing {task_id} at {reasoning_level}...")
    packet = craft_worker_prompt(task_id, task_content, playbook_dir, reasoning_level)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [worker] Done ({len(output)} chars)")
    submit_worker_report(project_dir, task_id, output)
    return output


def _step_qa(project_dir: str, playbook_dir: str, task_id: str, task_content: str,
             worker_report: str, reasoning_level: str) -> tuple[str, float]:
    """QA: verify the work at a stepped-down reasoning level."""
    # Pass the WORKER's level — craft_qa_prompt handles the step-down internally
    qa_level = QA_LEVEL_DOWN.get(reasoning_level, reasoning_level)
    print(f"  [qa] Verifying {task_id} at {qa_level} (stepped from {reasoning_level})...")
    packet = craft_qa_prompt(task_id, task_content, worker_report, playbook_dir, reasoning_level)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [qa] Done ({len(output)} chars)")

    # Extract score from QA result
    score = _extract_qa_score(output)
    submit_qa_report(project_dir, task_id, output, score)
    return output, score


def _step_manager(project_dir: str, task_id: str, task_content: str,
                  worker_report: str, qa_report: str, rework_count: int, goal: str) -> str:
    """Manager review: VERIFIED / REWORK / ESCALATED."""
    print(f"  [manager] Reviewing {task_id} (rework #{rework_count})...")
    packet = craft_manager_prompt(task_id, task_content, worker_report, qa_report, rework_count, goal)
    result = execute_dispatch(packet)
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    print(f"  [manager] Done")

    verdict = _extract_verdict(output)
    rework_items = _extract_rework_items(output) if verdict == "REWORK" else None

    # If REWORK, log a failure before submitting review (gate enforcement)
    if verdict == "REWORK":
        log_failure(project_dir, task_id, "manager_review", "pass", "rework_needed", "major")

    submit_manager_review(project_dir, task_id, verdict, output, rework_items)
    print(f"  [manager] Verdict: {verdict}")
    return verdict


def _extract_qa_score(qa_text: str) -> float:
    """Best-effort extraction of a QA score from the text."""
    # Try "Score: 0.9" or "8/10" patterns
    m = re.search(r'[Ss]core[:\s]+(\d+\.?\d*)\s*/\s*(\d+)', qa_text)
    if m:
        return float(m.group(1)) / float(m.group(2))
    m = re.search(r'[Ss]core[:\s]+(\d+\.?\d*)', qa_text)
    if m:
        val = float(m.group(1))
        return val if val <= 1.0 else val / 10.0
    if 'pass' in qa_text.lower() and 'fail' not in qa_text.lower():
        return 0.9
    return 0.5


def _extract_verdict(review_text: str) -> str:
    """Extract VERIFIED/REWORK/ESCALATED from manager text."""
    text = review_text.upper()
    if "VERIFIED" in text:
        return "VERIFIED"
    if "REWORK" in text:
        return "REWORK"
    if "ESCALATED" in text or "ESCALATE" in text:
        return "ESCALATED"
    return "VERIFIED"


def _extract_rework_items(text: str) -> list[str]:
    """Best-effort extraction of rework items."""
    items = re.findall(r'[-*]\s+(.+)', text)
    return items[:5] if items else ["Review and fix issues noted in QA report"]


# ── Main Pipeline ────────────────────────────────────────────────────────

def run_task_pipeline(project_dir: str, playbook_dir: str, task_id: str, index: list) -> str:
    """Run a task through the full pipeline based on its complexity."""
    task_content = get_task(project_dir, task_id)
    parsed = _parse_json_safe(task_content)
    if parsed and "error" in parsed:
        print(f"  ERROR: {parsed['error']}")
        return "ERROR"

    goal = get_project_goal(project_dir) or "Complete the task"

    # Extract task description for analysis
    desc_match = re.search(r'## Description\n(.+?)(?:\n##|\Z)', task_content, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else task_content[:500]

    # Analyze complexity
    model = derive_system_model(description)
    complexity = classify_complexity(description, model["elements"], model["actions"], flows=model["flows"])
    reasoning = classify_reasoning_level(description)

    print(f"  Complexity: {complexity} | Reasoning: {reasoning}")

    rework_count = 0
    while rework_count <= MAX_REWORK:
        if complexity == "DIRECT":
            worker_result = _step_worker(project_dir, playbook_dir, task_id, task_content, reasoning)
            return "VERIFIED"

        elif complexity == "LIGHT":
            worker_result = _step_worker(project_dir, playbook_dir, task_id, task_content, reasoning)
            qa_result, qa_score = _step_qa(project_dir, playbook_dir, task_id, task_content, worker_result, reasoning)
            if qa_score >= 0.7:
                submit_manager_review(project_dir, task_id, "VERIFIED", "QA passed", None)
                return "VERIFIED"
            verdict = _step_manager(project_dir, task_id, task_content, worker_result, qa_result, rework_count, goal)

        else:  # FULL
            if rework_count == 0:
                research = _step_researcher(project_dir, playbook_dir, task_id, task_content, goal)
                plan = _step_planner(project_dir, playbook_dir, task_id, task_content + "\n\n## Research\n" + research, goal)
                enriched_content = task_content + "\n\n## Research\n" + research + "\n\n## Plan\n" + plan
            else:
                enriched_content = task_content

            worker_result = _step_worker(project_dir, playbook_dir, task_id, enriched_content, reasoning)
            qa_result, qa_score = _step_qa(project_dir, playbook_dir, task_id, enriched_content, worker_result, reasoning)
            verdict = _step_manager(project_dir, task_id, enriched_content, worker_result, qa_result, rework_count, goal)

        if verdict == "VERIFIED":
            return "VERIFIED"
        elif verdict == "ESCALATED":
            print(f"  ESCALATED — needs human attention")
            return "ESCALATED"
        elif verdict == "REWORK":
            rework_count += 1
            print(f"  REWORK #{rework_count}/{MAX_REWORK}")
            if rework_count > MAX_REWORK:
                print(f"  Max rework reached — escalating")
                submit_manager_review(project_dir, task_id, "ESCALATED",
                                      f"Max rework ({MAX_REWORK}) exceeded", None)
                return "ESCALATED"
            # Re-read task (may have updated content)
            task_content = get_task(project_dir, task_id)
        else:
            return verdict

    return "ESCALATED"


# ── Poll Loop ────────────────────────────────────────────────────────────

def poll_loop(project_dir: str, playbook_dir: str, poll_seconds: int, dept: str | None, once: bool):
    """Main loop: find unblocked tasks, dispatch through pipeline."""
    print("=" * 60)
    print("  Systems Orchestrator v2 — Execution Loop")
    print(f"  Project: {project_dir}")
    print(f"  Poll: every {poll_seconds}s" + (" (single run)" if once else ""))
    if dept:
        print(f"  Department filter: {dept}")
    print("=" * 60)

    index = build_index()
    print(f"  Capability index: {len(index)} tools loaded")

    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- Cycle {cycle} ---")

        tasks_json = get_unblocked_tasks(project_dir, dept)
        parsed = _parse_json_safe(tasks_json)
        if not parsed or "error" in parsed:
            print(f"  No ledger found or error: {tasks_json[:200]}")
            if once:
                break
            time.sleep(poll_seconds)
            continue

        tasks = parsed.get("unblocked", [])
        if not tasks:
            print("  No unblocked tasks. Waiting...")
            if once:
                break
            time.sleep(poll_seconds)
            continue

        for task_info in tasks:
            task_id = task_info["task_id"] if isinstance(task_info, dict) else str(task_info)
            print(f"\n  Processing: {task_id}")
            try:
                result = run_task_pipeline(project_dir, playbook_dir, task_id, index)
                print(f"  Result: {result}")
                record_tool_outcome(
                    project_dir, "orchestrator_pipeline", task_id,
                    "execute", result == "VERIFIED",
                    f"complexity pipeline completed with {result}",
                )
            except Exception as e:
                print(f"  EXCEPTION: {e}")
                record_tool_outcome(
                    project_dir, "orchestrator_pipeline", task_id,
                    "execute", False, str(e),
                )

        if once:
            break
        time.sleep(poll_seconds)


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Systems Orchestrator v2 — Execution Loop")
    parser.add_argument("--project-dir", default=str(Path.cwd()),
                        help="Project directory (default: cwd)")
    parser.add_argument("--poll", type=int, default=POLL_INTERVAL,
                        help=f"Poll interval in seconds (default: {POLL_INTERVAL})")
    parser.add_argument("--dept", default=None,
                        help="Process only this department")
    parser.add_argument("--once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--playbook-dir", default=str(SERVER_DIR / "playbooks"),
                        help="Path to playbook directory")
    args = parser.parse_args()

    poll_loop(args.project_dir, args.playbook_dir, args.poll, args.dept, args.once)


if __name__ == "__main__":
    main()
