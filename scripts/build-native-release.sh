#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:-dist/icc-erp-native.tar.gz}"
if [[ "$output" != /* ]]; then
  output="$repo_root/$output"
fi

if [[ "${SKIP_UI_BUILD:-0}" != "1" ]]; then
  cd "$repo_root"
  npm run typecheck
  npm run build:ui
  npm run check:assets
fi

release_tmp="$(mktemp -d /tmp/icc-native-release.XXXXXX)"
cleanup() {
  find "$release_tmp" -depth -delete
}
trap cleanup EXIT

stage="$release_tmp/stage"
mkdir "$stage"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '*.pyo' "$repo_root/app" "$stage/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '*.pyo' "$repo_root/migrations" "$stage/"
cp "$repo_root/run.py" "$repo_root/requirements.txt" "$stage/"

(
  cd "$stage"
  find . -type f ! -name MANIFEST.sha256 -print | LC_ALL=C sort | while IFS= read -r file; do
    shasum -a 256 "$file"
  done > MANIFEST.sha256
)

mkdir -p "$(dirname "$output")"
archive_tmp="$release_tmp/icc-erp-native.tar.gz"
tar -czf "$archive_tmp" -C "$stage" .
mv "$archive_tmp" "$output"
(
  cd "$(dirname "$output")"
  shasum -a 256 "$(basename "$output")" > "$(basename "$output").sha256"
)

echo "Native release: $output"
echo "Checksum: $output.sha256"
