# Safety Documentation

This pipeline is designed for producing a publicly releasable cybersecurity
training dataset. Safety was a first-class consideration in the design.

## Three layers of safety

### Layer 1 — Converter system prompt

The converter uses a safety-aware system prompt that instructs the LLM to:

- Frame offensive techniques within authorized/educational contexts (CTF, pentest, research)
- Connect offensive knowledge to defensive applications naturally
- Skip content that reads as pure operational attack instructions with no educational value
- Add authorization context naturally in the body of outputs (not as bolted-on disclaimers)

This is not about censoring security knowledge — it's about framing. A heap
exploitation walkthrough in the public dataset teaches "here's how this class
of vulnerability works in a CTF environment and what a developer should take away."
The technical content is identical. The framing determines whether the example
trains a model to understand security or to attack systems.

### Layer 2 — Post-conversion safety validator

After the LLM converts each document, `processing/safety_validator.py` checks
the output for patterns that suggest operational attack assistance slipped
through despite the system prompt. Examples that match these patterns without
redemptive educational framing are rejected before entering the dataset.

### Layer 3 — LM quality filter

The standard quality filter (processing/filter.py) also catches safety issues
as a side effect of filtering for quality — vague, poorly-framed, or
instruction-violating outputs fail the quality check regardless of topic.

## What the dataset does and does not contain

**Does contain:**
- Vulnerability descriptions, CVE analyses, and security advisories
- CTF challenge solutions and exploit technique walkthroughs
- Penetration testing methodology in authorized engagement contexts
- Malware analysis, reverse engineering, and threat intelligence
- Detection rules, defensive techniques, and security hardening guides
- Security Q&A from Stack Exchange and practitioner blogs

**Does not contain (by design):**
- Step-by-step instructions for attacking named real production systems
- Operational attack assistance without educational or defensive framing
- Content whose only reasonable use is attacking systems without authorization
- Credentials, PII, or accidentally scraped sensitive data (scrubbed at collection)

## Dual-use acknowledgment

Security knowledge is inherently dual-use. The same understanding of how
a buffer overflow works is needed by both exploit developers and the
engineers who fix them. This dataset does not eliminate that duality —
it does not water down technical content. What it does is ensure the
framing consistently positions the knowledge in legitimate security
practice contexts.

Users who fine-tune models on this dataset are responsible for deploying
those models responsibly. The dataset card on HuggingFace includes a
recommended deployment system prompt for models trained on this data.

## Version note

A higher-capability version of the converter prompt exists for restricted
research contexts (pipeline_combined). That version prioritizes maximum
technical fidelity over safety framing and is appropriate for internal
security research tools with access controls. This repository contains
only the public-release version.

## Contact

If you identify a safety issue with specific examples in the released dataset,
open an issue with the example content (or a hash of it) and a description
of the concern. Examples that are genuinely harmful will be removed from
future dataset versions.
