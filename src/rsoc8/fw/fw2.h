/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* shared between the two images of firmware test 2 */
#include "rpe.h"
#define EXIT(c) do { _IO8(0x1F) = (c); for (;;) ; } while (0)
#define SHARED_FLAG (*(volatile uint8_t *)0x0700)
#define SHARED_CNT  (*(volatile uint8_t *)0x0701)
#define NMSG 8
#define ROUNDS 100
