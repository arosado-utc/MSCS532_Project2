"""
MSCS 532 - Project (Phase 2)
EmuCache: parameterized guest workloads for the proof of concept.

Phase 1's demo used two fixed guest programs. Phase 2 needs
workloads whose size and input mix are parameters, so the cache
statistics can be reported as a function of cache size and input
mix. Three families are provided, all on the same toy machine:

  counter        - one hot loop; small working set (4 blocks).
  multi_phase    - three sequential game phases with different
                   increments; large working set (10 blocks)
                   that is visited once and retired.
  hub_game       - a three-way hub that round-robins through
                   three routines; cyclic working set (7 blocks)
                   that revisits every block until each
                   countdown expires.
  patch_game     - one loop that rewrites its own increment
                   register between phases (self-modifying
                   code); the working set is created by
                   invalidation and re-translation rather than
                   by code layout.

Each builder returns a fresh Guest, so runs are independent.
Addresses 0x50 and up hold the data in all three workloads;
the code region [0x00, 0x40) is still the only code.
"""

from guest import (Guest, OP_ADD, OP_HALT, OP_JMP, OP_JZ, OP_LOAD,
                   OP_STORE, OP_SUB)


def counter(reps):
    """Score += 1, reps times, then halt.

    0x00: LOAD r1, 0x50   r1 = 1
    0x03: LOAD r2, 0x51   r2 = reps
    0x06: ADD  r0, r1     score += 1
    0x09: SUB  r2, r1     countdown -= 1
    0x0C: JZ   r2, 0x12   countdown == 0 -> halt
    0x0F: JMP  0x06
    0x12: HALT

    Block layout: the loop's JMP targets 0x06, inside the first
    block, so the decoder produces four block starts:
    [0x00,0x0F), [0x06,0x0F), [0x0F,0x12), [0x12,0x15).
    Working set = 4. Fetches = 2*reps. Score = reps.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if reps > 0xFF:
        raise ValueError("reps must fit in one guest byte")
    code = [
        (0x00, OP_LOAD), (0x01, 1), (0x02, 0x50),
        (0x03, OP_LOAD), (0x04, 2), (0x05, 0x51),
        (0x06, OP_ADD),  (0x07, 0), (0x08, 1),
        (0x09, OP_SUB),  (0x0A, 2), (0x0B, 1),
        (0x0C, OP_JZ),   (0x0D, 2), (0x0E, 0x12),
        (0x0F, OP_JMP),  (0x10, 0x06), (0x11, 0),
        (0x12, OP_HALT), (0x13, 0), (0x14, 0),
    ]
    data = [(0x50, 1), (0x51, reps)]
    return Guest(code + data)


def multi_phase_game(reps=50):
    """A three-phase game: each phase counts down reps times,
    adding a different increment to the score.

    Phase 1 adds 1, phase 2 adds 7, phase 3 adds 13. The
    increments are preloaded in r1, r5, and r7; only the
    countdown (r2) is reloaded between phases.

    0x00: LOAD r1, 0x50   r1 = 1
    0x03: LOAD r5, 0x51   r5 = 7
    0x06: LOAD r7, 0x52   r7 = 13
    0x09: LOAD r2, 0x53   r2 = reps
    0x0C: JMP  0x0F       start phase 1
    0x0F: ADD  r0, r1     phase 1 body
    0x12: SUB  r2, r1
    0x15: JZ   r2, 0x1B   phase 1 done -> phase 2
    0x18: JMP  0x0F
    0x1B: LOAD r2, 0x53   phase 2: reload countdown
    0x1E: ADD  r0, r5
    0x21: SUB  r2, r1
    0x24: JZ   r2, 0x2A   phase 2 done -> phase 3
    0x27: JMP  0x1E
    0x2A: LOAD r2, 0x53   phase 3: reload countdown
    0x2D: ADD  r0, r7
    0x30: SUB  r2, r1
    0x33: JZ   r2, 0x39   phase 3 done -> halt
    0x36: JMP  0x2D
    0x39: HALT

    Block layout: the phases 2 and 3 loopbacks target the ADD
    (0x1E, 0x2D), inside their block, to skip the countdown
    reload - the same mid-block entry effect the counter has at
    0x06. Phase 1's loopback targets 0x0F, the block start,
    because phase 1 has no reload to skip. That gives ten block
    starts: the prologue, three bodies, two mid-block entries,
    three loopbacks, and the halt. Working set = 10.
    Fetches = 6*reps - 1. Score = 21 * reps.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if reps > 0xFF:
        raise ValueError("reps must fit in one guest byte")
    code = [
        (0x00, OP_LOAD), (0x01, 1), (0x02, 0x50),
        (0x03, OP_LOAD), (0x04, 5), (0x05, 0x51),
        (0x06, OP_LOAD), (0x07, 7), (0x08, 0x52),
        (0x09, OP_LOAD), (0x0A, 2), (0x0B, 0x53),
        (0x0C, OP_JMP),  (0x0D, 0x0F), (0x0E, 0),
        (0x0F, OP_ADD),  (0x10, 0), (0x11, 1),
        (0x12, OP_SUB),  (0x13, 2), (0x14, 1),
        (0x15, OP_JZ),   (0x16, 2), (0x17, 0x1B),
        (0x18, OP_JMP),  (0x19, 0x0F), (0x1A, 0),
        (0x1B, OP_LOAD), (0x1C, 2), (0x1D, 0x53),
        (0x1E, OP_ADD),  (0x1F, 0), (0x20, 5),
        (0x21, OP_SUB),  (0x22, 2), (0x23, 1),
        (0x24, OP_JZ),   (0x25, 2), (0x26, 0x2A),
        (0x27, OP_JMP),  (0x28, 0x1E), (0x29, 0),
        (0x2A, OP_LOAD), (0x2B, 2), (0x2C, 0x53),
        (0x2D, OP_ADD),  (0x2E, 0), (0x2F, 7),
        (0x30, OP_SUB),  (0x31, 2), (0x32, 1),
        (0x33, OP_JZ),   (0x34, 2), (0x35, 0x39),
        (0x36, OP_JMP),  (0x37, 0x2D), (0x38, 0),
        (0x39, OP_HALT), (0x3A, 0), (0x3B, 0),
    ]
    data = [(0x50, 1), (0x51, 7), (0x52, 13), (0x53, reps)]
    return Guest(code + data)


def hub_game(count=30):
    """A three-way hub: the game round-robins through three
    routines until each of their three countdown cells reaches
    zero.

    Unlike the multi-phase game, the hub revisits every block:
    each full round fetches D1, P1, D2, P2, D3, and P3 again,
    so the working set stays live until the countdowns expire.
    That cyclic access is the regime where LRU shows graded
    behavior as the capacity approaches the working-set size.
    Phase 1 adds 1, phase 2 adds 5, and phase 3 adds 1 again;
    only the access pattern is the point.

    0x00: LOAD r2, 0x50   D1: c1 = mem[0x50]
    0x03: LOAD r1, 0x53   r1 = 1  (reloaded every visit, so
    0x06: LOAD r5, 0x54   no separate prologue is needed)
    0x09: JZ   r2, 0x18   c1 == 0 -> D2
    0x0C: ADD  r0, r1     P1: score += 1
    0x0F: SUB  r2, r1     c1 -= 1
    0x12: STORE 0x50, r2
    0x15: JMP  0x18       -> D2
    0x18: LOAD r3, 0x51   D2: c2
    0x1B: JZ   r3, 0x2A   c2 == 0 -> D3
    0x1E: ADD  r0, r5     P2: score += 5
    0x21: SUB  r3, r1     c2 -= 1
    0x24: STORE 0x51, r3
    0x27: JMP  0x2A       -> D3
    0x2A: LOAD r4, 0x52   D3: c3
    0x2D: JZ   r4, 0x3C   c3 == 0 -> halt
    0x30: ADD  r0, r1     P3: score += 1
    0x33: SUB  r4, r1     c3 -= 1
    0x36: STORE 0x52, r4
    0x39: JMP  0x00       -> D1 (next round)
    0x3C: HALT

    Block layout: seven blocks - three dispatcher blocks D1,
    D2, D3, three phase blocks P1, P2, P3, and the halt.
    Working set = 7. With all three countdowns equal to
    count, fetches = 6*count + 4 and score = 7*count.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if count > 0xFF:
        raise ValueError("count must fit in one guest byte")
    code = [
        (0x00, OP_LOAD), (0x01, 2), (0x02, 0x50),
        (0x03, OP_LOAD), (0x04, 1), (0x05, 0x53),
        (0x06, OP_LOAD), (0x07, 5), (0x08, 0x54),
        (0x09, OP_JZ),   (0x0A, 2), (0x0B, 0x18),
        (0x0C, OP_ADD),  (0x0D, 0), (0x0E, 1),
        (0x0F, OP_SUB),  (0x10, 2), (0x11, 1),
        (0x12, OP_STORE), (0x13, 0x50), (0x14, 2),
        (0x15, OP_JMP),  (0x16, 0x18), (0x17, 0),
        (0x18, OP_LOAD), (0x19, 3), (0x1A, 0x51),
        (0x1B, OP_JZ),   (0x1C, 3), (0x1D, 0x2A),
        (0x1E, OP_ADD),  (0x1F, 0), (0x20, 5),
        (0x21, OP_SUB),  (0x22, 3), (0x23, 1),
        (0x24, OP_STORE), (0x25, 0x51), (0x26, 3),
        (0x27, OP_JMP),  (0x28, 0x2A), (0x29, 0),
        (0x2A, OP_LOAD), (0x2B, 4), (0x2C, 0x52),
        (0x2D, OP_JZ),   (0x2E, 4), (0x2F, 0x3C),
        (0x30, OP_ADD),  (0x31, 0), (0x32, 1),
        (0x33, OP_SUB),  (0x34, 4), (0x35, 1),
        (0x36, OP_STORE), (0x37, 0x52), (0x38, 4),
        (0x39, OP_JMP),  (0x3A, 0x00), (0x3B, 0),
        (0x3C, OP_HALT), (0x3D, 0), (0x3E, 0),
    ]
    data = [(0x50, count), (0x51, count), (0x52, count),
            (0x53, 1), (0x54, 5)]
    return Guest(code + data)


def patch_game(cycles=3, reps=50):
    """One loop, many phases: between phases the game rewrites
    its own increment register index (self-modifying code).

    The loop body always reads the increment register from
    byte 0x17: ADD r0, r[0x17]. Phase 1 uses r1 = 1. At the
    end of a phase the patch routine stores 5 into 0x17, and
    from then on stores 7, so phase 2 uses r5 = 5 and every
    later phase uses r7 = 11. Each store is an SMC write: the
    watcher invalidates every cached block on page 0, and the
    next dispatch of each block retranslates it.

    0x00: LOAD r1, 0x50   r1 = 1      (phase 1 increment)
    0x03: LOAD r5, 0x51   r5 = 5      (phase 2 increment)
    0x06: LOAD r7, 0x52   r7 = 11     (later phases)
    0x09: LOAD r2, 0x53   r2 = reps
    0x0C: LOAD r3, 0x54   r3 = cycles - 1 (patches remaining)
    0x0F: JMP  0x15
    0x15: ADD  r0, r1     loop body; 0x17 holds the register
    0x18: SUB  r2, r1     index of the increment
    0x1B: JZ   r2, 0x21   phase done -> patch check
    0x1E: JMP  0x15
    0x21: JZ   r3, 0x39   no patches left -> halt
    0x24: SUB  r3, r1     patches remaining -= 1
    0x27: LOAD r4, 0x55   next increment register index
    0x2A: STORE 0x17, r4  *** SMC ***
    0x2D: LOAD r6, 0x56   index after next
    0x30: STORE 0x55, r6  update the "next" cell
    0x33: LOAD r2, 0x53   reload countdown
    0x36: JMP  0x15
    0x39: HALT

    With three cycles the game scores reps * (1 + 5 + 11) =
    17 * reps; with two, reps * 6; with one, reps.

    Block layout: the patch check (JZ) ends its own block at
    0x24, so the patch routine is two blocks - a check block
    [0x21,0x24) and a patch block [0x24,0x39) - and both sit
    on page 1, past the SMC write at 0x17. The first SMC write
    therefore invalidates the three page-0 blocks still in the
    cache (prologue, body, loopback), and every later one
    invalidates two, because the prologue is never fetched
    again. The check and patch blocks survive their own SMC
    writes - the bounded over-invalidation the page-granularity
    design accepts.
    """
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    if cycles - 1 > 0xFF:
        raise ValueError("cycles must fit in one guest byte + 1")
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if reps > 0xFF:
        raise ValueError("reps must fit in one guest byte")
    code = [
        (0x00, OP_LOAD), (0x01, 1), (0x02, 0x50),
        (0x03, OP_LOAD), (0x04, 5), (0x05, 0x51),
        (0x06, OP_LOAD), (0x07, 7), (0x08, 0x52),
        (0x09, OP_LOAD), (0x0A, 2), (0x0B, 0x53),
        (0x0C, OP_LOAD), (0x0D, 3), (0x0E, 0x54),
        (0x0F, OP_JMP),  (0x10, 0x15), (0x11, 0),
        (0x15, OP_ADD),  (0x16, 0), (0x17, 1),
        (0x18, OP_SUB),  (0x19, 2), (0x1A, 1),
        (0x1B, OP_JZ),   (0x1C, 2), (0x1D, 0x21),
        (0x1E, OP_JMP),  (0x1F, 0x15), (0x20, 0),
        (0x21, OP_JZ),   (0x22, 3), (0x23, 0x39),
        (0x24, OP_SUB),  (0x25, 3), (0x26, 1),
        (0x27, OP_LOAD), (0x28, 4), (0x29, 0x55),
        (0x2A, OP_STORE), (0x2B, 0x17), (0x2C, 4),
        (0x2D, OP_LOAD), (0x2E, 6), (0x2F, 0x56),
        (0x30, OP_STORE), (0x31, 0x55), (0x32, 6),
        (0x33, OP_LOAD), (0x34, 2), (0x35, 0x53),
        (0x36, OP_JMP),  (0x37, 0x15), (0x38, 0),
        (0x39, OP_HALT), (0x3A, 0), (0x3B, 0),
    ]
    data = [(0x50, 1), (0x51, 5), (0x52, 11), (0x53, reps),
            (0x54, cycles - 1), (0x55, 5), (0x56, 7)]
    return Guest(code + data)
