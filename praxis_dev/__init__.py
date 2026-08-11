"""Praxis Dev internal library.

This package hosts the runtime building blocks of the Praxis reference
implementation. The first delivered block is the closed JSON Schema validation
module (ADR-0002, proposed): see :mod:`praxis_dev.schema_validation`.
"""

from __future__ import annotations

from praxis_dev.schema_validation import (
    ANNOTATION_KEYWORDS,
    SUPPORTED_FORMATS,
    SUPPORTED_KEYWORDS,
    CODE_PATTERN_MALFORMED,
    CODE_REF_CYCLE,
    CODE_REF_TARGET,
    CODE_SCHEMA_SHAPE,
    Diagnostic,
    StrictJSONError,
    inspect_schema,
    is_valid,
    loads_strict,
    validate,
)

__all__ = [
    "ANNOTATION_KEYWORDS",
    "SUPPORTED_FORMATS",
    "SUPPORTED_KEYWORDS",
    "CODE_PATTERN_MALFORMED",
    "CODE_REF_CYCLE",
    "CODE_REF_TARGET",
    "CODE_SCHEMA_SHAPE",
    "Diagnostic",
    "StrictJSONError",
    "inspect_schema",
    "is_valid",
    "loads_strict",
    "validate",
]
