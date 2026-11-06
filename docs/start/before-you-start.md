---
title: Before you start
description: The one risky step of the conversion, how the installer protects you, and how to go back.
---

q2-offload replaces Qidi's firmware on the printer's three microcontrollers (mainboard,
toolhead, Box) with Klipper. Most of it can be redone as often as you like. **One step, once,
needs care.**

## The step that needs care

The very first time, the installer replaces Qidi's **bootloader** (the small program that
lets a microcontroller receive new firmware) with **Katapult**, using Qidi's own update
scripts. No special hardware is needed.

> [!CAUTION]
> If the power is cut during that step, or the wrong image is written, the microcontroller
> may not start again, and recovering it needs an **ST-Link** (a small programmer wired to the
> board). Keep the printer powered and connected until the installer says it's done.

How the installer protects that step:

- the images it writes are pinned by checksum, and the printer is checked first: it stops,
  with nothing flashed, if a microcontroller or root access is missing;
- one microcontroller at a time, each checked before the next;
- you type `INSTALL KATAPULT` to start it.

## Everything after that is safe to retry

Once Katapult is there, Klipper is flashed through it, now and at every update that needs it.
Katapult checks the microcontroller type, and the installer refuses to write if the address
it would write to is wrong. If a flash fails, Katapult is still there: run it again.
Each flash asks you to type `FLASH`, and it never runs during a print or from the web
interface: someone has to be at the printer.

## Can I go back to Qidi's firmware?

Yes, without an ST-Link: Qidi's own images can be flashed back through Katapult. It isn't
automated yet. See [Going back to stock](../help/back-to-stock.md).

## In short

- Read the installer's messages: it says what it is about to do before each step.
- Don't switch the printer off while it flashes.
- There is no warranty (the project is GPL-3.0): you do this at your own risk.

Next: [Prepare the host](../install/prepare-host.md).
