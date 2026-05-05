import time
from openai import OpenAI
from tqdm import tqdm
from utils import load_jsonl, save_jsonl, load_checkpoint, save_checkpoint, count_lines, append_jsonl

REFUSAL_PHRASES = [
    "i cannot","i can't","as an ai","i'm an ai","i don't know",
    "i apologize","i'm sorry, i","i am not able","it's not appropriate",
    "i'm unable to","language model","i was trained","i cannot provide",
]

TASK_WORDS = [
    "how","what","why","when","explain","describe","analyse","analyze",
    "find","identify","write","create","implement","demonstrate","show",
    "list","compare","define","detect","exploit","bypass","enumerate",
    "escalate","reverse","decompile","fuzz","audit","assess","mitigate",
    "trace","debug","disassemble","patch","exfiltrate","pivot",
]

SHORT_OUTPUT_SOURCES = {
    "mitre_attack","capec","nvd","osv","msrc","cisa_kev",
    "ubuntu_advisory","redhat_advisory","malpedia","github_advisory",
    "urlhaus","threatfox","malwarebazaar","anyrun","kernel_commit",
}

FILTER_PROMPT = """Rate the quality of this cybersecurity training example 1-10.

Score 8-10: Specific, technically accurate, genuinely useful to a security professional.
Score 5-7: Decent but generic or surface-level.
Score 1-4: Too vague, incorrect, or not about security.

Reply with ONLY a single integer 1-10. Nothing else."""


def make_client(cfg):
    api = cfg["api"]
    return OpenAI(
        base_url=api.get("model_base_url", "http://localhost:8000/v1"),
        api_key=api.get("model_api_key", "none"),
        timeout=60.0,
    )


def structural_filter(ex, cfg):
    f = cfg["processing"]["filter"]
    instruction = ex.get("instruction", "")
    output      = ex.get("output", "")
    source_type = ex.get("source_type", "")
    min_out = 80 if source_type in SHORT_OUTPUT_SOURCES else f.get("min_output_chars", 100)
    if len(instruction) < f.get("min_instruction_chars", 20):
        return False, "instruction too short"
    if len(output) < min_out:
        return False, "output too short"
    if len(output) > f.get("max_output_chars", 6000):
        return False, "output too long"
    out_lower = output.lower()
    for phrase in REFUSAL_PHRASES:
        if phrase in out_lower:
            return False, f"refusal: {phrase!r}"
    if output.count(" ") < 10:
        return False, "almost no words"
    if not any(w in instruction.lower() for w in TASK_WORDS):
        return False, "no task word in instruction"
    return True, ""


def lm_score(ex, client, model):
    text = (f"Instruction: {ex['instruction'][:300]}\n\n"
            f"Output (first 500 chars):\n{ex['output'][:500]}")
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=3, temperature=0,
            messages=[
                {"role": "system", "content": FILTER_PROMPT},
                {"role": "user",   "content": text},
            ],
        )
        return int(resp.choices[0].message.content.strip())
    except (ValueError, Exception):
        return 6


def run(cfg, processed_file, filtered_file, checkpoint_file):
    f_cfg    = cfg["processing"]["filter"]
    use_lm   = f_cfg.get("lm_filter_enabled", True)
    min_score= f_cfg.get("lm_min_score", 7)
    delay    = f_cfg.get("delay_seconds", 0.05)
    client   = make_client(cfg) if use_lm else None
    model    = cfg["api"].get("model_name", "Qwen/Qwen2.5-72B-Instruct-AWQ")

    cp = load_checkpoint(checkpoint_file)
    passed_set = set(cp.get("filtered_ids", []))
    all_examples = load_jsonl(processed_file)
    remaining = [e for e in all_examples
                 if e.get("source_url","") + e.get("instruction","")[:50] not in passed_set]

    already_kept = count_lines(filtered_file)
    print(f"[filter] {len(all_examples):,} total examples")
    print(f"[filter] {len(passed_set):,} already filtered, {len(remaining):,} remaining")
    print(f"[filter] {already_kept:,} already passed and saved to {filtered_file}")

    reject_reasons = {}
    lm_pass = lm_fail = 0
    batch = []

    for ex in tqdm(remaining, desc="Filtering", unit="ex"):
        ex_id = ex.get("source_url","") + ex.get("instruction","")[:50]
        ok, reason = structural_filter(ex, cfg)
        if not ok:
            reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
            passed_set.add(ex_id)
            continue
        if use_lm and client:
            score = lm_score(ex, client, model)
            if score < min_score:
                lm_fail += 1
                passed_set.add(ex_id)
                time.sleep(delay)
                continue
            lm_pass += 1
            time.sleep(delay)
        batch.append(ex)
        passed_set.add(ex_id)

        if len(batch) >= 500:
            append_jsonl(filtered_file, batch)
            cp["filtered_ids"] = list(passed_set)
            save_checkpoint(checkpoint_file, cp)
            batch = []

    if batch:
        append_jsonl(filtered_file, batch)
        cp["filtered_ids"] = list(passed_set)
        save_checkpoint(checkpoint_file, cp)

    print(f"\n[filter] Structural rejections:")
    for reason, n in sorted(reject_reasons.items(), key=lambda x: -x[1])[:10]:
        print(f"  {n:>6,}  {reason}")
    if use_lm:
        print(f"[filter] LM pass: {lm_pass:,}  fail: {lm_fail:,}")
    print(f"[filter] Total kept: {count_lines(filtered_file):,}")
