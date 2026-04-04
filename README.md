# Systems Orchestrator v2

Multi-agent task execution system that routes work through Claude CLI and Codex CLI using subscription-only models (no API keys). Features interactive goal onboarding with dry humor, keyword-based task analysis, outcome-learning tool scoring, and a project ledger for tracking work across 7 departments.

## Architecture

```
User Goal
  |
  v
[Onboarding] ──> refine until clear ──> lock goal
  |
  v
[Analyzer] ──> derive system model, classify complexity (DIRECT/LIGHT/FULL)
  |
  v
[Discovery] ──> build capability index (catalog + skills + MCPs + CLIs)
  |
  v
[Dispatcher] ──> route to Claude CLI or Codex CLI by task type + agent role
  |
  v
[Orchestrator Loop] ──> execute pipeline per complexity level
  |         |
  |   DIRECT: executor only
  |   LIGHT:  executor -> verifier
  |   FULL:   researcher -> planner -> executor -> verifier -> reviewer
  |
  v
[Ledger] ──> track tasks, outcomes, tool performance across departments
```

## Components

### Library Modules (`lib/`)

| Module | Purpose |
|--------|---------|
| `onboarding.py` | Interactive goal refinement with GoalAssessment scoring and humor |
| `analyzer.py` | System model derivation, complexity/reasoning classification, tool scoring |
| `discovery.py` | Unified capability index from catalog, skills, MCPs, and CLI tools |
| `dispatch.py` | Multi-model routing (Claude + Codex), prompt crafting, execution |
| `ledger.py` | Project ledger CRUD, task lifecycle, tool outcome learning |

### MCP Server (`server.py`)

25+ tools organized into groups:

- **Onboarding**: `start_project`, `refine_goal`, `lock_goal`
- **Analysis**: `analyze_task`, `query_capabilities`, `decompose_task`
- **Planning**: `impact_analysis`, `system_snapshot`, `health_check`, `model_status`, `suggest_packages`
- **Ledger**: `create_project_ledger`, `create_task`, `get_task`, `submit_worker_report`, `submit_qa_report`, `log_failure`, `submit_manager_review`, `get_unblocked_tasks`, `get_department_status`, `get_outcomes`
- **Learning**: `record_tool_outcome`, `get_tool_learning`
- **Dispatch**: `dispatch_worker`, `dispatch_qa`, `dispatch_researcher`, `dispatch_planner`, `dispatch_manager`

### Orchestrator Loop (`orchestrator_loop.py`)

Python execution loop that polls for unblocked tasks and runs them through the appropriate pipeline:

```bash
# Run once for engineering department
python3 orchestrator_loop.py --project-dir ./my-project --dept engineering --once

# Poll continuously
python3 orchestrator_loop.py --project-dir ./my-project --poll 15
```

### Agent Profiles (`agents/`)

5 agent roles with explicit behavioral contracts:

| Agent | Model | Purpose |
|-------|-------|---------|
| Executor | Codex/o4-mini | Creates and modifies files, runs commands |
| Verifier | Claude/sonnet | QA gate, scores 0.0-1.0, never modifies code |
| Researcher | Claude/sonnet | Reads, searches, investigates, produces findings |
| Planner | Claude/opus | Creates step-by-step execution plans |
| Reviewer | Claude/opus | Final review, issues VERIFIED/REWORK/ESCALATED |

### Department Playbooks (`playbooks/`)

14 playbooks (worker + qa per department):

`engineering`, `design`, `marketing`, `qa-testing`, `devops`, `product`, `security`

## Model Routing

Two subscription CLIs, zero API keys:

| CLI | Flag | Strengths |
|-----|------|-----------|
| Claude CLI (`claude -p`) | `--model opus/sonnet/haiku` | Reasoning, planning, QA, review, security |
| Codex CLI (`codex exec`) | `-m o4-mini/o3/gpt-4.1` | Code generation, execution, refactoring, tests |

Routing priority: task type > agent role > default.

## Tool Scoring

8-factor scoring with outcome learning:

1. Name match (keyword in tool name)
2. Description match (keyword in description)
3. Category match (task type matches tool category)
4. Action match (verb alignment)
5. use_when match (situational trigger text)
6. Tag match (metadata tags)
7. Historical win rate (from recorded outcomes)
8. Recency boost (recently successful tools)

## Setup

```bash
# Install dependencies
pip install mcp

# Register as MCP server in ~/.mcp.json
{
  "mcpServers": {
    "systems-orchestrator-v2": {
      "command": "python3",
      "args": ["/path/to/test/server.py"],
      "env": {}
    }
  }
}
```

## Testing

```bash
cd /home/Ricky/test
python3 -m pytest tests/ -v
```

43 tests covering analyzer, onboarding, discovery, dispatch, ledger, and end-to-end scenarios.

## Departments

| Key | Role |
|-----|------|
| engineering | Core development |
| design | UI/UX and visual |
| marketing | Content and outreach |
| qa-testing | Test coverage and validation |
| devops | Infrastructure and deployment |
| product | Requirements and user stories |
| security | SAST, dependency scan, threat modeling |

## Complexity Pipelines

| Level | Trigger | Steps |
|-------|---------|-------|
| DIRECT | Simple rename, config change | Executor only |
| LIGHT | Single component, 1-2 elements | Executor -> Verifier |
| FULL | Multi-component, architecture | Researcher -> Planner -> Executor -> Verifier -> Reviewer |
