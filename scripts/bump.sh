#!/usr/bin/env bash
# Move every upstream pin in VERSIONS to its latest version (branch head or latest release).
# Prints a summary of the changes; exit 0 even when nothing changed. Used by bump.yml.
# The Katapult deployers (DEPLOYER_*) are never bumped: they are flashed over the stock
# bootloader and a bad one bricks an MCU, so they only change by hand.
set -Eeuo pipefail
. "$(dirname "$0")/lib.sh"
file="${Q2_ROOT}/VERSIONS"

set_var() {
    local key="$1" new="$2" old
    old="$(sed -n "s/^${key}=//p" "$file")"
    [ -n "$new" ] || die "could not resolve ${key}"
    [ "$old" = "$new" ] && return 0
    sed -i "s#^${key}=.*#${key}=${new}#" "$file"
    echo "${key}: ${old} -> ${new}"
}

for name in KLIPPER MOONRAKER KATAPULT AUTOPA TIMELAPSE MAINSAIL_CONFIG KIAUH; do
    repo_var="${name}_REPO"; branch_var="${name}_BRANCH"
    sha="$(git ls-remote "${!repo_var}" "refs/heads/${!branch_var}" | cut -f1)"
    set_var "${name}_REF" "$sha"
done

latest_release() {
    download "https://api.github.com/repos/$1/releases/latest" - \
        ${GITHUB_TOKEN:+-H "Authorization: Bearer ${GITHUB_TOKEN}"} | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
}

# ghcr_index <image> <tag>: the tag's multi-arch index on GHCR, byte for byte (its sha256 is
# the digest)
ghcr_index() {
    local image="$1" tag="$2" token
    token="$(download "https://ghcr.io/token?scope=repository:${image}:pull" - | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
    download "https://ghcr.io/v2/${image}/manifests/${tag}" - -H "Authorization: Bearer ${token}" \
        -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json"
}

# Only take a container release once its image is actually published
ghcr_has_tag() { ghcr_index "$1" "$2" >/dev/null; }

# Obico's ML API: the image behind Obico's "release" tag, when it covers x86_64 and arm64.
# Prints the commit it was built from (its revision annotation).
obico_release_commit() {
    python3 - "$1" <<'EOF'
import json, sys
index = json.load(open(sys.argv[1]))
platforms = {(m.get("platform") or {}).get("architecture") for m in index.get("manifests", [])}
if {"amd64", "arm64"} <= platforms:
    print(index.get("annotations", {}).get("org.opencontainers.image.revision", ""))
EOF
}

# Commit of a tag (the commit an annotated tag points to)
tag_commit() {
    git ls-remote "$1" "refs/tags/$2" "refs/tags/$2^{}" | sort -k2 | tail -1 | cut -f1
}

# release_contains <owner/repo> <release commit> <commit>: the release has that commit
release_contains() {
    local status
    status="$(download "https://api.github.com/repos/$1/compare/$3...$2" - \
        ${GITHUB_TOKEN:+-H "Authorization: Bearer ${GITHUB_TOKEN}"} \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    [ "$status" = identical ] || [ "$status" = ahead ]
}

# Happy Hare: a commit pinned ahead of the latest release stays until a release contains it
v="$(latest_release moggieuk/Happy-Hare)"
ref="$(tag_commit "$HAPPY_HARE_REPO" "$v")"
if release_contains moggieuk/Happy-Hare "$ref" "$(sed -n 's/^HAPPY_HARE_REF=//p' "$file")"; then
    set_var HAPPY_HARE_RELEASE "$v"
    set_var HAPPY_HARE_REF "$ref"
fi
set_var MAINSAIL_VERSION "$(latest_release mainsail-crew/mainsail)"
set_var FLUIDD_VERSION "$(latest_release fluidd-core/fluidd)"
v="$(latest_release Donkie/Spoolman)"
ghcr_has_tag donkie/spoolman "${v#v}" && set_var SPOOLMAN_VERSION "$v"
index="$(mktemp)"
if ghcr_index "${OBICO_ML_API_IMAGE#ghcr.io/}" release > "$index" \
        && commit="$(obico_release_commit "$index")" && [ -n "$commit" ]; then
    set_var OBICO_ML_API_DIGEST "sha256:$(sha256sum "$index" | cut -d' ' -f1)"
    set_var OBICO_SERVER_REF "$commit"
fi
rm -f "$index"
true
