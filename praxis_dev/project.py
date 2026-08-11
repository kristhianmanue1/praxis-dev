"""Read-only Praxis project inspection (F1, proposed).

This module backs the ``praxis project`` read-only CLI surface. It loads a
project's ``.praxis.toml`` with :mod:`tomllib`, audits the normalized
configuration against ``schemas/project-config.schema.json`` using the closed
runtime validator (:mod:`praxis_dev.schema_validation`), checks the declared
contract paths, and resolves the current git ``HEAD`` without writing to the
target repository. It produces two payloads:

* ``audit_project`` -> an ``praxis/audit-result/v1`` object, which MUST satisfy
  ``schemas/audit-result.schema.json`` (timestamps are UTC ``Z``).
* ``status_payload`` -> an ``praxis/project-status/v1`` object, documented in
  :mod:`praxis_dev.cli` (this is a new informational surface; it is intentionally
  NOT added to ``schemas/`` so the versioned standard is unchanged).

The module is stdlib-only and never imports ``jsonschema``.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from praxis_dev import schema_validation as sv

TOOL_VERSION = "0.1.0-draft.1"
AUDIT_RESULT_SCHEMA_ID = "praxis/audit-result/v1"
PROJECT_CONFIG_SCHEMA = "schemas/project-config.schema.json"

# Assurance level derived from the effective profile. L0 means the profile is
# unknown / absent; it is a reporting artifact, not a separate conformance tier.
PROFILE_LEVELS: dict[str, str] = {
    "minimal": "L1",
    "standard": "L2",
    "high-assurance": "L3",
    "regulated": "L4",
}
KNOWN_PROFILES: frozenset[str] = frozenset(PROFILE_LEVELS)

_FAIL_SEVERITIES: frozenset[str] = frozenset({"BLOCKER", "HIGH", "MED"})
_PATH_KINDS: dict[str, str] = {
    "agent_contract": "file",
    "policy": "file",
    "decisions": "directory",
    "specs": "directory",
}


class ConfigMalformed(Exception):
    """Raised when ``.praxis.toml`` is unparseable (contract malformed)."""


class ConfigUnreadable(Exception):
    """Raised when ``.praxis.toml`` exists but cannot be read (environment)."""


class StandardSchemaUnavailable(Exception):
    """Raised when the project-config standard schema is missing, unreadable,
    or not valid JSON, so the config contract cannot be validated. The audit
    must treat this as inconclusive (exit 3), never pass."""


# Exit codes returned by audit_project (kept here to avoid a circular import
# with :mod:`praxis_dev.cli`, which re-uses them).
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INCONCLUSIVE = 3


# --------------------------------------------------------------------------- #
# Low-level, read-only helpers
# --------------------------------------------------------------------------- #
def _now_utc() -> str:
    """Current time as a UTC RFC 3339 ``Z`` string (audit-result policy)."""
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def head_revision(repo: Path) -> str | None:
    """Return the git ``HEAD`` sha (40/64 hex) of ``repo``, read-only.

    Uses ``git rev-parse`` which performs no writes. Returns ``None`` when git
    is unavailable, the path is not a repository, or resolution times out.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    sha = completed.stdout.strip()
    return sha or None


def _try_config(repo: Path) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Best-effort config load for informational callers.

    Returns ``(present, parsed_or_None, error_or_None)``. ``present`` is True
    when the file exists (even if it failed to parse). Used by ``status``.
    """
    path = repo / ".praxis.toml"
    if not path.is_file():
        return False, None, None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return True, None, f"unreadable: {exc}"
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return True, None, str(exc)
    return True, parsed, None


def load_config(repo: Path) -> dict[str, Any] | None:
    """Load and parse ``.praxis.toml``.

    Returns ``None`` when the file is missing. Raises :class:`ConfigMalformed`
    on a TOML syntax error and :class:`ConfigUnreadable` on an OS-level read
    failure (other than missing).
    """
    path = repo / ".praxis.toml"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigUnreadable(str(exc)) from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigMalformed(str(exc)) from exc


def load_project_config_schema(repo: Path) -> dict[str, Any]:
    """Load and verify ``schemas/project-config.schema.json`` from the repo.

    Raises :class:`StandardSchemaUnavailable` when the standard schema is
    missing, unreadable, not valid JSON, or **semantically unsupported** by the
    closed runtime validator (``sv.inspect_schema`` returns diagnostics). In
    every such case the config contract cannot be validated and the audit is
    inconclusive; no config findings are derived from an unsupported schema.
    """
    schema_path = repo / PROJECT_CONFIG_SCHEMA
    if not schema_path.is_file():
        raise StandardSchemaUnavailable(f"{PROJECT_CONFIG_SCHEMA} not found in repo")
    try:
        text = schema_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StandardSchemaUnavailable(f"{PROJECT_CONFIG_SCHEMA} unreadable: {exc}") from exc
    try:
        schema = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StandardSchemaUnavailable(f"{PROJECT_CONFIG_SCHEMA} is not valid JSON: {exc}") from exc
    inspect_diags = sv.inspect_schema(schema)
    if inspect_diags:
        detail = "; ".join(
            f"{d.code}@{d.path}: {d.message}" for d in inspect_diags[:3]
        )
        raise StandardSchemaUnavailable(
            f"{PROJECT_CONFIG_SCHEMA} is semantically unsupported by the closed "
            f"validator ({len(inspect_diags)} diagnostic(s)): {detail}"
        )
    return schema


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


def _path_findings(repo: Path, paths: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(paths, dict):
        return findings, diagnostics
    repo_resolved = repo.resolve()
    for key, kind in _PATH_KINDS.items():
        rel = paths.get(key)
        if not isinstance(rel, str):
            continue
        target = (repo / rel).resolve()
        try:
            target.relative_to(repo_resolved)
        except ValueError:
            findings.append(_finding(
                f"path-{key}", "HIGH", f"declared path {key!r} escapes the repo: {rel}",
                {"key": key, "expected_kind": kind, "path": rel, "problem": "escapes-repo"},
                f"Keep {key} inside the repo and update .praxis.toml.",
            ))
            continue
        if kind == "file" and not target.is_file():
            problem = "not-a-file"
        elif kind == "directory" and not target.is_dir():
            problem = "not-a-directory"
        else:
            continue
        findings.append(_finding(
            f"path-{key}", "HIGH", f"declared path {key!r} ({kind}) missing: {rel}",
            {"key": key, "expected_kind": kind, "path": rel, "problem": problem},
            f"Create the declared {kind} at {rel} or update .praxis.toml.",
        ))
    return findings, diagnostics


# --------------------------------------------------------------------------- #
# Public payload builders
# --------------------------------------------------------------------------- #
def audit_project(repo: Path, profile: str | None = None) -> tuple[dict[str, Any], int]:
    """Audit ``repo`` and return ``(audit_result, exit_code)``.

    The result object always satisfies ``schemas/audit-result.schema.json``.
    Exit code is 0 on pass, 1 on fail (missing/invalid config or paths). TOML
    syntax errors and unreadable configs surface as exceptions for the CLI to
    map to exit codes 2 and 3 respectively.
    """
    config = load_config(repo)
    findings: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    project_id: str | None = None
    standard_version = "unknown"
    config_profile: str | None = None
    schema_unavailable = False

    if config is None:
        findings.append(_finding(
            "config-missing", "BLOCKER", ".praxis.toml is missing",
            {"path": str(repo / ".praxis.toml")},
            "Create a .praxis.toml conforming to schemas/project-config.schema.json.",
        ))
    else:
        project_id = config.get("project_id") if isinstance(config.get("project_id"), str) else None
        if isinstance(config.get("standard_version"), str):
            standard_version = config["standard_version"]
        if isinstance(config.get("profile"), str):
            config_profile = config["profile"]

        try:
            schema = load_project_config_schema(repo)
        except StandardSchemaUnavailable as exc:
            # The config contract cannot be validated: this is NOT a pass and
            # NOT a fail of the project; it is inconclusive by environment.
            schema_unavailable = True
            diagnostics.append(_diagnostic("standard-schema-unavailable", "error", str(exc)))
            schema = None
        if schema is not None:
            for diag in sv.validate(config, schema):
                findings.append(_finding(
                    f"config-{diag.code}", "HIGH", diag.message,
                    {"path": diag.path, "code": diag.code},
                    "Fix .praxis.toml so it conforms to schemas/project-config.schema.json.",
                ))
                diagnostics.append(_diagnostic(diag.code, "error", diag.message))

        # Path checks are factual even when the schema is unavailable; they are
        # reported as findings but never override an inconclusive result.
        path_findings, _ = _path_findings(repo, config.get("paths"))
        findings.extend(path_findings)

    effective_profile = profile or config_profile
    observed_revision = head_revision(repo)
    if observed_revision is None:
        diagnostics.append(_diagnostic(
            "head-unobtainable", "warning", "could not resolve git HEAD (not a repo or git unavailable)",
        ))

    if config is None:
        result = "fail"
        exit_code = EXIT_FAIL
    elif schema_unavailable:
        result = "inconclusive"
        exit_code = EXIT_INCONCLUSIVE
    elif any(f["severity"] in _FAIL_SEVERITIES for f in findings):
        result = "fail"
        exit_code = EXIT_FAIL
    else:
        result = "pass"
        exit_code = EXIT_PASS
    level = PROFILE_LEVELS.get(effective_profile, "L0")

    audit_result = {
        "schema": AUDIT_RESULT_SCHEMA_ID,
        "tool_version": TOOL_VERSION,
        "standard_version": standard_version,
        "project_id": project_id,
        "observed_revision": observed_revision,
        "profile": effective_profile or "unknown",
        "result": result,
        "level": level,
        "findings": findings,
        "diagnostics": diagnostics,
        "observed_at": _now_utc(),
    }
    return audit_result, exit_code


def status_payload(repo: Path) -> dict[str, Any]:
    """Build the stable ``praxis/project-status/v1`` informational payload.

    Status is best-effort and never raises on config problems; it reports them
    in the payload. The shape is documented in :mod:`praxis_dev.cli`.
    """
    present, config, error = _try_config(repo)

    def _field(name: str, default: str) -> str:
        if config and isinstance(config.get(name), str):
            return config[name]
        return default

    return {
        "schema": "praxis/project-status/v1",
        "tool_version": TOOL_VERSION,
        "repo": str(repo.resolve()),
        "config_present": present,
        "config_parseable": config is not None,
        "config_error": error,
        "project_id": config.get("project_id") if (config and isinstance(config.get("project_id"), str)) else None,
        "standard_version": _field("standard_version", "unknown"),
        "profile": _field("profile", "unknown"),
        "lifecycle": _field("lifecycle", "unknown"),
        "observed_revision": head_revision(repo),
        "observed_at": _now_utc(),
    }


__all__ = [
    "EXIT_FAIL",
    "EXIT_INCONCLUSIVE",
    "EXIT_PASS",
    "KNOWN_PROFILES",
    "PROFILE_LEVELS",
    "TOOL_VERSION",
    "ConfigMalformed",
    "ConfigUnreadable",
    "StandardSchemaUnavailable",
    "audit_project",
    "head_revision",
    "load_config",
    "load_project_config_schema",
    "status_payload",
]
