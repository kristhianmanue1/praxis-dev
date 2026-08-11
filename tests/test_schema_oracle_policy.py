from __future__ import annotations

import sys
import unittest
from pathlib import Path

# The oracle module defers its jsonschema import, so it is importable in this
# stdlib-only test environment. We exercise the pure classification logic that
# decides whether a runtime/reference fixture divergence is declared Praxis
# policy or an unexpected gate failure.
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_schema_oracle as oracle  # noqa: E402

ALLOWED_LABEL = "audit-result.cases.json/datetime-non-utc"
ALLOWED_FIELD = "observed_at"
ALLOWED_TS = "2026-08-11T11:02:19+02:00"


class ClassifyDivergenceTests(unittest.TestCase):
    def _instance(self, observed_at: str) -> dict:
        return {"schema": "praxis/audit-result/v1", "observed_at": observed_at}

    def test_allowlisted_non_utc_is_policy(self) -> None:
        severity, detail = oracle.classify_divergence(
            ALLOWED_LABEL, self._instance(ALLOWED_TS),
            runtime_ok=False, reference_ok=True, codes={"format-date-time"},
        )
        self.assertEqual(severity, "POLICY")
        self.assertIn(ALLOWED_TS, detail)

    def test_valid_Z_timestamp_cannot_be_policy(self) -> None:
        # The whole point: if the runtime ever wrongly invalidated a valid UTC
        # `Z` timestamp, that is a BUG. It must NOT be classified as policy.
        severity, detail = oracle.classify_divergence(
            ALLOWED_LABEL, self._instance("2026-08-11T11:02:19Z"),
            runtime_ok=False, reference_ok=True, codes={"format-date-time"},
        )
        self.assertEqual(severity, "ERROR")
        self.assertIn("UNEXPECTED", detail)

    def test_unknown_label_is_error(self) -> None:
        severity, _ = oracle.classify_divergence(
            "audit-result.cases.json/some-other-case", self._instance(ALLOWED_TS),
            runtime_ok=False, reference_ok=True, codes={"format-date-time"},
        )
        self.assertEqual(severity, "ERROR")

    def test_different_offset_same_label_is_error(self) -> None:
        severity, _ = oracle.classify_divergence(
            ALLOWED_LABEL, self._instance("2026-08-11T11:02:19+05:00"),
            runtime_ok=False, reference_ok=True, codes={"format-date-time"},
        )
        self.assertEqual(severity, "ERROR")

    def test_runtime_valid_reference_invalid_is_error(self) -> None:
        severity, _ = oracle.classify_divergence(
            ALLOWED_LABEL, self._instance(ALLOWED_TS),
            runtime_ok=True, reference_ok=False, codes=set(),
        )
        self.assertEqual(severity, "ERROR")

    def test_non_datetime_codes_are_error(self) -> None:
        severity, _ = oracle.classify_divergence(
            ALLOWED_LABEL, self._instance(ALLOWED_TS),
            runtime_ok=False, reference_ok=True, codes={"format-date-time", "type"},
        )
        self.assertEqual(severity, "ERROR")

    def test_runtime_and_reference_agree_is_not_a_divergence(self) -> None:
        # classify_divergence is only called on disagreements, but ensure that
        # a (False, False) agreement is not mislabelled as policy.
        severity, _ = oracle.classify_divergence(
            ALLOWED_LABEL, self._instance(ALLOWED_TS),
            runtime_ok=False, reference_ok=False, codes={"format-date-time"},
        )
        self.assertEqual(severity, "ERROR")

    def test_allowed_timestamp_under_wrong_field_is_error(self) -> None:
        # Attacker: observed_at is a valid Z (runtime should accept it), but the
        # allowed non-UTC timestamp is planted under a different field. Broad
        # any-string matching would call this POLICY; field-exact matching must
        # reject it as ERROR.
        instance = {
            "schema": "praxis/audit-result/v1",
            ALLOWED_FIELD: "2026-08-11T11:02:19Z",
            "decoy_field": ALLOWED_TS,
        }
        severity, detail = oracle.classify_divergence(
            ALLOWED_LABEL, instance,
            runtime_ok=False, reference_ok=True, codes={"format-date-time"},
        )
        self.assertEqual(severity, "ERROR")
        self.assertIn("UNEXPECTED", detail)

    def test_non_dict_instance_is_error(self) -> None:
        severity, _ = oracle.classify_divergence(
            ALLOWED_LABEL, ALLOWED_TS,  # bare string, not a dict with the field
            runtime_ok=False, reference_ok=True, codes={"format-date-time"},
        )
        self.assertEqual(severity, "ERROR")


class AllowlistShapeTests(unittest.TestCase):
    def test_allowlist_pins_exactly_one_case(self) -> None:
        self.assertEqual(len(oracle.KNOWN_UTC_POLICY_FIXTURES), 1)

    def test_allowlist_timestamps_are_non_utc(self) -> None:
        for label, case in oracle.KNOWN_UTC_POLICY_FIXTURES.items():
            self.assertFalse(
                case.timestamp.endswith("Z") or case.timestamp.endswith("+00:00"),
                f"{label} pins a UTC timestamp {case.timestamp!r}",
            )

    def test_allowlist_label_matches_existing_fixture(self) -> None:
        # The allowlist must point at a real fixture case, field, and value.
        fixture_file, case_name = ALLOWED_LABEL.split("/", 1)
        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "tests" / "fixtures" / "schema_validation" / fixture_file
        )
        import json
        blob = json.loads(fixture_path.read_text(encoding="utf-8"))
        names = {case["name"] for case in blob["cases"]}
        self.assertIn(case_name, names)
        case = next(c for c in blob["cases"] if c["name"] == case_name)
        # Field-exact: the pinned field must equal the pinned value byte for byte.
        self.assertEqual(case["instance"][ALLOWED_FIELD], ALLOWED_TS)


if __name__ == "__main__":
    unittest.main()
