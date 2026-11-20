# Space Invaders - Hi-score Save

**Hi-score saving** for *Space Invaders* (Game Boy, Europe, Super Game Boy enhanced). The game is
unchanged: no new screens or menus. The hi-score you reached last time is simply still there next
time, instead of going back to 01000 whenever the console is switched off.

Only the Game Boy half of the ROM is changed. The ROM also holds the SNES version used with the
Super Game Boy; it is not touched and does not use the save.

**Download:** see the [latest release](https://github.com/yepyepyep4711/Space-Invaders/releases/latest) (BPS and IPS patches).
This repository contains no game data; you need your own copy of the ROM.

## Base ROM

The patch applies to exactly this file:

| This | Should be this |
|-------|-----|
| Name | `Space Invaders (E) [S][!].gb` |
| Size | 524288 bytes |
| CRC32 | `891B8F04` |
| MD5 | `704CEFB5C77DC74631B9ACBAA2B19435` |
| SHA-1 | `6395CA055DE6B6538B915D0CB69BD829D7AA2E2A` |

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
| `0x015F` | boot hook: `ld a,1 ; ld [$2100],a` becomes `call $00C3 ; nop ; nop` (the new code ends with the same two instructions) |
| `0x0A2E` | save hook in the hi-score update routine: `ldh a,[$8F] ; cp $AA` becomes `call $00A3 ; nop` (the new code ends with the same two instructions) |
| `0x00A3`-`0x00FE` | the new code, 92 bytes (save 32, load 60), in unused padding before the header |

Game RAM: hi-score `$FF8A` (low) / `$FF8B` (high), 2 bytes of BCD with the last digit (always 0)
implied: 12140 on screen is `14 12`. Score is `$FFC8`/`$FFC9`, same layout. The default 01000 is set at
boot, before the load runs. Save RAM at `$A000`: low byte, high byte, check byte (`$A5` + low + high).

- The **load routine** runs once per power-on, after the game sets its default. A valid save replaces
  it; a missing or damaged one leaves it alone. With Down + Select held it writes the default to the save.
- The **save routine** runs only when the game's own update routine (`$0A0C`) has copied a score that is
  at least the hi-score. Nothing runs every frame and no interrupt is hooked.
- The four-button soft reset jumps to `$0167`, after the load hook, so RAM is kept.

If you have Python, you can try this yourself using the scripts from the repository:
`patch_spaceinvaders.py` rebuilds the patched ROM from your original ROM, and
`make_release_spaceinvaders.py` builds the patches, READMEs and zip.

## Tested

Emulators: BGB and mGBA.
Real hardware: EZ Flash Jr and generic single-game rewritable cartridges, played on Game Boy,
Game Boy Color, Super Game Boy, Analogue Pocket and ModRetro Chromatic. Tested: saving, loading,
hi-score reset and soft resets. In Super Game Boy mode the hi-score is the same as on any other
Game Boy, so you get the Super Game Boy's visual enhancements and keep chasing the same hi-score
as on the go. The SNES version of the game (which does not save) still runs as before.

## Legal

No game data is included, only the differences. *Space Invaders* belongs to its respective
owners; this is an unofficial fan modification and is not affiliated with them.
