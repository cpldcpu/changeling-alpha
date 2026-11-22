/* Firmware for the host link test: a counter in RAM that the host watches, a mailbox echo, and a
   variable through which the host ends the test. */
#include "rpe.h"
#define CNT   (*(volatile uint16_t *)0x0700)
#define HVAR  (*(volatile uint8_t  *)0x0702)
void __attribute__((noinline)) tick(void) { CNT++; }
int main(void)
{
    DDR = 0xFF;
    for (;;) {
        tick();
        PORT = (uint8_t)CNT;
        if (MBSTAT & 0x80) { uint8_t v = MBDATA; while (!(MBSTAT & 0x40)) ; MBDATA = v + 1; }
        if (HVAR == 0xA5) { _IO8(0x1F) = 0; for (;;) ; }
    }
}
