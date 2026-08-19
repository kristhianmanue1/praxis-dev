"""Governed mutation planning (F2 increment 1, proposed).

This module backs ``praxis project init-plan``: it observes a repository
read-only and emits a ``praxis/mutation-plan/v1`` artifact that MUST satisfy
``schemas/plan.schema.json`` (embedded as :data:`praxis_dev.plan_schema.PLAN_SCHEMA`
for distribution). It never mutates the target repository.

Plan model
----------
A plan binds proposed ``create`` actions to the exact observed state via
content digests:

* ``observed_state.fingerprint`` — JCS digest over the target files and git
  ``HEAD``; any drift invalidates a later ``init-apply``.
* each action carries ``expected_before_sha256`` (null for ``create``: the
  path must not exist) and ``content_sha256`` (exact bytes to write).
* ``plan_fingerprint`` — sha256 over the RFC 8785 canonicalization of the plan
  WITHOUT the ``plan_fingerprint`` member itself, then inserted. An apply
  consumes this digest, not the file bytes.

Canonicalization subset
-----------------------
RFC 8785 (JCS) is implemented for the value domain plans actually use:
objects, arrays, ``str``, ``int``, ``bool`` and ``None``. Floats are rejected
(JCS number serialization for floats is not needed here and rejecting keeps
the implementation total and testable). Keys in plans are ASCII, where UTF-16
code-unit ordering (JCS) and Python ordering coincide.

Determinism
-----------
Given the same repository state, the same injected ``project_id`` and the
same ``now`` timestamp, ``build_init_plan`` produces byte-identical plans.
``uuid.uuid4()`` and wall-clock time are used only when the caller does not
inject them (the CLI never injects; tests do).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from praxis_dev.project import TOOL_VERSION, head_revision

MUTATION_PLAN_SCHEMA_ID = "praxis/mutation-plan/v1"
INIT_PLAN_RESULT_SCHEMA_ID = "praxis/init-plan-result/v1"
OPERATION = "project-init"
REQUIRED_AUTHORITY = "development-advisory"

# Order matters for stable digests over the target set.
TARGET_FILES: tuple[str, ...] = (
    ".praxis.toml",
    "AGENTS.md",
    "POLICY.md",
    "decisions/README.md",
    "specs/README.md",
)

STANDARD_VERSION = "0.1.0-draft.1"


class TargetStateError(Exception):
    """Raised when the target repository cannot be observed read-only."""


# --------------------------------------------------------------------------- #
# RFC 8785 (JCS) subset + digests
# --------------------------------------------------------------------------- #
def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("floats are outside the supported JCS value domain")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def jcs(value: Any) -> str:
    """Serialize ``value`` per RFC 8785 (JCS) for the supported subset.

    Objects sort by key (ASCII keys: Python and UTF-16 ordering coincide),
    strings use minimal escaping (``ensure_ascii=False``), separators are
    compact, and non-finite numbers are impossible because floats are
    rejected outright.
    """
    _reject_floats(value)
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_digest(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def plan_fingerprint(plan: dict[str, Any]) -> str:
    """Digest of the plan without its own ``plan_fingerprint`` member."""
    body = {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    return sha256_digest(jcs(body))


# --------------------------------------------------------------------------- #
# Read-only observation
# --------------------------------------------------------------------------- #
def _file_sha256(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise TargetStateError(f"cannot read {path.name}: {exc}") from exc
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git_remote(repo: Path) -> str | None:
    """Return the ``origin`` remote URL, read-only, or ``None``."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def observe_targets(repo: Path) -> dict[str, str | None]:
    """Content digest of every target path (None when absent)."""
    return {rel: _file_sha256(repo / rel) for rel in TARGET_FILES}


def observed_fingerprint(targets: dict[str, str | None], head: str | None) -> str:
    payload = {"files": targets, "head": head}
    return sha256_digest(jcs(payload))


# --------------------------------------------------------------------------- #
# Init template
# --------------------------------------------------------------------------- #
def render_config(project_id: str, profile: str = "minimal") -> str:
    return f"""\
schema = "praxis/project-config/v1"
project_id = "{project_id}"
standard_version = "{STANDARD_VERSION}"
profile = "{profile}"
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


_AGENTS_STUB = """\
# AGENTS.md

Contrato de agente del proyecto. Sustituye este stub por el contrato real y
manten el estado de decisiones fuera de este archivo.
"""

_POLICY_STUB = """\
# POLICY.md

Política operativa del proyecto. Sustituye este stub por la política real.
"""

_DECISIONS_STUB = """\
# Decisiones

ADRs del proyecto. El índice es derivado; no lo mantengas a mano.
"""

_SPECS_STUB = """\
# SPECs

Especificaciones del proyecto.
"""


def template_contents(project_id: str, profile: str = "minimal") -> dict[str, str]:
    """Exact bytes each target file must receive from ``init-apply``."""
    return {
        ".praxis.toml": render_config(project_id, profile),
        "AGENTS.md": _AGENTS_STUB,
        "POLICY.md": _POLICY_STUB,
        "decisions/README.md": _DECISIONS_STUB,
        "specs/README.md": _SPECS_STUB,
    }


# --------------------------------------------------------------------------- #
# Plan builder
# --------------------------------------------------------------------------- #
def classify_state(observed: dict[str, str | None], expected: dict[str, str]) -> str:
    """Classify the target set: ``create`` | ``identical`` | ``conflict``.

    ``create``     — no target exists (a clean initialization).
    ``identical``  — every target exists with exactly the template bytes.
    ``conflict``   — anything else: partial presence, or content that differs
                     from the template (init never overwrites).
    """
    present = {rel: digest for rel, digest in observed.items() if digest is not None}
    if not present:
        return "create"
    expected_digests = {
        rel: sha256_digest(content) for rel, content in expected.items()
    }
    if present == expected_digests:
        return "identical"
    return "conflict"


def _existing_identity(repo: Path) -> tuple[str, str] | None:
    """Read ``project_id``/``profile`` from an existing ``.praxis.toml``.

    Returns ``None`` when the file is absent, unparseable, or lacks a usable
    identity — callers treat that as a conflict (init never rewrites an
    identity it cannot understand).
    """
    import tomllib

    path = repo / ".praxis.toml"
    if not path.is_file():
        return None
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    project_id = parsed.get("project_id")
    profile = parsed.get("profile")
    if not isinstance(project_id, str) or not project_id:
        return None
    if not isinstance(profile, str) or profile not in ("minimal", "standard", "high-assurance", "regulated"):
        return None
    return project_id, profile


def build_init_plan(
    repo: Path,
    *,
    project_id: str | None = None,
    profile: str = "minimal",
    now: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    """Observe ``repo`` read-only and build the init mutation plan.

    Returns ``(plan, classification, contents)``. The plan is fully schema
    valid for classification ``create``; for ``identical``/``conflict`` the
    caller must NOT offer a plan (there is nothing valid to apply), and the
    returned plan is built anyway for testing purposes only.

    When ``.praxis.toml`` already exists, its ``project_id`` and ``profile``
    drive the template rendering (so a completed initialization classifies as
    ``identical``); an explicit ``project_id`` argument still wins.
    """
    import datetime

    repo = Path(repo)
    if not repo.is_dir():
        raise TargetStateError(f"not a directory: {repo}")
    existing = _existing_identity(repo)
    if existing is not None and project_id is None:
        project_id, profile = existing
    if project_id is None:
        project_id = str(uuid.uuid4())
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    observed = observe_targets(repo)
    head = head_revision(repo)
    remote = git_remote(repo)
    fingerprint = observed_fingerprint(observed, head)
    contents = template_contents(project_id, profile)
    classification = classify_state(observed, contents)

    actions = [
        {
            "action_id": f"create-{index}-{rel}",
            "kind": "create",
            "path": rel,
            "expected_before_sha256": None,
            "content_sha256": sha256_digest(contents[rel]),
        }
        for index, rel in enumerate(TARGET_FILES, start=1)
    ]
    preconditions = [
        {
            "kind": "targets-absent",
            "subject": ",".join(TARGET_FILES),
            "expected": True,
        }
    ]
    postconditions = [
        {
            "kind": "file-sha256",
            "subject": rel,
            "expected": sha256_digest(contents[rel]),
        }
        for rel in TARGET_FILES
    ]
    plan = {
        "schema": MUTATION_PLAN_SCHEMA_ID,
        "operation_id": "init-" + fingerprint[len("sha256:") :][:12],
        "operation": OPERATION,
        "project": {
            "project_id": project_id,
            "root_digest": fingerprint,
            "remote": remote,
            "head": head,
        },
        "observed_state": {
            "fingerprint": fingerprint,
            "files": observed,
            "classification": classification,
        },
        "allowed_paths": list(TARGET_FILES),
        "preconditions": preconditions,
        "actions": actions,
        "postconditions": postconditions,
        "required_authority": REQUIRED_AUTHORITY,
        "created_at": now,
        "expires_at": None,
        "canonicalization": "RFC8785",
    }
    plan["plan_fingerprint"] = plan_fingerprint(plan)
    return plan, classification, contents


__all__ = [
    "INIT_PLAN_RESULT_SCHEMA_ID",
    "MUTATION_PLAN_SCHEMA_ID",
    "OPERATION",
    "REQUIRED_AUTHORITY",
    "STANDARD_VERSION",
    "TARGET_FILES",
    "TargetStateError",
    "build_init_plan",
    "classify_state",
    "git_remote",
    "jcs",
    "observe_targets",
    "observed_fingerprint",
    "plan_fingerprint",
    "render_config",
    "sha256_digest",
    "template_contents",
]
