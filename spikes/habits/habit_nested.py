# SPDX-License-Identifier: GPL-3.0-or-later
"""Nested habits: a second 4-bit register, fed once per completed four-use window (2026-10-03).

Level 1: the last four choices (1 = same as the candidate habit). Every fourth use closes the window and pushes one
bit into level 2: 1 if at least three of the four matched. A habit forms when level 2 reads 1111, and is dropped
when level 2 holds two or more 0s. Same scenarios as habit_sim.py.
"""
import random

random.seed(11)


def pop(s):
    return bin(s).count("1")


def run(p_before, p_after, switch_at=60, steps=160, trials=4000, close_k=3):
    formed, broke, flips, false_on = [], [], [], 0
    for _ in range(trials):
        l1 = l2 = 0
        on, t_form, t_break, n = False, None, None, 0
        for t in range(steps):
            p = p_before if t < switch_at else p_after
            l1 = ((l1 << 1) | (1 if random.random() < p else 0)) & 15
            if (t + 1) % 4 == 0:  # the window closes: one bit up a level
                l2 = ((l2 << 1) | (1 if pop(l1) >= close_k else 0)) & 15
                was = on
                if not on and l2 == 15:
                    on = True
                elif on and pop(l2) <= 2:
                    on = False
                if on != was:
                    n += 1
                if on and t_form is None:
                    t_form = t + 1
                if t >= switch_at and was and not on and t_break is None:
                    t_break = t + 1 - switch_at
        formed.append(t_form)
        broke.append(t_break)
        flips.append(n)
    f = [x for x in formed if x is not None]
    b = [x for x in broke if x is not None]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else "-"
    return (f"{100 * len(f) / trials:.0f}% formed (median {med(f)} uses); "
            f"{100 * len(b) / trials:.0f}% dropped after the change (median {med(b)} uses); "
            f"{sum(flips) / trials:.1f} on/off flips per 160 uses")


for before, after, label in ((0.9, 0.9, "steady 9 in 10"), (0.9, 0.1, "9 in 10, then the person changes"),
                             (0.95, 0.95, "steady 19 in 20"), (0.7, 0.7, "7 in 10"), (0.5, 0.5, "a coin toss")):
    print(f"{label:34} {run(before, after)}")
