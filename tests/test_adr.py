from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from praxis_dev import adr
from praxis_dev import cli
from praxis_dev import schema_validation as sv

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCHEMA = json.loads((ROOT / "schemas/audit-result.schema.json").read_text(encoding="utf-8"))

ALL_HEADINGS = (
    "Contexto y problema",
    "Alcance y no objetivos",
    "Drivers e invariantes",
    "Opciones consideradas",
    "Decisión",
    "Consecuencias",
    "Seguridad, migración y reversibilidad",
    "Confirmación",
    "Relaciones con ADR, SPEC e implementación",
    "Disparadores de revisión",
    "Referencias y evidencia",
)
_TIMESTAMP = "2026-08-11T00:00:00Z"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _transitions(status: str, at: str = _TIMESTAMP) -> list[dict]:
    chain: list[tuple] = [(None, "draft")]
    extra = {
        "draft": [],
        "proposed": [("draft", "proposed")],
        "accepted": [("draft", "proposed"), ("proposed", "accepted")],
        "rejected": [("draft", "proposed"), ("proposed", "rejected")],
        "withdrawn": [("draft", "withdrawn")],
        "superseded": [
            ("draft", "proposed"), ("proposed", "accepted"), ("accepted", "superseded")
        ],
        "retired": [
            ("draft", "proposed"), ("proposed", "accepted"), ("accepted", "retired")
        ],
    }[status]
    chain.extend(extra)
    return [
        {"from": frm, "to": to, "at": at, "authority_receipt": None,
         "authority_receipt_sha256": None}
        for frm, to in chain
    ]


def _meta(adr_id: str, status: str = "proposed", **overrides) -> dict:
    digest = "sha256:" + "a" * 64 if status in {"accepted", "superseded", "retired"} else None
    metadata = {
        "schema": "praxis/adr-metadata/v1",
        "id": adr_id,
        "title": "A sufficiently descriptive title",
        "status": status,
        "created_at": _TIMESTAMP,
        "origin": "agent_assisted",
        "authors": ["agent"],
        "decision_owners": ["principal"],
        "assurance_profile": "standard",
        "supersedes": [],
        "superseded_by": None,
        "related": [],
        "decision_core_sha256": digest,
        "transitions": _transitions(status),
    }
    metadata.update(overrides)
    return metadata


def _seed_repo(tmp_path: str | Path) -> Path:
    repo = Path(tmp_path)
    schemas = repo / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "schemas/adr-metadata.schema.json", schemas)
    return repo


def _write_adr(
    repo: Path, filename: str, metadata: dict, *, headings: tuple = ALL_HEADINGS
) -> Path:
    decisions = repo / "docs/decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    block = (
        "<!-- praxis:adr\n"
        + json.dumps(metadata, indent=2, ensure_ascii=False)
        + "\n-->"
    )
    body = "\n\n".join(f"## {h}\n\nEvidence." for h in headings)
    text = f"{block}\n\n# {metadata['id']}: {metadata['title']}\n\n{body}\n"
    target = decisions / filename
    target.write_text(text, encoding="utf-8")
    return target


def _write_raw_adr(
    repo: Path, filename: str, raw_block: str, *, headings: tuple = ALL_HEADINGS,
    title: str = "Title here enough",
) -> Path:
    decisions = repo / "docs/decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(f"## {h}\n\nEvidence." for h in headings)
    text = f"{raw_block}\n\n# ADR-0001: {title}\n\n{body}\n"
    target = decisions / filename
    target.write_text(text, encoding="utf-8")
    return target


def _write_config(repo: Path, decisions: str) -> None:
    """Write a minimal ``.praxis.toml`` setting ``paths.decisions``."""
    (repo / ".praxis.toml").write_text(
        f"[paths]\ndecisions = {json.dumps(decisions)}\n", encoding="utf-8"
    )


def _external_adr(external: Path) -> None:
    """Seed an ADR (ADR-9999) OUTSIDE the repo that must never be read."""
    external.mkdir(parents=True, exist_ok=True)
    block = (
        "<!-- praxis:adr\n"
        + json.dumps(_meta("ADR-9999", "proposed"))
        + "\n-->"
    )
    body = "\n\n".join(f"## {h}\n\nEvidence." for h in ALL_HEADINGS)
    (external / "ADR-9999-evil.md").write_text(
        f"{block}\n\n# ADR-9999: must not be read\n\n{body}\n", encoding="utf-8"
    )


def _valid_audit(obj: dict) -> list:
    return sv.validate(obj, AUDIT_SCHEMA)


def _ids(result: dict) -> list[str]:
    return [f["id"] for f in result["findings"]]


def _sev(result: dict, fid: str) -> str | None:
    for f in result["findings"]:
        if f["id"] == fid:
            return f["severity"]
    return None


class ListTests(unittest.TestCase):
    def test_list_json_lists_parseable_adrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            _write_adr(repo, "ADR-0002-two.md", _meta("ADR-0002", "draft"))
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertEqual(obj["schema"], "praxis/adr-list/v1")
        self.assertEqual(obj["count"], 2)
        self.assertEqual([a["id"] for a in obj["adrs"]], ["ADR-0001", "ADR-0002"])
        self.assertEqual(obj["unparseable_count"], 0)

    def test_list_status_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            _write_adr(repo, "ADR-0002-two.md", _meta("ADR-0002", "draft"))
            rc, out, err = cli.run(
                ["adr", "list", str(repo), "--status", "draft", "--format", "json"]
            )
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertEqual([a["id"] for a in obj["adrs"]], ["ADR-0002"])

    def test_list_surfaces_unparseable_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-ok.md", _meta("ADR-0001", "proposed"))
            dup = (
                "<!-- praxis:adr\n"
                '{\n  "schema": "praxis/adr-metadata/v1",\n'
                '  "id": "ADR-0002",\n  "id": "ADR-0003"\n}\n-->'
            )
            _write_raw_adr(repo, "ADR-0002-dup.md", dup)
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertEqual(obj["count"], 1)
        self.assertEqual(obj["unparseable_count"], 1)
        self.assertEqual(obj["unparseable"][0]["filename"], "ADR-0002-dup.md")
        self.assertIn("duplicate-key", obj["unparseable"][0]["problem"])

    def test_list_empty_repo_returns_zero_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            (repo / "docs/decisions").mkdir(parents=True)
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        self.assertEqual(json.loads(out)["count"], 0)


class ShowTests(unittest.TestCase):
    def test_show_json_returns_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(
                ["adr", "show", str(repo), "ADR-0001", "--format", "json"]
            )
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertEqual(obj["schema"], "praxis/adr-summary/v1")
        self.assertTrue(obj["found"])
        self.assertEqual(obj["metadata"]["id"], "ADR-0001")
        self.assertEqual(obj["filename"], "ADR-0001-one.md")

    def test_show_not_found_is_exit_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(
                ["adr", "show", str(repo), "ADR-0099", "--format", "json"]
            )
        self.assertEqual(rc, cli.EXIT_FAIL, err)
        obj = json.loads(out)
        self.assertFalse(obj["found"])
        self.assertIsNone(obj["metadata"])

    def test_show_malformed_id_is_usage_error(self) -> None:
        rc, out, err = cli.run(["adr", "show", str(ROOT), "ADR-XX", "--format", "json"])
        self.assertEqual(rc, cli.EXIT_USAGE, err)
        self.assertEqual(out, "")

    def test_show_single_positional_treated_as_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(
                ["adr", "show", "ADR-0001", "--format", "json"],
            )
            # repo defaults to cwd which is the worktree here; ensure the call
            # is well-formed (not a usage error on positional count).
        self.assertNotEqual(rc, cli.EXIT_USAGE, err)


class AuditPassTests(unittest.TestCase):
    def test_audit_valid_adr_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(["adr", "audit", str(repo), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS, err)
        obj = json.loads(out)
        self.assertEqual(obj["schema"], "praxis/audit-result/v1")
        self.assertEqual(obj["result"], "pass")
        self.assertEqual(obj["findings"], [])
        self.assertEqual(_valid_audit(obj), [])

    def test_audit_supersession_reciprocal_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            old = _meta("ADR-0001", status="superseded", superseded_by="ADR-0002")
            new = _meta("ADR-0002", status="accepted", supersedes=["ADR-0001"])
            _write_adr(repo, "ADR-0001-old.md", old)
            _write_adr(repo, "ADR-0002-new.md", new)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_PASS, result["findings"])
        link_ids = [f["id"] for f in result["findings"] if f["id"].startswith("adr-link")]
        self.assertEqual(link_ids, [])


class AuditParseErrorTests(unittest.TestCase):
    def test_duplicate_keys_are_blocker_in_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            dup = (
                "<!-- praxis:adr\n"
                '{\n  "schema": "praxis/adr-metadata/v1",\n'
                '  "id": "ADR-0002",\n  "id": "ADR-0003"\n}\n-->'
            )
            _write_raw_adr(repo, "ADR-0002-dup.md", dup)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(result["result"], "fail")
        self.assertIn("adr-metadata-unparseable", _ids(result))
        self.assertEqual(_sev(result, "adr-metadata-unparseable"), "BLOCKER")
        self.assertEqual(_valid_audit(result), [])

    def test_missing_metadata_block_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_raw_adr(repo, "ADR-0001-noop.md", "# no metadata block here")
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-metadata-unparseable"), "BLOCKER")

    def test_invalid_json_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_raw_adr(repo, "ADR-0001-bad.md", "<!-- praxis:adr\n{not json}\n-->")
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-metadata-unparseable"), "BLOCKER")


class AuditMetadataSchemaTests(unittest.TestCase):
    def test_invalid_metadata_is_high_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", origin="bogus")
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertIn("adr-metadata", _ids(result))
        self.assertEqual(_sev(result, "adr-metadata"), "HIGH")
        self.assertEqual(_valid_audit(result), [])


class AuditFilenameIdTests(unittest.TestCase):
    def test_filename_id_mismatch_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0002-wrong.md", _meta("ADR-0001", "proposed"))
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-filename-id-mismatch"), "HIGH")

    def test_noncanonical_filename_is_high_and_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            # Matches the ADR-*.md glob but violates the canonical filename
            # pattern (no "-slug" segment).
            _write_adr(repo, "ADR-0001.md", _meta("ADR-0001", "proposed"))
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL, result["findings"])
        self.assertEqual(_sev(result, "adr-filename-noncanonical"), "HIGH")
        self.assertEqual(_valid_audit(result), [])


class AuditTransitionTests(unittest.TestCase):
    def test_invalid_transition_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="accepted")
            # Corrupt the chain: draft -> accepted is not allowed.
            metadata["transitions"] = [
                {"from": None, "to": "draft", "at": _TIMESTAMP,
                 "authority_receipt": None, "authority_receipt_sha256": None},
                {"from": "draft", "to": "accepted", "at": _TIMESTAMP,
                 "authority_receipt": None, "authority_receipt_sha256": None},
            ]
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-transition-invalid"), "BLOCKER")

    def test_non_contiguous_transition_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed")
            metadata["transitions"] = [
                {"from": None, "to": "draft", "at": _TIMESTAMP,
                 "authority_receipt": None, "authority_receipt_sha256": None},
                {"from": "proposed", "to": "proposed", "at": _TIMESTAMP,
                 "authority_receipt": None, "authority_receipt_sha256": None},
            ]
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, _ = adr.audit_adrs(repo)
        self.assertEqual(_sev(result, "adr-transition-invalid"), "BLOCKER")

    def test_backward_time_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed")
            metadata["transitions"] = [
                {"from": None, "to": "draft", "at": "2026-08-11T10:00:00Z",
                 "authority_receipt": None, "authority_receipt_sha256": None},
                {"from": "draft", "to": "proposed", "at": "2026-08-11T09:00:00Z",
                 "authority_receipt": None, "authority_receipt_sha256": None},
            ]
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, _ = adr.audit_adrs(repo)
        self.assertEqual(_sev(result, "adr-transition-invalid"), "BLOCKER")

    def test_status_not_projecting_final_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed")
            metadata["status"] = "draft"  # final transition is proposed
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, _ = adr.audit_adrs(repo)
        self.assertEqual(_sev(result, "adr-status-projection"), "BLOCKER")

    def test_created_at_not_projecting_first_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed")
            metadata["created_at"] = "2026-01-01T00:00:00Z"  # != first transition at
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, _ = adr.audit_adrs(repo)
        self.assertEqual(_sev(result, "adr-created-at-projection"), "BLOCKER")

    def test_first_transition_not_draft_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed")
            metadata["transitions"] = [
                {"from": None, "to": "proposed", "at": _TIMESTAMP,
                 "authority_receipt": None, "authority_receipt_sha256": None},
            ]
            metadata["status"] = "proposed"
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, _ = adr.audit_adrs(repo)
        self.assertEqual(_sev(result, "adr-transition-invalid"), "BLOCKER")


class AuditHeadingsTests(unittest.TestCase):
    def test_missing_heading_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            headings = tuple(h for h in ALL_HEADINGS if h != "Confirmación")
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"), headings=headings)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-heading-missing"), "HIGH")
        headings_evidence = [
            f["evidence"]["heading"]
            for f in result["findings"]
            if f["id"] == "adr-heading-missing"
        ]
        self.assertIn("Confirmación", headings_evidence)


class AuditRelationsTests(unittest.TestCase):
    def test_supersedes_missing_target_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="accepted", supersedes=["ADR-0009"])
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-link-missing"), "HIGH")

    def test_supersedes_non_reciprocal_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            old = _meta("ADR-0001", status="proposed")  # not superseded, no back-ref
            new = _meta("ADR-0002", status="accepted", supersedes=["ADR-0001"])
            _write_adr(repo, "ADR-0001-old.md", old)
            _write_adr(repo, "ADR-0002-new.md", new)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-link-nonreciprocal"), "HIGH")

    def test_superseded_by_missing_replacement_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta(
                "ADR-0001", status="superseded", superseded_by="ADR-0009"
            )
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-link-missing"), "HIGH")

    def test_related_missing_target_is_high_no_reciprocity_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            # ADR-0002 references ADR-0001 as related; ADR-0001 does NOT
            # reference back. Only existence is required.
            first = _meta("ADR-0001", status="proposed")
            second = _meta("ADR-0002", status="proposed", related=["ADR-0001"])
            _write_adr(repo, "ADR-0001-one.md", first)
            _write_adr(repo, "ADR-0002-two.md", second)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_PASS, result["findings"])

    def test_related_to_nonexistent_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed", related=["ADR-0009"])
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-link-missing"), "HIGH")

    def test_self_link_is_high_and_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            metadata = _meta("ADR-0001", status="proposed", related=["ADR-0001"])
            _write_adr(repo, "ADR-0001-one.md", metadata)
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL, result["findings"])
        self.assertEqual(_sev(result, "adr-link-self"), "HIGH")
        self.assertEqual(_valid_audit(result), [])


class AuditDuplicateAndDirectoryTests(unittest.TestCase):
    def test_duplicate_id_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-a.md", _meta("ADR-0001", "proposed"))
            _write_adr(repo, "ADR-0001-b.md", _meta("ADR-0001", "proposed"))
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-duplicate-id"), "BLOCKER")
        self.assertEqual(_valid_audit(result), [])

    def test_missing_decisions_directory_is_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            # No docs/decisions created.
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-directory-missing"), "BLOCKER")


class PathEscapeTests(unittest.TestCase):
    """``paths.decisions`` must never read outside the repo.

    Absolute paths, ``..`` traversal, and symlinks that resolve outside the
    repository root are rejected. ``adr audit`` emits a BLOCKER
    ``adr-decisions-path-escape``; ``adr list``/``adr show`` fall back to
    ``docs/decisions`` and expose a stable ``decisions_dir_error``. External
    content is never listed or audited.
    """

    @staticmethod
    def _escape_repo(tmp: str | Path, mode: str, *, seed_safe: bool = False) -> Path:
        repo = Path(tmp) / "repo"
        external = Path(tmp) / "external"
        repo.mkdir()
        _seed_repo(repo)
        _external_adr(external)
        if seed_safe:
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
        if mode == "absolute":
            _write_config(repo, str(external))
        elif mode == "dotdot":
            _write_config(repo, "../external")
        else:  # symlink
            (repo / "linked").symlink_to(external)
            _write_config(repo, "linked")
        return repo

    def _audit_escape(self, mode: str) -> tuple[dict, int, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._escape_repo(tmp, mode)
            records = adr.load_adrs(repo)
            result, exit_code = adr.audit_adrs(repo)
        return result, exit_code, [r.adr_id for r in records if r.adr_id]

    def test_audit_absolute_path_is_blocker_and_does_not_load_external(self) -> None:
        result, exit_code, loaded = self._audit_escape("absolute")
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(result["result"], "fail")
        self.assertEqual(_sev(result, "adr-decisions-path-escape"), "BLOCKER")
        self.assertEqual(_valid_audit(result), [])
        self.assertNotIn("ADR-9999", loaded)

    def test_audit_dotdot_path_is_blocker_and_does_not_load_external(self) -> None:
        result, exit_code, loaded = self._audit_escape("dotdot")
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-decisions-path-escape"), "BLOCKER")
        self.assertNotIn("ADR-9999", loaded)

    def test_audit_external_symlink_is_blocker_and_does_not_load_external(self) -> None:
        result, exit_code, loaded = self._audit_escape("symlink")
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-decisions-path-escape"), "BLOCKER")
        self.assertNotIn("ADR-9999", loaded)

    def test_list_absolute_path_uses_fallback_and_exposes_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._escape_repo(tmp, "absolute", seed_safe=True)
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
            obj = json.loads(out)
        self.assertEqual(rc, cli.EXIT_PASS, err)
        self.assertEqual(obj["decisions_dir"], adr.DEFAULT_DECISIONS_DIR)
        self.assertIsNotNone(obj["decisions_dir_error"])
        listed_ids = [a["id"] for a in obj["adrs"]]
        self.assertIn("ADR-0001", listed_ids)
        self.assertNotIn("ADR-9999", listed_ids)

    def test_list_external_symlink_does_not_list_external_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._escape_repo(tmp, "symlink")
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
            obj = json.loads(out)
        self.assertEqual(rc, cli.EXIT_PASS, err)
        self.assertIsNotNone(obj["decisions_dir_error"])
        self.assertEqual(obj["count"], 0)
        self.assertNotIn("ADR-9999", [a["id"] for a in obj["adrs"]])

    def test_show_external_symlink_does_not_read_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._escape_repo(tmp, "symlink")
            rc, out, err = cli.run(
                ["adr", "show", str(repo), "ADR-9999", "--format", "json"]
            )
            obj = json.loads(out)
        self.assertEqual(rc, cli.EXIT_FAIL, err)
        self.assertFalse(obj["found"])
        self.assertIsNotNone(obj["decisions_dir_error"])

    def test_safe_custom_relative_decisions_dir_is_used_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            custom = repo / "docs/choices"
            custom.mkdir(parents=True)
            block = (
                "<!-- praxis:adr\n"
                + json.dumps(_meta("ADR-0007", "proposed"))
                + "\n-->"
            )
            body = "\n\n".join(f"## {h}\n\nEvidence." for h in ALL_HEADINGS)
            (custom / "ADR-0007-x.md").write_text(
                f"{block}\n\n# ADR-0007\n\n{body}\n", encoding="utf-8"
            )
            _write_config(repo, "docs/choices")
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
            obj = json.loads(out)
        self.assertEqual(rc, cli.EXIT_PASS, err)
        # Legitimate in-repo custom path is honored; no false-positive escape.
        self.assertEqual(obj["decisions_dir"], "docs/choices")
        self.assertIsNone(obj["decisions_dir_error"])
        self.assertEqual([a["id"] for a in obj["adrs"]], ["ADR-0007"])

    def test_literal_dotdot_rejected_even_when_resolve_stays_in_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            _write_config(repo, "docs/../docs/decisions")
            result, exit_code = adr.audit_adrs(repo)
            obj = json.loads(cli.run(["adr", "list", str(repo), "--format", "json"])[1])
        self.assertEqual(exit_code, adr.EXIT_FAIL)
        self.assertEqual(_sev(result, "adr-decisions-path-escape"), "BLOCKER")
        self.assertEqual(obj["decisions_dir"], adr.DEFAULT_DECISIONS_DIR)
        self.assertIsNotNone(obj["decisions_dir_error"])
        self.assertIn("ADR-0001", [a["id"] for a in obj["adrs"]])


class AuditInconclusiveTests(unittest.TestCase):
    """When the ADR metadata schema cannot be established, audit is
    inconclusive (exit 3) regardless of other findings."""

    def test_schema_missing_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs/decisions").mkdir(parents=True)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            # No schemas/ directory.
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_INCONCLUSIVE)
        self.assertEqual(result["result"], "inconclusive")
        self.assertIn(
            "adr-schema-unavailable", [d["code"] for d in result["diagnostics"]]
        )
        # Content checks are skipped; no metadata findings derived.
        self.assertEqual(_ids(result), [])
        self.assertEqual(_valid_audit(result), [])

    def test_schema_invalid_json_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            (repo / "schemas/adr-metadata.schema.json").write_text("{not json")
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_INCONCLUSIVE)
        self.assertEqual(result["result"], "inconclusive")

    def test_schema_unsupported_is_inconclusive_without_metadata_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            (repo / "schemas/adr-metadata.schema.json").write_text(
                '{"not-a-schema": true}'
            )
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_INCONCLUSIVE)
        metadata_ids = [fid for fid in _ids(result) if fid != "adr-metadata-unparseable"]
        self.assertEqual(metadata_ids, [])

    def test_parse_error_still_reported_when_schema_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs/decisions").mkdir(parents=True)
            _write_raw_adr(repo, "ADR-0001-bad.md", "<!-- praxis:adr\n{not json}\n-->")
            result, exit_code = adr.audit_adrs(repo)
        self.assertEqual(exit_code, adr.EXIT_INCONCLUSIVE)
        # Factual parse error is still surfaced as BLOCKER, result stays inconclusive.
        self.assertEqual(_sev(result, "adr-metadata-unparseable"), "BLOCKER")


class JsonPurityTests(unittest.TestCase):
    def test_list_json_stdout_is_pure_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(["adr", "list", str(repo), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS)
        obj = json.loads(out)
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj["schema"], "praxis/adr-list/v1")

    def test_show_json_stdout_is_pure_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(
                ["adr", "show", str(repo), "ADR-0001", "--format", "json"]
            )
        self.assertEqual(rc, cli.EXIT_PASS)
        obj = json.loads(out)
        self.assertEqual(obj["schema"], "praxis/adr-summary/v1")

    def test_audit_json_stdout_is_pure_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            rc, out, err = cli.run(["adr", "audit", str(repo), "--format", "json"])
        self.assertEqual(rc, cli.EXIT_PASS)
        obj = json.loads(out)
        self.assertEqual(obj["schema"], "praxis/audit-result/v1")


class NoMutationTests(unittest.TestCase):
    _SKIP = {".git", "__pycache__", ".pytest_cache"}

    def _snapshot(self, repo: Path) -> dict[str, tuple[int, int, str]]:
        snapshot: dict[str, tuple[int, int, str]] = {}
        for path in repo.rglob("*"):
            if any(part in self._SKIP for part in path.relative_to(repo).parts):
                continue
            if not path.is_file():
                continue
            rel = path.relative_to(repo).as_posix()
            stat = path.stat()
            snapshot[rel] = (stat.st_size, stat.st_mtime_ns, _sha256(path))
        return snapshot

    def test_read_only_commands_do_not_mutate_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _seed_repo(tmp)
            _write_adr(repo, "ADR-0001-one.md", _meta("ADR-0001", "proposed"))
            before = self._snapshot(repo)
            cli.run(["adr", "list", str(repo)])
            cli.run(["adr", "list", str(repo), "--format", "json"])
            cli.run(["adr", "show", str(repo), "ADR-0001", "--format", "json"])
            cli.run(["adr", "audit", str(repo)])
            cli.run(["adr", "audit", str(repo), "--format", "json"])
            after = self._snapshot(repo)
        self.assertEqual(before, after)


class ExitCodeTests(unittest.TestCase):
    def test_no_command(self) -> None:
        self.assertEqual(cli.run([])[0], cli.EXIT_USAGE)

    def test_unknown_adr_operation(self) -> None:
        self.assertEqual(cli.run(["adr", "nope"])[0], cli.EXIT_USAGE)

    def test_show_missing_id(self) -> None:
        self.assertEqual(cli.run(["adr", "show", str(ROOT)])[0], cli.EXIT_USAGE)

    def test_bad_status(self) -> None:
        self.assertEqual(
            cli.run(["adr", "list", str(ROOT), "--status", "invented"])[0],
            cli.EXIT_USAGE,
        )

    def test_status_on_show_rejected(self) -> None:
        self.assertEqual(
            cli.run(["adr", "show", str(ROOT), "ADR-0001", "--status", "draft"])[0],
            cli.EXIT_USAGE,
        )

    def test_repo_not_found(self) -> None:
        self.assertEqual(
            cli.run(["adr", "audit", "/nonexistent/praxis/xyz"])[0], cli.EXIT_USAGE
        )

    def test_extra_positional_on_audit(self) -> None:
        self.assertEqual(
            cli.run(["adr", "audit", str(ROOT), str(ROOT)])[0], cli.EXIT_USAGE
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
