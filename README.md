# Exanima – Build Matters

In vanilla Exanima the **Physique** box on the character-creation screen is purely cosmetic.
This mod makes it matter. Where you put the marker decides how your character fights:

```
                        TOP — muscular
                        hits deal +100% damage
                               │
   LEFT — skinny               │                RIGHT — fat
   +100% attack speed    ───  centre  ───        ×2 health
                               │                (normal)
                               │
                  BOTTOM — muscular lean
                  +50% damage, +50% attack speed
```

* The **exact centre** of the box is "normal" – no bonus at all.
* Everything in between **blends smoothly**. The corners are an even mix of the two neighbouring edges
  (top-left = +50% damage and +50% attack speed, top-right = +50% damage and ×1.50 health, …).
* **Every number is yours to change** – see [Changing the numbers](#changing-the-numbers).

---

## Install

You need **Windows**, **Python 3.8+** and the Steam version of Exanima.

1. Download / clone this repository.
2. Install the one dependency once: `pip install -r requirements.txt`
3. **Close Exanima**, then double-click **`apply.bat`**
   (or run `python -m build_patch apply` in this folder).

That's it. Start the game as usual and make a **new character** (or load one – any character's build is used).
Existing saves work: the build is already stored in the character.

The script finds your Steam install by itself. If it can't (GOG, odd setup), put the full path to `Exanima.exe`
into `game_exe =` in `config.ini`.

### Undo

Double-click **`restore.bat`** (or `python -m build_patch restore`). A backup of the original `Exanima.exe` is kept
next to it as `Exanima.exe.bak`; restoring puts back exactly the original file.
Steam's *Verify integrity of game files* also removes the mod. Game updates replace the exe too – just run `apply.bat` again.

### Check what is active

`status.bat` (or `python -m build_patch status`) prints whether the exe is patched and the values inside it.

---

## Changing the numbers

Open **`config.ini`**, edit, save, and run **`apply.bat`** again (it re-patches from the untouched original, you do not
need to restore first). The numbers are *multipliers*: `1.0` = no change, `1.5` = +50 %, `0.5` = −50 %.

```ini
[build]
muscular_damage            = 1.5     ; TOP:    your hits deal this much damage
muscular_lean_damage       = 1.25    ; BOTTOM: ... and this much
muscular_lean_attack_speed = 1.25    ; BOTTOM: attack animations play this much faster
skinny_attack_speed        = 1.5     ; LEFT:   ... and this much
fat_health                 = 1.5     ; RIGHT:  damage you take is divided by this

[options]
apply_to = player                    ; or 'everyone'
game_exe =                           ; leave empty to auto-detect
```

Examples: you think 1.5× health is too strong → `fat_health = 1.25`. You want muscular to be a glass cannon
and fat to be a real tank → `muscular_damage = 2.0`, `fat_health = 2.0`. Values below 1 work too
(`skinny_attack_speed = 0.9` would be a handicap). Allowed range is 0.05 – 100.

**`apply_to = everyone`** makes the same rules apply to every character in the world, each according to *its own*
build. Many NPCs have random builds, so this makes fights less predictable (a fat enemy soaks more, a muscular one
hits harder). The default `player` leaves all enemies exactly as vanilla.

---

## How "health" works

Rather than editing a health stat, the mod divides the damage you take from hits by `fat_health`. Against hits that is
exactly a ×`fat_health` bigger health pool. Things that are not hits (bleeding, falling, …) are not scaled.

## How "attack speed" works

Every attack is a wind-up animation followed by a swing animation. The mod makes both play faster by
`attack_speed`, so ×1.5 means a whole attack takes about two thirds of the time. Walking and the recovery stance after
a swing are unchanged. Exanima simulates the weapon physically, so a faster swing can also land a little harder.

## Status

| Effect | State |
|---|---|
| Hit damage (muscular, muscular lean) | ✅ works, verified in game |
| Health (fat) | ✅ works for damage from hits |
| Attack speed (skinny, muscular lean) | ✅ works, verified in game |

Tested against the Steam build of Exanima whose `Exanima.exe` has SHA-256
`af9033c7857565ddf2e842a486b0a158b32375a8f95e18b69f4e171b919b6f70`. The patcher checks that the code it hooks is where it
expects it and refuses to patch otherwise, so a newer game version will produce an error instead of a broken game.

## Safety / disclaimer

* This is an unofficial fan mod, not affiliated with Bare Mettle Entertainment.
* It edits **your local copy** of `Exanima.exe` (it ships none of the game's files). Make sure you are comfortable with that.
  Because it modifies an executable, some antivirus programs may complain – the source is all here to read.
* Exanima is single player, but as with any mod: use at your own risk.

---

## For modders – how it works

* The marker position (x, y, both 0..1, origin top-left) is stored in the character record
  (`TSGCharacter + 0x2c / 0x30`). Every body (`TMotileDynamics`) points to its record at `+0x10a0`; the player's body is the
  global at `0x1004F0830`. Zombies etc. default to (0.5, 0.5) = the centre = "normal".
* `0x100159a60` is the contact/hit routine. Right before the result is applied (`0x10015C65F`) the patch jumps into a
  small routine that works out the attacker's damage multiplier and the victim's health multiplier from their builds and scales
  the three damage values by `attacker_damage / victim_health`.
* Attack animations are motion sequences 5–12 (`TMotileDynamics + 0x9b8`). Each physics tick their clock
  (`+0xa20`) is advanced by a per-creature step (`+0xdc8`) at `0x10016CAF8`; the patch multiplies that step by the
  attacker's attack-speed multiplier.
* The routines live in a new `.bld` section appended to the exe; the original instructions at the hooks are re-executed.
  There is no ASLR in this exe, so absolute addresses are stable.
* `build_patch/cave.py` – the injected machine code and the maths; `build_patch/miniasm.py` – a tiny assembler for the
  handful of instructions needed (no external assembler required); `build_patch/patcher.py` – PE editing, backup, verification.
* `tools/calc_test.py` runs the real machine code *inside a running game* on fake builds and compares it with a Python
  reference formula (`python -m tools.calc_test`). `tools/livepatch.py` installs the hooks into a running game without
  touching any file, handy for trying things (`install` / `remove` for damage, `install-speed` / `remove-speed` /
  `set-speed LEFT BOTTOM` for attack speed).

## License

MIT – see `LICENSE`.
