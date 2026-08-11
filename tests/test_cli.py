from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from praxis_dev import cli
from praxis_dev import schema_validation as sv

ROOT = Path(__file__).resolve().parents[1]
WORKTREE = ROOT
AUDIT_SCHEMA = json.loads((ROOT / "schemas" / "audit-result.schema.json").read_text(encoding="utf-8"))
CONFIG_SCHEMA_SRC = ROOT / "schemas" / "project-config.schema.json"

_VALID_CONFIG = """\
schema = "praxis/project-config/v1"
project_id = "4f352068-06ad-5ea5-98c3-c27e7b84d47e"
standard_version = "0.1.0-draft.1"
profile = "standard"
lifecycle = "development"

[modules]
core = "v1"

[paths]
agent_contract = "AGENTS.md"
policy = "POLICY.md"
decisions = "decisions"
specs = "specs"

[authority]
provider = "github-oauth-web/v1"
enforcement = "advisory"
"""


def _valid_audit_result(obj: dict) -> list:
    return sv.validate(obj, AUDIT_SCHEMA)


class AuditPositiveTests(unittest.TestCase):
    def test_audit_pass_on_worktree_json(self) -> None:
        rc, out, err = cli.run(["project", "audit", str(WORKTREE), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)  # raises if stdout is not pure JSON
        self.assertEqual(obj["schema"], "praxis/audit-result/v1")
        self.assertEqual(obj["result"], "pass")
        self.assertEqual(obj["findings"], [])
        self.assertTrue(obj["observed_at"].endswith("Z"))
        self.assertEqual(_valid_audit_result(obj), [])

    def test_audit_human_is_not_json(self) -> None:
        rc, out, err = cli.run(["project", "audit", str(WORKTREE)])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        self.assertNotIn("{", out)
        self.assertIn("praxis project audit", out)


class StatusTests(unittest.TestCase):
    def test_status_json_shape(self) -> None:
        rc, out, err = cli.run(["project", "status", str(WORKTREE), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertEqual(obj["schema"], "praxis/project-status/v1")
        self.assertTrue(obj["config_present"])
        self.assertTrue(obj["config_parseable"])
        self.assertIsNone(obj["config_error"])
        self.assertTrue(obj["observed_at"].endswith("Z"))

    def test_status_human(self) -> None:
        rc, out, err = cli.run(["project", "status", str(WORKTREE)])
        self.assertEqual(rc, cli.EXIT_PASS)
        self.assertNotIn("{", out)

    def test_status_missing_config_reports_absent_and_unparseable(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            Path(repo, "README.md").write_text("not a praxis repo")  # no .praxis.toml
            rc, out, err = cli.run(["project", "status", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertFalse(obj["config_present"])
        self.assertFalse(obj["config_parseable"])


class ConfigFailureTests(unittest.TestCase):
    def test_audit_missing_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            Path(repo, "AGENTS.md").write_text("x")  # an existing, non-praxis dir
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_FAIL, err)
        obj = json.loads(out)
        self.assertEqual(obj["result"], "fail")
        self.assertIn("config-missing", [f["id"] for f in obj["findings"]])
        self.assertEqual(_valid_audit_result(obj), [])

    def test_audit_malformed_config_is_usage_error_without_json(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            Path(repo, ".praxis.toml").write_text("this is = = broken {{{")
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_USAGE, err)
        self.assertEqual(out, "")  # no JSON object on contract error
        self.assertIn("malformed", err.lower())

    def test_audit_schema_invalid_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            self._seed_schema(repo)
            config = _VALID_CONFIG.replace('profile = "standard"', 'profile = "bogus"')
            Path(repo, ".praxis.toml").write_text(config)
            Path(repo, "AGENTS.md").write_text("x")
            Path(repo, "POLICY.md").write_text("x")
            Path(repo, "decisions").mkdir()
            Path(repo, "specs").mkdir()
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_FAIL, err)
        obj = json.loads(out)
        self.assertEqual(obj["result"], "fail")
        ids = [f["id"] for f in obj["findings"]]
        self.assertTrue(ids, "expected at least one finding")
        self.assertEqual(_valid_audit_result(obj), [])

    def test_audit_missing_declared_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            self._seed_schema(repo)
            Path(repo, ".praxis.toml").write_text(_VALID_CONFIG)
            Path(repo, "AGENTS.md").write_text("x")
            # POLICY.md, decisions/, specs/ deliberately absent
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_FAIL, err)
        obj = json.loads(out)
        ids = [f["id"] for f in obj["findings"]]
        self.assertIn("path-policy", ids)
        self.assertIn("path-decisions", ids)
        self.assertEqual(_valid_audit_result(obj), [])

    @staticmethod
    def _seed_schema(repo: str) -> None:
        target = Path(repo, "schemas")
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONFIG_SCHEMA_SRC, target / "project-config.schema.json")


class SchemaUnavailableTests(unittest.TestCase):
    """When the config contract cannot be validated (schema missing/unreadable/
    invalid JSON), audit MUST be inconclusive (rc 3), never pass or fail."""

    @staticmethod
    def _seed_valid_project(repo: Path) -> None:
        (repo / ".praxis.toml").write_text(_VALID_CONFIG)
        (repo / "AGENTS.md").write_text("x")
        (repo / "POLICY.md").write_text("x")
        (repo / "decisions").mkdir()
        (repo / "specs").mkdir()

    def test_schema_missing_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            self._seed_valid_project(Path(repo))  # valid config + paths, no schemas/
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_INCONCLUSIVE, err)
        obj = json.loads(out)
        self.assertEqual(obj["result"], "inconclusive")
        self.assertIn("standard-schema-unavailable",
                      [d["code"] for d in obj["diagnostics"]])
        self.assertEqual(_valid_audit_result(obj), [])

    def test_schema_invalid_json_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            self._seed_valid_project(Path(repo))
            schemas = Path(repo, "schemas")
            schemas.mkdir(parents=True, exist_ok=True)
            (schemas / "project-config.schema.json").write_text("{not valid json")
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_INCONCLUSIVE, err)
        obj = json.loads(out)
        self.assertEqual(obj["result"], "inconclusive")
        self.assertIn("standard-schema-unavailable",
                      [d["code"] for d in obj["diagnostics"]])
        self.assertEqual(_valid_audit_result(obj), [])

    def test_schema_semantically_unsupported_is_inconclusive(self) -> None:
        # Valid JSON, but the closed validator rejects it (unknown keyword).
        # The audit must be inconclusive and must NOT derive config findings.
        with tempfile.TemporaryDirectory() as repo:
            self._seed_valid_project(Path(repo))
            schemas = Path(repo, "schemas")
            schemas.mkdir(parents=True, exist_ok=True)
            (schemas / "project-config.schema.json").write_text(
                '{"not-a-schema": true}'
            )
            rc, out, err = cli.run(["project", "audit", repo, "--format", "json"])
        self.assertEqual(rc, cli.EXIT_INCONCLUSIVE, err)
        obj = json.loads(out)
        self.assertEqual(obj["result"], "inconclusive")
        self.assertIn("standard-schema-unavailable",
                      [d["code"] for d in obj["diagnostics"]])
        config_ids = [f["id"] for f in obj["findings"] if f["id"].startswith("config-")]
        self.assertEqual(config_ids, [])
        self.assertEqual(_valid_audit_result(obj), [])


class ExitCodeTests(unittest.TestCase):
    def test_no_args(self) -> None:
        self.assertEqual(cli.run([])[0], cli.EXIT_USAGE)

    def test_unknown_domain(self) -> None:
        self.assertEqual(cli.run(["nope"])[0], cli.EXIT_USAGE)

    def test_unknown_operation(self) -> None:
        self.assertEqual(cli.run(["project", "nope"])[0], cli.EXIT_USAGE)

    def test_bad_format(self) -> None:
        self.assertEqual(cli.run(["project", "audit", str(WORKTREE), "--format", "yaml"])[0], cli.EXIT_USAGE)

    def test_format_missing_value(self) -> None:
        self.assertEqual(cli.run(["project", "audit", str(WORKTREE), "--format"])[0], cli.EXIT_USAGE)

    def test_bad_profile(self) -> None:
        self.assertEqual(cli.run(["project", "audit", str(WORKTREE), "--profile", "nonsense"])[0], cli.EXIT_USAGE)

    def test_profile_on_status_rejected(self) -> None:
        self.assertEqual(cli.run(["project", "status", str(WORKTREE), "--profile", "standard"])[0], cli.EXIT_USAGE)

    def test_repo_not_found(self) -> None:
        self.assertEqual(cli.run(["project", "audit", "/nonexistent/praxis/repo/xyz"])[0], cli.EXIT_USAGE)

    def test_extra_positional(self) -> None:
        self.assertEqual(cli.run(["project", "audit", str(WORKTREE), str(WORKTREE)])[0], cli.EXIT_USAGE)


class JsonPurityTests(unittest.TestCase):
    def test_audit_json_stdout_is_pure_object(self) -> None:
        rc, out, err = cli.run(["project", "audit", str(WORKTREE), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS)
        obj = json.loads(out)
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj["schema"], "praxis/audit-result/v1")

    def test_status_json_stdout_is_pure_object(self) -> None:
        rc, out, err = cli.run(["project", "status", str(WORKTREE), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS)
        obj = json.loads(out)
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj["schema"], "praxis/project-status/v1")


class NoMutationTests(unittest.TestCase):
    _SKIP = {".git", "__pycache__", ".pytest_cache", "dist"}

    def _snapshot(self, repo: Path) -> dict[str, tuple[int, int, str]]:
        snapshot: dict[str, tuple[int, int, str]] = {}
        for path in repo.rglob("*"):
            if any(part in self._SKIP for part in path.relative_to(repo).parts):
                continue
            if not path.is_file():
                continue
            rel = path.relative_to(repo).as_posix()
            stat = path.stat()
            snapshot[rel] = (stat.st_size, stat.st_mtime_ns, hashlib_sha256(path))
        return snapshot

    def test_audit_and_status_do_not_mutate_repo(self) -> None:
        before = self._snapshot(WORKTREE)
        cli.run(["project", "audit", str(WORKTREE)])
        cli.run(["project", "status", str(WORKTREE)])
        after = self._snapshot(WORKTREE)
        self.assertEqual(before, after)


class ModuleInvocationTests(unittest.TestCase):
    def test_python_m_praxis_dev_status(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "praxis_dev", "project", "status", str(WORKTREE), "--format", "json"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["schema"], "praxis/project-status/v1")


def hashlib_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
