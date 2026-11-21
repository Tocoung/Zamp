"""Deterministic, explainable document classification engine."""

import re
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

from app.schemas.classification import (
    ClassificationStatus,
    ClassificationLimitationCode,
)
from app.classification.text_extractor import extract_document_text
from app.classification.rules import (
    CATEGORY_STRONG_HEADINGS,
    CATEGORY_CONTEXT_KEYWORDS,
    CATEGORY_FILENAME_SIGNALS,
)
from app.classification.privacy import sanitize_evidence_dict


CLASSIFIER_VERSION = "1.0.0"


@dataclass
class ClassificationResult:
    """Internal structured result produced by the ClassificationEngine.
    
    Attributes:
        predicted_category: Category name or 'UNKNOWN'.
        status: Operational classification status enum.
        confidence_score: Rule-based heuristic match score [0.0 - 1.0].
            Reflects keyword and heading match strength; not a statistical probability
            or guarantee of authenticity.
        evidence: Sanitized dictionary of explainability signals.
        limitation_code: Explanation code if unclassified or ambiguous.
        classifier_version: Engine implementation version string.
    """
    predicted_category: str
    status: ClassificationStatus
    confidence_score: float
    evidence: Dict[str, Any]
    limitation_code: Optional[str]
    classifier_version: str = CLASSIFIER_VERSION


class ClassificationEngine:
    """Deterministic, explainable classification engine evaluating extracted text and signals.
    
    Evaluates rule-based heading patterns and contextual keywords against extractable digital text.
    Filename signals are strictly auxiliary: filename alone can never produce a CLASSIFIED status
    or determine category without verified content signals.
    """

    def __init__(self, version: str = CLASSIFIER_VERSION):
        self.version = version

    def classify(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> ClassificationResult:
        """Classifies a document blob based on its extractable text and explainable signals.
        
        Args:
            content: Raw plaintext file bytes.
            filename: Sanitized original filename.
            mime_type: Canonical MIME type.
            
        Returns:
            ClassificationResult containing status, predicted category, heuristic match score,
            and sanitized privacy-hardened evidence.
        """
        # 1. Extract digital text (bounded, safe)
        text, is_extractable, limitation = extract_document_text(content=content, mime_type=mime_type)

        # 2. Check for non-extractable text (images or scanned textless PDFs)
        # Requirement: An unreadable or image-only document must remain INSUFFICIENT_TEXT
        # regardless of filename.
        if not is_extractable:
            empty_evidence = sanitize_evidence_dict({
                "matched_headings": [],
                "matched_keywords": [],
                "signals_by_category": {cat: 0.0 for cat in CATEGORY_STRONG_HEADINGS},
                "secondary_filename_signals": [],
                "text_length_chars": 0,
            })
            return ClassificationResult(
                predicted_category="UNKNOWN",
                status=ClassificationStatus.INSUFFICIENT_TEXT,
                confidence_score=0.0,
                evidence=empty_evidence,
                limitation_code=limitation or ClassificationLimitationCode.NO_EXTRACTABLE_TEXT.value,
                classifier_version=self.version,
            )

        # 3. Score categories against extracted text
        text_lower = text.lower()
        filename_lower = str(filename or "").lower()

        category_scores: Dict[str, float] = {}
        category_evidence: Dict[str, Dict[str, List[str]]] = {}

        for category, headings in CATEGORY_STRONG_HEADINGS.items():
            matched_headings = [h for h in headings if h in text_lower]
            context_keywords = CATEGORY_CONTEXT_KEYWORDS.get(category, [])
            matched_keywords = [k for k in context_keywords if re.search(r"\b" + re.escape(k) + r"\b", text_lower)]
            
            # Filename signals are minor secondary evidence only
            filename_tokens = CATEGORY_FILENAME_SIGNALS.get(category, [])
            matched_filenames = [f for f in filename_tokens if f in filename_lower]

            # Calculate deterministic weighted components
            heading_score = min(0.70, len(matched_headings) * 0.45)
            keyword_score = min(0.40, len(matched_keywords) * 0.12)

            # Requirement: Filename alone must never produce category signals or classification.
            # If there are zero content signals (no headings and no context keywords),
            # filename score is zeroed out.
            if len(matched_headings) == 0 and len(matched_keywords) == 0:
                filename_score = 0.0
                matched_filenames = []
            else:
                # Auxiliary bonus when content already has matching signals
                filename_score = min(0.08, len(matched_filenames) * 0.08)

            total_score = min(1.0, heading_score + keyword_score + filename_score)
            category_scores[category] = round(total_score, 2)
            category_evidence[category] = {
                "matched_headings": matched_headings,
                "matched_keywords": matched_keywords,
                "secondary_filename_signals": matched_filenames,
            }

        # 4. Rank categories
        ranked = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
        top_category, top_score = ranked[0]
        runner_up_category, runner_up_score = ranked[1] if len(ranked) > 1 else ("UNKNOWN", 0.0)

        top_ev = category_evidence.get(top_category, {
            "matched_headings": [],
            "matched_keywords": [],
            "secondary_filename_signals": [],
        })

        base_evidence = sanitize_evidence_dict({
            "matched_headings": top_ev["matched_headings"],
            "matched_keywords": top_ev["matched_keywords"],
            "signals_by_category": category_scores,
            "secondary_filename_signals": top_ev["secondary_filename_signals"],
            "text_length_chars": len(text),
        })

        # 5. Evaluate thresholds, ambiguity, and content-driven requirements
        # Requirement: Filename alone must never produce CLASSIFIED status.
        # If content has no headings and no keywords for the top category, remain UNKNOWN.
        if len(top_ev["matched_headings"]) == 0 and len(top_ev["matched_keywords"]) == 0:
            return ClassificationResult(
                predicted_category="UNKNOWN",
                status=ClassificationStatus.LOW_CONFIDENCE,
                confidence_score=0.0,
                evidence=base_evidence,
                limitation_code=ClassificationLimitationCode.INSUFFICIENT_EVIDENCE.value,
                classifier_version=self.version,
            )

        # Case A: Insufficient evidence (all scores below threshold 0.40)
        if top_score < 0.40:
            return ClassificationResult(
                predicted_category="UNKNOWN",
                status=ClassificationStatus.LOW_CONFIDENCE,
                confidence_score=top_score,
                evidence=base_evidence,
                limitation_code=ClassificationLimitationCode.INSUFFICIENT_EVIDENCE.value,
                classifier_version=self.version,
            )

        # Case B: Conflicting signals (top two categories are close competitors)
        if runner_up_score >= 0.35 and (top_score - runner_up_score) < 0.15:
            return ClassificationResult(
                predicted_category="UNKNOWN",
                status=ClassificationStatus.LOW_CONFIDENCE,
                confidence_score=top_score,
                evidence=base_evidence,
                limitation_code=ClassificationLimitationCode.CONFLICTING_SIGNALS.value,
                classifier_version=self.version,
            )

        # Case C: Confident classification (high score >= 0.70 and clear lead >= 0.18)
        # Must have verified content signals (at least one heading or strong keywords)
        has_content_signals = len(top_ev["matched_headings"]) > 0 or len(top_ev["matched_keywords"]) >= 2
        if top_score >= 0.70 and (top_score - runner_up_score) >= 0.18 and has_content_signals:
            return ClassificationResult(
                predicted_category=top_category,
                status=ClassificationStatus.CLASSIFIED,
                confidence_score=top_score,
                evidence=base_evidence,
                limitation_code=None,
                classifier_version=self.version,
            )

        # Case D: Moderate score (some signal, but below confident threshold)
        return ClassificationResult(
            predicted_category=top_category,
            status=ClassificationStatus.LOW_CONFIDENCE,
            confidence_score=top_score,
            evidence=base_evidence,
            limitation_code=ClassificationLimitationCode.INSUFFICIENT_EVIDENCE.value,
            classifier_version=self.version,
        )


# Singleton classification engine instance
classification_engine = ClassificationEngine()
