#!/usr/bin/env python3
"""Systems Orchestrator v2 — MCP server with interactive onboarding,
multi-model dispatch, and tool-level outcome learning.

Improvements over v1:
- Interactive goal onboarding with dry humor personality
- Two-model routing: Claude (reasoning) + Codex (execution)
- All MCP servers integrated: sequential-thinking, semgrep, exa, duckdb, memory, etc.
- VS Code MCP awareness: Playwright, Serena, GitHub, HuggingFace, Pylance, Azure
- Tool-level outcome learning (not just department-level)
- Skill integration: 21 skills discoverable and routable
- Agent subagent dispatch with context isolation
- Gate enforcement for QA workflow

Run: python3 server.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

# Add lib to path
SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from lib.onboarding import OnboardingFlow, GoalAssessment
from lib.analyzer import (
    ELEMENT_TYPES, ACTIONS,
    derive_system_model, classify_complexity, classify_reasoning_level,
    score_tool, score_and_rank,
    generate_llm_decomposition_prompt, generate_llm_tool_selection_prompt,
)
from lib.discovery import build_index, get_index_stats, query_index
from lib.dispatch import (
    MODELS, AGENT_ROUTING, QA_LEVEL_DOWN,
    get_available_models, route_task_to_model,
    craft_worker_prompt, craft_qa_prompt, craft_researcher_prompt,
    craft_planner_prompt, craft_manager_prompt,
)
from lib.ledger import (
    DEPARTMENTS, TASK_SIZES,
    create_project_ledger as _create_project_ledger,
    create_task as _create_task,
    get_task as _get_task,
    get_project_goal as _get_project_goal,
    get_outcomes as _get_outcomes,
    get_unblocked_tasks as _get_unblocked_tasks,
    get_department_status as _get_department_status,
    submit_worker_report as _submit_worker_report,
    submit_qa_report as _submit_qa_report,
    submit_manager_review as _submit_manager_review,
    record_tool_outcome as _record_tool_outcome,
    get_tool_scores as _get_tool_scores,
    record_architecture as _record_architecture,
    record_decision as _record_decision,
    update_project_state as _update_project_state,
    get_project_knowledge as _get_project_knowledge,
    log_failure as _log_failure,
    has_failure_logged as _has_failure_logged,
)

# ── Constants ────────────────────────────────────────────────────────────

PROJECT_DIR = Path.cwd()
PLAYBOOK_DIR = SERVER_DIR / "playbooks"
ESCALATION_THRESHOLD = 5

# ── Gate State (in-memory workflow enforcement) ──────────────────────────

GATE_STATE: dict[str, Any] = {
    "tool_errors": {},       # tool_name → consecutive error count
    "onboarding": None,      # OnboardingFlow instance
}


def track_tool_error(tool_name: str) -> str | None:
    """Track consecutive errors for a tool. Escalate if too many."""
    count = GATE_STATE["tool_errors"].get(tool_name, 0) + 1
    GATE_STATE["tool_errors"][tool_name] = count
    if count >= ESCALATION_THRESHOLD:
        GATE_STATE["tool_errors"][tool_name] = 0
        return f"ESCALATION: {tool_name} failed {ESCALATION_THRESHOLD} times. Check system state."
    return None


def clear_tool_errors(tool_name: str):
    GATE_STATE["tool_errors"].pop(tool_name, None)


# ── Lifespan ─────────────────────────────────────────────────────────────

@dataclass
class AppContext:
    index: list[dict[str, Any]] = field(default_factory=list)
    tool_outcomes: dict[str, dict] = field(default_factory=dict)


@asynccontextmanager
async def lifespan(server):
    ctx = AppContext()
    ctx.index = build_index()
    # Load tool outcomes if available
    try:
        scores_json = _get_tool_scores(str(PROJECT_DIR))
        scores = json.loads(scores_json)
        ctx.tool_outcomes = scores.get("tools", {})
    except Exception:
        ctx.tool_outcomes = {}
    yield ctx


# ── MCP Server ───────────────────────────────────────────────────────────

mcp = FastMCP(
    "systems-orchestrator",
    instructions="""You are a systems-thinking orchestrator. You coordinate skills, agents, and tools.

== NEW PROJECT (FULL complexity) ==
1. start_project("goal") → refine_goal() → lock_goal()   [onboard with the user]
2. /brainstorming                                          [explore approaches, produce spec]
3. create_project_ledger("locked goal")                    [create the ledger — NOT a markdown file]
4. /writing-plans                                          [turn spec into implementation plan]
5. analyze_task() per plan step                            [decompose, classify, match tools]
6. create_task() per step                                  [populate ledger]
7. /subagent-driven-development                            [execute plan task-by-task with review]

== EXISTING PROJECT (add feature / modify) ==
1. get_project_knowledge()                                 [understand current state]
2. /brainstorming                                          [design the change]
3. /writing-plans                                          [plan the implementation]
4. create_task() per step                                  [add to ledger]
5. /subagent-driven-development                            [execute with review]

== SIMPLE TASK (DIRECT / LIGHT) ==
1. analyze_task("description")                             [classify + match tools]
2. Just do it. No ledger, no ceremony.

== BUG / FAILURE ==
1. /systematic-debugging                                   [diagnose root cause FIRST]
2. Then fix with /test-driven-development                  [write failing test, then fix]

== PER TASK LIFECYCLE ==
create_task → dispatch_worker → submit_worker_report → dispatch_qa →
submit_qa_report → log_failure (if issues) → submit_manager_review
REWORK requires log_failure() first — enforced by gate.

== BEFORE CLAIMING DONE ==
/verification-before-completion — run tests, verify output, evidence before assertions.

== SKILL SEQUENCE (strict order) ==
/brainstorming → /writing-plans → /using-git-worktrees → /subagent-driven-development → /verification-before-completion → /finishing-a-development-branch
Never skip a step. Never start implementation before the plan exists.

== MODEL ROUTING ==
Code generation, refactoring, tests → Codex (dispatch routes executor to codex/o4-mini)
Reasoning, planning, QA, review → Claude (dispatch routes planner/verifier/reviewer to claude)

== CREATING NEW SKILLS/AGENTS ==
/plugin-dev:skill-development — create or improve a skill
/plugin-dev:agent-development — create an agent with tools and behavioral contracts
/plugin-dev:create-plugin — scaffold a complete plugin

== PROJECT KNOWLEDGE (use ledger tools, not raw files) ==
record_architecture() — capture components, modules, wiring
record_decision() — capture decisions and reasoning
update_project_state() — record test results, bugs, features, deployments
get_project_knowledge() — read the full project state at a glance

== PRINCIPLES ==
- Specimen: what specific element are you examining?
- Hypothesis: what do you expect to find or change?
- Invariant: what must NOT change?
- Leverage before build: check if an existing tool/skill solves it first.
- The ledger is the single source of truth. Write to it, not to random files.
""",
    lifespan=lifespan,
)

# ═══════════════════════════════════════════════════════════════════════════
# TOOL 1: start_project — Interactive onboarding
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def start_project(goal: str) -> str:
    """Start a new project with interactive goal onboarding.

    The orchestrator will assess your goal's clarity, ask sharpening questions
    with mild sarcasm, and help you nail down exactly what needs building.

    Call this first. Refine with refine_goal(). Lock with lock_goal().

    Args:
        goal: What do you want to build/achieve? Be as specific or vague as you dare.
    """
    flow = OnboardingFlow()
    GATE_STATE["onboarding"] = flow

    # Change 7: auto-skip refinement for high-clarity goals
    assessment = GoalAssessment(goal)
    if assessment.is_ready():
        flow.raw_goal = goal
        flow.refined_goal = goal
        flow.locked = True
        return json.dumps({
            "status": "auto_locked",
            "final_goal": goal,
            "assessment": assessment.to_dict(),
            "message": "Goal is clear and specific. Skipping refinement rounds.",
            "hint": "Proceed directly to create_project_ledger() or analyze_task().",
        }, indent=2)

    result = flow.start(goal)
    return json.dumps(result, indent=2)


@mcp.tool()
def refine_goal(
    refined_goal: str = "",
    scope: str = "",
    success: str = "",
    constraints: str = "",
    dependencies: str = "",
    audience: str = "",
) -> str:
    """Refine the project goal by providing more detail or answering probes.

    Args:
        refined_goal: Updated goal text (optional, keeps current if empty).
        scope: What's explicitly in/out of scope.
        success: How do we know it's done?
        constraints: Hard limits (tech, time, budget, taste).
        dependencies: External dependencies.
        audience: Who uses the output.
    """
    flow = GATE_STATE.get("onboarding")
    if not flow:
        return json.dumps({"error": "No onboarding in progress. Call start_project() first."})

    answers = {}
    if scope: answers["scope"] = scope
    if success: answers["success"] = success
    if constraints: answers["constraints"] = constraints
    if dependencies: answers["dependencies"] = dependencies
    if audience: answers["audience"] = audience

    result = flow.refine(refined_goal, answers)
    return json.dumps(result, indent=2)


@mcp.tool()
def lock_goal() -> str:
    """Lock the goal and proceed to execution planning.
    No more refinement after this. The bureaucracy has spoken.
    """
    flow = GATE_STATE.get("onboarding")
    if not flow:
        return json.dumps({"error": "No onboarding in progress. Call start_project() first."})
    result = flow.lock()
    return json.dumps(result, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 2: analyze_task — The Entry Gate
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def analyze_task(task: str, ctx: Context = None) -> str:
    """Analyze a task: extract system model, classify complexity, match tools.

    This is the main entry point. It:
    1. Derives elements, flows, actions from task text (keyword matching)
    2. Classifies complexity (DIRECT / LIGHT / FULL)
    3. Determines reasoning level (haiku / sonnet / opus)
    4. Scores and ranks available tools
    5. Routes to the appropriate model CLI (Claude vs Codex)
    6. Returns structured action plan

    Args:
        task: Natural language task description.
    """
    index = ctx.request_context.lifespan_context.index if ctx else build_index()
    tool_outcomes = ctx.request_context.lifespan_context.tool_outcomes if ctx else {}

    # 1. System model
    model = derive_system_model(task)
    elements = model["elements"]
    flows = model["flows"]
    actions = model["actions"]

    # 2. Complexity
    complexity = classify_complexity(task, elements, actions, flows=flows)

    # 3. Reasoning level
    reasoning = classify_reasoning_level(task)

    # 4. Tool matching
    matched_tools = []
    for action in actions:
        verb = action["verb"]
        elem_types = [e["type"] for e in elements]
        primary_elem = elem_types[0] if elem_types else ""

        ranked = score_and_rank(
            index, f"{verb} {task}", verb, primary_elem,
            tool_outcomes=tool_outcomes, top_n=3,
        )
        for score, tool in ranked:
            matched_tools.append({
                "tool": tool["name"],
                "type": tool.get("type", ""),
                "score": score,
                "for_action": verb,
                "source": tool.get("source", ""),
            })

    # Deduplicate by tool name, keep highest score
    seen: dict[str, dict] = {}
    for t in matched_tools:
        name = t["tool"]
        if name not in seen or t["score"] > seen[name]["score"]:
            seen[name] = t
    matched_tools = sorted(seen.values(), key=lambda x: -x["score"])

    # 5. Model routing
    primary_action = actions[0]["verb"] if actions else "transform"
    task_type = _infer_task_type(task, primary_action)
    model_cli, model_level = route_task_to_model(task_type, "executor")

    # 6. Build response
    result: dict[str, Any] = {
        "task": task,
        "system_model": {
            "elements": elements,
            "flows": flows,
            "actions": actions,
        },
        "complexity": complexity,
        "reasoning_level": reasoning,
        "model_routing": {
            "cli": model_cli,
            "level": model_level,
            "task_type": task_type,
        },
        "matched_tools": matched_tools[:10],
        "action_required": [],
    }

    # Build action steps — mix MCP tools and skills in correct sequence
    is_bug = any(w in task.lower() for w in ["bug", "fix", "crash", "error", "broken", "failing", "debug"])

    if complexity == "DIRECT":
        if is_bug:
            result["action_required"] = [
                {"step": 1, "instruction": "Diagnose root cause", "invoke": "/systematic-debugging"},
                {"step": 2, "instruction": "Write failing test, then fix", "invoke": "/test-driven-development"},
                {"step": 3, "instruction": "Verify fix", "invoke": "/verification-before-completion"},
            ]
        else:
            result["action_required"] = [
                {"step": 1, "instruction": "Execute directly. No ceremony needed.", "model": model_cli},
            ]
    elif complexity == "LIGHT":
        result["action_required"] = [
            {"step": 1, "instruction": "Create task in ledger", "invoke": "create_task()"},
            {"step": 2, "instruction": "Execute task", "agent": "executor", "model": model_cli},
            {"step": 3, "instruction": "Verify result", "agent": "verifier", "model": "claude"},
            {"step": 4, "instruction": "Confirm before committing", "invoke": "/verification-before-completion"},
        ]
    else:  # FULL
        result["action_required"] = [
            {"step": 1, "instruction": "Onboard — define and lock the goal", "invoke": "start_project() → refine_goal() → lock_goal()"},
            {"step": 2, "instruction": "Explore approaches, produce design spec", "invoke": "/brainstorming"},
            {"step": 3, "instruction": "Create project ledger with locked goal", "invoke": "create_project_ledger()"},
            {"step": 4, "instruction": "Turn spec into implementation plan", "invoke": "/writing-plans"},
            {"step": 5, "instruction": "Decompose each plan step", "invoke": "analyze_task() per step → create_task()"},
            {"step": 6, "instruction": "Execute plan task-by-task with review", "invoke": "/subagent-driven-development"},
            {"step": 7, "instruction": "Verify all work before claiming done", "invoke": "/verification-before-completion"},
            {"step": 8, "instruction": "Finish the branch", "invoke": "/finishing-a-development-branch"},
        ]

    # Recommended skills based on context
    result["recommended_skills"] = []
    if is_bug:
        result["recommended_skills"].append({"skill": "/systematic-debugging", "reason": "Bug detected — diagnose before fixing"})
    if complexity == "FULL":
        result["recommended_skills"].extend([
            {"skill": "/brainstorming", "reason": "FULL complexity — explore approaches first"},
            {"skill": "/writing-plans", "reason": "Create implementation plan from spec"},
            {"skill": "/subagent-driven-development", "reason": "Execute plan with fresh agents per task"},
        ])
    if any(w in task.lower() for w in ["create skill", "new skill", "build skill"]):
        result["recommended_skills"].append({"skill": "/plugin-dev:skill-development", "reason": "Creating a new skill"})
    if any(w in task.lower() for w in ["create agent", "new agent", "build agent"]):
        result["recommended_skills"].append({"skill": "/plugin-dev:agent-development", "reason": "Creating a new agent"})

    # LLM decomposition prompt for FULL complexity tasks
    if complexity == "FULL":
        result["llm_decomposition_prompt"] = generate_llm_decomposition_prompt(task)

    # LLM tool selection prompt when keyword matching has gaps
    has_gaps = len(matched_tools) < 2 or any(t["score"] < 2.0 for t in matched_tools[:3])
    if has_gaps:
        prompt = generate_llm_tool_selection_prompt(task, index)
        if prompt:
            result["llm_tool_selection_prompt"] = prompt

    # Legacy hint if keyword matching found very few signals
    if len(elements) == 0 and len(actions) <= 1:
        result["_llm_decomposition_suggested"] = True
        result["_hint"] = (
            "Keyword matching found few signals. Consider calling decompose_task() "
            "for LLM-assisted system model extraction."
        )

    return json.dumps(result, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 3: query_capabilities — Search the tool index
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def query_capabilities(
    query: str = "",
    tool_type: str = "",
    category: str = "",
    action: str = "",
    ctx: Context = None,
) -> str:
    """Search the capability index — tools, skills, MCP servers, CLIs.

    Args:
        query: Free-text search (matches name, description, use_when).
        tool_type: Filter by type: cli, mcp, mcp_server, skill.
        category: Filter by category: security, web, code, database, etc.
        action: Filter by action: observe, measure, analyze, test, verify, transform, plan.
    """
    index = ctx.request_context.lifespan_context.index if ctx else build_index()
    results = query_index(index, query, tool_type, category, action)
    stats = get_index_stats(index)

    return json.dumps({
        "results": results[:15],
        "result_count": len(results),
        "index_stats": stats,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 4: decompose_task — Structured system model
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def decompose_task(
    task: str,
    system: str = "",
    elements: list[dict[str, Any]] | None = None,
    flows: list[dict[str, Any]] | None = None,
    actions_needed: list[dict[str, Any]] | None = None,
    subsystems: list[str] | None = None,
) -> str:
    """Decompose a task into a system model: elements, flows, actions.

    If called with just the task, returns a skeleton to fill in.
    If called with populated fields, validates and enriches the model.

    Args:
        task: Natural language task description.
        system: The bounded system being operated on.
        elements: Objects — each with name, type, interfaces.
        flows: Data/process flows — each with from, to, type.
        actions_needed: Actions — each with verb, target, why.
        subsystems: Logical groupings of elements.
    """
    if not elements and not actions_needed:
        return json.dumps({
            "task": task,
            "system": "",
            "elements": [],
            "flows": [],
            "actions_needed": [],
            "subsystems": [],
            "_status": "skeleton",
            "_hint": (
                "Fill in: what system? What elements (name, type from "
                f"{sorted(ELEMENT_TYPES)}, interfaces)? What flows? "
                f"What actions (verb from {sorted(ACTIONS)}, target, why)?"
            ),
        }, indent=2)

    model = {
        "task": task,
        "system": system,
        "elements": elements or [],
        "flows": flows or [],
        "actions_needed": actions_needed or [],
        "subsystems": subsystems or [],
    }

    warnings = []
    if not system:
        warnings.append("Missing 'system' — name the bounded system.")
    for elem in model["elements"]:
        if elem.get("type", "") not in ELEMENT_TYPES:
            warnings.append(f"Element '{elem.get('name', '?')}' type '{elem.get('type', '')}' not in {sorted(ELEMENT_TYPES)}")
    for act in model["actions_needed"]:
        if act.get("verb", "") not in ACTIONS:
            warnings.append(f"Verb '{act.get('verb', '')}' not in {sorted(ACTIONS)}")

    model["_status"] = "valid" if not warnings else "incomplete"
    model["_warnings"] = warnings
    return json.dumps(model, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 5: impact_analysis — Pre-change evaluation
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def impact_analysis(
    proposed_change: str,
    target_files: list[str] | None = None,
    system_context: str = "",
) -> str:
    """Evaluate consequences of a proposed change BEFORE executing it.

    Args:
        proposed_change: What you plan to do.
        target_files: Files that will be modified.
        system_context: What system/subsystem this affects.
    """
    return json.dumps({
        "proposed_change": proposed_change,
        "target_files": target_files or [],
        "system_context": system_context,
        "analysis_required": {
            "direct_effects": "What files change? What behavior changes?",
            "indirect_effects": "What depends on the changed code? API contracts?",
            "invariants": "What must continue working exactly as before?",
            "alternatives": "At least one alternative approach.",
            "verdict": "PROCEED | MODIFY | SWITCH | DEFER",
        },
    }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 6: system_snapshot — Current system state
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def system_snapshot() -> str:
    """Discover what's running: ports, processes, containers, disk."""
    ts = datetime.now(timezone.utc).isoformat()
    elements = {
        "listening_ports": _run_cmd("ss -tlnp 2>/dev/null").splitlines()[:15],
        "running_processes": _run_cmd("ps aux --sort=-pcpu 2>/dev/null | head -15").splitlines(),
        "containers": _run_cmd("docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null").splitlines(),
        "disk_usage": _run_cmd("df -h 2>/dev/null | head -10").splitlines(),
    }
    empty_count = sum(1 for v in elements.values() if not v)
    if empty_count >= 3:
        escalation = track_tool_error("system_snapshot")
        if escalation:
            return json.dumps({"error": escalation})
    else:
        clear_tool_errors("system_snapshot")
    return json.dumps({"timestamp": ts, "elements": elements}, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 7: health_check — Verify tool availability  
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def health_check(capabilities: list[str] | None = None, ctx: Context = None) -> str:
    """Verify which capabilities are installed and functional.

    Args:
        capabilities: Tool names to check. Required.
    """
    if not capabilities:
        return json.dumps({"error": "Specify capability names to check."})
    capabilities = capabilities[:30]

    results = []
    for name in capabilities:
        path = shutil.which(name)
        entry: dict[str, Any] = {"name": name, "installed": path is not None, "path": path}
        if path:
            for flag in ["--version", "-V", "version"]:
                try:
                    r = subprocess.run(
                        [path, flag], capture_output=True, text=True, timeout=5,
                    )
                    out = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
                except Exception:
                    out = ""
                if out and "not found" not in out.lower():
                    entry["version"] = out
                    break
        results.append(entry)

    return json.dumps(results, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 8: model_status — Multi-model availability
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def model_status() -> str:
    """Check which AI model CLIs are available and their capabilities.
    Shows Claude, Codex, and routing strategy.
    """
    models = get_available_models()
    routing = {
        "agent_routing": {k: {"model": v[0], "level": v[1]} for k, v in AGENT_ROUTING.items()},
        "qa_step_down": QA_LEVEL_DOWN,
    }
    return json.dumps({"models": models, "routing": routing}, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL 9: suggest_packages — Find installable solutions
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def suggest_packages(need: str, element_type: str = "", prefer: str = "") -> str:
    """Search local package managers for installable solutions.

    Args:
        need: What capability you need.
        element_type: What system element this serves.
        prefer: Ecosystem preference: python, node, system, or empty for all.
    """
    results: dict[str, list[str]] = {}
    search_term = need.split()[0] if need.split() else need
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]+$', search_term):
        return json.dumps({"error": f"Invalid search term: '{search_term}'. Use only letters, numbers, hyphens, underscores."})

    if prefer in ("", "python"):
        out = _run_cmd(f"pip3 list 2>/dev/null | grep -i '{search_term}' | head -10")
        if out:
            results["pip_installed"] = out.splitlines()
        apt_py = _run_cmd(f"apt-cache search python3-.*{search_term} 2>/dev/null | head -5")
        if apt_py:
            results["apt_python"] = apt_py.splitlines()

    if prefer in ("", "node", "javascript"):
        out = _run_cmd(f"npm list -g --depth=0 2>/dev/null | grep -i '{search_term}' | head -10")
        if out:
            results["npm_installed"] = out.splitlines()

    if prefer in ("", "system"):
        out = _run_cmd(f"apt-cache search {search_term} 2>/dev/null | head -10", timeout=10)
        if out:
            results["apt_available"] = out.splitlines()

    if not results:
        return json.dumps({"need": need, "status": "no_results"})

    return json.dumps({"need": need, "packages": results}, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# LEDGER TOOLS — Project task management
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def create_project_ledger(
    goal: str,
    rules: list[str] | None = None,
    departments: list[str] | None = None,
) -> str:
    """Create a project ledger for task tracking with department support.

    Args:
        goal: What the project aims to achieve.
        rules: Constraints that apply to all work.
        departments: Which departments (defaults to all 7).
    """
    return _create_project_ledger(goal, rules, departments, str(PROJECT_DIR))


@mcp.tool()
def create_task(
    dept: str,
    title: str,
    description: str,
    size: str = "M",
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
    files_touched: list[str] | None = None,
) -> str:
    """Create a task in the project ledger.

    Args:
        dept: Department (engineering/design/marketing/qa-testing/devops/product/security).
        title: Short task title.
        description: Full task description.
        size: S/M/L/XL — determines agent pipeline depth.
        blocked_by: Task IDs this depends on.
        blocks: Task IDs this will unblock.
        files_touched: Files this modifies (conflict detection).
    """
    return _create_task(str(PROJECT_DIR), dept, title, description, size, blocked_by, blocks, files_touched)


@mcp.tool()
def get_task(task_id: str) -> str:
    """Read a task's full content.

    Args:
        task_id: Task ID (e.g. "ENG-001").
    """
    return _get_task(str(PROJECT_DIR), task_id)


@mcp.tool()
def submit_worker_report(task_id: str, report: str) -> str:
    """Submit worker completion report. Updates status to IN_REVIEW.

    Args:
        task_id: The task ID.
        report: Worker's completion report.
    """
    return _submit_worker_report(str(PROJECT_DIR), task_id, report)


@mcp.tool()
def submit_qa_report(task_id: str, report: str, score: float) -> str:
    """Submit QA report.

    Args:
        task_id: The task ID.
        report: QA findings (PASS/FAIL per item).
        score: 0.0-1.0 (PASS / total).
    """
    return _submit_qa_report(str(PROJECT_DIR), task_id, report, score)


@mcp.tool()
def log_failure(task_id: str, check_name: str, expected: str, actual: str, severity: str = "major") -> str:
    """Record a QA failure. REQUIRED before submit_manager_review(verdict='REWORK').

    Args:
        task_id: Task this failure belongs to.
        check_name: What was checked.
        expected: Correct result.
        actual: What was observed.
        severity: minor | major | critical.
    """
    return _log_failure(str(PROJECT_DIR), task_id, check_name, expected, actual, severity)


@mcp.tool()
def submit_manager_review(
    task_id: str,
    verdict: str,
    notes: str = "",
    rework_items: list[str] | None = None,
) -> str:
    """Submit manager verdict: VERIFIED/REWORK/ESCALATED.
    REWORK requires log_failure() called first.

    Args:
        task_id: The task ID.
        verdict: VERIFIED | REWORK | ESCALATED.
        notes: Additional context.
        rework_items: What to fix (if REWORK).
    """
    if verdict == "REWORK" and not _has_failure_logged(str(PROJECT_DIR), task_id):
        return json.dumps({
            "error": "GATE_REJECTION: Call log_failure() before issuing REWORK.",
            "hint": "Record each failure first, then submit the review.",
        })
    return _submit_manager_review(str(PROJECT_DIR), task_id, verdict, notes, rework_items)


@mcp.tool()
def get_unblocked_tasks(dept: str = "") -> str:
    """Get tasks ready to start (PENDING, all deps VERIFIED).

    Args:
        dept: Filter by department. Empty = all.
    """
    return _get_unblocked_tasks(str(PROJECT_DIR), dept or None)


@mcp.tool()
def get_department_status(dept: str) -> str:
    """Get task counts by status for a department.

    Args:
        dept: Department name.
    """
    return _get_department_status(str(PROJECT_DIR), dept)


@mcp.tool()
def get_outcomes(dept: str = "", verdict: str = "") -> str:
    """Read task outcomes — the learning loop data.

    Args:
        dept: Filter by department.
        verdict: Filter by verdict.
    """
    return _get_outcomes(str(PROJECT_DIR), dept, verdict)


# ═══════════════════════════════════════════════════════════════════════════
# TOOL-LEVEL LEARNING
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def record_tool_outcome(
    tool_name: str,
    task_id: str,
    action: str,
    success: bool,
    context: str = "",
) -> str:
    """Record whether a tool succeeded/failed for a task.
    Feeds the learning loop — tools that fail get scored lower.

    Args:
        tool_name: Name of the tool used.
        task_id: Task ID where it was used.
        action: What action was attempted.
        success: Did it work?
        context: Additional context.
    """
    return _record_tool_outcome(str(PROJECT_DIR), tool_name, task_id, action, success, context)


@mcp.tool()
def get_tool_learning(tool_name: str = "") -> str:
    """Get tool success/failure rates from the learning loop.

    Args:
        tool_name: Filter to a specific tool. Empty = all.
    """
    return _get_tool_scores(str(PROJECT_DIR), tool_name)


# ═══════════════════════════════════════════════════════════════════════════
# PROJECT KNOWLEDGE TOOLS — Capture what the system IS, not just task status
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def record_architecture(
    component: str,
    module: str,
    status: str = "OK",
    wired: bool = True,
    notes: str = "",
) -> str:
    """Record a system component — what it is, where it lives, whether it's wired.
    Call this as you discover or build components. Builds the architecture map.

    Args:
        component: Component name (e.g. "EXECUTOR", "AUTH_MIDDLEWARE")
        module: Module path (e.g. "engine.executor.WorkflowExecutor")
        status: OK | BROKEN | STUB | NOT_IMPLEMENTED
        wired: Whether it's connected in the boot path
        notes: Additional context
    """
    return _record_architecture(str(PROJECT_DIR), component, module, status, wired, notes)


@mcp.tool()
def record_decision(
    question: str,
    decision: str,
    reasoning: str = "",
    alternatives: str = "",
    decided_by: str = "",
) -> str:
    """Record a design decision — what was decided, why, and what was rejected.
    These accumulate into a decision log explaining why the system is shaped this way.

    Args:
        question: What question was answered (e.g. "Which database?")
        decision: What was decided (e.g. "SQLite for dev, Postgres for prod")
        reasoning: Why this was chosen
        alternatives: What was considered and rejected
        decided_by: Who made the call (user, planner, researcher)
    """
    return _record_decision(str(PROJECT_DIR), question, decision, reasoning, alternatives, decided_by)


@mcp.tool()
def update_project_state(
    category: str,
    key: str,
    value: str,
    notes: str = "",
) -> str:
    """Record a project state change — test result, bug found, feature shipped, etc.

    Args:
        category: bugs | tests | features | dependencies | deployments | other
        key: What specifically (e.g. "test_auth_flow", "CVE-2024-1234")
        value: The state (e.g. "PASSING", "FIXED", "DEPLOYED", "ADDED")
        notes: Context
    """
    return _update_project_state(str(PROJECT_DIR), category, key, value, notes)


@mcp.tool()
def get_project_knowledge() -> str:
    """Read the full project knowledge at a glance — goal, architecture,
    decisions, recent state changes, and task summary. Use this to understand
    where the project stands.
    """
    return _get_project_knowledge(str(PROJECT_DIR))


# ═══════════════════════════════════════════════════════════════════════════
# DISPATCH TOOLS — Craft agent prompts
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def dispatch_worker(task_id: str, reasoning_level: str = "") -> str:
    """Craft a worker dispatch prompt for a task.

    Args:
        task_id: The task ID.
        reasoning_level: Override reasoning level.
    """
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    packet = craft_worker_prompt(task_id, task_content, str(PLAYBOOK_DIR), reasoning_level)
    return json.dumps(packet, indent=2)


@mcp.tool()
def dispatch_qa(task_id: str, reasoning_level: str = "sonnet") -> str:
    """Craft a QA dispatch prompt for a task.

    Args:
        task_id: The task ID.
        reasoning_level: Worker's reasoning level (QA will step down from this).
    """
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    parts = task_content.split("## Worker Report\n")
    worker_report = parts[1].split("\n## QA Report")[0] if len(parts) > 1 else "No worker report found"
    packet = craft_qa_prompt(task_id, task_content, worker_report, str(PLAYBOOK_DIR), reasoning_level)
    return json.dumps(packet, indent=2)


@mcp.tool()
def dispatch_researcher(task_id: str) -> str:
    """Craft a researcher dispatch prompt.

    Args:
        task_id: The task ID.
    """
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    goal = _get_project_goal(str(PROJECT_DIR))
    packet = craft_researcher_prompt(task_id, task_content, str(PLAYBOOK_DIR), goal)
    return json.dumps(packet, indent=2)


@mcp.tool()
def dispatch_planner(task_id: str) -> str:
    """Craft a planner dispatch prompt.

    Args:
        task_id: The task ID.
    """
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    goal = _get_project_goal(str(PROJECT_DIR))
    packet = craft_planner_prompt(task_id, task_content, str(PLAYBOOK_DIR), goal)
    return json.dumps(packet, indent=2)


@mcp.tool()
def dispatch_manager(task_id: str, rework_count: int = 0) -> str:
    """Craft a manager review prompt.

    Args:
        task_id: The task ID.
        rework_count: How many rework cycles so far.
    """
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    parts = task_content.split("## Worker Report\n")
    worker_report = parts[1].split("\n## QA Report")[0] if len(parts) > 1 else ""
    parts2 = task_content.split("## QA Report")
    qa_report = parts2[1].split("\n## Manager Review")[0] if len(parts2) > 1 else ""
    goal = _get_project_goal(str(PROJECT_DIR))
    packet = craft_manager_prompt(task_id, task_content, worker_report, qa_report, rework_count, goal)
    return json.dumps(packet, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# RESOURCE + PROMPT
# ═══════════════════════════════════════════════════════════════════════════

@mcp.resource("capability://index")
def capability_index_resource(ctx: Context = None) -> str:
    """Full capability index grouped by action verb."""
    index = ctx.request_context.lifespan_context.index if ctx else build_index()
    by_action: dict[str, list[str]] = {}
    for cap in index:
        for a in cap.get("actions", []):
            by_action.setdefault(a, []).append(cap["name"])
    return json.dumps({"total": len(index), "by_action": by_action}, indent=2)


@mcp.prompt()
def systems_analysis() -> str:
    """Systems-thinking decomposition framework."""
    return (
        "Given a task, decompose it into a system model:\n\n"
        f"1. SYSTEM: What bounded system are you operating on?\n"
        f"2. ELEMENTS: What objects exist? (types: {', '.join(sorted(ELEMENT_TYPES))})\n"
        "3. FLOWS: What processes connect elements? (data/traffic/control/build)\n"
        f"4. ACTIONS: What do you do? (verbs: {', '.join(sorted(ACTIONS))})\n"
        "5. SUBSYSTEMS: How do elements group?\n\n"
        "Call decompose_task() with this model, then analyze_task() for the plan."
    )


# ── Helpers ──────────────────────────────────────────────────────────────

def _run_cmd(cmd: str, timeout: int = 5) -> str:
    """Run a shell command, return stdout."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _infer_task_type(task: str, primary_action: str) -> str:
    """Map task text to a task type for model routing."""
    task_lower = task.lower()
    code_signals = {"write", "implement", "refactor", "fix", "create function", "add method",
                    "generate code", "build", "scaffold", "test"}
    if any(s in task_lower for s in code_signals) and primary_action == "transform":
        return "code_generation"
    security_signals = {"scan", "audit", "vulnerability", "threat", "pentest"}
    if any(s in task_lower for s in security_signals):
        return "security_scan"
    if primary_action == "plan":
        return "planning"
    if primary_action == "analyze":
        return "analysis"
    if primary_action in ("test", "verify"):
        return "qa_verification"
    return "implementation"


# ── Run ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
