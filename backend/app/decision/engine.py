"""Deterministic, explainable decision engine orchestrator."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from app.decision.models import (
    DecisionAction,
    DecisionReason,
    DecisionRecommendation,
    DecisionResult,
    DecisionStatus,
)
from app.decision.config import DecisionConfig
from app.decision.rules import (
    map_finding_to_decision_reason,
    map_finding_to_recommendation,
)
from app.validation.models import ValidationResult, ValidationFinding


class DecisionEngine:
    """Orchestrates deterministic onboarding decision calculation from validation evidence."""

    def __init__(self, default_config: Optional[DecisionConfig] = None):
        self.config = default_config or DecisionConfig()

    def evaluate(
        self,
        validation_result: ValidationResult,
        vendor_id: str,
        vendor_data: Optional[Dict[str, Any]] = None,
        config: Optional[DecisionConfig] = None,
    ) -> DecisionResult:
        """Computes a deterministic DecisionResult from a ValidationResult.
        
        Args:
            validation_result: The validation engine result (consumed, not duplicated).
            vendor_id: Target vendor UUID.
            vendor_data: Optional vendor attributes for contextual evaluation.
            config: Optional configuration override.
            
        Returns:
            Structured DecisionResult with APPROVED, PENDING, or REJECTED status,
            along with explainable reason codes, reasons, and recommendations.
        """
        active_config = config or self.config
        decision_id = str(uuid.uuid4())

        blocking_reasons: List[DecisionReason] = []
        review_reasons: List[DecisionReason] = []
        informational_reasons: List[DecisionReason] = []

        recommendations_map: Dict[str, DecisionRecommendation] = {}

        # 1. Evaluate all validation findings deterministically
        for finding in validation_result.findings:
            action = active_config.resolve_action(
                rule_id=finding.rule_id,
                finding_code=finding.code,
                severity=finding.severity,
            )

            reason = map_finding_to_decision_reason(finding, action)
            recommendation = map_finding_to_recommendation(finding, action)

            if action == DecisionAction.BLOCK:
                blocking_reasons.append(reason)
                if recommendation and recommendation.action not in recommendations_map:
                    recommendations_map[recommendation.action] = recommendation
            elif action == DecisionAction.REVIEW:
                review_reasons.append(reason)
                if recommendation and recommendation.action not in recommendations_map:
                    recommendations_map[recommendation.action] = recommendation
            else:  # DecisionAction.IGNORE
                informational_reasons.append(reason)
                # Informational items usually don't need action unless explicit

        # 2. Determine final DecisionStatus
        if blocking_reasons:
            status = DecisionStatus.REJECTED
            all_reasons = blocking_reasons + review_reasons + informational_reasons
        elif review_reasons:
            status = DecisionStatus.PENDING
            all_reasons = review_reasons + informational_reasons
        else:
            status = DecisionStatus.APPROVED
            # Add positive approval explanation
            approval_reason = DecisionReason(
                code="DETERMINISTIC_RULES_PASSED",
                title="All Deterministic Validation Rules Satisfied",
                explanation="Vendor data successfully satisfied all mandatory fields, statutory formats, and consistency rules without blocking issues.",
                source_rule_id=None,
                source_finding_code=None,
                severity="INFO",
            )
            all_reasons = [approval_reason] + informational_reasons

            # Positive operational recommendation
            recommendations_map["PROCEED_WITH_ONBOARDING"] = DecisionRecommendation(
                action="PROCEED_WITH_ONBOARDING",
                description="Vendor record satisfies all configured deterministic onboarding rules. Proceed with operational setup.",
                priority="LOW",
            )

        # 3. Deterministic ordering of reason codes, reasons, and recommendations
        severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        all_reasons.sort(
            key=lambda r: (severity_order.get(r.severity, 3), r.code, r.source_rule_id or "")
        )

        reason_codes: List[str] = []
        seen_codes: Set[str] = set()
        for r in all_reasons:
            if r.code not in seen_codes:
                seen_codes.add(r.code)
                reason_codes.append(r.code)

        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        recommendations = list(recommendations_map.values())
        recommendations.sort(
            key=lambda rec: (priority_order.get(rec.priority, 3), rec.action)
        )

        # 4. Generate sanitized validation snapshot (strictly no raw bank numbers)
        sanitized_findings = [
            {
                "rule_id": f.rule_id,
                "field": f.field,
                "severity": f.severity,
                "code": f.code,
                "message": f.message,
                "suggestion": f.suggestion,
            }
            for f in validation_result.findings
        ]

        validation_snapshot = {
            "validation_id": validation_result.validation_id,
            "validation_status": validation_result.status,
            "ruleset_version": validation_result.ruleset_version,
            "validated_at": validation_result.validated_at.isoformat(),
            "summary": validation_result.summary.model_dump(),
            "findings": sanitized_findings,
        }

        return DecisionResult(
            decision_id=decision_id,
            vendor_id=vendor_id,
            status=status,
            decision_version=active_config.decision_version,
            ruleset_version=validation_result.ruleset_version,
            validation_id=validation_result.validation_id,
            validation_status=validation_result.status,
            reason_codes=reason_codes,
            reasons=all_reasons,
            recommendations=recommendations,
            validation_snapshot=validation_snapshot,
            decided_at=datetime.now(timezone.utc),
        )
