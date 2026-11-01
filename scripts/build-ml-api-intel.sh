#!/usr/bin/env bash
# Build q2-offload's Intel GPU image of Obico's ML API (detect/ml-api/Containerfile.intel) from
# obico-server's ml_api at OBICO_SERVER_REF. CI only: hosts download the published image.
# Usage: scripts/build-ml-api-intel.sh <image>
set -Eeuo pipefail
. "$(dirname "$0")/lib.sh"
image="${1:?image}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

info "obico-server ml_api at ${OBICO_SERVER_REF:0:12}"
git init --quiet "${work}/src"
git -C "${work}/src" remote add origin "$OBICO_SERVER_REPO"
git -C "${work}/src" sparse-checkout set ml_api
git -C "${work}/src" fetch --quiet --depth 1 --filter=blob:none origin "$OBICO_SERVER_REF"
git -C "${work}/src" checkout --quiet --detach FETCH_HEAD

# Docker Hub rate-limits anonymous pulls from shared runners: its ECR mirror as a fallback
base=ubuntu:24.04
for i in 1 2 3 4; do
    docker pull -q "$base" >/dev/null 2>&1 && break
    docker pull -q "public.ecr.aws/docker/library/${base}" >/dev/null 2>&1 \
        && docker tag "public.ecr.aws/docker/library/${base}" "$base" && break
    [ "$i" = 4 ] && die "could not pull ${base}"
    sleep $((i * 15))
done

info "Building ${image}"
docker build -q -f "${Q2_ROOT}/detect/ml-api/Containerfile.intel" \
    --label "org.opencontainers.image.source=https://github.com/cedbossneo/q2-offload" \
    --label "org.opencontainers.image.description=Obico's ML API (obico-server ${OBICO_SERVER_REF}) on Intel GPUs through OpenVINO" \
    --label "org.opencontainers.image.licenses=AGPL-3.0" \
    -t "$image" "${work}/src/ml_api" >/dev/null
ok "$image"
