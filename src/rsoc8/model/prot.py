# SPDX-FileCopyrightText: (c) 2026 Tim S. B. (GitHub: cpldcpu)
# SPDX-License-Identifier: Apache-2.0
"""Behavioural model of the program protection (PMCR, PMLIM, write enables of the code memories).
Written from the specification: section Memory / Code memory protection, system registers table
(PMCR, PMLIM), conventions (protected registers: unlock by the same core within four instructions, host link
needs none), host link text (writes from the host link to the code memories are not subject to the protection)."""
from collections import Counter


class Prot:
    def __init__(s):
        s.lock = 0; s.xwe = 0; s.pwe = 0; s.lim = 0; s.cov = Counter()

    def step(self, addr=0, we=0, wd=0, host=0, unlock=0, cm_addr=(0, 0), cm_we=(0, 0), cm_wother=(0, 0), cm_host=0):
        c = self.cov
        prot = int(addr in (0x158, 0x159))
        rd = 0
        if addr == 0x158: rd = (self.lock << 7) | (self.xwe << 1) | self.pwe
        if addr == 0x159: rd = self.lim
        ok_w = []
        for k in (0, 1):
            en = self.xwe if cm_wother[k] else self.pwe
            below = (cm_addr[k] >> 2) < self.lim
            allowed = int(bool(cm_we[k]) and (cm_host or (not self.lock and not below and en)))
            ok_w.append(allowed)
            if cm_we[k]:
                if cm_host: c['host_write_%s' % ('allowed_although_blocked' if (self.lock or below or not en) else 'allowed')] += 1
                else:
                    why = 'lock' if self.lock else 'below_limit' if below else 'no_enable_%s' % ('other' if cm_wother[k] else 'own') if not en else 'allowed'
                    c['core_write_mem%d_%s' % (k, why)] += 1
                    if allowed and (cm_addr[k] >> 2) == self.lim: c['core_write_at_limit_allowed'] += 1
                    if (not allowed) and (not self.lock) and en and (cm_addr[k] >> 2) == self.lim - 1: c['core_write_just_below_limit_blocked'] += 1
        out = (rd, prot, ok_w[0], ok_w[1])
        if we and addr in (0x158, 0x159):
            if unlock or host:
                c['write_%03x_accepted' % addr] += 1
                if addr == 0x158:
                    if self.lock and not (wd >> 7) & 1: c['lock_clear_attempt_ignored'] += 1
                    if wd & 0x7C: c['pmcr_reserved_bits_written'] += 1
                    self.lock |= (wd >> 7) & 1; self.xwe = (wd >> 1) & 1; self.pwe = wd & 1
                else: self.lim = wd
            else: c['write_%03x_rejected_no_unlock' % addr] += 1
        return out
