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

for name in KLIPPER HAPPY_HARE MOONRAKER KATAPULT AUTOPA TIMELAPSE MAINSAIL_CONFIG KIAUH; do
    repo_var="${name}_REPO"; branch_var="${name}_BRANCH"
    sha="$(git ls-remote "${!repo_var}" "refs/heads/${!branch_var}" | cut -f1)"
    set_var "${name}_REF" "$sha"
done

latest_release() {
    curl -fsSL ${GITHUB_TOKEN:+-H "Authorization: Bearer ${GITHUB_TOKEN}"} \
        "https://api.github.com/repos/$1/releases/latest" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
}

# Only take a container release once its image is actually published
ghcr_has_tag() {
    local image="$1" tag="$2" token
    token="$(curl -fsSL "https://ghcr.io/token?scope=repository:${image}:pull" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
    curl -fsS -o /dev/null -H "Authorization: Bearer ${token}" \
        -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
        "https://ghcr.io/v2/${image}/manifests/${tag}"
}

set_var MAINSAIL_VERSION "$(latest_release mainsail-crew/mainsail)"
set_var FLUIDD_VERSION "$(latest_release fluidd-core/fluidd)"
v="$(latest_release Donkie/Spoolman)"
ghcr_has_tag donkie/spoolman "${v#v}" && set_var SPOOLMAN_VERSION "$v"
v="$(latest_release oliverbravery/printguard)"
ghcr_has_tag oliverbravery/printguard "${v#v}" && set_var PRINTGUARD_VERSION "$v"
true
