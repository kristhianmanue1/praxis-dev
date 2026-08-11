"""Closed JSON Schema validation for Praxis (ADR-0002, proposed).

Architecture contract fixed by the controller:

* Runtime is stdlib-only. ``jsonschema`` is a CI differential oracle, NEVER a
  runtime dependency.
* The validator consumes ONLY schemas that are packaged and preverified in CI
  via :func:`inspect_schema`. It is NOT a general Draft 2020-12 validator.
* Fail-closed: unsupported keywords/formats, non-local ``$ref``, malformed
  keyword values and uncompilable patterns produce diagnostics instead of being
  silently ignored or raising. ``validate`` is fail-closed even when called
  without :func:`inspect_schema`.
* Input JSON (:func:`loads_strict`) rejects duplicate keys and non-finite
  constants (NaN, Infinity, -Infinity). :func:`validate` also rejects non-finite
  float values reached in the instance.
* ``format: date-time`` requires an RFC 3339 calendrical value proven to be UTC:
  only ``Z`` and ``+00:00`` are accepted; ``-00:00`` (unknown offset), non-UTC
  offsets, naive values and calendar-impossible dates are rejected.
* ``type: integer`` follows Draft 2020-12 semantics: ``1.0`` is accepted, booleans
  and ``1.5`` are rejected.

Implemented subset (inventoried across the Praxis schemas): ``type``, ``const``,
``enum``, ``required``, ``properties``, ``additionalProperties`` (bool/subschema),
``pattern``, ``minLength``/``maxLength``, ``minProperties``, ``minItems``/
``maxItems``, ``uniqueItems``, ``items`` (schema/boolean only, never a list),
``contains``, ``oneOf``, ``allOf``, ``if``/``then``/``else``, local ``$ref``
(``#/`` JSON pointer fragments, with ``~0``/``~1`` token decoding; malformed
escapes and non-local fragments are rejected), ``format: date-time`` and
declared annotations. Per Draft 2020-12, ``$ref`` does not exclude its sibling
keywords: at runtime each hop is resolved one step at a time so siblings of
every intermediate node apply, with a stack that terminates ref cycles.

:func:`inspect_schema` verifies the shape of every implemented keyword, resolves
all local ``$ref`` fragments (rejecting absent targets, non-subschema targets,
external/escape fragments and cycles), and compiles every ``pattern``. An empty
result is the contract that a schema is safe to consume at runtime.

Diagnostic codes are stable strings exposed as module-level ``CODE_*`` constants.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
SUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset({
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "pattern", "minLength", "maxLength", "minProperties", "minItems", "maxItems",
    "uniqueItems", "items", "contains", "oneOf", "allOf", "if", "then", "else",
    "$ref", "format",
})
ANNOTATION_KEYWORDS: Final[frozenset[str]] = frozenset({
    "$schema", "$id", "title", "description", "$defs", "default", "examples",
})
SUPPORTED_FORMATS: Final[frozenset[str]] = frozenset({"date-time"})

_TYPE_NAMES: Final[frozenset[str]] = frozenset({
    "null", "boolean", "object", "array", "number", "string", "integer",
})
_INT_LIMIT_KEYS: Final[frozenset[str]] = frozenset({
    "minLength", "maxLength", "minProperties", "maxProperties", "minItems", "maxItems",
})
# Supported keywords whose value is a single subschema (object or boolean).
_SINGLE_SUBSCHEMA_KEYS: Final[frozenset[str]] = frozenset({
    "additionalProperties", "contains", "if", "then", "else", "items",
})
# Supported keywords whose value is an array of subschemas.
_ARRAY_SUBSCHEMA_KEYS: Final[frozenset[str]] = frozenset({"oneOf", "allOf"})

# Recognized container shapes for traversal (vocabulary/position-aware). Some are
# NOT in the supported subset; they are still traversed so hidden unsupported
# keywords surface, but they remain flagged as unsupported.
_NAMED_MAP_CONTAINERS: Final[frozenset[str]] = frozenset({
    "properties", "patternProperties", "dependentSchemas", "$defs", "definitions",
})
_ARRAY_CONTAINERS: Final[frozenset[str]] = frozenset({
    "allOf", "anyOf", "oneOf", "prefixItems",
})
_SINGLE_CONTAINERS: Final[frozenset[str]] = frozenset({
    "additionalProperties", "contains", "propertyNames", "if", "then", "else",
    "not", "items", "unevaluatedItems", "unevaluatedProperties",
})

# Stable diagnostic codes.
CODE_TYPE = "type"
CODE_CONST = "const"
CODE_ENUM = "enum"
CODE_REQUIRED = "required"
CODE_PATTERN = "pattern"
CODE_MIN_LENGTH = "min-length"
CODE_MAX_LENGTH = "max-length"
CODE_MIN_PROPERTIES = "min-properties"
CODE_MIN_ITEMS = "min-items"
CODE_MAX_ITEMS = "max-items"
CODE_UNIQUE_ITEMS = "unique-items"
CODE_CONTAINS = "contains"
CODE_ONE_OF = "one-of"
CODE_ADDITIONAL_PROPERTIES = "additional-properties"
CODE_FORMAT_DATE_TIME = "format-date-time"
CODE_UNSUPPORTED_KEYWORD = "unsupported-keyword"
CODE_UNSUPPORTED_FORMAT = "unsupported-format"
CODE_SCHEMA_SHAPE = "schema-shape"
CODE_PATTERN_MALFORMED = "pattern-malformed"
CODE_EXTERNAL_REF = "external-ref"
CODE_UNSAFE_REF = "unsafe-ref"
CODE_REF_POINTER_MALFORMED = "ref-pointer-malformed"
CODE_REF_UNRESOLVABLE = "ref-unresolvable"
CODE_REF_TARGET = "ref-target"
CODE_REF_CYCLE = "ref-cycle"
CODE_SCHEMA_FALSE = "schema-false"
CODE_SCHEMA_NODE = "schema-node"
CODE_DUPLICATE_KEY = "duplicate-key"
CODE_NON_FINITE = "non-finite"

# date-time: RFC 3339 skeleton (Z or numeric offset); calendar validity is
# delegated to datetime.fromisoformat. UTC policy accepts only Z and +00:00.
_RFC3339_SKELETON = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


@dataclass(frozen=True)
class Diagnostic:
    """A single validation finding with a stable code and JSON-pointer-like path."""

    code: str
    path: str
    message: str


class StrictJSONError(ValueError):
    """Raised by :func:`loads_strict` on duplicate keys or non-finite constants."""


# --------------------------------------------------------------------------- #
# Strict JSON parsing
# --------------------------------------------------------------------------- #
def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"{CODE_DUPLICATE_KEY}: {key!r}")
        result[key] = value
    return result


def _reject_non_finite(literal: str) -> float:
    raise StrictJSONError(f"{CODE_NON_FINITE}: {literal}")


def loads_strict(text: str) -> Any:
    """Parse JSON rejecting duplicate object keys and non-finite numeric constants.

    Duplicate keys violate the Praxis single-home contract
    (``docs/contrato-cli.md``). ``NaN``, ``Infinity`` and ``-Infinity`` are not
    valid JSON; Python's ``json`` accepts them by default, so they are rejected
    here via ``parse_constant``.
    """
    if not isinstance(text, str):
        raise StrictJSONError("input must be a string")
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_finite,
    )
    _reject_non_finite_in(value)
    return value


def _reject_non_finite_in(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise StrictJSONError(f"{CODE_NON_FINITE}: {value!r}")
    if isinstance(value, list):
        for item in value:
            _reject_non_finite_in(item)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_non_finite_in(item)


# --------------------------------------------------------------------------- #
# Shape helpers (single source of truth shared by inspect and validate)
# --------------------------------------------------------------------------- #
def _is_schema(value: Any) -> bool:
    return isinstance(value, (dict, bool))


def _is_schema_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_schema(item) for item in value)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_uint(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_type_spec(value: Any) -> bool:
    if isinstance(value, str):
        return value in _TYPE_NAMES
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item in _TYPE_NAMES for item in value
    )


def _compiles(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


# A JSON Pointer token escape is valid only as ``~0`` (``~``) or ``~1`` (``/``).
# Any other tilde sequence, or a trailing bare ``~``, is a syntactic error that
# must be reported distinctly from an unresolvable reference.
_POINTER_INVALID_ESCAPE = re.compile(r"~(?:[^01]|$)")


def _pointer_parts(ref: Any) -> tuple[list[str] | None, list[Diagnostic]]:
    """Parse a local ``#/`` JSON Pointer into raw (still-encoded) tokens.

    Returns ``(parts, diags)`` where ``parts`` is ``None`` when ``diags`` is
    non-empty. Validates that ``ref`` is a local ``#/`` pointer, has no ``..``
    path-traversal segment, and that every token uses only ``~0``/``~1``
    escapes. Escape validation is a syntactic check distinct from resolution.
    """
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None, [Diagnostic(CODE_EXTERNAL_REF, "$", f"only local #/ refs supported: {ref!r}")]
    parts = ref[len("#/"):].split("/")
    if ".." in parts:
        return None, [Diagnostic(CODE_UNSAFE_REF, "$", f"unsafe ref escape: {ref!r}")]
    for raw in parts:
        if _POINTER_INVALID_ESCAPE.search(raw) is not None:
            return None, [Diagnostic(
                CODE_REF_POINTER_MALFORMED, "$",
                f"malformed JSON Pointer escape in {ref!r} (only ~0 and ~1 allowed)",
            )]
    return parts, []


def _resolve_single_ref(ref: Any, root: dict[str, Any]) -> tuple[Any, list[Diagnostic]]:
    """Resolve ONE ``#/`` ref hop WITHOUT following nested ``$ref``.

    Returns the node located at the pointer (dict/boolean subschema) and a
    diagnostic list. The caller is responsible for further ``$ref`` hops so
    that siblings of every intermediate node are applied per Draft 2020-12.
    """
    parts, diags = _pointer_parts(ref)
    if diags:
        return None, diags
    node: Any = root
    for raw in parts:
        token = _decode_pointer_token(raw)
        if not isinstance(node, dict) or token not in node:
            return None, [Diagnostic(CODE_REF_UNRESOLVABLE, "$", f"unresolvable ref {ref!r}")]
        node = node[token]
    if not isinstance(node, (dict, bool)):
        return None, [Diagnostic(CODE_REF_TARGET, "$", f"ref target is not a subschema: {ref!r}")]
    return node, []


def _resolve_ref_chain(ref: Any, root: dict[str, Any]) -> tuple[Any, list[Diagnostic]]:
    """Resolve a local ``#/`` ref, following nested refs and detecting cycles.

    Used for static inspection: collapses the full ``$ref`` chain to verify
    the terminal target is a usable subschema. Empty diagnostics means the
    terminal target is consumable. Runtime validation uses
    :func:`_resolve_single_ref` one hop at a time so siblings of every
    intermediate node are applied instead of collapsed away.
    """
    seen: set[str] = set()
    current = ref
    while True:
        if current in seen:
            return None, [Diagnostic(CODE_REF_CYCLE, "$", f"ref cycle detected at {current!r}")]
        seen.add(current)
        node, diags = _resolve_single_ref(current, root)
        if diags:
            return None, diags
        if isinstance(node, dict) and "$ref" in node:
            current = node["$ref"]
            continue
        return node, []


def _shape_errors(node: dict[str, Any], path: str) -> list[Diagnostic]:
    """Per-keyword value-shape diagnostics for a single schema node (no traversal)."""
    errors: list[Diagnostic] = []
    for key, val in node.items():
        kpath = f"{path}.{key}"
        if key not in SUPPORTED_KEYWORDS and key not in ANNOTATION_KEYWORDS:
            errors.append(Diagnostic(CODE_UNSUPPORTED_KEYWORD, kpath, f"unsupported keyword {key!r}"))
            continue
        if key == "format":
            if val not in SUPPORTED_FORMATS:
                errors.append(Diagnostic(CODE_UNSUPPORTED_FORMAT, kpath, f"unsupported format {val!r}"))
        elif key == "type":
            if not _is_type_spec(val):
                errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, "malformed 'type' value"))
        elif key == "enum" and not isinstance(val, list):
            errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, "'enum' must be an array"))
        elif key == "required" and not _is_str_list(val):
            errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, "'required' must be an array of strings"))
        elif key in _INT_LIMIT_KEYS and not _is_uint(val):
            errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, f"{key!r} must be a non-negative integer"))
        elif key == "uniqueItems" and not isinstance(val, bool):
            errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, "'uniqueItems' must be a boolean"))
        elif key == "pattern":
            if not isinstance(val, str):
                errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, "'pattern' must be a string"))
            elif not _compiles(val):
                errors.append(Diagnostic(CODE_PATTERN_MALFORMED, kpath, f"uncompilable pattern {val!r}"))
        elif key in _SINGLE_SUBSCHEMA_KEYS and not _is_schema(val):
            errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, f"{key!r} must be a schema (object or boolean)"))
        elif key in _ARRAY_SUBSCHEMA_KEYS and not _is_schema_list(val):
            errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, f"{key!r} must be an array of schemas"))
        elif key in _NAMED_MAP_CONTAINERS:
            if not isinstance(val, dict):
                errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, f"{key!r} must be an object"))
            elif not all(_is_schema(item) for item in val.values()):
                errors.append(Diagnostic(CODE_SCHEMA_SHAPE, kpath, f"{key!r} values must be schemas"))
    return errors


# --------------------------------------------------------------------------- #
# Schema preverification
# --------------------------------------------------------------------------- #
def inspect_schema(schema: Any) -> list[Diagnostic]:
    """Statically inspect a schema for closed-subset consumability.

    Returns a deterministic list of diagnostics. An empty list means the schema
    is safe to consume at runtime: root is an object, every keyword belongs to
    the supported subset or declared annotations with a correct value shape,
    every ``pattern`` compiles, every ``format`` is supported and every local
    ``$ref`` resolves (with JSON Pointer ``~0``/``~1`` decoding) to a subschema
    without cycles.
    """
    errors: list[Diagnostic] = []
    if isinstance(schema, bool):
        return [Diagnostic(CODE_SCHEMA_NODE, "$", "root schema must be an object, not boolean")]
    if not isinstance(schema, dict):
        return [Diagnostic(CODE_SCHEMA_NODE, "$", "root schema must be an object")]
    _inspect_node(schema, "$", schema, errors)
    return errors


def _inspect_node(node: Any, path: str, root: dict[str, Any], errors: list[Diagnostic]) -> None:
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        errors.append(Diagnostic(CODE_SCHEMA_NODE, path, "subschema must be object or boolean"))
        return
    errors.extend(_shape_errors(node, path))
    if "$ref" in node:
        _, ref_diags = _resolve_ref_chain(node["$ref"], root)
        errors.extend(ref_diags)
    for key, val in node.items():
        kpath = f"{path}.{key}"
        if key in _NAMED_MAP_CONTAINERS and isinstance(val, dict):
            for name, sub in val.items():
                _inspect_node(sub, f"{kpath}[{name}]", root, errors)
        elif key in _ARRAY_CONTAINERS and isinstance(val, list):
            for i, sub in enumerate(val):
                _inspect_node(sub, f"{kpath}[{i}]", root, errors)
        elif key in _SINGLE_CONTAINERS and isinstance(val, dict):
            _inspect_node(val, kpath, root, errors)


# --------------------------------------------------------------------------- #
# Instance validation
# --------------------------------------------------------------------------- #
def validate(instance: Any, schema: Any) -> list[Diagnostic]:
    """Validate ``instance`` against ``schema`` and return a deterministic list.

    The schema is assumed to have passed :func:`inspect_schema`; even so, this
    function is fail-closed on its own: malformed keyword values, unsupported
    keywords/formats, uncompilable patterns and bad refs produce diagnostics
    rather than being ignored or raising. Non-finite float values reached in the
    instance are rejected with ``CODE_NON_FINITE``.
    """
    root = schema if isinstance(schema, dict) else None
    return _validate(instance, schema, root, "$")


def is_valid(instance: Any, schema: Any) -> bool:
    """Convenience wrapper returning ``True`` when no diagnostics are produced."""
    return not validate(instance, schema)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_ok(instance: Any, spec: Any) -> bool:
    specs = spec if isinstance(spec, list) else [spec]
    for kind in specs:
        if kind == "object" and isinstance(instance, dict):
            return True
        if kind == "array" and isinstance(instance, list):
            return True
        if kind == "string" and isinstance(instance, str):
            return True
        if kind == "boolean" and isinstance(instance, bool):
            return True
        if kind == "null" and instance is None:
            return True
        if kind == "integer":
            if isinstance(instance, int) and not isinstance(instance, bool):
                return True
            if isinstance(instance, float) and instance.is_integer():
                return True
        if kind == "number" and _is_number(instance):
            return True
    return False


def _json_equal(a: Any, b: Any) -> bool:
    """Draft 2020-12 value equality: ``1 == 1.0``; object key order irrelevant."""
    a_num = _is_number(a)
    b_num = _is_number(b)
    if a_num or b_num:
        return a_num and b_num and a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return False


def _is_utc_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or not _RFC3339_SKELETON.match(value):
        return False
    # UTC policy: only the Z designator and the +00:00 offset assert UTC.
    # -00:00 is rejected (RFC 3339 reserves it for an unknown local offset).
    if not (value.endswith("Z") or value.endswith("+00:00")):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _validate(
    instance: Any,
    schema: Any,
    root: dict[str, Any] | None,
    path: str,
    ref_stack: frozenset[str] = frozenset(),
) -> list[Diagnostic]:
    if isinstance(instance, float) and not math.isfinite(instance):
        return [Diagnostic(CODE_NON_FINITE, path, "non-finite instance value")]
    errors: list[Diagnostic] = []
    if isinstance(schema, bool):
        if not schema:
            errors.append(Diagnostic(CODE_SCHEMA_FALSE, path, "boolean schema 'false' rejects all instances"))
        return errors
    if not isinstance(schema, dict):
        errors.append(Diagnostic(CODE_SCHEMA_NODE, path, "subschema must be object or boolean"))
        return errors

    # Fail-closed per-node shape audit (also makes validate robust standalone).
    errors.extend(_shape_errors(schema, path))

    # Draft 2020-12: $ref is NOT exclusive with its siblings. Resolve ONE hop
    # (do not collapse the chain), validate the target recursively while
    # carrying a stack of in-flight refs so cycles terminate, then fall through
    # to apply this node's siblings. Sibling/child validations start a fresh
    # stack because they are separate dynamic scopes.
    if "$ref" in schema:
        ref = schema["$ref"]
        ref_root = root if root is not None else schema
        target, ref_diags = _resolve_single_ref(ref, ref_root)
        errors.extend(ref_diags)
        if target is not None and not ref_diags:
            if ref in ref_stack:
                errors.append(Diagnostic(CODE_REF_CYCLE, path, f"ref cycle at {ref!r}"))
            else:
                errors.extend(_validate(instance, target, ref_root, path, ref_stack | {ref}))

    if "type" in schema and _is_type_spec(schema["type"]) and not _type_ok(instance, schema["type"]):
        errors.append(Diagnostic(CODE_TYPE, path, f"expected type {schema['type']!r}, got {type(instance).__name__}"))
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(Diagnostic(CODE_CONST, path, f"const mismatch (expected {schema['const']!r})"))
    if "enum" in schema and isinstance(schema["enum"], list) and not any(
        _json_equal(instance, candidate) for candidate in schema["enum"]
    ):
        errors.append(Diagnostic(CODE_ENUM, path, f"enum mismatch (got {instance!r})"))

    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and _compiles(pattern) and re.search(pattern, instance) is None:
            errors.append(Diagnostic(CODE_PATTERN, path, f"pattern mismatch /{pattern}/"))
        if "minLength" in schema and _is_uint(schema["minLength"]) and len(instance) < schema["minLength"]:
            errors.append(Diagnostic(CODE_MIN_LENGTH, path, f"minLength {schema['minLength']} unsatisfied"))
        if "maxLength" in schema and _is_uint(schema["maxLength"]) and len(instance) > schema["maxLength"]:
            errors.append(Diagnostic(CODE_MAX_LENGTH, path, f"maxLength {schema['maxLength']} exceeded"))
        if schema.get("format") == "date-time" and not _is_utc_rfc3339(instance):
            errors.append(Diagnostic(CODE_FORMAT_DATE_TIME, path, "format date-time (UTC RFC 3339) mismatch"))

    if isinstance(instance, list):
        if "minItems" in schema and _is_uint(schema["minItems"]) and len(instance) < schema["minItems"]:
            errors.append(Diagnostic(CODE_MIN_ITEMS, path, f"minItems {schema['minItems']} unsatisfied"))
        if "maxItems" in schema and _is_uint(schema["maxItems"]) and len(instance) > schema["maxItems"]:
            errors.append(Diagnostic(CODE_MAX_ITEMS, path, f"maxItems {schema['maxItems']} exceeded"))
        if schema.get("uniqueItems") is True:
            for i in range(len(instance)):
                for j in range(i + 1, len(instance)):
                    if _json_equal(instance[i], instance[j]):
                        errors.append(Diagnostic(CODE_UNIQUE_ITEMS, path, "uniqueItems violated"))
                        break
        items = schema.get("items")
        if _is_schema(items):
            for i, item in enumerate(instance):
                errors.extend(_validate(item, items, root, f"{path}[{i}]"))
        if "contains" in schema and _is_schema(schema["contains"]):
            hits = sum(1 for item in instance if not _validate(item, schema["contains"], root, path))
            if hits < 1:
                errors.append(Diagnostic(CODE_CONTAINS, path, "contains unsatisfied (0 matching items)"))

    if isinstance(instance, dict):
        props = schema.get("properties")
        props = props if isinstance(props, dict) else {}
        if _is_str_list(schema.get("required")):
            for key in schema["required"]:
                if key not in instance:
                    errors.append(Diagnostic(CODE_REQUIRED, path, f"missing required {key!r}"))
        if "minProperties" in schema and _is_uint(schema["minProperties"]) and len(instance) < schema["minProperties"]:
            errors.append(Diagnostic(CODE_MIN_PROPERTIES, path, f"minProperties {schema['minProperties']} unsatisfied"))
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in props and _is_schema(props[key]):
                errors.extend(_validate(value, props[key], root, f"{path}.{key}"))
            elif additional is False:
                errors.append(Diagnostic(CODE_ADDITIONAL_PROPERTIES, path, f"additional property {key!r} not allowed"))
            elif isinstance(additional, dict):
                errors.extend(_validate(value, additional, root, f"{path}.{key}"))

    one_of = schema.get("oneOf")
    if _is_schema_list(one_of):
        matches = sum(1 for sub in one_of if not _validate(instance, sub, root, path))
        if matches != 1:
            errors.append(Diagnostic(CODE_ONE_OF, path, f"oneOf matched {matches} subschemas (expected exactly 1)"))
    all_of = schema.get("allOf")
    if _is_schema_list(all_of):
        for sub in all_of:
            errors.extend(_validate(instance, sub, root, path))
    if isinstance(schema.get("if"), (dict, bool)):
        guard_ok = not _validate(instance, schema["if"], root, path)
        if guard_ok and _is_schema(schema.get("then")):
            errors.extend(_validate(instance, schema["then"], root, path))
        if not guard_ok and _is_schema(schema.get("else")):
            errors.extend(_validate(instance, schema["else"], root, path))

    return errors


__all__ = [
    "ANNOTATION_KEYWORDS",
    "SUPPORTED_FORMATS",
    "SUPPORTED_KEYWORDS",
    "CODE_ADDITIONAL_PROPERTIES",
    "CODE_CONST",
    "CODE_CONTAINS",
    "CODE_DUPLICATE_KEY",
    "CODE_ENUM",
    "CODE_EXTERNAL_REF",
    "CODE_FORMAT_DATE_TIME",
    "CODE_MAX_ITEMS",
    "CODE_MAX_LENGTH",
    "CODE_MIN_ITEMS",
    "CODE_MIN_LENGTH",
    "CODE_MIN_PROPERTIES",
    "CODE_NON_FINITE",
    "CODE_ONE_OF",
    "CODE_PATTERN",
    "CODE_PATTERN_MALFORMED",
    "CODE_REF_CYCLE",
    "CODE_REF_POINTER_MALFORMED",
    "CODE_REF_TARGET",
    "CODE_REF_UNRESOLVABLE",
    "CODE_REQUIRED",
    "CODE_SCHEMA_FALSE",
    "CODE_SCHEMA_NODE",
    "CODE_SCHEMA_SHAPE",
    "CODE_TYPE",
    "CODE_UNSAFE_REF",
    "CODE_UNIQUE_ITEMS",
    "CODE_UNSUPPORTED_FORMAT",
    "CODE_UNSUPPORTED_KEYWORD",
    "Diagnostic",
    "StrictJSONError",
    "inspect_schema",
    "is_valid",
    "loads_strict",
    "validate",
]
