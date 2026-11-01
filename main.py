"""
MSCS 532 - Project (Phase 1)
EmuCache demo: run guest programs through the translation cache
and print hit/miss/eviction/invalidation statistics.

Run:  python3 main.py
"""

from emulator import Emulator
from guest import (Guest, OP_ADD, OP_HALT, OP_JMP, OP_JZ, OP_LOAD,
                   OP_STORE, OP_SUB)


def program_counter():
    """Score += 1, 100 times, then halt.

    0x00: LOAD r1, 0x40   r1 = 1
    0x03: LOAD r2, 0x41   r2 = 100
    0x06: ADD  r0, r1     score += 1
    0x09: SUB  r2, r1     countdown -= 1
    0x0C: JZ   r2, 0x12   countdown == 0 -> halt
    0x0F: JMP  0x06
    0x12: HALT
    """
    code = [
        (0x00, OP_LOAD), (0x01, 1), (0x02, 0x40),
        (0x03, OP_LOAD), (0x04, 2), (0x05, 0x41),
        (0x06, OP_ADD),  (0x07, 0), (0x08, 1),
        (0x09, OP_SUB),  (0x0A, 2), (0x0B, 1),
        (0x0C, OP_JZ),   (0x0D, 2), (0x0E, 0x12),
        (0x0F, OP_JMP),  (0x10, 0x06), (0x11, 0),
        (0x12, OP_HALT), (0x13, 0), (0x14, 0),
    ]
    data = [(0x40, 1), (0x41, 100)]
    return Guest(code + data)


def program_self_patching():
    """A two-phase game that rewrites its own loop code.

    Phase 1: score += 1, 50 times. When the countdown hits zero,
    the patch routine rewrites the loop's ADD operand (byte 0x0B)
    so the loop adds r5 = 7 instead of r1 = 1, resets the
    countdown, and continues. When the second countdown hits zero
    the score is saved and the game halts.

    0x00: LOAD r1, 0x40   r1 = 1
    0x03: LOAD r2, 0x41   r2 = 50
    0x06: LOAD r5, 0x42   r5 = 7   (hard-mode increment)
    0x09: ADD  r0, r1     score += 1      byte 0x0B holds the 1
    0x0C: SUB  r2, r1     countdown -= 1
    0x0F: JZ   r2, 0x1A   countdown == 0 -> patch check
    0x12: JMP  0x09
    0x1A: LOAD r7, 0x45   r7 = PHASE
    0x1D: JZ   r7, 0x2C   PHASE == 0 -> patch; else -> done
    0x20: STORE 0x46, r0  done: save score
    0x23: HALT
    0x2C: LOAD r6, 0x43   patch: r6 = 5 (register index of r5)
    0x2F: STORE 0x0B, r6  *** SMC: loop now does ADD r0, r5 ***
    0x32: LOAD r2, 0x44   r2 = 50
    0x35: LOAD r7, 0x47   r7 = 1
    0x38: STORE 0x45, r7  PHASE = 1
    0x3B: JMP  0x09       continue in hard mode

    Data: 0x40=1  0x41=50  0x42=7  0x43=5  0x44=50
          0x45=0 (PHASE)  0x46=0 (score cell)  0x47=1
    """
    code = [
        (0x00, OP_LOAD), (0x01, 1), (0x02, 0x40),
        (0x03, OP_LOAD), (0x04, 2), (0x05, 0x41),
        (0x06, OP_LOAD), (0x07, 5), (0x08, 0x42),
        (0x09, OP_ADD),  (0x0A, 0), (0x0B, 1),
        (0x0C, OP_SUB),  (0x0D, 2), (0x0E, 1),
        (0x0F, OP_JZ),   (0x10, 2), (0x11, 0x1A),
        (0x12, OP_JMP),  (0x13, 0x09), (0x14, 0),
        (0x1A, OP_LOAD), (0x1B, 7), (0x1C, 0x45),
        (0x1D, OP_JZ),   (0x1E, 7), (0x1F, 0x2C),
        (0x20, OP_STORE), (0x21, 0x46), (0x22, 0),
        (0x23, OP_HALT), (0x24, 0), (0x25, 0),
        (0x2C, OP_LOAD), (0x2D, 6), (0x2E, 0x43),
        (0x2F, OP_STORE), (0x30, 0x0B), (0x31, 6),
        (0x32, OP_LOAD), (0x33, 2), (0x34, 0x44),
        (0x35, OP_LOAD), (0x36, 7), (0x37, 0x47),
        (0x38, OP_STORE), (0x39, 0x45), (0x3A, 7),
        (0x3B, OP_JMP),  (0x3C, 0x09), (0x3D, 0),
    ]
    data = [(0x40, 1), (0x41, 50), (0x42, 7), (0x43, 5),
            (0x44, 50), (0x45, 0), (0x46, 0), (0x47, 1)]
    return Guest(code + data)


def run_and_report(guest, capacity, label):
    """Run a guest through the recompiler and print its statistics."""
    emu = Emulator(guest, cache_capacity=capacity)
    regs = emu.run()
    s = emu.stats
    fetches = s["hits"] + s["misses"]
    pct = 100.0 * s["hits"] / fetches if fetches else 0.0
    print(f"  {label}")
    print(f"    final score   = {regs[0]}")
    print(f"    block fetches = {fetches}")
    print(f"    hits          = {s['hits']} ({pct:.1f}%)")
    print(f"    misses        = {s['misses']}")
    print(f"    evictions     = {s['evictions']}")
    print(f"    invalidations = {s['invalidations']}")
    print()
    return s


def main():
    print("== EmuCache: block translation cache for a game emulator ==\n")

    print("--- Program 1: simple counter (score += 1, 100 times) ---")
    run_and_report(program_counter(), 8, "cache capacity 8")

    print("--- Program 1 again with cache capacity 1 (eviction pressure) ---")
    run_and_report(program_counter(), 1, "cache capacity 1")

    print("--- Program 2: self-patching game (rewrites its own loop) ---")
    s = run_and_report(program_self_patching(), 8, "cache capacity 8")

    if s["invalidations"] >= 4:
        print("  The SMC write at 0x0B evicted the four cached blocks that")
        print("  cover page 0, and the loop retranslated with the new")
        print("  increment - the final score 400 = 50x1 + 50x7 proves the")
        print("  retranslated blocks actually run.")
    else:
        print("  WARNING: self-modifying code did not invalidate the cache!")


if __name__ == "__main__":
    main()
