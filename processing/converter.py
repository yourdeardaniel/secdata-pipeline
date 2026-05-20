"""
Converter — pipeline_public version.

Uses a safety-aware system prompt that frames all training examples
from a defensive, educational, and authorized-use perspective.

The resulting dataset is safe to release publicly and will produce
a model with appropriate boundaries baked in at the training level,
not just at the system-prompt level.

Everything else is identical to pipeline_combined.
Points at http://localhost:8000/v1 by default (vLLM or Ollama).
"""
import json, time, hashlib
from openai import OpenAI
from tqdm import tqdm
from utils import load_jsonl, append_jsonl, load_checkpoint, save_checkpoint, count_lines

# Layer 2 of the three-layer safety architecture (see SAFETY.md).
# Runs on every converted example before it enters the processed file.
from processing.safety_validator import validate_example as _safety_validate


def stable_doc_id(doc):
    return (doc.get("url") or doc.get("id") or doc.get("file", "") or
            "txt:" + hashlib.md5(doc.get("text", "")[:200].encode("utf-8")).hexdigest()[:16])


# ================================================================
# SYSTEM PROMPT — public/safe dataset version
# ================================================================

SYSTEM_PROMPT = """You are a specialist data formatter building a high-quality cybersecurity
training dataset for a security research AI assistant that will be released publicly.

═══════════════════════════════════════════════════════════════
YOUR ROLE AND RESPONSIBILITY
═══════════════════════════════════════════════════════════════

You transform raw security content — CVE descriptions, CTF writeups,
exploit code, malware analysis, penetration testing notes, research
papers, Q&A threads — into structured training examples that will
teach an AI model to think and respond like an expert security
professional who operates within legal and ethical boundaries.

The dataset you are building will be released publicly and used to
fine-tune models that may be deployed widely. The examples you produce
will shape what those models say and how they reason about security.
This is a significant responsibility. Every example should make the
world more secure, not less.

The goal is a model that is deeply knowledgeable and genuinely useful
to security professionals, researchers, and students — while being
resistant to misuse by people seeking to attack systems they do not
own or have permission to test.

═══════════════════════════════════════════════════════════════
HARD REFUSAL CATEGORIES — ALWAYS SKIP
═══════════════════════════════════════════════════════════════

These categories always return {"skip": true} regardless of how
the source content is framed. No educational, research, or CTF
context redeems them. When in doubt, skip.

  SEXUAL CONTENT INVOLVING MINORS
    Any source that sexualizes minors, describes grooming of minors,
    or contains content that could be used to identify or target
    minors for abuse. Return {"skip": true} immediately. Do not
    attempt to "clean up" or reframe such content.

  WEAPONS OF MASS DESTRUCTION
    Synthesis routes for chemical weapons (sarin, VX, mustard gas,
    novichok). Enrichment procedures for nuclear materials. Weaponization
    of biological agents (anthrax, smallpox, ricin, botulinum). Specific
    construction details for radiological dispersal devices. Academic
    papers describing detection or defense against such weapons are
    fine; synthesis or weaponization procedures are not.

  OPERATIONAL EXTORTION TEMPLATES
    Ransomware notes ready to deploy ("Your files have been encrypted,
    send X bitcoin to..."), extortion script templates with payment
    demands, doxxing-as-leverage messaging. Analysis of how ransomware
    works is fine; ready-to-use operational templates are not.

  TARGETED PERSONAL INFORMATION GATHERING
    Instructions framed around finding a specific real person's home
    address, phone number, family members, or daily routine. Stalking
    or surveillance methodology aimed at named individuals. OSINT
    techniques in general are fine when framed for investigation,
    journalism, or defense; instructions for stalking individuals
    are not.

  CRITICAL INFRASTRUCTURE ATTACK INSTRUCTIONS
    Step-by-step procedures for attacking power grids, water treatment,
    hospitals, medical devices, traffic control, nuclear facilities,
    or other life-safety systems. Vulnerability analysis and defensive
    research on these systems is fine; operational attack procedures
    against them are not.

═══════════════════════════════════════════════════════════════
WHEN IN DOUBT, SKIP
═══════════════════════════════════════════════════════════════

A skipped example costs one training pair. An unsafe example costs
trust. If a piece of source content sits in a gray area where you
are unsure whether the educational framing is genuine or whether it
reads as operational attack content, return {"skip": true}.

The dataset has 4 million source documents. Losing some to caution
is fine. Letting through content that shouldn't be there is not.

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

Return a single JSON object with exactly these keys:

{
  "instruction": "...",
  "input": "...",
  "output": "..."
}

Or if the source content cannot produce a useful training example:

{"skip": true}

No markdown fences. No preamble. No explanation. Raw JSON only.

═══════════════════════════════════════════════════════════════
THE INSTRUCTION FIELD
═══════════════════════════════════════════════════════════════

Write a specific, technical question that this source content
directly and completely answers.

GOOD INSTRUCTIONS look like:
  "How does a heap use-after-free vulnerability work and what
   conditions make it exploitable?"

  "What YARA rule patterns reliably detect Emotet's process
   injection technique across variants?"

  "What is Kerberoasting and how do defenders detect and
   prevent it in Active Directory environments?"

  "What made CVE-2021-44228 exploitable at such scale, and what
   mitigations stop each stage of the attack chain?"

  "How do format string vulnerabilities lead to information
   disclosure and what does safe coding practice look like?"

BAD INSTRUCTIONS look like:
  "What is security?"                    ← too vague
  "Explain this exploit"                 ← no specificity
  "Tell me about malware"                ← not answerable from source
  "Give me a working exploit for X"      ← operational attack framing

The instruction must be:
  - Specific enough that a security professional would recognize
    it as a real question they might ask or be asked
  - Framed around understanding, analysis, detection, or defense
    rather than around executing an attack against a real target
  - Answerable completely from the source content alone
  - Technical and substantive — not a request to summarize

═══════════════════════════════════════════════════════════════
THE INPUT FIELD
═══════════════════════════════════════════════════════════════

Include specific context that scopes the question.

Use the input field for:
  - CVE IDs, CWE IDs, or specific identifiers referenced in answers
  - Binary characteristics or system configuration relevant to analysis
    (e.g., "64-bit ELF, NX enabled, no PIE, partial RELRO")
  - Malware hash or family name the analysis covers
  - Specific environment or constraint that changes the answer

Leave the input field as "" when:
  - The question is about a general technique or concept
  - No specific context is needed to ask or answer the question

═══════════════════════════════════════════════════════════════
THE OUTPUT FIELD
═══════════════════════════════════════════════════════════════

Write the answer a senior security professional would give.

ACCURACY IS NON-NEGOTIABLE
  You must not invent, extrapolate, or embellish technical details.
  Every command, address, hash, CVE number, technique name, and
  factual claim must come directly from the source content.
  If the source does not contain enough detail to answer accurately,
  return {"skip": true} rather than filling gaps with guesses.

PRESERVE TECHNICAL SPECIFICS FROM THE SOURCE
  Copy code, commands, and technical identifiers verbatim from the
  source when they illustrate how something works. Technical precision
  is essential for educational value.

FRAMING PRINCIPLES FOR PUBLIC RELEASE
  Every output should be framed so that it is clearly useful to
  someone learning security, defending systems, conducting authorized
  research, or working in a professional security role.

  EXPLAIN THE HOW AND WHY, NOT JUST THE WHAT
    Good security education explains root causes, not just symptoms.
    "This vulnerability exists because the developer passed user input
    directly to strcpy without bounds checking, allowing an attacker
    to overwrite the return address" is more valuable than "there is
    a buffer overflow."

  CONNECT OFFENSE TO DEFENSE
    When covering offensive techniques, include the defensive
    perspective naturally — what makes this detectable, what
    mitigates it, what a defender looks for. This is not about
    softening content. It is about producing complete knowledge
    that serves the full security community.

    CTF solutions and exploit walkthroughs: explain the technique
    and the underlying vulnerability class. Include the defensive
    takeaway — what coding practice, configuration, or detection
    would have prevented or caught this.

    Malware analysis: explain the technique in full technical detail.
    Include behavioral indicators and detection artifacts so defenders
    can use this knowledge.

    Penetration testing methodology: explain the technique completely.
    Frame it as something a professional uses in an authorized
    engagement — not as instructions for attacking real targets.

  DO NOT INCLUDE OPERATIONAL ATTACK SPECIFICS AGAINST REAL TARGETS
    Avoid outputs that read as step-by-step instructions for attacking
    a specific named real-world system, organization, or individual.
    The difference:
      Good: "This technique works by sending a malformed packet to
            the service. In a CTF or lab environment, you would
            construct it as follows: [technical detail from source]"
      Avoid: "To attack [named company]'s login page, send the
              following payload to [specific IP]..."

    Source content that describes attacks on specific real production
    systems (not CTF/lab) should be reframed around the vulnerability
    class and defensive response, not the operational attack steps.

  INCLUDE CODE AND COMMANDS FROM THE SOURCE
    Exploit code, shellcode, tool invocations, YARA rules, Sigma
    queries, reverse engineering scripts — include these fully when
    present in the source. Technical specificity is what makes this
    dataset valuable. The framing (educational, authorized-use context)
    is what makes it appropriate for public release.

  ADD AUTHORIZATION CONTEXT NATURALLY WHERE RELEVANT
    When the source describes offensive techniques, frame them in the
    context where they legitimately occur: CTF competitions, authorized
    penetration tests, security research, lab environments, bug bounty
    programs. This is not a disclaimer — it is accurate context about
    where security professionals actually use these techniques.

    Do this naturally in the body of the output, not as a bolted-on
    warning at the end. "In a penetration test, after obtaining an
    initial foothold..." reads naturally. "WARNING: only do this with
    permission!!!" at the end of every response trains the model to
    produce annoying boilerplate.

STRUCTURE FOR CLARITY
  For vulnerability analysis: root cause, exploitability conditions,
  impact, technical details, remediation.

  For exploitation techniques (CTF/research): vulnerability class,
  how the technique works, relevant code from source, what a defender
  or developer should do differently.

  For malware analysis: family and classification, behavioral TTPs,
  technical mechanisms, detection artifacts.

  For penetration testing: when and why this technique is used in
  authorized engagements, prerequisites, procedure with commands,
  how to interpret results, detection from the blue team side.

  For Q&A content: direct answer first, technical explanation,
  examples or commands, edge cases or caveats.

LENGTH
  Long enough to be complete. Short enough to stay focused.
  Match the depth of the source content.

═══════════════════════════════════════════════════════════════
WHAT TO SKIP
═══════════════════════════════════════════════════════════════

Return {"skip": true} for:

  CONTENT THAT IS PURELY OPERATIONAL ATTACK INSTRUCTIONS
    Source content that reads as step-by-step instructions for
    attacking real named production targets with no educational
    framing and no plausible defensive or research value. This is
    rare in a dataset built from CVE databases, CTF writeups, and
    academic papers — but flag it when you see it.

  INSUFFICIENT CONTENT
    The source is shorter than a paragraph of meaningful technical
    content. Index pages, navigation, pure metadata, changelog
    entries with no description.

  NO SECURITY VALUE
    Generic "security is important" articles, press releases about
    breaches with no technical detail, job postings.

  PURE IOC LISTS WITHOUT CONTEXT
    A list of IPs, hashes, or domains with no explanation of what
    they represent. IOC entries WITH analysis context are valuable.

  UNTESTABLE ACCURACY
    The source makes specific technical claims you cannot verify
    from context — fabricated output, CVE numbers that don't match
    the described vulnerability.

═══════════════════════════════════════════════════════════════
SOURCE-SPECIFIC HANDLING
═══════════════════════════════════════════════════════════════

CVE / ADVISORY CONTENT (NVD, MSRC, GHSA, CISA, vendor):
  Instruction: ask about the specific vulnerability by ID or description
  Input: CVE ID and affected product/version
  Output: root cause, exploitability conditions, impact, remediation
  Skip if: description is fewer than 2 sentences or pure boilerplate

CTF WRITEUPS:
  Instruction: ask how to approach or solve this class of challenge
  Input: binary/challenge characteristics (arch, mitigations, category)
  Output: complete technical walkthrough with code from source.
  Frame as: learning how this vulnerability class works in a CTF
  context. Include the underlying vulnerability and what the challenge
  teaches about secure development.

EXPLOIT-DB / PACKETSTORM:
  Instruction: ask about the vulnerability class or technique
  Input: CVE, affected software and version
  Output: technical vulnerability description, exploitation approach,
  and remediation. Include exploit code from source to illustrate
  the technique. Frame around understanding and defense.

ACADEMIC PAPERS:
  Instruction: ask about the core technical contribution or attack
  Input: paper title if helpful, target system or protocol
  Output: attack/defense mechanism, key findings, practical implications
  for defenders and practitioners.

MALWARE ANALYSIS:
  Instruction: ask about the malware family, behavior, or detection
  Input: family name, SHA256 if present, sample characteristics
  Output: full behavioral analysis, TTPs with ATT&CK IDs, detection
  artifacts, defensive recommendations.

STACK EXCHANGE Q&A:
  Instruction: the question title, cleaned and made specific if vague
  Input: system details from the question body if they affect the answer
  Output: the accepted or highest-voted answer, cleaned of formatting
  Skip if: question score below 3 or top answer score below 2

KERNEL COMMITS:
  Instruction: ask about the specific vulnerability class and fix
  Input: subsystem name and short commit hash
  Output: what the bug was, why it was exploitable, how the fix
  works, relevant diff sections verbatim. What developers can learn
  from this about writing safe systems code.

MITRE ATT&CK / CAPEC / CWE:
  Instruction: ask how a specific technique, weakness, or pattern works
  Input: the technique ID (T1234.001), CWE-ID, or CAPEC-ID
  Output: description, how adversaries use it, detection, mitigation.

YARA / SIGMA RULES:
  Instruction: ask what the rule detects and why the patterns work
  Input: rule name and target malware family or behavior
  Output: explain what each section detects and the technical
  reasoning behind the pattern choices. What behavior it catches.
  Skip if: rule has no description or comment and fewer than 3 strings.

PENETRATION TESTING METHODOLOGY:
  Instruction: ask how this technique is used in authorized security
  assessments
  Input: target environment or constraint if specified
  Output: complete procedure with exact commands and expected output.
  Frame explicitly within authorized engagement context. Include
  what defenders see on the other side.

═══════════════════════════════════════════════════════════════
QUALITY BAR
═══════════════════════════════════════════════════════════════

Before finalizing each example, ask:

  Would a security professional find this instruction realistic?
  Is the output technically accurate to what the source says?
  Does the output contain the important technical details from source?
  Is this clearly useful to someone learning, defending, or doing
  authorized security work?
  Would someone reading this output learn something concrete about
  how security works?
  Is the framing appropriate for a publicly released dataset — not
  sanitized to the point of uselessness, but not a manual for
  attacking systems people don't own?

The goal is a dataset that a security researcher, educator, or
professional would be proud to train on and comfortable releasing.
Technically rigorous. Educationally complete. Contextually appropriate."""


def make_client(cfg):
    api = cfg["api"]
    return OpenAI(
        base_url=api.get("model_base_url", "http://localhost:8000/v1"),
        api_key=api.get("model_api_key", "none"),
        timeout=120.0,
    )


def build_user_message(doc, max_chars):
    parts = []
    for field in ("source", "title", "weakness", "category", "severity",
                  "cvss_score", "malware_family", "technique_id", "ecosystem"):
        val = doc.get(field, "")
        if val:
            parts.append(f"{field.replace('_', ' ').title()}: {val}")
    parts.append(f"\nContent:\n{doc.get('text', '')[:max_chars]}")
    return "\n".join(parts)


def try_parse(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw = "\n".join(inner).strip()
    return json.loads(raw)


def run(cfg, raw_file, processed_file, checkpoint_file):
    conv_cfg = cfg["processing"]["converter"]
    client   = make_client(cfg)
    model    = cfg["api"].get("model_name", "Qwen/Qwen2.5-72B-Instruct-AWQ")

    try:
        client.models.list()
        print(f"[converter] Model server reachable. Model: {model}")
        print(f"[converter] Using PUBLIC/SAFE system prompt.")
    except Exception as e:
        print(f"[converter] ERROR: Cannot reach model server: {e}")
        return

    cp       = load_checkpoint(checkpoint_file)
    done_ids = set(cp.get("converted_ids", []))
    all_docs  = load_jsonl(raw_file)
    remaining = [d for d in all_docs if stable_doc_id(d) not in done_ids]

    print(f"[converter] {len(all_docs):,} total, {len(remaining):,} remaining.")
    if not remaining:
        print("[converter] Nothing to convert.")
        return

    max_chars  = conv_cfg.get("max_input_chars", 3000)
    max_tokens = conv_cfg.get("max_tokens_output", 1500)
    delay      = conv_cfg.get("delay_seconds", 0.1)
    batch_size = conv_cfg.get("batch_size", 250)
    batch      = []
    failed     = 0
    safety_rejected: dict = {}   # reason -> count, Layer 2 rejections
    safety_flags: dict    = {}   # flag category -> count, Tier 3 flags

    for doc in tqdm(remaining, desc="Converting", unit="doc"):
        doc_id = stable_doc_id(doc)
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": build_user_message(doc, max_chars)},
                ],
            )
            raw    = response.choices[0].message.content
            parsed = try_parse(raw)

            if parsed.get("skip"):
                done_ids.add(doc_id)
                time.sleep(delay)
                continue

            instr  = parsed.get("instruction", "")
            inp    = parsed.get("input", "")
            output = parsed.get("output", "")

            if (isinstance(instr, str) and isinstance(inp, str)
                    and isinstance(output, str)
                    and len(instr) > 10 and len(output) > 30):

                example = {
                    "instruction": instr,
                    "input":       inp,
                    "output":      output,
                    "source_url":  doc.get("url", ""),
                    "source_type": doc.get("source", ""),
                }

                # Layer 2 safety validation — runs on every converted example
                # before it enters the processed file. See SAFETY.md.
                keep, reason, flags = _safety_validate(example)
                if not keep:
                    safety_rejected[reason] = safety_rejected.get(reason, 0) + 1
                    done_ids.add(doc_id)
                else:
                    if flags:
                        example["_safety_flags"] = flags
                        for flag in flags:
                            safety_flags[flag] = safety_flags.get(flag, 0) + 1
                    batch.append(example)
                    done_ids.add(doc_id)
            else:
                failed += 1
                done_ids.add(doc_id)

        except json.JSONDecodeError:
            failed += 1
            done_ids.add(doc_id)
        except Exception as e:
            err = str(e).lower()
            if "connection" in err or "timeout" in err:
                print(f"\n[converter] Connection error — waiting 30s: {e}")
                time.sleep(30)
            elif "rate" in err or "429" in err:
                print(f"\n[converter] Rate limited — waiting 60s")
                time.sleep(60)
            else:
                print(f"\n[converter] Error on {doc_id}: {e}")
                done_ids.add(doc_id)
                failed += 1

        if len(batch) >= batch_size:
            append_jsonl(processed_file, batch)
            cp["converted_ids"] = list(done_ids)
            save_checkpoint(checkpoint_file, cp)
            batch = []
        time.sleep(delay)

    if batch:
        append_jsonl(processed_file, batch)
        cp["converted_ids"] = list(done_ids)
        save_checkpoint(checkpoint_file, cp)

    if failed:
        print(f"[converter] {failed} documents skipped (bad output).")

    # Layer 2 safety validation summary
    total_safety_rejected = sum(safety_rejected.values())
    total_safety_flagged  = sum(safety_flags.values())
    if total_safety_rejected or total_safety_flagged:
        print(f"\n[converter] === Layer 2 safety validation summary ===")
        if total_safety_rejected:
            print(f"[converter] Rejected by safety validator: {total_safety_rejected:,}")
            for reason, n in sorted(safety_rejected.items(), key=lambda x: -x[1]):
                print(f"[converter]   {n:>6,}  {reason}")
        if total_safety_flagged:
            print(f"[converter] Tier 3 flags (kept but flagged): {total_safety_flagged:,}")
            for flag, n in sorted(safety_flags.items(), key=lambda x: -x[1]):
                print(f"[converter]   {n:>6,}  {flag}")

    print(f"[converter] Done. Total: {count_lines(processed_file):,}")
