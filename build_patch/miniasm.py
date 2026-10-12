"""Tiny x86-64 assembler: only the instruction forms the Exanima build patch needs."""
import struct

GPR = {'rax':0,'rcx':1,'rdx':2,'rbx':3,'rsp':4,'rbp':5,'rsi':6,'rdi':7}
XMM = {'xmm%d' % i: i for i in range(8)}

class Asm:
    def __init__(self, base):
        self.base = base
        self.b = bytearray()
        self.labels = {}
        self.fix = []        # (pos_of_rel32, label, end_of_instruction_pos)

    @property
    def here(self): return self.base + len(self.b)
    def align(self, n):
        while len(self.b) % n: self.b.append(0xCC)
    def label(self, name): self.labels[name] = self.here
    def raw(self, data): self.b += bytes(data)
    def f32(self, v): self.b += struct.pack('<f', v)
    def u32(self, v): self.b += struct.pack('<I', v)
    def u64(self, v): self.b += struct.pack('<Q', v)

    # ---- operand encoding ------------------------------------------------
    def _modrm(self, reg, rm, tail=0):
        """rm: ('x',n) register | ('rip',label) | (basegpr, disp). tail = bytes after disp (imm size)."""
        kind = rm[0]
        if kind == 'x' or kind == 'r':
            self.b.append(0xC0 | (reg << 3) | rm[1]); return
        if kind == 'rip':
            self.b.append(0x05 | (reg << 3))
            self.fix.append((len(self.b), rm[1], tail)); self.u32(0); return
        base, disp = GPR[kind], rm[1]
        sib = base == 4
        if disp == 0 and base != 5: mod = 0
        elif -128 <= disp <= 127: mod = 1
        else: mod = 2
        self.b.append((mod << 6) | (reg << 3) | (4 if sib else base))
        if sib: self.b.append(0x24)
        if mod == 1: self.b += struct.pack('<b', disp)
        elif mod == 2: self.b += struct.pack('<i', disp)

    def sse(self, prefix, opc, reg, rm):
        if prefix: self.b.append(prefix)
        self.b += bytes([0x0F, opc]); self._modrm(XMM[reg], self._rm(rm))
    def _rm(self, rm):
        if isinstance(rm, str) and rm in XMM: return ('x', XMM[rm])
        if isinstance(rm, str) and rm in GPR: return ('r', GPR[rm])
        if isinstance(rm, str): return ('rip', rm)
        return rm

    # ---- instructions --------------------------------------------------
    def movss(self, dst, src):
        if isinstance(dst, str) and dst in XMM: self.sse(0xF3, 0x10, dst, src)
        else: self.sse(0xF3, 0x11, src, dst)
    def addss(self, d, s): self.sse(0xF3, 0x58, d, s)
    def mulss(self, d, s): self.sse(0xF3, 0x59, d, s)
    def subss(self, d, s): self.sse(0xF3, 0x5C, d, s)
    def divss(self, d, s): self.sse(0xF3, 0x5E, d, s)
    def maxss(self, d, s): self.sse(0xF3, 0x5F, d, s)
    def minss(self, d, s): self.sse(0xF3, 0x5D, d, s)
    def comiss(self, d, s): self.sse(0, 0x2F, d, s)
    def andps(self, d, s): self.sse(0, 0x54, d, s)
    def xorps(self, d, s): self.sse(0, 0x57, d, s)
    def movaps(self, d, s): self.sse(0, 0x28, d, s)
    def movups(self, dst, src):
        if isinstance(dst, str) and dst in XMM: self.sse(0, 0x10, dst, src)
        else: self.sse(0, 0x11, src, dst)

    def mov_r64(self, dst, src):
        """mov r64, [mem] (src=('rip',label) or (base,disp)) / mov r64, r64"""
        if isinstance(src, str) and src in GPR:
            self.b += bytes([0x48, 0x89, 0xC0 | (GPR[src] << 3) | GPR[dst]]); return
        self.b.append(0x48); self.b.append(0x8B); self._modrm(GPR[dst], self._rm(src))
    def mov_m64(self, dst, src):
        """mov [mem], r64"""
        self.b.append(0x48); self.b.append(0x89); self._modrm(GPR[src], self._rm(dst))
    def cmp_r64_mem(self, reg, rm):
        self.b += bytes([0x48, 0x3B]); self._modrm(GPR[reg], self._rm(rm))
    def cmp_r64(self, a, b):
        self.b += bytes([0x48, 0x39, 0xC0 | (GPR[b] << 3) | GPR[a]])
    def test_r64(self, a, b):
        self.b += bytes([0x48, 0x85, 0xC0 | (GPR[b] << 3) | GPR[a]])
    def cmp_m8_imm8(self, rm, imm):
        self.b += bytes([0x80]); self._modrm(7, self._rm(rm), tail=1); self.b.append(imm)
    def sub_rsp(self, n): self.b += bytes([0x48, 0x83, 0xEC, n])
    def add_rsp(self, n): self.b += bytes([0x48, 0x83, 0xC4, n])
    def push(self, r): self.b.append(0x50 + GPR[r])
    def pop(self, r): self.b.append(0x58 + GPR[r])
    def mov_imm64(self, r, v): self.b += bytes([0x48, 0xB8 + GPR[r]]) + struct.pack('<Q', v)
    def jmp_reg(self, r): self.b += bytes([0xFF, 0xE0 + GPR[r]])
    def ret(self): self.b.append(0xC3)
    def nop(self, n=1): self.b += b'\x90' * n

    def jcc(self, cc, label):
        op = {'jne':0x85,'je':0x84,'jbe':0x86,'ja':0x87,'jae':0x83,'jb':0x82}[cc]
        self.b += bytes([0x0F, op]); self.fix.append((len(self.b), label, 0)); self.u32(0)   # rel32
    def call(self, label): self.b.append(0xE8); self.fix.append((len(self.b), label, 0)); self.u32(0)
    def jmp_abs(self, target):
        self.b.append(0xE9); self.fix.append((len(self.b), target, 0)); self.u32(0)

    def link(self):
        for pos, lab, tail in self.fix:
            tgt = self.labels[lab] if isinstance(lab, str) else lab
            if tail == -1:   # rel8
                rel = tgt - (self.base + pos + 1)
                assert -128 <= rel <= 127, (lab, rel)
                self.b[pos] = rel & 0xFF
            else:
                rel = tgt - (self.base + pos + 4 + tail)
                self.b[pos:pos+4] = struct.pack('<i', rel)
        return bytes(self.b)
