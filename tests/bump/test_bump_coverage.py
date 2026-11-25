"""Every version pinned in VERSIONS is moved by scripts/bump.sh, the daily upstream update,
unless it is listed here as pinned by hand on purpose. A new pin that bump.sh does not know
fails here instead of silently staying at its first version.
Usage: python3 tests/bump/test_bump_coverage.py"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSIONS = (ROOT / "VERSIONS").read_text()
BUMP = (ROOT / "scripts/bump.sh").read_text()

# Where to fetch from, not which version: never bumped
LOCATION = re.compile(r"_(REPO|BRANCH)$|^OBICO_ML_API(_INTEL)?_IMAGE$")
# Flashed over the stock bootloader: a bad one bricks an MCU, so only changed by hand
BY_HAND = re.compile(r"^(DEPLOYER|HID_FLASH)_")


def pins():
    keys = re.findall(r"^([A-Z0-9_]+)=", VERSIONS, re.M)
    return [k for k in keys if not LOCATION.search(k) and not BY_HAND.match(k)]


def bumped():
    keys = set(re.findall(r"\bset_var\s+([A-Z0-9_]+)\b", BUMP))
    for loop in re.findall(r"^for name in ([A-Z0-9_ ]+); do$", BUMP, re.M):
        keys.update(name + "_REF" for name in loop.split())
    return keys


def test_every_pin_is_bumped():
    missing = [k for k in pins() if k not in bumped()]
    assert not missing, "pinned in VERSIONS but never moved by scripts/bump.sh: %s" % ", ".join(missing)


def test_helixscreen_and_orca_profiles_are_bumped():
    assert {"HELIXSCREEN_VERSION", "ORCA_PROFILES_REF"} <= bumped()


def test_hand_pinned_firmware_tools_are_never_bumped():
    assert not [k for k in bumped() if BY_HAND.match(k)]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
