"""
Output safety validator — runs on converted training examples
before they enter the filtered dataset.

This is a post-conversion check that catches cases where the converter
produced an example that reads as operational attack assistance despite
the safety-aware system prompt.

Works alongside the LM quality filter, not instead of it.
"""
from __future__ import annotations

import re

# Phrases that suggest the output is operational attack assistance
# rather than educational security content.
# Conservative list — only clear-cut cases.
OPERATIONAL_OUTPUT_PATTERNS = [
    # Specific target + attack instruction pattern
    r"(?:to attack|to compromise|to exploit)\s+(?:the\s+)?\w+(?:\.com|\.org|\.gov|\.net|\.io)",
    # Step-by-step attack on a named real host
    r"(?:step \d+|first,|then,|next,|finally,).*(?:the target|their server|the victim)",
    # Ransom note templates
    r"your files have been (?:encrypted|locked).*bitcoin",
    # Doxxing instructions
    r"(?:find|locate|get)\s+(?:their|his|her)\s+(?:home address|real name|personal info|phone number)",
]

# Phrases that are explicitly good — indicate proper educational framing
GOOD_FRAMING_PATTERNS = [
    r"(?:authorized|authorized penetration|authorized testing|authorized environment)",
    r"(?:ctf|capture the flag|lab environment|test environment|practice environment)",
    r"(?:defensive|blue team|detection|mitigation|prevention|remediation)",
    r"(?:research|academic|educational|learning|understanding)",
    r"(?:vulnerability class|attack technique|exploitation method)",
]

_bad_compiled  = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in OPERATIONAL_OUTPUT_PATTERNS]
_good_compiled = [re.compile(p, re.IGNORECASE) for p in GOOD_FRAMING_PATTERNS]


def validate_example(example: dict) -> tuple[bool, str]:
    """
    Validate a converted training example.

    Returns (keep: bool, reason: str)
    """
    instruction = example.get("instruction", "")
    output      = example.get("output", "")
    full_text   = instruction + " " + output

    # Check for operational attack patterns in the output
    for pattern in _bad_compiled:
        if pattern.search(output):
            # Only block if there's no redemptive educational framing
            has_good_framing = any(p.search(full_text) for p in _good_compiled)
            if not has_good_framing:
                return False, "operational_output_no_educational_framing"

    return True, "ok"


def validate_batch(examples: list) -> tuple[list, list]:
    """
    Split a batch into kept and rejected examples.
    Returns (kept, rejected_with_reasons).
    """
    kept     = []
    rejected = []
    for ex in examples:
        ok, reason = validate_example(ex)
        if ok:
            kept.append(ex)
        else:
            rejected.append({**ex, "_reject_reason": reason})
    return kept, rejected
