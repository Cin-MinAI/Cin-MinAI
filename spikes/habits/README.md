# Habits on Quaddle's bitcode — experiments (2026-10-03)

How the assistant's personality could evolve: **frequent choices become habits**, and a habit is an address whose
choice has closed — the Choice Atom's |Γ|>1 (a real choice, ask the model) becoming |Γ|=1 (determined, just do it).
Ian's design: nest **3+1** — at each level three bits of switching (a…z: the two positions of the switch, with
**i**, the 0–1 relation, read from the changes between them) plus **w**, the working address
(0 − (1+1) + (1+1): a completed round trip), and only w carries up to the next level. *A binary allows for a switch
but no wall for the switch to exist on; Quaddle supplies the switch and the wall.*

Each script simulates people who pick the "habit candidate" with a fixed consistency (or change their mind halfway)
and measures: whether and when a habit forms, how steady it is (on/off flips), and how fast it notices a change.
No third-party packages: `python3 habit_3plus1.py`.

| Script | What it tries |
|---|---|
| `habit_flat.py` | one 4-bit history per address, read on the circular four-channel order (Quaddle state-machine spec §4.3): 1111 habit, 0000 none, 14 connected states forming/fading, 0101/1010 alternating |
| `habit_nested.py` | a second 4-bit register fed once per four uses (4+4) |
| `habit_3plus1.py` | Ian's 3+1 nesting, two or three levels, with three closure rules |

## Results

**Flat 4 bits:** the categories separate behaviour (9 in 10 sits in 1111 65 % of the time, a coin toss 6 %), and a
strict A/B alternation sits in 0101/1010 99.9 % of the time — alternation is a pattern, not noise. But four bits
can't tell a habit from a lucky streak: a coin toss forms a false habit every time, and a real one flickers ~7× per
160 uses.

**4+4 nesting:** real habits form after ~16 uses and stay steady; a change of mind is noticed after ~8; a coin toss
still forms a false habit 22 % of the time.

**3+1 nesting, three levels, strict at the bottom (level 1 closes only on all three) and forgiving above (2 of 3):**

| Person | Habit forms | Steadiness | Change of mind noticed |
|---|---|---|---|
| 19 in 20 | after ~27 uses | ~1 flip per 180 uses | — |
| 9 in 10 | after ~27 uses | ~1.7 flips | 97 %, after ~36 uses |
| 8 in 10 | 99 % | ~3 flips | — |
| 7 in 10 | ~70 %, slowly (~81 uses) | a weak habit | — |
| a coin toss | **~3 %**, late | ~0.1 flips | — |

No thresholds are stored anywhere ("9 in 10" is not a number in the machine): habit strength emerges from the
nesting — consistent behaviour closes w at every level; inconsistent behaviour can't get past the first wall. Three
levels of 3+1 is 12 bits per address. **i** reads maximal switching (2) in every window for a strict alternation.

Other settings, for the record: all levels strict (3 of 3) — honest but jittery at two levels, far too strict at
three; all levels forgiving (2 of 3) — steady but fooled by chance (a coin toss forms a habit 98-100 % of the time).

## Open

- Noticing a change of mind takes ~36 uses; the safeguard covers it (a habit pauses and asks again after two
  different choices in a row), but faster detection is worth trying.
- Not yet used: Quaddle's verified successor T(a,b,c,h) and its phase bit — e.g. whether reading the history in the
  two interleaved PVP/VPV phases steadies habits, or the 16-cycle's phase marks when a window closes.
- Safeguards (design, not experiment): a new habit is first **offered**, automatic only once accepted; irreversible
  actions never become automatic habits.
