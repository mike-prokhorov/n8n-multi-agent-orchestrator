"""Contract tests for the exported n8n workflows.

They check what breaks silently after an export or an edit:
the router's labels must match the dispatcher's branches, every
cross-workflow call must point at a workflow in this repo, and no
secret or instance-specific id may leave the author's n8n.
Run: python -m unittest discover -s tests
"""
import json
import re
import unittest
from pathlib import Path

WF_DIR = Path(__file__).resolve().parent.parent / "workflows"
FILES = sorted(WF_DIR.glob("*.json"))
WORKFLOWS = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in FILES}
PLACEHOLDER = re.compile(r"^<[a-z0-9-]+>$")

SECRET_PATTERNS = {
    "Telegram bot token": re.compile(r"\d{6,}:AA[A-Za-z0-9_-]{30,}|:AA[A-Za-z0-9_-]{30,}"),
    "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "JWT / Supabase key": re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"),
    "Bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
}


def nodes(name):
    return WORKFLOWS[name]["nodes"]


def switch_keys(workflow, node_name):
    node = next(n for n in nodes(workflow) if n["name"] == node_name)
    return {rule["outputKey"] for rule in node["parameters"]["rules"]["values"]}


class WorkflowContract(unittest.TestCase):
    def test_six_workflows_present(self):
        self.assertEqual(len(FILES), 6, [p.name for p in FILES])

    def test_connections_point_to_existing_nodes(self):
        for name, wf in WORKFLOWS.items():
            names = {n["name"] for n in wf["nodes"]}
            for source, outputs in wf.get("connections", {}).items():
                self.assertIn(source, names, f"{name}: unknown source {source!r}")
                for branch in outputs.values():
                    for targets in branch:
                        for target in targets or []:
                            self.assertIn(target["node"], names, f"{name}: {source} -> {target['node']}")

    def test_router_labels_match_dispatcher_branches(self):
        parser = next(n for n in nodes("02_ai_classifier.json") if n["type"].endswith("outputParserStructured"))
        schema = json.loads(parser["parameters"]["inputSchema"])["properties"]
        intents = set(schema["intent"]["enum"])
        departments = {d for d in schema["department"]["enum"] if d is not None}
        self.assertEqual(intents, switch_keys("03_action.json", "Switch by Intent"))
        self.assertEqual(departments, switch_keys("03_action.json", "Switch Department"))

    def test_sub_workflow_calls_target_workflows_in_repo(self):
        repo_names = {wf["name"] for wf in WORKFLOWS.values()}
        calls = [n for n in nodes("06_qualifier.json") if n["type"].endswith("executeWorkflow")]
        self.assertEqual(len(calls), 5)
        for node in calls:
            target = node["parameters"]["workflowId"].get("cachedResultName")
            self.assertIn(target, repo_names, f"{node['name']} calls a workflow that is not in this repo")

    def test_no_secrets_in_any_file(self):
        for name in WORKFLOWS:
            text = (WF_DIR / name).read_text(encoding="utf-8")
            for label, pattern in SECRET_PATTERNS.items():
                self.assertIsNone(pattern.search(text), f"{name}: looks like a {label}")

    def test_instance_ids_are_placeholders(self):
        for name, wf in WORKFLOWS.items():
            self.assertFalse(wf.get("staticData"), f"{name}: staticData is runtime state")
            self.assertFalse(wf.get("pinData"), f"{name}: pinData holds real executions")
            for n in wf["nodes"]:
                for cred in (n.get("credentials") or {}).values():
                    self.assertRegex(str(cred.get("id")), PLACEHOLDER, f"{name}/{n['name']}: credential id")
                if n.get("webhookId"):
                    self.assertRegex(n["webhookId"], PLACEHOLDER, f"{name}/{n['name']}: webhookId")
                if n["type"].endswith("executeWorkflow"):
                    ref = n["parameters"]["workflowId"]
                    self.assertRegex(str(ref.get("value")), PLACEHOLDER, f"{name}/{n['name']}: workflowId")
                    self.assertNotIn("cachedResultUrl", ref, f"{name}/{n['name']}: instance URL")


if __name__ == "__main__":
    unittest.main()
