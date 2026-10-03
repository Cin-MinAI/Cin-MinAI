# SPDX-License-Identifier: GPL-3.0-or-later
"""Habits nested 3+1 (Ian, 2026-10-03): per level, three bits of switching (a..z, with i read from the changes
inside them) plus one bit w, the working address, which is the only thing that nests upward.

Level 1: a 3-bit window of the last three choices (1 = the habit candidate). When it closes (every third use),
w1 = closure (rule 3: all three; rule 2: at least two), and w1 is pushed into level 2's 3-bit window.
Level 2 likewise closes every third w1 and yields w2. Levels: two (3+1 inside 3+1) or three.
A habit is "on" while the top level's w is 1 at its last closure; i (changes inside a window) is reported as the
alternation signal.

rule=0 is the winning setting: strict at the bottom (level 1 closes only on all three — the full round trip),
forgiving above (2 of 3). With three levels it forms real habits in ~27 uses, stays steady, and a coin toss forms
a false one only ~3 % of the time. See README.md.

    python3 habit_3plus1.py
"""
import random

random.seed(23)


def pop(s):
    return bin(s).count("1")


def changes(s):  # i: the number of 0-1 edges inside a 3-bit window
    b = [(s >> k) & 1 for k in range(3)]
    return (b[0] != b[1]) + (b[1] != b[2])


def simulate(p_before, p_after, levels=2, rule=3, switch_at=72, steps=180, trials=4000):
    formed, broke, flips, alt_hits = [], [], [], 0
    for _ in range(trials):
        win = [0] * levels      # each level's 3-bit window
        cnt = [0] * levels      # inputs since that level's window last closed
        on, t_form, t_break, n = False, None, None, 0
        for t in range(steps):
            p = p_before if t < switch_at else p_after
            x = 1 if random.random() < p else 0
            lvl = 0
            while lvl < levels:
                win[lvl] = ((win[lvl] << 1) | x) & 7
                cnt[lvl] += 1
                if cnt[lvl] < 3:
                    break
                cnt[lvl] = 0
                need = rule if rule else (3 if lvl == 0 else 2)  # rule 0: strict bottom, forgiving above
                w = 1 if pop(win[lvl]) >= need else 0          # the working address of this level: closed or not
                if lvl == levels - 1:
                    was = on
                    on = bool(w)
                    if on != was:
                        n += 1
                    if on and t_form is None:
                        t_form = t + 1
                    if t >= switch_at and was and not on and t_break is None:
                        t_break = t + 1 - switch_at
                x = w                                           # only w nests upward (the +1)
                lvl += 1
            if changes(win[0]) == 2:
                alt_hits += 1
        formed.append(t_form)
        broke.append(t_break)
        flips.append(n)
    f = [x for x in formed if x is not None]
    b = [x for x in broke if x is not None]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else "-"
    return (f"{100 * len(f) / trials:3.0f}% formed (median {med(f)} uses); "
            f"{100 * len(b) / trials:3.0f}% dropped after a change (median {med(b)}); "
            f"{sum(flips) / trials:4.1f} flips/180")


cases = ((0.9, 0.9, "steady 9 in 10"), (0.9, 0.1, "9 in 10, then changes"), (0.95, 0.95, "steady 19 in 20"),
         (0.8, 0.8, "8 in 10"), (0.7, 0.7, "7 in 10"), (0.5, 0.5, "a coin toss"))
for levels in (2, 3):
    for rule in (3, 2, 0):
        name = "strict bottom (3 of 3), forgiving above (2 of 3)" if rule == 0 else f"{rule} of 3 at every level"
        print(f"\n3+1 nested, {levels} levels, closure = {name}:")
        for before, after, label in cases:
            print(f"  {label:24} {simulate(before, after, levels, rule)}")

# alternation: i saturates (two 0-1 edges in every 3-bit window) for a strict A/B pattern
alt = [((t % 2) << 2) | (((t + 1) % 2) << 1) | (t % 2) for t in range(10)]
print("\nstrict A/B alternation: i =", sorted({changes(s) for s in alt}), "(2 = maximal switching, every window)")
