#!/usr/bin/env python3
"""Build the release package for the Space Invaders hi-score-save hack.

Usage (patch_spaceinvaders.py must be in the same folder):
    python make_release_spaceinvaders.py "roms\\Space Invaders (E) [S][!].gb" --author "Your Name"
        [--version 1.0] [--repo https://github.com/<you>/<repo>]

Creates  release\\Space Invaders - Hi-score Save v<version>.zip  containing
  - a BPS patch (recommended: checks that you have the right base ROM)
  - an IPS patch (for tools that only know IPS)
  - README.txt (with the base ROM's size, CRC32, MD5 and SHA-1)
The zip contains only what is needed to patch the game: neither the ROM nor the
Python scripts are included (the scripts belong in the repository).
Also writes release\\README.md, the same information as a GitHub README.
Both patches are applied again to the original and compared with the real output
before the zip is written.
"""
import argparse
import datetime
import hashlib
import shutil
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_spaceinvaders as pb  # noqa: E402

NAME = "Space Invaders - Hi-score Save"
FILE_NAME = NAME
# Edit this to name what you really tested (it appears in both READMEs):
TESTED_ON = ("Emulators: BGB and mGBA.\n"
             "Real hardware: EZ Flash Jr and generic single-game rewritable cartridges, played on Game Boy,\n"
             "Game Boy Color, Super Game Boy, Analogue Pocket and ModRetro Chromatic. Tested: saving, loading,\n"
             "hi-score reset and soft resets. In Super Game Boy mode the hi-score is the same as on any other\n"
             "Game Boy, so you get the Super Game Boy's visual enhancements and keep chasing the same hi-score\n"
             "as on the go. The SNES version of the game (which does not save) still runs as before.")


# ---------------------------------------------------------------- IPS
def make_ips(src, dst, gap=6):
    assert len(src) == len(dst) <= 0x1000000
    runs, i, n = [], 0, len(dst)
    while i < n:
        if src[i] == dst[i]:
            i += 1
            continue
        j = i + 1
        last = i                      # last differing byte seen
        while j < n and j - last <= gap:
            if src[j] != dst[j]:
                last = j
            j += 1
        runs.append((i, last + 1))
        i = last + 1
    out = bytearray(b"PATCH")
    for a, b in runs:
        while a < b:
            size = min(b - a, 0xFFFF)
            assert a != 0x454F46, "offset collides with the IPS 'EOF' marker"
            out += a.to_bytes(3, "big") + size.to_bytes(2, "big") + dst[a:a + size]
            a += size
    return bytes(out + b"EOF")


def apply_ips(src, patch):
    assert patch[:5] == b"PATCH" and patch[-3:] == b"EOF"
    out, p = bytearray(src), 5
    while patch[p:p + 3] != b"EOF" or p + 3 != len(patch):
        off = int.from_bytes(patch[p:p + 3], "big")
        size = int.from_bytes(patch[p + 3:p + 5], "big")
        p += 5
        if size == 0:                                   # RLE record
            run = int.from_bytes(patch[p:p + 2], "big")
            out[off:off + run] = bytes([patch[p + 2]]) * run
            p += 3
        else:
            out[off:off + size] = patch[p:p + size]
            p += size
    return bytes(out)


# ---------------------------------------------------------------- BPS
def bps_num(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def make_bps(src, dst, metadata=b""):
    assert len(src) == len(dst)
    out = bytearray(b"BPS1")
    out += bps_num(len(src)) + bps_num(len(dst)) + bps_num(len(metadata)) + metadata
    i, n = 0, len(dst)
    while i < n:
        j = i
        same = src[i] == dst[i]
        while j < n and (src[j] == dst[j]) == same:
            j += 1
        length = j - i
        if same:                                        # SourceRead
            out += bps_num(((length - 1) << 2) | 0)
        else:                                           # TargetRead
            out += bps_num(((length - 1) << 2) | 1) + dst[i:j]
        i = j
    out += zlib.crc32(src).to_bytes(4, "little") + zlib.crc32(dst).to_bytes(4, "little")
    out += zlib.crc32(out).to_bytes(4, "little")
    return bytes(out)


def apply_bps(src, patch):
    assert patch[:4] == b"BPS1"
    assert zlib.crc32(patch[:-4]) == int.from_bytes(patch[-4:], "little"), "patch CRC"
    assert zlib.crc32(src) == int.from_bytes(patch[-12:-8], "little"), "wrong base ROM"

    def num(p):
        data, shift = 0, 1
        while True:
            x = patch[p]
            p += 1
            data += (x & 0x7F) * shift
            if x & 0x80:
                return data, p
            shift <<= 7
            data += shift

    p = 4
    ssize, p = num(p)
    tsize, p = num(p)
    msize, p = num(p)
    p += msize
    out = bytearray()
    while p < len(patch) - 12:
        data, p = num(p)
        cmd, length = data & 3, (data >> 2) + 1
        if cmd == 0:
            out += src[len(out):len(out) + length]
        elif cmd == 1:
            out += patch[p:p + length]
            p += length
        else:
            raise NotImplementedError("this encoder only emits SourceRead/TargetRead")
    assert len(out) == tsize
    assert zlib.crc32(out) == int.from_bytes(patch[-8:-4], "little"), "target CRC"
    return bytes(out)


# ---------------------------------------------------------------- README
README = """\
{name}
Version {version}  -  by {author}  -  {date}
==============================================================================

DESCRIPTION
  Adds saving of the hi-score to Space Invaders (Game Boy, Europe, Super Game Boy
  enhanced). The game itself is unchanged: no new screens, no new menus. The
  hi-score you reached last time is simply still there the next time you play,
  instead of going back to 01000 every time the console is switched on.
  Only the Game Boy half of the ROM is changed. The ROM also contains the SNES
  version of the game used with the Super Game Boy; that part is not touched and
  does not use the save.

BASE ROM
  The patch applies to this exact file and no other:
      Name  : {rom_name}
      Size  : {size} bytes
      CRC32 : {crc32}
      MD5   : {md5}
      SHA-1 : {sha1}
  Check your copy before patching. A different dump (or one with a header) will
  not work. The BPS patch refuses to apply to a wrong ROM; the IPS patch cannot
  tell and would produce a broken game.

PATCHING
  Use the online patcher at https://www.romhacking.net/patch/ (it works in your
  browser, so there is nothing to install) or any other IPS/BPS patcher. Apply
  the BPS patch if you can (it verifies the base ROM); the IPS patch is identical
  in effect. Keep your original ROM; the patcher gives you a new file.

REQUIREMENTS
  Saving needs cartridge RAM that keeps its contents when the power is off:
    - Emulators: any emulator that supports MBC1 + RAM + battery. A .sav file is
      created next to the ROM (BGB, SameBoy, mGBA, etc.).
    - Real hardware: a flash cart or rewritable cartridge that supports MBC1 with
      8 KB of save RAM. Battery-backed RAM and non-volatile FRAM both qualify, for
      example the DMG-GBWR-50 rewritable cartridge.
  On hardware without save RAM the game still plays normally, but, as in the
  original game, the hi-score is lost when the console is switched off.

HOW IT WORKS FOR THE PLAYER
  - Nothing to do. The hi-score is stored automatically whenever you beat it.
  - The game's four-button soft reset keeps the hi-score, as in the original game.
- On a Super Game Boy the Game Boy version uses the same saved hi-score as on any other Game Boy.
  - On a Super Game Boy the Game Boy version uses the same saved hi-score as on any
    other Game Boy.
  - To reset the hi-score to 01000: switch the console on while holding
    DOWN + SELECT.

KNOWN LIMITATIONS
  - Only the hi-score is saved; nothing else.
  - The save has a check byte, but the digits are not validated (there is no room
    left for that). A damaged save is ignored in all but about 1 case in 256, where
    a meaningless hi-score could appear; use DOWN + SELECT at power-on to reset it.
  - The SNES (Super Game Boy) half of the ROM does not save anything.

TECHNICAL NOTES
  Changes to the ROM (all in bank 0; no bank switching, no interrupt hooked):
    Header          0x147 01 -> 03 (MBC1+RAM+BATTERY), 0x149 00 -> 02 (8 KB RAM),
                    header and global checksums recalculated.
    0x015F          "ld a,1 ; ld [$2100],a" in the boot code replaced by
                    "call ${load_addr:04X} ; nop ; nop" (boot hook; the new code ends with the
                    same two instructions, so ROM bank 1 is selected as before).
    0x0A2E          "ldh a,[$8F] ; cp $AA" in the game's hi-score update routine
                    replaced by "call ${save_addr:04X} ; nop" (save hook; the new code ends with
                    the same two instructions, so the flags are as the game expects).
    0x{save_addr:04X}-0x{end_addr:04X}  the new code, {total_len} bytes (save {save_len}, load {load_len}),
                    in unused padding between the end of the game's code at $00A2 and the header.
  Game RAM:   hi-score = $FF8A (low) / $FF8B (high), 2 bytes of BCD with the last
              digit (always 0) implied: 12140 on screen is 14 12. Score = $FFC8 / $FFC9,
              same layout. The default 01000 is set at boot, before the load runs.
  Save RAM at $A000: low byte, high byte, check byte ($A5 + low + high).
  Load runs once per power-on, after the game sets its default; a valid save
  replaces the default, a missing or damaged one leaves it alone. With DOWN + SELECT
  held it writes the default to the save instead.
  Save runs only when the game's own update routine ($0A0C) has copied a score that
  is higher than or equal to the hi-score. Nothing runs every frame.
  The four-button soft reset jumps to $0167, after the load hook, so RAM is kept.
  If you have Python, you can try this yourself using the scripts from the
  repository{repo_note}:
  {patcher_script} rebuilds the patched ROM from your original ROM, and
  {release_script} builds the patches, READMEs and zip.

TESTING
  {tested_on}

VERSION HISTORY
  {version}  Initial release.

LEGAL
  This package contains no game data, only the differences. You need your own
  copy of the original game. Space Invaders is the property of its respective
  owners; this is an unofficial fan modification and is not affiliated with them.
"""

README_MD = """\
# {name}

**Hi-score saving** for *Space Invaders* (Game Boy, Europe, Super Game Boy enhanced). The game is
unchanged: no new screens or menus. The hi-score you reached last time is simply still there next
time, instead of going back to 01000 whenever the console is switched off.

Only the Game Boy half of the ROM is changed. The ROM also holds the SNES version used with the
Super Game Boy; it is not touched and does not use the save.

**Download:** see the [latest release]({releases_url}) (BPS and IPS patches).
This repository contains no game data; you need your own copy of the ROM.

## Base ROM

The patch applies to exactly this file:

| This | Should be this |
|-------|-----|
| Name | `{rom_name}` |
| Size | {size} bytes |
| CRC32 | `{crc32}` |
| MD5 | `{md5}` |
| SHA-1 | `{sha1}` |

The BPS patch verifies this and refuses to apply to anything else; the IPS patch cannot.

## Patching

Apply the `.bps` patch (preferred) or the `.ips` patch to your ROM with the online patcher at
<https://www.romhacking.net/patch/> (it works in your browser, so there is nothing to
install) or any other IPS/BPS patcher. Your original is not modified.

## Requirements

Saving needs cartridge RAM:

- **Emulators:** anything that supports MBC1 + RAM + battery (BGB, SameBoy, mGBA, ...).
  A `.sav` file appears next to the ROM.
- **Hardware:** a flash cart or rewritable cartridge supporting MBC1 with 8 KB of save
  RAM. Battery-backed RAM and non-volatile FRAM both qualify; the DMG-GBWR-50 rewritable
  cartridge uses FRAM.

Without save RAM the game still plays, but, as in the original game, the hi-score is lost when
the console is switched off.

## Using it

- Nothing to do: the hi-score is stored automatically whenever you beat it.
- The game's four-button soft reset keeps the hi-score, as in the original game.
- On a Super Game Boy the Game Boy version uses the same saved hi-score as on any other Game Boy.
- **Reset the hi-score to 01000:** switch the console on while holding **Down + Select**.

## Limitations

- Only the hi-score is saved.
- The save has a check byte, but the digits are not validated (no room left). A damaged save is
  ignored in all but about 1 case in 256, where a meaningless hi-score could appear; reset it with
  Down + Select at power-on.
- The SNES (Super Game Boy) half does not save anything.

## How it works

Everything goes into unused padding in bank 0 or hook points; the header is changed to
MBC1+RAM+BATTERY (`0x147` 01 to 03, `0x149` 00 to 02) and its checksums are recalculated.

| Where | What |
|---|---|
| `0x015F` | boot hook: `ld a,1 ; ld [$2100],a` becomes `call ${load_addr:04X} ; nop ; nop` (the new code ends with the same two instructions) |
| `0x0A2E` | save hook in the hi-score update routine: `ldh a,[$8F] ; cp $AA` becomes `call ${save_addr:04X} ; nop` (the new code ends with the same two instructions) |
| `0x{save_addr:04X}`-`0x{end_addr:04X}` | the new code, {total_len} bytes (save {save_len}, load {load_len}), in unused padding before the header |

Game RAM: hi-score `$FF8A` (low) / `$FF8B` (high), 2 bytes of BCD with the last digit (always 0)
implied: 12140 on screen is `14 12`. Score is `$FFC8`/`$FFC9`, same layout. The default 01000 is set at
boot, before the load runs. Save RAM at `$A000`: low byte, high byte, check byte (`$A5` + low + high).

- The **load routine** runs once per power-on, after the game sets its default. A valid save replaces
  it; a missing or damaged one leaves it alone. With Down + Select held it writes the default to the save.
- The **save routine** runs only when the game's own update routine (`$0A0C`) has copied a score that is
  at least the hi-score. Nothing runs every frame and no interrupt is hooked.
- The four-button soft reset jumps to `$0167`, after the load hook, so RAM is kept.

If you have Python, you can try this yourself using the scripts from the repository:
`{patcher_script}` rebuilds the patched ROM from your original ROM, and
`{release_script}` builds the patches, READMEs and zip.

## Tested

{tested_on}

## Legal

No game data is included, only the differences. *Space Invaders* belongs to its respective
owners; this is an unofficial fan modification and is not affiliated with them.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("--author", default="Your Name")
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--outdir", default="release")
    ap.add_argument("--repo", default="", help="repository URL, used in README.txt and for the release link in README.md")
    a = ap.parse_args()

    src_path = Path(a.rom)
    src = src_path.read_bytes()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_src = Path(tmp) / src_path.name
        shutil.copy(src_path, tmp_src)
        patched_path = pb.main(str(tmp_src))      # the patcher says where it wrote the ROM
        dst = Path(patched_path).read_bytes()

    ips, bps = make_ips(src, dst), make_bps(src, dst)
    assert apply_ips(src, ips) == dst, "IPS round trip failed"
    assert apply_bps(src, bps) == dst, "BPS round trip failed"
    print(f"IPS: {len(ips)} bytes, BPS: {len(bps)} bytes (both verified against the real output)")
    print(f"Patched ROM: CRC32 {zlib.crc32(dst):08X}  SHA-1 {hashlib.sha1(dst).hexdigest().upper()}")

    base = f"{FILE_NAME} v{a.version}"
    # layout numbers come from the patcher, so the README can never drift from the code
    save_addr = pb.REGION[0]
    load_addr = save_addr + len(pb.build_savehi(save_addr))
    end_addr = load_addr + len(pb.build_load(load_addr, save_addr)) - 1
    names = dict(patcher_script=Path(pb.__file__).name, release_script=Path(__file__).name,
                 save_addr=save_addr, load_addr=load_addr, end_addr=end_addr,
                 total_len=end_addr + 1 - save_addr, save_len=load_addr - save_addr,
                 load_len=end_addr + 1 - load_addr, tested_on=TESTED_ON)
    hashes = dict(rom_name=src_path.name, size=len(src), crc32=f"{zlib.crc32(src):08X}",
                  md5=hashlib.md5(src).hexdigest().upper(), sha1=hashlib.sha1(src).hexdigest().upper())
    names_txt = dict(names, tested_on=TESTED_ON.replace("\n", "\n  "))   # keep README.txt's indentation
    readme = README.format(repo_note=f" ({a.repo})" if a.repo else "", **names_txt, **hashes,
                           name=NAME, version=a.version, author=a.author,
                           date=datetime.date.today().isoformat())
    releases_url = f"{a.repo.rstrip('/')}/releases/latest" if a.repo else "../../releases/latest"
    readme_md = README_MD.format(**names, **hashes, releases_url=releases_url, name=NAME)

    outdir = Path(a.outdir)
    outdir.mkdir(exist_ok=True)
    (outdir / "README.md").write_text(readme_md, encoding="utf-8")
    zpath = outdir / f"{base}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{base}.bps", bps)
        z.writestr(f"{base}.ips", ips)
        z.writestr("README.txt", readme)
    print(f"Written: {zpath}")
    print(f"Base ROM CRC32 {hashes['crc32']}  SHA-1 {hashes['sha1']}")


if __name__ == "__main__":
    main()
