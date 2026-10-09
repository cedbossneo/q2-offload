# shellcheck shell=bash
# Klipper host side of install.sh. Source after lib.sh; expects the settings variables
# (PRINTER_IP, HOST_IP, COMPONENTS...) to be set.

DATA="${HOME}/printer_data"
CFG="${DATA}/config"
STATE_DIR="${HOME}/.config/q2-offload"
MANIFEST="${STATE_DIR}/installed-files.sha256"
KLIPPY_ENV="${HOME}/klippy-env"

has() { [[ ",${COMPONENTS}," == *",$1,"* ]]; }

# The unattended update runs its root phase as root: sudo is then a no-op
# (env keeps "sudo VAR=value cmd" working).
if [ "$(id -u)" = 0 ]; then sudo() { env "$@"; }; fi

# Tell the user in the Mainsail/Fluidd console and in logs/q2-offload-update.log
notify() {
    echo "q2-offload: $*"
    curl -s -o /dev/null -X POST -G --data-urlencode "script=RESPOND TYPE=command MSG=\"q2-offload: $*\"" \
        localhost:7125/printer/gcode/script 2>/dev/null || true
}

# Systemd/nginx/docker are skipped in CI containers
in_ci() { [ "${Q2_CI:-0}" = 1 ]; }

svc() { in_ci || sudo systemctl "$@"; }

render() {
    sed -e "s#@HOME@#${HOME}#g" \
        -e "s#@USER@#${USER}#g" \
        -e "s#@PRINTER_IP@#${PRINTER_IP}#g" \
        -e "s#@HOST_IP@#${HOST_IP}#g" \
        -e "s#@Q2_ROOT@#${Q2_ROOT}#g" \
        -e "s#@Q2_ORIGIN@#${Q2_ORIGIN}#g" \
        -e "s#@FLUIDD_PORT@#${FLUIDD_PORT}#g" \
        -e "s#@MAINSAIL_PORT@#${MAINSAIL_PORT}#g" \
        "$1"
}

# Uncomment "#@NAME@" lines when component NAME is selected, drop them otherwise.
toggle() {
    local name
    local args=()
    for name in MAINSAIL FLUIDD SPOOLMAN AUTOPA PRINTGUARD; do
        if has "${name,,}"; then args+=(-e "s/^#@${name}@//"); else args+=(-e "/^#@${name}@/d"); fi
    done
    sed "${args[@]}"
}

manifest_set() {
    grep -v "  $2\$" "$MANIFEST" > "${MANIFEST}.tmp" || true
    echo "$1  $2" >> "${MANIFEST}.tmp"
    mv "${MANIFEST}.tmp" "$MANIFEST"
}

# install_config <rendered-content-file> <dest>: write a file we own, without clobbering
# local edits. A file changed since we installed it gets the new version as <dest>.new.
install_config() {
    local src="$1" dest="$2" old_sum cur_sum new_sum
    mkdir -p "$(dirname "$dest")" "$STATE_DIR"
    touch "$MANIFEST"
    new_sum="$(sha256sum < "$src" | cut -d' ' -f1)"
    if [ -e "$dest" ]; then
        cur_sum="$(sha256sum < "$dest" | cut -d' ' -f1)"
        old_sum="$(awk -v f="$dest" '$2 == f {print $1}' "$MANIFEST")"
        if [ "$cur_sum" = "$new_sum" ]; then
            manifest_set "$new_sum" "$dest"
            return 0
        fi
        if [ -n "$old_sum" ] && [ "$cur_sum" != "$old_sum" ]; then
            cp "$src" "${dest}.new"
            warn "kept your edited ${dest#"${HOME}"/}; new version saved as ${dest#"${HOME}"/}.new"
            return 0
        fi
        if [ -z "$old_sum" ]; then
            cp "$dest" "${dest}.pre-q2-offload"
            warn "existing ${dest#"${HOME}"/} saved as .pre-q2-offload"
        fi
    fi
    cp "$src" "$dest"
    manifest_set "$new_sum" "$dest"
}

host_packages() {
    local pkgs=(git curl unzip socat python3 python3-venv python3-dev build-essential libffi-dev
                libncurses-dev zlib1g-dev)
    { has mainsail || has fluidd || has autopa; } && pkgs+=(nginx)
    info "Installing system packages"
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${pkgs[@]}" >/dev/null
    if { has spoolman || has printguard; } && ! command -v docker >/dev/null; then
        info "Installing Docker (Spoolman / PrintGuard)"
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io >/dev/null
        svc enable --now docker
    fi
}

host_dirs() {
    mkdir -p "${DATA}"/{config,logs,gcodes,systemd,comms,scripts/plr,autopa/captures}
}

host_klipper() {
    "${Q2_ROOT}/scripts/prepare-klipper.sh" "${HOME}/klipper"
    if [ ! -x "${KLIPPY_ENV}/bin/python" ]; then
        info "Creating the Klipper Python environment"
        python3 -m venv "$KLIPPY_ENV"
    fi
    "${KLIPPY_ENV}/bin/pip" install -q --upgrade pip
    # numpy: input shaper + autopa; scipy: load cell continuous tare filter
    "${KLIPPY_ENV}/bin/pip" install -q -r "${HOME}/klipper/scripts/klippy-requirements.txt" numpy scipy
    # The C helper is normally built on first start; build it now so errors show up here
    "${KLIPPY_ENV}/bin/python" -c "import sys; sys.path.insert(0, '${HOME}/klipper/klippy'); import chelper; chelper.get_ffi()"
    ok "Klipper $(git -C "${HOME}/klipper" describe --tags --always)"
}

host_extensions() {
    local tmp
    checkout_ref "$TIMELAPSE_REPO" "$TIMELAPSE_REF" "${HOME}/moonraker-timelapse"
    checkout_ref "$MAINSAIL_CONFIG_REPO" "$MAINSAIL_CONFIG_REF" "${HOME}/mainsail-config"
    ln -sfn "${HOME}/moonraker-timelapse/component/timelapse.py" "${HOME}/moonraker/moonraker/components/timelapse.py"
    ln -sfn "${HOME}/moonraker-timelapse/klipper_macro/timelapse.cfg" "${CFG}/timelapse.cfg"
    ln -sfn "${HOME}/mainsail-config/mainsail.cfg" "${CFG}/mainsail.cfg"
    tmp="$(mktemp)"
    curl -fsSL "https://raw.githubusercontent.com/dw-0/kiauh/${KIAUH_REF}/kiauh/extensions/gcode_shell_cmd/assets/gcode_shell_command.py" -o "$tmp"
    install -m 644 "$tmp" "${HOME}/klipper/klippy/extras/gcode_shell_command.py"
    rm -f "$tmp"
    ok "timelapse, mainsail-config, gcode_shell_command"
}

host_moonraker() {
    local tmp
    checkout_ref "$MOONRAKER_REPO" "$MOONRAKER_REF" "${HOME}/moonraker"
    tmp="$(mktemp)"
    render "${Q2_ROOT}/host/moonraker.conf" | toggle > "$tmp"
    # moonraker.conf is the user's after the first install: never overwritten
    [ -e "${CFG}/moonraker.conf" ] || cp "$tmp" "${CFG}/moonraker.conf"
    rm -f "$tmp"
    # A component selected after the first install still needs its Moonraker section
    if has spoolman && ! grep -q '^\[spoolman\]' "${CFG}/moonraker.conf"; then
        printf '\n[spoolman]\nserver: http://localhost:7912\nsync_rate: 5\n' >> "${CFG}/moonraker.conf"
    fi
    moonraker_conf_migrate
    info "Installing Moonraker"
    local args=(-f -s)
    in_ci && args+=(-z -x)
    "${HOME}/moonraker/scripts/install-moonraker.sh" "${args[@]}" >/dev/null
    moonraker_asvc
    ok "Moonraker $(git -C "${HOME}/moonraker" describe --tags --always)"
}

# Unattended update, user phase: no sudo available, so only the checkout and Python deps
# (system packages are handled by moonraker_sysdeps in the root phase)
host_moonraker_update() {
    local before after
    before="$(git -C "${HOME}/moonraker" rev-parse HEAD 2>/dev/null || true)"
    checkout_ref "$MOONRAKER_REPO" "$MOONRAKER_REF" "${HOME}/moonraker"
    after="$(git -C "${HOME}/moonraker" rev-parse HEAD)"
    if [ "$before" != "$after" ]; then
        "${HOME}/moonraker-env/bin/pip" install -q -r "${HOME}/moonraker/scripts/moonraker-requirements.txt" \
            -r "${HOME}/moonraker/scripts/moonraker-speedups.txt"
        touch "${STATE_DIR}/moonraker-changed"
    fi
    moonraker_conf_migrate
    moonraker_asvc
    ok "Moonraker $(git -C "${HOME}/moonraker" describe --tags --always)"
}

moonraker_sysdeps() {
    local pkgs
    pkgs="$(python3 -c 'import json,sys; print(" ".join(p for p in json.load(open(sys.argv[1]))["debian"] if ";" not in p))' \
        "${HOME}/moonraker/scripts/system-dependencies.json")"
    # shellcheck disable=SC2086
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $pkgs >/dev/null
}

# Moonraker restarts the services listed in managed_services after updating a repo: the
# q2-offload entry triggers q2-offload.service, which runs "install.sh update".
moonraker_conf_migrate() {
    python3 - "${CFG}/moonraker.conf" <<'EOF'
import re, sys
path = sys.argv[1]
s = open(path).read()
m = re.search(r'^\[update_manager q2-offload\]\n((?:[^\[\n].*\n|\n)*)', s, re.M)
if m and 'managed_services' not in m.group(1):
    body = re.sub(r'^is_system_service:.*\n', '', m.group(1), flags=re.M)
    body = body.rstrip('\n') + '\nmanaged_services: q2-offload\n\n'
    s = s[:m.start(1)] + body + s[m.end(1):]
    open(path, 'w').write(s)
EOF
}

moonraker_asvc() {
    local asvc="${DATA}/moonraker.asvc"
    # Moonraker creates it from this default list on first start; do the same, then add ours
    [ -f "$asvc" ] || cp "${HOME}/moonraker/moonraker/assets/default_allowed_services" "$asvc"
    grep -qx q2-offload "$asvc" || echo q2-offload >> "$asvc"
}

# Drop a whole [section] from an ini-style file (Happy Hare re-adds its update_manager entry)
drop_section() {
    python3 - "$1" "$2" <<'EOF'
import re, sys
path, section = sys.argv[1], sys.argv[2]
out, skip = [], False
for line in open(path).read().split('\n'):
    m = re.match(r'^\[([^\]]+)\]', line)
    if m:
        skip = m.group(1).strip() == section
    if not skip:
        out.append(line)
open(path, 'w').write('\n'.join(out))
EOF
}

host_happy_hare() {
    local hh="${HOME}/Happy-Hare"
    checkout_ref "$HAPPY_HARE_REPO" "$HAPPY_HARE_REF" "$hh"
    apply_patches "$hh" "${Q2_ROOT}/patches/happy-hare" q2-offload
    render "${Q2_ROOT}/config/happy-hare/mmu_config" > "${hh}/.mmu_config"
    info "Installing Happy Hare (Qidi Box profile)"
    (cd "$hh" && ./install.sh -z -s -y) > "${STATE_DIR}/happy-hare-install.log" 2>&1 \
        || { tail -20 "${STATE_DIR}/happy-hare-install.log"; die "Happy Hare install failed (log: ${STATE_DIR}/happy-hare-install.log)"; }
    python3 "${Q2_ROOT}/scripts/apply-overrides.py" "${Q2_ROOT}/config/happy-hare/overrides.cfg" \
        "${CFG}/mmu/base" --home "$HOME"
    drop_section "${CFG}/moonraker.conf" "update_manager happy-hare"
    ok "Happy Hare $(git -C "$hh" describe --tags --always 2>/dev/null || git -C "$hh" rev-parse --short HEAD)"
}

host_config() {
    local f tmp
    tmp="$(mktemp)"
    for f in "${Q2_ROOT}"/config/klipper/*.cfg; do
        render "$f" | toggle > "$tmp"
        if [ "$(basename "$f")" = printer.cfg ]; then
            # printer.cfg carries the SAVE_CONFIG calibrations: only written on first install
            [ -e "${CFG}/printer.cfg" ] && [ -z "$(awk -v f="${CFG}/printer.cfg" '$2 == f' "$MANIFEST" 2>/dev/null)" ] \
                && { warn "keeping your existing printer.cfg"; continue; }
        fi
        install_config "$tmp" "${CFG}/$(basename "$f")"
    done
    for f in "${Q2_ROOT}"/config/plr/*.sh; do
        render "$f" > "$tmp"
        install_config "$tmp" "${DATA}/scripts/plr/$(basename "$f")"
        chmod +x "${DATA}/scripts/plr/$(basename "$f")"
    done
    # Single variables file shared by the Qidi macros and Happy Hare (which checks mmu__revision)
    [ -e "${CFG}/saved_variables.cfg" ] || printf '[Variables]\nmmu__revision = 0\n' > "${CFG}/saved_variables.cfg"
    if has mainsail; then
        mkdir -p "${CFG}/.theme"
        python3 "${Q2_ROOT}/scripts/navi.py" "$COMPONENTS" "$HOST_IP" "$FLUIDD_PORT" > "$tmp"
        install_config "$tmp" "${CFG}/.theme/navi.json"
    fi
    rm -f "$tmp"
    ok "Klipper configuration in ${CFG}"
}

host_autopa() {
    has autopa || return 0
    checkout_ref "$AUTOPA_REPO" "$AUTOPA_REF" "${HOME}/autopa"
    KLIPPER="${HOME}/klipper" KLIPPER_ENV="$KLIPPY_ENV" CONFIG_DIR="$CFG" \
        "${HOME}/autopa/install.sh" --no-nginx --no-moonraker < /dev/null > /dev/null
    ok "autopa"
}

web_client() {
    local name="$1" repo="$2" version="$3" tmp
    tmp="$(mktemp -d)"
    curl -fsSL "https://github.com/${repo}/releases/download/${version}/${name}.zip" -o "${tmp}/${name}.zip"
    rm -rf "${HOME:?}/${name}.new" && mkdir -p "${HOME}/${name}.new"
    unzip -q "${tmp}/${name}.zip" -d "${HOME}/${name}.new"
    # Keep Mainsail's config.json across updates
    [ -f "${HOME}/${name}/config.json" ] && cp "${HOME}/${name}/config.json" "${HOME}/${name}.new/"
    rm -rf "${HOME:?}/${name}" && mv "${HOME}/${name}.new" "${HOME}/${name}"
    rm -rf "$tmp"
    ok "${name} ${version}"
}

host_web_clients() {
    if has mainsail; then web_client mainsail mainsail-crew/mainsail "$MAINSAIL_VERSION"; fi
    if has fluidd; then web_client fluidd fluidd-core/fluidd "$FLUIDD_VERSION"; fi
}

host_web() {
    host_web_clients
    host_nginx
}

host_nginx() {
    { has mainsail || has fluidd || has autopa; } || return 0
    in_ci && return 0
    local tmp
    tmp="$(mktemp)"
    render "${Q2_ROOT}/host/nginx/q2-offload.conf" > "$tmp"
    # Without Fluidd the Mainsail server becomes the default one; with neither client the
    # Fluidd server block stays so autopa is still served
    has fluidd || ! has mainsail || python3 - "$tmp" <<'EOF'
import sys,re
p=sys.argv[1]; s=open(p).read()
# No Fluidd: drop its server block, Mainsail becomes the default server
blocks=s.split('\nserver {')
s=blocks[0]+''.join('\nserver {'+b for b in blocks[1:] if 'fluidd' not in b)
open(p,'w').write(s.replace('listen 81;','listen 81 default_server;'))
EOF
    has mainsail || python3 - "$tmp" <<'EOF'
import sys
p=sys.argv[1]; s=open(p).read()
blocks=s.split('\nserver {')
open(p,'w').write(blocks[0]+''.join('\nserver {'+b for b in blocks[1:] if 'mainsail' not in b))
EOF
    sudo install -m 644 "$tmp" /etc/nginx/sites-available/q2-offload
    render "${Q2_ROOT}/host/nginx/q2-offload-common.conf" > "$tmp"
    sudo install -m 644 "$tmp" /etc/nginx/q2-offload-common.conf
    rm -f "$tmp"
    sudo ln -sfn /etc/nginx/sites-available/q2-offload /etc/nginx/sites-enabled/q2-offload
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t -q || die "nginx configuration test failed"
    svc enable nginx
    svc reload nginx || svc restart nginx
    # nginx (www-data) must be able to read the web clients and autopa in $HOME
    chmod o+x "$HOME"
    ok "nginx: Fluidd :${FLUIDD_PORT}, Mainsail :${MAINSAIL_PORT}"
}

host_spoolman() {
    has spoolman || return 0
    in_ci && return 0
    mkdir -p "${HOME}/spoolman-data"
    if sudo docker inspect spoolman >/dev/null 2>&1; then
        [ "$(sudo docker inspect -f '{{.Config.Image}}' spoolman)" = "ghcr.io/donkie/spoolman:${SPOOLMAN_VERSION#v}" ] \
            && { ok "Spoolman ${SPOOLMAN_VERSION}"; return 0; }
        sudo docker rm -f spoolman >/dev/null
    fi
    sudo docker run -d --name spoolman --restart unless-stopped -p 7912:8000 \
        -e TZ="$(cat /etc/timezone 2>/dev/null || echo UTC)" \
        -v "${HOME}/spoolman-data:/home/app/.local/share/spoolman" \
        "ghcr.io/donkie/spoolman:${SPOOLMAN_VERSION#v}" >/dev/null
    ok "Spoolman ${SPOOLMAN_VERSION} on :7912"
}

host_printguard() {
    has printguard || return 0
    in_ci && return 0
    sudo mkdir -p /srv/printguard
    if sudo docker inspect printguard >/dev/null 2>&1; then
        [ "$(sudo docker inspect -f '{{.Config.Image}}' printguard)" = "ghcr.io/oliverbravery/printguard:${PRINTGUARD_VERSION#v}" ] \
            && { ok "PrintGuard"; return 0; }
        sudo docker rm -f printguard >/dev/null
    fi
    # One CPU at the lowest weight: inference + video remux must never starve Klipper
    sudo docker run -d --name printguard --restart unless-stopped -p 8000:8000 \
        -e TZ="$(cat /etc/timezone 2>/dev/null || echo UTC)" -v /srv/printguard:/data \
        --cpus 1 --cpu-shares 256 --memory 1g "ghcr.io/oliverbravery/printguard:${PRINTGUARD_VERSION#v}" >/dev/null
    ok "PrintGuard on :8000 (camera: http://${PRINTER_IP}/webcam/?action=stream)"
}

host_services() {
    in_ci && return 0
    local tmp
    tmp="$(mktemp)"
    render "${Q2_ROOT}/host/systemd/klipper.env" > "${DATA}/systemd/klipper.env"
    [ "$(id -u)" = 0 ] && chown "${USER}:" "${DATA}/systemd/klipper.env"
    render "${Q2_ROOT}/host/systemd/klipper.service" > "$tmp"
    sudo install -m 644 "$tmp" /etc/systemd/system/klipper.service
    render "${Q2_ROOT}/host/systemd/q2-serial-bridge@.service" > "$tmp"
    sudo install -m 644 "$tmp" /etc/systemd/system/q2-serial-bridge@.service
    render "${Q2_ROOT}/host/systemd/q2-offload.service" > "$tmp"
    sudo install -m 644 "$tmp" /etc/systemd/system/q2-offload.service
    rm -f "$tmp"
    sudo systemctl daemon-reload
    sudo systemctl enable -q klipper q2-serial-bridge@main:7001 q2-serial-bridge@thr:7002 q2-serial-bridge@mmu:7003
    ok "systemd units (klipper, q2-serial-bridge@main/thr/mmu)"
}

host_start() {
    sudo systemctl restart q2-serial-bridge@main:7001 q2-serial-bridge@thr:7002 q2-serial-bridge@mmu:7003
    sleep 2
    sudo systemctl restart klipper moonraker
}

# Fetch the firmware matching this Klipper + patch series from the q2-offload releases,
# or build it locally with --build-firmware.
host_firmware() {
    local id dir
    id="$(firmware_id)"
    dir="${STATE_DIR}/firmware/${id}"
    if [ -s "${dir}/q2-main.bin" ] && (cd "$dir" && sha256sum -c --quiet SHA256SUMS); then
        export FIRMWARE_DIR="$dir"; return 0
    fi
    mkdir -p "$dir"
    if [ "${BUILD_FIRMWARE:-0}" = 1 ]; then
        info "Building firmware ${id} locally"
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gcc-arm-none-eabi libnewlib-arm-none-eabi >/dev/null
        "${Q2_ROOT}/scripts/prepare-klipper.sh" "${STATE_DIR}/klipper-build"
        "${Q2_ROOT}/scripts/build-firmware.sh" "${STATE_DIR}/klipper-build" "$dir"
    else
        info "Downloading firmware ${id}"
        local base="https://github.com/${Q2_GITHUB_REPO}/releases/download/fw-${id}"
        for f in SHA256SUMS BUILD_INFO q2-main.bin q2-thr.bin q2-box.bin q2-main.dict q2-thr.dict q2-box.dict; do
            curl -fsSL "${base}/${f}" -o "${dir}/${f}" \
                || die "firmware fw-${id} is not published (yet). Re-run with --build-firmware to build it here."
        done
    fi
    (cd "$dir" && sha256sum -c --quiet SHA256SUMS) || die "firmware checksum mismatch in ${dir}"
    local m mcu
    for m in main:stm32f407xx thr:stm32f103xe box:stm32f401xc; do
        mcu="${m#*:}"; m="${m%%:*}"
        grep -Eq "\"MCU\": *\"${mcu}\"" "${dir}/q2-${m}.dict" || die "q2-${m} is not built for ${mcu}"
    done
    export FIRMWARE_DIR="$dir"
    ok "firmware ${id}"
}

host_install_all() {
    host_packages
    host_dirs
    host_klipper
    host_moonraker
    host_extensions
    host_config
    host_happy_hare
    host_autopa
    host_web
    host_spoolman
    host_printguard
    host_services
}
