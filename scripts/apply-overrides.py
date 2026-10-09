#!/usr/bin/env python3
"""Apply config/happy-hare/overrides.cfg to the Happy Hare config in <config-dir>/mmu/base.

Usage: apply-overrides.py <overrides.cfg> <mmu-base-dir> [--home DIR]

Idempotent: options are set in place (continuation lines included; an override value may
itself continue on indented lines), missing options are appended at the end of their section,
'!key' removes an option and '!section' removes the whole section. Fails if a targeted file
or section does not exist, so a Happy Hare change that renames something is caught (in CI)
instead of silently ignored.
"""
import argparse
import os
import re
import sys

HEADER = re.compile(r'^\[([^\]]+)\]\s*(#.*)?$')
TARGET = re.compile(r'^\[\s*(\S+)\s*::\s*(.+?)\s*\]\s*$')


def parse_overrides(path, home):
    """Return [(file, section, [(op, key, value)])] in file order."""
    blocks = []
    with open(path) as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if line[:1] in (' ', '\t') and blocks and blocks[-1][2] and blocks[-1][2][-1][0] == 'set':
                # Indented continuation of a multi-line value (e.g. drying_data)
                op, key, value = blocks[-1][2].pop()
                blocks[-1][2].append((op, key, value + '\n    ' + line.strip()))
                continue
            m = TARGET.match(line)
            if m:
                blocks.append((m.group(1), m.group(2), []))
                continue
            if not blocks:
                sys.exit("%s: option outside a [file :: section] block: %s" % (path, line))
            ops = blocks[-1][2]
            if line.startswith('!'):
                name = line[1:].strip()
                ops.append(('delsection', None, None) if name == 'section' else ('del', name, None))
                continue
            key, sep, value = line.partition(':')
            if not sep:
                sys.exit("%s: expected 'key: value': %s" % (path, line))
            ops.append(('set', key.strip(), value.strip().replace('@HOME@', home)))
    return blocks


def find_section(lines, section):
    """Return (start, end) line indexes of [section] (end exclusive), or None."""
    start = None
    for i, line in enumerate(lines):
        m = HEADER.match(line.strip())
        if not m:
            continue
        if start is not None:
            return start, i
        if m.group(1).strip() == section:
            start = i
    return (start, len(lines)) if start is not None else None


def option_span(lines, start, end, key):
    """Return (i, j) covering 'key' and its indented continuation lines, or None."""
    pat = re.compile(r'^%s\s*[:=]' % re.escape(key))
    for i in range(start + 1, end):
        if pat.match(lines[i]):
            j = i + 1
            while j < end and lines[j][:1] in (' ', '\t') and lines[j].strip():
                j += 1
            return i, j
    return None


def apply_block(lines, section, ops):
    span = find_section(lines, section)
    if span is None:
        raise KeyError(section)
    start, end = span
    for op, key, value in ops:
        if op == 'delsection':
            # Drop the section and the blank/comment lines that belong to it
            del lines[start:end]
            return lines
        hit = option_span(lines, start, end, key)
        if op == 'del':
            if hit:
                del lines[hit[0]:hit[1]]
                end -= hit[1] - hit[0]
            continue
        new = '%s: %s' % (key, value)
        if hit:
            lines[hit[0]:hit[1]] = [new]
            end -= (hit[1] - hit[0]) - 1
        else:
            insert = end
            while insert > start + 1 and not lines[insert - 1].strip():
                insert -= 1
            lines.insert(insert, new)
            end += 1
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('overrides')
    ap.add_argument('base_dir')
    ap.add_argument('--home', default=os.path.expanduser('~'))
    args = ap.parse_args()

    by_file = {}
    for fname, section, ops in parse_overrides(args.overrides, args.home):
        by_file.setdefault(fname, []).append((section, ops))

    for fname, blocks in by_file.items():
        path = os.path.join(args.base_dir, fname)
        if not os.path.exists(path):
            sys.exit("missing Happy Hare file: %s" % path)
        with open(path) as f:
            lines = f.read().split('\n')
        for section, ops in blocks:
            try:
                lines = apply_block(lines, section, ops)
            except KeyError:
                if any(op == 'delsection' for op, _, _ in ops):
                    continue  # already removed
                sys.exit("%s: section [%s] not found" % (path, section))
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
        print("overrides applied: %s" % fname)


if __name__ == '__main__':
    main()
