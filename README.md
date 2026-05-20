# secdata-pipeline

**Requires Python 3.9 or newer.** Tested on 3.9, 3.10, 3.11, 3.12.

Converts raw security documents from [secdata-scrapers](https://github.com/yourdeardaniel/secdata-scrapers)
into annotated instruction-tuning training examples for defensive cybersecurity LLMs.

The raw input corpus ([secdata-raw](https://huggingface.co/datasets/deardaniel/secdata-raw))
is **4,051,139 documents** from 50+ public security sources, released under CC BY-SA 4.0.

This repository is the conversion phase: it transforms those raw documents
into clean instruction-response training pairs with a three-layer safety
architecture. Expected output: **~500K–1M filtered training examples**
after deduplication and quality filtering.

The converted dataset (`secdata` v2.0) is planned for public release pending
compute resources.

---

## What it does

```
raw_docs.jsonl (4.05M docs from secdata-scrapers)
  → converter.py        LLM reformats each doc as {instruction, input, output}
                        with safety-aware system prompt (Layer 1)
                        + post-conversion regex validator (Layer 2)
  → filter.py           removes low-quality, vague, and framing-failure examples (Layer 3)
  → deduplicator.py     removes near-duplicate examples (cosine similarity)
  → final_dataset.jsonl ~500K–1M examples
```

The converter uses a **safety-aware system prompt** that frames all security
content in educational and authorized-use contexts. Each generated example
runs through a regex validator that catches operational attack patterns
without redemptive framing. See [SAFETY.md](SAFETY.md) for the full
three-layer safety architecture, pattern categories, and known limitations.

---

## Setup

```bash
git clone https://github.com/yourdeardaniel/secdata-pipeline
cd secdata-pipeline
pip install -r requirements.txt

# Get the raw data — either from the public Hugging Face release
# or by copying directly from your secdata-scrapers run.

# Option 1: Hugging Face (recommended)
pip install huggingface_hub
mkdir -p data/raw
# Download chunks from https://huggingface.co/datasets/deardaniel/secdata-raw
# and concatenate into data/raw/raw_docs.jsonl

# Option 2: Direct copy from scraper VPS
scp user@scraper-vps:~/secdata-scrapers/data/raw/raw_docs.jsonl data/raw/

# Start your inference server (one of):

# Self-hosted Qwen 2.5 72B on H100:
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct-AWQ \
  --quantization awq --max-model-len 4096 \
  --gpu-memory-utilization 0.90 --port 8000

# Or use a cloud API by setting model_base_url in config.yaml to point at
# Anthropic, OpenAI, Together, or any OpenAI-compatible endpoint.

# Verify server
python main.py --check-model

# Run pipeline
tmux new -s pipeline
python main.py --convert-only
python main.py --filter-only
python main.py --dedup-only
```

---

## Output format

```json
{
  "instruction": "How does a heap use-after-free vulnerability work?",
  "input": "",
  "output": "A use-after-free occurs when memory is accessed after being freed...",
  "source_url": "https://example.com/writeup/12345",
  "source_type": "stackexchange_dump"
}
```

Compatible with Axolotl, LLaMA-Factory, and Hugging Face Trainer directly.

---

## Hardware and cost

The conversion phase is the bottleneck. With 4M+ raw documents, the cost
and time depend heavily on which inference path you choose.

### Self-hosted (Qwen 2.5 72B AWQ on H100-class GPU)

**GPU memory** is the hard constraint. Qwen 2.5 72B AWQ needs ~40GB of VRAM
to load and serve. Any GPU or combination with 40GB+ VRAM works. Less VRAM
means using a smaller model, which produces lower-quality training examples.

**Throughput** determines time. vLLM with batched inference on an H100 80GB
can process the corpus in a few weeks of continuous runtime. Exact throughput
varies with document size distribution and batch tuning. Costs at typical
cloud rates (~$2-2.50/hr for H100): roughly **$1,000-3,000** for the full
conversion.

### Cloud API (Anthropic, OpenAI, Together)

The pipeline is built around OpenAI-compatible endpoints, so any cloud
provider works. After deduplication and filtering, the conversion needs
roughly 4-6 billion tokens. Cost estimates with current pricing and batch
discounts:

| Provider | Model | Est. cost | Notes |
|---|---|---|---|
| Anthropic | Sonnet 4.6 | ~$12K-18K | Strong system-prompt adherence |
| OpenAI | GPT-4o-mini | ~$3K-6K | Cheapest cloud option |
| OpenAI | GPT-4o | ~$15K-25K | Higher quality on hard documents |
| Self-hosted | Qwen 2.5 72B | ~$1K-3K | Lowest cost, most setup |

### Partial runs

Partial runs are viable and recommended for first iterations:

- ~100K documents → ~50K training examples, costs ~$300-500 on cloud APIs
- ~500K documents → ~250K training examples, costs ~$1,500-2,500
- Full ~1M post-filter conversion → ~500K-1M examples, costs as above

Set `max_documents` in `config.yaml` to limit the run.

### Why H100 specifically for self-hosting

It's the cheapest path to high-throughput batched inference on a 72B model
when renting by the hour. Smaller models (Qwen 2.5 32B, 14B, 7B) work on
less VRAM but produce lower-quality conversions. See `config.yaml.example`
for model selection.

### Why not a CPU

LLM inference on CPU is 50-100× slower than GPU. Processing 1M+ documents
on CPU would take months and isn't practical.

---

## Safety architecture

Three layers run on every example:

1. **Converter system prompt** — frames offensive techniques in authorized
   and educational contexts, with explicit hard-refusal categories (CSAM,
   WMD synthesis, ransom templates, targeted personal info, critical
   infrastructure attacks) that always return `{"skip": true}`.

2. **Post-conversion regex validator** (`safety_validator.py`) — checks
   each generated example against 17+ pattern categories across three
   severity tiers. Tier 1 (always reject), Tier 2 (reject without redemptive
   framing), Tier 3 (flag for logging). Each rejection produces a specific
   category reason for audit and tuning.

3. **Quality filter** (`filter.py`) — LM-based quality scoring that catches
   structural and framing failures as a side effect of quality control.

The methodology is documented in [SAFETY.md](SAFETY.md), including the full
pattern lists, design rationale, known limitations, and the philosophy
(framing rather than sanitization).

This is one of the first openly documented attempts at dual-use safety in
security training data. Pattern lists are intentionally inspectable regex —
contributions and critiques welcome via issues or PRs.

---

## Versioning

- **v1.0.0** — Initial public release of the pipeline
- **v1.1.0** — Safety architecture hardening: Layer 2 validator expanded
  from 4 patterns to 17+ across 3 tiers, Layer 1 prompt updated with
  hard-refusal categories, validator-not-called bug fixed. See
  [CHANGELOG.md](CHANGELOG.md).

---

## License

**Code:** Apache 2.0 — see [LICENSE](LICENSE).

**Dataset output:** Depends on the raw input. If your raw data came from
secdata-scrapers and includes Stack Exchange content (which it does by
default), the output dataset must be released under **CC BY-SA 4.0** to
satisfy share-alike obligations. The published raw corpus
([secdata-raw](https://huggingface.co/datasets/deardaniel/secdata-raw))
is CC BY-SA 4.0 for this reason.

The pipeline preserves `license` metadata from the raw documents through
to final output, enabling license-aware filtering or attribution during
dataset publishing.

---

## Related repositories

- [secdata-scrapers](https://github.com/yourdeardaniel/secdata-scrapers) —
  collection infrastructure that produced the raw corpus
- [secdata-raw](https://huggingface.co/datasets/deardaniel/secdata-raw) —
  the 4M-document raw corpus on Hugging Face (CC BY-SA 4.0)

---

## Contributing

PRs are welcome, especially for:
- Additional safety validator patterns (see SAFETY.md for the existing
  pattern categories)
- Source-specific prompt refinements in the converter
- Quality filter improvements
- Documentation and examples

For bug reports or methodology questions, open an issue.
