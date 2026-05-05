# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
