#!/usr/bin/env python3
"""
secdata-pipeline — Cybersecurity Dataset Pipeline
==================================================
Converts raw security documents from secdata-scrapers into
annotated instruction-tuning examples.

Requires: raw_docs.jsonl from secdata-scrapers in data/raw/

Usage:
    python main.py --check-model      verify LLM server is running
    python main.py --convert-only     convert raw docs to pairs
    python main.py --filter-only      quality filter converted pairs
    python main.py --dedup-only       deduplicate filtered pairs
    python main.py --stats            show current progress
    python main.py                    run full pipeline

LLM server (one of):
  vLLM on H100:  python -m vllm.entrypoints.openai.api_server
                   --model Qwen/Qwen2.5-72B-Instruct-AWQ --port 8000
  Ollama on GPU: ollama serve && ollama pull qwen2.5:32b

Safety:
  This pipeline uses a safety-aware converter prompt that frames all
  security content in educational and authorized-use contexts.
  An additional post-conversion safety validator checks every example
  before it enters the dataset.
  See SAFETY.md for full documentation.
"""
import argparse, os, sys, yaml
from openai import OpenAI
from utils import ensure_dirs, count_lines
from processing import converter, filter as qual_filter, deduplicator


def load_config(path):
    with open(path) as f: return yaml.safe_load(f)


def setup_paths(cfg):
    ensure_dirs(cfg["output"]["raw_dir"],
                cfg["output"]["processed_dir"],
                os.path.dirname(cfg["output"]["final_file"]),
                os.path.dirname(cfg["output"]["checkpoint_file"]))
    return {
        "raw":        os.path.join(cfg["output"]["raw_dir"], "raw_docs.jsonl"),
        "processed":  os.path.join(cfg["output"]["processed_dir"], "converted.jsonl"),
        "filtered":   os.path.join(cfg["output"]["processed_dir"], "filtered.jsonl"),
        "final":      cfg["output"]["final_file"],
        "checkpoint": cfg["output"]["checkpoint_file"],
    }


def print_stats(paths):
    rows = [
        ("Raw documents",        paths["raw"]),
        ("Converted pairs",      paths["processed"]),
        ("After quality filter", paths["filtered"]),
        ("Final dataset",        paths["final"]),
    ]
    print("\n=== Pipeline Stats ===")
    for label, path in rows:
        n = count_lines(path)
        print(f"  {'✓' if n>0 else '·'} {label:<26} {n:>10,}")
    print()


def check_model(cfg):
    url = cfg["api"].get("model_base_url", "http://localhost:8000/v1")
    print(f"[check] Testing model server at {url}...")
    try:
        client = OpenAI(base_url=url,
                        api_key=cfg["api"].get("model_api_key","none"),
                        timeout=10)
        models = client.models.list()
        print(f"[check] ✓ Reachable. Models: {[m.id for m in models.data]}")
        return True
    except Exception as e:
        print(f"[check] ✗ Cannot reach server: {e}")
        print("\nStart vLLM:  python -m vllm.entrypoints.openai.api_server \\")
        print("               --model Qwen/Qwen2.5-72B-Instruct-AWQ --port 8000")
        print("Start Ollama: ollama serve && ollama pull qwen2.5:32b")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="secdata-pipeline — convert raw docs to training examples")
    parser.add_argument("--config",       default="config.yaml")
    parser.add_argument("--check-model",  action="store_true")
    parser.add_argument("--convert-only", action="store_true")
    parser.add_argument("--filter-only",  action="store_true")
    parser.add_argument("--dedup-only",   action="store_true")
    parser.add_argument("--stats",        action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Config not found: {args.config}"); sys.exit(1)

    cfg   = load_config(args.config)
    paths = setup_paths(cfg)

    if args.stats:
        print_stats(paths); return

    if args.check_model:
        check_model(cfg); return

    if args.convert_only:
        if count_lines(paths["raw"]) == 0:
            print("No raw documents found. Run secdata-scrapers first."); return
        if not check_model(cfg): return
        converter.run(cfg, paths["raw"], paths["processed"], paths["checkpoint"])
        print_stats(paths); return

    if args.filter_only:
        qual_filter.run(cfg, paths["processed"], paths["filtered"], paths["checkpoint"])
        print_stats(paths); return

    if args.dedup_only:
        deduplicator.deduplicate(cfg, paths["filtered"], paths["final"])
        print_stats(paths); return

    # Full pipeline
    print_stats(paths)
    if count_lines(paths["raw"]) == 0:
        print("No raw documents. Run secdata-scrapers and copy raw_docs.jsonl here.")
        return
    if not check_model(cfg): return
    print("\nStarting full pipeline. This takes ~10 days on H100.")
    input("Press Enter to continue, Ctrl+C to cancel...\n")
    converter.run(cfg, paths["raw"], paths["processed"], paths["checkpoint"])
    qual_filter.run(cfg, paths["processed"], paths["filtered"], paths["checkpoint"])
    deduplicator.deduplicate(cfg, paths["filtered"], paths["final"])
    print("\n=== Pipeline complete ===")
    print_stats(paths)


if __name__ == "__main__":
    main()
