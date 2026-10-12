"""Builds the machine code that gets injected into Exanima.exe for the build (physique) bonuses.

Box layout (character creation, x right / y down, both 0..1, centre = normal):
    top    centre  -> muscular        : +50% hit damage
    bottom centre  -> muscular lean   : +25% hit damage, +25% attack speed
    left   centre  -> skinny          : +50% attack speed
    right  centre  -> fat             : +50% max health (taken damage / 1.5)
Everything in between blends linearly; the corners are the 50/50 mix of the two neighbouring archetypes.
"""
import struct
from .miniasm import Asm

# --- default tunables (the real values come from config.ini via config.py) ----
BONUS = dict(
    dmg_top    = 0.50,   # muscular
    dmg_bottom = 0.25,   # muscular lean
    spd_bottom = 0.25,   # muscular lean
    spd_left   = 0.50,   # skinny
    hp_right   = 0.50,   # fat
)

# --- game addresses (Exanima.exe, no ASLR) ---------------------------------
PLAYER_DYN_GLOBAL = 0x1004F0830   # global holding the player's TMotileDynamics
SG_PTR_OFFSET     = 0x10A0        # TMotileDynamics -> TSGCharacter
SG_X, SG_Y        = 0x2C, 0x30    # TSGCharacter physique position
SG_VPTR           = 0x100311DE8   # TSGCharacter vptr (sanity check)
HIT_SITE          = 0x10015C65F   # inside the contact/hit routine, before damage is applied
HIT_RESUME        = 0x10015C667
HIT_ORIG          = bytes.fromhex('f30f108578ffffff')   # movss xmm0,[rbp-0x88]

# Attack animations (sequence index 5..12 at TMotileDynamics+0x9B8) advance their clock with
#   mov rax,[rbp-8] ; movss xmm0,[rax+0xA20] ; addss xmm0,[rax+0xDC8] ; movss [rax+0xA20],xmm0 ; jmp +0x3e
# inside the per-tick dynamics update. The hook scales the per-tick step (+0xDC8) by the attack-speed multiplier.
SPD_SITE   = 0x10016CAF8
SPD_ORIG   = bytes.fromhex('488b45f8' 'f30f1080200a0000')   # the 12 bytes overwritten by the jump
SPD_CHECK  = bytes.fromhex('488b45f8f30f1080200a0000f30f5880c80d0000f30f1180200a0000eb3e')   # whole block, verified before patching
SPD_RESUME = 0x10016CB54
DYN_ANIM_CLOCK, DYN_ANIM_STEP = 0xA20, 0xDC8

DATA_SIZE = 0x80
FAR_CONST = 0x10015C66F + 0x1BF829   # constant read by the 2nd displaced `mulss xmm0,[rip+0x1bf829]`
HIT_RESUME_FAR    = 0x10015C66F   # after the two displaced instructions (far mode)
HIT_ORIG_FAR      = bytes.fromhex('f30f108578ffffff' 'f30f590529f81b00')   # both displaced instructions

def build(base, everyone=False, far=False, debug=False, bonus=None):
    B = bonus or BONUS
    a = Asm(base)
    L = a.label
    # ---- data block (16-byte aligned) ----
    L('ABS');  a.u32(0x7FFFFFFF); a.u32(0x7FFFFFFF); a.u32(0x7FFFFFFF); a.u32(0x7FFFFFFF)
    L('SIGN'); a.u32(0x80000000); a.u32(0x80000000); a.u32(0x80000000); a.u32(0x80000000)
    L('ONE');  a.f32(1.0)
    L('HALF'); a.f32(0.5)
    a.u32(0); a.u32(0)
    L('K_QPOS_DMG'); a.f32(B['dmg_top'])
    L('K_QNEG_DMG'); a.f32(B['dmg_bottom'])
    L('K_QNEG_SPD'); a.f32(B['spd_bottom'])
    L('K_PNEG_SPD'); a.f32(B['spd_left'])
    L('K_PPOS_HP');  a.f32(B['hp_right'])
    L('FLAG_ALL');   a.u32(1 if everyone else 0)
    L('SGV');        a.u64(SG_VPTR)
    L('PLAYERP');    a.u64(PLAYER_DYN_GLOBAL)
    L('DBG_M');      a.f32(0.0)
    L('DBG_CNT');    a.u32(0)
    L('DBG_SPD');    a.f32(0.0)
    while len(a.b) < DATA_SIZE: a.u32(0)
    assert len(a.b) == DATA_SIZE

    # ---- calc: rax = TMotileDynamics*  ->  xmm0 = damage mult, xmm1 = health mult, xmm3 = attack speed mult
    L('calc')
    a.mov_r64('rax', ('rax', SG_PTR_OFFSET))
    a.test_r64('rax', 'rax')
    a.jcc('je', 'calc_default')
    a.mov_r64('rcx', ('rip', 'SGV'))
    a.cmp_r64_mem('rcx', ('rax', 0))
    a.jcc('jne', 'calc_default')
    a.movss('xmm3', ('rax', SG_X))
    a.movss('xmm4', ('rax', SG_Y))
    a.movss('xmm5', 'HALF')
    a.subss('xmm3', 'xmm5')            # x - .5
    a.subss('xmm5', 'xmm4')            # .5 - y
    a.addss('xmm3', 'xmm3')            # p  (-1 left .. +1 right)
    a.addss('xmm5', 'xmm5')            # q  (-1 bottom .. +1 top)
    a.movaps('xmm4', 'xmm3'); a.andps('xmm4', 'ABS')
    a.movaps('xmm0', 'xmm5'); a.andps('xmm0', 'ABS')
    a.addss('xmm4', 'xmm0')            # |p|+|q|
    a.movss('xmm0', 'ONE')
    a.comiss('xmm4', 'xmm0')
    a.jcc('jbe', 'calc_inside')
    a.divss('xmm3', 'xmm4'); a.divss('xmm5', 'xmm4')   # corners: project back onto the diamond
    L('calc_inside')
    a.xorps('xmm4', 'xmm4')
    a.movaps('xmm0', 'xmm5'); a.maxss('xmm0', 'xmm4')  # qpos
    a.xorps('xmm5', 'SIGN');  a.maxss('xmm5', 'xmm4')  # qneg
    a.movaps('xmm1', 'xmm3'); a.maxss('xmm1', 'xmm4')  # ppos
    a.xorps('xmm3', 'SIGN');  a.maxss('xmm3', 'xmm4')  # pneg
    a.movaps('xmm4', 'xmm5'); a.mulss('xmm4', 'K_QNEG_DMG')
    a.mulss('xmm5', 'K_QNEG_SPD')
    a.mulss('xmm0', 'K_QPOS_DMG')
    a.mulss('xmm1', 'K_PPOS_HP')
    a.mulss('xmm3', 'K_PNEG_SPD')
    a.addss('xmm0', 'xmm4')
    a.addss('xmm3', 'xmm5')
    a.movss('xmm2', 'ONE')
    a.addss('xmm0', 'xmm2'); a.addss('xmm1', 'xmm2'); a.addss('xmm3', 'xmm2')
    a.ret()
    L('calc_default')
    a.movss('xmm0', 'ONE'); a.movaps('xmm1', 'xmm0'); a.movaps('xmm3', 'xmm0')
    a.ret()
    a.align(16)

    # ---- hit hook (replaces `movss xmm0,[rbp-0x88]` at HIT_SITE) ----
    L('hit')
    a.sub_rsp(0x28)
    a.movss('xmm0', 'ONE'); a.movss(('rsp', 0x20), 'xmm0')
    a.mov_r64('rdx', ('rip', 'PLAYERP')); a.mov_r64('rdx', ('rdx', 0))
    a.mov_r64('rax', ('rbp', -8))                      # attacker
    a.cmp_m8_imm8('FLAG_ALL', 0); a.jcc('jne', 'hit_atk')
    a.cmp_r64('rax', 'rdx');       a.jcc('jne', 'hit_vic')
    L('hit_atk')
    a.call('calc')
    a.movss(('rsp', 0x20), 'xmm0')                     # M = damage multiplier of the attacker
    L('hit_vic')
    a.mov_r64('rdx', ('rip', 'PLAYERP')); a.mov_r64('rdx', ('rdx', 0))
    a.mov_r64('rax', ('rbp', -0x68))                   # victim
    a.cmp_m8_imm8('FLAG_ALL', 0); a.jcc('jne', 'hit_vic2')
    a.cmp_r64('rax', 'rdx');       a.jcc('jne', 'hit_done')
    L('hit_vic2')
    a.call('calc')
    a.movss('xmm0', ('rsp', 0x20)); a.divss('xmm0', 'xmm1'); a.movss(('rsp', 0x20), 'xmm0')   # M /= health mult of the victim
    L('hit_done')
    a.movss('xmm0', ('rsp', 0x20))
    for off in (-0x98, -0x70, -0x88):
        a.movss('xmm1', ('rbp', off)); a.mulss('xmm1', 'xmm0'); a.movss(('rbp', off), 'xmm1')
    if debug: a.movss('DBG_M', 'xmm0')
    a.add_rsp(0x28)
    a.movss('xmm0', ('rbp', -0x88))                    # displaced original instruction
    if far:
        # second displaced instruction: mulss xmm0,[rip+disp] -> rewritten with an absolute address
        a.mov_imm64('rax', FAR_CONST); a.mulss('xmm0', ('rax', 0))
        a.mov_imm64('rax', HIT_RESUME_FAR); a.jmp_reg('rax')
    else:
        a.jmp_abs(HIT_RESUME)
    a.align(16)

    # ---- attack-speed hook (replaces the 12 bytes at SPD_SITE; ends by doing the clock update itself) ----
    # rax/rcx/rdx/xmm0-5 and flags may be clobbered by `calc`; everything except rax/xmm0 (dead at SPD_RESUME,
    # where rax is reloaded) is saved and restored.
    L('spd')
    a.push('rcx'); a.push('rdx')
    a.sub_rsp(0x68)
    for i in range(1, 6): a.movups(('rsp', 0x10 * (i - 1)), 'xmm%d' % i)
    a.mov_r64('rax', ('rbp', -8))                       # this creature's TMotileDynamics (displaced instruction)
    a.mov_m64(('rsp', 0x60), 'rax')
    a.movss('xmm0', 'ONE'); a.movss(('rsp', 0x50), 'xmm0')
    a.mov_r64('rdx', ('rip', 'PLAYERP')); a.mov_r64('rdx', ('rdx', 0))
    a.cmp_m8_imm8('FLAG_ALL', 0); a.jcc('jne', 'spd_calc')
    a.cmp_r64('rax', 'rdx');       a.jcc('jne', 'spd_apply')
    L('spd_calc')
    a.call('calc')
    a.movss(('rsp', 0x50), 'xmm3')                      # attack-speed multiplier
    L('spd_apply')
    a.mov_r64('rax', ('rsp', 0x60))
    a.movss('xmm0', ('rax', DYN_ANIM_STEP)); a.mulss('xmm0', ('rsp', 0x50))
    a.addss('xmm0', ('rax', DYN_ANIM_CLOCK)); a.movss(('rax', DYN_ANIM_CLOCK), 'xmm0')
    if debug: a.movss('xmm0', ('rsp', 0x50)); a.movss('DBG_SPD', 'xmm0')
    for i in range(1, 6): a.movups('xmm%d' % i, ('rsp', 0x10 * (i - 1)))
    a.add_rsp(0x68)
    a.pop('rdx'); a.pop('rcx')
    if far:
        a.mov_imm64('rax', SPD_RESUME); a.jmp_reg('rax')
    else:
        a.jmp_abs(SPD_RESUME)
    return a
