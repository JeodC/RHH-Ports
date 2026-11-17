#!/usr/bin/env bash

set -euo pipefail

REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CATALOG_URL="https://github.com/${REPO}/releases/download/ports-latest/ports.json"

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

python3 "$ROOT/buildtools/generate_pm_catalog.py" --output "$OUT"

SRC_JSON="$ROOT/docs/010_rhh.source.json"

# Skip images if they haven't changed
if curl -sfL -o "$OUT/current_catalog.json" "$CATALOG_URL"; then
  if cmp -s "$OUT/current_catalog.json" "$OUT/ports.json"; then
    echo "PortMaster catalog unchanged; skipping upload."
    exit 0
  fi
  OLD_MD5=$(jq -r '.utils["images.zip"].md5 // empty' "$OUT/current_catalog.json" || true)
  NEW_MD5=$(md5sum "$OUT/images.zip" | awk '{print $1}')
  if [[ -n "$OLD_MD5" && "$OLD_MD5" == "$NEW_MD5" ]]; then
    echo "images.zip unchanged; uploading catalog only."
    gh release upload ports-latest "$OUT/ports.json" "$SRC_JSON" --clobber
    exit 0
  fi
fi

gh release upload ports-latest \
  "$OUT/ports.json" \
  "$OUT/images.zip" \
  "$SRC_JSON" \
  --clobber
