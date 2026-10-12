"""Reads config.ini and turns the friendly multipliers into the 'bonus' numbers the injected code uses."""
import configparser
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(ROOT, 'config.ini')

DEFAULTS = {
    'muscular_damage': 1.5,
    'muscular_lean_damage': 1.25,
    'muscular_lean_attack_speed': 1.25,
    'skinny_attack_speed': 1.5,
    'fat_health': 1.5,
}

class ConfigError(Exception):
    pass

def load(path=None):
    path = path or DEFAULT_CONFIG
    cp = configparser.ConfigParser(inline_comment_prefixes=(';',))
    if os.path.exists(path):
        cp.read(path, encoding='utf-8')
    elif path != DEFAULT_CONFIG:
        raise ConfigError('config file not found: %s' % path)
    mult = {}
    for key, default in DEFAULTS.items():
        raw = cp.get('build', key, fallback=str(default)).strip()
        try:
            v = float(raw)
        except ValueError:
            raise ConfigError('[build] %s = %r is not a number' % (key, raw))
        if not (0.05 <= v <= 100.0):
            raise ConfigError('[build] %s = %s is outside the allowed range 0.05 .. 100' % (key, v))
        mult[key] = v
    apply_to = cp.get('options', 'apply_to', fallback='player').strip().lower()
    if apply_to not in ('player', 'everyone'):
        raise ConfigError("[options] apply_to must be 'player' or 'everyone', not %r" % apply_to)
    game_exe = cp.get('options', 'game_exe', fallback='').strip().strip('"')
    return dict(mult=mult, everyone=(apply_to == 'everyone'), game_exe=game_exe)

def to_bonus(mult):
    """multipliers -> the additive 'bonus at full archetype' numbers used by the machine code"""
    return dict(
        dmg_top    = mult['muscular_damage'] - 1.0,
        dmg_bottom = mult['muscular_lean_damage'] - 1.0,
        spd_bottom = mult['muscular_lean_attack_speed'] - 1.0,
        spd_left   = mult['skinny_attack_speed'] - 1.0,
        hp_right   = mult['fat_health'] - 1.0,
    )

def from_bonus(bonus):
    return {
        'muscular_damage': 1.0 + bonus['dmg_top'],
        'muscular_lean_damage': 1.0 + bonus['dmg_bottom'],
        'muscular_lean_attack_speed': 1.0 + bonus['spd_bottom'],
        'skinny_attack_speed': 1.0 + bonus['spd_left'],
        'fat_health': 1.0 + bonus['hp_right'],
    }
