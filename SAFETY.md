# Safety Documentation

This pipeline is designed to produce a publicly releasable cybersecurity
instruction-tuning dataset. The dataset is built from public security sources,
and safety considerations are first-class concerns in the design — both at
the level of what gets included and the framing in which it appears.

This document describes the three-layer safety architecture, the specific
patterns each layer checks for, the known limitations, and the philosophy
behind the design choices.

## The three layers, concretely

### Layer 1 — Converter system prompt

Location: `processing/converter.py`, the `SYSTEM_PROMPT` constant.

The converter LLM operates under a ~4,000-token system prompt that frames
the entire conversion task. The prompt has several sections, each with
specific operational purposes:

**Role and responsibility.** Sets up the model as a data formatter
producing examples for public release, with explicit acknowledgment
that the output shapes downstream model behavior.

**Hard refusal categories.** Explicit list of content categories that
always return `{"skip": true}` regardless of framing:
- Sexual content involving minors
- Weapons of mass destruction (synthesis, weaponization, enrichment)
- Operational extortion templates (ransomware notes, payment demands)
- Targeted personal information gathering (stalking, doxxing of named individuals)
- Critical infrastructure attack procedures (power, water, hospitals, transit)

**"When in doubt, skip" principle.** Explicit guidance that a skipped
example costs one training pair while an unsafe example costs trust,
biasing the converter toward conservative skipping.

**Output format and field structure.** Specifies the JSON output schema
and what each field should contain.

**Framing principles.** The heart of the prompt's safety work. Specific
rules with examples:
- Connect offense to defense naturally in the body of every example
- Frame offensive techniques within authorized contexts (CTF, pentest,
  research, lab) where they legitimately occur
- Use authorization context as integrated framing rather than bolted-on
  disclaimers ("WARNING: only do this with permission!!!")
- Don't include operational attack specifics against named real targets
- Do include technical specifics — code, commands, exploit details —
  from the source content. Sanitization is not the goal; framing is.

**Source-specific handling.** Different rules for CVE entries vs CTF
writeups vs malware analysis vs Stack Exchange Q&A, each with appropriate
framing for that source type.

**Quality bar.** Final checklist of questions the converter should ask
about each example before finalizing it.

### Layer 2 — Post-conversion regex validator

Location: `processing/safety_validator.py`.

After the converter produces each example, the validator checks the output
against a tiered set of regex patterns. There are three tiers:

#### Tier 1 — Always reject
No amount of educational framing redeems a Tier 1 match. Categories:

| Category | What it catches |
|---|---|
| `csam_indicator` | Sexual/sexualized language near minor-age terms; CSAM/CP abbreviations |
| `wmd_synthesis` | Synthesis verbs near specific WMD names (sarin, anthrax, etc.) |
| `ransom_template` | "Your files have been encrypted" + cryptocurrency payment demand |
| `grooming_pattern` | "Groom" + minor terms in online contact contexts |

#### Tier 2 — Reject unless redemptive framing
Patterns that catch operational attack content. Retained only if the
example also contains specific good-framing indicators. Categories:

| Category | What it catches |
|---|---|
| `named_real_target_attack` | "Attack/exploit/compromise" + real domains/IPs |
| `stepwise_attack_real_target` | Sequential steps targeting "the victim", "their server", etc. |
| `doxxing_pattern` | "Find their home address / phone number / real name" |
| `phishing_real_target` | Phishing aimed at named real companies/services |
| `operational_malware_deployment` | "Deploy/install malware on their system" |
| `insider_threat_sabotage` | "As an insider, steal/sabotage" patterns |
| `financial_fraud_real_target` | "Drain their wallet/bank account" patterns |
| `critical_infrastructure_attack` | Operational attacks on power/water/hospitals |

#### Tier 3 — Flag but keep
Patterns that suggest borderline content worth logging without rejection.
Examples kept; flags recorded in the output for later review:

| Category | What it catches |
|---|---|
| `real_domain_in_text` | Real-looking domains (filters example.com, test.com, lab.* etc.) |
| `real_email_in_text` | Real-looking email addresses |
| `real_phone_in_text` | US phone number patterns |
| `potential_pii_ssn` | SSN-shaped sequences |
| `potential_pii_credit_card` | 16-digit credit-card-shaped sequences |

#### Good-framing patterns

Tier 2 patterns are "redeemed" by specific framing indicators. The
good-framing patterns are intentionally narrow — generic words like
"security" or "research" alone don't qualify. Categories of good framing:

- Explicit authorization (authorized pentest/engagement/red team)
- CTF/lab/sandbox environments (HackTheBox, TryHackMe, picoCTF, lab environment)
- Defensive framing (blue team, defender, detection engineering, incident response)
- Concept/class focus (vulnerability class, root cause, attack pattern)
- Research/academic (peer-reviewed, academic paper, research paper)
- Educational (students learn, learners will understand, curriculum)
- Historical/post-incident framing (post-incident, root cause analysis, lessons learned)

### Layer 3 — Quality filter

Location: `processing/filter.py`.

The quality filter runs after the safety validator. Its primary purpose
is quality, but it catches additional safety issues as a side effect:

- Structural checks: instruction length, output length, refusal-phrase
  detection, task-word presence in instruction.
- LM-based scoring: each example is scored 1-10 by an LM-based quality
  judge. Default threshold is 7; examples below threshold are dropped.

Vague outputs, outputs that refuse to engage with the source, and outputs
that fail to address the instruction are filtered here regardless of topic.
This catches the residual safety issues that survived Layers 1 and 2.

## What gets caught at each layer (in practice)

The layers are designed to be progressively more specific:

**Layer 1 catches the upstream issues.** Most concerning content never
gets generated in the first place — the converter system prompt either
skips it or reframes it. This is the cheap layer because it prevents
work downstream.

**Layer 2 catches the cases Layer 1 missed.** The validator is the
backstop for cases where the converter produced something the prompt
should have prevented. Each rejection is logged with its category, so
the user can see exactly what slipped through and tune the prompt or
validator accordingly.

**Layer 3 catches quality-related residue.** Examples that aren't
obviously harmful but are vague, off-topic, or unhelpful get filtered
at this layer.

## Known limitations

This safety architecture is one of the first openly documented attempts
at dual-use safety in security training data. It is not a complete
solution. Honest limitations:

**Regex is not semantic.** The validator catches surface patterns. An
adversarially constructed example using different phrasing could evade
the patterns. The good-framing redemption means a determined attacker
could include CTF framing keywords to bypass Tier 2 — but at that point,
they've also added enough context that the trained model is unlikely to
treat the result as operational attack instruction.

**False positives are accepted as a cost.** The validator will reject
some legitimate educational examples that happen to use phrasing matching
Tier 2 patterns without enough good-framing indicators. Given a corpus
of 4M+ documents, the dataset can absorb this loss. Rates per category
will be published with the converted dataset.

**Coverage is bounded by what's in the patterns.** New attack categories
or evasion patterns require pattern updates. The patterns can be inspected,
critiqued, and improved by anyone reading the code — this is the explicit
tradeoff of using transparent regex over an opaque ML classifier.

**Layer 3 quality filter is not a safety classifier.** It catches
safety-relevant issues incidentally. Pretending otherwise would be
misrepresentation.

**No PII audit has been performed on raw v1.0.** The raw dataset includes
the `_had_credentials_scrubbed` field from the scraper but has not been
systematically PII-audited. The Tier 3 flags in the validator catch some
PII-shaped patterns in output, but the v2.0 converted dataset will undergo
more thorough PII review.

## Philosophy

The dataset and pipeline take the position that the right response to
dual-use cybersecurity content is **framing**, not **sanitization**.

A heap exploitation walkthrough in the converted dataset teaches "here's
how this class of vulnerability works in a CTF environment and what a
developer should take away from it." The technical content is identical
to what's in the source. The framing determines whether the example
trains a model to understand security or to attack systems.

This is the same philosophy that underlies how security education works
generally — security curricula, CTF challenges, vulnerability research,
red-team training, all involve teaching offensive techniques because
defenders need to understand them. The way that knowledge is framed in
the educational context is what makes it work.

## What the dataset does and does not contain

**Does contain:**
- Vulnerability descriptions, CVE analyses, and security advisories
- CTF challenge solutions and exploit technique walkthroughs (framed
  as CTF / lab content)
- Penetration testing methodology in authorized engagement contexts
- Malware analysis, reverse engineering, and threat intelligence
- Detection rules, defensive techniques, and security hardening guides
- Security Q&A from Stack Exchange and practitioner blogs
- Code, commands, and exploit techniques from source content — preserved
  for technical fidelity, framed for educational use

**Does not contain (by design):**
- Step-by-step instructions for attacking named real production systems
- Operational attack assistance without educational or defensive framing
- Content whose only reasonable use is attacking systems without authorization
- CSAM, weapons-of-mass-destruction synthesis, or other Tier 1 categories
- Credentials, PII, or accidentally scraped sensitive data
  (best-effort scrubbing at collection, more thorough review in v2.0)

## Dual-use acknowledgment

Security knowledge is inherently dual-use. The same understanding of how
a buffer overflow works is needed by both exploit developers and the
engineers who fix them. This dataset does not eliminate that duality —
it does not water down technical content. What it does is ensure the
framing consistently positions the knowledge in legitimate security
practice contexts.

Users who fine-tune models on this dataset are responsible for deploying
those models responsibly. The dataset card on Hugging Face includes a
recommended deployment system prompt for models trained on this data.

## Version note

A higher-capability version of the converter prompt exists for restricted
research contexts (the `pipeline_combined` internal version). That version
prioritizes maximum technical fidelity over safety framing and is appropriate
only for security research with access controls. This repository contains
only the public-release version.

## Contact

If you identify a safety issue with specific examples in the released dataset:
- Open an issue at https://github.com/yourdeardaniel/secdata-pipeline/issues
- Include the example content (or a hash of it) and a description of the concern
- Examples that are genuinely harmful will be removed from future dataset versions

If you have suggestions for additional patterns the validator should catch,
PRs against `processing/safety_validator.py` are welcome. The patterns are
intentionally open for community improvement.
