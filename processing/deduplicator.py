"""
Deduplicator — finds and removes near-duplicate training examples.
Uses sentence embeddings + cosine similarity.

Key optimizations:
  - Pre-allocated numpy array (no rebuild per iteration)
  - Batched similarity comparison
  - Memory-efficient for 250k+ examples
"""
import numpy as np
from tqdm import tqdm
from utils import load_jsonl, save_jsonl


def deduplicate(cfg, filtered_file, final_file):
    d_cfg = cfg["processing"]["deduplication"]
    if not d_cfg.get("enabled", True):
        print("[dedup] Disabled — copying filtered → final.")
        save_jsonl(final_file, load_jsonl(filtered_file))
        return

    threshold  = d_cfg.get("similarity_threshold", 0.88)
    model_name = d_cfg.get("model", "all-MiniLM-L6-v2")
    batch_size = d_cfg.get("batch_size", 256)

    examples = load_jsonl(filtered_file)
    n = len(examples)
    if n == 0:
        print("[dedup] No examples to deduplicate.")
        return

    print(f"[dedup] Loading embedding model: {model_name}")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[dedup] sentence-transformers not installed.")
        save_jsonl(final_file, examples)
        return

    model = SentenceTransformer(model_name)
    texts = [ex.get("instruction", "") + " " + ex.get("output", "")[:200]
             for ex in examples]

    print(f"[dedup] Encoding {n:,} examples...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    dim = embeddings.shape[1]
    print(f"[dedup] Embeddings shape: {embeddings.shape} ({embeddings.nbytes / 1e6:.0f} MB)")

    print(f"[dedup] Running deduplication (threshold={threshold})...")

    # Pre-allocate kept-embeddings matrix to avoid expensive rebuild per iteration
    kept_indices = np.empty(n, dtype=np.int32)
    kept_embs    = np.empty((n, dim), dtype=np.float32)
    kept_count   = 0

    with tqdm(total=n, desc="Deduplicating", unit="ex") as pbar:
        for i in range(n):
            emb = embeddings[i]
            if kept_count == 0:
                kept_indices[kept_count] = i
                kept_embs[kept_count] = emb
                kept_count += 1
                pbar.update(1)
                continue

            # Vectorized similarity against all currently-kept embeddings.
            # Slice is a view — zero copy.
            sims = kept_embs[:kept_count] @ emb
            if float(sims.max()) < threshold:
                kept_indices[kept_count] = i
                kept_embs[kept_count] = emb
                kept_count += 1

            pbar.update(1)

    deduped = [examples[i] for i in kept_indices[:kept_count]]
    removed = n - len(deduped)
    save_jsonl(final_file, deduped)

    print(f"\n[dedup] Input:   {n:,}")
    print(f"[dedup] Removed: {removed:,} ({removed/max(n,1):.1%})")
    print(f"[dedup] Output:  {len(deduped):,} → {final_file}")
