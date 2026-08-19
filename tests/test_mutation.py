from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from praxis_dev import cli
from praxis_dev import mutation
from praxis_dev import schema_validation as sv
from praxis_dev.mutation import (
    build_init_plan,
    classify_state,
    jcs,
    observe_targets,
    plan_fingerprint,
    sha256_digest,
    template_contents,
)
from praxis_dev.plan_schema import PLAN_SCHEMA, _PLAN_SCHEMA_JSON

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "4f352068-06ad-5ea5-98c3-c27e7b84d47e"
NOW = "2026-08-19T00:00:00Z"


class SchemaSyncTests(unittest.TestCase):
    def test_embedded_schema_matches_canonical_file(self) -> None:
        canonical = (ROOT / "schemas" / "plan.schema.json").read_text(encoding="utf-8")
        self.assertEqual(_PLAN_SCHEMA_JSON, canonical)

    def test_embedded_schema_is_valid_json_object(self) -> None:
        self.assertIsInstance(PLAN_SCHEMA, dict)
        self.assertEqual(PLAN_SCHEMA["title"], "Praxis governed mutation plan v1")


class JcsTests(unittest.TestCase):
    def test_sorts_keys_recursively(self) -> None:
        self.assertEqual(jcs({"b": 1, "a": {"d": 2, "c": 3}}), '{"a":{"c":3,"d":2},"b":1}')

    def test_compact_separators_and_minimal_escaping(self) -> None:
        self.assertEqual(jcs({"k": "é\"x\n"}), '{"k":"é\\"x\\n"}')

    def test_preserves_insertion_independence(self) -> None:
        self.assertEqual(jcs({"a": 1, "b": 2}), jcs({"b": 2, "a": 1}))

    def test_rejects_floats(self) -> None:
        with self.assertRaises(TypeError):
            jcs({"a": 1.5})
        with self.assertRaises(TypeError):
            jcs({"a": [{"b": 0.1}]})

    def test_none_bool_int(self) -> None:
        self.assertEqual(jcs([None, True, False, 0]), "[null,true,false,0]")


class PlanBuilderTests(unittest.TestCase):
    def _fresh_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_fresh_repo_yields_schema_valid_create_plan(self) -> None:
        repo = self._fresh_repo()
        plan, classification, _ = build_init_plan(
            repo, project_id=PROJECT_ID, now=NOW
        )
        self.assertEqual(classification, "create")
        diagnostics = sv.validate(plan, PLAN_SCHEMA)
        self.assertEqual(diagnostics, [], [str(d) for d in diagnostics])
        self.assertEqual(len(plan["actions"]), 5)
        self.assertTrue(all(a["kind"] == "create" for a in plan["actions"]))
        self.assertEqual(plan["canonicalization"], "RFC8785")
        self.assertEqual(plan["required_authority"], "development-advisory")

    def test_fingerprint_is_self_consistent(self) -> None:
        repo = self._fresh_repo()
        plan, _, _ = build_init_plan(repo, project_id=PROJECT_ID, now=NOW)
        self.assertEqual(plan["plan_fingerprint"], plan_fingerprint(plan))
        # and it is NOT the digest of the plan including its own fingerprint
        with_self = sha256_digest(jcs(plan))
        self.assertNotEqual(plan["plan_fingerprint"], with_self)

    def test_deterministic_given_same_state_and_inputs(self) -> None:
        repo = self._fresh_repo()
        one, _, _ = build_init_plan(repo, project_id=PROJECT_ID, now=NOW)
        two, _, _ = build_init_plan(repo, project_id=PROJECT_ID, now=NOW)
        self.assertEqual(one, two)

    def test_drift_changes_observed_fingerprint(self) -> None:
        repo = self._fresh_repo()
        before, _, _ = build_init_plan(repo, project_id=PROJECT_ID, now=NOW)
        (repo / "AGENTS.md").write_text("foreign\n", encoding="utf-8")
        after, classification, _ = build_init_plan(
            repo, project_id=PROJECT_ID, now=NOW
        )
        self.assertEqual(classification, "conflict")
        self.assertNotEqual(
            before["observed_state"]["fingerprint"],
            after["observed_state"]["fingerprint"],
        )

    def test_classify_identical_when_all_targets_match_template(self) -> None:
        repo = self._fresh_repo()
        contents = template_contents(PROJECT_ID)
        for rel, text in contents.items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        plan, classification, _ = build_init_plan(repo, now=NOW)
        self.assertEqual(classification, "identical")

    def test_classify_conflict_on_unparseable_config(self) -> None:
        repo = self._fresh_repo()
        (repo / ".praxis.toml").write_text("not [ valid toml", encoding="utf-8")
        _, classification, _ = build_init_plan(repo, now=NOW)
        self.assertEqual(classification, "conflict")

    def test_classify_conflict_on_partial_targets(self) -> None:
        repo = self._fresh_repo()
        contents = template_contents(PROJECT_ID)
        (repo / ".praxis.toml").write_text(
            contents[".praxis.toml"], encoding="utf-8"
        )
        _, classification, _ = build_init_plan(repo, now=NOW)
        self.assertEqual(classification, "conflict")

    def test_existing_identity_drives_template_rendering(self) -> None:
        repo = self._fresh_repo()
        contents = template_contents(PROJECT_ID)
        for rel, text in contents.items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        # no injected project_id: identity must come from .praxis.toml
        plan, classification, _ = build_init_plan(repo, now=NOW)
        self.assertEqual(classification, "identical")
        self.assertEqual(plan["project"]["project_id"], PROJECT_ID)

    def test_classify_state_unit(self) -> None:
        expected = {rel: sha256_digest(t) for rel, t in template_contents("x").items()}
        self.assertEqual(classify_state({}, template_contents("x")), "create")
        self.assertEqual(classify_state(dict(expected), template_contents("x")), "identical")
        partial = {".praxis.toml": expected[".praxis.toml"]}
        self.assertEqual(classify_state(partial, template_contents("x")), "conflict")
        foreign = {".praxis.toml": "sha256:" + "0" * 64}
        self.assertEqual(classify_state(foreign, template_contents("x")), "conflict")

    def test_action_digests_match_template_bytes(self) -> None:
        repo = self._fresh_repo()
        plan, _, contents = build_init_plan(repo, project_id=PROJECT_ID, now=NOW)
        by_path = {a["path"]: a for a in plan["actions"]}
        for rel, text in contents.items():
            self.assertEqual(by_path[rel]["content_sha256"], sha256_digest(text))
        post = {c["subject"]: c["expected"] for c in plan["postconditions"]}
        for rel, text in contents.items():
            self.assertEqual(post[rel], sha256_digest(text))


class CliInitPlanTests(unittest.TestCase):
    def _fresh_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_create_writes_schema_valid_plan_and_envelope(self) -> None:
        repo = self._fresh_repo()
        plan_path = repo / "plan.json"
        rc, out, err = cli.run(
            ["project", "init-plan", str(repo), "--output", str(plan_path), "--format", "json"]
        )
        self.assertEqual(rc, cli.EXIT_PASS, err)
        envelope = json.loads(out)
        self.assertEqual(envelope["schema"], "praxis/init-plan-result/v1")
        self.assertEqual(envelope["result"], "create")
        self.assertEqual(envelope["diagnostics"], [])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(sv.validate(plan, PLAN_SCHEMA), [])
        self.assertEqual(envelope["plan_fingerprint"], plan["plan_fingerprint"])

    def test_identical_exit_zero_without_plan_file(self) -> None:
        repo = self._fresh_repo()
        for rel, text in template_contents(PROJECT_ID).items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        plan_path = repo / "plan.json"
        rc, out, _ = cli.run(
            ["project", "init-plan", str(repo), "--output", str(plan_path)]
        )
        self.assertEqual(rc, cli.EXIT_PASS)
        self.assertIn("identical", out)
        self.assertFalse(plan_path.exists())

    def test_conflict_exit_fail_without_plan_file(self) -> None:
        repo = self._fresh_repo()
        (repo / "AGENTS.md").write_text("existing contract\n", encoding="utf-8")
        plan_path = repo / "plan.json"
        rc, out, _ = cli.run(
            ["project", "init-plan", str(repo), "--output", str(plan_path), "--format", "json"]
        )
        self.assertEqual(rc, cli.EXIT_FAIL)
        self.assertEqual(json.loads(out)["result"], "conflict")
        self.assertFalse(plan_path.exists())

    def test_missing_output_is_usage_error(self) -> None:
        repo = self._fresh_repo()
        rc, _, _ = cli.run(["project", "init-plan", str(repo)])
        self.assertEqual(rc, cli.EXIT_USAGE)

    def test_existing_output_is_usage_error(self) -> None:
        repo = self._fresh_repo()
        existing = repo / "plan.json"
        existing.write_text("{}", encoding="utf-8")
        rc, _, _ = cli.run(
            ["project", "init-plan", str(repo), "--output", str(existing)]
        )
        self.assertEqual(rc, cli.EXIT_USAGE)

    def test_missing_repo_argument_is_usage_error(self) -> None:
        rc, _, _ = cli.run(["project", "init-plan", "--output", "/tmp/x.json"])
        self.assertEqual(rc, cli.EXIT_USAGE)

    def test_repo_not_found_is_usage_error(self) -> None:
        rc, _, _ = cli.run(
            ["project", "init-plan", "/nonexistent/repo", "--output", "/tmp/x.json"]
        )
        self.assertEqual(rc, cli.EXIT_USAGE)

    def test_no_repo_mutation_during_planning(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as sibling:
            repo = self._fresh_repo()
            before = sorted(os.listdir(repo))
            plan_path = Path(sibling) / "plan.json"
            cli.run(["project", "init-plan", str(repo), "--output", str(plan_path)])
            after = sorted(os.listdir(repo))
            self.assertEqual(before, after)


class ApplyRoundTripTests(unittest.TestCase):
    """Full plan -> apply cycle and its adversarial paths."""

    def _fresh_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _plan_for(self, repo: Path, **kwargs) -> tuple[Path, str]:
        plan_path = repo / "plan.json"
        rc, out, _ = cli.run(
            ["project", "init-plan", str(repo), "--output", str(plan_path), "--format", "json"]
        )
        self.assertEqual(rc, cli.EXIT_PASS)
        envelope = json.loads(out)
        return plan_path, envelope["plan_fingerprint"]

    def _apply(self, repo: Path, plan_path: Path, fingerprint: str):
        return cli.run(
            [
                "project", "init-apply", str(repo),
                "--plan", str(plan_path),
                "--expected-fingerprint", fingerprint,
                "--format", "json",
            ]
        )

    def test_happy_path_applies_exact_template_bytes(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        rc, out, err = self._apply(repo, plan_path, fp)
        self.assertEqual(rc, 0, err)
        self.assertIn("applied", out)
        import tomllib

        config = tomllib.loads((repo / ".praxis.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["schema"], "praxis/project-config/v1")
        for rel in mutation.TARGET_FILES:
            self.assertTrue((repo / rel).is_file(), rel)

    def test_second_apply_is_drift_exit_five(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        self._apply(repo, plan_path, fp)
        rc, out, _ = self._apply(repo, plan_path, fp)
        self.assertEqual(rc, 5)
        self.assertIn("drift", out)

    def test_wrong_fingerprint_rejected_exit_five(self) -> None:
        repo = self._fresh_repo()
        plan_path, _ = self._plan_for(repo)
        bogus = "sha256:" + "0" * 64
        rc, out, _ = self._apply(repo, plan_path, bogus)
        self.assertEqual(rc, 5)
        self.assertIn("fingerprint-rejected", out)
        # nothing was written
        for rel in mutation.TARGET_FILES:
            self.assertFalse((repo / rel).exists(), rel)

    def test_drift_between_plan_and_apply_aborts(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        (repo / "AGENTS.md").write_text("intruder\n", encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, fp)
        self.assertEqual(rc, 5)
        self.assertIn("drift", out)

    def test_tampered_plan_body_fingerprint_mismatch(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["allowed_paths"].append("evil.sh")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, fp)
        self.assertEqual(rc, 2)
        self.assertIn("fingerprint", out)

    def test_arbitrary_content_rejected(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        # Forge payload: keep structure, replace content digest of a stub.
        evil = "sha256:" + "e" * 64
        for action in plan["actions"]:
            if action["path"] == "POLICY.md":
                action["content_sha256"] = evil
        # recompute fingerprint to pass the fingerprint gate...
        plan.pop("plan_fingerprint")
        plan["plan_fingerprint"] = mutation.plan_fingerprint(plan)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, plan["plan_fingerprint"])
        outcome = json.loads(out)
        self.assertEqual(rc, 2)
        self.assertIn("noncanonical", out)
        # POLICY.md must not exist; earlier actions are honestly reported.
        self.assertFalse((repo / "POLICY.md").exists())
        applied = outcome.get("applied_actions", [])
        self.assertIn("create-1-.praxis.toml", applied)
        self.assertNotIn("create-3-POLICY.md", applied)

    def test_path_escape_rejected(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["actions"][1]["path"] = "../outside.md"
        plan["allowed_paths"].append("../outside.md")
        plan.pop("plan_fingerprint")
        plan["plan_fingerprint"] = mutation.plan_fingerprint(plan)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, plan["plan_fingerprint"])
        self.assertEqual(rc, 2)
        self.assertIn("invalid-plan", out)
        self.assertFalse((repo.parent / "outside.md").exists())

    def test_symlink_ancestor_refused(self) -> None:
        repo = self._fresh_repo()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        link_root = repo / "decisions"
        link_root.symlink_to(Path(outside.name), target_is_directory=True)
        plan_path, fp = self._plan_for(repo)  # observe follows no symlinks for digests
        rc, out, _ = self._apply(repo, plan_path, fp)
        # The symlinked dir must never receive our writes.
        self.assertNotEqual(rc, 0)
        self.assertEqual(sorted(p.name for p in Path(outside.name).iterdir()), [])

    def test_symlink_target_refused(self) -> None:
        repo = self._fresh_repo()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (repo / "POLICY.md").symlink_to(Path(outside.name) / "captured.md")
        plan_path, fp = self._plan_for(repo)
        rc, out, _ = self._apply(repo, plan_path, fp)
        self.assertNotEqual(rc, 0)
        self.assertFalse((Path(outside.name) / "captured.md").exists())

    def test_unparseable_plan_is_usage_error(self) -> None:
        repo = self._fresh_repo()
        plan_path = repo / "plan.json"
        plan_path.write_text("{not json", encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, "sha256:" + "0" * 64)
        self.assertEqual(rc, 2)
        self.assertIn("invalid-plan", out)

    def test_duplicate_json_keys_rejected(self) -> None:
        repo = self._fresh_repo()
        plan_path = repo / "plan.json"
        plan_path.write_text('{"a":1,"a":2}', encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, "sha256:" + "0" * 64)
        self.assertEqual(rc, 2)

    def test_missing_plan_file_is_rejected_cleanly(self) -> None:
        repo = self._fresh_repo()
        rc, out, _ = self._apply(repo, repo / "nope.json", "sha256:" + "0" * 64)
        self.assertEqual(rc, 2)
        self.assertIn("invalid-plan", out)

    def test_wrong_operation_rejected(self) -> None:
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["operation"] = "project-upgrade"
        plan.pop("plan_fingerprint")
        plan["plan_fingerprint"] = mutation.plan_fingerprint(plan)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rc, out, _ = self._apply(repo, plan_path, plan["plan_fingerprint"])
        self.assertEqual(rc, 2)
        self.assertIn("operation", out)

    def test_apply_leaves_no_plan_inside_repo_targets(self) -> None:
        # plan.json lives in repo but outside TARGET_FILES: allowed, and apply
        # must not touch it beyond reading.
        repo = self._fresh_repo()
        plan_path, fp = self._plan_for(repo)
        before = plan_path.read_bytes()
        self._apply(repo, plan_path, fp)
        self.assertEqual(plan_path.read_bytes(), before)

    def test_usage_missing_flags(self) -> None:
        repo = self._fresh_repo()
        rc, _, _ = cli.run(["project", "init-apply", str(repo)])
        self.assertEqual(rc, cli.EXIT_USAGE)
        rc, _, _ = cli.run(["project", "init-apply", str(repo), "--plan", "x.json"])
        self.assertEqual(rc, cli.EXIT_USAGE)
        rc, _, _ = cli.run(
            ["project", "init-apply", str(repo), "--plan", "x.json",
             "--expected-fingerprint", "not-a-sha"]
        )
        self.assertEqual(rc, cli.EXIT_USAGE)


class ProfileRoundTripTests(unittest.TestCase):
    def test_non_default_profile_applies(self) -> None:
        import tomllib

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            # Plan for a standard-profile project by pre-rendering identity
            # is not possible via CLI (uuid random); use the builder API.
            plan, classification, _ = mutation.build_init_plan(
                repo, project_id=PROJECT_ID, profile="standard", now=NOW
            )
            self.assertEqual(classification, "create")
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            rc, out, err = cli.run(
                [
                    "project", "init-apply", str(repo),
                    "--plan", str(plan_path),
                    "--expected-fingerprint", plan["plan_fingerprint"],
                ]
            )
            self.assertEqual(rc, 0, err)
            config = tomllib.loads((repo / ".praxis.toml").read_text(encoding="utf-8"))
            self.assertEqual(config["profile"], "standard")


class AdversarialRegressionTests(unittest.TestCase):
    """Regression tests for attacks found in the adversarial round."""

    PID = "4f352068-06ad-5ea5-98c3-c27e7b84d47e"

    def _fresh_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _plan_in(self, repo: Path, **overrides) -> tuple[Path, dict]:
        plan, classification, _ = mutation.build_init_plan(
            repo, project_id=self.PID, now=NOW
        )
        self.assertEqual(classification, "create")
        plan.update(overrides)
        plan.pop("plan_fingerprint")
        plan["plan_fingerprint"] = mutation.plan_fingerprint(plan)
        plan_path = repo / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan_path, plan

    def test_expired_plan_rejected_as_drift(self) -> None:
        repo = self._fresh_repo()
        plan_path, plan = self._plan_in(repo, expires_at="2020-01-01T00:00:00Z")
        outcome, code = mutation.apply_init_plan(repo, plan_path, plan["plan_fingerprint"])
        self.assertEqual(code, 5)
        self.assertEqual(outcome["diagnostics"][0]["code"], "plan-expired")
        for rel in mutation.TARGET_FILES:
            self.assertFalse((repo / rel).exists(), rel)

    def test_manipulated_authority_rejected(self) -> None:
        repo = self._fresh_repo()
        plan_path, plan = self._plan_in(repo, required_authority="superuser-bypass")
        outcome, code = mutation.apply_init_plan(repo, plan_path, plan["plan_fingerprint"])
        self.assertEqual(code, 2)
        self.assertEqual(outcome["diagnostics"][0]["code"], "plan-authority-unsupported")
        for rel in mutation.TARGET_FILES:
            self.assertFalse((repo / rel).exists(), rel)

    def test_covert_path_traversal_rejected(self) -> None:
        repo = self._fresh_repo()
        plan, _, _ = mutation.build_init_plan(repo, project_id=self.PID, now=NOW)
        for action in plan["actions"]:
            if action["path"] == "POLICY.md":
                action["path"] = "POLICY.md/../../evil.md"
        plan["allowed_paths"].append("POLICY.md/../../evil.md")
        plan.pop("plan_fingerprint")
        plan["plan_fingerprint"] = mutation.plan_fingerprint(plan)
        plan_path = repo / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        outcome, code = mutation.apply_init_plan(repo, plan_path, plan["plan_fingerprint"])
        self.assertNotEqual(code, 0)
        self.assertFalse((repo / "evil.md").exists())
        self.assertFalse((repo.parent / "evil.md").exists())

    def test_naive_expiry_rejected_by_schema(self) -> None:
        # A naive timestamp (no timezone) violates the schema's date-time
        # format first; the runtime _check_expiry is defense in depth.
        repo = self._fresh_repo()
        plan_path, plan = self._plan_in(repo, expires_at="2020-01-01T00:00:00")
        outcome, code = mutation.apply_init_plan(repo, plan_path, plan["plan_fingerprint"])
        self.assertEqual(code, 2)
        self.assertEqual(outcome["result"], "invalid-plan")
        for rel in mutation.TARGET_FILES:
            self.assertFalse((repo / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
