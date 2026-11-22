/* Firmware test 7, one core: clocking block. Core and peripheral divider, measurement of the clock
   against a reference on input pin 4 (testbench: +ref=<half period in ps>), window, status, clock
   output and debug signal. The testbench has the external clock only. Exit code 0 = pass. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)

static void __attribute__((noinline)) spin(void) { uint8_t i; for (i = 0; i < 100; i++) __asm__("nop"); }
static uint16_t timed(void) { uint16_t t = time_now(); spin(); return time_now() - t; }

int main(void)
{
    uint16_t a, b, c;

    if (CLKSTAT & (CKS_SRC | CKS_STRAP)) EXIT(1);           /* external clock, strap low */
    /* core divider: the same loop takes 3 times as many units of the time base */
    a = timed();
    CLKCDIV = 2;                                            /* no effect without the unlock */
    if (CLKCDIV != 0) EXIT(2);
    CCP_UNLOCK(); CLKCDIV = 2;
    b = timed();
    CCP_UNLOCK(); CLKCDIV = 0;
    if (b < 3 * a - 6 || b > 3 * a + 6) EXIT(3);
    /* peripheral divider: the time base counts every fourth cycle */
    CLKPDIV = 3;
    c = timed();
    CLKPDIV = 0;
    if (c < a / 4 - 2 || c > a / 4 + 2) EXIT(4);

    /* measurement: 4 periods of the reference; the testbench gives 250 clock cycles per period */
    CCP_UNLOCK(); CLKCTL = CKC_REF_PIN;
    TRTGT = 1000; TRWIN = 1;                                /* valid within 64 counts of 1000 */
    IFRL = EV_TRIM;
    TRINT = TRINT_MEAS | 3;
    if (!(TRINT & TRINT_MEAS)) EXIT(5);
    wait_for(EV_TRIM);
    a = TRCNT;
    if (a < 999 || a > 1001) EXIT(6);
    if ((CLKSTAT & (CKS_MDONE | CKS_MVALID)) != (CKS_MDONE | CKS_MVALID)) EXIT(7);
    /* a target outside the window: the measurement ends, no event */
    TRTGT = 2000; IFRL = EV_TRIM;
    TRINT = TRINT_MEAS | 3;
    while (TRINT & TRINT_MEAS) ;
    if ((CLKSTAT & (CKS_MDONE | CKS_MVALID)) != CKS_MDONE) EXIT(8);
    if (IFRL & EV_TRIM) EXIT(9);
    if (OSCTRIM != 0x80) EXIT(10);

    /* request for the oscillator, which the testbench does not have: the chip keeps running */
    CCP_UNLOCK(); CLKCTL = CKC_OSCEN | CKC_SRC;
    delay_after(3000); wait_for(EV_DLY);
    if (CLKSTAT & (CKS_SRC | CKS_OSCRUN)) EXIT(11);
    if (!(CLKSTAT & CKS_EXTP)) EXIT(12);
    CCP_UNLOCK(); CLKCTL = 0;

    /* clock output divided by 8 on output pin 1, core clock enable on the debug pin */
    CCP_UNLOCK(); CLKCDIV = 4;
    CLKOUT = CLKOUT_EN | 2; DBGSEL = DBGSEL_EN | 12;
    _IO8(0x1D) = 0;
    delay_after(4000); wait_for(EV_DLY);
    _IO8(0x1D) = 0;
    CLKOUT = 0; DBGSEL = 0;
    EXIT(0);
}
