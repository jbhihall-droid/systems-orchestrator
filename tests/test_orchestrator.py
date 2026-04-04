#!/usr/bin/env python3
"""Test suite for Systems Orchestrator v2.

Tests the analyzer, discovery, onboarding, dispatch routing, and ledger
modules without requiring external API calls.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main

# Add parent to path
TEST_DIR = Path(__file__).resolve().parent
SERVER_DIR = TEST_DIR.parent
sys.path.insert(0, str(SERVER_DIR))

from lib.analyzer import (
    derive_system_model,
    classify_complexity,
    classify_reasoning_level,
    score_tool,
    score_and_rank,
)
from lib.onboarding import GoalAssessment, OnboardingFlow
from lib.discovery import build_index, query_index, get_index_stats
from lib.dispatch import (
    route_task_to_model,
    get_available_models,
    AGENT_ROUTING,
    QA_LEVEL_DOWN,
    MODELS,
)
from lib.ledger import (
    create_project_ledger,
    create_task,
    get_task,
    submit_worker_report,
    submit_qa_report,
    submit_manager_review,
    get_unblocked_tasks,
    record_tool_outcome,
    get_tool_scores,
)


# ======================================================================
# Analyzer Tests
# ======================================================================

class TestAnalyzer(TestCase):
    """Test keyword extraction and complexity classification."""

    def test_derive_simple_task(self):
        model = derive_system_model("fix the login endpoint")
        self.assertIsInstance(model, dict)
        self.assertIn("elements", model)
        self.assertIn("flows", model)
        self.assertIn("actions", model)

    def test_derive_detects_api(self):
        model = derive_system_model("test the REST API endpoint /users")
        elem_types = [e["type"] for e in model["elements"]]
        self.assertTrue(
            any(t in elem_types for t in ["api", "service"]),
            f"Expected api or service, got {elem_types}",
        )

    def test_derive_detects_database(self):
        model = derive_system_model("migrate the postgres database schema")
        elem_types = [e["type"] for e in model["elements"]]
        self.assertIn("database", elem_types)

    def test_derive_detects_container(self):
        model = derive_system_model("build a docker container for the service")
        elem_types = [e["type"] for e in model["elements"]]
        self.assertIn("container", elem_types)

    def test_derive_detects_flow(self):
        model = derive_system_model("set up a CI/CD pipeline that deploys to staging")
        self.assertTrue(len(model["flows"]) > 0, "Should detect pipeline flow")

    def test_complexity_direct(self):
        c = classify_complexity("rename a variable", [], [])
        self.assertEqual(c, "DIRECT")

    def test_complexity_light(self):
        elements = [{"type": "api", "name": "endpoint"}]
        actions = [{"verb": "test"}]
        c = classify_complexity("test api endpoint", elements, actions)
        self.assertIn(c, ["LIGHT", "DIRECT"])

    def test_complexity_full(self):
        elements = [
            {"type": "api"}, {"type": "database"}, {"type": "container"},
            {"type": "service"}, {"type": "config"},
        ]
        actions = [{"verb": "analyze"}, {"verb": "transform"}, {"verb": "test"}]
        c = classify_complexity(
            "redesign the microservice architecture with database migration",
            elements, actions, flows=[{"from": "a", "to": "b"}],
        )
        self.assertEqual(c, "FULL")

    def test_reasoning_level_haiku_or_sonnet(self):
        level = classify_reasoning_level("rename a variable")
        self.assertIn(level, ["haiku", "sonnet"])

    def test_reasoning_level_opus(self):
        level = classify_reasoning_level("design a distributed system architecture")
        self.assertEqual(level, "opus")

    def test_score_tool_basic(self):
        tool = {
            "name": "semgrep",
            "description": "Static analysis for security vulnerabilities",
            "categories": ["security"],
            "actions": ["analyze"],
            "use_when": "scanning code for vulnerabilities",
        }
        score = score_tool(tool, "scan for security vulnerabilities", "analyze", "code")
        self.assertGreater(score, 0.0)

    def test_score_and_rank(self):
        index = [
            {"name": "semgrep", "description": "SAST scanner", "categories": ["security"],
             "actions": ["analyze"], "use_when": "security scanning", "tags": []},
            {"name": "prettier", "description": "Code formatter", "categories": ["code"],
             "actions": ["transform"], "use_when": "formatting code", "tags": []},
        ]
        ranked = score_and_rank(index, "scan for vulnerabilities", "analyze", "code")
        self.assertEqual(ranked[0][1]["name"], "semgrep")


# ======================================================================
# Onboarding Tests
# ======================================================================

class TestOnboarding(TestCase):
    """Test interactive goal assessment and flow."""

    def test_goal_assessment_vague(self):
        a = GoalAssessment("make it better")
        self.assertLess(a.score, 0.5)
        self.assertIn(a.category, ["vague", "missing_tech"])

    def test_goal_assessment_good(self):
        a = GoalAssessment(
            "Build a REST API using FastAPI that serves user data from PostgreSQL"
        )
        self.assertGreater(a.score, 0.5)

    def test_goal_has_tech(self):
        a = GoalAssessment("deploy docker container")
        d = a.to_dict()
        self.assertNotIn("missing_tech", d["issues"])

    def test_goal_missing_tech(self):
        a = GoalAssessment("create a website")
        d = a.to_dict()
        self.assertIn("missing_tech", d["issues"])

    def test_onboarding_flow_start(self):
        flow = OnboardingFlow()
        result = flow.start("build something cool")
        self.assertIn("status", result)
        self.assertEqual(result["status"], "needs_refinement")
        self.assertIn("assessment", result)

    def test_onboarding_flow_refine(self):
        flow = OnboardingFlow()
        flow.start("build something cool")
        result = flow.refine(
            "Build a CLI tool in Python that queries a database",
            {"scope": "Just the CLI, no web UI", "success": "It returns query results"},
        )
        self.assertIn("status", result)

    def test_onboarding_flow_lock(self):
        flow = OnboardingFlow()
        flow.start(
            "Build a REST API with FastAPI serving user data from PostgreSQL"
        )
        result = flow.lock()
        self.assertIn(result["status"], ["locked", "needs_refinement"])
        self.assertTrue("final_goal" in result or "assessment" in result)


# ======================================================================
# Discovery Tests
# ======================================================================

class TestDiscovery(TestCase):
    """Test capability index building and querying."""

    def test_build_index_returns_list(self):
        index = build_index()
        self.assertIsInstance(index, list)
        self.assertGreater(len(index), 0)

    def test_index_has_required_fields(self):
        index = build_index()
        for entry in index[:5]:
            self.assertIn("name", entry)
            self.assertIn("type", entry)

    def test_query_by_type(self):
        index = build_index()
        cli_tools = query_index(index, tool_type="cli")
        for tool in cli_tools:
            self.assertEqual(tool["type"], "cli")

    def test_query_by_text(self):
        index = build_index()
        results = query_index(index, query="security")
        self.assertGreater(len(results), 0)

    def test_get_stats(self):
        index = build_index()
        stats = get_index_stats(index)
        self.assertIn("total", stats)
        self.assertIn("by_type", stats)


# ======================================================================
# Dispatch Tests
# ======================================================================

class TestDispatch(TestCase):
    """Test model routing and prompt crafting."""

    def test_agent_routing_completeness(self):
        expected_agents = {"researcher", "planner", "executor", "verifier", "reviewer"}
        self.assertEqual(set(AGENT_ROUTING.keys()), expected_agents)

    def test_qa_step_down(self):
        self.assertEqual(QA_LEVEL_DOWN["opus"], "sonnet")
        self.assertEqual(QA_LEVEL_DOWN["sonnet"], "haiku")

    def test_route_code_to_codex(self):
        cli, level = route_task_to_model("code_generation", "executor")
        self.assertIn(cli, ["codex", "claude"])

    def test_route_analysis_to_claude(self):
        cli, level = route_task_to_model("analysis", "researcher")
        self.assertEqual(cli, "claude")

    def test_get_available_models(self):
        models = get_available_models()
        self.assertIsInstance(models, dict)
        self.assertTrue(len(models) > 0)

    def test_models_have_required_fields(self):
        for name, info in MODELS.items():
            self.assertIn("binary", info)
            self.assertIn("exec_flag", info)
            self.assertIn("models", info)


# ======================================================================
# Ledger Tests
# ======================================================================

class TestLedger(TestCase):
    """Test project ledger CRUD and lifecycle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orchestrator_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_project_ledger(self):
        result = json.loads(create_project_ledger("Test project", [], None, self.tmp))
        self.assertIn("created", result)
        self.assertTrue(Path(result["created"]).exists())

    def test_create_and_get_task(self):
        create_project_ledger("Test", [], None, self.tmp)
        result = json.loads(
            create_task(self.tmp, "engineering", "Fix bug", "Fix the login bug", "S")
        )
        task_id = result["task_id"]
        self.assertTrue(task_id.startswith("ENG-"))

        content = get_task(self.tmp, task_id)
        self.assertIn("Fix the login bug", content)

    def test_task_lifecycle(self):
        create_project_ledger("Test", [], None, self.tmp)
        result = json.loads(
            create_task(self.tmp, "engineering", "Test task", "Do the thing", "M")
        )
        task_id = result["task_id"]

        submit_worker_report(
            self.tmp, task_id, "I did the thing.\nfiles_changed: foo.py"
        )
        submit_qa_report(self.tmp, task_id, "All checks pass. Score: 0.9", 0.9)

        result = json.loads(
            submit_manager_review(self.tmp, task_id, "VERIFIED", "Looks good")
        )
        self.assertEqual(result["verdict"], "VERIFIED")

    def test_unblocked_tasks(self):
        create_project_ledger("Test", [], None, self.tmp)
        create_task(self.tmp, "engineering", "Task A", "First task", "S")
        result = json.loads(get_unblocked_tasks(self.tmp))
        self.assertIn("unblocked", result)
        self.assertGreater(len(result["unblocked"]), 0)

    def test_tool_outcome_recording(self):
        create_project_ledger("Test", [], None, self.tmp)
        record_tool_outcome(
            self.tmp, "semgrep", "ENG-001", "analyze", True, "found 0 issues"
        )
        record_tool_outcome(
            self.tmp, "semgrep", "ENG-002", "analyze", False, "timeout"
        )

        scores = json.loads(get_tool_scores(self.tmp, "semgrep"))
        self.assertIn("tools", scores)
        self.assertIn("semgrep", scores["tools"])
        semgrep_stats = scores["tools"]["semgrep"]
        self.assertEqual(semgrep_stats["total"], 2)
        self.assertEqual(semgrep_stats["success"], 1)

    def test_dependency_blocking(self):
        create_project_ledger("Test", [], None, self.tmp)
        r1 = json.loads(
            create_task(self.tmp, "engineering", "Task A", "First", "S")
        )
        r2 = json.loads(create_task(
            self.tmp, "engineering", "Task B", "Second", "S",
            blocked_by=[r1["task_id"]],
        ))

        unblocked = json.loads(get_unblocked_tasks(self.tmp))
        unblocked_ids = [t.get("task_id", t) for t in unblocked["unblocked"]]
        self.assertNotIn(r2["task_id"], unblocked_ids)


# ======================================================================
# Integration-level Tests (no external calls)
# ======================================================================

class TestAnalyzeTaskScenarios(TestCase):
    """End-to-end analysis scenarios matching v1 test cases."""

    def _analyze(self, task: str) -> dict:
        """Simulate analyze_task without MCP context."""
        model = derive_system_model(task)
        complexity = classify_complexity(
            task, model["elements"], model["actions"], flows=model["flows"]
        )
        reasoning = classify_reasoning_level(task)
        return {
            "task": task,
            "elements": model["elements"],
            "flows": model["flows"],
            "actions": model["actions"],
            "complexity": complexity,
            "reasoning": reasoning,
        }

    def test_simple_rename(self):
        r = self._analyze("rename the variable foo to bar")
        self.assertEqual(r["complexity"], "DIRECT")
        self.assertIn(r["reasoning"], ["haiku", "sonnet"])

    def test_docker_build(self):
        r = self._analyze("build a Docker container for the web service")
        elem_types = [e["type"] for e in r["elements"]]
        self.assertIn("container", elem_types)

    def test_api_with_database(self):
        r = self._analyze("create a REST API that reads from PostgreSQL database")
        elem_types = [e["type"] for e in r["elements"]]
        self.assertTrue(
            any(t in elem_types for t in ["api", "service"]),
            f"Expected api or service, got {elem_types}",
        )
        self.assertIn("database", elem_types)

    def test_security_scan(self):
        r = self._analyze("run a security vulnerability scan on the codebase")
        action_verbs = [a["verb"] for a in r["actions"]]
        self.assertTrue(
            any(v in action_verbs for v in ["analyze", "test", "verify"]),
            f"Expected security action verb, got {action_verbs}",
        )

    def test_complex_architecture(self):
        r = self._analyze(
            "redesign the microservice architecture: migrate the database, "
            "update the API gateway, containerize all services, and set up CI/CD"
        )
        self.assertEqual(r["complexity"], "FULL")
        self.assertEqual(r["reasoning"], "opus")

    def test_ci_cd_pipeline(self):
        r = self._analyze("set up a CI/CD pipeline with GitHub Actions")
        self.assertTrue(len(r["flows"]) > 0 or len(r["elements"]) > 0)

    def test_monitoring_setup(self):
        r = self._analyze("add Prometheus monitoring to the Kubernetes cluster")
        elem_types = [e["type"] for e in r["elements"]]
        self.assertTrue(
            any(t in elem_types for t in [
                "infrastructure", "service", "config", "container"
            ]),
            f"Expected infra-related element, got {elem_types}",
        )


if __name__ == "__main__":
    unittest_main(verbosity=2)
