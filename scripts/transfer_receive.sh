#!/bin/bash
# ============================================================
# transfer_receive.sh — Run on the RECEIVING VPS
# ============================================================
# Downloads and decompresses files from the sending VPS.
# The sending VPS must be running transfer_send.sh first.
#
# Usage:
#   bash scripts/transfer_receive.sh SENDER_IP PORT MODE
#
# Examples:
#   bash scripts/transfer_receive.sh 12.34.56.78 8888 raw
#   bash scripts/transfer_receive.sh 12.34.56.78 8888 filtered
#   bash scripts/transfer_receive.sh 12.34.56.78 8888 final

set -e

SENDER_IP="$1"
PORT="${2:-8888}"
MODE="${3:-raw}"

if [ -z "$SENDER_IP" ]; then
    echo "Usage: bash transfer_receive.sh SENDER_IP [PORT] [raw|filtered|final]"
    echo "Example: bash transfer_receive.sh 12.34.56.78 8888 raw"
    exit 1
fi

BASE_URL="http://$SENDER_IP:$PORT"
DOWNLOAD_DIR="/tmp/transfer_receive"
mkdir -p "$DOWNLOAD_DIR"

echo ""
echo "=== Transfer Receiver ==="
echo "Downloading from: $BASE_URL"
echo "Mode: $MODE"
echo ""

# ── Download with resume support ─────────────────────────────

download_and_verify() {
    local filename="$1"
    local dest_path="$2"
    local url="$BASE_URL/${filename}.gz"
    local checksum_url="$BASE_URL/${filename}.gz.md5"
    local local_gz="$DOWNLOAD_DIR/${filename}.gz"

    echo "  Downloading $filename..."

    # download with wget — -c enables resume
    wget -c --show-progress "$url" -O "$local_gz"

    # verify checksum
    if wget -q "$checksum_url" -O "$local_gz.md5.remote" 2>/dev/null; then
        expected=$(cat "$local_gz.md5.remote")
        actual=$(md5sum "$local_gz" | awk '{print $1}')
        if [ "$expected" = "$actual" ]; then
            echo "  ✓ Checksum verified"
        else
            echo "  ✗ Checksum MISMATCH — file may be corrupt, try again"
            echo "    Expected: $expected"
            echo "    Got:      $actual"
            exit 1
        fi
    fi

    # decompress
    ensure_dirs "$dest_path"
    echo "  Decompressing → $dest_path"
    gunzip -c "$local_gz" > "$dest_path"
    echo "  ✓ Done: $(du -sh $dest_path | cut -f1)"

    # clean up compressed file
    rm -f "$local_gz" "$local_gz.md5.remote"
}

ensure_dirs() {
    mkdir -p "$(dirname $1)"
}

# ── Download files based on mode ─────────────────────────────

case "$MODE" in
    raw|"4090-to-h100")
        echo "Receiving: raw_docs.jsonl + checkpoint (4090 → H100)"
        download_and_verify "raw_docs.jsonl"  "data/raw/raw_docs.jsonl"
        download_and_verify "checkpoint.json" "data/checkpoint.json"
        ;;
    filtered|"h100-to-4090")
        echo "Receiving: filtered.jsonl + checkpoint (H100 → 4090)"
        download_and_verify "filtered.jsonl"  "data/processed/filtered.jsonl"
        download_and_verify "checkpoint.json" "data/checkpoint.json"
        ;;
    final|"to-runpod")
        echo "Receiving: final_dataset.jsonl (→ RunPod A100)"
        download_and_verify "final_dataset.jsonl" "data/final_dataset.jsonl"
        ;;
    all)
        echo "Receiving: all files"
        download_and_verify "raw_docs.jsonl"     "data/raw/raw_docs.jsonl"
        download_and_verify "filtered.jsonl"     "data/processed/filtered.jsonl"
        download_and_verify "final_dataset.jsonl" "data/final_dataset.jsonl"
        download_and_verify "checkpoint.json"    "data/checkpoint.json"
        ;;
    *)
        echo "Unknown mode: $MODE"
        exit 1
        ;;
esac

echo ""
echo "=== Transfer complete ==="
echo ""

# ── Show what to do next ─────────────────────────────────────

case "$MODE" in
    raw|"4090-to-h100")
        echo "Next steps on this H100 VPS:"
        echo "  python main.py --check-model   # verify vLLM is running"
        echo "  python main.py --convert-only  # start conversion"
        echo "  python main.py --filter-only   # then filtering"
        echo ""
        echo "When done, run on this H100:"
        echo "  bash scripts/transfer_send.sh filtered"
        ;;
    filtered|"h100-to-4090")
        echo "Next steps on this 4090 VPS:"
        echo "  python main.py --dedup-only    # run deduplication"
        echo ""
        echo "When done, run on this 4090:"
        echo "  bash scripts/transfer_send.sh final"
        echo "  # Then receive on RunPod A100 for fine-tuning"
        ;;
    final|"to-runpod")
        echo "Next steps on this RunPod A100:"
        echo "  # Follow the Axolotl fine-tuning guide"
        echo "  # Your dataset is at: data/final_dataset.jsonl"
        ;;
esac
