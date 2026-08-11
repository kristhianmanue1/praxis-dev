"""Read-only Praxis ADR inspection (F1, proposed).

This module backs the ``praxis adr`` read-only CLI surface. It discovers
Architecture Decision Records under the configured ``paths.decisions``
directory, extracts the ``<!-- praxis:adr ... -->`` metadata block, parses it
with :func:`praxis_dev.schema_validation.loads_strict` (rejecting duplicate
keys and non-finite constants), and audits each record against:

* ``schemas/adr-metadata.schema.json`` via the closed runtime validator;
* filename/id coherence (``ADR-NNNN`` from filename matches metadata ``id``);
* append-only transition history with allowed transitions, contiguous
  ``from``/``to`` and monotonically non-decreasing ``at``;
* the projections ``status == transitions[-1].to`` and
  ``created_at == transitions[0].at``;
* the eleven required ADRG body headings (``docs/modulos/adrg.md`` §6);
* relation existence for ``related`` and bidirectional reciprocity for
  ``supersedes``/``superseded_by`` (self-links are rejected).

Path containment: ``paths.decisions`` is never allowed to read outside the
repo. Absolute paths, ``..`` traversal, and symlinks that resolve outside the
repository root are rejected. ``adr audit`` reports this as a BLOCKER
(``adr-decisions-path-escape``); ``adr list``/``adr show`` fall back to
``docs/decisions`` and expose a stable ``decisions_dir_error`` string.

Three payloads are produced:

* :func:`audit_adrs` -> a ``praxis/audit-result/v1`` object satisfying
  ``schemas/audit-result.schema.json``. When the ADR metadata standard schema
  is missing, unreadable, not valid JSON or semantically unsupported by the
  closed validator, the audit is **inconclusive** (exit 3): the metadata
  contract cannot be validated, so no metadata findings are derived. Only
  factual observations (missing decisions directory, unparseable blocks) are
  reported in that case.
* :func:`list_adrs` -> a ``praxis/adr-list/v1`` informational payload.
* :func:`show_adr` -> a ``praxis/adr-summary/v1`` informational payload.

The informational payloads are intentionally NOT added to ``schemas/`` so the
versioned standard is unchanged. The module is stdlib-only, never imports
``jsonschema``, and never writes to the target repository.

Decision-core digest drift (ADRG §10) is out of scope for F1; the schema's
``allOf`` still enforces digest presence/format for accepted lineage.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from praxis_dev import schema_validation as sv
from praxis_dev.project import PROFILE_LEVELS, TOOL_VERSION, head_revision

ADR_METADATA_SCHEMA = "schemas/adr-metadata.schema.json"
ADR_SCHEMA_ID = "praxis/adr-metadata/v1"
AUDIT_RESULT_SCHEMA_ID = "praxis/audit-result/v1"
LIST_SCHEMA_ID = "praxis/adr-list/v1"
SUMMARY_SCHEMA_ID = "praxis/adr-summary/v1"
DEFAULT_DECISIONS_DIR = "docs/decisions"

ADR_STATUSES: frozenset[str] = frozenset({
    "draft", "proposed", "accepted", "rejected", "withdrawn", "superseded",
    "retired",
})
# ADRG §5 permitted transitions, plus the null->draft creation hop.
ADR_ALLOWED_TRANSITIONS: frozenset[tuple[str | None, str]] = frozenset({
    (None, "draft"),
    ("draft", "proposed"),
    ("draft", "withdrawn"),
    ("proposed", "accepted"),
    ("proposed", "rejected"),
    ("proposed", "withdrawn"),
    ("accepted", "superseded"),
    ("accepted", "retired"),
})
# ADRG §6 required body headings (canonical H2 spelling from the template).
ADR_REQUIRED_HEADINGS: tuple[str, ...] = (
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

ADR_ID_PATTERN = re.compile(r"^ADR-[0-9]{4}$")
ADR_FILENAME_PATTERN = re.compile(r"^ADR-([0-9]{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_BLOCK = re.compile(r"\A<!-- praxis:adr\s*\n(?P<payload>\{.*?\})\s*\n-->", re.DOTALL)
_RFC3339_SKELETON = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

_FAIL_SEVERITIES: frozenset[str] = frozenset({"BLOCKER", "HIGH"})

# Exit codes returned by audit_adrs (single home alongside the CLI surface).
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INCONCLUSIVE = 3


class AdrSchemaUnavailable(Exception):
    """Raised when ``schemas/adr-metadata.schema.json`` is missing, unreadable,
    not valid JSON, or semantically unsupported by the closed validator. The
    audit must treat this as inconclusive (exit 3), never pass or fail."""


# --------------------------------------------------------------------------- #
# Read-only helpers
# --------------------------------------------------------------------------- #
def _now_utc() -> str:
    """Current time as a UTC RFC 3339 ``Z`` string (audit-result policy)."""
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: Any) -> datetime | None:
    """Parse a UTC RFC 3339 timestamp (``Z`` or ``+00:00`` only)."""
    if not isinstance(value, str) or not _RFC3339_SKELETON.match(value):
        return None
    if not (value.endswith("Z") or value.endswith("+00:00")):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


def decisions_dir(repo: Path) -> str:
    """Resolve the configured ``paths.decisions`` directory, best-effort.

    Returns ``docs/decisions`` when ``.praxis.toml`` is absent, unparseable,
    or does not declare the path. Never raises.

    This returns the raw configured value; it does NOT guarantee the value
    stays inside the repo. Use :func:`_safe_decisions_dir` for any path that
    will actually be read, and :func:`_decisions_escape_error` to surface a
    path-escape condition.
    """
    path = repo / ".praxis.toml"
    if not path.is_file():
        return DEFAULT_DECISIONS_DIR
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_DECISIONS_DIR
    paths = config.get("paths")
    if isinstance(paths, dict) and isinstance(paths.get("decisions"), str):
        return paths["decisions"]
    return DEFAULT_DECISIONS_DIR


def _decisions_escape_error(repo: Path, configured: str) -> str | None:
    """Return a stable error string when ``configured`` is unsafe for ``repo``.

    Rejects absolute paths, ANY literal ``..`` segment (even when ``resolve()``
    would stay inside the repo), and symlinks that resolve outside the
    repository root. Returns ``None`` when the path is safe. Never raises: an
    unresolvable path is treated as an escape.
    """
    candidate = Path(configured)
    if candidate.is_absolute():
        return "paths.decisions must be a relative path within the repo"
    if ".." in candidate.parts:
        # Hard rule: reject any literal '..' segment even when resolve() would
        # stay inside the repo (e.g. docs/../docs/decisions).
        return "paths.decisions must not contain '..' path segments"
    try:
        repo_root = repo.resolve()
        target = (repo / candidate).resolve()
    except (OSError, RuntimeError):
        return "paths.decisions could not be resolved within the repo"
    try:
        target.relative_to(repo_root)
    except ValueError:
        return (
            "paths.decisions resolves outside the repo (absolute, '..' "
            "traversal, or external symlink)"
        )
    return None


def _safe_decisions_dir(repo: Path) -> str:
    """Return the effective decisions directory, falling back when unsafe.

    Returns the configured ``paths.decisions`` when it stays inside the repo,
    otherwise :data:`DEFAULT_DECISIONS_DIR`. All read paths must go through
    this helper so a malicious configuration can never read outside the repo.
    """
    configured = decisions_dir(repo)
    if _decisions_escape_error(repo, configured) is not None:
        return DEFAULT_DECISIONS_DIR
    return configured


def _config_best_effort(repo: Path) -> dict[str, Any]:
    path = repo / ".praxis.toml"
    if not path.is_file():
        return {}
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return config if isinstance(config, dict) else {}


@dataclass(frozen=True)
class AdrRecord:
    """One discovered ADR file with its parsed metadata (or a parse error)."""

    path: Path
    relpath: str
    filename: str
    text: str
    metadata: dict[str, Any] | None
    parse_error: str | None

    @property
    def adr_id(self) -> str | None:
        if self.metadata is None:
            return None
        value = self.metadata.get("id")
        return value if isinstance(value, str) else None


def load_adr_schema(repo: Path) -> dict[str, Any]:
    """Load and verify ``schemas/adr-metadata.schema.json`` from the repo.

    Raises :class:`AdrSchemaUnavailable` when the standard schema is missing,
    unreadable, not valid JSON, or semantically unsupported by the closed
    runtime validator. Mirrors :func:`project.load_project_config_schema`.
    """
    schema_path = repo / ADR_METADATA_SCHEMA
    if not schema_path.is_file():
        raise AdrSchemaUnavailable(f"{ADR_METADATA_SCHEMA} not found in repo")
    try:
        text = schema_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AdrSchemaUnavailable(f"{ADR_METADATA_SCHEMA} unreadable: {exc}") from exc
    try:
        schema = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdrSchemaUnavailable(f"{ADR_METADATA_SCHEMA} is not valid JSON: {exc}") from exc
    inspect_diags = sv.inspect_schema(schema)
    if inspect_diags:
        detail = "; ".join(f"{d.code}@{d.path}: {d.message}" for d in inspect_diags[:3])
        raise AdrSchemaUnavailable(
            f"{ADR_METADATA_SCHEMA} is semantically unsupported by the closed "
            f"validator ({len(inspect_diags)} diagnostic(s)): {detail}"
        )
    return schema


def _load_one(path: Path, repo: Path) -> AdrRecord:
    rel = path.relative_to(repo).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return AdrRecord(path, rel, path.name, "", None, f"unreadable: {exc}")
    match = ADR_BLOCK.search(text)
    if not match:
        return AdrRecord(path, rel, path.name, text, None, "missing praxis:adr metadata block")
    payload = match.group("payload")
    try:
        metadata = sv.loads_strict(payload)
    except ValueError as exc:  # StrictJSONError (dup keys/non-finite) or JSONDecodeError
        return AdrRecord(path, rel, path.name, text, None, f"invalid JSON: {exc}")
    if not isinstance(metadata, dict):
        return AdrRecord(path, rel, path.name, text, None, "metadata block is not a JSON object")
    return AdrRecord(path, rel, path.name, text, metadata, None)


def load_adrs(repo: Path) -> list[AdrRecord]:
    """Discover and parse every ``ADR-*.md`` under the decisions directory.

    Returns a deterministic list ordered by filename. Records whose metadata
    block is missing or unparseable are returned with ``metadata=None`` and a
    ``parse_error`` string; callers decide how to surface them.

    The directory is resolved via :func:`_safe_decisions_dir`, so a
    ``paths.decisions`` value that escapes the repo is never followed.
    """
    directory = repo / _safe_decisions_dir(repo)
    if not directory.is_dir():
        return []
    records: list[AdrRecord] = []
    for path in sorted(directory.glob("ADR-*.md")):
        records.append(_load_one(path, repo))
    return records


# --------------------------------------------------------------------------- #
# Finding / diagnostic builders
# --------------------------------------------------------------------------- #
def _finding(
    fid: str, severity: str, message: str, evidence: dict[str, Any], remediation: str
) -> dict[str, Any]:
    return {
        "id": fid,
        "severity": severity,
        "message": message,
        "evidence": evidence,
        "remediation": remediation,
    }


def _diagnostic(code: str, level: str, message: str) -> dict[str, Any]:
    return {"code": code, "level": level, "message": message}


# --------------------------------------------------------------------------- #
# Per-ADR audits
# --------------------------------------------------------------------------- #
def _audit_metadata_schema(record: AdrRecord, schema: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for diag in sv.validate(record.metadata, schema):
        findings.append(_finding(
            "adr-metadata", "HIGH", diag.message,
            {"path": record.relpath, "code": diag.code, "json_pointer": diag.path},
            "Fix the metadata so it conforms to schemas/adr-metadata.schema.json.",
        ))
    return findings


def _audit_filename_id(record: AdrRecord) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    filename_match = ADR_FILENAME_PATTERN.match(record.filename)
    if filename_match is None:
        findings.append(_finding(
            "adr-filename-noncanonical", "HIGH",
            f"non-canonical ADR filename: {record.filename}",
            {"path": record.relpath, "filename": record.filename},
            "Rename to ADR-NNNN-slug.md matching the manifest filename pattern.",
        ))
        return findings
    adr_id = record.adr_id
    if adr_id is not None and ADR_ID_PATTERN.match(adr_id) is not None:
        if filename_match.group(1) != adr_id[len("ADR-"):]:
            findings.append(_finding(
                "adr-filename-id-mismatch", "HIGH",
                f"filename number {filename_match.group(1)} differs from id {adr_id}",
                {"path": record.relpath, "filename": record.filename, "id": adr_id},
                "Align the filename number and the metadata id.",
            ))
    return findings


def _audit_headings(record: AdrRecord) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for heading in ADR_REQUIRED_HEADINGS:
        if re.search(rf"^##\s+{re.escape(heading)}\s*$", record.text, re.MULTILINE) is None:
            findings.append(_finding(
                "adr-heading-missing", "HIGH", f"missing required heading: {heading}",
                {"path": record.relpath, "heading": heading},
                f"Add a '## {heading}' section to the ADR body.",
            ))
    return findings


def _audit_transitions(record: AdrRecord) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    metadata = record.metadata or {}
    transitions = metadata.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        # The schema validator reports missing/empty transitions; nothing to
        # project here.
        return findings

    prev_to: str | None = None
    prev_at: datetime | None = None
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            findings.append(_finding(
                "adr-transition-invalid", "BLOCKER", f"transition {index} is not an object",
                {"path": record.relpath, "index": index},
                "Make each transition an object with from/to/at authority fields.",
            ))
            continue
        source = transition.get("from")
        target = transition.get("to")
        if (source, target) not in ADR_ALLOWED_TRANSITIONS:
            findings.append(_finding(
                "adr-transition-invalid", "BLOCKER",
                f"transition {index} is not allowed: {source!r}->{target!r}",
                {"path": record.relpath, "index": index, "from": source, "to": target},
                "Use only transitions permitted by docs/modulos/adrg.md §5.",
            ))
        if index > 0 and source != prev_to:
            findings.append(_finding(
                "adr-transition-invalid", "BLOCKER",
                f"transition {index} is not contiguous (expected from={prev_to!r})",
                {"path": record.relpath, "index": index, "expected_from": prev_to, "from": source},
                "Transitions must chain: each from must equal the previous to.",
            ))
        observed_at = _parse_utc(transition.get("at"))
        if observed_at is None:
            findings.append(_finding(
                "adr-transition-invalid", "BLOCKER",
                f"transition {index} has an invalid timestamp",
                {"path": record.relpath, "index": index, "at": transition.get("at")},
                "Use UTC RFC 3339 (Z) timestamps for every transition.",
            ))
        elif prev_at is not None and observed_at < prev_at:
            findings.append(_finding(
                "adr-transition-invalid", "BLOCKER",
                f"transition {index} moves backward in time",
                {"path": record.relpath, "index": index},
                "Keep transition timestamps monotonically non-decreasing.",
            ))
        prev_to = target if isinstance(target, str) else prev_to
        prev_at = observed_at if observed_at is not None else prev_at

    first = transitions[0] if isinstance(transitions[0], dict) else {}
    last = transitions[-1] if isinstance(transitions[-1], dict) else {}
    if first.get("from") is not None or first.get("to") != "draft":
        findings.append(_finding(
            "adr-transition-invalid", "BLOCKER",
            "first transition must create draft (from null, to draft)",
            {"path": record.relpath, "first_from": first.get("from"), "first_to": first.get("to")},
            "Start the transition history with {from: null, to: draft}.",
        ))
    if metadata.get("status") != last.get("to"):
        findings.append(_finding(
            "adr-status-projection", "BLOCKER",
            "status does not match the final transition",
            {"path": record.relpath, "status": metadata.get("status"), "final_to": last.get("to")},
            "Set status to the final transition's 'to' value.",
        ))
    if metadata.get("created_at") != first.get("at"):
        findings.append(_finding(
            "adr-created-at-projection", "BLOCKER",
            "created_at does not match the first transition",
            {"path": record.relpath, "created_at": metadata.get("created_at"), "first_at": first.get("at")},
            "Set created_at to the first transition's 'at' value.",
        ))
    return findings


def _index_by_id(records: list[AdrRecord]) -> tuple[dict[str, AdrRecord], set[str]]:
    by_id: dict[str, AdrRecord] = {}
    duplicates: set[str] = set()
    for record in records:
        adr_id = record.adr_id
        if adr_id is None or ADR_ID_PATTERN.match(adr_id) is None:
            continue
        if adr_id in by_id:
            duplicates.add(adr_id)
        else:
            by_id[adr_id] = record
    return by_id, duplicates


def _ids_for(metadata: dict[str, Any] | None, field: str) -> list[str]:
    """Return ``metadata[field]`` as a list[str], or [] when not a str list."""
    if metadata is None:
        return []
    value = metadata.get(field)
    if not isinstance(value, list):
        return []
    return value if all(isinstance(item, str) for item in value) else []


def _audit_relations(record: AdrRecord, by_id: dict[str, AdrRecord]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    metadata = record.metadata
    adr_id = record.adr_id
    rel = record.relpath

    linked = _ids_for(metadata, "supersedes") + _ids_for(metadata, "related")
    replacement = metadata.get("superseded_by") if metadata else None
    if adr_id is not None and (adr_id in linked or replacement == adr_id):
        findings.append(_finding(
            "adr-link-self", "HIGH", "ADR must not link to itself",
            {"path": rel, "id": adr_id},
            "Remove self-references from supersedes/superseded_by/related.",
        ))

    # supersedes: target must exist and reciprocate (superseded_by + status).
    for old_id in _ids_for(metadata, "supersedes"):
        target = by_id.get(old_id)
        if target is None:
            findings.append(_finding(
                "adr-link-missing", "HIGH", f"superseded ADR {old_id} does not exist",
                {"path": rel, "ref": old_id, "field": "supersedes"},
                f"Create {old_id} or remove the supersedes reference.",
            ))
        elif adr_id is not None:
            if target.metadata.get("superseded_by") != adr_id:
                findings.append(_finding(
                    "adr-link-nonreciprocal", "HIGH",
                    f"superseded ADR {old_id} does not point back via superseded_by",
                    {"path": rel, "ref": old_id, "field": "supersedes"},
                    f"Set {old_id}.superseded_by to {adr_id}.",
                ))
            if target.metadata.get("status") != "superseded":
                findings.append(_finding(
                    "adr-link-nonreciprocal", "HIGH",
                    f"superseded ADR {old_id} is not in status 'superseded'",
                    {"path": rel, "ref": old_id, "field": "supersedes"},
                    f"Transition {old_id} to 'superseded' in a single logical operation.",
                ))

    # superseded_by: target must exist and list this ADR in its supersedes.
    if isinstance(replacement, str) and replacement:
        target = by_id.get(replacement)
        if target is None:
            findings.append(_finding(
                "adr-link-missing", "HIGH", f"replacement ADR {replacement} does not exist",
                {"path": rel, "ref": replacement, "field": "superseded_by"},
                f"Create {replacement} or remove the superseded_by reference.",
            ))
        elif adr_id is not None and adr_id not in _ids_for(target.metadata, "supersedes"):
            findings.append(_finding(
                "adr-link-nonreciprocal", "HIGH",
                f"replacement ADR {replacement} does not list this in supersedes",
                {"path": rel, "ref": replacement, "field": "superseded_by"},
                f"Add {adr_id} to {replacement}.supersedes.",
            ))

    # related: existence only (no reciprocity, per ADRG scope).
    for related_id in _ids_for(metadata, "related"):
        if related_id not in by_id:
            findings.append(_finding(
                "adr-link-missing", "HIGH", f"related ADR {related_id} does not exist",
                {"path": rel, "ref": related_id, "field": "related"},
                f"Create {related_id} or remove the related reference.",
            ))
    return findings


# --------------------------------------------------------------------------- #
# Public payload builders
# --------------------------------------------------------------------------- #
def audit_adrs(repo: Path) -> tuple[dict[str, Any], int]:
    """Audit ADRs in ``repo`` and return ``(audit_result, exit_code)``.

    The result always satisfies ``schemas/audit-result.schema.json``. Exit is
    ``0`` on pass, ``1`` when any BLOCKER/HIGH finding is produced, and ``3``
    when the ADR metadata standard schema is unavailable (inconclusive). In the
    inconclusive case only factual observations (missing decisions directory,
    unparseable metadata blocks) are reported; content checks that depend on
    the schema contract are skipped.
    """
    findings: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    configured_dir = decisions_dir(repo)
    escape_error = _decisions_escape_error(repo, configured_dir)
    if escape_error is not None:
        findings.append(_finding(
            "adr-decisions-path-escape", "BLOCKER", escape_error,
            {"configured": configured_dir, "fallback": DEFAULT_DECISIONS_DIR},
            "Set paths.decisions to a relative path that stays inside the repo.",
        ))

    directory_rel = _safe_decisions_dir(repo)
    directory = repo / directory_rel

    schema_unavailable = False
    schema: dict[str, Any] | None = None
    try:
        schema = load_adr_schema(repo)
    except AdrSchemaUnavailable as exc:
        schema_unavailable = True
        diagnostics.append(_diagnostic("adr-schema-unavailable", "error", str(exc)))

    if not directory.is_dir():
        findings.append(_finding(
            "adr-directory-missing", "BLOCKER",
            f"decisions directory missing: {directory_rel}",
            {"path": directory_rel},
            "Create the directory declared in .praxis.toml paths.decisions.",
        ))

    records = load_adrs(repo)
    # Parse errors are always factual BLOCKER findings (inventory parity with list).
    for record in records:
        if record.parse_error is not None:
            findings.append(_finding(
                "adr-metadata-unparseable", "BLOCKER",
                f"could not parse metadata: {record.parse_error}",
                {"path": record.relpath, "filename": record.filename, "problem": record.parse_error},
                "Fix the praxis:adr JSON block so it parses without duplicate keys.",
            ))

    if schema is not None:
        by_id, duplicate_ids = _index_by_id(records)
        for dup_id in sorted(duplicate_ids):
            findings.append(_finding(
                "adr-duplicate-id", "BLOCKER", f"duplicate ADR id: {dup_id}",
                {"id": dup_id},
                "ADR numbers must be unique and never reused.",
            ))
        for record in records:
            if record.metadata is None:
                continue
            findings.extend(_audit_metadata_schema(record, schema))
            findings.extend(_audit_filename_id(record))
            findings.extend(_audit_headings(record))
            findings.extend(_audit_transitions(record))
        for record in records:
            if record.metadata is not None:
                findings.extend(_audit_relations(record, by_id))

    config = _config_best_effort(repo)
    project_id = config.get("project_id") if isinstance(config.get("project_id"), str) else None
    standard_version = (
        config["standard_version"]
        if isinstance(config.get("standard_version"), str)
        else "unknown"
    )
    profile = config["profile"] if isinstance(config.get("profile"), str) else None
    level = PROFILE_LEVELS.get(profile, "L0")

    observed_revision = head_revision(repo)
    if observed_revision is None:
        diagnostics.append(_diagnostic(
            "head-unobtainable", "warning",
            "could not resolve git HEAD (not a repo or git unavailable)",
        ))

    if schema_unavailable:
        result, exit_code = "inconclusive", EXIT_INCONCLUSIVE
    elif any(f["severity"] in _FAIL_SEVERITIES for f in findings):
        result, exit_code = "fail", EXIT_FAIL
    else:
        result, exit_code = "pass", EXIT_PASS

    audit_result = {
        "schema": AUDIT_RESULT_SCHEMA_ID,
        "tool_version": TOOL_VERSION,
        "standard_version": standard_version,
        "project_id": project_id,
        "observed_revision": observed_revision,
        "profile": profile or "unknown",
        "result": result,
        "level": level,
        "findings": findings,
        "diagnostics": diagnostics,
        "observed_at": _now_utc(),
    }
    return audit_result, exit_code


def list_adrs(repo: Path, status_filter: str | None = None) -> dict[str, Any]:
    """Build the stable ``praxis/adr-list/v1`` informational payload.

    Unparseable records are surfaced in ``unparseable[]`` (parity with audit,
    where they become BLOCKER findings). ``--status`` filters only parseable
    records whose ``status`` field matches exactly.
    """
    records = load_adrs(repo)
    adrs: list[dict[str, Any]] = []
    unparseable: list[dict[str, Any]] = []
    for record in records:
        if record.metadata is None:
            unparseable.append({
                "filename": record.filename,
                "path": record.relpath,
                "problem": record.parse_error,
            })
            continue
        status = record.metadata.get("status")
        if status_filter is not None and status != status_filter:
            continue
        adrs.append({
            "id": record.metadata.get("id"),
            "title": record.metadata.get("title"),
            "status": status,
            "filename": record.filename,
            "path": record.relpath,
        })
    adrs.sort(key=lambda entry: (entry.get("id") or "", entry.get("path") or ""))
    configured_dir = decisions_dir(repo)
    return {
        "schema": LIST_SCHEMA_ID,
        "tool_version": TOOL_VERSION,
        "repo": str(repo.resolve()),
        "decisions_dir": _safe_decisions_dir(repo),
        "decisions_dir_error": _decisions_escape_error(repo, configured_dir),
        "adrs": adrs,
        "unparseable": unparseable,
        "count": len(adrs),
        "unparseable_count": len(unparseable),
    }


def show_adr(repo: Path, adr_id: str) -> dict[str, Any]:
    """Build the stable ``praxis/adr-summary/v1`` informational payload.

    Looks up the ADR by its metadata ``id``. ``found`` is ``False`` when no
    parseable ADR carries that id; the caller maps that to exit 1.
    """
    records = load_adrs(repo)
    escape_error = _decisions_escape_error(repo, decisions_dir(repo))
    for record in records:
        if record.metadata is not None and record.metadata.get("id") == adr_id:
            return {
                "schema": SUMMARY_SCHEMA_ID,
                "tool_version": TOOL_VERSION,
                "repo": str(repo.resolve()),
                "id": adr_id,
                "found": True,
                "metadata": record.metadata,
                "filename": record.filename,
                "path": record.relpath,
                "decisions_dir_error": escape_error,
            }
    return {
        "schema": SUMMARY_SCHEMA_ID,
        "tool_version": TOOL_VERSION,
        "repo": str(repo.resolve()),
        "id": adr_id,
        "found": False,
        "metadata": None,
        "filename": None,
        "path": None,
        "decisions_dir_error": escape_error,
    }


__all__ = [
    "ADR_ALLOWED_TRANSITIONS",
    "ADR_METADATA_SCHEMA",
    "ADR_REQUIRED_HEADINGS",
    "ADR_STATUSES",
    "DEFAULT_DECISIONS_DIR",
    "EXIT_FAIL",
    "EXIT_INCONCLUSIVE",
    "EXIT_PASS",
    "AdrRecord",
    "AdrSchemaUnavailable",
    "audit_adrs",
    "decisions_dir",
    "head_revision",
    "list_adrs",
    "load_adr_schema",
    "load_adrs",
    "show_adr",
]
