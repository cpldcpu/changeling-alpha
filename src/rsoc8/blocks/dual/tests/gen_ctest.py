#!/usr/bin/env python3
# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Generate self-checking C tests. Expected values are computed here in Python, so a wrong
flag or instruction in the core shows up as a mismatch against compiler-generated code."""
import random
rnd = random.Random(12345)
M16, M32 = 0xFFFF, 0xFFFFFFFF
def s16(x): x &= M16; return x - 0x10000 if x & 0x8000 else x
def s32(x): x &= M32; return x - (1 << 32) if x & 0x80000000 else x
def cdiv(a, b): q = abs(a) // abs(b); return -q if (a < 0) != (b < 0) else q
def cmod(a, b): return a - cdiv(a, b) * b

u8  = [rnd.randrange(256) for _ in range(24)]
i16 = [0, 1, -1, 32767, -32768, 255, -256, 12345, -12345, 100, -100, 32766, -32767, 2, -2, 4660]
u32 = [0, 1, 0xFF, 0x100, 0xFFFF, 0x10000, 0xFFFFFF, 0x1000000, 0xFFFFFFFF, 0x80000000,
       0x7FFFFFFF, 0x12345678, 0x12345679, 0x12355678, 0x13345678, 0xDEADBEEF]
u16 = [rnd.randrange(65536) for _ in range(12)] + [0, 1, 0xFFFF, 0x8000]
text = b"The quick brown fox jumps over the lazy dog 0123456789"

exp = {}
# 1: byte sums into 16 and 32 bit accumulators, with a multiply-by-constant mix
a16, a32 = 0, 0
for i, v in enumerate(u8):
    a16 = (a16 + v * (i + 1)) & M16
    a32 = (a32 * 31 + v + a16) & M32
exp[1] = (a16 ^ (a32 & M16) ^ (a32 >> 16)) & M16
# 2: signed 16-bit comparisons
c = 0
for x in i16:
    for y in i16:
        c += (x < y) + 3 * (x >= y) + 5 * (x == y) + 7 * (x > y) + 11 * (x <= y)
exp[2] = c & M16
# 3: unsigned 32-bit comparisons and subtraction
c = 0
for x in u32:
    for y in u32:
        c = (c + (x < y) + 3 * (x == y) + 5 * (x > y) + ((x - y) & M32 & 0xFF) + (((x - y) & M32) >> 24)) & M16
exp[3] = c
# 4: shifts
c = 0
for i, v in enumerate(u16):
    n = i % 16
    c = (c + ((v << n) & M16) + (v >> n) + ((s16(v) >> n) & M16)) & M16
for i, v in enumerate(u32):
    n = (i * 3) % 32
    c = (c + (((v << n) & M32) >> 16) + ((v >> n) & M16) + ((s32(v) >> n) & M16)) & M16
exp[4] = c
# 5: multiply, divide, modulo
c = 0
for i in range(len(u16) - 1):
    x, y = u16[i], u16[i + 1]
    c = (c + ((x * y) & M16)) & M16
    if y:
        c = (c + x // y + x % y) & M16
    sx, sy = s16(x), s16(y)
    if sy:
        c = (c + (cdiv(sx, sy) & M16) + (cmod(sx, sy) & M16)) & M16
for i in range(len(u32) - 1):
    x, y = u32[i], u32[i + 1]
    p = (x * y) & M32
    c = (c + (p & M16) + (p >> 16)) & M16
    if y:
        q, r = x // y, x % y
        c = (c + (q & M16) + (q >> 16) + (r & M16) + (r >> 16)) & M16
exp[5] = c
# 6: CRC-16/CCITT over a constant string in program memory
crc = 0xFFFF
for ch in text:
    crc ^= ch << 8
    for _ in range(8):
        crc = ((crc << 1) ^ 0x1021) & M16 if crc & 0x8000 else (crc << 1) & M16
exp[6] = crc
# 7: copy constant table to RAM, reverse it, checksum
buf = list(text[:32])
buf.reverse()
c = 0
for i, v in enumerate(buf):
    c = (c * 3 + v + i) & M16
exp[7] = c
# 8: function pointers and switch
def f0(x): return (x + 7) & M16
def f1(x): return (x ^ 0x5A5A) & M16
def f2(x): return ((x << 3) | (x >> 13)) & M16
def f3(x): return (x - 999) & M16
def sw(x):
    k = x & 15
    return {0: 11, 1: 22, 2: 33, 3: 44, 4: 55, 5: 66, 6: 77, 7: 88, 8: 99, 9: 110}.get(k, k * 2 + 1)
c = 0x1234
for i in range(40):
    c = [f0, f1, f2, f3][(c >> 4) & 3](c)
    c = (c + sw(c)) & M16
exp[8] = c
# 9: recursion
def fib(n): return n if n < 2 else fib(n - 1) + fib(n - 2)
def ack(m, n):
    if m == 0: return n + 1
    if n == 0: return ack(m - 1, 1)
    return ack(m - 1, ack(m, n - 1))
exp[9] = (fib(13) * 3 + ack(2, 3)) & M16
# 10: insertion sort
arr = [s16(v) for v in u16]
arr.sort()
c = 0
for i, v in enumerate(arr):
    c = (c * 5 + (v & M16) + i) & M16
exp[10] = c
# 11: signed 8-bit arithmetic
c = 0
for v in u8:
    sv = v - 256 if v & 0x80 else v
    a = -sv if sv < 0 else sv           # abs, int promoted
    c = (c + a + (sv >> 2 & M16) + (1 if sv < -50 else 0) * 17 + (1 if sv > 50 else 0) * 29) & M16
exp[11] = c

def arr_c(name, typ, vals, const=True):
    return "%s%s %s[%d] = {%s};" % ("const " if const else "", typ, name, len(vals), ", ".join(str(v) for v in vals))

out = []
out.append('#include <stdint.h>')
out.append('#define IOREG(a) (*(volatile uint8_t *)(a))')
out.append('#define IRQSET IOREG(0x30)\n#define PUTC IOREG(0x31)\n#define EXITR IOREG(0x32)\n#define TIMER IOREG(0x33)\n#define PORT IOREG(0x02)\n#define SREGR IOREG(0x3F)')
out.append(arr_c("u8t", "uint8_t", u8))
out.append(arr_c("i16t", "int16_t", i16))
out.append(arr_c("u32t", "uint32_t", ["0x%XUL" % v for v in u32]))
out.append(arr_c("u16t", "uint16_t", u16))
out.append('const char text[] = "%s";' % text.decode())
out.append('volatile uint8_t vz;   /* always 0, defeats constant folding */')
out.append('#define NU8 %d\n#define NI16 %d\n#define NU32 %d\n#define NU16 %d\n#define NTEXT %d' % (len(u8), len(i16), len(u32), len(u16), len(text)))
for k in sorted(exp):
    out.append('#define EXP%d 0x%04XU' % (k, exp[k]))
open("tests/ctest_data.h", "w").write("\n".join(out) + "\n")
print(exp)
