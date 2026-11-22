/* Firmware test 9, one core: oscillator. Needs the oscillator model (tb/osc_model.v) and a reference
   of 100 kHz on input pin 4 (+ref=5000000). The firmware switches to the oscillator, lets the loop
   trim it to 15 MHz (600 cycles in 4 reference periods), and puts the clock divided by 2 on output
   pin 1, where the testbench measures the period. Works with the strap low and high. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
int main(void)
{
    uint8_t n = 0, good = 0; uint16_t c;
    if (!(CLKSTAT & CKS_STRAP)) {
        if (CLKSTAT & CKS_SRC) EXIT(1);
        PROT_WRITE(CLKCTL, CKC_OSCEN);
        while (!(CLKSTAT & CKS_OSCRUN)) ;
        PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC);
    }
    while (!(CLKSTAT & CKS_SRC)) ;
    TRTGT = 600; TRWIN = 3; TRINT = 3;                      /* valid within 192 counts of the target */
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC | CKC_REF_PIN | CKC_LOOP);
    while (good < 4) {                                      /* four measurements in a row within 0.5 % */
        IFRL = EV_TRIM; wait_for(EV_TRIM);
        c = TRCNT;
        good = (c >= 597 && c <= 603) ? good + 1 : 0;
        if (++n == 200) EXIT(2);
    }
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC | CKC_REF_PIN | CKC_TRIMD);
    if (!(CLKSTAT & CKS_TRIMD)) EXIT(3);
    CLKOUT = CLKOUT_EN | 0;
    delay_after(2000); wait_for(EV_DLY);
    _IO8(0x1D) = OSCTRIM;
    EXIT(0);
}
