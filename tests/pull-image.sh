#!/usr/bin/env bash
# Pull an official Docker Hub image, retrying and alternating with AWS's mirror: both
# registries rate-limit anonymous pulls from shared runners. Prints the name that worked.
# Usage: tests/pull-image.sh <image>   (e.g. debian:bookworm)
set -uo pipefail
image="${1:?image}"
for i in 1 2 3 4 5 6; do
    for c in "public.ecr.aws/docker/library/${image}" "$image"; do
        if docker pull -q "$c" >/dev/null 2>&1; then echo "$c"; exit 0; fi
    done
    sleep $((i * 15))
done
echo "could not pull ${image}" >&2
exit 1
