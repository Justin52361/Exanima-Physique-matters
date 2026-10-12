"""Dev tool: install / remove / inspect the damage hook in a RUNNING Exanima.exe (no files are modified).
Run from the project root:  python -m tools.livepatch install [--everyone] | remove | status
Useful for trying values in-game without re-patching the exe.
"""
import ctypes, ctypes.wintypes as w, os, struct, subprocess, sys, tempfile
from build_patch import cave

k = ctypes.WinDLL('kernel32', use_last_error=True)
k.OpenProcess.restype = w.HANDLE
k.VirtualAllocEx.restype = ctypes.c_void_p
k.VirtualAllocEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, w.DWORD, w.DWORD]
k.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualProtectEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, w.DWORD, ctypes.POINTER(w.DWORD)]
k.OpenThread.restype = w.HANDLE

class TE(ctypes.Structure):
    _fields_ = [('sz', w.DWORD), ('cnt', w.DWORD), ('tid', w.DWORD), ('owner', w.DWORD), ('base', w.LONG), ('delta', w.LONG), ('flags', w.DWORD)]

def pid():
    for name in ('Exanima.exe', 'Exanima_bld.exe'):
        out = subprocess.check_output(['tasklist', '/fi', 'imagename eq ' + name, '/fo', 'csv', '/nh']).decode()
        if ',' in out: return int(out.split(',')[1].strip('"'))
    sys.exit('Exanima is not running')

def tids(p):
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    s = k.CreateToolhelp32Snapshot(4, 0); te = TE(); te.sz = ctypes.sizeof(te); r = []
    ok = k.Thread32First(s, ctypes.byref(te))
    while ok:
        if te.owner == p: r.append(te.tid)
        ok = k.Thread32Next(s, ctypes.byref(te))
    k.CloseHandle(s); return r

class Proc:
    def __init__(s):
        s.pid = pid(); s.h = k.OpenProcess(0x1F0FFF, False, s.pid)
    def read(s, a, n):
        b = ctypes.create_string_buffer(n); r = ctypes.c_size_t()
        return b.raw[:r.value] if k.ReadProcessMemory(s.h, ctypes.c_void_p(a), b, n, ctypes.byref(r)) else None
    def write(s, a, data):
        old = w.DWORD(); k.VirtualProtectEx(s.h, ctypes.c_void_p(a), len(data), 0x40, ctypes.byref(old))
        ok = k.WriteProcessMemory(s.h, ctypes.c_void_p(a), data, len(data), None)
        k.VirtualProtectEx(s.h, ctypes.c_void_p(a), len(data), old.value, ctypes.byref(old))
        assert ok, ctypes.get_last_error()
    def freeze(s):
        hs = []
        for t in tids(s.pid):
            th = k.OpenThread(0x1FFFFF, False, t); k.SuspendThread(th); hs.append(th)
        return hs
    def thaw(s, hs):
        for th in hs: k.ResumeThread(th); k.CloseHandle(th)

CAVE_BASE = 0x100700000
STATE = os.path.join(tempfile.gettempdir(), 'exanima_livepatch_state')

def install(everyone):
    p = Proc()
    cur = p.read(cave.HIT_SITE, 16)
    if cur == cave.HIT_ORIG_FAR: pass
    elif cur[0] == 0x48: sys.exit('already patched - run remove first')
    else: sys.exit('unexpected bytes at hit site: %s' % cur.hex())
    # the address space around the image is fully used, so the live test uses an absolute jump to a cave anywhere
    base = k.VirtualAllocEx(p.h, None, 0x1000, 0x3000, 0x40)
    assert base, 'allocation failed'
    a = cave.build(base, everyone, far=True, debug=True)
    code = a.link(); assert len(code) < 0x1000
    p.write(base, code)
    jmp = b'\x48\xB8' + struct.pack('<Q', a.labels['hit']) + b'\xFF\xE0' + b'\x90' * 4
    hs = p.freeze()
    try: p.write(cave.HIT_SITE, jmp)
    finally: p.thaw(hs)
    open(STATE, 'w').write(hex(base))
    print('installed; cave at', hex(base), 'everyone=%s' % everyone)

def remove():
    p = Proc(); hs = p.freeze()
    try: p.write(cave.HIT_SITE, cave.HIT_ORIG_FAR)
    finally: p.thaw(hs)
    print('hit site restored (cave memory left allocated, harmless)')

SPD_STATE = STATE + '_spd'

def install_speed(everyone):
    """Installs only the attack-speed hook (works on top of an exe that is already patched for damage)."""
    p = Proc()
    cur = p.read(cave.SPD_SITE, len(cave.SPD_CHECK))
    if cur[:2] == b'\x48\xB8': sys.exit('speed hook already installed - run remove-speed first')
    if cur != cave.SPD_CHECK: sys.exit('unexpected bytes at speed site: %s' % cur.hex())
    base = k.VirtualAllocEx(p.h, None, 0x1000, 0x3000, 0x40)
    assert base, 'allocation failed'
    a = cave.build(base, everyone, far=True, debug=True)
    code = a.link(); assert len(code) < 0x1000
    p.write(base, code)
    jmp = b'\x48\xB8' + struct.pack('<Q', a.labels['spd']) + b'\xFF\xE0'
    assert len(jmp) == len(cave.SPD_ORIG)
    hs = p.freeze()
    try: p.write(cave.SPD_SITE, jmp)
    finally: p.thaw(hs)
    open(SPD_STATE, 'w').write(hex(base))
    print('speed hook installed; cave at', hex(base), 'everyone=%s' % everyone)

def remove_speed():
    p = Proc(); hs = p.freeze()
    try: p.write(cave.SPD_SITE, cave.SPD_ORIG)
    finally: p.thaw(hs)
    print('speed site restored')

def set_speed_bonus(spd_left, spd_bottom):
    p = Proc(); base = int(open(SPD_STATE).read(), 16)
    labels = cave.build(base, far=True, debug=True).labels
    p.write(labels['K_PNEG_SPD'], struct.pack('<f', spd_left)); p.write(labels['K_QNEG_SPD'], struct.pack('<f', spd_bottom))
    print('speed bonuses now left=%g bottom=%g' % (spd_left, spd_bottom))

def status():
    p = Proc()
    if os.path.exists(STATE):
        base = int(open(STATE).read(), 16)
        m, cnt = struct.unpack('<fI', p.read(base + 0x58, 8))
        print('last damage multiplier applied: %.4f' % m)
    if os.path.exists(SPD_STATE):
        base = int(open(SPD_STATE).read(), 16)
        lab = cave.build(base, far=True, debug=True).labels['DBG_SPD']
        print('last attack-speed multiplier applied: %.4f' % struct.unpack('<f', p.read(lab, 4))[0])

if __name__ == '__main__':
    cmd = sys.argv[1]
    {'install': lambda: install('--everyone' in sys.argv), 'remove': remove, 'status': status,
     'install-speed': lambda: install_speed('--everyone' in sys.argv), 'remove-speed': remove_speed,
     'set-speed': lambda: set_speed_bonus(float(sys.argv[2]), float(sys.argv[3]))}[cmd]()
