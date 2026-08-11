#!/usr/bin/env python3.12
"""Deterministic, dependency-free checks for the Praxis Dev repository."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path("standards/praxis/v1/manifest.json")
CONFIG_PATH = Path(".praxis.toml")
ADR_DIR = Path("docs/decisions")
ADR_FILENAME = re.compile(r"^ADR-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_ID = re.compile(r"^ADR-\d{4}$")
ADR_METADATA = re.compile(
    r"\A<!-- praxis:adr\s*\n(?P<payload>\{.*?\})\s*\n-->", re.DOTALL
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")
ADR_REQUIRED_SECTIONS = (
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
ADR_CORE_SECTIONS = (
    "Contexto y problema",
    "Alcance y no objetivos",
    "Drivers e invariantes",
    "Opciones consideradas",
    "Decisión",
    "Consecuencias",
)
ADR_ALLOWED_TRANSITIONS = {
    (None, "draft"),
    ("draft", "proposed"),
    ("draft", "withdrawn"),
    ("proposed", "accepted"),
    ("proposed", "rejected"),
    ("proposed", "withdrawn"),
    ("accepted", "superseded"),
    ("accepted", "retired"),
}
ADR_PROTECTED_TARGETS = {"accepted", "rejected", "superseded", "retired"}
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
PROJECT_ID = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$"
)
SAFE_RELATIVE_PATH = re.compile(
    r"^(?!\.{1,2}(?:/|$))(?!.*(?:^|/)\.{1,2}(?:/|$))"
    r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)
UTC_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON property: {key}")
        result[key] = value
    return result


def _loads_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_object)


def _load_json(path: Path) -> dict[str, Any]:
    data = _loads_json(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value must be an object")
    return data


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not UTC_TIMESTAMP.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _safe_project_path(root: Path, raw: Any) -> Path | None:
    if not isinstance(raw, str) or not SAFE_RELATIVE_PATH.fullmatch(raw):
        return None
    candidate = root / raw
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _has_symlink_component(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _section_text(text: str, heading: str) -> str | None:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        text.replace("\r\n", "\n"),
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip("\n") if match else None


def decision_core_digest(text: str, title: str) -> str | None:
    sections: list[str] = []
    for heading in ADR_CORE_SECTIONS:
        body = _section_text(text, heading)
        if body is None:
            return None
        sections.append(f"## {heading}\n{body}")
    payload = (
        "praxis-decision-core-v1\n"
        + f"title:{title}\n"
        + "\n".join(sections)
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def check_config(root: Path, manifest: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    path = root / CONFIG_PATH
    if not path.is_file():
        return [Issue("config.missing", str(CONFIG_PATH), "required config is missing")]
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [Issue("config.invalid", str(CONFIG_PATH), str(exc))]
    if config.get("schema") != "praxis/project-config/v1":
        issues.append(Issue("config.schema", str(CONFIG_PATH), "unsupported schema"))
    project_id = config.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        issues.append(Issue("config.project-id", str(CONFIG_PATH), "invalid project_id"))
    if config.get("standard_version") != manifest.get("version"):
        issues.append(
            Issue("config.version", str(CONFIG_PATH), "config and manifest versions differ")
        )
    profiles = manifest.get("profiles", {})
    if config.get("profile") not in profiles:
        issues.append(Issue("config.profile", str(CONFIG_PATH), "unknown profile"))
    modules = config.get("modules")
    declared_modules = manifest.get("modules", {})
    if not isinstance(modules, dict):
        issues.append(Issue("config.modules", str(CONFIG_PATH), "modules must be a table"))
    else:
        for module, version in modules.items():
            if module not in declared_modules:
                issues.append(
                    Issue("config.modules", str(CONFIG_PATH), f"unknown module {module}")
                )
            elif version != declared_modules[module]:
                issues.append(
                    Issue(
                        "config.modules",
                        str(CONFIG_PATH),
                        f"unsupported version {module}={version}",
                    )
                )
        required = set(profiles.get(config.get("profile"), []))
        missing = sorted(required - set(modules))
        if missing:
            issues.append(
                Issue(
                    "config.modules",
                    str(CONFIG_PATH),
                    f"profile modules missing: {', '.join(missing)}",
                )
            )
        dependencies = manifest.get("module_dependencies", {})
        for module in modules:
            missing_dependencies = sorted(set(dependencies.get(module, [])) - set(modules))
            if missing_dependencies:
                issues.append(
                    Issue(
                        "config.modules",
                        str(CONFIG_PATH),
                        f"{module} dependencies missing: {', '.join(missing_dependencies)}",
                    )
                )
    paths = config.get("paths")
    if not isinstance(paths, dict):
        issues.append(Issue("config.paths", str(CONFIG_PATH), "paths must be a table"))
    else:
        expected_kinds = {
            "agent_contract": "file",
            "policy": "file",
            "decisions": "directory",
            "specs": "directory",
        }
        for key, expected_kind in expected_kinds.items():
            candidate = _safe_project_path(root, paths.get(key))
            if candidate is None:
                issues.append(
                    Issue("config.paths", str(CONFIG_PATH), f"unsafe or missing path {key}")
                )
                continue
            if _has_symlink_component(root, candidate):
                issues.append(
                    Issue("config.paths", str(CONFIG_PATH), f"symlinked path {key}")
                )
            elif expected_kind == "file" and not candidate.is_file():
                issues.append(
                    Issue("config.paths", str(CONFIG_PATH), f"file not found for {key}")
                )
            elif expected_kind == "directory" and not candidate.is_dir():
                issues.append(
                    Issue("config.paths", str(CONFIG_PATH), f"directory not found for {key}")
                )
    authority = config.get("authority", {})
    if not isinstance(authority, dict) or authority.get("fail_closed") is not True:
        issues.append(
            Issue("config.authority", str(CONFIG_PATH), "authority.fail_closed must be true")
        )
    return issues


def check_manifest_semantics(root: Path, manifest: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    modules = manifest.get("modules")
    dependencies = manifest.get("module_dependencies")
    profiles = manifest.get("profiles")
    if not all(isinstance(value, dict) for value in (modules, dependencies, profiles)):
        return [Issue("manifest.structure", str(MANIFEST_PATH), "invalid module tables")]
    module_names = set(modules)
    if set(dependencies) != module_names:
        issues.append(
            Issue(
                "manifest.dependencies",
                str(MANIFEST_PATH),
                "dependency keys must equal module keys",
            )
        )
    for module, required in dependencies.items():
        if not isinstance(required, list) or any(item not in module_names for item in required):
            issues.append(
                Issue(
                    "manifest.dependencies",
                    str(MANIFEST_PATH),
                    f"invalid dependencies for {module}",
                )
            )
    for profile, enabled in profiles.items():
        if not isinstance(enabled, list) or any(item not in module_names for item in enabled):
            issues.append(
                Issue("manifest.profile", str(MANIFEST_PATH), f"unknown module in {profile}")
            )
            continue
        enabled_set = set(enabled)
        for module in enabled:
            missing = set(dependencies.get(module, [])) - enabled_set
            if missing:
                issues.append(
                    Issue(
                        "manifest.profile",
                        str(MANIFEST_PATH),
                        f"{profile}:{module} lacks {', '.join(sorted(missing))}",
                    )
                )
    for name, raw_path in manifest.get("schemas", {}).items():
        path = _safe_project_path(root, raw_path)
        if path is None or not path.is_file():
            issues.append(
                Issue("manifest.schema", str(MANIFEST_PATH), f"missing schema {name}")
            )
    return issues


def check_required_paths(root: Path, manifest: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for entry in manifest.get("reference_repository_required_paths", []):
        relative = Path(entry["path"])
        path = root / relative
        if path.is_symlink():
            issues.append(Issue("path.symlink", str(relative), "required path is a symlink"))
            continue
        if not path.is_file():
            issues.append(Issue("path.missing", str(relative), "required file is missing"))
            continue
        limit = int(entry.get("max_lines", 0))
        if limit and _line_count(path) > limit:
            issues.append(
                Issue("size.exceeded", str(relative), f"exceeds {limit} lines")
            )
    return issues


def check_root_markdown(root: Path, manifest: dict[str, Any]) -> list[Issue]:
    allowed = set(manifest.get("allowed_root_markdown", []))
    return [
        Issue("root.markdown", path.name, "unregistered root Markdown file")
        for path in sorted(root.glob("*.md"))
        if path.name not in allowed
    ]


def check_general_sizes(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    roots_and_limits = (("docs", 800), ("templates", 800), ("scripts", 800), ("tests", 800))
    for directory, limit in roots_and_limits:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in {".md", ".py", ".tpl"}:
                if _line_count(path) > limit:
                    issues.append(
                        Issue(
                            "size.exceeded",
                            str(path.relative_to(root)),
                            f"exceeds {limit} lines",
                        )
                    )
    return issues


def check_json_files(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for directory in (root / "schemas", root / "standards"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            try:
                data = _load_json(path)
                if path.parent == root / "schemas":
                    if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                        issues.append(
                            Issue(
                                "schema.dialect",
                                str(path.relative_to(root)),
                                "schema must declare Draft 2020-12",
                            )
                        )
                    if not isinstance(data.get("$id"), str) or data.get("type") != "object":
                        issues.append(
                            Issue(
                                "schema.structure",
                                str(path.relative_to(root)),
                                "schema requires $id and object root",
                            )
                        )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                issues.append(
                    Issue("json.invalid", str(path.relative_to(root)), str(exc))
                )
    return issues


def check_trailing_whitespace(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    suffixes = {".md", ".py", ".json", ".toml", ".tpl"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.suffix not in suffixes:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if line.endswith((" ", "\t")):
                issues.append(
                    Issue(
                        "text.trailing-whitespace",
                        str(path.relative_to(root)),
                        f"line {number}",
                    )
                )
    return issues


def _parse_adr(path: Path) -> tuple[dict[str, Any] | None, list[Issue]]:
    relative = str(path)
    text = path.read_text(encoding="utf-8")
    match = ADR_METADATA.search(text)
    if not match:
        return None, [Issue("adr.metadata", relative, "missing praxis:adr JSON metadata")]
    try:
        metadata = _loads_json(match.group("payload"))
    except (json.JSONDecodeError, ValueError) as exc:
        return None, [Issue("adr.metadata", relative, f"invalid JSON: {exc}")]
    if not isinstance(metadata, dict):
        return None, [Issue("adr.metadata", relative, "metadata must be an object")]
    issues: list[Issue] = []
    for section in ADR_REQUIRED_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(section)}\s*$", text, re.MULTILINE):
            issues.append(Issue("adr.section", relative, f"missing section: {section}"))
    return metadata, issues


def _valid_string_list(value: Any, *, non_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not non_empty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    )


def _check_receipt_envelope(
    root: Path,
    path: Path,
    schema: dict[str, Any],
    transition: dict[str, Any],
    adr_id: str,
    project_id: str | None,
    core_digest: str | None,
) -> list[Issue]:
    relative = str(path.relative_to(root))
    try:
        receipt = _load_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [Issue("adr.authority", relative, f"invalid receipt JSON: {exc}")]
    issues: list[Issue] = []
    required = set(schema.get("required", []))
    properties = set(schema.get("properties", {}))
    if missing := sorted(required - set(receipt)):
        issues.append(Issue("adr.authority", relative, f"receipt fields missing: {', '.join(missing)}"))
    if unknown := sorted(set(receipt) - properties):
        issues.append(Issue("adr.authority", relative, f"unknown receipt fields: {', '.join(unknown)}"))
    expected = {
        "schema": "praxis/authority-receipt/v1",
        "project_id": project_id,
        "target_id": adr_id,
        "from_state": transition.get("from"),
        "to_state": transition.get("to"),
        "content_digest": core_digest,
        "single_use": True,
        "canonicalization": "RFC8785",
    }
    for field, value in expected.items():
        if value is not None and receipt.get(field) != value:
            issues.append(Issue("adr.authority", relative, f"receipt {field} does not match"))
    for field in ("payload_digest", "plan_fingerprint", "content_digest"):
        if not isinstance(receipt.get(field), str) or not DIGEST.fullmatch(receipt[field]):
            issues.append(Issue("adr.authority", relative, f"invalid receipt {field}"))
    issued = _parse_datetime(receipt.get("issued_at"))
    expires = _parse_datetime(receipt.get("expires_at"))
    if issued is None or expires is None or expires <= issued:
        issues.append(Issue("adr.authority", relative, "invalid receipt validity interval"))
    if not _valid_string_list(receipt.get("scope"), non_empty=True):
        issues.append(Issue("adr.authority", relative, "invalid receipt scope"))
    proof = receipt.get("proof")
    proof_fields = {"type", "key_id", "algorithm", "signature", "provider_data"}
    if not isinstance(proof, dict) or set(proof) != proof_fields:
        issues.append(Issue("adr.authority", relative, "invalid receipt proof envelope"))
    return issues


def _check_adr_metadata(
    root: Path,
    path: Path,
    text: str,
    metadata: dict[str, Any],
    schema: dict[str, Any],
    receipt_schema: dict[str, Any],
    statuses: set[str],
    project_id: str | None,
) -> list[Issue]:
    relative = str(path.relative_to(root))
    issues: list[Issue] = []

    def add(code: str, message: str) -> None:
        issues.append(Issue(code, relative, message))

    required = set(schema.get("required", []))
    properties = set(schema.get("properties", {}))
    missing = sorted(required - set(metadata))
    unknown = sorted(set(metadata) - properties)
    if missing:
        add("adr.metadata", f"missing metadata: {', '.join(missing)}")
    if unknown:
        add("adr.metadata", f"unknown metadata: {', '.join(unknown)}")
    if metadata.get("schema") != "praxis/adr-metadata/v1":
        add("adr.metadata", "unsupported metadata schema")
    title = metadata.get("title")
    if not isinstance(title, str) or not 5 <= len(title) <= 160:
        add("adr.title", "title must contain 5..160 characters")
    else:
        expected_heading = f"# {metadata.get('id')}: {title}"
        if not re.search(rf"^{re.escape(expected_heading)}\s*$", text, re.MULTILINE):
            add("adr.title", "heading, id and metadata title differ")
    if metadata.get("status") not in statuses:
        add("adr.status", f"invalid status {metadata.get('status')!r}")
    if metadata.get("origin") not in {"human", "agent_assisted", "agent_generated"}:
        add("adr.origin", "invalid origin")
    if metadata.get("assurance_profile") not in {
        "minimal",
        "standard",
        "high-assurance",
        "regulated",
    }:
        add("adr.profile", "invalid assurance_profile")
    for field in ("authors", "decision_owners"):
        if not _valid_string_list(metadata.get(field), non_empty=True):
            add("adr.metadata", f"{field} must be non-empty and unique")
    for field in ("supersedes", "related"):
        values = metadata.get(field)
        if not _valid_string_list(values) or any(not ADR_ID.fullmatch(item) for item in values):
            add("adr.metadata", f"{field} must contain unique ADR ids")
    replacement = metadata.get("superseded_by")
    if replacement is not None and (
        not isinstance(replacement, str) or not ADR_ID.fullmatch(replacement)
    ):
        add("adr.metadata", "superseded_by must be an ADR id or null")

    transitions = metadata.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        add("adr.transitions", "transitions must be a non-empty array")
        return issues
    previous_to: str | None = None
    previous_at: datetime | None = None
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            add("adr.transitions", f"transition {index} must be an object")
            continue
        expected_keys = {
            "from",
            "to",
            "at",
            "authority_receipt",
            "authority_receipt_sha256",
        }
        if set(transition) != expected_keys:
            add("adr.transitions", f"transition {index} has invalid fields")
        source = transition.get("from")
        target = transition.get("to")
        if (source, target) not in ADR_ALLOWED_TRANSITIONS:
            add("adr.transitions", f"transition {index} is not allowed: {source}->{target}")
        if index and source != previous_to:
            add("adr.transitions", f"transition {index} is not contiguous")
        observed_at = _parse_datetime(transition.get("at"))
        if observed_at is None:
            add("adr.transitions", f"transition {index} has invalid timestamp")
        elif previous_at and observed_at < previous_at:
            add("adr.transitions", f"transition {index} moves backward in time")
        previous_at = observed_at or previous_at
        receipt = transition.get("authority_receipt")
        receipt_digest = transition.get("authority_receipt_sha256")
        if (receipt is None) != (receipt_digest is None):
            add("adr.authority", f"transition {index} has incomplete receipt binding")
        if target in ADR_PROTECTED_TARGETS and receipt is None:
            add("adr.authority", f"transition {index} requires authority receipt")
        if receipt is not None:
            receipt_path = _safe_project_path(root, receipt)
            if receipt_path is None or _has_symlink_component(root, receipt_path):
                add("adr.authority", f"transition {index} has unsafe receipt path")
            elif not receipt_path.is_file():
                add("adr.authority", f"transition {index} receipt does not exist")
            elif not isinstance(receipt_digest, str) or not DIGEST.fullmatch(receipt_digest):
                add("adr.authority", f"transition {index} has invalid receipt digest")
            else:
                actual = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                if actual != receipt_digest:
                    add("adr.authority", f"transition {index} receipt digest mismatch")
                else:
                    core_digest = decision_core_digest(text, title) if isinstance(title, str) else None
                    issues.extend(
                        _check_receipt_envelope(
                            root,
                            receipt_path,
                            receipt_schema,
                            transition,
                            str(metadata.get("id")),
                            project_id,
                            core_digest,
                        )
                    )
        previous_to = target if isinstance(target, str) else previous_to
    if transitions[0].get("from") is not None or transitions[0].get("to") != "draft":
        add("adr.transitions", "first transition must create draft from null")
    if metadata.get("created_at") != transitions[0].get("at"):
        add("adr.transitions", "created_at must match first transition")
    if metadata.get("status") != transitions[-1].get("to"):
        add("adr.transitions", "status must match final transition")

    status = metadata.get("status")
    core_digest = metadata.get("decision_core_sha256")
    if status in {"accepted", "superseded", "retired"}:
        actual_core = decision_core_digest(text, title) if isinstance(title, str) else None
        if not isinstance(core_digest, str) or not DIGEST.fullmatch(core_digest):
            add("adr.core", "accepted lineage lacks decision core digest")
        elif core_digest != actual_core:
            add("adr.core", "decision core digest mismatch")
    elif core_digest is not None:
        add("adr.core", "non-accepted ADR must not claim a decision core digest")
    if status == "superseded" and replacement is None:
        add("adr.superseded", "missing superseded_by")
    if status != "superseded" and replacement is not None:
        add("adr.superseded", "only superseded ADR may set superseded_by")
    return issues


def check_adrs(root: Path, manifest: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    adr_dir = root / ADR_DIR
    if not adr_dir.is_dir():
        return [Issue("adr.directory", str(ADR_DIR), "ADR directory is missing")]
    schema_raw = manifest.get("schemas", {}).get("adr_metadata")
    schema_path = _safe_project_path(root, schema_raw)
    if schema_path is None or not schema_path.is_file():
        return [Issue("adr.schema", str(ADR_DIR), "ADR metadata schema is missing")]
    try:
        schema = _load_json(schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [Issue("adr.schema", str(schema_path.relative_to(root)), str(exc))]
    receipt_raw = manifest.get("schemas", {}).get("authority_receipt")
    receipt_schema_path = _safe_project_path(root, receipt_raw)
    if receipt_schema_path is None or not receipt_schema_path.is_file():
        return [Issue("adr.schema", str(ADR_DIR), "authority receipt schema is missing")]
    try:
        receipt_schema = _load_json(receipt_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [Issue("adr.schema", str(receipt_schema_path.relative_to(root)), str(exc))]
    project_id: str | None = None
    try:
        config = tomllib.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
        raw_project_id = config.get("project_id")
        project_id = raw_project_id if isinstance(raw_project_id, str) else None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        pass
    statuses = set(manifest.get("adr", {}).get("statuses", []))
    by_id: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(adr_dir.glob("ADR-*.md")):
        relative = str(path.relative_to(root))
        filename = ADR_FILENAME.fullmatch(path.name)
        if not filename:
            issues.append(Issue("adr.filename", relative, "non-canonical ADR filename"))
        text = path.read_text(encoding="utf-8")
        metadata, parse_issues = _parse_adr(path)
        issues.extend(
            Issue(issue.code, relative, issue.message) for issue in parse_issues
        )
        if metadata is None:
            continue
        issues.extend(
            _check_adr_metadata(
                root,
                path,
                text,
                metadata,
                schema,
                receipt_schema,
                statuses,
                project_id,
            )
        )
        adr_id = metadata.get("id")
        if not isinstance(adr_id, str) or not ADR_ID.fullmatch(adr_id):
            issues.append(Issue("adr.id", relative, "invalid ADR id"))
            continue
        if filename and adr_id != f"ADR-{filename.group(1)}":
            issues.append(Issue("adr.id", relative, "id and filename differ"))
        if adr_id in by_id:
            issues.append(Issue("adr.duplicate", relative, f"duplicate id {adr_id}"))
        else:
            by_id[adr_id] = (path, metadata)
    for adr_id, (path, metadata) in by_id.items():
        relative = str(path.relative_to(root))
        linked_ids = list(metadata.get("supersedes", [])) + list(
            metadata.get("related", [])
        )
        if adr_id in linked_ids or metadata.get("superseded_by") == adr_id:
            issues.append(Issue("adr.link", relative, "ADR must not link to itself"))
        for old_id in metadata.get("supersedes", []):
            old = by_id.get(old_id)
            if old is None:
                issues.append(Issue("adr.link", relative, f"missing superseded ADR {old_id}"))
            elif old[1].get("superseded_by") != adr_id or old[1].get("status") != "superseded":
                issues.append(Issue("adr.link", relative, f"non-reciprocal supersession {old_id}"))
        for related_id in metadata.get("related", []):
            if related_id not in by_id:
                issues.append(Issue("adr.link", relative, f"missing related ADR {related_id}"))
        replacement = metadata.get("superseded_by")
        if replacement and replacement not in by_id:
            issues.append(
                Issue("adr.link", relative, f"missing replacement {replacement}")
            )
    return issues


def check_markdown_links(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts or "templates" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group("target").strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            candidate = (path.parent / target).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                issues.append(Issue("link.escape", str(path.relative_to(root)), target))
                continue
            if not candidate.exists():
                issues.append(Issue("link.missing", str(path.relative_to(root)), target))
    return issues


def check_repository(root: Path) -> list[Issue]:
    manifest_file = root / MANIFEST_PATH
    if not manifest_file.is_file():
        return [Issue("manifest.missing", str(MANIFEST_PATH), "manifest is missing")]
    try:
        manifest = _load_json(manifest_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [Issue("manifest.invalid", str(MANIFEST_PATH), str(exc))]
    checks = (
        check_config(root, manifest),
        check_manifest_semantics(root, manifest),
        check_required_paths(root, manifest),
        check_root_markdown(root, manifest),
        check_general_sizes(root),
        check_json_files(root),
        check_trailing_whitespace(root),
        check_adrs(root, manifest),
        check_markdown_links(root),
    )
    return [issue for group in checks for issue in group]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    issues = check_repository(args.root.resolve())
    if issues:
        print(f"Praxis repository gate: FAIL ({len(issues)} findings)")
        for issue in issues:
            print(f"[{issue.code}] {issue.path}: {issue.message}")
        return 1
    print("Praxis bootstrap repository gate: PASS (not a conformance claim)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
