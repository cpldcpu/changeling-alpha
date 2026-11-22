/* Firmware test 8, one core: program protection. Stores to the code memories with PMCR and PMLIM. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define OWN_A (*(volatile uint8_t *)0x4600)     /* word 0x300 of code memory 0 */
#define OWN_B (*(volatile uint8_t *)0x4610)     /* word 0x308 */
#define OTH   (*(volatile uint8_t *)0x4E00)     /* word 0x300 of code memory 1 */
int main(void)
{
    OWN_A = 0x11; if (OWN_A != 0x00) EXIT(1);              /* no write enable after reset */
    PMCR = PMCR_PWE; if (PMCR != 0) EXIT(2);                /* protected register */
    PROT_WRITE(PMCR, PMCR_PWE);
    OWN_A = 0x22; if (OWN_A != 0x22) EXIT(3);
    OTH = 0x33; if (OTH != 0x00) EXIT(4);                   /* the other memory needs XWE */
    PROT_WRITE(PMCR, PMCR_PWE | PMCR_XWE);
    OTH = 0x44; if (OTH != 0x44) EXIT(5);
    PROT_WRITE(PMLIM, 0xC1);                             /* words below 0x304 are protected */
    OWN_A = 0x55; if (OWN_A != 0x22) EXIT(6);
    OTH = 0x56; if (OTH != 0x44) EXIT(7);
    OWN_B = 0x66; if (OWN_B != 0x66) EXIT(8);
    PROT_WRITE(PMCR, PMCR_PWE | PMCR_XWE | PMCR_LOCK);
    OWN_B = 0x77; if (OWN_B != 0x66) EXIT(9);
    PROT_WRITE(PMCR, PMCR_PWE | PMCR_XWE);               /* the lock cannot be cleared */
    if (!(PMCR & PMCR_LOCK)) EXIT(10);
    OWN_B = 0x78; if (OWN_B != 0x66) EXIT(11);
    EXIT(0);
}
