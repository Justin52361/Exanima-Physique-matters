"""Runs the injected `calc` routine inside a running Exanima on fake build records and compares it with a Python reference.
Run from the project root:  python -m tools.calc_test   (start the game first; nothing in the game is modified)"""
import ctypes, ctypes.wintypes as w, struct, sys
from build_patch import cave
from . import livepatch as L
k = L.k
k.CreateRemoteThread.restype = w.HANDLE
k.CreateRemoteThread.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]

def reference(x, y):
    p = (x - 0.5) * 2; q = (0.5 - y) * 2
    a = abs(p) + abs(q)
    if a > 1: p /= a; q /= a
    B = cave.BONUS
    dmg = 1 + B['dmg_top'] * max(q, 0) + B['dmg_bottom'] * max(-q, 0)
    spd = 1 + B['spd_bottom'] * max(-q, 0) + B['spd_left'] * max(-p, 0)
    hp  = 1 + B['hp_right'] * max(p, 0)
    return dmg, hp, spd

def main():
    pr = L.Proc()
    base = k.VirtualAllocEx(pr.h, None, 0x4000, 0x3000, 0x40)
    a = cave.build(base, False, True, True)
    # test stub appended after the cave: rcx -> [dyn ptr][out0][out1][out2]
    a.align(16); a.label('stub')
    a.mov_r64('rdx', 'rcx'); a.mov_r64('rax', ('rdx', 0)); a.call('calc')
    a.movss(('rdx', 8), 'xmm0'); a.movss(('rdx', 12), 'xmm1'); a.movss(('rdx', 16), 'xmm3'); a.ret()
    code = a.link(); pr.write(base, code)
    blk = base + 0x1000                      # scratch: fake dynamics @+0x100, fake SG @+0x400
    dyn, sg = blk + 0x100, blk + 0x400
    pts = [(.5,.5),(.5,0),(.5,1),(0,.5),(1,.5),(0,0),(1,0),(0,1),(1,1),(.221,.3),(.8,.2),(.3,.9),(.5,.25),(.75,.5)]
    bad = 0
    print('%-12s %-22s %-22s' % ('(x, y)', 'game dmg/hp/spd', 'reference'))
    for x, y in pts:
        pr.write(sg, struct.pack('<Q', cave.SG_VPTR).ljust(0x2c, b'\0') + struct.pack('<ff', x, y))
        pr.write(dyn + cave.SG_PTR_OFFSET, struct.pack('<Q', sg))
        pr.write(blk, struct.pack('<QIII', dyn, 0, 0, 0))
        th = k.CreateRemoteThread(pr.h, None, 0, a.labels['stub'], blk, 0, None)
        k.WaitForSingleObject(th, 5000)
        got = struct.unpack('<fff', pr.read(blk + 8, 12)); ref = reference(x, y)
        ok = all(abs(g - r) < 1e-4 for g, r in zip(got, ref)); bad += not ok
        print('%-12s %-22s %-22s %s' % ((x, y), ' '.join('%.3f' % g for g in got), ' '.join('%.3f' % r for r in ref), 'ok' if ok else 'MISMATCH'))
    # null SG pointer / wrong vptr must give 1,1,1
    pr.write(dyn + cave.SG_PTR_OFFSET, struct.pack('<Q', 0)); pr.write(blk, struct.pack('<QIII', dyn, 0, 0, 0))
    th = k.CreateRemoteThread(pr.h, None, 0, a.labels['stub'], blk, 0, None); k.WaitForSingleObject(th, 5000)
    print('null SG ->', struct.unpack('<fff', pr.read(blk + 8, 12)))
    pr.write(sg, struct.pack('<Q', 0x1234)); pr.write(dyn + cave.SG_PTR_OFFSET, struct.pack('<Q', sg))
    th = k.CreateRemoteThread(pr.h, None, 0, a.labels['stub'], blk, 0, None); k.WaitForSingleObject(th, 5000)
    print('bad vptr ->', struct.unpack('<fff', pr.read(blk + 8, 12)))
    print('ALL OK' if not bad else '%d MISMATCHES' % bad)
if __name__ == '__main__':
    main()
