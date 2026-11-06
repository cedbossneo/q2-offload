#!/usr/bin/env bash
# Host stack install on a minimal Debian/Ubuntu image: the installer in CI mode, its
# update path, the unattended update's user phase, and the config validation after each.
# Runs as root in a throwaway container; the installer itself runs as user "q2" with sudo,
# as on a real host.
# Usage: tests/host/run.sh <repo> <firmware-dir>
set -euo pipefail
REPO="${1:?repo}"; FW="${2:?firmware dir}"

. /etc/os-release
echo "== ${PRETTY_NAME} ($(uname -m))"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends sudo ca-certificates >/dev/null

useradd -m -s /bin/bash q2
echo 'q2 ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/q2
cp -r "$REPO" /home/q2/q2-offload
cp -r "$FW" /home/q2/dist
chown -R q2:q2 /home/q2/q2-offload /home/q2/dist

logs() {
    tail -100 /home/q2/.config/q2-offload/happy-hare-install.log 2>/dev/null || true
    ls -la /home/q2/printer_data/config /home/q2/printer_data/config/mmu/base 2>/dev/null || true
}
trap 'logs' ERR
# A login shell, as a real user: Happy Hare refuses to install under sudo (SUDO_USER set)
as_q2() { su - q2 -c "cd ~/q2-offload && $*"; }
echo "== install"
as_q2 './install.sh host --ci --yes && scripts/validate-config.sh ~/dist'
echo "== re-run (update path must be idempotent)"
as_q2 './install.sh host --ci --yes && scripts/validate-config.sh ~/dist'
echo "== unattended update, user phase (what Moonraker triggers)"
as_q2 './install.sh _update-user --unattended --ci && scripts/validate-config.sh ~/dist'
