from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_praxis_pyz import build

ROOT = Path(__file__).resolve().parents[1]
WORKTREE = ROOT


class BuildPyzTests(unittest.TestCase):
    def test_build_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = build(Path(tmp) / "a" / "praxis.pyz")
            second = build(Path(tmp) / "b" / "praxis.pyz")
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
                "zipapp build is not byte-reproducible",
            )

    def test_pyz_has_shebang_and_no_jsonschema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = build(Path(tmp) / "praxis.pyz")
            raw = target.read_bytes()
            self.assertTrue(raw.startswith(b"#!/usr/bin/env python3.12\n"))
            import zipfile

            names = zipfile.ZipFile(target).namelist()
            self.assertIn("__main__.py", names)
            self.assertIn("praxis_dev/cli.py", names)
            self.assertFalse(
                any("jsonschema" in name for name in names),
                "zipapp must not bundle jsonschema",
            )

    def test_pyz_runs_status_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = build(Path(tmp) / "praxis.pyz")
            proc = subprocess.run(
                [sys.executable, str(target), "project", "status", str(WORKTREE), "--format", "json"],
                capture_output=True,
                text=True,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        obj = json.loads(proc.stdout)
        self.assertEqual(obj["schema"], "praxis/project-status/v1")

    def test_pyz_runs_audit_json_and_satisfies_schema(self) -> None:
        from praxis_dev import schema_validation as sv

        audit_schema = json.loads((ROOT / "schemas" / "audit-result.schema.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            target = build(Path(tmp) / "praxis.pyz")
            proc = subprocess.run(
                [sys.executable, str(target), "project", "audit", str(WORKTREE), "--format", "json"],
                capture_output=True,
                text=True,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        obj = json.loads(proc.stdout)
        self.assertEqual(obj["schema"], "praxis/audit-result/v1")
        self.assertEqual(sv.validate(obj, audit_schema), [])

    def test_pyz_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = build(Path(tmp) / "praxis.pyz")
            no_args = subprocess.run([sys.executable, str(target)], capture_output=True, text=True)
            bad_fmt = subprocess.run(
                [sys.executable, str(target), "project", "audit", str(WORKTREE), "--format", "yaml"],
                capture_output=True,
                text=True,
            )
        self.assertEqual(no_args.returncode, 2)
        self.assertEqual(bad_fmt.returncode, 2)


if __name__ == "__main__":
    unittest.main()
