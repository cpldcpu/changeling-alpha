/* Register definitions for the rcore8 protocol emulator.
 * Matches the register map section (label sec:map) of the architecture specification, draft 0.36.
 * Pin positions in PINB and PORTC are provisional. */
#ifndef RPE_H
#define RPE_H
#include <stdint.h>

#define _IO8(a)   (*(volatile uint8_t  *)(a))
#define _IO16(a)  (*(volatile uint16_t *)(a))   /* low byte at the lower address */
#define _CF8(o)   (*(volatile uint8_t  *)(0x3F00 + (o)))
#define _CF16(o)  (*(volatile uint16_t *)(0x3F00 + (o)))

/* ---------------- fast I/O tier, 0x00 to 0x3F ---------------- */
#define PINR     _IO8(0x00)   /* bidirectional port: pin levels (R) */
#define DDR      _IO8(0x01)   /* bidirectional port: direction, 1 = output */
#define PORT     _IO8(0x02)   /* bidirectional port: output value */
#define PINB     _IO8(0x03)   /* input pins (R) */
#define PORTC    _IO8(0x04)   /* output pins */
#define LOCK     _IO8(0x05)   /* four locks between the cores (view per core) */
#define IFRL     _IO8(0x06)   /* event flags, low byte */
#define IFRH     _IO8(0x07)   /* event flags, high byte */
#define IFR      _IO16(0x06)
#define LR0STAT  _IO8(0x08)   /* receive cell 0: status (owner core only) */
#define LR0DATA  _IO8(0x09)   /* receive cell 0: oldest received frame; reading removes it */
#define LT0STAT  _IO8(0x0A)   /* transmit cell 0: status */
#define LT0DATA  _IO8(0x0B)   /* transmit cell 0: frame to transmit */
#define LR1STAT  _IO8(0x10)   /* receive cell 1 */
#define LR1DATA  _IO8(0x11)
#define LT1STAT  _IO8(0x12)   /* transmit cell 1 */
#define LT1DATA  _IO8(0x13)
#define MBSTAT   _IO8(0x0C)   /* mailbox status (R) */
#define MBDATA   _IO8(0x0D)   /* mailbox data */
#define CORECTL  _IO8(0x0E)   /* core enable, core state, number of the reading core */
#define CLKSTAT  _IO8(0x0F)   /* clock status (R) */
#define WAITL    _IO8(0x20)   /* wait mask low; writing starts the wait (per core) */
#define WAITH    _IO8(0x21)   /* wait mask high (per core) */
#define IERL     _IO8(0x22)   /* interrupt enable low (per core) */
#define IERH     _IO8(0x23)
#define IER      _IO16(0x22)
#define DLYL     _IO8(0x24)   /* read: time base low (latches high). write: wake-up time low, sets it, clears DLY (per core) */
#define DLYH     _IO8(0x25)   /* read: time base high. write: wake-up time high (write first) */
#define TCNTL    _IO8(0x26)   /* 16-bit timer count */
#define TCNTH    _IO8(0x27)
#define TCNT     _IO16(0x26)
#define ICRL     _IO8(0x28)   /* capture value (R) */
#define ICRH     _IO8(0x29)
#define ICR      _IO16(0x28)
#define CRCIN    _IO8(0x2A)   /* feeds one byte to the CRC unit (W) */
#define CCP      _IO8(0x3C)   /* signature for protected writes (W, per core) */
#define SPL      _IO8(0x3D)   /* stack pointer (per core) */
#define SPH      _IO8(0x3E)
#define SREG     _IO8(0x3F)   /* status flags (per core) */

/* event flags: 16-bit masks for IFR, IER and the wait mask; vector = flag number + 1 */
#define EV_PC    0x0001   /* pin change */
#define EV_CAPT  0x0002   /* timer capture */
#define EV_OCA   0x0004   /* timer compare A */
#define EV_OCB   0x0008   /* timer compare B */
#define EV_OVF   0x0010   /* timer overflow */
#define EV_MBX   0x0020   /* mailbox holds a byte from the host */
#define EV_TRIM  0x0040   /* trim measurement inside the window */
#define EV_DLY   0x0080   /* time base reached the core's wake-up time (per core) */
#define EV_LR0   0x0100   /* receive cell 0 (seen by the owner core of pair 0 only) */
#define EV_LT0   0x0200   /* transmit cell 0 */
#define EV_LR1   0x0400   /* receive cell 1 (owner core of pair 1) */
#define EV_LT1   0x0800   /* transmit cell 1 */
#define EV_SW0   0x1000   /* software flags, shared by both cores */
#define EV_SW1   0x2000
#define EV_SW2   0x4000
#define EV_SW3   0x8000
/* bit numbers in IFRH for SBI, CBI and skip instructions */
#define IFRH_LR0 0
#define IFRH_LT0 1
#define IFRH_LR1 2
#define IFRH_LT1 3
#define IFRL_DLY 7
#define IFRH_SW0 4
#define IFRH_SW1 5
#define IFRH_SW2 6
#define IFRH_SW3 7

/* LRnSTAT (RXF, IDLE, MATCH, OVR, STUFF, BOTHL) and LTnSTAT (TXE, BUSY) */
#define LCS_RXF    0x80   /* a received frame is waiting */
#define LCS_TXE    0x40   /* transmit buffer empty */
#define LCS_BUSY   0x20   /* a frame is being transmitted */
#define LCS_FERR   0x40   /* R: wrong parity (write 1 to clear) */
#define LCS_EOP    0x20   /* R: both pins have gone low, e.g. USB end of packet (write 1 to clear) */
#define LCS_IDLE   0x10   /* line idle (write 1 to clear) */
#define LCS_MATCH  0x08   /* match pattern found (write 1 to clear) */
#define LCS_OVR    0x04   /* a frame was lost (write 1 to clear) */
#define LCS_STUFF  0x02   /* stuffing error (write 1 to clear) */
#define LCS_BOTHL  0x01   /* both pins low */
#define LCS_RXF_BIT 7
#define LCS_TXE_BIT 6

/* MBSTAT */
#define MBS_RXF    0x80
#define MBS_TXE    0x40

/* CORECTL */
#define CORE_EN(n)   (0x01u << (n))   /* n = 0, 1 */
#define CORE_WAIT(n) (0x10u << (n))   /* read only */
#define CORE_ID      0x80             /* read only: number of the reading core */

/* LOCK: bit n = lock n held by the reading core; bit n+4 = held by the other core (read only) */
#define LOCK_OTHER(n) (0x10u << (n))

/* CLKSTAT */
#define CKS_SRC    0x01   /* active source: 0 external, 1 internal */
#define CKS_OSCRUN 0x02
#define CKS_EXTP   0x04
#define CKS_TRIMD  0x08
#define CKS_MDONE  0x10
#define CKS_MVALID 0x20
#define CKS_STRAP  0x80

/* PINB and PORTC, provisional */
#define PINB_HSCK  0x01
#define PINB_HCS   0x02
#define PINB_HMOSI 0x04
#define PINB_STRAP 0x08
#define PINB_REF   0x10
#define PORTC_CKO  0x02
#define PORTC_DBG  0x04

/* ---------------- configuration page, 0x3F00 to 0x3FFF ---------------- */
/* blocks of the four cells in the configuration page. Both cell types use the same offsets; a
   register that a type does not have reads as zero. R: receive cell, T: transmit cell */
#define LC_R0      0x00
#define LC_T0      0x10
#define LC_R1      0x60
#define LC_T1      0x70
#define LC_CTRL    0x0
#define LC_PIN     0x1
#define LC_OUT     0x2
#define LC_CLK     0x3
#define LC_TIM     0x4
#define LC_A_REG   0x5
#define LC_B_REG   0x6
#define LC_C_REG   0x7
#define LC_DEC     0x8
#define LC_ENC     0x9
#define LC_SH      0xA
#define LC_MATCH   0xB
#define LC_RUN     0xC
#define LC_EVM     0xD
#define LC_CS      0xE
#define LC_EC      0x7                     /* receive cell: edge count, 4 bits (LCEC) */
#define LC_X       0xF                     /* LCX: additional frame bit, bus conditions; not part of the lc_setup table */
#define LCX_PAR_ODD  0x01                  /* additional bit: odd parity */
#define LCX_PAR_EVEN 0x02                  /* even parity */
#define LCX_PAR_BIT9 0x03                  /* ninth data bit, in LCX_X9 */
#define LCX_ESTR     0x04                  /* T, clocked by a pin: first bit at the first shift edge after the write */
#define LCX_BCD      0x04                  /* R: bus condition detector (data edge while the clock pin is high) */
#define LCX_BEV      0x08                  /* R: LCX_STP, LCX_STA, LCX_ECF set the event of the cell */
#define LCX_STP      0x10                  /* R: rising data edge while the clock was high (write 1 to clear) */
#define LCX_STA      0x20                  /* R: falling data edge while the clock was high (write 1 to clear) */
#define LCX_ECF      0x40                  /* R: edge count reached (write 1 to clear) */
#define LCX_X9       0x80                  /* R: ninth bit of the oldest frame; T: ninth bit of the next frame written */
#define LC_NREG    15                      /* registers per cell, for table copies */
#define LC_REG(cell, reg) _CF8((cell) + (reg))        /* e.g. LC_REG(LC_T1, LC_ENC) */
#define LC_BASE(cell)     ((volatile uint8_t *)(0x3F00 + (cell)))


/* LCCTRL */
#define LCC_EN       0x80
#define LCC_RXEN     0x40
#define LCC_TXEN     0x20
#define LCC_UNIT     0x10                  /* 1: both edges of the source clock */
#define LCC_PRE(n)   ((n) & 7)             /* time unit divided by 2^n */
/* LCPIN */
#define LCP_INSEL(p) (((p) & 7) << 5)
#define LCP_INV      0x10
#define LCP_FILT_OFF 0x00
#define LCP_FILT_2   0x04
#define LCP_FILT_3   0x08
#define LCP_OEM_DDR  0x00
#define LCP_OEM_ON   0x01
#define LCP_OEM_BUSY 0x02
/* LCOUT */
#define LCO_OUTSEL(p) (((p) & 7) << 5)
#define LCO_OUTEN    0x10
#define LCO_NSEL(p)  (((p) & 7) << 1)
#define LCO_NEN      0x01
/* LCCLK */
#define LCK_CSEL(p)  (((p) & 7) << 5)
#define LCK_CEN      0x10
#define LCK_NFN      0x08                  /* second output: 0 complement, 1 bit clock */
#define LCK_CPOL     0x04
#define LCK_CPHA     0x02
#define LCK_BLEN     0x01                  /* both-low detector */
/* LCTIM */
#define LCT_EDGE_NONE 0x00
#define LCT_EDGE_RISE 0x40
#define LCT_EDGE_FALL 0x80
#define LCT_EDGE_BOTH 0xC0
#define LCT_ACC_WAIT  0x20                 /* edges accepted only while waiting */
#define LCT_STOP_RUN  0x00
#define LCT_STOP_SAMPLE 0x08
#define LCT_STOP_FRAME  0x10
#define LCT_TWOPH     0x04
#define LCT_TRIG_TIMER 0x00
#define LCT_TRIG_EDGE  0x01
#define LCT_TRIG_PAIR  0x02                /* R: middle of each transmitted bit. T: one bit per received bit */
/* LCSH */
#define LCH_LEN(bits) ((((bits) - 1) & 7) << 5)   /* frame length in bits, 1 to 8 */
#define LCH_LSBF     0x10
#define LCH_SRC      0x08                  /* transmit the neighbour's decoded bit */
#define LCH_CMP      0x04                  /* compare mode */
#define LCH_MEN      0x02                  /* search for the match pattern */
#define LCH_SS       0x01                  /* add start and stop bit */
/* LCRUN */
#define LCR_LIM(n)   (((n) & 7) << 5)
#define LCR_RMODE    0x10                  /* 0 count ones, 1 count equal bits */
#define LCR_LOW2     0x08
#define LCR_IDLE     0x04
#define LCR_EOP      0x02                  /* T: after the last bit both outputs are low for two bit periods (USB end of packet) */
#define LCR_REF_NONE 0x00
#define LCR_REF_EDGE 0x01
#define LCR_REF_BOTHL 0x02
#define LCR_REF_BOTHL_IDLE 0x03
/* LCCS */
#define LCX_SSEL(p)  (((p) & 7) << 5)
#define LCX_SSEN     0x10
#define LCX_SSPOL    0x08
/* lookup tables */
#define LUT_DEC_LEVEL   0xF0
#define LUT_DEC_INVERT  0x0F
#define LUT_DEC_NRZI    0xC3
#define LUT_ENC_NRZ     0xF0
#define LUT_ENC_NRZI    0xA5
#define LUT_ENC_MANCH   0xC3

/* clocking */
#define CLKCTL   _CF8(0x20)   /* protected */
#define OSCTRIM  _CF8(0x21)
#define CLKCDIV  _CF8(0x22)   /* protected */
#define CLKPDIV  _CF8(0x23)
#define TRINT    _CF8(0x24)
#define TRCNTL   _CF8(0x25)
#define TRCNTH   _CF8(0x26)
#define TRCNT    _CF16(0x25)
#define TRTGTL   _CF8(0x27)
#define TRTGTH   _CF8(0x28)
#define TRTGT    _CF16(0x27)
#define TRWIN    _CF8(0x29)
#define CLKOUT   _CF8(0x2A)
#define CKC_SRC      0x01
#define CKC_OSCEN    0x02
#define CKC_LOOP     0x04
#define CKC_TRIMD    0x08
#define CKC_REF_HOST 0x00
#define CKC_REF_PIN  0x10
#define CKC_REF_CELL 0x20
#define CKC_REF_SLOW 0x30                  /* relaxation oscillator, about 100 kHz */
#define CKC_REFCELL(n) (((n) & 1) << 6)     /* receive cell that supplies the reference event */
#define CKC_RELAXEN  0x80                  /* enables the relaxation oscillator */
#define TRI_MEAS     0x80
#define TRINT_MEAS   0x80                  /* write 1: start a measurement; reads 1 while it runs */
#define CKO_EN       0x80
#define CLKOUT_EN    0x80                  /* low bits: source clock divided by 2^(n+1) */
#define DBGSEL_EN    0x80                  /* low bits: signal number */
/* CLKCDIV, CLKPDIV: the core / peripheral clock is enabled in one of every (value + 1) cycles of the source clock */

/* 16-bit timer */
#define TCR      _CF8(0x30)
#define TCAP     _CF8(0x31)
#define OCRA     _CF16(0x32)
#define OCRB     _CF16(0x34)
#define TCR_RUN      0x80
#define TCR_CTC      0x40
#define TCR_PS(n)    ((n) & 7)
#define TCAP_FALL    0x80
#define TCAP_SRC_PIN 0x00
#define TCAP_SRC_EDGE 0x20  /* accepted edge of receive cell TCAP_PIN (0 or 1) */
#define TCAP_SRC_REF  0x40  /* reference event of that cell */
#define TCAP_SRC_OFF 0x60
#define TCAP_PIN(p)  ((p) & 7)

/* PWM */
#define PWMC     _CF8(0x38)
#define PWMTOP   _CF8(0x39)
#define PWM0     _CF8(0x3A)
#define PWM1     _CF8(0x3B)
#define PWM2     _CF8(0x3C)
#define PWMC_EN(n)   (1u << (n))
#define PWMC_PS(n)   (((n) & 7) << 4)

/* CRC unit */
#define CRCCTL   _CF8(0x40)
#define CRCLEN   _CF8(0x41)   /* width minus one */
#define CRCPOLY0 _CF8(0x42)
#define CRCPOLY1 _CF8(0x43)
#define CRCPOLY2 _CF8(0x44)
#define CRCPOLY3 _CF8(0x45)
#define CRCVAL0  _CF8(0x46)
#define CRCVAL1  _CF8(0x47)
#define CRCVAL2  _CF8(0x48)
#define CRCVAL3  _CF8(0x49)
#define CRC_EN       0x80
#define CRC_RIGHT    0x40
#define CRC_SRC_SW   0x00
#define CRC_SRC_R0   0x08                  /* received bits of receive cell 0 */
#define CRC_SRC_T0   0x10                  /* transmitted bits of transmit cell 0 */
#define CRC_SRC_R1   0x18
#define CRC_SRC_T1   0x20
#define CRC_OWNER(n) ((n) & 1)
/* Reference value and status. CRCST is the read side of the address of CRCIN. */
#define CRCREF0  _CF8(0x4A)
#define CRCREF1  _CF8(0x4B)
#define CRCREF2  _CF8(0x4C)
#define CRCREF3  _CF8(0x4D)
#define CRCST    _IO8(0x2A)
#define CRCST_EQF    0x80                  /* value was equal to CRCREF at the last frame boundary */
#define CRCST_EQ     0x40                  /* value is equal to CRCREF now */
#define CRCST_BUSY   0x20                  /* a byte written to CRCIN is being processed */
#define CRC_RESIDUAL_ETH   0xDEBB20E3ul    /* CRC-32, right shift, after a frame with its check sequence */
#define CRC_RESIDUAL_USB16 0xB001u
#define CRC_RESIDUAL_USB5  0x06u
#define CRC_BUSY     0x02                  /* a byte written to CRCIN is still being processed (R) */
/* Set up the CRC unit. poly without the top term; for right shift bit-reversed, and the bits of poly and
   init above the width must be 0. Example, Ethernet: crc_setup(CRC_RIGHT | CRC_SRC_SW, 31, 0xEDB88320, 0xFFFFFFFF) */
static inline void crc_setup(uint8_t ctl, uint8_t len, uint32_t poly, uint32_t init)
{
    CRCCTL = ctl & 0x01; CRCLEN = len;
    CRCPOLY0 = (uint8_t)poly; CRCPOLY1 = (uint8_t)(poly >> 8); CRCPOLY2 = (uint8_t)(poly >> 16); CRCPOLY3 = (uint8_t)(poly >> 24);
    CRCVAL0 = (uint8_t)init; CRCVAL1 = (uint8_t)(init >> 8); CRCVAL2 = (uint8_t)(init >> 16); CRCVAL3 = (uint8_t)(init >> 24);
    CRCCTL = ctl | CRC_EN;
}
/* A byte written to CRCIN is processed in the four clock cycles after the write. Wait for CRC_BUSY = 0
   before reading CRCVAL; a loop that loads, writes and counts is slow enough between two writes. */
static inline void crc_wait(void) { while (CRCCTL & CRC_BUSY) ; }
static inline uint32_t crc_value(void)
{
    return (uint32_t)CRCVAL0 | ((uint32_t)CRCVAL1 << 8) | ((uint32_t)CRCVAL2 << 16) | ((uint32_t)CRCVAL3 << 24);
}

/* system */
#define ARB      _CF8(0x50)   /* protected */
#define LCOWN    _CF8(0x51)   /* protected */
#define DBGSEL   _CF8(0x52)
#define ODE      _CF8(0x53)
#define PCMSK    _CF8(0x54)
#define ARB_ALTERNATE 0              /* on a collision the cores take turns */
#define ARB_CORE0     1              /* core 0 always wins: exact timing for core 0 */
#define ARB_CORE1     2              /* core 1 always wins: exact timing for core 1 */
#define LCOWN_PAIR(pair, core) (((core) & 1) << (pair))
#define DBG_EN       0x80

/* program memory protection */
#define PMCR     _CF8(0x58)   /* protected */
#define PMLIM    _CF8(0x59)   /* protected */
#define PMCR_PWE     0x01             /* stores to the core's own code memory */
#define PMCR_XWE     0x02             /* stores to the other core's code memory */
#define PMCR_LOCK    0x80

/* ---------------- helpers ---------------- */
#define CCP_SIGNATURE 0xD8
#define CCP_UNLOCK()  (CCP = CCP_SIGNATURE)   /* the protected write must follow within four instructions */
/* Write to a protected register. Value and address are loaded first, so that the store follows the
   unlock directly whatever the compiler does. Use this in place of CCP_UNLOCK() for registers of the
   configuration page. */
#define PROT_WRITE(reg, val) do { uint8_t v_ = (val); volatile uint8_t *p_ = &(reg); uint8_t s_ = CCP_SIGNATURE; \
    __asm__ __volatile__("out 0x3C, %2\n\tst %a1, %0" : : "r"(v_), "e"(p_), "d"(s_)); } while (0)

/* stop the calling core until one of the flags in mask is set */
/* Write the 15 configuration registers of a line cell from a table in the order LCCTRL .. LCCS.
   LCCTRL is written last, so that the cell starts with the complete setting. */
static inline void lc_setup(uint8_t cell, const uint8_t *cfg)
{
    volatile uint8_t *p = &LC_REG(cell, 1); uint8_t i;
    for (i = 1; i < 15; i++) *p++ = cfg[i];
    LC_REG(cell, 0) = cfg[0];
}
static inline void wait_for(uint16_t mask) { WAITH = (uint8_t)(mask >> 8); WAITL = (uint8_t)mask; }
/* shared time base (peripheral clock cycles); low byte must be read first */
static inline uint16_t timer_count(void) { uint8_t l = TCNTL; return (uint16_t)l | ((uint16_t)TCNTH << 8); }
static inline uint16_t timer_capture(void) { uint8_t l = ICRL; return (uint16_t)l | ((uint16_t)ICRH << 8); }
static inline void timer_set(uint16_t v) { TCNTH = (uint8_t)(v >> 8); TCNTL = (uint8_t)v; }
static inline uint16_t time_now(void) { uint8_t l = DLYL; return (uint16_t)l | ((uint16_t)DLYH << 8); }
/* set the calling core's wake-up time; clears EV_DLY. Longest wait 32767 */
static inline void delay_until(uint16_t t) { DLYH = (uint8_t)(t >> 8); DLYL = (uint8_t)t; }
static inline void delay_after(uint16_t units) { delay_until(time_now() + units); }
/* periodic use: t += period; delay_until(t); wait_for(EV_DLY); */

/* interrupts exist on both cores; the vectors are in the core's own code memory */
#define ISR_(n) void __vector_##n(void) __attribute__((signal, used)); void __vector_##n(void)
#define ISR(n) ISR_(n)
#define VEC_PC   1
#define VEC_CAPT 2
#define VEC_OCA  3
#define VEC_OCB  4
#define VEC_OVF  5
#define VEC_MBX  6
#define VEC_TRIM 7
#define VEC_DLY  8
#define VEC_LR0  9
#define VEC_LT0  10
#define VEC_LR1  11
#define VEC_LT1  12
#define VEC_SW0  13
#define VEC_SW1  14
#define VEC_SW2  15
#define VEC_SW3  16
/* code memories in the data address space, the same for both cores */
#define CODE0_BASE 0x4000
#define CODE1_BASE 0x4800

/* locks: take returns nonzero if the calling core now holds lock n (n must be a constant 0..3) */
#define lock_try(n)     (LOCK |= (uint8_t)(1u << (n)), (LOCK & (1u << (n))))
#define lock_take(n)    do { } while (!lock_try(n))
#define lock_release(n) (LOCK &= (uint8_t)~(1u << (n)))
#define sei()   __asm__ __volatile__("sei")
#define cli()   __asm__ __volatile__("cli")
#define sleep() __asm__ __volatile__("sleep")
#endif
