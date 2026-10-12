"""Patches Exanima.exe so the Physique box matters. See README.md."""
import hashlib
import os
import shutil
import struct
import subprocess

import pefile

from . import cave, config, gamepath

KNOWN_SHA256 = 'af9033c7857565ddf2e842a486b0a158b32375a8f95e18b69f4e171b919b6f70'   # the Exanima.exe this was written against
SECTION_NAME = b'.bld\0\0\0\0'
FILE_ALIGN, SECT_ALIGN = 0x200, 0x1000

class PatchError(Exception):
    pass

def _up(v, a):
    return (v + a - 1) // a * a

def _pe(data):
    return pefile.PE(data=data, fast_load=True)

def is_patched(data):
    return any(s.Name.rstrip(b'\0') == b'.bld' for s in _pe(data).sections)

def game_running():
    try:
        out = subprocess.check_output(['tasklist', '/fi', 'imagename eq Exanima.exe', '/fo', 'csv', '/nh'],
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).decode(errors='ignore')
        return 'exanima.exe' in out.lower()
    except Exception:
        return False

def build_patched(data, bonus, everyone):
    """Returns the patched exe image (bytes). `data` must be an UNPATCHED Exanima.exe."""
    pe = _pe(data)
    if any(s.Name.rstrip(b'\0') == b'.bld' for s in pe.sections):
        raise PatchError('internal error: input exe is already patched')
    image_base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
    site_off = text.PointerToRawData + (cave.HIT_SITE - image_base - text.VirtualAddress)
    spd_off = text.PointerToRawData + (cave.SPD_SITE - image_base - text.VirtualAddress)
    if data[site_off:site_off + 8] != cave.HIT_ORIG or data[spd_off:spd_off + len(cave.SPD_CHECK)] != cave.SPD_CHECK:
        raise PatchError('This Exanima.exe is not the version the patch was written for (the code it hooks looks different).\n'
                         'Nothing was changed. Please open an issue and mention your game version.')
    last = pe.sections[-1]
    new_rva = _up(last.VirtualAddress + max(last.Misc_VirtualSize, last.SizeOfRawData), SECT_ALIGN)
    new_raw = _up(last.PointerToRawData + last.SizeOfRawData, FILE_ALIGN)
    if new_raw != len(data):
        raise PatchError('Unexpected extra data at the end of Exanima.exe - not patching.')
    asm = cave.build(image_base + new_rva, everyone=everyone, far=False, debug=False, bonus=bonus)
    code = asm.link()
    raw_size = _up(len(code), FILE_ALIGN)
    table_end = pe.sections[0].get_file_offset() + 40 * len(pe.sections)
    if table_end + 40 > pe.OPTIONAL_HEADER.SizeOfHeaders or any(data[table_end:table_end + 40]):
        raise PatchError('No room for another section header - not patching.')
    out = bytearray(data)
    out[table_end:table_end + 40] = struct.pack('<8sIIIIIIHHI', SECTION_NAME, len(code), new_rva, raw_size, new_raw,
                                                0, 0, 0, 0, 0x60000060)       # code | initialised data | exec | read
    out += code.ljust(raw_size, b'\0')
    nt = pe.DOS_HEADER.e_lfanew
    struct.pack_into('<H', out, nt + 6, len(pe.sections) + 1)                      # NumberOfSections
    struct.pack_into('<I', out, nt + 24 + 56, new_rva + _up(len(code), SECT_ALIGN))  # SizeOfImage
    jmp = b'\xE9' + struct.pack('<i', asm.labels['hit'] - (cave.HIT_SITE + 5)) + b'\x90\x90\x90'
    out[site_off:site_off + 8] = jmp                                                # hook the hit routine
    jmp = b'\xE9' + struct.pack('<i', asm.labels['spd'] - (cave.SPD_SITE + 5))
    out[spd_off:spd_off + len(cave.SPD_ORIG)] = jmp.ljust(len(cave.SPD_ORIG), b'\x90')  # hook the attack-animation clock
    struct.pack_into('<I', out, nt + 24 + 64, pefile.PE(data=bytes(out)).generate_checksum())
    return bytes(out)

def read_settings(data):
    """Reads the active multipliers back out of a patched exe."""
    pe = _pe(data)
    sec = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.bld')
    base = pe.OPTIONAL_HEADER.ImageBase + sec.VirtualAddress
    labels = cave.build(base, bonus=cave.BONUS).labels
    raw = data[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]
    f = lambda name: struct.unpack_from('<f', raw, labels[name] - base)[0]
    bonus = dict(dmg_top=f('K_QPOS_DMG'), dmg_bottom=f('K_QNEG_DMG'), spd_bottom=f('K_QNEG_SPD'),
                 spd_left=f('K_PNEG_SPD'), hp_right=f('K_PPOS_HP'))
    everyone = struct.unpack_from('<I', raw, labels['FLAG_ALL'] - base)[0] != 0
    return config.from_bonus(bonus), everyone

# --------------------------------------------------------------------------- commands
def resolve_exe(cfg, cli_exe=None):
    exe = cli_exe or cfg['game_exe'] or gamepath.find_exe()
    if not exe or not os.path.exists(exe):
        raise PatchError('Could not find Exanima.exe automatically.\n'
                         'Set  game_exe = C:\\full\\path\\to\\Exanima.exe  in config.ini (or pass --exe).')
    return os.path.abspath(exe)

def _check_writable(exe):
    if game_running():
        raise PatchError('Exanima is running - close the game first.')
    try:
        open(exe, 'ab').close()
    except PermissionError:
        raise PatchError('Cannot write to %s\nClose the game, and if it is in "Program Files" try running this as administrator.' % exe)

def _fmt(mult, everyone):
    names = [('muscular_damage', 'muscular (top)          damage'),
             ('muscular_lean_damage', 'muscular lean (bottom)  damage'),
             ('muscular_lean_attack_speed', 'muscular lean (bottom)  attack speed'),
             ('skinny_attack_speed', 'skinny (left)           attack speed'),
             ('fat_health', 'fat (right)             health')]
    lines = ['  %-38s x%.3g' % (label, mult[key]) for key, label in names]
    lines.append('  applies to: %s' % ('every character' if everyone else 'the player only'))
    return '\n'.join(lines)

def apply(cfg, cli_exe=None):
    exe = resolve_exe(cfg, cli_exe)
    bak = exe + '.bak'
    _check_writable(exe)
    current = open(exe, 'rb').read()
    if is_patched(current):
        # settings changed: start again from the untouched original
        if not os.path.exists(bak):
            raise PatchError('Exanima.exe is patched but %s is missing, so it cannot be re-patched.\n'
                             'Use Steam "Verify integrity of game files" to restore it, then apply again.' % bak)
        original = open(bak, 'rb').read()
        if is_patched(original):
            raise PatchError('%s is itself a patched file - cannot continue.\nUse Steam "Verify integrity of game files", then apply again.' % bak)
    else:
        original = current
        shutil.copy2(exe, bak)          # the exe on disk is the pristine one (also refreshes the backup after a game update)
    if hashlib.sha256(original).hexdigest() != KNOWN_SHA256:
        print('Note: this Exanima.exe differs from the version the patch was developed on; checking the hook site instead...')
    patched = build_patched(original, config.to_bonus(cfg['mult']), cfg['everyone'])
    with open(exe, 'wb') as fh:
        fh.write(patched)
    written = open(exe, 'rb').read()
    if written != patched:
        raise PatchError('Verification of the written file failed.')
    print('Patched', exe)
    print('Backup :', bak)
    print(_fmt(cfg['mult'], cfg['everyone']))

def restore(cfg, cli_exe=None):
    exe = resolve_exe(cfg, cli_exe)
    bak = exe + '.bak'
    _check_writable(exe)
    if not os.path.exists(bak):
        if not is_patched(open(exe, 'rb').read()):
            print('Exanima.exe is already original - nothing to do.')
            return
        raise PatchError('No backup at %s. Use Steam "Verify integrity of game files" to restore the original.' % bak)
    if is_patched(open(bak, 'rb').read()):
        raise PatchError('%s is a patched file, not a clean backup. Use Steam "Verify integrity of game files".' % bak)
    shutil.copy2(bak, exe)
    print('Restored the original Exanima.exe')

def status(cfg, cli_exe=None):
    exe = resolve_exe(cfg, cli_exe)
    data = open(exe, 'rb').read()
    print('Exanima.exe:', exe)
    if is_patched(data):
        mult, everyone = read_settings(data)
        print('State      : PATCHED')
        print(_fmt(mult, everyone))
    else:
        print('State      : original (not patched)')
    print('Backup     :', 'present' if os.path.exists(exe + '.bak') else 'none')

def build_copy(cfg, out_path, cli_exe=None):
    """Writes a patched copy somewhere else; touches nothing in the game folder."""
    exe = resolve_exe(cfg, cli_exe)
    data = open(exe, 'rb').read()
    if is_patched(data):
        bak = exe + '.bak'
        if not os.path.exists(bak):
            raise PatchError('Exanima.exe is already patched and there is no backup to build from.')
        data = open(bak, 'rb').read()
    with open(out_path, 'wb') as fh:
        fh.write(build_patched(data, config.to_bonus(cfg['mult']), cfg['everyone']))
    print('wrote', out_path)
