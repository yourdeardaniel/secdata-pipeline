# secdata-pipeline

**Requires Python 3.9 or newer.** Tested on 3.9, 3.10, 3.11, 3.12.

Converts raw security documents from [secdata-scrapers](https://github.com/your-username/secdata-scrapers)
into annotated instruction-tuning training examples.

**Output: ~479,000 clean training examples** from ~1.37M raw documents.

---

## What it does

```
raw_docs.jsonl (1.37M docs)
  → converter.py   LLM reformats each doc as {instruction, input, output}
  → filter.py      removes low-quality, vague, and safety-failing examples
  → deduplicator.py removes near-duplicate examples (cosine similarity)
  → final_dataset.jsonl (~479,000 examples)
```

The converter uses a **safety-aware system prompt** that frames all security
content in educational and authorized-use contexts. See [SAFETY.md](SAFETY.md).

---

## Setup

```bash
git clone https://github.com/your-username/secdata-pipeline
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

| Phase | Hardware | Duration | Cost |
|---|---|---|---|
| Conversion | H100 80GB | ~10 days | ~$478 |
| Filtering | H100 (same) | ~1 day | ~$48 |
| Deduplication | RTX 4090 | ~6 hrs | ~$3 |

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
