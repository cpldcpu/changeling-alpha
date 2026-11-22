/* Switch to the internal oscillator and trim it with a reference signal on the reference pin.
   The reference has a period of 10 us; four periods are 600 cycles of a 15 MHz clock. */
#include "rpe.h"

int main(void)
{
    PROT_WRITE(CLKCTL, CKC_OSCEN);                           /* start the oscillator */
    while (!(CLKSTAT & CKS_OSCRUN)) ;
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC);                 /* request it as the source */
    while (!(CLKSTAT & CKS_SRC)) ;                           /* the switch is done */

    TRTGT = 600;                                             /* target count */
    TRINT = 3;                                               /* four reference periods per measurement */
    TRWIN = 3;                                               /* valid within 192 counts of the target */
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC | CKC_REF_PIN | CKC_LOOP);
    for (;;) {                                               /* one trim step per valid measurement */
        IFRL = EV_TRIM;
        wait_for(EV_TRIM);
        if (TRCNT > 597 && TRCNT < 603) break;               /* within 0.5 % */
    }
    PROT_WRITE(CLKCTL, CKC_OSCEN | CKC_SRC | CKC_REF_PIN | CKC_TRIMD);    /* loop off, mark as trimmed */
    for (;;) wait_for(EV_SW0);
}
