/* Self-checking C tests for rcore8. Exit code 0 = pass, otherwise the number of the failing test. */
#include "ctest_data.h"

static void fail(uint8_t n) { EXITR = n; for (;;) ; }
#define CHECK(n, got, want) do { if ((uint16_t)(got) != (uint16_t)(want)) fail(n); PUTC = '.'; } while (0)

#if PART == 1
static uint16_t t1(void) {
  uint16_t a16 = 0; uint32_t a32 = 0; uint8_t i;
  for (i = 0; i < NU8; i++) {
    uint8_t v = u8t[(uint8_t)(i + vz)];
    a16 = (uint16_t)(a16 + v * (i + 1));
    a32 = a32 * 31 + v + a16;
  }
  return a16 ^ (uint16_t)a32 ^ (uint16_t)(a32 >> 16);
}
static uint16_t t2(void) {
  uint16_t c = 0; uint8_t i, j;
  for (i = 0; i < NI16; i++) for (j = 0; j < NI16; j++) {
    int16_t x = i16t[(uint8_t)(i + vz)], y = i16t[(uint8_t)(j + vz)];
    c += (x < y) + 3 * (x >= y) + 5 * (x == y) + 7 * (x > y) + 11 * (x <= y);
  }
  return c;
}
static uint16_t t3(void) {
  uint16_t c = 0; uint8_t i, j;
  for (i = 0; i < NU32; i++) for (j = 0; j < NU32; j++) {
    uint32_t x = u32t[(uint8_t)(i + vz)], y = u32t[(uint8_t)(j + vz)], d = x - y;
    c += (x < y) + 3 * (x == y) + 5 * (x > y) + (uint8_t)d + (uint8_t)(d >> 24);
  }
  return c;
}
static uint16_t t4(void) {
  uint16_t c = 0; uint8_t i;
  for (i = 0; i < NU16; i++) {
    uint16_t v = u16t[(uint8_t)(i + vz)]; uint8_t n = i % 16;
    c += (uint16_t)(v << n) + (uint16_t)(v >> n) + (uint16_t)((int16_t)v >> n);
  }
  for (i = 0; i < NU32; i++) {
    uint32_t v = u32t[(uint8_t)(i + vz)]; uint8_t n = (uint8_t)(i * 3) % 32;
    c += (uint16_t)((uint32_t)(v << n) >> 16) + (uint16_t)(v >> n) + (uint16_t)((int32_t)v >> n);
  }
  return c;
}
static uint16_t t6(void) {
  uint16_t crc = 0xFFFF; uint8_t i, k;
  for (i = 0; i < NTEXT; i++) {
    crc ^= (uint16_t)(uint8_t)text[(uint8_t)(i + vz)] << 8;
    for (k = 0; k < 8; k++) crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}
static uint8_t buf[32];
static uint16_t t7(void) {
  uint16_t c = 0; uint8_t i; const char *s = text + vz; uint8_t *d = buf;
  for (i = 0; i < 32; i++) *d++ = (uint8_t)*s++;
  for (i = 0; i < 16; i++) { uint8_t t = buf[i]; buf[i] = buf[31 - i]; buf[31 - i] = t; }
  for (i = 0; i < 32; i++) c = c * 3 + buf[i] + i;
  return c;
}
static uint16_t f0(uint16_t x) { return x + 7; }
static uint16_t f1(uint16_t x) { return x ^ 0x5A5A; }
static uint16_t f2(uint16_t x) { return (uint16_t)((x << 3) | (x >> 13)); }
static uint16_t f3(uint16_t x) { return x - 999; }
static uint16_t (*const ftab[4])(uint16_t) = { f0, f1, f2, f3 };
static uint16_t sw(uint16_t x) {
  uint8_t k = x & 15;
  switch (k) {
    case 0: return 11; case 1: return 22; case 2: return 33; case 3: return 44; case 4: return 55;
    case 5: return 66; case 6: return 77; case 7: return 88; case 8: return 99; case 9: return 110;
    default: return k * 2 + 1;
  }
}
static uint16_t t8(void) {
  uint16_t c = 0x1234 + vz; uint8_t i;
  for (i = 0; i < 40; i++) { c = ftab[(c >> 4) & 3](c); c += sw(c); }
  return c;
}
static uint16_t fib(uint8_t n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
static uint16_t ack(uint16_t m, uint16_t n) {
  if (m == 0) return n + 1;
  if (n == 0) return ack(m - 1, 1);
  return ack(m - 1, ack(m, n - 1));
}
static uint16_t t9(void) { return fib(13 + vz) * 3 + ack(2 + vz, 3); }
static int16_t arr[NU16];
static uint16_t t10(void) {
  uint16_t c = 0; uint8_t i, j;
  for (i = 0; i < NU16; i++) arr[i] = (int16_t)u16t[(uint8_t)(i + vz)];
  for (i = 1; i < NU16; i++) {
    int16_t key = arr[i];
    for (j = i; j > 0 && arr[j - 1] > key; j--) arr[j] = arr[j - 1];
    arr[j] = key;
  }
  for (i = 0; i < NU16; i++) c = c * 5 + (uint16_t)arr[i] + i;
  return c;
}
static uint16_t t11(void) {
  uint16_t c = 0; uint8_t i;
  for (i = 0; i < NU8; i++) {
    int8_t sv = (int8_t)u8t[(uint8_t)(i + vz)];
    int16_t a = sv < 0 ? -sv : sv;
    c += a + (uint16_t)(sv >> 2) + (sv < -50) * 17 + (sv > 50) * 29;
  }
  return c;
}
int main(void) {
  CHECK(1, t1(), EXP1); CHECK(2, t2(), EXP2); CHECK(3, t3(), EXP3); CHECK(4, t4(), EXP4);
  CHECK(6, t6(), EXP6); CHECK(7, t7(), EXP7); CHECK(8, t8(), EXP8); CHECK(9, t9(), EXP9);
  CHECK(10, t10(), EXP10); CHECK(11, t11(), EXP11);
  EXITR = 0; for (;;) ;
}
#endif

#if PART == 2
static uint16_t t5(void) {
  uint16_t c = 0; uint8_t i;
  for (i = 0; i < NU16 - 1; i++) {
    uint16_t x = u16t[(uint8_t)(i + vz)], y = u16t[(uint8_t)(i + 1 + vz)];
    int16_t sx = (int16_t)x, sy = (int16_t)y;
    c += (uint16_t)(x * y);
    if (y) c += x / y + x % y;
    if (sy) c += (uint16_t)(sx / sy) + (uint16_t)(sx % sy);
  }
  for (i = 0; i < NU32 - 1; i++) {
    uint32_t x = u32t[(uint8_t)(i + vz)], y = u32t[(uint8_t)(i + 1 + vz)], p = x * y;
    c += (uint16_t)p + (uint16_t)(p >> 16);
    if (y) { uint32_t q = x / y, r = x % y; c += (uint16_t)q + (uint16_t)(q >> 16) + (uint16_t)r + (uint16_t)(r >> 16); }
  }
  return c;
}
int main(void) { CHECK(5, t5(), EXP5); EXITR = 0; for (;;) ; }
#endif

#if PART == 3 || PART == 4
volatile uint8_t isr_flag, order[4], nord, cnt1, cnt2, cnt3;
#define ISR(n) void __vector_##n(void) __attribute__((signal, used)); void __vector_##n(void)
ISR(1) { isr_flag = 1; cnt1++; if (nord < 4) order[nord++] = 1; }
ISR(2) { cnt2++; if (nord < 4) order[nord++] = 2; }
ISR(3) { uint16_t x = cnt3; x = x * 3 + 1; cnt3 = (uint8_t)x; if (nord < 4) order[nord++] = 3; }
#endif

#if PART == 3
static uint8_t delay_test(void) {
  uint8_t r;
  __asm__ __volatile__("cli\n ldi r20,1\n out 0x30,r20\n sei\n lds %0, isr_flag\n nop\n" : "=d"(r) : : "r20");
  return r;
}
int main(void) {
  /* single-bit I/O operations */
  PORT = 0x00; PORT |= 0x08; PORT |= 0x80; PORT &= (uint8_t)~0x08; PORT |= 0x01;
  CHECK(20, PORT, 0x81);
  { uint8_t n = 0; if (PORT & 0x80) n += 1; if (!(PORT & 0x08)) n += 2; if (PORT & 0x02) n += 4; if (!(PORT & 0x01)) n += 8; CHECK(21, n, 3); }
  /* one instruction executes after SEI before the interrupt is taken */
  isr_flag = 0;
  CHECK(22, delay_test(), 0);
  CHECK(23, isr_flag, 1);
  CHECK(24, cnt1, 1);
  /* priority: lowest vector first, each taken exactly once */
  __asm__ __volatile__("cli");
  nord = 0; IRQSET = 0x07;
  __asm__ __volatile__("sei");
  __asm__ __volatile__("nop\n nop\n nop\n nop");
  CHECK(25, nord, 3);
  CHECK(26, order[0] * 16 + order[1] * 4 + order[2], 16 + 8 + 3);
  CHECK(27, cnt1 + cnt2 * 16, 2 + 16);
  CHECK(28, cnt3, 1);
  /* interrupts stay disabled inside a handler and while I = 0 */
  __asm__ __volatile__("cli");
  IRQSET = 0x02;
  __asm__ __volatile__("nop\n nop");
  CHECK(29, cnt2, 1);
  CHECK(30, SREGR & 0x80, 0);
  __asm__ __volatile__("sei\n nop\n nop");
  CHECK(31, cnt2, 2);
  /* flags survive an interrupt in the middle of multi-byte arithmetic */
  { uint32_t a = 0x00FFFFFFUL + vz, b = 1; uint16_t i; uint32_t s = 0;
    for (i = 0; i < 300; i++) { IRQSET = 0x04; s += a + b; a += 0x01010101UL; }
    CHECK(32, (uint16_t)s ^ (uint16_t)(s >> 16), 0xE132 ^ 0x0DE1); }
  EXITR = 0; for (;;) ;
}
#endif

#if PART == 4
int main(void) {
  __asm__ __volatile__("sei");
  TIMER = 60;
  __asm__ __volatile__("sleep");
  CHECK(40, cnt1, 1);
  TIMER = 3;                                  /* request arrives before the sleep instruction */
  __asm__ __volatile__("nop\n nop\n nop\n nop\n nop\n nop");
  CHECK(41, cnt1, 2);
  __asm__ __volatile__("cli");
  TIMER = 5;
  __asm__ __volatile__("sei\n sleep");        /* SEI immediately followed by SLEEP must not lose the wake-up */
  CHECK(42, cnt1, 3);
  EXITR = 0; for (;;) ;
}
#endif
