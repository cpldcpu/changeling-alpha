/* Switch to the internal oscillator, trim it to 60 MHz with a reference signal on the reference pin, and
   then hold it with the relaxation oscillator as the reference.
   The reference pin has a period of 10 us; four periods are 2400 cycles of a 60 MHz clock.
   The relaxation oscillator is enabled from the start, because it changes the frequency of the ring. */
#include "rpe.h"

#define ON (CKC_OSCEN | CKC_SRC | CKC_RELAXEN)

int main(void)
{
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_RELAXEN);             /* start both oscillators */
    while (!(CLKSTAT & CKS_OSCRUN)) ;
    PROT_WRITE(CLKCTL, ON);                                  /* request the ring as the source */
    while (!(CLKSTAT & CKS_SRC)) ;                           /* the switch is done */

    TRTGT = 2400;                                            /* target count */
    TRINT = 3;                                               /* four reference periods per measurement */
    TRWIN = 8;                                               /* valid within 512 counts of the target */
    PROT_WRITE(CLKCTL, ON | CKC_REF_PIN | CKC_LOOP);
    for (;;) {                                               /* one trim step per valid measurement */
        IFRL = EV_TRIM;
        wait_for(EV_TRIM);
        if (TRCNT > 2388 && TRCNT < 2412) break;             /* within 0.5 % */
    }

    PROT_WRITE(CLKCTL, ON | CKC_REF_SLOW);                   /* loop off, reference: relaxation oscillator */
    TRWIN = 0;
    TRINT = 0x80 | 63;                                       /* one measurement over 64 of its periods */
    while (!(CLKSTAT & CKS_MDONE)) ;
    TRTGT = TRCNT;                                           /* this count is 60 MHz on this chip */
    TRWIN = 16;                                              /* valid within 1024 counts */
    PROT_WRITE(CLKCTL, ON | CKC_REF_SLOW | CKC_LOOP | CKC_TRIMD);    /* the loop holds the frequency */
    for (;;) wait_for(EV_SW0);
}
