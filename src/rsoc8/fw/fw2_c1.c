/* Firmware test 2, image of core 1 */
#include "fw2.h"
/* the start-up code sets the stack pointer for the ATtiny40; core 1 gets its own stack */
#include "rpe_core1.h"

static const uint8_t msg[NMSG] = { 'd', 'u', 'a', 'l', 0x00, 0xFF, 0x5A, 0xC3 };   /* in code memory 1 */

int main(void)
{
    uint8_t i;
    if (!(CORECTL & CORE_ID)) EXIT(21);
    LC_REG(LC_T1, LC_PIN) = LCP_OEM_ON;                     /* UART transmit on pin 6 */
    LC_REG(LC_T1, LC_OUT) = LCO_OUTSEL(6) | LCO_OUTEN;
    LC_REG(LC_T1, LC_B_REG) = 8;
    LC_REG(LC_T1, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T1, LC_SH)  = 0xE0 | 0x10 | 0x01;
    LC_REG(LC_T1, LC_RUN) = 0x04;
    LC_REG(LC_T1, LC_EVM) = LCS_TXE;
    LC_REG(LC_T1, LC_CTRL) = LCC_EN | LCC_TXEN;
    if (LC_REG(LC_T1, LC_B_REG) != 8) EXIT(22);
    if (LR0STAT != 0 || LC_REG(LC_R0, LC_B_REG) != 0) EXIT(23);     /* pair 0 belongs to core 0 */

    for (i = 0; i < NMSG; i++) {
        wait_for(EV_LT1);                                   /* buffer empty */
        LT1DATA = msg[i];
    }
    SHARED_FLAG = 0x5A;
    IFRH |= 0x10;                                           /* SW0 */

    for (i = 0; i < ROUNDS; i++) {
        lock_take(0);
        SHARED_CNT = SHARED_CNT + 1;
        lock_release(0);
    }
    IFRH |= 0x20;                                           /* SW1 */
    for (;;) wait_for(EV_SW3);
}
