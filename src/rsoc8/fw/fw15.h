/* Firmware tests 15 and 16: SPI against the testbench models (tb/spi_slave_model.v, tb/spi_master_model.v).
   Pins as in test 11: 0 MOSI, 1 SCK, 2 MISO, 3 chip select, 4 ready (chip output, high when the slave is set up).
   Master data 0xA5 + 29 i, slave data 0x3C + 53 i, i = byte number in the transfer. */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define M_BYTE(i) ((uint8_t)(0xA5 + 29 * (i)))
#define S_BYTE(i) ((uint8_t)(0x3C + 53 * (i)))
#define CS_PIN  0x08
#define RDY_PIN 0x10
