"""Scoring engine — multi-factor tool scoring with outcome learning.

Separated from server.py for testability and clarity.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ── Element Types & Actions ──────────────────────────────────────────────

ELEMENT_TYPES = frozenset({
    "service", "database", "queue", "cache", "file", "container",
    "host", "network", "code", "config", "secret", "data_source",
    "frontend", "scheduler", "notifier",
})

ACTIONS = frozenset({
    "observe", "measure", "analyze", "test", "verify", "transform", "plan",
})

# ── Keyword Dictionaries ────────────────────────────────────────────────

ELEMENT_KEYWORDS: dict[str, list[str]] = {
    "service": ["api", "endpoint", "microservice", "rest api", "restful", "graphql", "grpc",
                "backend", "web app", "web application", "payment", "stripe",
                "application", "daemon", "running services", "open port"],
    "database": ["database", "db", "sql", "postgres", "mysql", "mongo", "sqlite", "schema",
                 "migration", "table", "query", "index", "collection", "store", "cache",
                 "e-commerce", "shopping cart", "product catalog", "user account",
                 "rag", "vector", "embedding", "knowledge base"],
    "queue": ["queue", "kafka", "rabbitmq", "pub/sub", "event bus"],
    "cache": ["memcached", "cdn", "ttl"],
    "file": ["file", "csv", "json", "yaml", "toml", "xml", "log", "template",
             ".py", ".js", ".ts", ".md", ".txt", ".html", ".css", ".sh", "document"],
    "container": ["docker", "container", "image", "dockerfile", "compose",
                  "kubernetes", "k8s", "pod", "helm"],
    "host": ["server", "vm", "instance", "ec2", "droplet", "bare-metal",
             "raspberry", "ssh", "machine", "node"],
    "network": ["network", "dns", "firewall", "proxy", "nginx", "loadbalancer",
                "vpn", "ssl", "tls", "tcp", "udp", "subnet", "traffic", "route", "wifi"],
    "code": ["function", "class", "module", "library", "package", "refactor", "lint",
             "compile", "variable", "method", "syntax", "bug", "error", "exception",
             "test suite", "unit test", "test case", "app", "crash", "android",
             "audit", "codebase", "source code"],
    "config": ["config", "env", "environment", "settings", ".env", "dotenv"],
    "secret": ["secret", "credential", "password", "certificate", "vault", "keystore"],
    "data_source": ["dataset", "parquet", "feed", "scrape", "scraper", "crawl", "crawler",
                    "ingest", "stream", "rss", "extract data",
                    "restaurant", "weather api", "stock price", "sensor",
                    "real-time", "real time", "live data", "customer support tickets"],
    "frontend": ["ui", "ux", "frontend", "front end", "front-end", "screen",
                 "layout", "button", "form", "modal", "navigation", "menu", "dashboard",
                 "responsive", "css", "html", "react", "vue", "angular",
                 "widget", "design system", "theme", "landing page", "user friendly",
                 "dark mode", "tailwind"],
    "scheduler": ["schedule", "cron", "timer", "interval", "periodic", "recurring",
                  "daily", "hourly", "every", "batch", "celery", "trigger"],
    "notifier": ["notify", "notifies", "notification", "alert", "email", "sms", "push",
                 "webhook", "subscribe", "subscription", "digest", "remind", "reminder",
                 "slack", "telegram", "discord"],
}

FLOW_KEYWORDS: dict[str, list[str]] = {
    "data": ["pipeline", "etl", "ingest", "transform", "load", "stream", "sync", "replicate"],
    "traffic": ["request", "response", "route", "proxy", "gateway", "balance", "traffic"],
    "control": ["ci", "cd", "deploy", "release", "rollback", "pipeline", "workflow", "automation"],
    "build": ["build", "compile", "package", "bundle", "webpack", "vite", "make", "cmake", "gradle"],
}

ACTION_KEYWORDS: dict[str, list[str]] = {
    "observe": ["monitor", "watch", "log", "trace", "track", "inspect", "observe", "telemetry", "metrics"],
    "measure": ["benchmark", "profile", "measure", "perf", "latency", "throughput", "load-test"],
    "analyze": ["analyze", "audit", "scan", "review", "assess", "investigate", "diagnose", "debug"],
    "test": ["test", "check", "validate", "assert", "expect", "spec", "coverage", "unit", "integration", "e2e"],
    "verify": ["verify", "confirm", "ensure", "guarantee", "certify", "approve"],
    "transform": ["create", "build", "generate", "write", "implement", "deploy", "install", "configure",
                   "update", "modify", "refactor", "fix", "patch", "migrate", "upgrade", "convert"],
    "plan": ["plan", "design", "architect", "spec", "rfc", "proposal", "roadmap", "estimate", "scope"],
}

# ── Keywords for complexity classification ───────────────────────────────

FULL_SIGNAL_KEYWORDS = frozenset({
    "microservice", "kubernetes", "infrastructure", "architecture", "pipeline",
    "migration", "platform", "distributed", "cluster", "orchestrat",
    "terraform", "ansible", "helm", "ci/cd", "multi-",
    "from scratch", "full stack", "redesign", "fine-tune",
    "slack bot", "discord bot", "telegram bot",
    "scrape", "crawl", "e-commerce",
    "security audit", "full audit", "cron job", "daily report",
    "real-time", "real time", "dashboard with",
    "open ports", "network scan",
})

DIRECT_SIGNAL_KEYWORDS = frozenset({
    "version", "status", "list", "show", "get", "read",
    "ping", "whoami", "uptime", "which", "where",
})

# Reasoning level signals
OPUS_SIGNALS = frozenset({
    "design", "architect", "design system", "security review", "security audit",
    "threat model", "migration plan", "performance analysis", "root cause",
    "code review", "infrastructure design", "system design",
    "from scratch", "full stack", "complete system", "redesign",
    "platform", "fine-tune",
})

HAIKU_SIGNALS = frozenset({
    "rename", "fix typo", "fix padding", "fix css", "fix bug", "fix error", "fix the",
    "add import", "update config", "update version", "create file",
    "run tests", "run test", "format", "install",
    "check if", "check the", "debug why", "delete", "remove",
})


# ── System Model Derivation ─────────────────────────────────────────────

def derive_system_model(task: str) -> dict[str, Any]:
    """Extract elements, flows, and actions from a task description using keyword matching."""
    task_lower = task.lower()
    words = set(re.findall(r"[a-z0-9/._-]+", task_lower))

    elements = []
    for etype, keywords in ELEMENT_KEYWORDS.items():
        matches = []
        for kw in keywords:
            if len(kw) <= 3:
                # Short keywords need word boundaries to avoid substring false positives
                if re.search(r"\b" + re.escape(kw) + r"\b", task_lower):
                    matches.append(kw)
            else:
                if kw in task_lower or kw in words:
                    matches.append(kw)
        if matches:
            elements.append({"type": etype, "matched_keywords": matches})

    flows = []
    for ftype, keywords in FLOW_KEYWORDS.items():
        matches = [kw for kw in keywords if kw in task_lower or kw in words]
        if matches:
            flow: dict[str, Any] = {"type": ftype, "matched_keywords": matches}
            # Add direction if a FLOW_PATTERN matched this keyword set
            for pattern, from_hint, to_hint in FLOW_PATTERNS:
                if pattern in task_lower and any(kw in matches or kw == pattern for kw in matches + [pattern]):
                    flow["from"] = from_hint
                    flow["to"] = to_hint
                    break
            flows.append(flow)

    # Also check FLOW_PATTERNS for flows not yet captured by FLOW_KEYWORDS
    existing_keywords = {kw for f in flows for kw in f.get("matched_keywords", [])}
    for pattern, from_hint, to_hint in FLOW_PATTERNS:
        if pattern in task_lower and pattern not in existing_keywords:
            flows.append({
                "type": "data",
                "matched_keywords": [pattern],
                "from": from_hint,
                "to": to_hint,
            })

    actions = []
    for action, keywords in ACTION_KEYWORDS.items():
        matches = [kw for kw in keywords if kw in task_lower or kw in words]
        if matches:
            actions.append({"verb": action, "matched_keywords": matches})

    return {
        "elements": elements,
        "flows": flows,
        "actions": actions,
    }


# ── Complexity Classification ────────────────────────────────────────────

def classify_complexity(
    task: str,
    elements: list[dict],
    actions: list[dict],
    subsystems: list[str] | None = None,
    flows: list[dict] | None = None,
) -> str:
    """Classify task as DIRECT / LIGHT / FULL based on signals."""
    task_lower = task.lower()

    word_count = len(task.split())
    element_count = len(elements)
    action_count = len(actions)
    flow_count = len(flows) if flows else 0
    sub_count = len(subsystems) if subsystems else 0

    has_full_signal = any(kw in task_lower for kw in FULL_SIGNAL_KEYWORDS)

    # FULL first: explicit signal overrides everything
    if has_full_signal:
        return "FULL"

    complexity_score = element_count + action_count + flow_count * 2 + sub_count * 2

    # FULL: large structure or connected components
    if complexity_score >= 6:
        return "FULL"
    if flow_count >= 1 and element_count >= 2:
        return "FULL"

    # DIRECT: short task, low structure, no flows
    if word_count < 20 and complexity_score <= 3 and flow_count == 0:
        return "DIRECT"

    return "LIGHT"


# ── Reasoning Level Classification ───────────────────────────────────────

def classify_reasoning_level(task: str) -> str:
    """Determine reasoning level: haiku (fast), sonnet (balanced), opus (deep)."""
    task_lower = task.lower()

    if any(s in task_lower for s in OPUS_SIGNALS):
        return "opus"

    if any(s in task_lower for s in HAIKU_SIGNALS):
        return "haiku"

    # Default
    return "sonnet"


# ── Tool Scoring ─────────────────────────────────────────────────────────

def score_tool(
    tool: dict[str, Any],
    query: str,
    action_verb: str = "",
    element_type: str = "",
    tool_outcomes: dict[str, dict] | None = None,
) -> float:
    """Multi-factor scoring for a tool against a query.

    Factors:
    1. Name match (direct substring)
    2. Category/tag overlap
    3. use_when match (if present)
    4. Action verb alignment
    5. Element type alignment
    6. Outcome learning (tool win rate from history)
    """
    score = 0.0
    query_lower = query.lower()
    query_words = set(query_lower.split())
    name = tool.get("name", "").lower()
    desc = tool.get("description", "").lower()
    # Handle both v1 "category" (string) and v2 "categories" (list)
    raw_cats = tool.get("categories", [])
    if not raw_cats and tool.get("category"):
        raw_cats = [tool["category"]]
    categories = [c.lower() for c in raw_cats]
    # use_when handled below — may be str or list
    actions = [a.lower() for a in tool.get("actions", [])]
    # Handle both v2 "element_types" and v1 "inputs" for element alignment
    raw_etypes = tool.get("element_types", []) or tool.get("inputs", [])
    element_types = [e.lower() for e in raw_etypes]
    tags = [t.lower() for t in tool.get("tags", [])]

    # 1. Name match (strong signal)
    if name in query_lower:
        score += 5.0
    elif any(part in query_lower for part in name.split("-") if len(part) > 2):
        score += 2.0

    # 2. Category overlap
    for cat in categories:
        if cat in query_lower:
            score += 1.5
        cat_words = set(cat.split())
        if cat_words & query_words:
            score += 0.5

    # 3. use_when match (high-value signal)
    # use_when may be a string (v2 catalog) or a list of strings (v1 catalog)
    raw_use_when = tool.get("use_when", "")
    if isinstance(raw_use_when, list):
        use_when_phrases = [p.lower() for p in raw_use_when if p]
        use_when = " ".join(use_when_phrases)
    else:
        use_when_phrases = []
        use_when = raw_use_when.lower() if raw_use_when else ""
    if use_when:
        use_words = set(use_when.split())
        overlap = use_words & query_words
        if overlap:
            score += len(overlap) * 1.0
        # Phrase match bonus — explicit phrases from list entries or quoted strings
        for phrase in use_when_phrases:
            if phrase and phrase in query_lower:
                score += 3.0
        for phrase in re.findall(r'"([^"]+)"', use_when):
            if phrase in query_lower:
                score += 3.0

    # 4. Description match
    desc_words = set(desc.split())
    desc_overlap = desc_words & query_words
    score += len(desc_overlap) * 0.3

    # 5. Action verb alignment
    if action_verb:
        if action_verb.lower() in actions:
            score += 2.0
        elif action_verb.lower() in desc:
            score += 0.5

    # 6. Element type alignment + category gate
    if element_type:
        if element_type.lower() in element_types:
            score += 2.0
        elif element_type.lower() in categories:
            score += 1.0
        # Category gate: if the tool has a v1-style "category" field, check domain match.
        # Tools outside the expected domain are penalised heavily (×0.1).
        tool_category = tool.get("category", "")
        if tool_category and not category_matches(tool_category, element_type.lower()):
            score *= 0.1

    # 7. Tag match
    for tag in tags:
        if tag in query_lower:
            score += 1.0

    # 8. Tool outcome learning
    if tool_outcomes:
        outcomes = tool_outcomes.get(name, {})
        win_rate = outcomes.get("win_rate", 0.5)
        total = outcomes.get("total", 0)
        if total >= 3:  # Only apply if we have enough data
            # Adjust score by win rate: good tools get boost, bad ones get penalty
            score *= (0.5 + win_rate)  # range: 0.5x to 1.5x

    return round(score, 2)


def score_and_rank(
    tools: list[dict[str, Any]],
    query: str,
    action_verb: str = "",
    element_type: str = "",
    tool_outcomes: dict[str, dict] | None = None,
    top_n: int = 5,
) -> list[tuple[float, dict[str, Any]]]:
    """Score all tools and return top N ranked results."""
    scored = []
    for tool in tools:
        s = score_tool(tool, query, action_verb, element_type, tool_outcomes)
        if s > 0:
            scored.append((s, tool))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]


# ── Category Gating ──────────────────────────────────────────────────────

ELEMENT_CATEGORIES: dict[str, list[str]] = {
    "host": ["security/scanning", "security/recon", "security/defense", "network/", "system/", "infra/"],
    "service": ["development/web", "development/backend", "network/", "security/scanning", "security/web", "infra/web"],
    "file": ["development/cli", "system/", "data/pipeline", "data/analysis"],
    "container": ["infra/", "development/general"],
    "database": ["data/", "development/backend"],
    "network": ["security/", "network/"],
    "code": ["development/", "security/scanning", "security/web"],
    "process": ["development/", "system/", "data/", "infra/scheduling"],
    "frontend": ["development/frontend", "testing/browser", "development/general"],
    "data_source": ["data/scraping", "data/pipeline", "data/analysis", "testing/browser", "development/backend"],
    "scheduler": ["infra/scheduling", "infra/messaging", "data/pipeline"],
    "notifier": ["infra/notification", "infra/messaging", "data/cache"],
}


def category_matches(cap_category: str, element_type: str) -> bool:
    """Return True if a tool's category is relevant for the given element type."""
    prefixes = ELEMENT_CATEGORIES.get(element_type, [])
    if not prefixes:
        return True
    return any(cap_category.startswith(p.rstrip("/")) for p in prefixes)


# ── Flow Patterns (directional) ──────────────────────────────────────────

FLOW_PATTERNS: list[tuple[str, str, str]] = [
    # (keyword, from_type_hint, to_type_hint)
    ("wire up", "code", "service"),
    ("wire it to", "code", "service"),
    ("connect to", "service", "service"),
    ("talk to", "service", "service"),
    ("send to", "service", "notifier"),
    ("notif", "data_source", "notifier"),
    ("feed into", "data_source", "database"),
    ("store in", "process", "database"),
    ("display", "database", "frontend"),
    ("render", "database", "frontend"),
    ("scrape", "data_source", "database"),
    ("crawl", "data_source", "database"),
    ("poll", "scheduler", "data_source"),
    ("schedule", "scheduler", "process"),
    ("trigger", "scheduler", "process"),
    ("stream to", "data_source", "service"),
    ("push to", "service", "frontend"),
    ("pull from", "data_source", "service"),
    ("sync", "service", "database"),
    ("replicate", "database", "database"),
    ("migrate", "database", "database"),
    ("deploy to", "code", "host"),
    ("serve", "host", "frontend"),
    ("expose", "service", "frontend"),
    ("index", "database", "service"),
]


# ── LLM Prompt Generation ────────────────────────────────────────────────

def generate_llm_decomposition_prompt(task: str) -> str:
    """Generate a prompt for Claude to decompose a task into a system model.

    Use when keyword matching finds few signals (FULL complexity or sparse elements).
    Pipe the output to `claude -p` and feed the JSON result back to decompose_task().
    """
    return f"""Decompose this task into a system model. Return ONLY valid JSON, no markdown.

Task: {task}

Return this exact JSON structure:
{{
  "system": "short name for the bounded system",
  "elements": [
    {{"name": "element_name", "type": "one of: {', '.join(sorted(ELEMENT_TYPES))}", "interfaces": ["what it exposes or consumes"]}}
  ],
  "flows": [
    {{"from": "element_name", "to": "element_name", "type": "data|control|auth", "description": "what flows"}}
  ],
  "actions_needed": [
    {{"verb": "one of: {', '.join(sorted(ACTIONS))}", "target": "element_name", "why": "reason"}}
  ],
  "subsystems": ["logical grouping names"]
}}

Be specific — name real technologies and concrete elements, not abstract categories.
Every element must have at least one action. Every flow must connect two elements."""


def generate_llm_tool_selection_prompt(task: str, index: list) -> str | None:
    """Generate a prompt for Claude to select tools when keyword matching has gaps.

    Returns None if the index is empty. Otherwise returns a prompt string
    that can be piped to `claude -p` to get structured tool recommendations.
    """
    if not index:
        return None

    # Build a compact catalog summary: up to 5 tools per category
    cat_summary: dict[str, list[str]] = {}
    for cap in index:
        # Support both v1 catalog (has "category") and v2 index (has "categories")
        cat = cap.get("category") or (cap.get("categories") or ["uncategorized"])[0]
        if cat not in cat_summary:
            cat_summary[cat] = []
        if len(cat_summary[cat]) < 5:
            cat_summary[cat].append(cap["name"])
    cat_lines = "\n".join(
        f"  {cat}: {', '.join(tools)}" for cat, tools in sorted(cat_summary.items())
    )

    return f"""Given this task, recommend the best tools from the available catalog.
Return ONLY valid JSON, no markdown.

Task: {task}

Available tools by category:
{cat_lines}

Return this JSON structure:
{{
  "recommended_tools": [
    {{"name": "tool_name", "category": "its category", "why": "one sentence reason", "action": "one of: {', '.join(sorted(ACTIONS))}"}}
  ],
  "missing_tools": [
    {{"need": "what capability is missing", "suggested_install": "package name or null"}}
  ]
}}

Pick 3-5 tools. Only recommend tools from the list above. If nothing fits, say so in missing_tools."""
