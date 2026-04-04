"""Interactive goal onboarding with dry humor.

Guides the user through progressively sharper questions until the goal
is crystal clear — or until the user tells us to shut up and build.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── Personality lines ────────────────────────────────────────────────────

GREETINGS = [
    "Ah, another ambitious project. Let me grab my clipboard and pretend this is normal.",
    "Welcome to the orchestrator. I'd offer coffee but I'm a server process.",
    "Right then. You want something built. I want clear requirements. Let's see who caves first.",
]

CLARIFYING_PROMPTS = {
    "vague": [
        "That's... beautifully abstract. Could you add a verb? Maybe a noun? I'm not picky.",
        "I love the enthusiasm. Now, *specifically*, what should exist when we're done?",
        "Poetry aside, what does 'done' look like? A file? A server? World peace?",
    ],
    "too_big": [
        "That's roughly the scope of a small space program. Can we pick one hemisphere?",
        "I count at least 7 projects in there. Which one's due first?",
        "Even I need to breathe between tasks. Let's chunk this down.",
    ],
    "missing_tech": [
        "What language/framework? Or shall I read your aura?",
        "I need to know the stack. Python? Node? Carrier pigeons?",
        "Slight gap in the brief: what technology are we inflicting this upon?",
    ],
    "missing_output": [
        "And the deliverable is... a warm feeling? Or something more tangible?",
        "When this is done, what artifact exists that didn't before?",
        "What file/service/widget should I have built when the dust settles?",
    ],
    "looks_good": [
        "Now *that* I can work with. Let me fire up the engines.",
        "Clear, scoped, actionable. You're suspiciously good at this.",
        "Finally, a goal with actual edges. Deploying taste alongside functionality.",
    ],
}

PROBE_QUESTIONS = [
    ("scope", "What's the boundary? What's explicitly *not* part of this?"),
    ("success", "How do we know it's done? What would a test check?"),
    ("constraints", "Any hard constraints? Time, tech, 'no JavaScript'... the usual suspects."),
    ("dependencies", "Does this depend on anything external being true first?"),
    ("audience", "Who uses the output? You? A team? The general public and their myriad expectations?"),
]

# ── Goal Assessment ──────────────────────────────────────────────────────

class GoalAssessment:
    """Structured assessment of how clear/actionable a user goal is."""

    def __init__(self, goal: str):
        self.goal = goal
        self.issues: list[str] = []
        self.score = 0.0  # 0 = useless, 1 = ship-it
        self.category = "vague"
        self._assess()

    def _assess(self):
        words = self.goal.split()
        score = 0.0

        # Has verbs? (action words)
        action_words = {"build", "create", "deploy", "fix", "refactor", "add", "remove",
                        "implement", "design", "test", "configure", "set", "update",
                        "install", "migrate", "upgrade", "analyze", "scan", "audit",
                        "write", "generate", "optimize", "monitor", "debug"}
        has_verb = bool(action_words & {w.lower().rstrip(".,;:!?") for w in words})
        if has_verb:
            score += 0.25
        else:
            self.issues.append("missing_verb")

        # Has a technology/domain mention?
        tech_words = {"python", "node", "js", "typescript", "react", "django", "flask",
                      "docker", "kubernetes", "k8s", "api", "rest", "graphql", "sql",
                      "postgres", "redis", "nginx", "terraform", "ansible", "bash",
                      "shell", "git", "ci", "cd", "pipeline", "html", "css", "server",
                      "database", "container", "function", "lambda", "mcp", "claude",
                      "codex", "llm", "ai", "ml", "model", "kotlin", "android", "java",
                      "rust", "go", "swift", "network", "firewall", "ssl", "tls"}
        has_tech = bool(tech_words & {w.lower().rstrip(".,;:!?") for w in words})
        if has_tech:
            score += 0.2
        else:
            self.issues.append("missing_tech")

        # Has an output/deliverable mentioned?
        output_words = {"file", "script", "server", "app", "application", "site",
                        "page", "endpoint", "service", "binary", "package", "module",
                        "library", "tool", "dashboard", "report", "config", "image",
                        "container", "function", "workflow", "pipeline", "chart",
                        "diagram", "test", "spec", "doc", "documentation"}
        has_output = bool(output_words & {w.lower().rstrip(".,;:!?") for w in words})
        if has_output:
            score += 0.25
        else:
            self.issues.append("missing_output")

        # Length / detail
        if len(words) > 15:
            score += 0.15
        elif len(words) > 8:
            score += 0.1
        elif len(words) < 4:
            self.issues.append("too_short")

        # Scope sanity — too many conjunctions = scope creep
        conjunction_count = sum(1 for w in words if w.lower() in ("and", "also", "plus", "then", "additionally"))
        if conjunction_count > 3:
            score -= 0.1
            self.issues.append("scope_creep")

        self.score = max(0.0, min(1.0, score))
        if self.score >= 0.7:
            self.category = "looks_good"
        elif "scope_creep" in self.issues:
            self.category = "too_big"
        elif "missing_tech" in self.issues:
            self.category = "missing_tech"
        elif "missing_output" in self.issues:
            self.category = "missing_output"
        else:
            self.category = "vague"

    def is_ready(self) -> bool:
        """If goal is already clear, skip refinement."""
        return (
            self.score >= 0.7
            and "missing_tech" not in self.issues
            and "missing_output" not in self.issues
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "clarity_score": round(self.score, 2),
            "category": self.category,
            "issues": self.issues,
            "ready": self.score >= 0.7,
        }


# ── Onboarding Flow ──────────────────────────────────────────────────────

class OnboardingFlow:
    """Manages the interactive goal refinement conversation."""

    def __init__(self):
        self.raw_goal: str = ""
        self.refined_goal: str = ""
        self.answers: dict[str, str] = {}
        self.round: int = 0
        self.probes_asked: list[str] = []
        self.locked: bool = False

    def start(self, goal: str) -> dict[str, Any]:
        """Start onboarding with initial goal. Returns greeting + assessment."""
        self.raw_goal = goal
        self.round = 1
        assessment = GoalAssessment(goal)

        import random
        greeting = random.choice(GREETINGS)
        flavor = random.choice(CLARIFYING_PROMPTS.get(assessment.category, CLARIFYING_PROMPTS["vague"]))

        result: dict[str, Any] = {
            "greeting": greeting,
            "assessment": assessment.to_dict(),
            "flavor_text": flavor,
            "round": self.round,
        }

        if assessment.score >= 0.7:
            # Good enough — but ask probes to sharpen
            next_probes = [p for p in PROBE_QUESTIONS if p[0] not in self.probes_asked][:2]
            result["probes"] = [{"topic": p[0], "question": p[1]} for p in next_probes]
            self.probes_asked.extend(p[0] for p in next_probes)
            result["status"] = "good_but_can_sharpen"
            result["hint"] = "Goal looks workable. Answer the probes to sharpen it, or say 'lock it in' to proceed."
        else:
            # Needs work
            result["status"] = "needs_refinement"
            result["hint"] = f"Issues found: {', '.join(assessment.issues)}. Refine and resubmit."

        return result

    def refine(self, refined_goal: str = "", probe_answers: dict[str, str] | None = None) -> dict[str, Any]:
        """Accept a refined goal and/or probe answers. Returns updated assessment."""
        self.round += 1

        if probe_answers:
            self.answers.update(probe_answers)

        if refined_goal:
            self.raw_goal = refined_goal

        assessment = GoalAssessment(self.raw_goal)

        # Enrich with probe answers
        enriched = self.raw_goal
        if self.answers.get("scope"):
            enriched += f" [Scope: {self.answers['scope']}]"
        if self.answers.get("success"):
            enriched += f" [Success criteria: {self.answers['success']}]"
        if self.answers.get("constraints"):
            enriched += f" [Constraints: {self.answers['constraints']}]"

        self.refined_goal = enriched

        import random
        result: dict[str, Any] = {
            "assessment": GoalAssessment(enriched).to_dict(),
            "round": self.round,
            "probes_answered": list(self.answers.keys()),
        }

        if assessment.score >= 0.6 or self.round >= 3:
            remaining = [p for p in PROBE_QUESTIONS if p[0] not in self.probes_asked][:1]
            if remaining and self.round < 4:
                result["probes"] = [{"topic": p[0], "question": p[1]} for p in remaining]
                self.probes_asked.extend(p[0] for p in remaining)

            flavor = random.choice(CLARIFYING_PROMPTS["looks_good"])
            result["flavor_text"] = flavor
            result["status"] = "ready_to_lock"
            result["refined_goal"] = self.refined_goal
            result["hint"] = "Say 'lock it in' to finalize, or keep refining."
        else:
            flavor = random.choice(CLARIFYING_PROMPTS.get(assessment.category, CLARIFYING_PROMPTS["vague"]))
            result["flavor_text"] = flavor
            result["status"] = "needs_refinement"
            next_probes = [p for p in PROBE_QUESTIONS if p[0] not in self.probes_asked][:2]
            result["probes"] = [{"topic": p[0], "question": p[1]} for p in next_probes]
            self.probes_asked.extend(p[0] for p in next_probes)

        return result

    def lock(self) -> dict[str, Any]:
        """Lock the goal. No more refinement."""
        self.locked = True
        import random
        return {
            "status": "locked",
            "final_goal": self.refined_goal or self.raw_goal,
            "answers": self.answers,
            "rounds": self.round,
            "flavor_text": random.choice([
                "Goal locked. The bureaucracy has been satisfied. Let's build.",
                "Sealed, signed, and slightly over-engineered. Proceeding.",
                "Goal accepted. I'll pretend I'm not impressed.",
            ]),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_goal": self.raw_goal,
            "refined_goal": self.refined_goal,
            "answers": self.answers,
            "round": self.round,
            "locked": self.locked,
        }
