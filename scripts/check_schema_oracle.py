#!/usr/bin/env python3.12
"""CI differential oracle gate for Praxis schema validation (ADR-0002).

PURPOSE
-------
This script runs ONLY in CI. It cross-checks Praxis's closed, stdlib-only
runtime validator (``praxis_dev.schema_validation``) against the third-party
``jsonschema`` reference implementation, over the packaged Praxis schemas and a
set of curated probes. It exists to catch *unintended* divergences from the
Draft 2020-12 specification.

WHY ``jsonschema`` IS A DIFFERENTIAL REFERENCE, NOT A CANONICAL AUTHORITY
------------------------------------------------------------------------
Praxis defines its own validation contract (closed subset, fail-closed,
stdlib-only, UTC-only date-time, etc.). ``jsonschema`` is a widely audited
Draft 2020-12 implementation, so it is an excellent *oracle* to surface bugs
in the Praxis runtime. It does NOT define Praxis correctness: where Praxis
intentionally deviates from the generic spec (notably the UTC-only date-time
policy), Praxis wins and the divergence is declared explicitly in this file as
a known policy divergence. Every other discrepancy is a gate failure.

Because ``jsonschema`` is a reference and not authority, it is deliberately
kept out of the runtime path and the zipapp. The script self-checks that the
runtime source does not import it (contract item 1), and the workflow installs
it solely from ``requirements/ci-oracle.txt`` with ``--require-hashes``.

The ``jsonschema`` import is deferred (see :func:`_ensure_jsonschema`) so the
pure classification helpers (notably :func:`classify_divergence`) can be
imported and unit-tested in a stdlib-only environment without the oracle
dependency.

EXIT CODE
---------
0 when (a) schemas/fixtures exactly cover the manifest-declared set, (b) every
schema meta-validates, (c) runtime and reference agree on every fixture case
except the ONE declared Praxis policy divergence, and (d) every synthetic probe
matches its declared expectation for BOTH implementations. Non-zero otherwise.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "schema_validation"
MANIFEST = ROOT / "standards" / "praxis" / "v1" / "manifest.json"
RUNTIME_SOURCE = ROOT / "praxis_dev" / "schema_validation.py"

sys.path.insert(0, str(ROOT))
from praxis_dev import schema_validation as sv  # noqa: E402

# Deferred, CI-only. Populated by _ensure_jsonschema() so this module stays
# importable without jsonschema (the pure helpers below are unit-tested in a
# stdlib-only env). A None value at use time means main() was not entered,
# which only happens under CI misconfiguration.
Draft202012Validator: Any = None
FormatChecker: Any = None
SchemaError: Any = None


def _ensure_jsonschema() -> None:
    """Import jsonschema lazily; fail loudly if missing (CI-only script)."""
    global Draft202012Validator, FormatChecker, SchemaError
    if Draft202012Validator is not None:
        return
    try:
        from jsonschema import Draft202012Validator as _Validator
        from jsonschema import FormatChecker as _FormatChecker
        from jsonschema.exceptions import SchemaError as _SchemaError
    except ImportError as exc:  # pragma: no cover - CI misconfiguration
        sys.exit(f"FATAL: jsonschema not installed; this script is CI-only: {exc}")
    Draft202012Validator = _Validator
    FormatChecker = _FormatChecker
    SchemaError = _SchemaError


# --------------------------------------------------------------------------- #
# Exact UTC-policy allowlist (FIXTURE cases only).
#
# The ONLY fixture case where Praxis is expected to be stricter than the
# reference is the UTC date-time policy. It is pinned by (a) the exact fixture
# label, (b) the exact JSON field on the instance, and (c) the exact non-UTC
# value at that field. classify_divergence accepts the divergence ONLY when the
# instance is a dict and ``instance[case.field] == case.timestamp`` byte for
# byte. A valid ``Z`` value at the pinned field, the allowed non-UTC value
# planted under any other field, a non-dict instance, any other label, or any
# non-date-time diagnostic code is an UNEXPECTED divergence and fails the gate.
# The synthetic probes carry their own declared divergences separately.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _PolicyCase:
    field: str
    timestamp: str


KNOWN_UTC_POLICY_FIXTURES: dict[str, _PolicyCase] = {
    "audit-result.cases.json/datetime-non-utc": _PolicyCase(
        field="observed_at", timestamp="2026-08-11T11:02:19+02:00",
    ),
}


# --------------------------------------------------------------------------- #
# Synthetic probe schemas.
# --------------------------------------------------------------------------- #
SIBLINGS_SCHEMA: dict[str, Any] = {
    "$defs": {
        "base": {"type": "string"},
        "constrained": {"$ref": "#/$defs/base", "minLength": 3},
    },
    "$ref": "#/$defs/constrained",
}
DATE_TIME_SCHEMA: dict[str, Any] = {"type": "string", "format": "date-time"}


@dataclass(frozen=True)
class Probe:
    """A synthetic case with the validity each implementation MUST produce.

    For agreement probes ``expect_runtime == expect_reference``. For declared
    Praxis policy divergences they differ (e.g. UTC-only date-time), which
    documents the policy instead of letting it pass silently.
    """

    label: str
    schema: dict[str, Any]
    instance: Any
    expect_runtime: bool
    expect_reference: bool


PROBES: tuple[Probe, ...] = (
    Probe("integer-1.0-accepts", {"type": "integer"}, 1.0, True, True),
    Probe("integer-1.5-rejects", {"type": "integer"}, 1.5, False, False),
    Probe("integer-bool-rejects", {"type": "integer"}, True, False, False),
    Probe("uniqueitems-1-true-distinct", {"uniqueItems": True}, [1, True], True, True),
    Probe("uniqueitems-1-1.0-equal", {"uniqueItems": True}, [1, 1.0], False, False),
    Probe("contains-match",
          {"type": "array", "contains": {"type": "string"}}, [1, "x"], True, True),
    Probe("contains-zero",
          {"type": "array", "contains": {"type": "string"}}, [1, 2], False, False),
    Probe("oneof-exactly-one",
          {"oneOf": [{"type": "string"}, {"type": "null"}]}, "s", True, True),
    Probe("oneof-zero",
          {"oneOf": [{"type": "string"}, {"type": "null"}]}, 5, False, False),
    Probe("ref-siblings-chain-valid", SIBLINGS_SCHEMA, "abcd", True, True),
    Probe("ref-siblings-chain-invalid", SIBLINGS_SCHEMA, "x", False, False),
    # Declared Praxis UTC-policy divergences: reference accepts these valid
    # RFC 3339 values; Praxis rejects non-UTC offsets by policy.
    Probe("datetime-Z-agree-valid", DATE_TIME_SCHEMA,
          "2026-08-11T11:02:19Z", True, True),
    Probe("datetime-plus-offset-policy-divergence", DATE_TIME_SCHEMA,
          "2026-08-11T11:02:19+02:00", False, True),
    Probe("datetime-minus-zero-policy-divergence", DATE_TIME_SCHEMA,
          "2026-08-11T11:02:19-00:00", False, True),
    Probe("datetime-garbage-agree-invalid", DATE_TIME_SCHEMA,
          "not-a-date", False, False),
)


# --------------------------------------------------------------------------- #
# Pure helpers (no jsonschema dependency; unit-tested in stdlib env).
# --------------------------------------------------------------------------- #
def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _instance_string_values(instance: Any) -> set[str]:
    """All string values reachable in ``instance``.

    Retained as a sanity utility for tests; the policy decision itself uses
    field-exact matching (see :func:`classify_divergence`) so a planted value
    under a foreign field cannot be accepted.
    """
    found: set[str] = set()
    stack: list[Any] = [instance]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, dict):
            stack.extend(value.values())
    return found


def classify_divergence(
    label: str,
    instance: Any,
    runtime_ok: bool,
    reference_ok: bool,
    codes: Iterable[str],
) -> tuple[str, str]:
    """Classify a runtime/reference disagreement for a fixture case.

    Returns ``(severity, detail)``. The ONLY accepted policy divergence is a
    declared UTC date-time case: runtime invalid, reference valid, no
    non-date-time diagnostic codes, the label is allowlisted, the instance is a
    dict, and ``instance[case.field] == case.timestamp`` byte for byte. Every
    other disagreement is an ERROR -- notably a valid ``Z`` value at the pinned
    field, the allowed non-UTC value planted under any other field, or a
    non-dict instance, must NOT be classified as policy.
    """
    code_list = list(codes)
    non_policy = [c for c in code_list if c != sv.CODE_FORMAT_DATE_TIME]
    case = KNOWN_UTC_POLICY_FIXTURES.get(label)
    field_value = (
        instance.get(case.field)
        if case is not None and isinstance(instance, dict)
        else None
    )
    is_policy = (
        runtime_ok is False
        and reference_ok is True
        and not non_policy
        and case is not None
        and isinstance(instance, dict)
        and field_value == case.timestamp
    )
    if is_policy:
        return (
            "POLICY",
            f"{label}: Praxis UTC date-time policy at "
            f"{case.field}={case.timestamp!r} (runtime invalid, reference valid)",
        )
    return (
        "ERROR",
        f"{label}: UNEXPECTED divergence runtime={runtime_ok} "
        f"reference={reference_ok}; codes={sorted(code_list)}",
    )


def _assert_runtime_is_stdlib_only(errors: list[str]) -> None:
    """Contract item 1: the runtime must not import the oracle dependency."""
    text = RUNTIME_SOURCE.read_text(encoding="utf-8")
    for token in ("import jsonschema", "from jsonschema"):
        if token in text:
            errors.append(
                f"runtime {RUNTIME_SOURCE.name} imports oracle dependency ({token!r}); "
                "jsonschema must remain CI-only"
            )


def _assert_allowlist_is_non_utc(errors: list[str]) -> None:
    """Defense-in-depth: a declared UTC-policy case must target a non-UTC value
    at a named field. A ``Z`` or ``+00:00`` value here would whitelist a
    timestamp the runtime is supposed to ACCEPT, masking a real bug."""
    for label, case in KNOWN_UTC_POLICY_FIXTURES.items():
        if not isinstance(case.field, str) or not case.field:
            errors.append(f"allowlist {label!r} has an empty/non-string field")
        if case.timestamp.endswith("Z") or case.timestamp.endswith("+00:00"):
            errors.append(
                f"allowlist {label!r} pins UTC timestamp {case.timestamp!r}; "
                f"UTC-policy divergence must target a non-UTC offset"
            )


# --------------------------------------------------------------------------- #
# Loading & manifest-driven coverage (contract item 4).
# --------------------------------------------------------------------------- #
def _load_schemas(errors: list[str]) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        try:
            schema = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot load schema {path.name}: {exc}")
            continue
        schemas[path.name] = schema
    return schemas


def _load_fixtures(errors: list[str]) -> list[tuple[Path, dict[str, Any]]]:
    fixtures: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(FIXTURES.glob("*.cases.json")):
        try:
            blob = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot load fixture {path.name}: {exc}")
            continue
        fixtures.append((path, blob))
    return fixtures


def _declared_schema_files(errors: list[str]) -> list[str]:
    """Derive the schema filenames the manifest declares (the source of truth
    for the expected set of 7 schemas)."""
    try:
        manifest = _load_json(MANIFEST)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot load manifest {MANIFEST.relative_to(ROOT)}: {exc}")
        return []
    declared: list[str] = []
    table = manifest.get("schemas", {})
    if not isinstance(table, dict) or not table:
        errors.append("manifest declares no schemas")
        return []
    for logical, raw_path in table.items():
        if not isinstance(raw_path, str):
            errors.append(f"manifest schema {logical!r} path is not a string")
            continue
        declared.append(Path(raw_path).name)
    return declared


def _check_coverage(
    declared: list[str],
    loaded_schemas: dict[str, dict[str, Any]],
    fixtures: list[tuple[Path, dict[str, Any]]],
    errors: list[str],
) -> None:
    """Fail explicitly if schemas/fixtures do not cover the manifest-declared set."""
    declared_set = set(declared)
    loaded_set = set(loaded_schemas)
    missing = sorted(declared_set - loaded_set)
    extra = sorted(loaded_set - declared_set)
    if missing:
        errors.append(f"manifest schemas missing on disk: {missing}")
    if extra:
        errors.append(f"schemas on disk not declared in manifest: {extra}")
    fixture_targets = {
        blob.get("schema_file")
        for _, blob in fixtures
        if isinstance(blob.get("schema_file"), str)
    }
    for name in sorted(declared_set):
        if name not in fixture_targets:
            errors.append(f"no fixture file references declared schema {name}")
    undeclared_fixtures = sorted(fixture_targets - declared_set)
    if undeclared_fixtures:
        errors.append(f"fixtures reference undeclared schemas: {undeclared_fixtures}")


# --------------------------------------------------------------------------- #
# jsonschema-dependent checks (run only after _ensure_jsonschema()).
# --------------------------------------------------------------------------- #
def _reference_valid(instance: Any, schema: dict[str, Any], checker: Any) -> bool:
    return Draft202012Validator(schema, format_checker=checker).is_valid(instance)


def _meta_validate(schemas: dict[str, dict[str, Any]], errors: list[str]) -> None:
    """Contract item 3: Draft202012Validator.check_schema on every schema."""
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            errors.append(f"meta-schema validation failed for {name}: {exc.message}")


def _fixture_differential(
    schemas: dict[str, dict[str, Any]],
    fixtures: list[tuple[Path, dict[str, Any]]],
    checker: Any,
    errors: list[str],
    policy: list[str],
) -> None:
    """Compare runtime vs reference validity on every fixture case.

    A divergence is accepted ONLY via :func:`classify_divergence`, i.e. the one
    declared UTC policy case. Anything else is a gate failure.
    """
    for path, blob in fixtures:
        schema_name = blob.get("schema_file")
        schema = schemas.get(schema_name) if isinstance(schema_name, str) else None
        if schema is None:
            errors.append(f"{path.name}: references unknown schema {schema_name!r}")
            continue
        ref_validator = Draft202012Validator(schema, format_checker=checker)
        for case in blob.get("cases", []):
            instance = case.get("instance")
            label = f"{path.name}/{case.get('name', '?')}"
            runtime_ok = sv.is_valid(instance, schema)
            reference_ok = ref_validator.is_valid(instance)
            if runtime_ok == reference_ok:
                continue
            codes = {d.code for d in sv.validate(instance, schema)}
            severity, detail = classify_divergence(
                label, instance, runtime_ok, reference_ok, codes
            )
            (policy if severity == "POLICY" else errors).append(detail)


def _synthetic_probes(checker: Any, errors: list[str], policy: list[str]) -> None:
    """Assert each probe's declared outcome for BOTH implementations."""
    for probe in PROBES:
        runtime_ok = sv.is_valid(probe.instance, probe.schema)
        reference_ok = _reference_valid(probe.instance, probe.schema, checker)
        ok = runtime_ok == probe.expect_runtime and reference_ok == probe.expect_reference
        if not ok:
            errors.append(
                f"probe {probe.label!r}: runtime={runtime_ok} reference={reference_ok} "
                f"(expected runtime={probe.expect_runtime} reference={probe.expect_reference})"
            )
            continue
        if not probe.expect_runtime and probe.expect_reference:
            policy.append(
                f"probe {probe.label!r}: declared Praxis UTC-policy divergence "
                f"(runtime invalid, reference valid)"
            )


def main() -> int:
    errors: list[str] = []
    policy: list[str] = []

    _assert_runtime_is_stdlib_only(errors)
    _assert_allowlist_is_non_utc(errors)
    schemas = _load_schemas(errors)
    declared = _declared_schema_files(errors)
    fixtures = _load_fixtures(errors)
    _check_coverage(declared, schemas, fixtures, errors)

    _ensure_jsonschema()
    checker = FormatChecker()
    _meta_validate(schemas, errors)
    _fixture_differential(schemas, fixtures, checker, errors, policy)
    _synthetic_probes(checker, errors, policy)

    print("Praxis schema differential oracle (CI-only; not a conformance claim)")
    for item in policy:
        print(f"  [POLICY] {item}")
    if errors:
        print(f"FAIL ({len(errors)} unexpected divergence/error)")
        for item in errors:
            print(f"  [ERROR] {item}")
        return 1
    declared_count = len(set(declared)) or len(schemas)
    print(
        f"PASS: {len(policy)} declared Praxis policy divergence(s); "
        f"no unexpected divergences across {declared_count} manifest-declared schemas"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
