from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.check_repo import (
    check_adrs,
    check_json_files,
    check_manifest_semantics,
    check_repository,
    check_root_markdown,
    check_trailing_whitespace,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (PROJECT_ROOT / "standards/praxis/v1/manifest.json").read_text(encoding="utf-8")
)


def _metadata(adr_id: str, status: str = "proposed") -> dict[str, object]:
    timestamp = "2026-08-11T00:00:00Z"
    transitions: list[dict[str, object]] = [
        {
            "from": None,
            "to": "draft",
            "at": timestamp,
            "authority_receipt": None,
            "authority_receipt_sha256": None,
        }
    ]
    if status != "draft":
        transitions.append(
            {
                "from": "draft",
                "to": "proposed" if status not in {"withdrawn"} else status,
                "at": timestamp,
                "authority_receipt": None,
                "authority_receipt_sha256": None,
            }
        )
    if status not in {"draft", "proposed", "withdrawn"}:
        transitions.append(
            {
                "from": "proposed",
                "to": status if status not in {"superseded", "retired"} else "accepted",
                "at": timestamp,
                "authority_receipt": None,
                "authority_receipt_sha256": None,
            }
        )
    if status in {"superseded", "retired"}:
        transitions.append(
            {
                "from": "accepted",
                "to": status,
                "at": timestamp,
                "authority_receipt": None,
                "authority_receipt_sha256": None,
            }
        )
    return {
        "schema": "praxis/adr-metadata/v1",
        "id": adr_id,
        "title": "A sufficiently descriptive title",
        "status": status,
        "created_at": timestamp,
        "origin": "agent_assisted",
        "authors": ["agent"],
        "decision_owners": ["principal"],
        "assurance_profile": "standard",
        "supersedes": [],
        "superseded_by": None,
        "related": [],
        "decision_core_sha256": None,
        "transitions": transitions,
    }


def _write_adr(path: Path, metadata: dict[str, object]) -> None:
    sections = (
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
    body = "\n\n".join(f"## {section}\n\nEvidence." for section in sections)
    path.write_text(
        "<!-- praxis:adr\n"
        + json.dumps(metadata, indent=2)
        + f"\n-->\n\n# {metadata['id']}: {metadata['title']}\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )


def _prepare_adr_root(root: Path) -> Path:
    directory = root / "docs/decisions"
    directory.mkdir(parents=True)
    schema_dir = root / "schemas"
    schema_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "schemas/adr-metadata.schema.json", schema_dir)
    shutil.copy2(PROJECT_ROOT / "schemas/authority-receipt.schema.json", schema_dir)
    return directory


class RepositoryGateTests(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        self.assertEqual(check_repository(PROJECT_ROOT), [])

    def test_unregistered_root_markdown_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
            issues = check_root_markdown(root, MANIFEST)
            self.assertEqual([issue.code for issue in issues], ["root.markdown"])

    def test_trailing_whitespace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "bad.md").write_text("bad  \n", encoding="utf-8")
            issues = check_trailing_whitespace(root)
            self.assertEqual(
                [issue.code for issue in issues], ["text.trailing-whitespace"]
            )

    def test_duplicate_adr_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directory = _prepare_adr_root(root)
            _write_adr(directory / "ADR-0001-first.md", _metadata("ADR-0001"))
            _write_adr(directory / "ADR-0001-second.md", _metadata("ADR-0001"))
            issues = check_adrs(root, MANIFEST)
            self.assertIn("adr.duplicate", [issue.code for issue in issues])

    def test_accepted_adr_requires_digest_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directory = _prepare_adr_root(root)
            metadata = _metadata("ADR-0001", status="accepted")
            _write_adr(directory / "ADR-0001-first.md", metadata)
            messages = [issue.message for issue in check_adrs(root, MANIFEST)]
            self.assertTrue(any("core digest" in message for message in messages))
            self.assertTrue(any("authority receipt" in message for message in messages))

    def test_reciprocal_supersession_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directory = _prepare_adr_root(root)
            old = _metadata("ADR-0001")
            new = _metadata("ADR-0002", status="proposed")
            new["supersedes"] = ["ADR-0001"]
            _write_adr(directory / "ADR-0001-old.md", old)
            _write_adr(directory / "ADR-0002-new.md", new)
            issues = check_adrs(root, copy.deepcopy(MANIFEST))
            self.assertIn("adr.link", [issue.code for issue in issues])

    def test_status_must_project_final_transition(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directory = _prepare_adr_root(root)
            metadata = _metadata("ADR-0001")
            metadata["status"] = "draft"
            _write_adr(directory / "ADR-0001-first.md", metadata)
            messages = [issue.message for issue in check_adrs(root, MANIFEST)]
            self.assertIn("status must match final transition", messages)

    def test_decision_core_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directory = _prepare_adr_root(root)
            metadata = _metadata("ADR-0001", status="accepted")
            metadata["decision_core_sha256"] = "sha256:" + "a" * 64
            _write_adr(directory / "ADR-0001-first.md", metadata)
            messages = [issue.message for issue in check_adrs(root, MANIFEST)]
            self.assertIn("decision core digest mismatch", messages)

    def test_profile_must_include_module_dependencies(self) -> None:
        manifest = copy.deepcopy(MANIFEST)
        manifest["profiles"]["standard"].remove("evidence")
        messages = [
            issue.message for issue in check_manifest_semantics(PROJECT_ROOT, manifest)
        ]
        self.assertTrue(any("standard:adrg lacks evidence" in item for item in messages))

    def test_duplicate_json_property_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            schema_dir = root / "schemas"
            schema_dir.mkdir()
            (schema_dir / "duplicate.json").write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema",'
                '"$id":"first","$id":"second","type":"object"}\n',
                encoding="utf-8",
            )
            issues = check_json_files(root)
            self.assertEqual([issue.code for issue in issues], ["json.invalid"])


if __name__ == "__main__":
    unittest.main()
