# secdata-pipeline

**Requires Python 3.9 or newer.** Tested on 3.9, 3.10, 3.11, 3.12.

Converts raw security documents from [secdata-scrapers](https://github.com/yourdeardaniel/secdata-scrapers)
into annotated instruction-tuning training examples.

**Output: ~479,000 clean training examples** from ~1.37M raw documents.

---

## What it does

```
raw_docs.jsonl (1.37M docs)
  → converter.py    LLM reformats each doc as {instruction, input, output}
  → filter.py       removes low-quality, vague, and safety-failing examples
  → deduplicator.py removes near-duplicate examples (cosine similarity)
  → final_dataset.jsonl (~479,000 examples)
```

The converter uses a **safety-aware system prompt** that frames all security
content in educational and authorized-use contexts. See [SAFETY.md](SAFETY.md).

---

## Setup

```bash
git clone https://github.com/yourdeardaniel/secdata-pipeline
cd secdata-pipeline
pip install -r requirements.txt

# Copy raw data from scraper
scp user@scraper-vps:~/secdata-scrapers/data/raw/raw_docs.jsonl data/raw/

# Start vLLM on H100
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct-AWQ \
  --quantization awq --max-model-len 4096 \
  --gpu-memory-utilization 0.90 --port 8000

# Verify server
python main.py --check-model

# Run pipeline (~10 days on H100)
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
  "source_url": "https://ctftime.org/writeup/12345",
  "source_type": "ctftime"
}
```

Compatible with Axolotl, LLaMA-Factory, and HuggingFace Trainer directly.

---

## Hardware requirements

The conversion phase is the bottleneck. The pipeline works by running an LLM
over every raw document — 1.37 million of them — and asking it to reformat each
one into a training example. That requires serious GPU memory and takes time.

### What actually determines the hardware you need

**GPU memory** is the hard constraint. The converter uses Qwen 2.5 72B (AWQ
quantized), which needs ~40GB of VRAM to load and serve. Any GPU or combination
of GPUs with 40GB+ VRAM will work. Less VRAM means you have to use a smaller
model, which produces lower quality training examples.

**Throughput** determines how long it takes. The pipeline processes roughly
1,400 documents per hour on an H100 80GB. Slower GPUs will produce the same
output — just take longer, meaning more time renting the hardware.

**The deduplication phase** uses sentence embeddings, not an LLM — it's much
lighter and can run on any modern GPU or even a fast CPU.

### Recommended configurations

| Configuration | VRAM | Conversion time | Estimated cost | Notes |
|---|---|---|---|---|
| 1× H100 80GB | 80GB | ~10 days | ~$530 | Fastest single-GPU option |
| 1× A100 80GB | 80GB | ~14 days | ~$560 | Slightly slower, similar cost |
| 2× A100 40GB | 80GB total | ~14 days | ~$560 | vLLM tensor parallelism across both |
| 1× RTX 4090 | 24GB | not viable at 72B | — | Too little VRAM for this model |

**Why H100 specifically?** It's the cheapest path to completing the conversion
in a reasonable time window when renting by the hour. An H100 on Vast.ai or
RunPod costs ~$2.00–2.50/hr and processes roughly 1,400 docs/hr. At 1.37M
documents that's about 980 hours of GPU time, or ~$530 total.

**Why not a cheaper GPU?** You can use a smaller model (e.g. Qwen 2.5 32B or
14B) on a GPU with less VRAM — the pipeline works with any OpenAI-compatible
server. The tradeoff is lower quality training examples. If you're running this
on your own hardware or have access to different compute, set the model in
`config.yaml` and run `python main.py --check-model` to verify your setup works
before committing to the full run.

**Why not a CPU?** LLM inference on CPU is 50–100× slower than GPU. Processing
1.37M documents on CPU would take months and isn't practical.

### Using a different model

If you have access to different hardware, set `model_name` in `config.yaml`
to any model your server can run. Smaller models that fit in less VRAM:

- `Qwen/Qwen2.5-32B-Instruct` — needs ~20GB VRAM, good quality
- `Qwen/Qwen2.5-14B-Instruct` — needs ~10GB VRAM, acceptable quality
- `Qwen/Qwen2.5-7B-Instruct`  — needs ~6GB VRAM, lower quality

The converter prompt works with any capable instruction-tuned model. Quality
of the resulting dataset scales with model capability.

---

## Safety

Three layers of safety filtering are applied:

1. **Converter prompt** — instructs the LLM to frame content educationally
2. **Safety validator** — post-conversion check for operational attack patterns
3. **LM quality filter** — score-based filter that also catches framing failures

See [SAFETY.md](SAFETY.md) for full documentation.

---

## License

**Code:** Apache 2.0 — see [LICENSE](LICENSE).

**Dataset output:** Depends on what was scraped. If your raw data came from
secdata-scrapers and includes Stack Exchange content (the default), the
output dataset must be released under **CC BY-SA 4.0** to satisfy
share-alike obligations. See `secdata-scrapers/LICENSING_NOTES.md` for the
full discussion.

The pipeline preserves `license` metadata from the raw documents, so
license-aware filtering or attribution is possible during dataset publishing.
