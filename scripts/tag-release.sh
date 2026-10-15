#!/usr/bin/env bash
# Version tags followed by Moonraker's update channels (channel: in host/moonraker.conf):
#   tag-release.sh beta [<commit>]   vYYYY.MM.DD-beta.N on a commit of main that passed CI
#   tag-release.sh stable [<tag>]    vYYYY.MM.DD[.N] on the commit of a beta tag tested on a
#                                    printer (default: the latest beta)
# Tags are annotated: git describe, which Moonraker uses for the installed version, prefers
# them over the lightweight fw-* firmware release tags that sit on the same commits.
# Used by ci.yml, bump.yml and promote.yml.
set -Eeuo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }
tag_exists() { git rev-parse -q --verify "refs/tags/$1" >/dev/null; }

create() {
    local tag="$1" commit="$2"
    git -c user.name=q2-offload-bot -c user.email=q2-offload-bot@users.noreply.github.com \
        tag -a "$tag" -m "q2-offload ${tag}" "$commit"
    git push -q origin "refs/tags/${tag}"
    echo "${tag} -> ${commit}"
}

kind="${1:-}"
git fetch -q --tags origin main

case "$kind" in
    beta)
        commit="$(git rev-parse "${2:-HEAD}^{commit}")"
        existing="$(git tag --points-at "$commit" -l 'v*-beta.*' | head -1)"
        [ -z "$existing" ] || { echo "${commit} is already ${existing}"; exit 0; }
        base="v$(date -u +%Y.%m.%d)"
        n=1
        while tag_exists "${base}-beta.${n}"; do n=$((n + 1)); done
        create "${base}-beta.${n}" "$commit"
        ;;
    stable)
        src="${2:-}"
        if [ -z "$src" ]; then
            src="$(git tag -l 'v*-beta.*' --merged origin/main --sort=-creatordate | head -1)"
            [ -n "$src" ] || die "no beta tag on main yet"
        fi
        [[ "$src" =~ ^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}-beta\.[0-9]+$ ]] || die "'${src}' is not a beta tag (vYYYY.MM.DD-beta.N)"
        tag_exists "$src" || die "no tag ${src}"
        commit="$(git rev-parse "${src}^{commit}")"
        git merge-base --is-ancestor "$commit" origin/main || die "${src} is not on main"
        existing="$(git tag --points-at "$commit" -l 'v*' | grep -v -- '-beta\.' | head -1 || true)"
        [ -z "$existing" ] || { echo "${src} is already stable as ${existing}"; exit 0; }
        tag="${src%-beta.*}"
        n=1
        while tag_exists "$tag"; do tag="${src%-beta.*}.${n}"; n=$((n + 1)); done
        create "$tag" "$commit"
        ;;
    *)
        die "usage: tag-release.sh beta [<commit>] | stable [<beta tag>]"
        ;;
esac
