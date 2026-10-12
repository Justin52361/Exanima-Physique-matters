# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows-only binary patcher ("Exanima – Build Matters") that makes the character-creation Physique box affect gameplay. It appends a new `.bld` section containing hand-assembled x86-64 code to `Exanima.exe`, then hooks two places with a `jmp` into it: the hit routine (damage/health) and the attack-animation clock (attack speed). No game files are shipped. See `README.md` for user-facing behaviour and the status table.

## Commands

Requires Python 3.8+ and `pip install -r requirements.txt` (only `pefile`). Run from the repo root:

```
python -m build_patch apply      # patch Exanima.exe (auto-detects Steam install; re-run after editing config.ini)
python -m build_patch restore    # copy Exanima.exe.bak back over the exe
python -m build_patch status     # show whether patched + active multipliers (read back from the .bld section)
python -m build_patch build --out X.exe   # write a patched copy elsewhere, touches nothing in the game folder
```
Options: `--config PATH`, `--exe PATH`. `apply.bat` / `restore.bat` / `status.bat` just wrap these.

Dev tools (need a **running** Exanima; nothing on disk is modified):
```
python -m tools.livepatch install [--everyone] | remove | status   # inject the damage hook into the live process
python -m tools.livepatch install-speed [--everyone] | remove-speed | set-speed LEFT BOTTOM   # attack-speed hook only (works on an already-patched exe)
python -m tools.calc_test                                          # run the injected `calc` routine on fake builds vs. a Python reference
```
There is no test suite, linter, or build step beyond these; `calc_test` is the only verification of the machine code's maths.

## Architecture

- `config.ini` → `build_patch/config.py`: user-facing multipliers (1.5 = +50%) are converted to "bonus" values (0.5) by `to_bonus`/`from_bonus`. `cave.BONUS` holds the defaults and its keys (`dmg_top`, `dmg_bottom`, `spd_bottom`, `spd_left`, `hp_right`) are the contract between config, cave, patcher and `calc_test`'s `reference()`.
- `build_patch/cave.py`: builds the injected code via `miniasm.Asm`. Holds all game addresses (no ASLR, absolute): hook site `HIT_SITE=0x10015C65F` (inside the contact routine at `0x100159a60`), the `HIT_ORIG` bytes expected there, player dynamics global, and struct offsets (`TMotileDynamics+0x10A0 → TSGCharacter`, physique x/y at `+0x2C/+0x30`). The `calc` routine maps (x,y) to damage/health/speed multipliers (diamond-clamped blend, centre = 1.0); the hit hook scales the three damage values by `attacker_damage / victim_health`. The `spd` hook replaces 12 bytes at `SPD_SITE=0x10016CAF8` (inside the per-tick dynamics update `0x100169200`, only reached for attack sequences 5..12 at `TMotileDynamics+0x9B8`) and does the clock update itself — `clock(+0xA20) += step(+0xDC8) * speed` — then jumps to `SPD_RESUME`. `SPD_CHECK` (the whole original block) is verified before patching. Constants and the `FLAG_ALL` (player vs everyone) flag are emitted as labelled data and read back by name.
- `build_patch/miniasm.py`: minimal assembler supporting only the instruction forms the cave uses (labels with rel32 fixups, rip-relative operands). Add instruction forms here when the cave needs new ones.
- `build_patch/patcher.py`: PE surgery with `pefile` — verifies `HIT_ORIG` / `SPD_CHECK` at the hook sites (refuses to patch other game versions), appends the `.bld` section header/data, fixes NumberOfSections/SizeOfImage/checksum, overwrites the hook sites with `jmp rel32` + nops (displaced instructions are re-executed in the cave). `apply` always re-patches from `Exanima.exe.bak` if the exe is already patched, and refreshes the backup from the on-disk exe when it is pristine. `status` recovers settings by rebuilding the cave at the section's base address to get label offsets.
- `tools/livepatch.py` uses the same `cave.build` (with `far=`/`debug=` options) to inject into a live process via Win32 APIs; `calc_test.py` imports its `Proc`/`k` helpers.

When changing the cave layout, keep `read_settings` in `patcher.py` and the labels (`K_QPOS_DMG`, `K_QNEG_DMG`, `K_QNEG_SPD`, `K_PNEG_SPD`, `K_PPOS_HP`, `FLAG_ALL`) in sync, and update `KNOWN_SHA256` / `HIT_*` / `SPD_*` only against a verified game build.
