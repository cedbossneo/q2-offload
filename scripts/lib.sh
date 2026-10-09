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

# checkout_ref <repo-url> <ref> <dir>: clone if needed, then detach at <ref>.
checkout_ref() {
    local url="$1" ref="$2" dir="$3"
    if [ ! -d "${dir}/.git" ]; then
        git clone --quiet --filter=blob:none "$url" "$dir"
    fi
    git -C "$dir" fetch --quiet origin
    git -C "$dir" checkout --quiet --force --detach "$ref"
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

# Identifier of a firmware build: Klipper ref + hash of the patch series and build configs.
firmware_id() {
    local sum
    sum="$(cat "${Q2_ROOT}"/patches/klipper/*.patch "${Q2_ROOT}"/firmware/configs/*.config \
        | sha256sum | cut -c1-8)"
    printf '%s-%s\n' "${KLIPPER_REF:0:9}" "$sum"
}
