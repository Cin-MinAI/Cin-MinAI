# SPDX-License-Identifier: GPL-3.0-or-later
"""Habits on Quaddle's 16 four-bit states: a first exploration (2026-10-03).

Each address keeps its last four choices as bits: 1 = the same as the candidate habit, 0 = something else.
Read on the circular four-channel order a-i-1-z (Quaddle_Number_Theory_State_Machine §4.3), the 16 states split
into 14 connected circular intervals (incl. 0000 and 1111) and the 2 alternating states 0101/1010.
"""
import random
from collections import Counter

random.seed(7)


def category(s):
    b = [(s >> i) & 1 for i in range(4)]
    if s == 0b1111:
        return "habit 1111"
    if s == 0:
        return "none 0000"
    if s in (0b0101, 0b1010):
        return "alternating"
    return "forming/fading"


def push(s, x):  # newest choice in the low bit, oldest falls off
    return ((s << 1) | x) & 0b1111


def stationary(p, steps=200_000):
    s, c = 0, Counter()
    for _ in range(steps):
        s = push(s, 1 if random.random() < p else 0)
        c[category(s)] += 1
    return {k: round(100 * v / steps, 1) for k, v in sorted(c.items())}


print("Share of time in each category, by how consistently the person picks the habit (p):")
for p in (0.5, 0.7, 0.8, 0.9, 0.95, 1.0):
    print(f"  p={p:<4}", stationary(p))

# habit rule A: form at 1111, keep until two of the last four differ (popcount <= 2)
# habit rule B: form at 1111, drop at the first miss (twitchy)
def pop(s):
    return bin(s).count("1")


def run(p_before, p_after, switch_at=60, steps=160, trials=3000):
    """A person who picks the habit with probability p_before, then changes to p_after at switch_at."""
    res = {"A": [], "B": []}
    for rule in ("A", "B"):
        formed, broke, flips = [], [], []
        for _ in range(trials):
            s, on, t_form, t_break, n_flip = 0, False, None, None, 0
            for t in range(steps):
                p = p_before if t < switch_at else p_after
                s = push(s, 1 if random.random() < p else 0)
                was = on
                if not on and s == 0b1111:
                    on = True
                elif on and (pop(s) <= 2 if rule == "A" else s != 0b1111):
                    on = False
                if on != was:
                    n_flip += 1
                if on and t_form is None:
                    t_form = t + 1
                if t >= switch_at and was and not on and t_break is None:
                    t_break = t + 1 - switch_at
            formed.append(t_form)
            broke.append(t_break)
            flips.append(n_flip)
        f = [x for x in formed if x is not None]
        b = [x for x in broke if x is not None]
        res[rule] = dict(formed=f"{100 * len(f) / trials:.0f}% formed, median {sorted(f)[len(f) // 2] if f else '-'} uses",
                         broke=f"{100 * len(b) / trials:.0f}% dropped after the change, median {sorted(b)[len(b) // 2] if b else '-'} uses",
                         flips=f"{sum(flips) / trials:.1f} on/off flips per 160 uses")
    return res


print("\nForming and dropping a habit (A: keep until 2 of the last 4 differ; B: drop at the first miss):")
for before, after, label in ((0.9, 0.9, "steady 9 in 10"), (0.9, 0.1, "9 in 10, then the person changes"),
                             (0.7, 0.7, "7 in 10"), (0.5, 0.5, "a coin toss")):
    r = run(before, after)
    print(f"  {label}:")
    for rule in ("A", "B"):
        print(f"    rule {rule}: {r[rule]['formed']}; {r[rule]['broke']}; {r[rule]['flips']}")

# alternation as its own pattern: a person who alternates A, B, A, B (e.g. two machines on alternate days)
s, c = 0, Counter()
for t in range(4000):
    s = push(s, t % 2)
    c[category(s)] += 1
print("\nA strict A/B alternation sits in:", dict(c))
