/* SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
 * SPDX-License-Identifier: Apache-2.0 */
/* variables shared by the two images: fixed addresses in the data memory */
#include "rpe.h"
#define SHARED_COUNT (*(volatile uint16_t *)0x0700)
