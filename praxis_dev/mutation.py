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


# --------------------------------------------------------------------------- #
# Governed apply (F2 increment 2)
# --------------------------------------------------------------------------- #
# Exit codes for apply outcomes (single home; the CLI re-uses them).
APPLY_PASS = 0
APPLY_FAIL = 1
APPLY_DRIFT = 5  # contrato-cli.md §3: drift o conflicto concurrente


class PlanRejected(Exception):
    """A plan failed validation or state checks; carrying an outcome payload."""

    def __init__(self, outcome: dict[str, Any]) -> None:
        super().__init__(outcome.get("result", "rejected"))
        self.outcome = outcome


class PlanInvalid(PlanRejected):
    """The plan artifact does not satisfy the mutation-plan schema."""


class PlanDrift(PlanRejected):
    """Observed state no longer matches the plan's observed state."""


def _apply_result(
    result: str,
    diagnostics: list[dict[str, Any]],
    *,
    plan_fingerprint_value: str | None = None,
    applied: list[str] | None = None,
) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        "schema": "praxis/init-apply-result/v1",
        "tool_version": TOOL_VERSION,
        "result": result,
        "diagnostics": diagnostics,
    }
    if plan_fingerprint_value is not None:
        outcome["plan_fingerprint"] = plan_fingerprint_value
    if applied is not None:
        outcome["applied_actions"] = applied
    return outcome


def _reject_plan(plan: Any) -> dict[str, Any]:
    """Structural validation of the plan against the embedded schema."""
    diagnostics = sv_validate_plan(plan)
    if diagnostics:
        return _apply_result(
            "invalid-plan",
            [
                {"code": f"plan-{d.code}", "level": "error", "message": d.message}
                for d in diagnostics
            ],
        )
    return _apply_result("ok", [])


def sv_validate_plan(plan: Any):
    """Validate ``plan`` against the embedded mutation-plan schema."""
    from praxis_dev import schema_validation as sv
    from praxis_dev.plan_schema import PLAN_SCHEMA

    return sv.validate(plan, PLAN_SCHEMA)


def load_plan_file(plan_path: Path) -> dict[str, Any]:
    """Load and structurally validate a plan artifact.

    Raises :class:`PlanInvalid` with a full outcome payload on failure.
    Duplicate JSON keys are rejected (contrato-cli.md §9).
    """
    from praxis_dev.schema_validation import loads_strict

    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {"code": "plan-unreadable", "level": "error", "message": str(exc)}
            ])
        ) from exc
    try:
        plan = loads_strict(text)
    except ValueError as exc:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {"code": "plan-unparseable", "level": "error", "message": str(exc)}
            ])
        ) from exc
    if not isinstance(plan, dict):
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {"code": "plan-not-object", "level": "error",
                 "message": "plan artifact must be a JSON object"}
            ])
        )
    rejection = _reject_plan(plan)
    if rejection["result"] != "ok":
        raise PlanInvalid(rejection)
    return plan


def _check_fingerprint(plan: dict[str, Any], expected: str) -> None:
    actual = plan.get("plan_fingerprint")
    recomputed = plan_fingerprint(plan)
    if actual != recomputed:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-fingerprint-mismatch",
                    "level": "error",
                    "message": "plan_fingerprint does not match the plan body",
                }
            ])
        )
    if actual != expected:
        raise PlanInvalid(
            _apply_result("fingerprint-rejected", [
                {
                    "code": "plan-fingerprint-unexpected",
                    "level": "error",
                    "message": (
                        f"expected {expected}, plan carries {actual}; refusing "
                        "to apply anything other than the exact reviewed plan"
                    ),
                }
            ])
        )


def _check_operation(plan: dict[str, Any]) -> None:
    if plan.get("operation") != OPERATION:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-operation-unsupported",
                    "level": "error",
                    "message": f"init-apply only consumes {OPERATION!r} plans",
                }
            ])
        )
    if plan.get("required_authority") != REQUIRED_AUTHORITY:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-authority-unsupported",
                    "level": "error",
                    "message": (
                        f"init-apply only consumes plans requiring "
                        f"{REQUIRED_AUTHORITY!r} (got {plan.get('required_authority')!r})"
                    ),
                }
            ])
        )


def _check_expiry(plan: dict[str, Any], now: str | None = None) -> None:
    """Reject expired plans (``expires_at`` in the past). Null means no expiry."""
    import datetime as _dt

    expires = plan.get("expires_at")
    if not isinstance(expires, str) or not expires:
        return
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        exp = _dt.datetime.fromisoformat(expires.replace("Z", "+00:00"))
        current = _dt.datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-expiry-unparseable",
                    "level": "error",
                    "message": f"expires_at is not a valid RFC 3339 timestamp: {expires!r}",
                }
            ])
        ) from None
    if exp.tzinfo is None or current.tzinfo is None:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-expiry-naive",
                    "level": "error",
                    "message": "expires_at must carry an explicit timezone",
                }
            ])
        )
    if current >= exp:
        raise PlanDrift(
            _apply_result("drift", [
                {
                    "code": "plan-expired",
                    "level": "error",
                    "message": f"plan expired at {expires} (now {now}); replan",
                }
            ])
        )


_PATH_RE = None


def _safe_join(repo: Path, rel: str) -> Path:
    """Join and verify the path stays inside ``repo`` (no escape, no symlink).

    Raises :class:`PlanInvalid` (path not allowed) or :class:`PlanDrift`
    (parent is a symlink — the filesystem may have been tampered with).
    """
    global _PATH_RE
    import re

    if _PATH_RE is None:
        _PATH_RE = re.compile(
            r"^(?!\.{1,2}(?:/|$))(?!.*(?:^|/)\.{1,2}(?:/|$))"
            r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
        )
    if _PATH_RE.match(rel) is None:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-path-invalid",
                    "level": "error",
                    "message": f"action path is not a safe relative path: {rel!r}",
                }
            ])
        )
    repo_resolved = repo.resolve()
    target = repo / rel
    # Every existing ancestor must be a real directory (no symlinks).
    current = repo_resolved
    for part in Path(rel).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise PlanDrift(
                _apply_result("drift", [
                    {
                        "code": "path-ancestor-symlink",
                        "level": "error",
                        "message": f"ancestor of {rel!r} is a symlink: refusing",
                    }
                ])
            )
        if current.exists() and not current.is_dir():
            raise PlanInvalid(
                _apply_result("invalid-plan", [
                    {
                        "code": "plan-path-invalid",
                        "level": "error",
                        "message": f"ancestor of {rel!r} exists and is not a directory",
                    }
                ])
            )
    if target.is_symlink():
        raise PlanDrift(
            _apply_result("drift", [
                {
                    "code": "path-is-symlink",
                    "level": "error",
                    "message": f"target {rel!r} is a symlink: refusing",
                }
            ])
        )
    resolved = target.resolve()
    try:
        resolved.relative_to(repo_resolved)
    except ValueError:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-path-escape",
                    "level": "error",
                    "message": f"action path escapes the repository: {rel!r}",
                }
            ])
        ) from None
    return target


def _check_state_against_plan(repo: Path, plan: dict[str, Any]) -> None:
    """Fail on drift: observed state must match the plan exactly."""
    observed = observe_targets(repo)
    head = head_revision(repo)
    fingerprint_now = observed_fingerprint(observed, head)
    planned_fingerprint = plan["observed_state"]["fingerprint"]
    planned_files = plan["observed_state"].get("files", {})
    problems: list[dict[str, Any]] = []
    if fingerprint_now != planned_fingerprint:
        changed = [
            rel
            for rel in TARGET_FILES
            if observed.get(rel) != planned_files.get(rel)
        ]
        head_changed = plan["project"].get("head") != head
        problems.append({
            "code": "observed-state-drift",
            "level": "error",
            "message": (
                "repository state changed after planning "
                f"(files changed: {changed or 'none'}, head changed: {head_changed}); "
                "replan with init-plan"
            ),
        })
    for action in plan["actions"]:
        rel = action["path"]
        if rel not in plan["allowed_paths"]:
            problems.append({
                "code": "action-outside-allowed-paths",
                "level": "error",
                "message": f"action path {rel!r} is not in allowed_paths",
            })
    if problems:
        raise PlanDrift(_apply_result("drift", problems))


def _apply_actions(
    repo: Path, plan: dict[str, Any], contents: dict[str, str]
) -> list[str]:
    """Write every action; raises on first unexpected state.

    ``contents`` maps allowed path -> exact bytes (the template). The plan's
    per-action digests MUST match those bytes: a plan whose content hashes
    disagree with the canonical template is rejected, so init-apply cannot be
    used as an arbitrary file writer.
    """
    allowed_digests = {
        rel: sha256_digest(text) for rel, text in contents.items()
    }
    applied: list[str] = []
    for action in plan["actions"]:
        rel = action["path"]
        target = _safe_join(repo, rel)
        if action["kind"] != "create":
            raise PlanInvalid(
                _apply_result("invalid-plan", [
                    {
                        "code": "action-kind-unsupported",
                        "level": "error",
                        "message": f"init-apply only supports create (got {action['kind']!r})",
                    }
                ], applied=applied)
            )
        if action["content_sha256"] != allowed_digests.get(rel):
            raise PlanInvalid(
                _apply_result("invalid-plan", [
                    {
                        "code": "action-content-noncanonical",
                        "level": "error",
                        "message": (
                            f"action for {rel!r} does not carry the canonical "
                            "template digest; refusing arbitrary content"
                        ),
                    }
                ], applied=applied)
            )
        if target.exists():
            raise PlanDrift(
                _apply_result("drift", [
                    {
                        "code": "create-target-exists",
                        "level": "error",
                        "message": f"target {rel!r} appeared after planning",
                    }
                ], applied=applied)
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents[rel], encoding="utf-8")
        applied.append(action["action_id"])

    # Postconditions: verify on disk immediately after writing.
    for condition in plan["postconditions"]:
        rel = condition["subject"]
        if condition["kind"] != "file-sha256":
            continue
        target = _safe_join(repo, rel)
        actual = _file_sha256(target)
        if actual != condition["expected"]:
            raise PlanDrift(
                _apply_result("drift", [
                    {
                        "code": "postcondition-violated",
                        "level": "error",
                        "message": f"postcondition for {rel!r} not satisfied after write",
                    }
                ], applied=applied)
            )
    return applied


def apply_init_plan(
    repo: Path,
    plan_path: Path,
    expected_fingerprint: str,
) -> tuple[dict[str, Any], int]:
    """Apply a ``project-init`` mutation plan under full drift checking.

    Returns ``(outcome, exit_code)``. Never silently overwrites: any drift,
    unexpected path or existing target aborts before that action; earlier
    completed actions in the SAME apply remain (reported in
    ``applied_actions``) — the contract offers no transactional rollback, it
    offers fail-closed refusal, and drift on a later action leaves the
    repository in a state that the next ``init-plan`` will classify as
    ``conflict``, which is the honest outcome.
    """
    repo = Path(repo)
    if not repo.is_dir():
        return (
            _apply_result("usage", [
                {"code": "repo-not-found", "level": "error",
                 "message": f"repo not found: {repo}"}
            ]),
            2,
        )
    try:
        plan = load_plan_file(Path(plan_path))
        _check_operation(plan)
        _check_fingerprint(plan, expected_fingerprint)
        _check_expiry(plan)
        _check_state_against_plan(repo, plan)
        contents = _render_for_plan(plan)
        applied = _apply_actions(repo, plan, contents)
    except PlanRejected as exc:
        outcome = exc.outcome
        exit_code = {
            "drift": APPLY_DRIFT,
            "fingerprint-rejected": APPLY_DRIFT,
        }.get(outcome.get("result", ""), APPLY_FAIL)
        if outcome.get("result") in ("invalid-plan",):
            exit_code = 2
        return outcome, exit_code
    outcome = _apply_result("applied", [], plan_fingerprint_value=plan["plan_fingerprint"], applied=applied)
    return outcome, APPLY_PASS


_KNOWN_PROFILES: tuple[str, ...] = (
    "minimal",
    "standard",
    "high-assurance",
    "regulated",
)


def _render_for_plan(plan: dict[str, Any]) -> dict[str, str]:
    """Re-derive the exact template the plan committed to.

    The plan carries ``content_sha256`` per action; init-apply refuses to be
    an arbitrary file writer, so the rendered template must reproduce those
    digests. The profile is not stored in the plan directly: try every known
    profile and require exactly one to match the ``.praxis.toml`` digest.
    Ambiguity is impossible (each profile string differs inside the config),
    and no match means the plan is non-canonical and rejected.
    """
    project_id = plan["project"]["project_id"]
    config_digest = next(
        (
            a["content_sha256"]
            for a in plan["actions"]
            if a["path"] == ".praxis.toml"
        ),
        None,
    )
    if config_digest is None:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-missing-config-action",
                    "level": "error",
                    "message": "plan has no action for .praxis.toml",
                }
            ])
        )
    matches = [
        profile
        for profile in _KNOWN_PROFILES
        if sha256_digest(render_config(project_id, profile)) == config_digest
    ]
    if not matches:
        raise PlanInvalid(
            _apply_result("invalid-plan", [
                {
                    "code": "plan-content-noncanonical",
                    "level": "error",
                    "message": (
                        "plan .praxis.toml digest matches no canonical "
                        "rendering for any known profile; refusing arbitrary content"
                    ),
                }
            ])
        )
    return template_contents(project_id, matches[0])


__all__ = [
    "APPLY_DRIFT",
    "APPLY_FAIL",
    "APPLY_PASS",
    "INIT_PLAN_RESULT_SCHEMA_ID",
    "MUTATION_PLAN_SCHEMA_ID",
    "OPERATION",
    "REQUIRED_AUTHORITY",
    "STANDARD_VERSION",
    "TARGET_FILES",
    "PlanDrift",
    "PlanInvalid",
    "PlanRejected",
    "TargetStateError",
    "apply_init_plan",
    "build_init_plan",
    "classify_state",
    "git_remote",
    "jcs",
    "load_plan_file",
    "observe_targets",
    "observed_fingerprint",
    "plan_fingerprint",
    "render_config",
    "sha256_digest",
    "template_contents",
]
