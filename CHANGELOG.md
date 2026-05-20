# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] — Safety architecture hardening

### Changed
- **Layer 2 safety validator substantially expanded.** From 4 patterns in one
  category to 17+ patterns across three tiers (always-reject, reject-without-
  redemption, flag-and-keep). New categories include CSAM indicators (zero
  tolerance), WMD synthesis, ransom templates, doxxing patterns, phishing
  against named real targets, operational malware deployment, insider threat
  sabotage, financial fraud, and critical infrastructure attacks. Each
  rejection now produces a specific category reason for logging.
- **Layer 1 prompt: added Hard Refusal Categories section.** The converter
  system prompt now explicitly lists five categories (CSAM, WMD, ransom
  templates, targeted personal info gathering, critical infrastructure attack
  procedures) that always return `{"skip": true}` regardless of framing. This
  matches the validator's Tier 1 categories so the two layers reinforce each
  other.
- **Layer 1 prompt: added "When in doubt, skip" principle.** Explicit guidance
  that the asymmetric cost of false positives vs false negatives means the
  converter should bias toward skipping uncertain content.
- **Good-framing patterns made specific.** Previously generic words like
  "research" or "security" could redeem Tier 2 matches. Now redemption requires
  specific indicators: named CTF platforms, explicit authorization language,
  defensive role names, vulnerability-class focus, etc.
- **SAFETY.md rewritten** to document the actual pattern categories, tier
  structure, known limitations, and design philosophy.

### Fixed
- **Critical: safety validator is now actually called.** Previous version
  imported `validate_example` but never invoked it in the conversion loop.
  The validator now runs on every converted example before it enters the
  processed file. Rejection counts and Tier 3 flag counts are tracked and
  printed in a summary at the end of each run.

### Added
- Built-in self-test for safety validator: run
  `python3 processing/safety_validator.py` to verify all pattern tiers work.
- Tier 3 (flag-and-keep) for borderline PII patterns: real-looking domains,
  emails, phone numbers, SSN/credit-card-shaped sequences. Logged for later
  review rather than rejected.
- Per-category rejection statistics printed at end of each conversion run.

## [1.0.0] — Initial public release

### Features
- LLM-based conversion of raw security documents into instruction-tuning
  examples with `{instruction, input, output}` structure
- Safety-aware converter system prompt designed for public dataset release
- Post-conversion safety validator that catches operational attack patterns
- LM-based quality filter with configurable score threshold
- Embedding-based deduplication (cosine similarity)
- Resumable conversion via document-level checkpoints

### Safety architecture
- Layer 1: Converter system prompt frames offensive content educationally
- Layer 2: Safety validator rejects examples without redemptive framing
- Layer 3: Quality filter catches structural and framing failures
- License metadata preserved from raw documents through to final dataset

### Infrastructure
- Compatible with vLLM, Ollama, and any OpenAI-compatible API server
- Tuned for Qwen 2.5 72B Instruct (AWQ) but works with any capable model
- Atomic checkpoint writes
- Streaming JSONL I/O — never holds the full dataset in memory
