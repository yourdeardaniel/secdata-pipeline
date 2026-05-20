"""
Output safety validator — runs on converted training examples
before they enter the filtered dataset.

This is Layer 2 of the three-layer safety architecture documented in SAFETY.md.
It is a post-conversion check that catches cases where the converter produced
an example that reads as operational attack assistance despite Layer 1
(the safety-aware system prompt).

Design principles:

  1. Conservative bias. The cost of a false positive (rejecting a good example)
     is one lost training pair out of millions. The cost of a false negative
     (operational attack content in a public dataset) is far higher. When
     uncertain, reject.

  2. Transparent patterns. All patterns are regex defined in source. They can
     be inspected, audited, critiqued, and improved by anyone reading the code.
     This is intentional — unlike an ML safety classifier, the criteria are
     explicit.

  3. Tiered severity. Some categories always reject (no amount of educational
     framing redeems CSAM-related patterns or WMD synthesis). Others reject
     unless offsetting good-framing indicators are present.

  4. Per-category reasons. Every rejection produces a specific reason string,
     enabling later analysis of what the validator is catching and tuning of
     individual patterns.

  5. Conservative good-framing recognition. Good-framing indicators must be
     specific (CTF, authorized engagement, vulnerability class, blue team) —
     not generic words like "research" or "security" that anything could match.

This validator runs after every conversion. Rejected examples are logged with
their rejection reason for review. A summary of rejection counts by category
is printed at the end of the run.
"""
from __future__ import annotations

import re
from typing import Tuple, List, Dict


# =====================================================================
# TIER 1 — ALWAYS REJECT
# These patterns describe content that no educational framing can redeem.
# =====================================================================

TIER_1_HARD_BLOCK_PATTERNS: Dict[str, List[str]] = {
    # CSAM / sexual content involving minors — zero tolerance.
    # Patterns intentionally broad. False positives here are entirely acceptable.
    "csam_indicator": [
        r"\b(?:sexual|sexually|erotic|naked|nude|porn)\b.{0,40}\b(?:child|children|minor|minors|underage|teen|teens|kid|kids|infant|toddler|baby|babies|girl|boy|preteen|adolescent)\b",
        r"\b(?:child|children|minor|minors|underage|teen|teens|kid|kids|infant|toddler|baby|babies|preteen|adolescent)\b.{0,40}\b(?:sexual|sexually|erotic|naked|nude|porn)\b",
        r"\bcsam\b",
        r"\bchild\s+(?:sexual|sex|porn)\b",
        r"\bcp\s*(?:material|content|images?|videos?)\b",
    ],

    # Weapons of mass destruction — synthesis routes, dispersal mechanisms.
    # Unlikely to appear in security data but possible from academic sources.
    "wmd_synthesis": [
        r"\b(?:synthesize|synthesis of|manufacture|produce|create)\b.{0,100}\b(?:sarin|vx nerve|tabun|soman|novichok|mustard gas|chlorine gas|hydrogen cyanide)\b",
        r"\b(?:enrich|enriching|enrichment of)\b.{0,30}\b(?:uranium|plutonium)\b.{0,100}\b(?:weapon|bomb|device)\b",
        r"\b(?:weaponize|weaponizing|weaponization of)\b.{0,30}\b(?:anthrax|smallpox|plague|ebola|botulinum|ricin)\b",
        r"\b(?:dirty bomb|radiological dispersal device)\b.{0,100}\b(?:construct|build|assemble|build a|how to)\b",
    ],

    # Explicit ransomware templates — operational extortion language with payment demand.
    "ransom_template": [
        r"\byour files (?:have been |are )?(?:encrypted|locked).{0,200}\b(?:bitcoin|btc|monero|xmr|ethereum|eth)\b",
        r"\b(?:pay|send|transfer)\b.{0,30}\b(?:bitcoin|btc|monero|xmr)\b.{0,200}\b(?:decrypt|unlock|restore|recover)\b.{0,30}\b(?:files|data)\b",
        r"\bdeadline\b.{0,40}\b(?:double|increase|destroy|delete|leak)\b.{0,100}\b(?:files|data|ransom|payment)\b",
    ],

    # CSAM-adjacent grooming language
    "grooming_pattern": [
        r"\b(?:groom|grooming|target)\b.{0,30}\b(?:child|minor|underage|kid)\b.{0,100}\b(?:online|chat|message|contact)\b",
    ],
}


# =====================================================================
# TIER 2 — REJECT UNLESS GOOD-FRAMING PRESENT
# These patterns describe content that is concerning but can sometimes be
# legitimate in CTF, authorized testing, or defensive analysis contexts.
# Requires explicit good-framing indicators to be retained.
# =====================================================================

TIER_2_REDEEMABLE_PATTERNS: Dict[str, List[str]] = {

    # Attack instructions targeting real-world domains/sites/IPs by name.
    "named_real_target_attack": [
        # "attack/exploit/compromise [domain]"
        r"\b(?:to attack|to compromise|to exploit|to hack|attacking|compromising|exploiting|hacking)\b\s+(?:the\s+)?(?:[\w-]+\.)+(?:com|org|gov|net|io|edu|mil|co|us|uk|de|fr|cn|ru|jp|kr|in)\b",
        # "target's domain" or "victim's server" with specifics
        r"\b(?:the\s+)?(?:target's|victim's|their)\s+(?:server|api|website|domain|infrastructure|systems?|network|database)\b.{0,80}\b(?:exploit|attack|compromise|breach|infiltrate|brute[ -]?force|inject)\b",
        # Specific public IP attack
        r"\b(?:attack|exploit|compromise|target)\b.{0,40}\b(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b",
    ],

    # Sequential/multi-step attacks on named real victims (not labs or CTFs)
    "stepwise_attack_real_target": [
        r"\b(?:step\s*\d+|first\s*[,:]|then\s*[,:]|next\s*[,:]|finally\s*[,:]|after that\s*[,:])\b.{0,200}\b(?:the target|their server|the victim|the company|the organization|the user's account)\b",
        r"\bonce you have access\b.{0,200}\b(?:exfiltrate|extract|steal|destroy|delete|wipe)\b",
    ],

    # Doxxing / personal-info gathering against named individuals
    "doxxing_pattern": [
        r"\b(?:find|locate|get|obtain|discover|retrieve)\b\s+(?:their|his|her|the target's|the victim's)\s+(?:home address|residential address|phone number|real name|legal name|personal info|personal information|family members|social security|ssn)\b",
        r"\b(?:track|stalk|surveil|monitor|follow)\b\s+(?:their|his|her|the target's|the victim's)\s+(?:location|whereabouts|movements|daily routine)\b",
        r"\bdox(?:xing|x)?\b.{0,40}\b(?:them|him|her|the target|the victim)\b",
    ],

    # Credential harvesting / phishing aimed at real named companies/services
    "phishing_real_target": [
        r"\b(?:phish|phishing|spear[ -]?phish(?:ing)?|credential harvest(?:ing)?)\b\s+(?:against|targeting|aimed at)\s+(?:[\w-]+\.)+(?:com|org|gov|net|io|edu)\b",
        r"\bclone(?:d)?\s+(?:the\s+)?(?:gmail|outlook|microsoft 365|office 365|okta|google workspace|github|gitlab|aws|azure|salesforce|slack|zoom)\s+login\b",
    ],

    # Operational malware deployment against real systems
    "operational_malware_deployment": [
        r"\b(?:deploy|install|execute|run|drop)\b\s+(?:the\s+)?(?:malware|payload|implant|backdoor|rat|stealer|cryptominer|ransomware)\s+(?:on|to|against)\s+(?:their|the target's|the victim's|the company's)\b",
        r"\bestablish persistence\b.{0,100}\b(?:their|the target's|the victim's)\s+(?:host|system|network|workstation|server)\b",
    ],

    # Insider threat / sabotage instructions
    "insider_threat_sabotage": [
        r"\b(?:as an? (?:insider|employee|contractor|admin)|with insider access)\b.{0,200}\b(?:steal|exfiltrate|sabotage|destroy|leak|wipe|damage)\b",
        r"\b(?:before|right before)\b\s+(?:you\s+)?(?:quit|resign|leave|get fired)\b.{0,150}\b(?:steal|exfiltrate|copy|delete|destroy|wipe|sabotage)\b",
    ],

    # Financial fraud / account takeover instructions targeting real accounts
    "financial_fraud_real_target": [
        r"\b(?:drain|empty|steal from)\b\s+(?:their|his|her|the victim's|the target's)\s+(?:wallet|bank account|crypto account|exchange account)\b",
        r"\bsim\s*swap(?:ping)?\b.{0,100}\b(?:their|his|her|the target's|the victim's)\b",
        r"\bbypass\b.{0,40}\b(?:bank|2fa|two[- ]?factor|mfa)\b.{0,200}\b(?:their|the target's|the victim's|the user's)\s+account\b",
    ],

    # Critical infrastructure attack content (power, water, hospitals, transit)
    "critical_infrastructure_attack": [
        r"\b(?:attack|exploit|compromise|disable|disrupt|destroy)\b\s+(?:a\s+)?(?:power grid|electrical grid|water treatment|water supply|hospital|medical device|pacemaker|insulin pump|traffic light|air traffic|nuclear plant|nuclear reactor|dam control)\b",
    ],
}


# =====================================================================
# TIER 3 — FLAG FOR LOGGING (not rejected)
# These patterns indicate content that may be borderline. Not rejected,
# but logged so the user can review what's passing through and tune.
# =====================================================================

TIER_3_FLAG_PATTERNS: Dict[str, List[str]] = {
    "real_domain_in_text": [
        r"\b(?<!example\.)(?<!test\.)(?<!localhost\.)(?<!lab\.)(?<!ctf\.)(?:[a-z][\w-]*\.)+(?:com|org|net|io|gov|edu|mil)\b",
    ],
    "real_email_in_text": [
        r"\b(?!example@)(?!test@)(?!user@)(?!admin@example)[a-zA-Z0-9._%+-]+@(?!example\.)(?!test\.)(?!localhost)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
    ],
    "real_phone_in_text": [
        r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    ],
    "potential_pii_ssn": [
        r"\b\d{3}-\d{2}-\d{4}\b",
    ],
    "potential_pii_credit_card": [
        r"\b(?:\d{4}[- ]?){3}\d{4}\b",
    ],
}


# =====================================================================
# GOOD FRAMING — must be specific enough to actually indicate educational
# or authorized context, not just generic security vocabulary.
# =====================================================================

GOOD_FRAMING_PATTERNS: List[str] = [
    # Explicit authorization contexts
    r"\b(?:authorized (?:penetration test|pentest|engagement|assessment|red team|testing)|with (?:proper |written )?authorization|authorized environment|authorized assessment|legitimate engagement)\b",
    r"\b(?:scope of (?:the )?engagement|rules of engagement|engagement scope|customer-authorized|client-authorized)\b",

    # CTF / lab / sandbox / research environments
    r"\b(?:ctf|capture the flag|capture[- ]the[- ]flag|ctf challenge|ctf writeup|ctf walkthrough)\b",
    r"\b(?:lab environment|sandbox|test environment|staging environment|isolated environment|practice environment|training environment|research environment)\b",
    r"\b(?:hackthebox|tryhackme|vulnhub|picoctf|hack the box|over the wire)\b",

    # Defensive framing
    r"\b(?:defensive|blue team|defender|detection (?:engineer|engineering)|threat hunt(?:er|ing)?|incident response|forensic|forensics|soc analyst)\b",
    r"\b(?:detect|detection|mitigat(?:e|ion)|prevent(?:ion)?|remediat(?:e|ion)|harden(?:ing)?|patch|patching)\b\s+(?:this|the|such|these)\b",
    r"\b(?:what (?:to look for|defenders see)|how to detect|indicators of compromise|telemetry|logging|monitoring|alerting)\b",

    # Concept / class focus rather than operation focus
    r"\b(?:vulnerability class|class of (?:vulnerability|vulnerabilities|bug|bugs)|attack pattern|attack technique|exploitation technique|underlying (?:vulnerability|cause|weakness))\b",
    r"\b(?:root cause|why this works|why this is exploitable|conceptually|in principle|in general|broadly speaking)\b",

    # Research / academic
    r"\b(?:peer[- ]reviewed|academic (?:paper|research)|research paper|published research|prior work|literature)\b",

    # Educational
    r"\b(?:students? learn|learners? (?:will|should) understand|teaching|curriculum|coursework|learning outcome)\b",
    r"\b(?:to understand how|in order to understand|the goal is to understand|builds understanding)\b",

    # Historical / post-incident framing (not operational future-tense)
    r"\b(?:post[- ]incident|after the incident|root cause analysis|lessons learned|post-mortem|incident report)\b",
    r"\b(?:in (?:the )?(?:case of |incident at )|the \w+ breach of \d{4}|historically|previously documented)\b",
]


# =====================================================================
# Compile all patterns once at module load.
# =====================================================================

def _compile_dict(d: Dict[str, List[str]]) -> Dict[str, List[re.Pattern]]:
    return {
        category: [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]
        for category, patterns in d.items()
    }


_TIER_1_COMPILED = _compile_dict(TIER_1_HARD_BLOCK_PATTERNS)
_TIER_2_COMPILED = _compile_dict(TIER_2_REDEEMABLE_PATTERNS)
_TIER_3_COMPILED = _compile_dict(TIER_3_FLAG_PATTERNS)
_GOOD_COMPILED = [re.compile(p, re.IGNORECASE) for p in GOOD_FRAMING_PATTERNS]


# =====================================================================
# Public API
# =====================================================================

def has_good_framing(text: str) -> bool:
    """Check whether text contains specific educational/authorized framing."""
    return any(p.search(text) for p in _GOOD_COMPILED)


def check_tier_1(text: str) -> Tuple[bool, str]:
    """
    Check text against Tier 1 (always-reject) patterns.
    Returns (passed, reason). passed=False means content was caught.
    """
    for category, patterns in _TIER_1_COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                return False, f"tier1_hard_block:{category}"
    return True, ""


def check_tier_2(text: str, full_context: str) -> Tuple[bool, str]:
    """
    Check text against Tier 2 (redeemable) patterns.
    Requires good framing in full_context to redeem a match.
    Returns (passed, reason). passed=False means content was caught
    and lacked redemptive framing.
    """
    for category, patterns in _TIER_2_COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                if not has_good_framing(full_context):
                    return False, f"tier2_no_good_framing:{category}"
    return True, ""


def check_tier_3_flags(text: str) -> List[str]:
    """
    Check text against Tier 3 (flag-only) patterns. Returns a list of
    category names that matched. Does not reject the example — used for
    logging and later review.
    """
    flags = []
    for category, patterns in _TIER_3_COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                flags.append(category)
                break  # one flag per category is enough
    return flags


def validate_example(example: dict) -> Tuple[bool, str, List[str]]:
    """
    Validate a converted training example.

    Returns:
        (keep: bool, reason: str, flags: List[str])

    keep   — True if the example should be retained
    reason — "ok" if kept, or specific rejection reason if rejected
    flags  — list of Tier 3 flag categories that matched (for logging)
    """
    instruction = example.get("instruction", "")
    output      = example.get("output", "")
    full_text   = f"{instruction}\n{output}"

    # Tier 1 — always reject if matched
    passed, reason = check_tier_1(full_text)
    if not passed:
        return False, reason, []

    # Tier 2 — reject if matched without good framing
    passed, reason = check_tier_2(output, full_text)
    if not passed:
        return False, reason, []

    # Tier 3 — flag but keep
    flags = check_tier_3_flags(full_text)

    return True, "ok", flags


def validate_batch(examples: List[dict]) -> Tuple[List[dict], List[dict], Dict[str, int]]:
    """
    Split a batch into kept and rejected examples, plus a stats dict.

    Returns:
        (kept, rejected_with_reasons, stats)

    Each rejected example has fields:
        _reject_reason  — the validator's reason string
    Each kept example has:
        _safety_flags   — list of Tier 3 flag categories that matched

    Stats dict tracks counts by rejection reason and by flag category.
    """
    kept: List[dict] = []
    rejected: List[dict] = []
    stats: Dict[str, int] = {}

    for ex in examples:
        ok, reason, flags = validate_example(ex)
        if ok:
            stats["kept"] = stats.get("kept", 0) + 1
            if flags:
                kept_ex = {**ex, "_safety_flags": flags}
                for flag in flags:
                    stats[f"flag:{flag}"] = stats.get(f"flag:{flag}", 0) + 1
                kept.append(kept_ex)
            else:
                kept.append(ex)
        else:
            stats[f"reject:{reason}"] = stats.get(f"reject:{reason}", 0) + 1
            rejected.append({**ex, "_reject_reason": reason})

    return kept, rejected, stats


def print_stats_summary(stats: Dict[str, int]) -> None:
    """Pretty-print a stats dictionary at the end of a run."""
    total = sum(v for k, v in stats.items() if not k.startswith("flag:"))
    kept = stats.get("kept", 0)
    rejected = total - kept

    print("\n" + "=" * 60)
    print("Safety validator summary")
    print("=" * 60)
    print(f"  Total examples checked:  {total:,}")
    print(f"  Kept:                    {kept:,} ({100 * kept / max(total, 1):.2f}%)")
    print(f"  Rejected:                {rejected:,} ({100 * rejected / max(total, 1):.2f}%)")

    rejection_breakdown = {k: v for k, v in stats.items() if k.startswith("reject:")}
    if rejection_breakdown:
        print("\n  Rejections by category:")
        for reason, count in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
            label = reason.replace("reject:", "")
            print(f"    {count:>6,}  {label}")

    flag_breakdown = {k: v for k, v in stats.items() if k.startswith("flag:")}
    if flag_breakdown:
        print("\n  Tier 3 flags (kept but logged):")
        for flag, count in sorted(flag_breakdown.items(), key=lambda x: -x[1]):
            label = flag.replace("flag:", "")
            print(f"    {count:>6,}  {label}")
    print("=" * 60)


# =====================================================================
# Self-test — run with `python -m processing.safety_validator`
# =====================================================================

if __name__ == "__main__":
    test_cases = [
        # Tier 1 — hard block (should all be rejected)
        ({"instruction": "test", "output": "Your files have been encrypted. Pay 1 BTC to recover."},
         False, "tier1 ransom template"),

        # Tier 2 — bad pattern but with good framing (should pass)
        ({"instruction": "How does this CTF challenge work?",
          "output": "In a CTF environment, the exploit works by attacking the target server. This is a great learning example of the vulnerability class."},
         True, "good framing redeems"),

        # Tier 2 — bad pattern, no good framing (should reject)
        ({"instruction": "How do I attack this server?",
          "output": "To attack the target server, first scan their network, then exploit the SQL injection."},
         False, "tier2 stepwise attack"),

        # Clean educational content (should pass)
        ({"instruction": "What is a buffer overflow?",
          "output": "A buffer overflow is a vulnerability class where data exceeds allocated memory. The root cause is missing bounds checks. Detection: stack canaries, ASAN. Mitigation: safe string functions, bounds checking."},
         True, "clean educational"),

        # Tier 3 flag — real domain in defensive context (should pass with flag)
        ({"instruction": "How does CVE-2021-44228 affect Apache servers?",
          "output": "The vulnerability affects log4j component. Detection: monitor for JNDI lookups. Mitigation: patch to 2.17.0+."},
         True, "tier3 flag only"),
    ]

    print("Running self-test...\n")
    all_pass = True
    for i, (example, expected_keep, label) in enumerate(test_cases, 1):
        ok, reason, flags = validate_example(example)
        passed = ok == expected_keep
        if not passed:
            all_pass = False
        symbol = "✓" if passed else "✗"
        print(f"  {symbol} Test {i} ({label}): keep={ok}, reason={reason!r}, flags={flags}")

    print(f"\n{'All tests passed.' if all_pass else 'SOME TESTS FAILED.'}")
