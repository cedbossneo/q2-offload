# shellcheck shell=bash
# Shared helpers for install.sh, the build scripts and CI. Source, do not execute.

Q2_ROOT="${Q2_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# shellcheck source=../VERSIONS
. "${Q2_ROOT}/VERSIONS"

if [ -t 1 ]; then
    C_INFO=$'\e[36m'; C_OK=$'\e[32m'; C_WARN=$'\e[33m'; C_ERR=$'\e[31m'; C_OFF=$'\e[0m'
else
    C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_OFF=''
fi

info() { printf '%s==>%s %s\n' "${C_INFO}" "${C_OFF}" "$*"; }
ok()   { printf '%s ok%s %s\n' "${C_OK}" "${C_OFF}" "$*"; }
warn() { printf '%sWARNING:%s %s\n' "${C_WARN}" "${C_OFF}" "$*" >&2; }
die()  { printf '%sERROR:%s %s\n' "${C_ERR}" "${C_OFF}" "$*" >&2; exit 1; }

# Ask a yes/no question; default answer in $2 (y|n). ASSUME_YES=1 answers yes.
confirm() {
    local prompt="$1" default="${2:-n}" reply
    if [ "${ASSUME_YES:-0}" = 1 ]; then return 0; fi
    [ -t 0 ] || die "'${prompt}' needs an answer: run in a terminal or pass --yes"
    read -r -p "${prompt} [$( [ "$default" = y ] && echo Y/n || echo y/N )] " reply
    reply="${reply:-$default}"
    [[ "$reply" =~ ^[Yy] ]]
}

# Ask the user to type an exact phrase (used before anything that can brick an MCU).
confirm_phrase() {
    local phrase="$1" reply
    [ -t 0 ] || die "Interactive confirmation required for: ${phrase}"
    read -r -p "Type '${phrase}' to continue: " reply
    [ "$reply" = "$phrase" ] || die "Confirmation did not match, nothing was done"
}

# download <url> <file|-> [curl options...]: curl with retries, so one GitHub 5xx or timeout
# does not fail an install or the daily upstream update. "-" writes to stdout. Errors that
# are not transient (404) fail at once.
DOWNLOAD_RETRIES=5
DOWNLOAD_RETRY_DELAY=10
DOWNLOAD_CONNECT_TIMEOUT=20
download() {
    local url="$1" out="$2"
    shift 2
    curl -fsSL --retry "$DOWNLOAD_RETRIES" --retry-delay "$DOWNLOAD_RETRY_DELAY" \
        --connect-timeout "$DOWNLOAD_CONNECT_TIMEOUT" "$@" -o "$out" "$url"
}

# checkout_ref <repo-url> <ref> <dir>: clone if needed, then detach at <ref>.
# A clone left by another install (a fork, a single-branch or shallow clone) may not have
# <ref> ("fatal: unable to read tree"): its origin is pointed at <repo-url> and <ref> is
# fetched by itself when the branches did not bring it.
checkout_ref() {
    local url="$1" ref="$2" dir="$3" origin
    if [ ! -d "${dir}/.git" ]; then
        git clone --quiet --filter=blob:none "$url" "$dir"
    fi
    origin="$(git -C "$dir" remote get-url origin 2>/dev/null || true)"
    if [ "${origin%.git}" != "${url%.git}" ]; then
        warn "${dir} comes from ${origin:-no origin}, switching it to ${url}"
        git -C "$dir" remote set-url origin "$url" 2>/dev/null || git -C "$dir" remote add origin "$url"
    fi
    git -C "$dir" fetch --quiet origin
    git -C "$dir" cat-file -e "${ref}^{commit}" 2>/dev/null || git -C "$dir" fetch --quiet origin "$ref"
    git -C "$dir" checkout --quiet --force --detach "$ref"
}

# obico_ml_api_image: Obico's ML API image pinned in VERSIONS
obico_ml_api_image() { echo "${OBICO_ML_API_IMAGE}@${OBICO_ML_API_DIGEST}"; }

# obico_ml_api_intel_image: q2-offload's Intel GPU build of the same obico-server commit. Its tag
# follows that commit and detect/ml-api/Containerfile.intel
obico_ml_api_intel_image() {
    local recipe
    recipe="$(sha256sum "${Q2_ROOT}/detect/ml-api/Containerfile.intel" | cut -c1-8)"
    echo "${OBICO_ML_API_INTEL_IMAGE}:${OBICO_SERVER_REF:0:12}-${recipe}"
}

# pull_image <image> [prefix...]: docker pull with retries, docker run through the prefix (e.g. sudo)
pull_image() {
    local image="$1" i
    shift
    for i in 1 2 3; do
        "$@" docker pull -q "$image" >/dev/null && return 0
        [ "$i" = 3 ] || sleep $((i * 10))
    done
    warn "could not download ${image}: is ghcr.io reachable?"
    return 1
}

# apply_patches <git-dir> <patch-dir> <branch>: build <branch> = HEAD + every patch.
# A patch that no longer applies but reverse-applies is already upstream: skipped.
apply_patches() {
    local dir="$1" pdir="$2" branch="$3" p name
    git -C "$dir" checkout --quiet -B "$branch"
    for p in "$pdir"/*.patch; do
        [ -e "$p" ] || continue
        name="$(basename "$p")"
        if git -C "$dir" apply --check "$p" 2>/dev/null; then
            if head -1 "$p" | grep -q '^From '; then
                git -C "$dir" -c user.name=q2-offload -c user.email=q2-offload@users.noreply.github.com \
                    am --quiet --committer-date-is-author-date "$p"
            else
                git -C "$dir" apply "$p"
                git -C "$dir" add -A
                git -C "$dir" -c user.name=q2-offload -c user.email=q2-offload@users.noreply.github.com \
                    commit --quiet -m "q2-offload: ${name%.patch}"
            fi
            ok "patch ${name}"
        elif git -C "$dir" apply --reverse --check "$p" 2>/dev/null; then
            ok "patch ${name} (already upstream, skipped)"
        else
            die "patch ${name} does not apply to $(git -C "$dir" rev-parse --short HEAD)"
        fi
    done
}

# Identifier of a firmware build: Klipper ref + hash of the build configs and of the patches
# that reach the MCU build. A host-only patch (klippy/ only) must not ask users to reflash.
firmware_id() {
    local sum p fw_patches=()
    for p in "${Q2_ROOT}"/patches/klipper/*.patch; do
        grep '^diff --git a/' "$p" | grep -qv '^diff --git a/klippy/' && fw_patches+=("$p")
    done
    sum="$(cat "${fw_patches[@]}" "${Q2_ROOT}"/firmware/configs/*.config \
        | sha256sum | cut -c1-8)"
    printf '%s-%s\n' "${KLIPPER_REF:0:9}" "$sum"
}
