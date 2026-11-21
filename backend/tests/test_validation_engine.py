"""Unit tests for the Deterministic Validation Engine orchestrator and registry."""

import pytest
from app.validation.config import ValidationConfig
from app.validation.engine import ValidationEngine
from app.validation.models import Severity, ValidationStatus, ValidationFinding
from app.validation.registry import RuleRegistry
from app.validation.rules.base import ValidationRule


class DummyPassingRule(ValidationRule):
    def __init__(self, rule_id="RULE_PASS"):
        super().__init__(
            rule_id=rule_id,
            name="Always Pass",
            description="Always passes with 0 findings",
            default_severity=Severity.INFO,
            target_fields=["field_a"],
            category="general",
        )

    def validate(self, data, context, config):
        return []


class DummyFailingRule(ValidationRule):
    def __init__(self, rule_id="RULE_FAIL", severity=Severity.ERROR, field="field_b"):
        super().__init__(
            rule_id=rule_id,
            name="Always Fail",
            description="Always emits a finding",
            default_severity=severity,
            target_fields=[field],
            category="general",
        )
        self.field = field

    def validate(self, data, context, config):
        return [
            self.create_finding(
                field=self.field,
                code="DUMMY_FAIL_CODE",
                message=f"Test failure on {self.field}",
                suggestion="Fix the field",
                config=config,
            )
        ]


class TestValidationEngineOrchestration:
    """Verifies engine execution, result aggregation, and deterministic ordering."""

    def test_multiple_rules_execute_and_collect_all_findings(self):
        """Engine does not short-circuit on the first error and runs all active rules."""
        registry = RuleRegistry()
        registry.register_rule(DummyPassingRule("RULE_1"))
        registry.register_rule(DummyFailingRule("RULE_2_ERROR", severity=Severity.ERROR, field="field_2"))
        registry.register_rule(DummyFailingRule("RULE_3_WARN", severity=Severity.WARNING, field="field_3"))
        registry.register_rule(DummyFailingRule("RULE_4_ERROR", severity=Severity.ERROR, field="field_4"))

        engine = ValidationEngine(registry=registry)
        result = engine.validate_vendor({"field_2": "val", "field_3": "val", "field_4": "val"})

        assert result.status == ValidationStatus.FAILED
        assert result.valid is False
        assert result.summary.total_checks == 4
        assert result.summary.passed == 1
        assert result.summary.failed == 2
        assert result.summary.warnings == 1
        assert len(result.findings) == 3

    def test_deterministic_ordering_of_findings(self):
        """Findings are deterministically ordered: Severity (ERROR -> WARNING -> INFO), then field name, then rule ID."""
        registry = RuleRegistry()
        # Register in mixed order
        registry.register_rule(DummyFailingRule("RULE_WARN_Z", severity=Severity.WARNING, field="z_field"))
        registry.register_rule(DummyFailingRule("RULE_ERR_B", severity=Severity.ERROR, field="b_field"))
        registry.register_rule(DummyFailingRule("RULE_ERR_A", severity=Severity.ERROR, field="a_field"))
        registry.register_rule(DummyFailingRule("RULE_INFO_M", severity=Severity.INFO, field="m_field"))

        engine = ValidationEngine(registry=registry)
        result = engine.validate_vendor({})

        # Order must be: ERR_A, ERR_B, WARN_Z, INFO_M
        severities = [f.severity for f in result.findings]
        fields = [f.field for f in result.findings]

        assert severities == [Severity.ERROR, Severity.ERROR, Severity.WARNING, Severity.INFO]
        assert fields == ["a_field", "b_field", "z_field", "m_field"]

    def test_disabled_rules_do_not_execute(self):
        """Rules listed in disabled_rules are skipped completely from execution and total_checks."""
        registry = RuleRegistry()
        registry.register_rule(DummyFailingRule("ACTIVE_ERR", severity=Severity.ERROR))
        registry.register_rule(DummyFailingRule("DISABLED_ERR", severity=Severity.ERROR))

        config = ValidationConfig(disabled_rules={"DISABLED_ERR"})
        engine = ValidationEngine(registry=registry, config=config)
        result = engine.validate_vendor({})

        assert result.summary.total_checks == 1
        assert len(result.findings) == 1
        assert result.findings[0].rule_id == "ACTIVE_ERR"

    def test_severity_overrides_are_respected(self):
        """Configuring a severity override alters the finding's severity level."""
        registry = RuleRegistry()
        registry.register_rule(DummyFailingRule("OVERRIDABLE_RULE", severity=Severity.ERROR, field="field_x"))

        # Override ERROR to WARNING
        config = ValidationConfig(severity_overrides={"OVERRIDABLE_RULE": Severity.WARNING})
        engine = ValidationEngine(registry=registry, config=config)
        result = engine.validate_vendor({})

        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.WARNING
        # With only WARNING findings, status becomes PASSED_WITH_WARNINGS and valid is True
        assert result.status == ValidationStatus.PASSED_WITH_WARNINGS
        assert result.valid is True

    def test_zero_mutation_of_input_vendor_data(self):
        """Engine never mutates the original vendor dictionary or object."""
        original_dict = {
            "legal_name": "  Untrimmed Co  ",
            "contact_email": "TEST@EXAMPLE.COM",
            "bank_account_number": "987654321",
            "nested_data": {"active": True},
        }
        dict_copy = dict(original_dict)

        engine = ValidationEngine()
        engine.validate_vendor(original_dict)

        assert original_dict == dict_copy
        assert original_dict["legal_name"] == "  Untrimmed Co  "

    def test_findings_never_leak_sensitive_bank_account_values(self):
        """Findings messages and suggestions never expose the raw account number."""
        sample_secret = "SECRET_BANK_ACCT_999888777"
        engine = ValidationEngine()
        
        result = engine.validate_vendor({
            "bank_account_number": sample_secret,
        })

        for finding in result.findings:
            assert sample_secret not in finding.message
            if finding.suggestion:
                assert sample_secret not in finding.suggestion
