#!/usr/bin/env bash
# Replace the shipped panel bundle with the one the dashable-viewer Build
# workflow published for a tag, and record where it came from.
#
#   scripts/update-bundle.sh v0.11.0
#
# Downloads dashable-panel.js and its SHA-256 from that release of
# robot-one-software/dashable-viewer, verifies the checksum, writes the bundle
# to custom_components/dashable/frontend/ and rewrites viewer-source.json. The
# Release workflow later rebuilds from the same tag and refuses to publish if
# the result differs from the committed file.

set -euo pipefail

tag=${1:?usage: scripts/update-bundle.sh vX.Y.Z}
repo=robot-one-software/dashable-viewer
root=$(cd "$(dirname "$0")/.." && pwd)
dest="$root/custom_components/dashable/frontend/dashable-panel.js"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

gh release download "$tag" --repo "$repo" --pattern 'dashable-panel.js*' --dir "$tmp"
(cd "$tmp" && shasum -a 256 -c dashable-panel.js.sha256)

commit=$(gh api "repos/$repo/commits/$tag" --jq .sha)
app_commit=$(gh api "repos/$repo/contents/SOURCE.json?ref=$tag" --jq .content | base64 -d \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["app_commit"])')

cp "$tmp/dashable-panel.js" "$dest"
sha=$(shasum -a 256 "$dest" | cut -d' ' -f1)
bytes=$(wc -c < "$dest" | tr -d ' ')

cat > "$root/viewer-source.json" <<EOF
{
  "repository": "$repo",
  "tag": "$tag",
  "commit": "$commit",
  "app_commit": "$app_commit",
  "sha256": "$sha",
  "bytes": $bytes
}
EOF

echo "bundle updated from $repo@$tag: $bytes bytes, sha256 $sha"
echo "BUILD_PROVENANCE.md row: | <panel version> | \`$tag\` | \`${app_commit:0:8}\` | $bytes | \`${sha:0:16}\` |"
