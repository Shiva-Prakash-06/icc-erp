#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/or/relative/path/to/icc-erp-native.tar.gz" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
archive="$1"
if [[ "$archive" != /* ]]; then
  archive="$repo_root/$archive"
fi
test -f "$archive"

if [[ -f "$archive.sha256" ]]; then
  (cd "$(dirname "$archive")" && shasum -a 256 -c "$(basename "$archive").sha256")
fi

verify_tmp="$(mktemp -d /tmp/icc-native-verify.XXXXXX)"
cleanup() {
  find "$verify_tmp" -depth -delete
}
trap cleanup EXIT

tar -xzf "$archive" -C "$verify_tmp"
for required in app migrations run.py requirements.txt MANIFEST.sha256; do
  test -e "$verify_tmp/$required"
done

for forbidden in instance tests e2e node_modules frontend terraform .git .env; do
  test ! -e "$verify_tmp/$forbidden"
done

if find "$verify_tmp" -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.pem' -o -name '*.key' -o -iname '*credential*' -o -iname '*secret*' -o -iname '*backup*' \) -print -quit | grep -q .; then
  echo "Forbidden credential, secret, key, backup, or database file in native release" >&2
  exit 1
fi

(cd "$verify_tmp" && shasum -a 256 -c MANIFEST.sha256 >/dev/null)
python3 -m compileall -q "$verify_tmp/app" "$verify_tmp/migrations" "$verify_tmp/run.py"

file_count="$(find "$verify_tmp" -type f | wc -l | tr -d ' ')"
echo "Native runtime allowlist verified: $file_count files"
