#!/usr/bin/env python3
"""Ask a stock Qidi MCU to reboot into its bootloader, as Qidi's own update scripts do.

Reads the firmware dictionary over the Klipper protocol to find the "reset" command id, then
sends it. Standard library only: nothing to install on the printer. It only reboots the MCU;
hid-flash does the writing afterwards.

Usage: q2_stock_reset.py <device> [--baud N]
"""
import argparse
import json
import os
import select
import sys
import termios
import time
import zlib

SYNC = 0x7E
HEADER = 2
TRAILER = 3
DEST = 0x10
SEQ_MASK = 0x0F
MSG_IDENTIFY_RESPONSE = 0
MSG_IDENTIFY = 1
CHUNK = 40
TIMEOUT_SECONDS = 2.0
RETRIES = 5


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        byte ^= crc & 0xFF
        byte = (byte ^ (byte << 4)) & 0xFF
        crc = ((byte << 8) | (crc >> 8)) ^ (byte >> 4) ^ (byte << 3)
        crc &= 0xFFFF
    return crc


def encode_vlq(value):
    """Klipper's variable length integer, negative values included."""
    out = []
    if value >= 0xC000000 or value < -0x4000000:
        out.append((value >> 28) & 0x7F | 0x80)
    if value >= 0x180000 or value < -0x80000:
        out.append((value >> 21) & 0x7F | 0x80)
    if value >= 0x3000 or value < -0x1000:
        out.append((value >> 14) & 0x7F | 0x80)
    if value >= 0x60 or value < -0x20:
        out.append((value >> 7) & 0x7F | 0x80)
    out.append(value & 0x7F)
    return bytes(out)


def decode_vlq(data, pos):
    byte = data[pos]
    pos += 1
    value = byte & 0x7F
    if byte & 0x60 == 0x60:
        value |= -0x20
    while byte & 0x80:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
    return value, pos


def frame(payload, seq):
    head = bytes([len(payload) + HEADER + TRAILER, DEST | (seq & SEQ_MASK)]) + payload
    crc = crc16(head)
    return head + bytes([crc >> 8, crc & 0xFF, SYNC])


def split_frames(buffer):
    """Valid frame payloads in the buffer, and what is left to read."""
    payloads = []
    while buffer:
        length = buffer[0]
        if length < HEADER + TRAILER or length > 64:
            buffer = buffer[1:]
            continue
        if len(buffer) < length:
            break
        block = buffer[:length]
        crc = crc16(block[:-TRAILER])
        if block[-1] == SYNC and block[-3] == crc >> 8 and block[-2] == crc & 0xFF:
            payloads.append(block[HEADER:-TRAILER])
            buffer = buffer[length:]
        else:
            buffer = buffer[1:]
    return payloads, buffer


def parse_identify_response(payload):
    msgid, pos = decode_vlq(payload, 0)
    if msgid != MSG_IDENTIFY_RESPONSE:
        return None
    offset, pos = decode_vlq(payload, pos)
    size, pos = decode_vlq(payload, pos)
    return offset, payload[pos:pos + size]


class Link:
    def __init__(self, device, baud):
        self.fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        speed = getattr(termios, "B%d" % baud, None)
        if speed is None:
            raise SystemExit("unsupported baud rate %d" % baud)
        attrs[4] = attrs[5] = speed
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        self.seq = 0
        self.pending = b""

    def send(self, payload):
        os.write(self.fd, frame(payload, self.seq))
        self.seq += 1

    def identify_chunk(self, offset):
        request = encode_vlq(MSG_IDENTIFY) + encode_vlq(offset) + encode_vlq(CHUNK)
        for _ in range(RETRIES):
            # Clears anything half sent by the MCU's previous session
            os.write(self.fd, bytes([SYNC]))
            self.send(request)
            deadline = time.monotonic() + TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if select.select([self.fd], [], [], 0.1)[0]:
                    self.pending += os.read(self.fd, 4096)
                payloads, self.pending = split_frames(self.pending)
                for payload in payloads:
                    parsed = parse_identify_response(payload)
                    if parsed and parsed[0] == offset:
                        return parsed[1]
        raise SystemExit("no answer from the MCU")

    def dictionary(self):
        data = b""
        while True:
            chunk = self.identify_chunk(len(data))
            data += chunk
            if len(chunk) < CHUNK:
                return json.loads(zlib.decompress(data))


def reset_id(dictionary):
    for name, msgid in dictionary["commands"].items():
        if name.split(" ")[0] == "reset":
            return msgid
    raise SystemExit("this firmware has no reset command")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("device")
    # USB ignores it; the toolhead's UART passes its real rate
    parser.add_argument("--baud", type=int, default=230400)
    args = parser.parse_args()
    link = Link(args.device, args.baud)
    command = reset_id(link.dictionary())
    link.send(encode_vlq(command))
    print("reset sent (command id %d)" % command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
