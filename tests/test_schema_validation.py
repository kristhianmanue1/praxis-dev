from __future__ import annotations

import json
from pathlib import Path
import unittest

from praxis_dev import schema_validation as sv
from praxis_dev.schema_validation import Diagnostic, StrictJSONError

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "schema_validation"


def codes(diags: list[Diagnostic]) -> list[str]:
    return [d.code for d in diags]


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class LoadsStrictTests(unittest.TestCase):
    def test_valid_parses(self) -> None:
        self.assertEqual(sv.loads_strict('{"a": 1, "b": [1, 2]}'), {"a": 1, "b": [1, 2]})

    def test_duplicate_keys_rejected(self) -> None:
        with self.assertRaises(StrictJSONError) as ctx:
            sv.loads_strict('{"$id": "a", "$id": "b"}')
        self.assertIn(sv.CODE_DUPLICATE_KEY, str(ctx.exception))

    def test_nan_rejected(self) -> None:
        with self.assertRaises(StrictJSONError):
            sv.loads_strict('{"x": NaN}')

    def test_infinity_rejected(self) -> None:
        with self.assertRaises(StrictJSONError):
            sv.loads_strict('{"x": Infinity}')

    def test_negative_infinity_rejected(self) -> None:
        with self.assertRaises(StrictJSONError):
            sv.loads_strict('{"x": -Infinity}')

    def test_non_string_input_rejected(self) -> None:
        with self.assertRaises(StrictJSONError):
            sv.loads_strict(b'{"a": 1}')  # type: ignore[arg-type]


class InspectSchemaTests(unittest.TestCase):
    def test_all_praxis_schemas_are_consumable(self) -> None:
        for path in sorted(SCHEMAS.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sv.inspect_schema(schema), [], f"{path.name} not consumable")

    def test_unknown_keyword_fails_closed(self) -> None:
        schema = {"type": "object", "patternProperties": {"^x$": {"type": "string"}}}
        self.assertIn(sv.CODE_UNSUPPORTED_KEYWORD, codes(sv.inspect_schema(schema)))

    def test_unsupported_format_fails_closed(self) -> None:
        schema = {"type": "string", "format": "uri"}
        self.assertIn(sv.CODE_UNSUPPORTED_FORMAT, codes(sv.inspect_schema(schema)))

    def test_external_ref_fails_closed(self) -> None:
        schema = {"$ref": "https://example.com/schema.json"}
        self.assertIn(sv.CODE_EXTERNAL_REF, codes(sv.inspect_schema(schema)))

    def test_escape_ref_fails_closed(self) -> None:
        schema = {"$ref": "#/../etc/passwd"}
        self.assertIn(sv.CODE_UNSAFE_REF, codes(sv.inspect_schema(schema)))

    def test_boolean_root_rejected(self) -> None:
        self.assertEqual(codes(sv.inspect_schema(True)), [sv.CODE_SCHEMA_NODE])

    def test_property_named_like_keyword_not_flagged(self) -> None:
        schema = {"type": "object",
                  "properties": {"format": {"type": "string"}, "required": {"type": "boolean"}}}
        self.assertEqual(sv.inspect_schema(schema), [])


class KeywordTypeTests(unittest.TestCase):
    def test_integer_accepts_1_and_1_0(self) -> None:
        self.assertEqual(sv.validate(1, {"type": "integer"}), [])
        self.assertEqual(sv.validate(1.0, {"type": "integer"}), [])

    def test_integer_rejects_1_5_and_bool(self) -> None:
        self.assertIn(sv.CODE_TYPE, codes(sv.validate(1.5, {"type": "integer"})))
        self.assertIn(sv.CODE_TYPE, codes(sv.validate(True, {"type": "integer"})))

    def test_number_accepts_int_and_float_rejects_bool(self) -> None:
        self.assertEqual(sv.validate(2, {"type": "number"}), [])
        self.assertEqual(sv.validate(2.5, {"type": "number"}), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate(True, {"type": "number"})))

    def test_other_types(self) -> None:
        self.assertEqual(sv.validate("s", {"type": "string"}), [])
        self.assertEqual(sv.validate({}, {"type": "object"}), [])
        self.assertEqual(sv.validate([], {"type": "array"}), [])
        self.assertEqual(sv.validate(None, {"type": "null"}), [])
        self.assertEqual(sv.validate(False, {"type": "boolean"}), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate("s", {"type": "object"})))


class KeywordConstEnumTests(unittest.TestCase):
    def test_const_numeric_equality(self) -> None:
        self.assertEqual(sv.validate(1.0, {"const": 1}), [])

    def test_const_mismatch(self) -> None:
        self.assertIn(sv.CODE_CONST, codes(sv.validate(2, {"const": 1})))

    def test_enum(self) -> None:
        self.assertEqual(sv.validate("b", {"enum": ["a", "b"]}), [])
        self.assertIn(sv.CODE_ENUM, codes(sv.validate("c", {"enum": ["a", "b"]})))


class KeywordObjectTests(unittest.TestCase):
    def test_required(self) -> None:
        schema = {"type": "object", "required": ["a", "b"], "properties": {"a": {}, "b": {}}}
        self.assertIn(sv.CODE_REQUIRED, codes(sv.validate({"a": 1}, schema)))

    def test_min_properties(self) -> None:
        self.assertIn(sv.CODE_MIN_PROPERTIES, codes(sv.validate({}, {"minProperties": 1})))

    def test_additional_properties_false(self) -> None:
        schema = {"type": "object", "properties": {"a": {}}, "additionalProperties": False}
        self.assertIn(sv.CODE_ADDITIONAL_PROPERTIES, codes(sv.validate({"a": 1, "x": 2}, schema)))

    def test_additional_properties_schema(self) -> None:
        schema = {"type": "object", "additionalProperties": {"type": "string"}}
        self.assertEqual(sv.validate({"a": "x"}, schema), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate({"a": 1}, schema)))


class KeywordStringTests(unittest.TestCase):
    def test_pattern_search_semantics(self) -> None:
        self.assertEqual(sv.validate("xab", {"type": "string", "pattern": "ab"}), [])
        self.assertIn(sv.CODE_PATTERN, codes(sv.validate("xcd", {"type": "string", "pattern": "ab"})))

    def test_min_max_length_boundaries(self) -> None:
        self.assertEqual(sv.validate("abc", {"type": "string", "minLength": 3, "maxLength": 3}), [])
        self.assertIn(sv.CODE_MIN_LENGTH, codes(sv.validate("ab", {"minLength": 3})))
        self.assertIn(sv.CODE_MAX_LENGTH, codes(sv.validate("abcd", {"maxLength": 3})))


class KeywordArrayTests(unittest.TestCase):
    def test_min_max_items(self) -> None:
        self.assertIn(sv.CODE_MIN_ITEMS, codes(sv.validate([1], {"minItems": 2})))
        self.assertIn(sv.CODE_MAX_ITEMS, codes(sv.validate([1, 2, 3], {"maxItems": 2})))

    def test_unique_items_objects_reordered(self) -> None:
        schema = {"uniqueItems": True}
        self.assertIn(sv.CODE_UNIQUE_ITEMS,
                      codes(sv.validate([{"a": 1, "b": 2}, {"b": 2, "a": 1}], schema)))

    def test_unique_items_1_vs_1_0(self) -> None:
        self.assertIn(sv.CODE_UNIQUE_ITEMS, codes(sv.validate([1, 1.0], {"uniqueItems": True})))

    def test_unique_items_1_vs_true_distinct(self) -> None:
        self.assertEqual(sv.validate([1, True], {"uniqueItems": True}), [])

    def test_items(self) -> None:
        schema = {"type": "array", "items": {"type": "integer"}}
        self.assertEqual(sv.validate([1, 2, 3], schema), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate([1, "x"], schema)))

    def test_contains_match_and_zero(self) -> None:
        schema = {"type": "array", "contains": {"type": "string"}}
        self.assertEqual(sv.validate([1, "x"], schema), [])
        self.assertIn(sv.CODE_CONTAINS, codes(sv.validate([1, 2], schema)))


class CombinatorTests(unittest.TestCase):
    def test_one_of_ambiguous(self) -> None:
        schema = {"oneOf": [{"type": "string", "minLength": 1}, {"type": "string", "pattern": "^a"}]}
        self.assertIn(sv.CODE_ONE_OF, codes(sv.validate("abc", schema)))

    def test_one_of_exact_and_zero(self) -> None:
        schema = {"oneOf": [{"type": "string"}, {"type": "null"}]}
        self.assertEqual(sv.validate("s", schema), [])
        self.assertIn(sv.CODE_ONE_OF, codes(sv.validate(5, schema)))

    def test_all_of_combinator(self) -> None:
        schema = {"allOf": [{"type": "string"}, {"minLength": 3}]}
        self.assertEqual(sv.validate("abc", schema), [])
        self.assertIn(sv.CODE_MIN_LENGTH, codes(sv.validate("ab", schema)))
        self.assertIn(sv.CODE_TYPE, codes(sv.validate(5, schema)))

    def test_if_then_branch(self) -> None:
        schema = {"if": {"type": "string"}, "then": {"const": "a"}, "else": {"const": "b"}}
        self.assertIn(sv.CODE_CONST, codes(sv.validate("x", schema)))

    def test_if_else_branch(self) -> None:
        schema = {"if": {"type": "string"}, "then": {"const": "a"}, "else": {"const": "b"}}
        self.assertIn(sv.CODE_CONST, codes(sv.validate(5, schema)))


class RefTests(unittest.TestCase):
    def test_local_ref_resolves(self) -> None:
        schema = {"$defs": {"pos": {"type": "integer"}}, "$ref": "#/$defs/pos"}
        self.assertEqual(sv.validate(3, schema), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate("x", schema)))

    def test_external_ref_fails_closed_in_validate(self) -> None:
        self.assertIn(sv.CODE_EXTERNAL_REF, codes(sv.validate(1, {"$ref": "https://x/s.json"})))

    def test_unresolvable_local_ref(self) -> None:
        self.assertIn(sv.CODE_REF_UNRESOLVABLE, codes(sv.validate(1, {"$ref": "#/$defs/missing"})))


class DateTimeTests(unittest.TestCase):
    def _dt(self, value: str) -> list[str]:
        return codes(sv.validate(value, {"type": "string", "format": "date-time"}))

    def test_z_valid(self) -> None:
        self.assertEqual(self._dt("2026-08-11T11:02:19Z"), [])

    def test_plus_zero_valid(self) -> None:
        self.assertEqual(self._dt("2026-08-11T11:02:19+00:00"), [])

    def test_minus_zero_rejected(self) -> None:
        self.assertIn(sv.CODE_FORMAT_DATE_TIME, self._dt("2026-08-11T11:02:19-00:00"))

    def test_non_utc_offset_rejected(self) -> None:
        self.assertIn(sv.CODE_FORMAT_DATE_TIME, self._dt("2026-08-11T11:02:19+02:00"))

    def test_naive_rejected(self) -> None:
        self.assertIn(sv.CODE_FORMAT_DATE_TIME, self._dt("2026-08-11T11:02:19"))

    def test_impossible_date_rejected(self) -> None:
        self.assertIn(sv.CODE_FORMAT_DATE_TIME, self._dt("2026-99-99T25:61:61Z"))


class FailClosedTests(unittest.TestCase):
    def test_validate_unknown_keyword(self) -> None:
        diags = sv.validate("x", {"type": "string", "anyOf": [{"const": "x"}]})
        self.assertIn(sv.CODE_UNSUPPORTED_KEYWORD, codes(diags))

    def test_validate_unsupported_format(self) -> None:
        diags = sv.validate("x", {"type": "string", "format": "email"})
        self.assertIn(sv.CODE_UNSUPPORTED_FORMAT, codes(diags))


class AuditorRegressionTests(unittest.TestCase):
    def test_contains_malformed_value_flagged(self) -> None:
        self.assertIn(sv.CODE_SCHEMA_SHAPE, codes(sv.inspect_schema({"contains": "bad"})))

    def test_items_as_list_flagged_in_inspect_and_validate(self) -> None:
        schema = {"items": [{"type": "string"}]}
        self.assertIn(sv.CODE_SCHEMA_SHAPE, codes(sv.inspect_schema(schema)))
        self.assertIn(sv.CODE_SCHEMA_SHAPE, codes(sv.validate([], schema)))

    def test_broken_local_ref_flagged_at_inspect(self) -> None:
        for ref in ("#/$defs/missing", "#//missing"):
            self.assertIn(sv.CODE_REF_UNRESOLVABLE, codes(sv.inspect_schema({"$ref": ref})), ref)

    def test_pattern_invalid_regex_does_not_raise(self) -> None:
        diags = sv.validate("x", {"pattern": "["})
        self.assertIn(sv.CODE_PATTERN_MALFORMED, codes(diags))

    def test_non_finite_instance_rejected(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            self.assertIn(sv.CODE_NON_FINITE, codes(sv.validate(bad, {"type": "number"})), repr(bad))

    def test_malformed_keyword_shapes_flagged(self) -> None:
        cases = {
            "type": {"type": "interger"},
            "enum": {"enum": "not-list"},
            "required": {"required": ["a", 2]},
            "minLength-negative": {"minLength": -1},
            "minLength-bool": {"minLength": True},
            "uniqueItems": {"uniqueItems": "yes"},
            "oneOf": {"oneOf": {"not": "list"}},
            "additionalProperties": {"additionalProperties": "nope"},
        }
        for name, schema in cases.items():
            self.assertIn(sv.CODE_SCHEMA_SHAPE, codes(sv.inspect_schema(schema)), name)

    def test_ref_with_json_pointer_escapes_resolves(self) -> None:
        schema = {"$defs": {"a/b": {"type": "string"}}, "$ref": "#/$defs/a~1b"}
        self.assertEqual(sv.inspect_schema(schema), [])
        self.assertEqual(sv.validate("x", schema), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate(1, schema)))

    def test_cyclic_ref_detected_without_infinite_recursion(self) -> None:
        schema = {"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}},
                  "$ref": "#/$defs/a"}
        self.assertIn(sv.CODE_REF_CYCLE, codes(sv.inspect_schema(schema)))
        self.assertIn(sv.CODE_REF_CYCLE, codes(sv.validate(1, schema)))

    def test_ref_non_subschema_target_flagged(self) -> None:
        schema = {"$defs": {"k": "not-a-schema"}, "$ref": "#/$defs/k"}
        self.assertIn(sv.CODE_REF_TARGET, codes(sv.inspect_schema(schema)))


class FixtureCasesTests(unittest.TestCase):
    def test_fixture_cases(self) -> None:
        files = sorted(FIXTURES.glob("*.cases.json"))
        self.assertEqual(len(files), 7, "expected one fixture file per schema")
        seen_schemas: set[str] = set()
        for path in files:
            blob = json.loads(path.read_text(encoding="utf-8"))
            schema = load_schema(blob["schema_file"])
            seen_schemas.add(blob["schema_file"])
            self.assertEqual(sv.inspect_schema(schema), [], f"{blob['schema_file']} not consumable")
            for case in blob["cases"]:
                with self.subTest(file=path.name, case=case["name"]):
                    diags = sv.validate(case["instance"], schema)
                    if case["valid"]:
                        self.assertEqual(diags, [], f"{path.name}/{case['name']} unexpectedly invalid")
                    else:
                        self.assertTrue(diags, f"{path.name}/{case['name']} unexpectedly valid")
                        self.assertIn(case["code"], codes(diags),
                                      f"{path.name}/{case['name']} missing expected code {case['code']}")
        # Ensure every Praxis schema has at least one fixture file.
        for schema_path in sorted(SCHEMAS.glob("*.schema.json")):
            self.assertIn(schema_path.name, seen_schemas, f"no fixture for {schema_path.name}")


class RefSiblingAndPointerTests(unittest.TestCase):
    """Draft 2020-12 $ref semantics and JSON Pointer escape diagnostics."""

    def test_root_ref_siblings_apply_through_chain(self) -> None:
        schema = {
            "$defs": {
                "base": {"type": "string"},
                "constrained": {"$ref": "#/$defs/base", "minLength": 3},
            },
            "$ref": "#/$defs/constrained",
        }
        self.assertEqual(sv.inspect_schema(schema), [])
        self.assertIn(sv.CODE_MIN_LENGTH, codes(sv.validate("x", schema)))
        self.assertEqual(sv.validate("abcd", schema), [])

    def test_siblings_apply_at_intermediate_ref_not_only_root(self) -> None:
        schema = {
            "$defs": {
                "a": {"$ref": "#/$defs/b", "minLength": 5},
                "b": {"type": "string"},
            },
            "$ref": "#/$defs/a",
        }
        self.assertEqual(sv.inspect_schema(schema), [])
        self.assertIn(sv.CODE_MIN_LENGTH, codes(sv.validate("hi", schema)))
        self.assertEqual(sv.validate("abcdef", schema), [])

    def test_valid_tilde1_escape_still_resolves(self) -> None:
        schema = {"$defs": {"a/b": {"type": "string"}}, "$ref": "#/$defs/a~1b"}
        self.assertEqual(sv.inspect_schema(schema), [])
        self.assertEqual(sv.validate("x", schema), [])
        self.assertIn(sv.CODE_TYPE, codes(sv.validate(1, schema)))

    def test_invalid_tilde2_escape_flagged_distinct_from_unresolvable(self) -> None:
        schema = {"$ref": "#/$defs/a~2b"}
        for diags in (sv.inspect_schema(schema), sv.validate(1, schema)):
            self.assertIn(sv.CODE_REF_POINTER_MALFORMED, codes(diags))
            self.assertNotIn(sv.CODE_REF_UNRESOLVABLE, codes(diags))

    def test_trailing_tilde_escape_flagged(self) -> None:
        schema = {"$ref": "#/$defs/a~"}
        self.assertIn(sv.CODE_REF_POINTER_MALFORMED, codes(sv.inspect_schema(schema)))

    def test_cyclic_ref_with_siblings_terminates(self) -> None:
        schema = {
            "$defs": {
                "a": {"$ref": "#/$defs/b", "minLength": 1},
                "b": {"$ref": "#/$defs/a"},
            },
            "$ref": "#/$defs/a",
        }
        diags = sv.validate("x", schema)
        self.assertIn(sv.CODE_REF_CYCLE, codes(diags))


if __name__ == "__main__":
    unittest.main()
