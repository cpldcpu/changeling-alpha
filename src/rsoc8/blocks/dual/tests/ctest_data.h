#include <stdint.h>
#define IOREG(a) (*(volatile uint8_t *)(a))
#define IRQSET IOREG(0x30)
#define PUTC IOREG(0x31)
#define EXITR IOREG(0x32)
#define TIMER IOREG(0x33)
#define PORT IOREG(0x02)
#define SREGR IOREG(0x3F)
const uint8_t u8t[24] = {213, 5, 152, 188, 99, 138, 223, 82, 191, 63, 221, 133, 89, 95, 181, 46, 211, 85, 75, 105, 39, 97, 174, 164};
const int16_t i16t[16] = {0, 1, -1, 32767, -32768, 255, -256, 12345, -12345, 100, -100, 32766, -32767, 2, -2, 4660};
const uint32_t u32t[16] = {0x0UL, 0x1UL, 0xFFUL, 0x100UL, 0xFFFFUL, 0x10000UL, 0xFFFFFFUL, 0x1000000UL, 0xFFFFFFFFUL, 0x80000000UL, 0x7FFFFFFFUL, 0x12345678UL, 0x12345679UL, 0x12355678UL, 0x13345678UL, 0xDEADBEEFUL};
const uint16_t u16t[16] = {3082, 60140, 44501, 3521, 54457, 452, 874, 21470, 23445, 37561, 13041, 54333, 0, 1, 65535, 32768};
const char text[] = "The quick brown fox jumps over the lazy dog 0123456789";
volatile uint8_t vz;   /* always 0, defeats constant folding */
#define NU8 24
#define NI16 16
#define NU32 16
#define NU16 16
#define NTEXT 54
#define EXP1 0x8A89U
#define EXP2 0x0B80U
#define EXP3 0xDB8FU
#define EXP4 0x0A1BU
#define EXP5 0x0958U
#define EXP6 0xBE38U
#define EXP7 0xAF1CU
#define EXP8 0x162BU
#define EXP9 0x02C4U
#define EXP10 0xD199U
#define EXP11 0x0865U
