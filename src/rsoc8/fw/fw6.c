/* Firmware test 6, one core: 16-bit timer (compare interrupt, capture of line cell edges), PWM,
   CRC unit (bytes from software, bits of a transmit cell, bits of a receive cell). Exit code 0 = pass. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)

static volatile uint8_t n_oca, n_cap;
static volatile uint16_t t_oca[6], cap[10];
ISR(VEC_OCA)  { if (n_oca < 6) t_oca[n_oca++] = time_now(); }
ISR(VEC_CAPT) { uint16_t v = timer_capture(); if (n_cap < 10) cap[n_cap++] = v; }

static const uint8_t msg[] = { 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x00, 0xFF, 0xA5 };

static uint32_t crc_sw(const uint8_t *p, uint8_t n)
{
    uint32_t v = 0xFFFFFFFF; uint8_t i;
    while (n--) { v ^= *p++; for (i = 0; i < 8; i++) v = (v & 1) ? (v >> 1) ^ 0xEDB88320 : v >> 1; }
    return v;
}
static void uart_cells(uint8_t bit, uint8_t rtim)
{
    LC_REG(LC_T0, LC_CTRL) = 0; LC_REG(LC_R0, LC_CTRL) = 0;
    LC_REG(LC_T0, LC_PIN) = LCP_OEM_ON;
    LC_REG(LC_T0, LC_OUT) = LCO_OUTSEL(5) | LCO_OUTEN;
    LC_REG(LC_T0, LC_B_REG) = bit;
    LC_REG(LC_T0, LC_ENC) = LUT_ENC_NRZ;
    LC_REG(LC_T0, LC_SH)  = 0xE0 | 0x10 | 0x01;
    LC_REG(LC_T0, LC_RUN) = 0x04;
    LC_REG(LC_T0, LC_CTRL) = LCC_EN | LCC_TXEN;
    LC_REG(LC_R0, LC_PIN) = LCP_INSEL(5);
    LC_REG(LC_R0, LC_TIM) = rtim;
    LC_REG(LC_R0, LC_A_REG) = bit + bit / 2;
    LC_REG(LC_R0, LC_B_REG) = bit;
    LC_REG(LC_R0, LC_DEC) = LUT_DEC_LEVEL;
    LC_REG(LC_R0, LC_SH)  = 0xE0 | 0x10;
    LC_REG(LC_R0, LC_EVM) = LCS_RXF;
    LC_REG(LC_R0, LC_CTRL) = LCC_EN | LCC_RXEN;
}

int main(void)
{
    uint8_t i; uint32_t ref;

    /* 1. compare A clears the count: one interrupt every 200 clock cycles */
    OCRA = 199;
    TCR = TCR_RUN | TCR_CTC;
    IFRL = EV_OCA; IERL = EV_OCA;
    sei();
    while (n_oca < 6) ;
    cli(); IERL = 0;
    for (i = 0; i < 5; i++) {                               /* the entry into the handler varies by a few cycles */
        uint16_t d = t_oca[i + 1] - t_oca[i];
        if (d < 197 || d > 203) EXIT(10 + i);
    }
    { uint16_t d = t_oca[5] - t_oca[0]; if (d < 997 || d > 1003) EXIT(15); }
    if (timer_count() >= 200) EXIT(16);

    /* 2. capture on every accepted edge of receive cell 0: the byte 0x55 has an edge at every bit */
    TCR = 0; timer_set(0);
    uart_cells(160, LCT_EDGE_BOTH | LCT_STOP_FRAME);
    TCAP = TCAP_SRC_EDGE | TCAP_PIN(0);
    TCR = TCR_RUN;
    IFRL = EV_CAPT; IERL = EV_CAPT;
    sei();
    LT0DATA = 0x55;
    while (n_cap < 10) ;
    cli(); IERL = 0; TCAP = TCAP_SRC_OFF;
    for (i = 0; i < 9; i++) if ((uint16_t)(cap[i + 1] - cap[i]) != 160) EXIT(20 + i);
    while (LT0STAT & LCS_BUSY) ;

    /* 3. PWM: period 100, duty 25, 50 and 100 cycles; the testbench measures the pins */
    PWMTOP = 99; PWM0 = 25; PWM1 = 50; PWM2 = 100;
    PWMC = PWMC_EN(0) | PWMC_EN(1) | PWMC_EN(2);
    _IO8(0x1E) = 0;
    delay_after(3000); wait_for(EV_DLY);
    _IO8(0x1E) = 0;
    PWMC = 0;

    /* 4. CRC-32 of bytes written by software */
    ref = crc_sw(msg, sizeof msg);
    crc_setup(CRC_RIGHT | CRC_SRC_SW, 31, 0xEDB88320, 0xFFFFFFFF);
    for (i = 0; i < sizeof msg; i++) CRCIN = msg[i];
    crc_wait();
    if (crc_value() != ref) EXIT(40);
    CRCCTL = 0;

    /* 5. CRC-32 of the data bits that transmit cell 0 sends, then of the bits that receive cell 0 receives */
    uart_cells(8, LCT_EDGE_FALL | LCT_ACC_WAIT | LCT_STOP_FRAME);
    crc_setup(CRC_RIGHT | CRC_SRC_T0, 31, 0xEDB88320, 0xFFFFFFFF);
    for (i = 0; i < sizeof msg; i++) {
        while (!(LT0STAT & LCS_TXE)) ;
        LT0DATA = msg[i];
        wait_for(EV_LR0);
        if (LR0DATA != msg[i]) EXIT(50);
    }
    if (crc_value() != ref) EXIT(51);
    CRCCTL = 0;
    crc_setup(CRC_RIGHT | CRC_SRC_R0, 31, 0xEDB88320, 0xFFFFFFFF);
    for (i = 0; i < sizeof msg; i++) {
        while (!(LT0STAT & LCS_TXE)) ;
        LT0DATA = msg[i];
        wait_for(EV_LR0);
        if (LR0DATA != msg[i]) EXIT(52);
    }
    if (crc_value() != ref) EXIT(53);
    EXIT(0);
}
