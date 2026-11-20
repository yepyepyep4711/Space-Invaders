#!/usr/bin/env python3
"""Add hi-score saving (cartridge RAM) to "Space Invaders (E) [S][!].gb".

Usage:  python patch_spaceinvaders.py "roms\\Space Invaders (E) [S][!].gb"
Output: same folder, "<name> (hi-score save).gb". The original is not modified.

Diagnostics (to find out which part of the patch causes a problem):
  --header-only   only the cartridge header is changed (RAM declared), no code at all.
  --load-only     header + boot hook; a saved hi-score is restored, nothing is saved.
  --save-only     header + update hook; the hi-score is saved, nothing is restored.

What it changes (everything is in bank 0; no bank switching, no interrupt hook)
  header 0x147   01 -> 03   MBC1 -> MBC1+RAM+BATTERY
  header 0x149   00 -> 02   8 KB cartridge RAM
  0x015F         "ld a,1 ; ld [$2100],a" (5 bytes) -> "call Load ; nop ; nop"
                 (Load ends with the same two instructions, so ROM bank 1 is selected
                 exactly as before)
  0x0A2E         "ldh a,[$8F] ; cp $AA" (4 bytes) -> "call SaveHi ; nop"
                 (SaveHi ends with the same two instructions, so the flags that the
                 following "jr z" tests are exactly as before)
  0x00A3-0x00FE  SaveHi (32 bytes) and Load (60 bytes): the unused padding between the
                 game's deferred-call routine (ends at $00A2) and the header

Game RAM
  hi-score   $FF8A (low) / $FF8B (high): 2 bytes of BCD, the last digit (always 0) is
             implied: 12140 on screen is 14 12. Default 01000 is set at boot ($0153-$0157),
             before Load runs. The boot clear loop at $01AF starts at $FF8F, so it does not
             touch it.
  score      $FFC8 / $FFC9, same layout.
  The game's update routine ($0A0C) compares score and hi-score high byte first and, if
  the score is higher or equal, copies it ($0A26-$0A2C). That is the only place in the
  Game Boy part of the ROM that writes $FF8A/$FF8B. SaveHi runs right after the copy.

Reset: Down + Select held at power-on writes the default (01000) to the save. The game's
four-button soft reset jumps to $0167, after the load, so it keeps the hi-score in RAM.
Only the Game Boy half of the ROM is touched; the SNES (Super Game Boy) data is not.

SRAM layout at $A000: low byte, high byte, check byte = $A5 + low + high (mod 256).
Load accepts a record only if the check byte matches. There is no room left for a
digit check, so random contents pass with a probability of 1 in 256.
"""
import sys
from pathlib import Path

HI_LO, HI_HI = 0xFF8A, 0xFF8B
SRAM = 0xA000
BOOT_HOOK = 0x015F
BOOT_ORIG = bytes.fromhex("3E01EA0021")            # ld a,1 ; ld [$2100],a
BOOT_CONTEXT = (0x0150, bytes.fromhex("F33E01E08B3E00E08AE08CE08DE08E3E01EA0021CD0068"))
UPDATE_HOOK = 0x0A2E
UPDATE_ORIG = bytes.fromhex("F08FFEAA")            # ldh a,[$8F] ; cp $AA
UPDATE_ROUTINE = (0x0A0C, bytes.fromhex(                # 0A0C-0A33, from the disassembly
    "F0D1 CB47 206D 218BFF F0C9 96 3865 200A 21C8FF F08A 96 2802 3059 "
    "F0C8 E08A F0C9 E08B F08F FEAA 284B".replace(" ", "")))
REGION = (0x00A3, 0x0100)                          # 93 bytes of noise between code and header
REGION_ORIG = bytes.fromhex(
    "FFFFFFFFFFFFEFFFBFFBFFBBFF"                                   # 00A3-00AF
    "FEEFFFFFBFFFFFFFFFF7FFFFFFFFFBFF"                             # 00B0-00BF
    "BFFFFFFFFEFFFBFFFEBFFFFFAFFFFFFF"                             # 00C0-00CF
    "FFFFFFFFBEFFFFFFFBFF3EFBFBFFBFFF"                             # 00D0-00DF
    "BFFFBFFFBFFFFFFFFEFFEFFFFFFFFFFF"                             # 00E0-00EF
    "BFFFFFFFEBFFEFFFEEFFEBFBBEFFAEFF")                            # 00F0-00FF
assert len(REGION_ORIG) == REGION[1] - REGION[0]

# Held together at power-on -> ignore the save and write the default.
RESET_DPAD = 0x08        # Right=1, Left=2, Up=4, Down=8
RESET_BUTTONS = 0x04     # A=1, B=2, Select=4, Start=8


def le(v):
    return bytes([v & 0xFF, v >> 8])


def asm(org, prog):
    """Tiny two-pass assembler: bytes, 'label:' strings, ('jr', opcode, label)."""
    labels, pos = {}, org
    for it in prog:
        if isinstance(it, bytes):
            pos += len(it)
        elif isinstance(it, str):
            labels[it.rstrip(":")] = pos
        else:
            pos += 2
    out, pos = bytearray(), org
    for it in prog:
        if isinstance(it, bytes):
            out += it
            pos += len(it)
        elif isinstance(it, tuple):
            _, op, lab = it
            off = labels[lab] - (pos + 2)
            assert -128 <= off <= 127, "jr out of range"
            out += bytes([op, off & 0xFF])
            pos += 2
    return bytes(out)


def build_savehi(org):
    """Write the hi-score and its check byte to cartridge RAM. Preserves BC and HL; ends
    with the two instructions it replaced (ldh a,[$8F] ; cp $AA), so A and the flags are
    exactly what the game expects."""
    return asm(org, [
        b"\xC5", b"\xE5",                      # push bc / hl
        b"\x3E\x0A", b"\xEA\x00\x00",          # ld a,$0A ; ld [$0000],a      enable SRAM
        b"\x21" + le(SRAM),                    # ld hl,$A000
        b"\xF0\x8A", b"\x22", b"\x47",         # ldh a,[$8A] ; ldi [hl],a ; ld b,a    low byte
        b"\xF0\x8B", b"\x22",                  # ldh a,[$8B] ; ldi [hl],a             high byte
        b"\x80", b"\xC6\xA5", b"\x77",         # add a,b ; add a,$A5 ; ld [hl],a      check byte
        b"\xAF", b"\xEA\x00\x00",              # xor a ; ld [$0000],a         disable SRAM
        b"\xE1", b"\xC1",                      # pop hl / bc
        b"\xF0\x8F", b"\xFE\xAA",              # the two replaced instructions
        b"\xC9",                               # ret
    ])


def build_load(org, savehi_addr):
    """Boot: Down+Select -> write the default, then restore the hi-score from the save if
    its check byte matches. Clobbers A, B, HL and the flags (nothing at boot depends on
    them). Ends with the two instructions it replaced (ld a,1 ; ld [$2100],a)."""
    return asm(org, [
        b"\x3E\x20", b"\xE0\x00",              # ld a,$20 ; ldh [$00],a       select d-pad
        b"\xF0\x00", b"\xF0\x00",              # ldh a,[$00] x2               (settle)
        b"\xE6" + bytes([RESET_DPAD]),         # and DOWN                     0 = pressed
        ("jr", 0x20, "norm"),                  # jr nz,norm
        b"\x3E\x10", b"\xE0\x00",              # ld a,$10 ; ldh [$00],a       select buttons
        b"\xF0\x00", b"\xF0\x00",
        b"\xE6" + bytes([RESET_BUTTONS]),      # and SELECT
        ("jr", 0x20, "norm"),
        b"\xCD" + le(savehi_addr),             # call SaveHi    held: the RAM still has the
        "norm:",                               #                game's default 01000 -> save it
        b"\x3E\x0A", b"\xEA\x00\x00",          # ld a,$0A ; ld [$0000],a      enable SRAM
        b"\x21" + le(SRAM),                    # ld hl,$A000
        b"\x2A", b"\x86",                      # ldi a,[hl] ; add a,[hl]      low + high
        b"\xC6\xA5",                           # add a,$A5
        b"\x23", b"\xBE",                      # inc hl ; cp [hl]             check byte
        ("jr", 0x20, "fin"),                   # jr nz,fin     invalid -> keep the default
        b"\x2B", b"\x3A",                      # dec hl ; ldd a,[hl]          high byte
        b"\xE0\x8B",                           # ldh [$8B],a
        b"\x7E", b"\xE0\x8A",                  # ld a,[hl] ; ldh [$8A],a      low byte
        "fin:",
        b"\xAF", b"\xEA\x00\x00",              # xor a ; ld [$0000],a         disable SRAM
        b"\x3E\x01", b"\xEA\x00\x21",          # the two replaced instructions
        b"\xC9",                               # ret
    ])


def fix_checksums(rom):
    c = 0
    for b in rom[0x134:0x14D]:
        c = (c - b - 1) & 0xFF
    rom[0x14D] = c
    g = (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF
    rom[0x14E], rom[0x14F] = g >> 8, g & 0xFF


def expect(rom, addr, want, what):
    got = bytes(rom[addr:addr + len(want)])
    if got != want:
        sys.exit(f"Refusing to patch: {what} at 0x{addr:04X} is {got.hex(' ')}, "
                 f"expected {want.hex(' ')}. Wrong ROM version?")


def main(path, header_only=False, only=None):
    """only: None (full patch) or a diagnostic build: 'load' or 'save'."""
    src = Path(path)
    rom = bytearray(src.read_bytes())
    if len(rom) != 0x80000:
        sys.exit("Expected a 512 KB ROM.")

    expect(rom, 0x134, b"SPACE INVADERS", "title")
    expect(rom, 0x147, b"\x01", "cartridge type")
    expect(rom, 0x148, b"\x04", "ROM size")
    expect(rom, 0x149, b"\x00", "RAM size")
    expect(rom, 0x14D, b"\x62", "header checksum")
    expect(rom, 0x14E, b"\x1F\xA8", "global checksum")
    expect(rom, BOOT_CONTEXT[0], BOOT_CONTEXT[1], "boot code")
    expect(rom, UPDATE_ROUTINE[0], UPDATE_ROUTINE[1], "hi-score update routine")
    expect(rom, REGION[0], REGION_ORIG, "padding area")

    if header_only:
        rom[0x147] = 0x03
        rom[0x149] = 0x02
        fix_checksums(rom)
        dst = src.with_name(src.stem + " (header only).gb")
        dst.write_bytes(rom)
        print(f"Written: {dst}  (header only, no save code)")
        return dst

    savehi_addr = REGION[0]
    savehi = build_savehi(savehi_addr)
    load_addr = savehi_addr + len(savehi)
    load = build_load(load_addr, savehi_addr) if only in (None, "load") else b""
    end = load_addr + len(load)
    if end > REGION[1]:
        sys.exit(f"The new code needs {end - savehi_addr} bytes, only {REGION[1] - savehi_addr} available.")
    print(f"SaveHi: {len(savehi)} bytes at 0x{savehi_addr:04X}")
    if load:
        print(f"Load  : {len(load)} bytes at 0x{load_addr:04X}  ({REGION[1] - end} bytes of the area left)")

    rom[savehi_addr:end] = savehi + load
    if only in (None, "save"):
        rom[UPDATE_HOOK:UPDATE_HOOK + 4] = b"\xCD" + le(savehi_addr) + b"\x00"      # call SaveHi ; nop
    if load:
        rom[BOOT_HOOK:BOOT_HOOK + 5] = b"\xCD" + le(load_addr) + b"\x00\x00"        # call Load ; nop ; nop
    rom[0x147] = 0x03        # MBC1+RAM+BATTERY
    rom[0x149] = 0x02        # 8 KB RAM
    fix_checksums(rom)

    suffix = {None: "hi-score save", "load": "load only", "save": "save only"}[only]
    dst = src.with_name(f"{src.stem} ({suffix}).gb")
    dst.write_bytes(rom)
    print(f"Written: {dst}" + ("" if only is None else "  (diagnostic build, not the full patch)"))
    return dst


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    flags = {"--load-only": "load", "--save-only": "save"}
    only = next((v for k, v in flags.items() if k in sys.argv), None)
    main(args[0], header_only="--header-only" in sys.argv, only=only)
