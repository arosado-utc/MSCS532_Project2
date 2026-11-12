"""
MSCS 532 - Project (Phases 1 + 2)
EmuCache test suite.

Run with:  python3 tests.py

Covers the hash table, the LRU cache, the SMC watcher, the block
decoder, and full end-to-end runs of the demo guest programs. The
end-to-end tests are checked against a naive single-step
interpreter, so any divergence between the cached path and the
reference path fails the suite. Phase 2 adds the parameterized
workloads from workloads.py and the benchmark harness from
benchmark.py: every workload is checked against the reference
interpreter, and the expected block counts, eviction counts, and
invalidation counts are asserted by hand.
"""

from benchmark import run_case
from cache import HashTable, LRUCache
from emulator import Emulator
from guest import (Guest, OP_ADD, OP_HALT, OP_JMP, OP_JZ, OP_LOAD,
                   OP_STORE, OP_SUB)
from main import program_counter, program_self_patching
from smc import PageWatcher
from workloads import counter, hub_game, multi_phase_game, patch_game


# reference interpreter: single-step, no blocks, no cache
def naive_run(guest, max_steps=100_000):
    """Step through the guest one instruction at a time."""
    regs, mem = guest.regs, guest.mem
    pc = 0
    for _ in range(max_steps):
        op, a, b = mem[pc], mem[pc + 1], mem[pc + 2]
        if op == OP_ADD:
            regs[a] = (regs[a] + regs[b]) % 65536
        elif op == OP_LOAD:
            regs[a] = mem[b]
        elif op == OP_STORE:
            mem[a] = regs[b] % 256
        elif op == OP_SUB:
            regs[a] = (regs[a] - regs[b]) % 65536
        elif op == OP_JMP:
            pc = a
            continue  # JMP sets pc; do not fall through
        elif op == OP_JZ:
            if regs[a] == 0:
                pc = b
            else:
                pc += 3
            continue  # JZ sets pc; do not fall through
        elif op == OP_HALT:
            return regs
        else:
            raise ValueError(f"undecodable opcode 0x{op:02X} at 0x{pc:02X}")
        pc += 3
    raise RuntimeError("guest did not halt")


# HashTable
def test_ht_basic_put_get():
    ht = HashTable()
    ht.put(0x10, "block1")
    assert ht.get(0x10) == "block1"
    ht.put(0x10, "block1-v2")
    assert ht.get(0x10) == "block1-v2"
    assert ht.get(0x99) is None
    assert ht.get(0x99, "default") == "default"


def test_ht_contains_and_delete():
    ht = HashTable()
    ht.put(5, "x")
    assert 5 in ht
    ht.delete(5)
    assert 5 not in ht
    assert ht.delete(5) is False
    # re-inserting a deleted key must work (tombstone reuse)
    ht.put(5, "y")
    assert ht.get(5) == "y"


def test_ht_rehash_preserves_entries():
    ht = HashTable(4)
    for k in range(0, 500, 3):  # forces several rehashes
        ht.put(k, k * 10)
    for k in range(0, 500, 3):
        assert ht.get(k) == k * 10
    assert len(ht) == 167


def test_ht_sequential_keys_spread():
    """Consecutive program counters must not cluster in one probe
    chain - 300 sequential keys, all findable."""
    ht = HashTable(16)
    for k in range(300):
        ht.put(k, k)
    for k in range(300):
        assert ht.get(k) == k
    assert len(ht) == 300


# LRUCache
def test_lru_eviction_order():
    c = LRUCache(2)
    c.put(1, "a")
    c.put(2, "b")
    c.get(1)             # 1 becomes most recent
    evicted = c.put(3, "c")
    assert evicted == (2, "b")  # 2 was the LRU entry
    assert c.get(2) is None
    assert c.get(1) == "a"
    assert c.get(3) == "c"


def test_lru_refresh_does_not_evict():
    c = LRUCache(2)
    c.put(1, "a")
    c.put(2, "b")
    assert c.put(1, "a2") is None
    assert c.get(1) == "a2"
    assert len(c) == 2


def test_lru_remove():
    c = LRUCache(2)
    c.put(1, "a")
    c.put(2, "b")
    assert c.remove(1) == "a"
    assert c.get(1) is None
    assert c.remove(1) is None
    assert len(c) == 1
    # the freed slot must be reusable without growth
    c.put(1, "a3")
    assert len(c) == 2


# PageWatcher
def test_watcher_basic():
    w = PageWatcher(page_size=32)
    w.register(1, 0x00, 0x10)   # page 0
    w.register(2, 0x20, 0x30)   # page 1
    assert w.on_write(0x05) == {1}
    assert w.on_write(0x25) == {2}
    assert w.on_write(0x40) == set()  # data page: not watched
    w.unregister(1, 0x00, 0x10)
    assert w.on_write(0x05) == set()
    assert w.on_write(0x25) == {2}


def test_watcher_spanning_pages():
    w = PageWatcher(page_size=32)
    w.register(7, 0x10, 0x30)  # spans pages 0 and 1
    assert w.on_write(0x1F) == {7}
    assert w.on_write(0x25) == {7}
    w.unregister(7, 0x10, 0x30)
    assert w.on_write(0x1F) == set()
    assert w.on_write(0x25) == set()


def test_watcher_bad_page_size():
    try:
        PageWatcher(page_size=24)
        assert False, "expected ValueError"
    except ValueError:
        pass


# Guest block decoder
def test_decode_block_stops_at_branch():
    g = program_counter()
    start, insts, end = g.decode_block(0x00)
    assert start == 0x00
    assert insts[-1][0] == OP_JZ  # block ends at, including, the JZ
    assert end == 0x0F            # first address past the block


def test_decode_block_missing_code():
    g = program_counter()
    try:
        g.decode_block(0x50)  # no code there
        assert False, "expected ValueError"
    except ValueError:
        pass


# End-to-end: emulator vs naive interpreter
def test_counter_program_matches_reference():
    g = program_counter()
    expected = naive_run(g)
    g2 = program_counter()
    actual = Emulator(g2, cache_capacity=8).run()
    assert actual == expected
    assert actual[0] == 100  # the score


def test_counter_cache_stats():
    emu = Emulator(program_counter(), cache_capacity=8)
    emu.run()
    assert emu.stats["misses"] == 4       # 4 distinct block starts
    assert emu.stats["hits"] == 196
    assert emu.stats["evictions"] == 0
    assert emu.stats["invalidations"] == 0


def test_counter_eviction_pressure():
    emu = Emulator(program_counter(), cache_capacity=1)
    regs = emu.run()
    assert regs[0] == 100                # still correct
    assert emu.stats["hits"] == 0        # nothing survives a fetch
    assert emu.stats["evictions"] == 199


def test_self_patching_program_matches_reference():
    g = program_self_patching()
    expected = naive_run(g)
    g2 = program_self_patching()
    actual = Emulator(g2, cache_capacity=8).run()
    assert actual == expected
    assert actual[0] == 400  # 50 x 1 + 50 x 7: the patched loop ran


def test_self_patching_invalidation_count():
    emu = Emulator(program_self_patching(), cache_capacity=8)
    emu.run()
    # four cached blocks cover page 0 (0x00, 0x09, 0x12, 0x1A)
    assert emu.stats["invalidations"] == 4
    # the SMC write must not evict via capacity pressure
    assert emu.stats["evictions"] == 0


def test_data_write_does_not_invalidate():
    """Stores to the data region (>= 0x40) must not touch the cache."""
    emu = Emulator(program_counter(), cache_capacity=8)
    emu.run()
    before = dict(emu.stats)
    emu._store(0x50, 0xAB)  # data region write
    assert emu.stats["invalidations"] == before["invalidations"]


def test_non_halting_guest_hits_step_limit():
    # a program that jumps to itself: 0x00: JMP 0x00
    g = Guest([(0x00, OP_JMP), (0x01, 0x00), (0x02, 0)])
    emu = Emulator(g, cache_capacity=4)
    try:
        emu.run(max_steps=100)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


# Phase 2: workloads
def test_workloads_match_reference():
    """Every workload must produce the same register file as the
    naive interpreter, and the expected final score."""
    cases = [
        (lambda: counter(100), 100),
        (lambda: multi_phase_game(50), 21 * 50),
        (lambda: hub_game(30), 7 * 30),
        (lambda: patch_game(3, 50), 17 * 50),
    ]
    for builder, score in cases:
        expected = naive_run(builder())
        actual = Emulator(builder(), cache_capacity=8).run()
        assert actual == expected
        assert actual[0] == score


def test_counter_working_set():
    """The counter has four block starts (the loopback targets
    0x06, inside the first block); C = 8 covers them all."""
    emu = Emulator(counter(255), cache_capacity=8)
    emu.run()
    assert emu.stats["misses"] == 4
    assert emu.stats["evictions"] == 0


def test_counter_capacity_one():
    emu = Emulator(counter(100), cache_capacity=1)
    emu.run()
    assert emu.stats["hits"] == 0
    assert emu.stats["misses"] == 200


def test_hub_working_set_and_thrash():
    """The hub's seven blocks stay live until the countdowns
    expire. A C = 8 cache holds them all (seven misses, no
    evictions); a C = 3 cache cannot hold the six-block round
    and re-misses on almost every fetch."""
    big = Emulator(hub_game(30), cache_capacity=8)
    big.run()
    assert big.stats["misses"] == 7
    assert big.stats["evictions"] == 0
    small = Emulator(hub_game(30), cache_capacity=3)
    small.run()
    assert small.stats["misses"] > 100
    assert small.stats["evictions"] > 0


def test_multi_phase_no_remisses():
    """The phases are sequential: retired blocks are never
    re-fetched, so misses stay at the working-set size (10)
    even when the cache cannot hold them - evictions happen,
    re-misses do not."""
    emu = Emulator(multi_phase_game(50), cache_capacity=2)
    emu.run()
    assert emu.stats["misses"] == 10
    assert emu.stats["evictions"] == 8


def test_patch_invalidations_follow_the_page():
    """The SMC write lands on page 0; the check and patch
    blocks sit on page 1 and survive their own writes. The
    first patch invalidates three cached blocks (prologue,
    body, loopback), later patches invalidate two (the
    prologue is gone), so four cycles give 3 + 2 + 2 = 7."""
    emu = Emulator(patch_game(4, 20), cache_capacity=8)
    emu.run()
    assert emu.stats["invalidations"] == 7
    assert emu.stats["misses"] == 12
    assert emu.stats["evictions"] == 0


def test_patch_single_cycle_no_smc():
    """One cycle means no patch routine run and no SMC write."""
    emu = Emulator(patch_game(1, 100), cache_capacity=8)
    emu.run()
    assert emu.stats["invalidations"] == 0
    assert emu.stats["misses"] == 5


def test_workload_builder_validation():
    for bad in (dict(reps=0), dict(reps=256)):
        try:
            counter(**bad)
            assert False, "expected ValueError"
        except ValueError:
            pass
    for bad in (0, 256):
        try:
            hub_game(bad)
            assert False, "expected ValueError"
        except ValueError:
            pass
    try:
        patch_game(cycles=0, reps=50)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_hit_rate_monotone_in_capacity():
    """A larger LRU cache never misses more than a smaller one
    on the same access sequence, so the hit rate must be
    non-decreasing in the capacity."""
    for builder in (lambda: counter(100), lambda: multi_phase_game(50),
                    lambda: hub_game(30), lambda: patch_game(3, 50)):
        rates = [run_case(builder, c)["hit_rate_pct"]
                 for c in (1, 2, 3, 4, 5, 6, 8, 10, 16)]
        for lo, hi in zip(rates, rates[1:]):
            assert hi >= lo, (builder, rates)


def test_run_case_row_is_consistent():
    row = run_case(lambda: patch_game(3, 50), 8)
    assert row["hits"] + row["misses"] == row["fetches"]
    assert row["hit_rate_pct"] == round(
        100.0 * row["hits"] / row["fetches"], 2)
    assert 0.0 <= row["hit_rate_pct"] <= 100.0
def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")

    print()
    if failed:
        print(f"{failed} of {len(tests)} test(s) FAILED.")
        raise SystemExit(1)
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
