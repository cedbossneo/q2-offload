---
title: Spools and NFC tags
description: Tag a spool once, and the Box recognises it in any gate, with its Spoolman record.
---

The Qidi Box has two NFC readers, one for gates 0 and 1, one for gates 2 and 3. With a tag on
each spool, the printer knows which spool is in which gate, and Spoolman keeps track of it.

## Tag a spool

1. **Get NTAG215 stickers.** Leave them unlocked, so you can rewrite them.

2. **Write the tag with your phone**, using an OpenSpool app (OpenSpool or SpoolFlux, for
   example): brand, material, colour, temperatures. Spell brand and material the same way
   every time, or Spoolman creates duplicate filaments.

3. **Stick it on the flange**, on the side that faces the neighbouring gate.

4. **Load the spool in the Box.** The reader picks up the tag as the Box preloads it.

## What happens on the first scan

Happy Hare creates the vendor, the filament (one per colour) and the spool in Spoolman, and
remembers the tag on the spool. Later scans of that tag select the same spool, in whatever
gate you put it.

When brand, material and colour match an entry of **SpoolmanDB** (the filament database built
into Spoolman), the filament gets the manufacturer's name, temperatures, density and spool
weight. The closest colour wins, so a colour picked in the app is fine. A filament you already
imported from SpoolmanDB is reused. Without a match, the filament is named after its material
and uses the tag's temperatures: rename it in Spoolman.

A new filament also gets an offer to [measure its pressure advance](pressure-advance.md).

> [!NOTE]
> New spools are created with 1000 g. For a part-used spool, correct the weight in Spoolman.

<details>
<summary>The Box didn't see the tag</summary>

`MMU_NFC_SCAN GATE=n` turns the spool a full revolution to look for a tag the preload missed.

</details>
