"""Run q2_stock_reset.py against a fake MCU on a pty, speaking the Klipper protocol.
Usage: python3 tests/macros/test_stock_reset.py"""
import importlib.util
import json
import os
import pathlib
import pty
import select
import subprocess
import sys
import threading
import tty
import zlib

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "printer/q2_stock_reset.py"
spec = importlib.util.spec_from_file_location("reset", SCRIPT)
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


class FakeMcu(threading.Thread):
    def __init__(self, dictionary, reset_id):
        super().__init__(daemon=True)
        self.data = zlib.compress(json.dumps(dictionary).encode())
        self.reset_id = reset_id
        self.master, slave = pty.openpty()
        tty.setraw(slave)
        self.device = os.ttyname(slave)
        self.slave = slave
        self.got_reset = threading.Event()

    def run(self):
        buffer = b""
        while not self.got_reset.is_set():
            if not select.select([self.master], [], [], 5)[0]:
                return
            buffer += os.read(self.master, 4096)
            payloads, buffer = reset.split_frames(buffer.lstrip(b"\x7e"))
            for payload in payloads:
                self.handle(payload)

    def handle(self, payload):
        msgid, pos = reset.decode_vlq(payload, 0)
        if msgid == self.reset_id:
            self.got_reset.set()
        elif msgid == reset.MSG_IDENTIFY:
            offset, pos = reset.decode_vlq(payload, pos)
            count, pos = reset.decode_vlq(payload, pos)
            chunk = self.data[offset:offset + count]
            answer = reset.encode_vlq(reset.MSG_IDENTIFY_RESPONSE) + reset.encode_vlq(offset) + reset.encode_vlq(len(chunk)) + chunk
            os.write(self.master, reset.frame(answer, 0))


def run(dictionary, reset_id):
    mcu = FakeMcu(dictionary, reset_id)
    mcu.start()
    result = subprocess.run([sys.executable, str(SCRIPT), mcu.device], capture_output=True, text=True, timeout=30)
    mcu.got_reset.wait(2)
    return result, mcu


def test_large_dictionary_is_read_and_reset_sent():
    commands = {"reset": 115, **{"cmd_%d a=%%u" % i: i + 2 for i in range(300)}}
    result, mcu = run({"commands": commands, "responses": {}, "version": "x" * 2000}, 115)
    assert result.returncode == 0, result.stderr
    assert mcu.got_reset.is_set() and "115" in result.stdout


def test_negative_command_id_is_encoded_like_klipper():
    assert reset.encode_vlq(-5) == bytes([123])
    assert reset.decode_vlq(reset.encode_vlq(-5), 0)[0] == -5
    assert reset.decode_vlq(reset.encode_vlq(115), 0)[0] == 115
    result, mcu = run({"commands": {"reset": -5}}, -5)
    assert result.returncode == 0 and mcu.got_reset.is_set(), result.stderr


def test_firmware_without_reset_fails_cleanly():
    result, mcu = run({"commands": {"other": 3}}, 99)
    assert result.returncode != 0 and "no reset command" in result.stderr and not mcu.got_reset.is_set()


def test_crc_matches_klipper():
    # Same values as klippy/msgproto.py crc16_ccitt
    assert reset.crc16(b"123456789") == 0x6F91


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d stock reset tests passed" % len(tests))
