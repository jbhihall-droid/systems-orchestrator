# Systems Orchestrator — What This Is and Why It Exists

You are operating inside a systems-thinking orchestrator. Before you do anything, understand what you're working with and why it was built this way.

---

## The Problem We Solved

A single LLM conversation degrades as context grows. By message 40, the model has forgotten decisions from message 5. Retry loops waste tokens. Agents working in shared context contaminate each other's reasoning — the QA agent "remembers" what the worker did instead of independently verifying it.

This orchestrator exists to solve that. Every agent gets a fresh context. Every decision is recorded. Every claim is verified by someone who didn't make it.

## What You Have

### The Ledger

There is a project ledger. It is the single source of truth for what has been done, what's pending, what failed, and why. Tasks move through states: PENDING → IN_REVIEW → VERIFIED or REWORK or ESCALATED.

Study it. Understand what `create_project_ledger` stores and why it takes a `goal` parameter. Ask yourself: who sees that goal? Who doesn't? Why would you hide the goal from some agents?

Every verdict writes to `outcomes.jsonl`. This is not logging — it is learning data. Figure out where it gets read back.

### The Agents

Five roles exist. Each has a markdown profile in `agents/`. Read them.

- One decomposes and sequences. It sees the project goal.
- One builds. It does not see the project goal.
- One verifies. It assumes the builder lied.
- One researches. It never builds.
- One judges. It sees the project goal and decides the verdict.

Why would you give the builder a narrow scope? Why would you make the verifier adversarial? Why does the judge need the goal but the builder doesn't? These are not arbitrary choices.

### The Pipeline

Every task starts with `analyze_task`. This is the entry gate. It returns:
- A system model (elements, flows, actions, subsystems)
- A complexity classification (DIRECT / LIGHT / FULL)
- A reasoning level (haiku / sonnet / opus)
- Tool matches with confidence scores
- An `action_required` field that tells you exactly what to do next

Read the `action_required` steps. They are numbered. Follow them in order. The ordering exists because there are gates — operations that must happen before other operations will succeed. If you skip a step, the system will reject your input and tell you why.

### The Execution Loop

`orchestrator_loop.sh` dispatches agents via `claude -p`. Each invocation is a fresh process with zero prior context. The worker cannot see what the QA agent will check. The QA agent cannot see the worker's reasoning, only their claims.

This is the most important architectural property. If you break context isolation, you break the verification guarantee.

---

## What We Discovered About Reasoning

The orchestrator started with keyword matching for everything — detecting elements from prompts, scoring tools, classifying complexity. Substring matching against word lists.

It worked for 77% of cases. The other 23% produced garbage: "import" matched "data source", "pipeline" matched "IP address", "restaurant" matched nothing, and the system recommended network scanners for UI redesign tasks.

We tried fixing it with more keywords. Each fix broke something else. This is the ceiling of pattern matching against natural language.

Then we added one thing: a structured prompt sent to `claude -p` that asks for a JSON decomposition. For the same "build a CI/CD pipeline" task:

- Keywords found: 3 elements, 0 flows, 3 actions
- LLM found: 12 elements, 14 flows, 12 actions, 6 subsystems — naming specific technologies, mapping complete data pipelines, using all 7 verbs correctly

The keyword system is still there. It handles the 77% — the simple cases where speed matters more than accuracy. It runs in milliseconds and costs zero tokens. For DIRECT tasks like "rename variable" or "fix CSS padding", it's the right tool.

For FULL tasks, the LLM does the thinking. `analyze_task` generates two prompts when it detects gaps:
- `llm_decomposition_prompt` — produces a system model
- `llm_tool_selection_prompt` — picks tools from the catalog

The keyword system is the triage nurse. The LLM is the doctor. Figure out when each one runs and why.

---

## The Language Model — Where and Why

Claude (`claude -p`) is used in specific places, not everywhere:

1. **Task decomposition** — FULL complexity tasks get an LLM decomposition prompt. The keyword system can't understand "build a restaurant notification system" requires a scraper, a database, a scheduler, and a notification service. The LLM can.

2. **Tool selection** — When keyword scoring has gaps (confidence < 8.0 or no actions derived), an LLM prompt selects from the actual catalog. It knows that `adb` is for Android debugging and `crawlee` is for web scraping, without needing keyword lists.

3. **Agent dispatch** — Each agent (worker, QA, planner, manager) is a separate `claude -p` call. Fresh context per agent. The prompt carries: role profile + playbook + task details + reasoning level.

4. **Nothing else** — Complexity classification, element detection, scoring, flow detection, subsystem grouping, gate enforcement, ledger operations — all deterministic code. No LLM calls for things that can be computed.

The reasoning level controls prompt depth:
- **haiku** — tight, ~140 words. "Do the task, report what changed."
- **sonnet** — standard, ~810 words. Full playbook, lessons, evidence requirements.
- **opus** — deep, ~860 words. Hypothesis required, alternatives considered, impact analysis, confidence levels.

QA steps DOWN from the worker's level. If the worker needed deep reasoning to build it, the verifier needs less reasoning to check it. Figure out the mapping.

---

## Multi-Model Agent Strategy

Not every agent needs the same model. Different models have different strengths.

You have access to three model ecosystems:
- **Claude** (Anthropic) — strong at reasoning, following complex instructions, structured output, and code generation
- **Codex** (OpenAI) — strong at code completion, fast execution, function calling
- **Antigravity / Gemini** (Google) — strong at long-context analysis, multimodal understanding, large document processing

Think about where each model's strengths align with the five agent roles:

- Which role needs to hold an entire codebase in context and reason about architecture?
- Which role needs to quickly generate code from a specific, narrow prompt?
- Which role needs to read a worker's full report, a QA's full report, and the project goal, then make a judgment call?
- Which role needs to search documentation, compare alternatives, and evaluate trade-offs?
- Which role needs to run commands, read output, and produce a structured pass/fail report?

The dispatch system already supports reasoning levels. Extending it to model selection means adding a `model` field alongside `reasoning_level` in the task metadata, and having `orchestrator_loop.sh` route to `claude -p`, `codex`, or `gemini` based on the role.

The infrastructure is there. The routing decision is yours.

---

## What the System Tracks

- **outcomes.jsonl** — every VERIFIED/REWORK/ESCALATED verdict with department, task ID, timestamp
- **failures.md** — structured QA failures (check name, expected, actual, severity)
- **project-ledger/index.md** — task status table
- **project-ledger/tasks/*.md** — individual task files with worker report, QA report, manager review

The learning loop reads outcomes back into `_score()` to boost tools from departments with high success rates. This is crude — department-level, not tool-level. There's a better feedback mechanism waiting to be built. Look at what data is available and figure out what granularity of learning is possible.

---

## The Catalog

181 curated tool entries + live PATH discovery at startup. Each entry has:
- `actions` — which verbs this tool performs (observe, measure, analyze, test, verify, transform, plan)
- `use_when` / `do_not_use_when` — explicit routing hints that override keyword matching
- `category` — controls element-type gating (wrong domain = 90% score penalty)
- `capabilities` — free-text capabilities for keyword matching

44 entries have `use_when` hints. 137 don't. The autoresearch loop (`autoresearch_catalog.md`) can optimize these automatically using `test_analyze.py` as the metric. Currently at 77% case accuracy / 92% check accuracy on 26 test prompts.

---

## The Test Harness

`test_analyze.py` runs 26 prompts through the full pipeline and checks:
- Element detection accuracy
- Complexity classification
- Reasoning level assignment
- Tool category matching

Run it after every change. The number goes up or it doesn't ship.

`optimize_catalog.py` diagnoses which catalog entries need better `use_when` fields. It shows the score gap between current top-3 and the tool that should rank.

---

## What's Not Built Yet

- Multi-model routing (Claude/Codex/Gemini per agent role)
- Tool-level outcome learning (currently department-level)
- Automatic playbook updates from failure patterns
- Research phase in the execution loop for LIGHT tasks
- Integration with context7 for live documentation in dispatch prompts

These are the next problems. The architecture supports all of them. The data flows exist. The gaps are in the wiring.

---

## Ground Rules

1. `analyze_task` is the entry point. Always start there.
2. Follow `action_required` steps in order. Gates exist for a reason.
3. The keyword system handles DIRECT tasks. The LLM handles FULL tasks. Don't reverse this.
4. Fresh context per agent. Never pass one agent's reasoning to another — only their structured output.
5. Every claim needs evidence. Tool output, not summaries.
6. The test harness is the truth. If the score drops, the change was wrong.
7. The ledger goal flows to planners and reviewers only. Workers get their task. That's it.
