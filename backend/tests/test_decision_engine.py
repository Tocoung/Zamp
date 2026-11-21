"""Unit tests for deterministic decision engine mapping, logic, explainability, and policy hardening."""

from datetime import datetime, timezone
import pytest

from app.decision.models import (
    DecisionAction,
    DecisionReason,
    DecisionRecommendation,
    DecisionResult,
    DecisionStatus,
)
from app.decision.config import DecisionConfig, DEFAULT_RULE_ACTIONS
from app.decision.engine import DecisionEngine
from app.decision.rules import (
    map_finding_to_decision_reason,
    map_finding_to_recommendation,
)
from app.validation.registry import default_registry
from app.validation.rules.required import REQUIRED_FIELDS_METADATA
from app.validation.models import (
    Severity,
    ValidationFinding,
    ValidationResult,
    ValidationSummary,
)


@pytest.fixture
def clean_decision_engine() -> DecisionEngine:
    """Provides a fresh DecisionEngine instance with default configuration."""
    return DecisionEngine(default_config=DecisionConfig())


@pytest.fixture
def mock_validation_passed() -> ValidationResult:
    """Mock validation result representing all checks passed without findings."""
    return ValidationResult(
        validation_id="val-clean-001",
        vendor_id="vendor-123",
        status="PASSED",
        valid=True,
        summary=ValidationSummary(
            total_checks=28,
            passed=28,
            failed=0,
            warnings=0,
            info=0,
        ),
        findings=[],
        validated_at=datetime.now(timezone.utc),
        ruleset_version="1.0.0",
    )


class TestDecisionEngineRegistryCoverage:
    """Verifies that all registered validation rules have explicit and deterministic mappings."""

    def test_all_registered_validation_rules_explicitly_mapped(self):
        """Every single rule in default_registry (all 28 rules) must be explicitly mapped in rule_actions."""
        config = DecisionConfig()
        coverage_report = config.verify_registry_coverage(default_registry)

        assert coverage_report["is_fully_covered"] is True
        assert coverage_report["total_registered_rules"] == 28
        assert coverage_report["explicitly_mapped_count"] == 28
        assert coverage_report["fallback_covered_count"] == 0

        # Confirm all 19 required field rules explicitly map to DecisionAction.REVIEW
        for field, rule_id, _, _ in REQUIRED_FIELDS_METADATA:
            assert rule_id in config.rule_actions, f"Rule {rule_id} missing from rule_actions"
            assert config.rule_actions[rule_id] == DecisionAction.REVIEW

        # Confirm format rules map to BLOCK
        format_rules = [
            "FMT_EMAIL_STRUCTURE",
            "FMT_PHONE_INTERNATIONAL",
            "FMT_TAX_ID_SYNTAX",
            "FMT_BANK_ROUTING",
            "FMT_BANK_ACCOUNT_STRUCTURAL",
        ]
        for f_rule in format_rules:
            assert config.rule_actions[f_rule] == DecisionAction.BLOCK

        # Confirm consistency rules
        assert config.rule_actions["CONST_ACCOUNT_HOLDER_MATCH"] == DecisionAction.REVIEW
        assert config.rule_actions["CONST_TAX_TYPE_COUNTRY"] == DecisionAction.REVIEW
        assert config.rule_actions["CONST_ROUTING_BANK_COUNTRY"] == DecisionAction.REVIEW
        assert config.rule_actions["CONST_CROSS_BORDER_REGISTRATION"] == DecisionAction.IGNORE


class TestRequiredFieldDecisionPolicy:
    """Verifies that missing required fields produce PENDING with actionable recommendations."""

    @pytest.mark.parametrize("field,rule_id,msg,sugg", REQUIRED_FIELDS_METADATA)
    def test_each_required_field_rule_evaluates_to_pending(
        self, clean_decision_engine: DecisionEngine, field: str, rule_id: str, msg: str, sugg: str
    ):
        """Each of the 19 required fields when missing must evaluate to PENDING (never REJECTED)."""
        finding = ValidationFinding(
            rule_id=rule_id,
            field=field,
            severity=Severity.ERROR,
            status="FAILED",
            code="REQUIRED_FIELD_MISSING",
            message=msg,
            suggestion=sugg,
        )

        val_result = ValidationResult(
            validation_id=f"val-req-{field}",
            vendor_id="vendor-test",
            status="FAILED",
            valid=False,
            summary=ValidationSummary(total_checks=28, passed=27, failed=1, warnings=0, info=0),
            findings=[finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(
            validation_result=val_result,
            vendor_id="vendor-test",
        )

        # Incomplete submission must be PENDING, not REJECTED
        assert result.status == DecisionStatus.PENDING
        expected_code = f"MISSING_{field.upper()}"
        assert expected_code in result.reason_codes

        # Verify reason details
        matching_reasons = [r for r in result.reasons if r.code == expected_code]
        assert len(matching_reasons) == 1
        assert field in matching_reasons[0].explanation
        assert "incomplete" in matching_reasons[0].explanation.lower()

        # Verify actionable recommendation
        expected_rec_action = f"PROVIDE_{field.upper()}"
        matching_recs = [rec for rec in result.recommendations if rec.action == expected_rec_action]
        assert len(matching_recs) == 1
        assert matching_recs[0].priority == "MEDIUM"

    def test_multiple_missing_fields_produce_pending_with_all_reasons(
        self, clean_decision_engine: DecisionEngine
    ):
        """When multiple required fields are missing, all reasons are preserved under PENDING."""
        findings = [
            ValidationFinding(
                rule_id="COMPANY_LEGAL_NAME_REQUIRED",
                field="legal_name",
                severity=Severity.ERROR,
                status="FAILED",
                code="REQUIRED_FIELD_MISSING",
                message="Legal company name is required.",
                suggestion="Provide legal name.",
            ),
            ValidationFinding(
                rule_id="CONTACT_EMAIL_REQUIRED",
                field="contact_email",
                severity=Severity.ERROR,
                status="FAILED",
                code="REQUIRED_FIELD_MISSING",
                message="Business contact email is required.",
                suggestion="Provide contact email.",
            ),
            ValidationFinding(
                rule_id="BANK_ACCOUNT_NUMBER_REQUIRED",
                field="bank_account_number",
                severity=Severity.ERROR,
                status="FAILED",
                code="REQUIRED_FIELD_MISSING",
                message="Bank account number is required.",
                suggestion="Provide account number.",
            ),
        ]

        val_result = ValidationResult(
            validation_id="val-multi-missing",
            vendor_id="vendor-test",
            status="FAILED",
            valid=False,
            summary=ValidationSummary(total_checks=28, passed=25, failed=3, warnings=0, info=0),
            findings=findings,
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(
            validation_result=val_result,
            vendor_id="vendor-test",
        )

        assert result.status == DecisionStatus.PENDING
        assert "MISSING_LEGAL_NAME" in result.reason_codes
        assert "MISSING_CONTACT_EMAIL" in result.reason_codes
        assert "MISSING_BANK_ACCOUNT_NUMBER" in result.reason_codes
        assert len(result.reasons) == 3
        assert len(result.recommendations) == 3


class TestDecisionPolicyPrecedence:
    """Verifies resolution precedence: Finding code override -> Rule ID mapping -> Severity fallback."""

    def test_precedence_hierarchy(self):
        config = DecisionConfig(
            rule_actions={"TEST_RULE": DecisionAction.BLOCK},
            finding_code_actions={"OVERRIDE_CODE": DecisionAction.IGNORE},
            default_error_action=DecisionAction.BLOCK,
            default_warning_action=DecisionAction.REVIEW,
            default_info_action=DecisionAction.IGNORE,
        )

        # 1. Finding code override beats Rule ID mapping
        action1 = config.resolve_action(
            rule_id="TEST_RULE",
            finding_code="OVERRIDE_CODE",
            severity="ERROR",
        )
        assert action1 == DecisionAction.IGNORE

        # 2. Rule ID mapping beats severity fallback
        action2 = config.resolve_action(
            rule_id="TEST_RULE",
            finding_code="NON_OVERRIDDEN_CODE",
            severity="INFO",
        )
        assert action2 == DecisionAction.BLOCK

        # 3. Severity fallback is used when neither finding code nor rule ID is mapped
        action3_err = config.resolve_action(
            rule_id="UNMAPPED_RULE",
            finding_code="UNMAPPED_CODE",
            severity="ERROR",
        )
        assert action3_err == DecisionAction.BLOCK

        action3_warn = config.resolve_action(
            rule_id="UNMAPPED_RULE",
            finding_code="UNMAPPED_CODE",
            severity="WARNING",
        )
        assert action3_warn == DecisionAction.REVIEW

        action3_info = config.resolve_action(
            rule_id="UNMAPPED_RULE",
            finding_code="UNMAPPED_CODE",
            severity="INFO",
        )
        assert action3_info == DecisionAction.IGNORE


class TestExplanationSanitization:
    """Verifies that persisted reasons and recommendations do not leak sensitive or raw inputs."""

    def test_account_holder_name_mismatch_sanitized(self):
        """Account holder mismatch explanation must be generic and not leak raw submitted strings."""
        raw_message = (
            "Bank account holder name ('Confidential Parent Holdings LLC') "
            "does not appear to match legal company name ('Secret Subsidiary Inc')."
        )
        finding = ValidationFinding(
            rule_id="CONST_ACCOUNT_HOLDER_MATCH",
            field="bank_account_holder_name",
            severity=Severity.WARNING,
            status="FAILED",
            code="ACCOUNT_HOLDER_NAME_MISMATCH",
            message=raw_message,
        )

        reason = map_finding_to_decision_reason(finding, DecisionAction.REVIEW)
        assert reason.code == "ACCOUNT_HOLDER_NAME_MISMATCH"
        assert reason.explanation == (
            "The bank account holder name does not sufficiently match "
            "the registered company or trade name."
        )
        assert "Confidential Parent Holdings LLC" not in reason.explanation
        assert "Secret Subsidiary Inc" not in reason.explanation

        rec = map_finding_to_recommendation(finding, DecisionAction.REVIEW)
        assert rec is not None
        assert rec.action == "VERIFY_ACCOUNT_HOLDER"
        assert "Confidential" not in rec.description

    def test_dummy_bank_account_sanitized(self):
        """Dummy bank account sequence reason must not leak digits."""
        finding = ValidationFinding(
            rule_id="FMT_BANK_ACCOUNT_STRUCTURAL",
            field="bank_account_number",
            severity=Severity.ERROR,
            status="FAILED",
            code="DUMMY_ACCOUNT_SEQUENCE",
            message="Bank account number appears to be an invalid placeholder sequence (repeated single digit).",
        )

        reason = map_finding_to_decision_reason(finding, DecisionAction.BLOCK)
        assert "placeholder" in reason.explanation.lower()
        rec = map_finding_to_recommendation(finding, DecisionAction.BLOCK)
        assert rec is not None
        assert rec.action == "PROVIDE_GENUINE_ACCOUNT_NUMBER"


class TestDecisionEngineMapping:
    """Tests deterministic mapping from ValidationResult to DecisionResult."""

    def test_fully_valid_vendor_evaluates_to_approved(
        self, clean_decision_engine: DecisionEngine, mock_validation_passed: ValidationResult
    ):
        """A clean validation result with 0 findings must produce an APPROVED decision."""
        result = clean_decision_engine.evaluate(
            validation_result=mock_validation_passed,
            vendor_id="vendor-123",
        )

        assert result.status == DecisionStatus.APPROVED
        assert result.decision_version == "1.0.0"
        assert result.ruleset_version == "1.0.0"
        assert result.validation_id == "val-clean-001"
        assert result.validation_status == "PASSED"
        assert "DETERMINISTIC_RULES_PASSED" in result.reason_codes
        assert len(result.reasons) >= 1
        assert result.reasons[0].code == "DETERMINISTIC_RULES_PASSED"
        assert any(rec.action == "PROCEED_WITH_ONBOARDING" for rec in result.recommendations)

    def test_warning_requiring_review_evaluates_to_pending(
        self, clean_decision_engine: DecisionEngine
    ):
        """A review-level warning (e.g., account holder mismatch) must evaluate to PENDING."""
        warning_finding = ValidationFinding(
            rule_id="CONST_ACCOUNT_HOLDER_MATCH",
            field="bank_account_holder_name",
            severity=Severity.WARNING,
            status="FAILED",
            code="ACCOUNT_HOLDER_NAME_MISMATCH",
            message="Account holder name 'XYZ Holding' differs from legal entity name 'Acme Corp'.",
            suggestion="Verify DBA or parent company relationship.",
        )

        val_result = ValidationResult(
            validation_id="val-warn-001",
            vendor_id="vendor-123",
            status="PASSED_WITH_WARNINGS",
            valid=True,
            summary=ValidationSummary(total_checks=28, passed=27, failed=0, warnings=1, info=0),
            findings=[warning_finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(
            validation_result=val_result,
            vendor_id="vendor-123",
        )

        assert result.status == DecisionStatus.PENDING
        assert "ACCOUNT_HOLDER_NAME_MISMATCH" in result.reason_codes
        assert len(result.reasons) == 1
        assert result.reasons[0].title == "Bank Account Holder Name Requires Review"
        assert any(rec.action == "VERIFY_ACCOUNT_HOLDER" for rec in result.recommendations)

    def test_configured_blocking_error_evaluates_to_rejected(
        self, clean_decision_engine: DecisionEngine
    ):
        """A blocking error finding (e.g., invalid GSTIN) must evaluate to REJECTED."""
        blocking_finding = ValidationFinding(
            rule_id="FMT_TAX_ID_SYNTAX",
            field="tax_id_number",
            severity=Severity.ERROR,
            status="FAILED",
            code="INVALID_GSTIN_FORMAT",
            message="GSTIN format is invalid.",
            suggestion="Provide valid 15-character GSTIN.",
        )

        val_result = ValidationResult(
            validation_id="val-err-001",
            vendor_id="vendor-123",
            status="FAILED",
            valid=False,
            summary=ValidationSummary(total_checks=28, passed=27, failed=1, warnings=0, info=0),
            findings=[blocking_finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(
            validation_result=val_result,
            vendor_id="vendor-123",
        )

        assert result.status == DecisionStatus.REJECTED
        assert "INVALID_GSTIN_FORMAT" in result.reason_codes
        assert len(result.reasons) == 1
        assert result.reasons[0].severity == "ERROR"
        assert any(rec.action == "VERIFY_TAX_REGISTRATION" for rec in result.recommendations)

    def test_cross_border_info_finding_does_not_block_approval(
        self, clean_decision_engine: DecisionEngine
    ):
        """Cross-border informational note (INFO) must not trigger PENDING or REJECTED."""
        info_finding = ValidationFinding(
            rule_id="CONST_CROSS_BORDER_REGISTRATION",
            field="address_country",
            severity=Severity.INFO,
            status="FAILED",
            code="CROSS_BORDER_OPERATIONS_NOTE",
            message="Cross-border operations: Incorporated in India, operating address in US.",
            suggestion="Ensure foreign authorization documents are ready.",
        )

        val_result = ValidationResult(
            validation_id="val-info-001",
            vendor_id="vendor-123",
            status="PASSED",
            valid=True,
            summary=ValidationSummary(total_checks=28, passed=27, failed=0, warnings=0, info=1),
            findings=[info_finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(
            validation_result=val_result,
            vendor_id="vendor-123",
        )

        # Cross-border note is mapped to IGNORE, so outcome must remain APPROVED
        assert result.status == DecisionStatus.APPROVED
        assert "DETERMINISTIC_RULES_PASSED" in result.reason_codes
        assert "CROSS_BORDER_OPERATIONS_NOTE" in result.reason_codes

    def test_custom_action_overrides_block_review_ignore(self):
        """Test fine-grained configuration overrides for rule and finding actions."""
        custom_config = DecisionConfig(
            rule_actions={"CUSTOM_RULE": DecisionAction.BLOCK},
            finding_code_actions={
                "MILD_WARNING": DecisionAction.IGNORE,
                "SPECIAL_ERROR": DecisionAction.REVIEW,
            },
        )
        engine = DecisionEngine(default_config=custom_config)

        # 1. SPECIAL_ERROR mapped to REVIEW -> PENDING instead of REJECTED
        special_finding = ValidationFinding(
            rule_id="SOME_RULE",
            field="field_a",
            severity=Severity.ERROR,
            status="FAILED",
            code="SPECIAL_ERROR",
            message="Special error downgraded to review.",
        )
        val_result1 = ValidationResult(
            validation_id="v1",
            vendor_id="v",
            status="FAILED",
            valid=False,
            summary=ValidationSummary(total_checks=1, passed=0, failed=1, warnings=0, info=0),
            findings=[special_finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )
        res1 = engine.evaluate(val_result1, vendor_id="v")
        assert res1.status == DecisionStatus.PENDING

        # 2. MILD_WARNING mapped to IGNORE -> APPROVED
        mild_finding = ValidationFinding(
            rule_id="SOME_RULE",
            field="field_b",
            severity=Severity.WARNING,
            status="FAILED",
            code="MILD_WARNING",
            message="Mild warning ignored.",
        )
        val_result2 = ValidationResult(
            validation_id="v2",
            vendor_id="v",
            status="PASSED_WITH_WARNINGS",
            valid=True,
            summary=ValidationSummary(total_checks=1, passed=0, failed=0, warnings=1, info=0),
            findings=[mild_finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )
        res2 = engine.evaluate(val_result2, vendor_id="v")
        assert res2.status == DecisionStatus.APPROVED

    def test_deterministic_ordering_of_reasons_and_recommendations(
        self, clean_decision_engine: DecisionEngine
    ):
        """Reasons must be sorted deterministically (ERROR first, then WARNING, then INFO)."""
        finding_warn = ValidationFinding(
            rule_id="CONST_TAX_TYPE_COUNTRY",
            field="tax_id_type",
            severity=Severity.WARNING,
            status="FAILED",
            code="TAX_TYPE_COUNTRY_MISMATCH",
            message="Tax scheme mismatch.",
        )
        finding_err = ValidationFinding(
            rule_id="FMT_EMAIL_STRUCTURE",
            field="contact_email",
            severity=Severity.ERROR,
            status="FAILED",
            code="INVALID_EMAIL_FORMAT",
            message="Email format invalid.",
        )
        finding_info = ValidationFinding(
            rule_id="CONST_CROSS_BORDER_REGISTRATION",
            field="address_country",
            severity=Severity.INFO,
            status="FAILED",
            code="CROSS_BORDER_OPERATIONS_NOTE",
            message="Cross-border note.",
        )

        val_result = ValidationResult(
            validation_id="v-order",
            vendor_id="v",
            status="FAILED",
            valid=False,
            summary=ValidationSummary(total_checks=3, passed=0, failed=1, warnings=1, info=1),
            findings=[finding_info, finding_warn, finding_err],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(val_result, vendor_id="v")

        assert result.status == DecisionStatus.REJECTED
        # Severities in sorted order: ERROR, WARNING, INFO
        severities = [r.severity for r in result.reasons]
        assert severities == ["ERROR", "WARNING", "INFO"]

    def test_sensitive_banking_data_never_leaked_in_decision(
        self, clean_decision_engine: DecisionEngine
    ):
        """Decision reasons, recommendations, and snapshot must never contain raw account numbers."""
        dummy_account_finding = ValidationFinding(
            rule_id="FMT_BANK_ACCOUNT_STRUCTURAL",
            field="bank_account_number",
            severity=Severity.ERROR,
            status="FAILED",
            code="DUMMY_ACCOUNT_SEQUENCE",
            message="Bank account number appears to be an invalid placeholder sequence (repeated single digit).",
            suggestion="Provide the legitimate, active commercial bank account number.",
        )

        val_result = ValidationResult(
            validation_id="val-sec-001",
            vendor_id="vendor-sec",
            status="FAILED",
            valid=False,
            summary=ValidationSummary(total_checks=28, passed=27, failed=1, warnings=0, info=0),
            findings=[dummy_account_finding],
            validated_at=datetime.now(timezone.utc),
            ruleset_version="1.0.0",
        )

        result = clean_decision_engine.evaluate(val_result, vendor_id="vendor-sec")

        # Verify no digits from raw accounts appear in reason or recommendation text
        result_json_str = result.model_dump_json()
        assert "11111111" not in result_json_str
        assert "50200012345678" not in result_json_str
        for rec in result.recommendations:
            assert rec.action == "PROVIDE_GENUINE_ACCOUNT_NUMBER"
            assert "bank account number" in rec.description.lower()
