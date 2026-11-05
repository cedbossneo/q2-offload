# shellcheck shell=bash
# Printer-board side of install.sh, driven over SSH. Source after lib.sh and host.sh.

# Account on the printer board, saved in settings.env. Stock firmware 01.01.02+ moves /home/mks
# to /home/qidi behind a symlink, but mks reportedly keeps its login and the qidi password is
# not documented, so mks stays the default.
PRINTER_USER="${PRINTER_USER:-mks}"
PRINTER_WORK="/home/${PRINTER_USER}/q2-offload"
SSH_OPTS=(-o ConnectTimeout=10 -o ServerAliveInterval=15)
# Unattended update: never wait for a password
[ "${UNATTENDED:-0}" = 1 ] && SSH_OPTS+=(-o BatchMode=yes)

pssh() { ssh "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" "$@"; }
# Root commands. After "setup", a sudoers rule allows exactly this command without a
# password; before that, -tt lets sudo ask for it (stock Qidi image: "makerbase").
proot() { ssh -tt "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" sudo /bin/bash "${PRINTER_WORK}/q2-printer.sh" "$@"; }

# Before a first conversion, with no change to the MCUs: can this account work here, and does
# the stock image have what the flash needs? Stops with the reason before anything is flashed.
printer_check_stock() {
    proot stock-check || die "the printer is not ready for a first conversion; nothing was flashed. See docs/recovery.md"
}

printer_ssh_key() {
    if ssh -o BatchMode=yes "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" true 2>/dev/null; then
        return 0
    fi
    info "Setting up SSH key access to ${PRINTER_USER}@${PRINTER_IP} (mks: stock password makerbase)"
    [ -f "${HOME}/.ssh/id_ed25519" ] || ssh-keygen -q -t ed25519 -N '' -f "${HOME}/.ssh/id_ed25519"
    ssh-copy-id -i "${HOME}/.ssh/id_ed25519.pub" "${PRINTER_USER}@${PRINTER_IP}" >/dev/null
    ssh -o BatchMode=yes "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" true \
        || die "SSH key login to the printer failed"
}

printer_push() {
    local tmp
    # On 01.01.02+ the home belongs to qidi: root has to create our directory
    if ! pssh "mkdir -p ${PRINTER_WORK}" 2>/dev/null; then
        info "Creating ${PRINTER_WORK} on the printer (printer sudo password)"
        ssh -tt "${SSH_OPTS[@]}" "${PRINTER_USER}@${PRINTER_IP}" sudo install -d -o "$PRINTER_USER" "$PRINTER_WORK" \
            || die "${PRINTER_USER} has no root access on the printer; nothing was changed (see docs/recovery.md)"
    fi
    pssh "mkdir -p ${PRINTER_WORK}/firmware ${PRINTER_WORK}/deployer"
    tmp="$(mktemp -d)"
    curl -fsSL "https://raw.githubusercontent.com/Arksine/katapult/${KATAPULT_REF}/scripts/flashtool.py" -o "${tmp}/flashtool.py"
    scp -q "${SSH_OPTS[@]}" "${Q2_ROOT}/printer/q2-printer.sh" "${Q2_ROOT}/printer/q2_stock_reset.py" "${Q2_ROOT}/printer/q2-serial-proxy@.service" \
        "${tmp}/flashtool.py" "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/"
    rm -rf "$tmp"
    if [ -n "${FIRMWARE_DIR:-}" ]; then
        # One directory per MCU with klipper.bin + klipper.dict: flashtool then also checks
        # that the image was built for the MCU it is writing to
        local m stage
        stage="$(mktemp -d)"
        for m in main thr box; do
            mkdir -p "${stage}/${m}"
            cp "${FIRMWARE_DIR}/q2-${m}.bin" "${stage}/${m}/klipper.bin"
            cp "${FIRMWARE_DIR}/q2-${m}.dict" "${stage}/${m}/klipper.dict"
        done
        (cd "$stage" && sha256sum ./*/klipper.bin ./*/klipper.dict > SHA256SUMS)
        pssh "rm -rf ${PRINTER_WORK}/firmware && mkdir -p ${PRINTER_WORK}/firmware"
        scp -q -r "${SSH_OPTS[@]}" "$stage"/* "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/firmware/"
        rm -rf "$stage"
        pssh "cd ${PRINTER_WORK}/firmware && sha256sum -c --quiet SHA256SUMS" \
            || die "firmware copy on the printer is corrupted"
    fi
}

# SSH key, current scripts on the printer, then the sudo rule for q2-printer.sh: the
# printer's sudo password is asked once here, every later step runs without it.
printer_prepare() {
    printer_ssh_key
    printer_push
    # q2-printer.sh flashes and proxies the Box only without this marker (--no-box)
    if has_box; then pssh "rm -f ${PRINTER_WORK}/no-box"; else pssh "touch ${PRINTER_WORK}/no-box"; fi
    if ! pssh "sudo -n /bin/bash ${PRINTER_WORK}/q2-printer.sh status" >/dev/null 2>&1; then
        info "Allowing ${PRINTER_USER} to run q2-printer.sh as root (printer sudo password, asked once)"
        proot sudoers
    fi
}

# The Qidi Box on the printer's USB, in any of its states: stock firmware, our Klipper, or
# Katapult (same names as q2-printer.sh). Prints the device name, nothing if there is none.
printer_box_device() {
    pssh "ls /dev/serial/by-id/ 2>/dev/null" 2>/dev/null \
        | grep -E '^usb-(Klipper_QIDI_BOX_V2|Klipper_stm32f401xc_|katapult_stm32f401xc_)' | head -1 || true
}

# Check the Box setting (--box / --no-box) against what is plugged into the printer, before
# anything is flashed. "switch": a fresh install may still change to --no-box (the host is
# not configured yet). "strict": the host is configured, so only stop with instructions.
printer_check_box() {
    local mode="${1:-strict}" found
    in_ci && return 0
    found="$(printer_box_device)"
    if has_box; then
        if [ -n "$found" ]; then ok "Qidi Box found (${found})"; return 0; fi
        warn "no Qidi Box found on the printer's USB (looked for usb-Klipper_QIDI_BOX_V2*, usb-Klipper_stm32f401xc*, usb-katapult_stm32f401xc*)"
        echo "If you have one, check its USB cable to the printer and that it is switched on, then run this again."
        if [ "$mode" != switch ]; then
            die "no Qidi Box: connect it, or reinstall without it: ./install.sh --no-box"
        fi
        # Never switched silently: --yes or no terminal stops here
        if [ "${ASSUME_YES:-0}" = 1 ] || [ ! -t 0 ]; then
            die "no Qidi Box: connect it, or run with --no-box"
        fi
        confirm "Install without a Qidi Box (same as --no-box: mainboard and toolhead only, no Happy Hare)?" n \
            || die "stopped before any change: connect the Box, or run with --no-box"
        # shellcheck disable=SC2034  # read by has_box in host.sh
        BOX=0
        save_settings
        info "Continuing without a Qidi Box (saved; ./install.sh --box to change it later)"
    else
        [ -z "$found" ] && return 0
        warn "a Qidi Box is connected (${found}), but this install is set to --no-box: it will not be flashed or used"
        echo "To use it, run the installer with --box instead."
        confirm "Continue without the Box?" y || die "stopped: run again with --box"
    fi
}

# First conversion only: fetch and verify the pinned Katapult deployers, copy them over.
printer_fetch_deployers() {
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL "$DEPLOYER_URL" -o "${tmp}/deployer.tgz"
    echo "${DEPLOYER_SHA256}  ${tmp}/deployer.tgz" | sha256sum -c --quiet || die "deployer archive checksum mismatch"
    tar xzf "${tmp}/deployer.tgz" -C "$tmp"
    # The archive is read-only, its top directory too: without this the copies on the
    # printer cannot be replaced on a second run and the temporary directory cannot be removed
    chmod -R u+w "$tmp"
    echo "${DEPLOYER_MCU_SHA256}  ${tmp}/mcu-deployer.bin" | sha256sum -c --quiet || die "mcu-deployer checksum mismatch"
    echo "${DEPLOYER_THR_SHA256}  ${tmp}/thr-deployer.bin" | sha256sum -c --quiet || die "thr-deployer checksum mismatch"
    echo "${DEPLOYER_MMU_SHA256}  ${tmp}/mmu-deployer.bin" | sha256sum -c --quiet || die "mmu-deployer checksum mismatch"
    pssh "rm -f ${PRINTER_WORK}/deployer/*-deployer.bin"
    scp -q "${SSH_OPTS[@]}" "$tmp"/*-deployer.bin "${PRINTER_USER}@${PRINTER_IP}:${PRINTER_WORK}/deployer/"
    rm -rf "$tmp"
}

# Firmware phase: optional Katapult deploy (first conversion), then Klipper on all three
# MCUs, in a single root session on the printer (one sudo password prompt).
printer_convert() {
    local deploy="${1:-}"
    printer_check_box strict
    if [ "$deploy" = deploy ]; then
        cat <<EOF

${C_WARN}First conversion: Katapult bootloader on the $(has_box && echo three MCUs || echo mainboard and toolhead)${C_OFF}
Qidi's own update scripts flash a Katapult "deployer" (n3oney/qidi-q2-klipper) while the
stock firmware still runs. Afterwards Katapult replaces Qidi's bootloader: Qidi's firmware
can still be flashed back through Katapult (docs/recovery.md), but recovering from a power
cut during THIS step needs an ST-Link.
  - keep the printer powered and connected the whole time
  - one MCU at a time; each one is checked before the next
EOF
        confirm_phrase "INSTALL KATAPULT"
    fi
    cat <<EOF

${C_WARN}Flashing Klipper ($(firmware_id)) on mainboard, toolhead$(has_box && echo ' and Qidi Box')${C_OFF}
Each MCU is put into Katapult and its application offset is checked before writing.
EOF
    # Never skipped, not even with --yes
    confirm_phrase "FLASH"
    if [ -n "$(systemctl list-unit-files klipper.service --no-legend 2>/dev/null)" ]; then
        sudo systemctl stop q2-link-watch 2>/dev/null || true  # it must not restart the link during a flash; host_start starts it again
        sudo systemctl stop klipper q2-serial-bridge@main:7001 q2-serial-bridge@thr:7002 q2-serial-bridge@mmu:7003 2>/dev/null || true  # all three: a Box bridge may be left over
    fi
    # shellcheck disable=SC2086  # $deploy is empty or one word
    proot convert "$(firmware_id)" $deploy || die "firmware phase failed; see docs/recovery.md"
    ok "all MCUs on firmware $(firmware_id)"
}

printer_firmware_id() { pssh "cat ${PRINTER_WORK}/firmware-id 2>/dev/null" || true; }

printer_proxies() {
    proot setup "$HOST_IP"
}

# Point HelixScreen (the touchscreen UI) at the host's Moonraker, installing it if needed.
printer_helixscreen() {
    local settings="/home/${PRINTER_USER}/helixscreen/config/settings.json"
    if ! pssh "test -f ${settings}"; then
        confirm "Install HelixScreen on the printer touchscreen (stock Qidi UI needs a local Klipper)?" y || return 0
        info "Installing HelixScreen on the printer: download and setup take a few minutes; its installer may ask for the printer sudo password"
        pssh -t "curl -sSL https://releases.helixscreen.org/install.sh | sh" \
            || { warn "HelixScreen install failed; run it later on the printer"; return 0; }
        pssh "test -f ${settings}" || {
            warn "HelixScreen: in its first-run wizard, set Moonraker to ${HOST_IP}:7125"; return 0; }
    fi
    pssh "python3 - ${settings} ${HOST_IP}" <<'EOF' || { warn "could not update ${settings}: set Moonraker to ${HOST_IP}:7125 in HelixScreen"; return 0; }
import json, sys
path, host = sys.argv[1], sys.argv[2]
data = json.load(open(path))
printers = data.get('printers') or {}
for p in (printers.values() if printers else [data]):
    p['moonraker_host'] = host
    p['moonraker_port'] = 7125
json.dump(data, open(path, 'w'), indent=2)
EOF
    proot helixscreen-restart || true
    ok "HelixScreen -> Moonraker ${HOST_IP}:7125"
}

