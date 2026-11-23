"""Deterministic rule-based similarity algorithms for fuzzy cross-document matching."""

import re
from typing import Dict, List, Optional, Set, Tuple


def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes standard Levenshtein edit distance between two strings using dynamic programming."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row[j + 1] = min(insertions, deletions, substitutions)
        prev_row = curr_row

    return prev_row[-1]


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Computes normalized similarity ratio based on Levenshtein distance [0.0 - 1.0]."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(s1, s2)
    return max(0.0, 1.0 - (dist / max_len))


def token_jaccard_similarity(s1: str, s2: str) -> float:
    """Calculates Jaccard similarity coefficient of word tokens [0.0 - 1.0]."""
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def token_sort_ratio(s1: str, s2: str) -> float:
    """Calculates similarity after sorting constituent word tokens alphabetically."""
    sorted1 = " ".join(sorted(s1.split()))
    sorted2 = " ".join(sorted(s2.split()))
    return levenshtein_ratio(sorted1, sorted2)


def compute_company_name_similarity(norm_name1: str, norm_name2: str) -> float:
    """Computes transparent, deterministic similarity score between two normalized company names.
    
    Returns a score between 0.0 and 1.0:
    - 1.0: Exact match after canonical normalization.
    - >= 0.88: Close match (minor spelling, token ordering, or formatting difference).
    - 0.70 - 0.87: Potential discrepancy (significant word overlap but differing tokens).
    - < 0.70: Confirmed mismatch / unrelated entities.
    """
    if not norm_name1 or not norm_name2:
        return 0.0
    if norm_name1 == norm_name2:
        return 1.0

    direct_ratio = levenshtein_ratio(norm_name1, norm_name2)
    sorted_ratio = token_sort_ratio(norm_name1, norm_name2)
    jaccard = token_jaccard_similarity(norm_name1, norm_name2)

    # Weighted composite: give high weight to sorted tokens and direct character edit ratio
    composite = max(
        direct_ratio,
        sorted_ratio,
        0.5 * sorted_ratio + 0.3 * jaccard + 0.2 * direct_ratio,
    )
    return round(composite, 4)


def compute_address_similarity(
    norm_addr1: str,
    norm_addr2: str,
    postal_code1: Optional[str] = None,
    postal_code2: Optional[str] = None,
    city1: Optional[str] = None,
    city2: Optional[str] = None,
) -> Tuple[float, Optional[str]]:
    """Conservative address comparison evaluating structural components and text similarity.
    
    Returns:
        (similarity_score, conflict_reason)
        
    Safety invariant:
    If postal codes or cities are both present and clearly conflict, the similarity score is
    penalized and a conflict reason is returned, preventing superficial high text similarity
    from declaring two different locations as matching.
    """
    if not norm_addr1 or not norm_addr2:
        return 0.0, "One or both address values are empty"

    if norm_addr1 == norm_addr2:
        return 1.0, None

    # Check for hard postal code conflict
    if postal_code1 and postal_code2:
        p1 = re.sub(r"[^\d]", "", postal_code1)
        p2 = re.sub(r"[^\d]", "", postal_code2)
        if p1 and p2 and p1 != p2:
            return 0.25, f"Postal code mismatch: '{postal_code1}' vs '{postal_code2}'"

    # Check for hard city conflict
    if city1 and city2:
        c1 = re.sub(r"[^a-z]", "", city1.lower())
        c2 = re.sub(r"[^a-z]", "", city2.lower())
        if c1 and c2 and c1 != c2:
            c_sim = levenshtein_ratio(c1, c2)
            if c_sim < 0.70:
                return 0.35, f"City mismatch: '{city1}' vs '{city2}'"

    # Text token similarity
    jaccard = token_jaccard_similarity(norm_addr1, norm_addr2)
    sorted_ratio = token_sort_ratio(norm_addr1, norm_addr2)
    composite = max(sorted_ratio, 0.6 * jaccard + 0.4 * sorted_ratio)

    return round(composite, 4), None


# Alias for convenience
evaluate_address_similarity = compute_address_similarity
