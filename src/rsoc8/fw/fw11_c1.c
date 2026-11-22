/* Firmware test 11, image of core 1: SPI master with pair 1, chip select through the port register */
#include "fw11.h"
#include "rpe_core1.h"
static uint8_t mt[15] = { 0xA0, 0x01, 0x13, 0x08, 0x04, 1, 8, 1, 0x00, 0xF0, 0xE0, 0, 0, 0x00, 0x00 };
static const uint8_t mr[15] = { 0xC0, 0x40, 0x00, 0x00, 0x02, 1, 1, 0, 0xF0, 0x00, 0xE0, 0, 0, 0x80, 0x00 };
int main(void)
{
    uint8_t m, i, v, e;
    PORT |= 0x08; DDR |= 0x08;                              /* chip select high */
    for (m = 0; m < 2; m++) {
        LC_REG(LC_T1, LC_CTRL) = 0; LC_REG(LC_R1, LC_CTRL) = 0;
        mt[3] = m ? 0x0A : 0x08;
        lc_setup(LC_T1, mt); lc_setup(LC_R1, mr);
        while (S_READY != m + 1) ;
        PORT &= ~0x08;
        delay_after(40); wait_for(EV_DLY);
        e = 1;
        for (i = 0; i < NB; i++) {
            LT1DATA = M_BYTE(i, m);
            wait_for(EV_LR1);
            v = LR1DATA;
            if (v != S_BYTE(i, m) && e == 1) e = 60 + 10 * m + i;
        }
        delay_after(40); wait_for(EV_DLY);
        PORT |= 0x08;
        M_DONE = e;
    }
    for (;;) wait_for(EV_SW3);
}
