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
from lib.discovery import build_index, get_index_stats, query_index, load_skill_registry
from setup import WORKFLOW_TEMPLATES
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
    first_run: bool = False


@asynccontextmanager
async def lifespan(server):
    ctx = AppContext()

    # Check first-run setup
    config_path = SERVER_DIR / "config.json"
    ctx.first_run = not config_path.exists()

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
    "dobby",
    instructions="""You are Dobby — a systems-thinking assistant that coordinates skills, agents, and tools.

== FIRST RUN ==
If setup_orchestrator() returns first_run: true, this is a new installation.
You MUST call setup_orchestrator() immediately and walk the user through setup:
1. Show them the persona options and ask which fits
2. Call configure_orchestrator() with their choice
3. Show what CLI tools are missing and ask if they want to install them
4. Call install_tools() with the tools they approve
5. Show what MCP servers are missing and ask if they want to install them
6. Call install_mcp_servers() with the servers they approve
7. Show available workflows with get_workflows()
Do NOT skip setup. Do NOT proceed to other tools until setup is complete.

== HOW TO USE THIS MCP SERVER ==
Every tool returns JSON. You MUST read the JSON response and present the key findings
to the user in clear, natural language. Do not just call the tool silently — always
summarize what you learned from the response. Specifically:

- analyze_task() → Tell the user: complexity level, what tools match, what steps to take
- query_capabilities() → Show the user which tools were found and what they do
- system_snapshot() → Summarize: what's running, what ports are open, disk usage
- health_check() → Report which tools are installed vs missing
- model_status() → Tell the user which AI models are available and how routing works
- start_project/refine_goal/lock_goal → Show the assessment, ask the user the probe questions
- decompose_task() → Present the system model: elements, flows, actions needed
- create_task/get_task → Confirm what was created, show task details
- dispatch_worker/dispatch_qa → Show the agent's output and any issues found
- submit_manager_review → Report the verdict: VERIFIED, REWORK, or ESCALATED
- get_project_knowledge() → Summarize the project state for the user
- suggest_packages() → Show package options the user can install
- impact_analysis() → Present the assessment structure to fill in
- execute_pipeline() → Show each stage as it runs: researcher → planner → worker → QA → manager verdict
- install_mcp_servers() → Show which MCP servers were installed, remind to restart CC
- get_workflows() → Show workflow steps clearly, guide user through each step
- run_workflow() → Show which workflow is starting, current step, total steps, what to invoke
- advance_workflow() → Show completed step summary, next step, progress bar (Step 3 of 5)
- workflow_status() → Show progress bar and completed/remaining steps

IMPORTANT: When a workflow is running, ALWAYS show the user:
  1. The workflow name and total steps
  2. Which step they're on (e.g. "Step 2 of 5: Plan")
  3. What was completed so far
  4. What to do now and what tool/skill to invoke
  Never run workflow steps silently — the user must see the work being done.

When a response contains "action_required" steps, walk the user through them.
When a response contains "matched_tools", explain which tools are relevant and why.
When a response contains "recommended_skills", tell the user which skills to invoke.
When a response contains an "error", explain what went wrong and suggest a fix.
When a response contains "hint" or "_hint", follow that guidance.

== WHEN TO USE WHICH TOOL ==
- User describes a task → analyze_task() first, then follow the action_required steps
- User wants to see what tools exist → query_capabilities()
- User wants to start a project → start_project() → refine_goal() → lock_goal()
- User asks about system state → system_snapshot()
- User asks if a tool is installed → health_check()
- User wants to know about AI models → model_status()
- User wants to install MCP servers → install_mcp_servers()
- User asks about workflows or "how do I..." → get_workflows()
- User says "build a feature" → run_workflow(workflow="feature-dev", task="...") to start
- Workflow running → show current step, what to do, progress (Step 2 of 5)
- Step done → call advance_workflow(session_id) to get next step
- Check progress → workflow_status(session_id)

== FULL PIPELINE (how tasks actually execute) ==
1. User gives a prompt
2. analyze_task() → picks best workflow + complexity level
3. For complex tasks: start_project() → refine_goal() → lock_goal()
4. create_project_ledger("locked goal") → stores the end goal
5. create_task() per plan step → populates the ledger
6. execute_pipeline(task_id) → THIS IS THE MAIN EXECUTION TOOL:
   - Dispatches REAL subagents (researcher, planner, worker, QA, manager)
   - Each agent runs as a separate claude process with full MCP access
   - Reports progress at each stage: [1/6] Researcher → [2/6] Planner → etc.
   - Manager reviews work and issues verdict: VERIFIED / REWORK / ESCALATED
   - Rework loops up to 2x before escalation
   - Returns structured result with all stage outputs

SIMPLE TASK:
1. analyze_task() → follow the recommended workflow
2. run_workflow() if a workflow matches, or just do it directly

BUG FIX:
1. /systematic-debugging → /test-driven-development

== TASK LIFECYCLE ==
create_task → execute_pipeline(task_id) → agents run automatically
Pipeline handles: worker → QA → manager review → rework loop
REWORK requires log_failure() first — enforced by gate.

== MODEL ROUTING ==
Code generation, refactoring, tests → Codex (if installed, else Claude)
Reasoning, planning, QA, review → Claude

== KEY SKILLS (invoke with /skill-name) ==
/brainstorming — explore approaches before building
/writing-plans — turn spec into implementation tasks
/systematic-debugging — diagnose bugs methodically
/test-driven-development — write failing test, then implement
/verification-before-completion — evidence before claiming done
/frontend-design:frontend-design — build web UIs
/senior-security — threat modeling and security analysis
/claude-api — build apps with Claude API/SDK

== PRINCIPLES ==
- Always present MCP tool results to the user — never call silently
- Leverage before build: check if an existing tool/skill solves it first
- The ledger is the single source of truth for project state
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
    tool_names = [t["tool"] for t in matched_tools[:5]]
    _summary = (
        f"Task classified as {complexity} complexity, reasoning level {reasoning}. "
        f"Routing to {model_cli}/{model_level} (task type: {task_type}). "
        f"Top tool matches: {', '.join(tool_names) if tool_names else 'none found'}. "
        f"Found {len(elements)} system elements, {len(flows)} flows, {len(actions)} actions."
    )
    result: dict[str, Any] = {
        "_summary": _summary,
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

    # Recommend skills from registry based on task context
    registry = load_skill_registry()
    result["recommended_skills"] = []
    task_lower = task.lower()

    for skill in registry:
        # Check use_when triggers
        if any(trigger in task_lower for trigger in skill.get("use_when", [])):
            # Check do_not_use_when anti-triggers
            if not any(anti in task_lower for anti in skill.get("do_not_use_when", [])):
                result["recommended_skills"].append({
                    "skill": skill["name"],
                    "reason": skill["description"],
                    "phase": skill.get("phase", ""),
                    "sequence_order": skill.get("sequence_order", 0),
                })

    # Always add workflow skills based on complexity
    if complexity == "FULL":
        workflow_skills = [s for s in registry if s.get("category") == "workflow"]
        for ws in sorted(workflow_skills, key=lambda x: x.get("sequence_order", 99)):
            if not any(r["skill"] == ws["name"] for r in result["recommended_skills"]):
                result["recommended_skills"].append({
                    "skill": ws["name"],
                    "reason": ws["description"],
                    "phase": ws.get("phase", ""),
                    "sequence_order": ws.get("sequence_order", 0),
                })

    # Sort by sequence_order so the caller knows the execution order
    result["recommended_skills"].sort(key=lambda x: x.get("sequence_order", 99))

    # ── Workflow matching ──────────────────────────────────────────────
    # Score each workflow template against the task using trigger phrases.
    # Only exact phrase matches count — no partial word matching to avoid
    # false positives from generic words like "page", "create", "app".
    task_words = set(task_lower.split())
    workflow_scores: list[tuple[float, str, dict]] = []
    for wf_key, wf in WORKFLOW_TEMPLATES.items():
        triggers = wf.get("triggers", [])
        if not triggers:
            continue
        score = 0.0
        matched_triggers = []
        for trigger in triggers:
            if trigger in task_lower:
                # Exact phrase match — high confidence
                score += 3.0
                matched_triggers.append(trigger)
        if score > 0:
            workflow_scores.append((score, wf_key, {
                "workflow": wf_key,
                "label": wf["label"],
                "description": wf["description"],
                "score": score,
                "matched_triggers": matched_triggers,
                "steps": " → ".join(s["name"] for s in wf["steps"]),
            }))

    workflow_scores.sort(key=lambda x: -x[0])

    # LLM selects the best workflow — understands intent better than keywords.
    # Trigger matches are used as a hint but LLM has final say.
    best_wf_key = None
    best_wf_info = None

    llm_pick = _llm_select_workflow(task)
    if llm_pick and llm_pick in WORKFLOW_TEMPLATES:
        wf = WORKFLOW_TEMPLATES[llm_pick]
        best_wf_key = llm_pick
        # Check if triggers also matched this pick
        trigger_match = [ws[2]["matched_triggers"] for ws in workflow_scores if ws[1] == llm_pick]
        matched_on = trigger_match[0] if trigger_match else []
        best_wf_info = {
            "workflow": llm_pick,
            "label": wf["label"],
            "description": wf["description"],
            "score": 10.0,
            "matched_triggers": matched_on or ["(LLM-selected)"],
            "steps": " → ".join(s["name"] for s in wf["steps"]),
        }
    elif workflow_scores:
        # Fallback to trigger matching if LLM unavailable
        best_wf_key = workflow_scores[0][1]
        best_wf_info = workflow_scores[0][2]

    if best_wf_key and best_wf_info:
        result["recommended_workflow"] = best_wf_info
        # Add alternatives from trigger matching (excluding the pick)
        alts = [ws[2] for ws in workflow_scores if ws[1] != best_wf_key][:2]
        if alts:
            result["alternative_workflows"] = alts
        # Override action_required with the matched workflow's steps
        best_wf = WORKFLOW_TEMPLATES[best_wf_key]
        result["action_required"] = [
            {"step": i + 1, "instruction": s["description"], "invoke": s["invoke"], "phase": s["name"]}
            for i, s in enumerate(best_wf["steps"])
        ]
        # Update summary with workflow info
        result["_summary"] = (
            f"Task classified as {complexity} complexity. "
            f"Best workflow: {best_wf_info['label']} ({best_wf_info['steps']}). "
            f"Matched on: {', '.join(best_wf_info['matched_triggers'])}. "
            f"Top tools: {', '.join(t['tool'] for t in matched_tools[:3])}."
        )

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

    tool_lines = [f"  - {r['name']}: {r.get('description', '')}" for r in results[:5]]
    _summary = (
        f"Found {len(results)} matching capabilities"
        + (f" for '{query}'" if query else "")
        + (f" (type={tool_type})" if tool_type else "")
        + (f" (category={category})" if category else "")
        + f". Index has {stats['total']} total ({stats['installed']} installed)."
        + ("\nTop matches:\n" + "\n".join(tool_lines) if tool_lines else "")
    )
    return json.dumps({
        "_summary": _summary,
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

    port_count = len([p for p in elements.get("listening_ports", []) if p.startswith("LISTEN")])
    proc_count = len(elements.get("running_processes", [])) - 1  # minus header
    container_count = len(elements.get("containers", [])) - 1  # minus header
    _summary = (
        f"System snapshot at {ts}: "
        f"{port_count} listening ports, "
        f"{max(0, proc_count)} top processes, "
        f"{max(0, container_count)} containers running. "
        f"Disk: {elements.get('disk_usage', ['unknown'])[1] if len(elements.get('disk_usage', [])) > 1 else 'unknown'}"
    )
    return json.dumps({"_summary": _summary, "timestamp": ts, "elements": elements}, indent=2, default=str)


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

    installed = [r["name"] for r in results if r["installed"]]
    missing = [r["name"] for r in results if not r["installed"]]
    _summary = (
        f"Checked {len(results)} tools. "
        f"Installed: {', '.join(installed) if installed else 'none'}. "
        + (f"Missing: {', '.join(missing)}." if missing else "All present.")
    )
    return json.dumps({"_summary": _summary, "tools": results}, indent=2, default=str)


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
    installed = [n for n, m in models.items() if m["installed"]]
    missing = [n for n, m in models.items() if not m["installed"]]
    _summary = (
        f"Models installed: {', '.join(installed) if installed else 'none'}. "
        + (f"Not installed: {', '.join(missing)}. " if missing else "")
        + f"Executor routes to {AGENT_ROUTING['executor'][0]}/{AGENT_ROUTING['executor'][1]}."
    )
    return json.dumps({"_summary": _summary, "models": models, "routing": routing}, indent=2)


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
async def dispatch_worker(task_id: str, reasoning_level: str = "", ctx: Context = None) -> str:
    """Dispatch a worker agent to execute a task.

    Args:
        task_id: The task ID.
        reasoning_level: Override reasoning level.
    """
    if ctx:
        await ctx.report_progress(0, 3, f"Loading task {task_id}...")
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    if ctx:
        await ctx.report_progress(1, 3, "Crafting worker prompt...")
    packet = craft_worker_prompt(task_id, task_content, str(PLAYBOOK_DIR), reasoning_level)
    if ctx:
        await ctx.report_progress(2, 3, f"Dispatching to {packet['model_cli']}/{packet['reasoning_level']}...")
    packet["_summary"] = (
        f"Worker agent dispatched for task {task_id}. "
        f"Model: {packet['model_cli']}/{packet['reasoning_level']}, dept: {packet.get('dept', 'engineering')}. "
        f"Execute this prompt to get the worker's output."
    )
    if ctx:
        await ctx.report_progress(3, 3, "Worker prompt ready")
    return json.dumps(packet, indent=2)


@mcp.tool()
async def dispatch_qa(task_id: str, reasoning_level: str = "sonnet", ctx: Context = None) -> str:
    """Dispatch a QA verification agent to review a task.

    Args:
        task_id: The task ID.
        reasoning_level: Worker's reasoning level (QA will step down from this).
    """
    if ctx:
        await ctx.report_progress(0, 3, f"Loading task {task_id} for QA review...")
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    parts = task_content.split("## Worker Report\n")
    worker_report = parts[1].split("\n## QA Report")[0] if len(parts) > 1 else "No worker report found"
    if ctx:
        await ctx.report_progress(1, 3, "Crafting QA verification prompt...")
    packet = craft_qa_prompt(task_id, task_content, worker_report, str(PLAYBOOK_DIR), reasoning_level)
    packet["_summary"] = (
        f"QA agent dispatched for task {task_id}. "
        f"Model: {packet['model_cli']}/{packet['reasoning_level']}. "
        f"Verifying worker output independently."
    )
    if ctx:
        await ctx.report_progress(3, 3, "QA prompt ready")
    return json.dumps(packet, indent=2)


@mcp.tool()
async def dispatch_researcher(task_id: str, ctx: Context = None) -> str:
    """Dispatch a researcher agent to investigate a task.

    Args:
        task_id: The task ID.
    """
    if ctx:
        await ctx.report_progress(0, 2, f"Loading task {task_id} for research...")
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    goal = _get_project_goal(str(PROJECT_DIR))
    if ctx:
        await ctx.report_progress(1, 2, "Crafting researcher prompt...")
    packet = craft_researcher_prompt(task_id, task_content, str(PLAYBOOK_DIR), goal)
    packet["_summary"] = (
        f"Researcher agent dispatched for task {task_id}. "
        f"Model: {packet['model_cli']}/{packet['reasoning_level']}. "
        f"Investigating unknowns, risks, and approach options."
    )
    if ctx:
        await ctx.report_progress(2, 2, "Research prompt ready")
    return json.dumps(packet, indent=2)


@mcp.tool()
async def dispatch_planner(task_id: str, ctx: Context = None) -> str:
    """Dispatch a planner agent to break down a task into steps.

    Args:
        task_id: The task ID.
    """
    if ctx:
        await ctx.report_progress(0, 2, f"Loading task {task_id} for planning...")
    task_content = _get_task(str(PROJECT_DIR), task_id)
    if task_content.startswith("{"):
        parsed = json.loads(task_content)
        if "error" in parsed:
            return task_content
    goal = _get_project_goal(str(PROJECT_DIR))
    if ctx:
        await ctx.report_progress(1, 2, "Crafting planner prompt...")
    packet = craft_planner_prompt(task_id, task_content, str(PLAYBOOK_DIR), goal)
    packet["_summary"] = (
        f"Planner agent dispatched for task {task_id}. "
        f"Model: {packet['model_cli']}/{packet['reasoning_level']}. "
        f"Breaking task into ordered, concrete steps."
    )
    if ctx:
        await ctx.report_progress(2, 2, "Plan prompt ready")
    return json.dumps(packet, indent=2)


@mcp.tool()
async def dispatch_manager(task_id: str, rework_count: int = 0, ctx: Context = None) -> str:
    """Dispatch a manager agent to review worker + QA results and make a verdict.

    Args:
        task_id: The task ID.
        rework_count: How many rework cycles so far.
    """
    if ctx:
        await ctx.report_progress(0, 2, f"Loading task {task_id} for manager review...")
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
    if ctx:
        await ctx.report_progress(1, 2, "Crafting manager review prompt...")
    packet = craft_manager_prompt(task_id, task_content, worker_report, qa_report, rework_count, goal)
    packet["_summary"] = (
        f"Manager review dispatched for task {task_id} (rework #{rework_count}). "
        f"Model: {packet['model_cli']}/{packet['reasoning_level']}. "
        f"Will issue verdict: VERIFIED, REWORK, or ESCALATED."
    )
    if ctx:
        await ctx.report_progress(2, 2, "Manager prompt ready")
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


# ═══════════════════════════════════════════════════════════════════════════
# SETUP TOOLS — First-run onboarding via MCP
# ═══════════════════════════════════════════════════════════════════════════

# Import setup module for tool packs, MCP packs, workflows, and install recipes
from setup import (
    TOOL_PACKS, MCP_PACKS, WORKFLOW_TEMPLATES, PERSONA_SUGGESTIONS, INSTALL_RECIPES,
    detect_package_manager, get_install_cmd, install_mcp_server, get_installed_mcp_servers,
    load_config, CONFIG_PATH,
)


@mcp.tool()
async def setup_orchestrator(ctx: Context = None) -> str:
    """Check if Dobby needs first-run setup.

    Call this FIRST in any new conversation. If first_run is true,
    walk the user through persona selection, tool packs, and installation.

    Returns system status, available personas, tool packs, and what's missing.
    """
    first_run = ctx.request_context.lifespan_context.first_run if ctx else not CONFIG_PATH.exists()
    config = load_config()
    pm = detect_package_manager()

    if ctx:
        await ctx.report_progress(0, len(TOOL_PACKS), "Scanning tool packs...")

    # Check what's installed
    all_pack_tools: dict[str, bool] = {}
    pack_status = {}
    for i, (pack_key, pack) in enumerate(TOOL_PACKS.items()):
        if ctx:
            await ctx.report_progress(i + 1, len(TOOL_PACKS), f"Checking {pack['label']}...")
        installed = []
        missing = []
        for tool in pack["tools"]:
            is_installed = shutil.which(tool) is not None
            all_pack_tools[tool] = is_installed
            if is_installed:
                installed.append(tool)
            else:
                missing.append(tool)
        pack_status[pack_key] = {
            "label": pack["label"],
            "description": pack["description"],
            "installed": installed,
            "missing": missing,
            "complete": len(missing) == 0,
        }

    total_tools = len(all_pack_tools)
    total_installed = sum(1 for v in all_pack_tools.values() if v)
    total_missing = total_tools - total_installed

    # Build persona options
    personas = {k: v["label"] for k, v in PERSONA_SUGGESTIONS.items()}

    _summary = (
        f"{'FIRST RUN — setup required. ' if first_run else 'Setup status: '}"
        f"{total_installed}/{total_tools} pack tools installed, {total_missing} missing. "
        f"Package manager: {pm or 'none detected'}. "
        + (f"Current persona: {config.get('persona', 'not set')}. " if not first_run else "")
        + ("Present the persona options to the user and ask which fits them. "
           "Then call configure_orchestrator() with their choice."
           if first_run else "")
    )

    return json.dumps({
        "_summary": _summary,
        "first_run": first_run,
        "package_manager": pm,
        "current_config": config if not first_run else None,
        "personas": personas,
        "tool_packs": pack_status,
        "total_installed": total_installed,
        "total_missing": total_missing,
        "_next_step": (
            "Ask the user which persona fits them, then call configure_orchestrator(persona=...). "
            "After that, call install_tools() with the missing tools they approve."
            if first_run else
            "Setup is complete. Use other tools normally."
        ),
    }, indent=2)


@mcp.tool()
async def configure_orchestrator(
    persona: str,
    permission_mode: str = "bypassPermissions",
    reasoning_level: str = "sonnet",
    extra_packs: list[str] | None = None,
) -> str:
    """Configure the orchestrator with user preferences. Call after setup_orchestrator().

    Args:
        persona: User role — one of: fullstack, backend, frontend, data, devops, security, student, everything
        permission_mode: How subagents handle permissions: bypassPermissions, dontAsk, default
        reasoning_level: Default reasoning depth: haiku, sonnet, opus
        extra_packs: Additional tool packs beyond the persona suggestion (e.g. ["security", "rust"])
    """
    suggestion = PERSONA_SUGGESTIONS.get(persona)
    if not suggestion:
        return json.dumps({
            "_summary": f"Unknown persona '{persona}'. Valid options: {', '.join(PERSONA_SUGGESTIONS.keys())}",
            "error": f"Unknown persona: {persona}",
            "valid_personas": list(PERSONA_SUGGESTIONS.keys()),
        }, indent=2)

    selected_packs = list(suggestion["packs"])
    if extra_packs:
        for p in extra_packs:
            if p in TOOL_PACKS and p not in selected_packs:
                selected_packs.append(p)

    # Detect codex
    codex_installed = shutil.which("codex") is not None

    config = {
        "version": 2,
        "setup_complete": True,
        "persona": suggestion["label"],
        "catalog_profile": suggestion["profile"],
        "selected_packs": selected_packs,
        "dispatch": {
            "permission_mode": permission_mode,
            "timeout_seconds": 300,
            "max_parallel": 4,
        },
        "models": {
            "preferred_executor": "codex" if codex_installed else "claude",
            "default_level": reasoning_level,
        },
    }

    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

    # Calculate what CLI tools need installing
    missing_tools = []
    for pack_key in selected_packs:
        pack = TOOL_PACKS.get(pack_key, {})
        for tool in pack.get("tools", []):
            if not shutil.which(tool) and tool not in missing_tools:
                missing_tools.append(tool)

    pm = detect_package_manager()
    installable = []
    manual = []
    for tool in missing_tools:
        cmd = get_install_cmd(tool, pm) if pm else None
        if cmd:
            installable.append({"tool": tool, "command": cmd})
        else:
            manual.append(tool)

    # Check which MCP servers need installing
    mcp_pack_names = suggestion.get("mcp_packs", [])
    installed_mcps = get_installed_mcp_servers()
    missing_mcps = {}
    for mp in mcp_pack_names:
        mpack = MCP_PACKS.get(mp, {})
        for sname in mpack.get("servers", {}):
            if sname not in installed_mcps:
                missing_mcps[sname] = mp

    # Get recommended workflows
    workflow_names = suggestion.get("workflows", [])
    workflows = {k: WORKFLOW_TEMPLATES[k]["label"] for k in workflow_names if k in WORKFLOW_TEMPLATES}

    _summary = (
        f"Configured as '{suggestion['label']}' with packs: {', '.join(selected_packs)}. "
        f"Permission mode: {permission_mode}, reasoning: {reasoning_level}. "
        + (f"{len(missing_tools)} CLI tools need installing. " if missing_tools else "All CLI tools installed. ")
        + (f"{len(missing_mcps)} MCP servers need installing. " if missing_mcps else "All MCP servers configured. ")
        + f"{len(workflows)} workflows available."
    )

    next_steps = []
    if installable:
        next_steps.append(f"1. Call install_tools(tools={[t['tool'] for t in installable]}) for CLI tools")
    if missing_mcps:
        next_steps.append(f"{'2' if installable else '1'}. Call install_mcp_servers(servers={list(missing_mcps.keys())}) for MCP servers")
    if not next_steps:
        next_steps.append("Setup complete! Try get_workflows() to see available workflow patterns.")

    return json.dumps({
        "_summary": _summary,
        "config_saved": True,
        "persona": suggestion["label"],
        "selected_packs": selected_packs,
        "missing_cli_tools": missing_tools,
        "installable": installable,
        "manual_install": manual,
        "missing_mcp_servers": missing_mcps,
        "mcp_packs": mcp_pack_names,
        "workflows": workflows,
        "_next_step": "\n".join(next_steps),
    }, indent=2)


@mcp.tool()
async def install_tools(tools: list[str], ctx: Context = None) -> str:
    """Install missing tools using the system package manager.

    Call this after configure_orchestrator() to install approved tools.
    Only installs tools the user has explicitly approved.

    Args:
        tools: List of tool names to install (e.g. ["nmap", "ruff", "bat"])
    """
    pm = detect_package_manager()
    if not pm:
        return json.dumps({
            "_summary": "No package manager detected. Cannot auto-install.",
            "error": "No package manager found (need pacman, apt, or brew)",
        }, indent=2)

    MAX_INSTALL = 30
    results = []
    installed_count = 0
    failed_count = 0
    skipped = []
    if len(tools) > MAX_INSTALL:
        skipped = tools[MAX_INSTALL:]
        tools = tools[:MAX_INSTALL]
    total = len(tools)

    if ctx:
        msg = f"Starting installation of {total} tools via {pm}..."
        if skipped:
            msg += f" ({len(skipped)} skipped due to batch limit: {', '.join(skipped)})"
        await ctx.report_progress(0, total, msg)

    for i, tool in enumerate(tools):
        cmd = get_install_cmd(tool, pm)
        if not cmd:
            results.append({"tool": tool, "status": "no_recipe", "message": f"No install recipe for {pm}"})
            failed_count += 1
            if ctx:
                await ctx.report_progress(i + 1, total, f"⚠ {tool} — no install recipe")
            continue

        if ctx:
            await ctx.report_progress(i, total, f"Installing {tool}... ({cmd})")

        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                results.append({"tool": tool, "status": "installed", "command": cmd})
                installed_count += 1
                if ctx:
                    await ctx.report_progress(i + 1, total, f"✓ {tool} installed")
            else:
                err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "unknown error"
                results.append({"tool": tool, "status": "failed", "error": err, "command": cmd})
                failed_count += 1
                if ctx:
                    await ctx.report_progress(i + 1, total, f"✗ {tool} failed: {err[:80]}")
        except subprocess.TimeoutExpired:
            results.append({"tool": tool, "status": "timeout", "command": cmd})
            failed_count += 1
            if ctx:
                await ctx.report_progress(i + 1, total, f"✗ {tool} timed out")
        except Exception as e:
            results.append({"tool": tool, "status": "error", "error": str(e)})
            failed_count += 1
            if ctx:
                await ctx.report_progress(i + 1, total, f"✗ {tool} error: {e}")

    _summary = (
        f"Installed {installed_count}/{total} tools"
        + (f", {failed_count} failed" if failed_count else "")
        + f" using {pm}."
        + (f" {len(skipped)} skipped (batch limit {MAX_INSTALL}): {', '.join(skipped)}" if skipped else "")
    )

    return json.dumps({
        "_summary": _summary,
        "results": results,
        "skipped": skipped,
        "installed": installed_count,
        "failed": failed_count,
    }, indent=2)


@mcp.tool()
async def install_mcp_servers(servers: list[str] | None = None, pack: str = "", ctx: Context = None) -> str:
    """Install MCP servers via `claude mcp add`.

    Either specify individual server names or a pack name.
    Installs into ~/.mcp.json so they're available on next CC restart.

    Args:
        servers: Individual server names (e.g. ["sequential-thinking", "memory"])
        pack: MCP pack name (e.g. "core-mcp", "dev-mcp", "data-mcp")
    """
    already_installed = get_installed_mcp_servers()
    to_install: dict[str, dict] = {}

    if pack and pack in MCP_PACKS:
        for name, config in MCP_PACKS[pack]["servers"].items():
            if name not in already_installed:
                to_install[name] = config
    elif servers:
        # Find server configs from all packs
        all_servers = {}
        for p in MCP_PACKS.values():
            all_servers.update(p.get("servers", {}))
        for name in servers:
            if name in all_servers and name not in already_installed:
                to_install[name] = all_servers[name]
            elif name in already_installed:
                pass  # already installed
            else:
                to_install[name] = {"command": "npx", "args": ["-y", f"@modelcontextprotocol/server-{name}"]}
    else:
        # List available packs
        packs_info = {}
        for pk, pv in MCP_PACKS.items():
            server_names = list(pv["servers"].keys())
            packs_info[pk] = {
                "label": pv["label"],
                "description": pv["description"],
                "servers": server_names,
                "installed": [s for s in server_names if s in already_installed],
                "missing": [s for s in server_names if s not in already_installed],
            }
        return json.dumps({
            "_summary": f"Available MCP packs. {len(already_installed)} servers already configured. Specify pack= or servers= to install.",
            "packs": packs_info,
            "currently_installed": sorted(already_installed),
        }, indent=2)

    if not to_install:
        return json.dumps({
            "_summary": "All requested MCP servers are already installed.",
            "already_installed": sorted(already_installed),
        }, indent=2)

    results = []
    total = len(to_install)
    installed_count = 0

    for i, (name, config) in enumerate(to_install.items()):
        if ctx:
            await ctx.report_progress(i, total, f"Installing MCP server: {name}...")
        success, msg = install_mcp_server(name, config)
        results.append({"server": name, "success": success, "message": msg})
        if success:
            installed_count += 1
        if ctx:
            icon = "✓" if success else "✗"
            await ctx.report_progress(i + 1, total, f"{icon} {name}: {msg}")

    _summary = (
        f"Installed {installed_count}/{total} MCP servers. "
        + ("Restart Claude Code (Ctrl+Shift+P → Reload Window) to activate them." if installed_count > 0 else "")
    )
    return json.dumps({
        "_summary": _summary,
        "results": results,
        "installed": installed_count,
        "restart_required": installed_count > 0,
    }, indent=2)


@mcp.tool()
def get_workflows(workflow: str = "") -> str:
    """Get available workflow templates or details for a specific workflow.

    Workflows are step-by-step patterns for common tasks.
    Follow the steps in order — each step tells you what to invoke.

    Args:
        workflow: Specific workflow name (e.g. "feature-dev"). Empty = list all.
    """
    if workflow and workflow in WORKFLOW_TEMPLATES:
        wf = WORKFLOW_TEMPLATES[workflow]
        steps_text = "\n".join(
            f"  {i+1}. [{s['name']}] {s['invoke']} — {s['description']}"
            for i, s in enumerate(wf["steps"])
        )
        _summary = (
            f"Workflow: {wf['label']}\n{wf['description']}\n\n"
            f"Steps:\n{steps_text}\n\n"
            + (f"Requires MCP: {', '.join(wf['requires_mcp'])}\n" if wf['requires_mcp'] else "")
            + (f"Requires skills: {', '.join(wf['requires_skills'])}" if wf['requires_skills'] else "")
        )
        return json.dumps({
            "_summary": _summary,
            "workflow": workflow,
            **wf,
        }, indent=2)

    # List all workflows
    listing = {}
    for key, wf in WORKFLOW_TEMPLATES.items():
        listing[key] = {
            "label": wf["label"],
            "description": wf["description"],
            "step_count": len(wf["steps"]),
            "steps_preview": " → ".join(s["name"] for s in wf["steps"]),
        }

    _summary = (
        f"{len(WORKFLOW_TEMPLATES)} workflows available:\n"
        + "\n".join(f"  {k}: {v['steps_preview']}" for k, v in listing.items())
        + "\n\nCall get_workflows(workflow='name') for full details."
    )
    return json.dumps({
        "_summary": _summary,
        "workflows": listing,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE EXECUTION — Full agent pipeline via MCP
# ═══════════════════════════════════════════════════════════════════════════

from orchestrator_loop import (
    run_task_pipeline,
    _step_researcher, _step_planner, _step_worker, _step_qa, _step_manager,
    _extract_qa_score, _extract_verdict,
)


@mcp.tool()
async def execute_pipeline(task_id: str, ctx: Context = None) -> str:
    """Execute a task through the full agent pipeline with live progress.

    This is the MAIN way to execute tasks. It runs the full pipeline:
      FULL:   researcher → planner → worker → QA → manager review
      LIGHT:  worker → QA → manager (if QA score < 0.7)
      DIRECT: worker only

    Each stage dispatches a real subagent (claude -p with MCP access),
    waits for its output, and feeds it to the next stage.
    The manager issues a final verdict: VERIFIED, REWORK, or ESCALATED.
    Max 2 rework cycles before auto-escalation.

    Args:
        task_id: The task ID to execute (e.g. "ENG-001")
    """
    import re as _re

    task_content = _get_task(str(PROJECT_DIR), task_id)
    parsed = json.loads(task_content) if task_content.startswith("{") else None
    if parsed and "error" in parsed:
        return task_content

    goal = _get_project_goal(str(PROJECT_DIR)) or "Complete the task"
    playbook_dir = str(PLAYBOOK_DIR)

    # Analyze complexity
    desc_match = _re.search(r'## Description\n(.+?)(?:\n##|\Z)', task_content, _re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else task_content[:500]

    model = derive_system_model(description)
    complexity = classify_complexity(description, model["elements"], model["actions"], flows=model["flows"])
    reasoning = classify_reasoning_level(description)

    if ctx:
        await ctx.report_progress(0, 6, f"Task {task_id}: {complexity} complexity, {reasoning} reasoning")

    stages_completed = []
    rework_count = 0
    max_rework = 2

    while rework_count <= max_rework:
        if complexity == "FULL" and rework_count == 0:
            # Stage 1: Research
            if ctx:
                await ctx.report_progress(1, 6, f"[1/6] Researcher agent investigating {task_id}...")
            research = _step_researcher(str(PROJECT_DIR), playbook_dir, task_id, task_content, goal)
            stages_completed.append({"stage": "researcher", "output_length": len(research),
                                      "summary": research[:200] + "..." if len(research) > 200 else research})
            if ctx:
                await ctx.report_progress(1, 6, f"✓ Research complete ({len(research)} chars)")

            # Stage 2: Planner
            if ctx:
                await ctx.report_progress(2, 6, f"[2/6] Planner agent creating execution plan...")
            enriched = task_content + "\n\n## Research\n" + research
            plan = _step_planner(str(PROJECT_DIR), playbook_dir, task_id, enriched, goal)
            stages_completed.append({"stage": "planner", "output_length": len(plan),
                                      "summary": plan[:200] + "..." if len(plan) > 200 else plan})
            if ctx:
                await ctx.report_progress(2, 6, f"✓ Plan created ({len(plan)} chars)")

            enriched = enriched + "\n\n## Plan\n" + plan
        elif complexity == "FULL":
            enriched = task_content  # rework — skip research/plan
        else:
            enriched = task_content

        # Stage 3: Worker execution
        stage_num = 3 if complexity == "FULL" else 1
        total_stages = 6 if complexity == "FULL" else (3 if complexity == "LIGHT" else 1)
        if ctx:
            await ctx.report_progress(stage_num, total_stages,
                f"[{stage_num}/{total_stages}] Worker agent executing task...")
        worker_result = _step_worker(str(PROJECT_DIR), playbook_dir, task_id, enriched, reasoning)
        stages_completed.append({"stage": "worker", "output_length": len(worker_result),
                                  "summary": worker_result[:200] + "..." if len(worker_result) > 200 else worker_result})
        if ctx:
            await ctx.report_progress(stage_num, total_stages,
                f"✓ Worker complete ({len(worker_result)} chars)")

        if complexity == "DIRECT":
            # Direct tasks skip QA and manager
            return json.dumps({
                "_summary": f"Task {task_id} executed (DIRECT). Worker output: {len(worker_result)} chars. Auto-VERIFIED.",
                "task_id": task_id,
                "complexity": complexity,
                "verdict": "VERIFIED",
                "stages": stages_completed,
            }, indent=2)

        # Stage 4: QA verification
        stage_num = 4 if complexity == "FULL" else 2
        if ctx:
            await ctx.report_progress(stage_num, total_stages,
                f"[{stage_num}/{total_stages}] QA agent verifying work...")
        qa_result, qa_score = _step_qa(str(PROJECT_DIR), playbook_dir, task_id, enriched, worker_result, reasoning)
        stages_completed.append({"stage": "qa", "score": qa_score, "output_length": len(qa_result),
                                  "summary": qa_result[:200] + "..." if len(qa_result) > 200 else qa_result})
        if ctx:
            await ctx.report_progress(stage_num, total_stages,
                f"✓ QA complete (score: {qa_score:.1f})")

        # LIGHT complexity: auto-verify if QA passes
        if complexity == "LIGHT" and qa_score >= 0.7:
            from lib.ledger import submit_manager_review as _smr
            _smr(str(PROJECT_DIR), task_id, "VERIFIED", "QA passed", None)
            return json.dumps({
                "_summary": f"Task {task_id} VERIFIED (LIGHT). QA score: {qa_score:.1f}. All stages complete.",
                "task_id": task_id,
                "complexity": complexity,
                "verdict": "VERIFIED",
                "qa_score": qa_score,
                "stages": stages_completed,
            }, indent=2)

        # Stage 5: Manager review
        stage_num = 5 if complexity == "FULL" else 3
        if ctx:
            await ctx.report_progress(stage_num, total_stages,
                f"[{stage_num}/{total_stages}] Manager reviewing worker + QA results...")
        verdict = _step_manager(str(PROJECT_DIR), task_id, enriched, worker_result, qa_result, rework_count, goal)
        stages_completed.append({"stage": "manager", "verdict": verdict})
        if ctx:
            await ctx.report_progress(stage_num, total_stages,
                f"✓ Manager verdict: {verdict}")

        if verdict == "VERIFIED":
            return json.dumps({
                "_summary": (
                    f"Task {task_id} VERIFIED ({complexity}). "
                    f"Pipeline: {' → '.join(s['stage'] for s in stages_completed)}. "
                    f"QA score: {qa_score:.1f}. All stages passed."
                ),
                "task_id": task_id,
                "complexity": complexity,
                "verdict": "VERIFIED",
                "qa_score": qa_score,
                "rework_count": rework_count,
                "stages": stages_completed,
            }, indent=2)
        elif verdict == "ESCALATED":
            return json.dumps({
                "_summary": f"Task {task_id} ESCALATED. Needs human intervention. Review the stages below.",
                "task_id": task_id,
                "verdict": "ESCALATED",
                "rework_count": rework_count,
                "stages": stages_completed,
            }, indent=2)
        elif verdict == "REWORK":
            rework_count += 1
            if ctx:
                await ctx.report_progress(stage_num, total_stages,
                    f"⟲ REWORK #{rework_count}/{max_rework} — re-executing worker...")
            if rework_count > max_rework:
                from lib.ledger import submit_manager_review as _smr
                _smr(str(PROJECT_DIR), task_id, "ESCALATED", f"Max rework ({max_rework}) exceeded", None)
                return json.dumps({
                    "_summary": f"Task {task_id} ESCALATED after {max_rework} rework attempts.",
                    "task_id": task_id,
                    "verdict": "ESCALATED",
                    "rework_count": rework_count,
                    "stages": stages_completed,
                }, indent=2)
            task_content = _get_task(str(PROJECT_DIR), task_id)

    return json.dumps({
        "_summary": f"Task {task_id} ESCALATED (max rework exceeded).",
        "task_id": task_id,
        "verdict": "ESCALATED",
        "stages": stages_completed,
    }, indent=2)


# ── Workflow Execution State ─────────────────────────────────────────────
# Tracks active workflow progress so the host can query stage status

_ACTIVE_WORKFLOWS: dict[str, dict] = {}


@mcp.tool()
async def run_workflow(workflow: str, task: str = "", ctx: Context = None) -> str:
    """Start a workflow and get the first step with full instructions.

    This is the main way to execute a workflow. Call this to begin, then
    follow each step. After completing a step, call advance_workflow()
    to get the next step.

    The host MUST show the user:
    - Which workflow is running and how many steps total
    - The current step number and what to do
    - Progress through the workflow (e.g. "Step 2 of 5")

    Args:
        workflow: Workflow key (e.g. "automation", "beautiful-ui", "bug-fix")
        task: The user's original task description (for context in each step)
    """
    if workflow not in WORKFLOW_TEMPLATES:
        # LLM-select if not an exact key
        llm_pick = _llm_select_workflow(task or workflow)
        if llm_pick:
            workflow = llm_pick
        else:
            return json.dumps({
                "_summary": f"Unknown workflow '{workflow}'. Call get_workflows() to see available options.",
                "error": f"Unknown workflow: {workflow}",
            }, indent=2)

    wf = WORKFLOW_TEMPLATES[workflow]
    total = len(wf["steps"])
    import uuid
    session_id = f"wf_{workflow}_{uuid.uuid4().hex[:8]}"

    _ACTIVE_WORKFLOWS[session_id] = {
        "workflow": workflow,
        "label": wf["label"],
        "task": task,
        "current_step": 0,
        "total_steps": total,
        "completed_steps": [],
        "status": "running",
    }

    step = wf["steps"][0]
    if ctx:
        await ctx.report_progress(0, total, f"Starting workflow: {wf['label']}")
        await ctx.report_progress(1, total, f"Step 1/{total}: {step['name']}")

    _summary = (
        f"== WORKFLOW: {wf['label']} ==\n"
        f"Task: {task or '(none specified)'}\n"
        f"Total steps: {total}\n\n"
        f"▶ STEP 1 of {total}: {step['name']}\n"
        f"  What to do: {step['description']}\n"
        f"  Invoke: {step['invoke']}\n\n"
        f"Upcoming:\n"
        + "\n".join(f"  {i+2}. {s['name']} — {s['description']}" for i, s in enumerate(wf["steps"][1:]))
        + f"\n\nAfter completing this step, call advance_workflow(session_id='{session_id}')."
    )

    return json.dumps({
        "_summary": _summary,
        "session_id": session_id,
        "workflow": workflow,
        "label": wf["label"],
        "total_steps": total,
        "current_step": 1,
        "step": {
            "number": 1,
            "name": step["name"],
            "invoke": step["invoke"],
            "description": step["description"],
        },
        "remaining": [{"number": i+2, "name": s["name"], "description": s["description"]}
                       for i, s in enumerate(wf["steps"][1:])],
    }, indent=2)


@mcp.tool()
async def advance_workflow(session_id: str, step_result: str = "", ctx: Context = None) -> str:
    """Advance to the next step in a running workflow.

    Call this after completing the current step. Include what was accomplished
    in step_result so the workflow tracks progress.

    The host MUST show the user:
    - What step just completed
    - What the next step is
    - Overall progress (e.g. "Step 3 of 5 complete")

    Args:
        session_id: The workflow session ID from run_workflow()
        step_result: Brief summary of what was accomplished in the current step
    """
    state = _ACTIVE_WORKFLOWS.get(session_id)
    if not state:
        return json.dumps({
            "_summary": "No active workflow with that session ID. Call run_workflow() to start one.",
            "error": "Invalid session_id",
        }, indent=2)

    if state["status"] == "completed":
        return json.dumps({
            "_summary": "This workflow is already complete. Start a new one with run_workflow().",
            "status": "completed",
            "completed_steps": state["completed_steps"],
        }, indent=2)

    wf = WORKFLOW_TEMPLATES[state["workflow"]]
    completed_idx = state["current_step"]
    total = state["total_steps"]

    # Record completion of current step
    state["completed_steps"].append({
        "step": completed_idx + 1,
        "name": wf["steps"][completed_idx]["name"],
        "result": step_result or "(completed)",
    })

    next_idx = completed_idx + 1
    state["current_step"] = next_idx

    if ctx:
        await ctx.report_progress(next_idx, total,
            f"✓ Step {completed_idx + 1}/{total} ({wf['steps'][completed_idx]['name']}) complete")

    # Check if workflow is done
    if next_idx >= total:
        state["status"] = "completed"
        if ctx:
            await ctx.report_progress(total, total, f"✓ Workflow '{state['label']}' complete!")

        completed_summary = "\n".join(
            f"  ✓ {s['step']}. {s['name']}: {s['result']}" for s in state["completed_steps"]
        )
        _summary = (
            f"== WORKFLOW COMPLETE: {state['label']} ==\n"
            f"All {total} steps finished.\n\n"
            f"Completed steps:\n{completed_summary}\n"
        )
        return json.dumps({
            "_summary": _summary,
            "status": "completed",
            "workflow": state["workflow"],
            "total_steps": total,
            "completed_steps": state["completed_steps"],
        }, indent=2)

    # Return next step
    step = wf["steps"][next_idx]
    if ctx:
        await ctx.report_progress(next_idx, total,
            f"▶ Step {next_idx + 1}/{total}: {step['name']}")

    completed_summary = "\n".join(
        f"  ✓ {s['step']}. {s['name']}: {s['result']}" for s in state["completed_steps"]
    )
    _summary = (
        f"== WORKFLOW: {state['label']} — Step {next_idx + 1} of {total} ==\n\n"
        f"Completed:\n{completed_summary}\n\n"
        f"▶ STEP {next_idx + 1} of {total}: {step['name']}\n"
        f"  What to do: {step['description']}\n"
        f"  Invoke: {step['invoke']}\n"
        + (f"\n  Remaining: {', '.join(s['name'] for s in wf['steps'][next_idx + 1:])}\n" if next_idx + 1 < total else "")
        + f"\nCall advance_workflow(session_id='{session_id}') when this step is done."
    )

    return json.dumps({
        "_summary": _summary,
        "session_id": session_id,
        "status": "running",
        "current_step": next_idx + 1,
        "total_steps": total,
        "step": {
            "number": next_idx + 1,
            "name": step["name"],
            "invoke": step["invoke"],
            "description": step["description"],
        },
        "completed_steps": state["completed_steps"],
        "remaining": [{"number": i + next_idx + 2, "name": s["name"], "description": s["description"]}
                       for i, s in enumerate(wf["steps"][next_idx + 1:])],
    }, indent=2)


@mcp.tool()
def workflow_status(session_id: str = "") -> str:
    """Check the status of active workflows.

    Args:
        session_id: Specific workflow session to check. Empty = list all active.
    """
    if session_id and session_id in _ACTIVE_WORKFLOWS:
        state = _ACTIVE_WORKFLOWS[session_id]
        wf = WORKFLOW_TEMPLATES.get(state["workflow"], {})
        total = state["total_steps"]
        current = state["current_step"]
        completed = len(state["completed_steps"])

        progress_bar = "█" * completed + "░" * (total - completed)
        _summary = (
            f"Workflow: {state['label']} [{progress_bar}] {completed}/{total}\n"
            f"Status: {state['status']}\n"
            f"Task: {state.get('task', '')}\n"
        )
        if state["completed_steps"]:
            _summary += "\nCompleted:\n" + "\n".join(
                f"  ✓ {s['name']}: {s['result']}" for s in state["completed_steps"]
            )
        if current < total:
            step = wf["steps"][current]
            _summary += f"\n\nCurrent: Step {current + 1} — {step['name']}: {step['description']}"

        return json.dumps({"_summary": _summary, **state}, indent=2)

    # List all active
    if not _ACTIVE_WORKFLOWS:
        return json.dumps({"_summary": "No active workflows.", "workflows": []}, indent=2)

    workflows = []
    for sid, state in _ACTIVE_WORKFLOWS.items():
        completed = len(state["completed_steps"])
        total = state["total_steps"]
        workflows.append({
            "session_id": sid,
            "workflow": state["label"],
            "progress": f"{completed}/{total}",
            "status": state["status"],
        })
    _summary = "Active workflows:\n" + "\n".join(
        f"  {w['workflow']}: {w['progress']} ({w['status']})" for w in workflows
    )
    return json.dumps({"_summary": _summary, "workflows": workflows}, indent=2)


# ── Helpers ──────────────────────────────────────────────────────────────

def _llm_select_workflow(task: str) -> str | None:
    """Ask the LLM to pick the best workflow for a task.
    Returns the workflow key (e.g. 'automation', 'bug-fix') or None on failure.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return None

    # Build compact workflow catalog for the prompt
    catalog_lines = []
    for key, wf in WORKFLOW_TEMPLATES.items():
        steps = " → ".join(s["name"] for s in wf["steps"])
        catalog_lines.append(f"  {key}: {wf['label']} — {wf['description']} [{steps}]")
    catalog_text = "\n".join(catalog_lines)

    prompt = f"""Pick the single best workflow for this task. Return ONLY the workflow key, nothing else.

Task: {task}

Available workflows:
{catalog_text}

Reply with just the key (e.g. "automation" or "bug-fix"). No explanation."""

    try:
        r = subprocess.run(
            [claude_bin, "-p", "--model", "haiku"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=15,
        )
        pick = r.stdout.strip().strip('"').strip("'").strip()
        # Validate it's an actual workflow key
        if pick in WORKFLOW_TEMPLATES:
            return pick
        # Try fuzzy match — LLM might return the label instead of key
        pick_lower = pick.lower().replace(" ", "-").replace("_", "-")
        if pick_lower in WORKFLOW_TEMPLATES:
            return pick_lower
        # Try matching against labels
        for key, wf in WORKFLOW_TEMPLATES.items():
            if pick_lower in wf["label"].lower().replace(" ", "-"):
                return key
        return None
    except Exception:
        return None


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
    """Map task text to a task type for model routing.
    Uses LLM for classification, falls back to keywords.
    """
    claude_bin = shutil.which("claude")
    if claude_bin:
        try:
            prompt = (
                f"Classify this task into exactly ONE type. Reply with ONLY the type, nothing else.\n\n"
                f"Types: code_generation, refactoring, test_writing, implementation, "
                f"code_review, security_scan, architecture, research, planning, "
                f"qa_verification, documentation, analysis, automation, design\n\n"
                f"Task: {task}"
            )
            r = subprocess.run(
                [claude_bin, "-p", "--model", "haiku"],
                input=prompt, capture_output=True, text=True, timeout=10,
            )
            pick = r.stdout.strip().strip('"').lower().replace(" ", "_")
            valid_types = {"code_generation", "refactoring", "test_writing", "implementation",
                          "code_review", "security_scan", "architecture", "research", "planning",
                          "qa_verification", "documentation", "analysis", "automation", "design"}
            if pick in valid_types:
                return pick
        except Exception:
            pass

    # Fallback: keyword matching
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
