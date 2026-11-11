"""
MSCS 532 - Project (Phase 2)
EmuCache benchmark harness: cache statistics as a function of
cache size and input mix.

Run:  python3 benchmark.py

Output:
    results/capacity_sweep.csv   one row per (workload, capacity)
    results/size_sweep.csv       one row per (workload, size)
    results/patch_sweep.csv      one row per (reps, cycles)
    plots/hit_rate_vs_capacity.png
    plots/wall_time_vs_size.png
    plots/patch_frequency.png

Measurement notes:
    * Event counts (hits, misses, evictions, invalidations) are
      the primary metrics: they are exact and reproducible.
    * Wall time is secondary; at these sizes the runs are small,
      so each point is timed once rather than averaged.
"""

import csv
import os
import time

from emulator import Emulator
from workloads import counter, hub_game, multi_phase_game, patch_game

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PLOTS = os.path.join(HERE, "plots")

CAPACITIES = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16]

# One representative size per workload family for the capacity
# sweep; the size sweep varies these separately.
WORKLOADS = [
    ("counter", lambda: counter(100)),
    ("multi_phase", lambda: multi_phase_game(50)),
    ("hub", lambda: hub_game(30)),
    ("patch", lambda: patch_game(3, 50)),
]

# Total loop iterations stay at 300 across the patch sweep:
# shorter patch periods mean more SMC rewrites of the same work.
PATCH_POINTS = [(150, 2), (75, 4), (50, 6), (30, 10), (25, 12)]


def run_case(builder, capacity):
    """Run one workload once and return its statistics as a dict."""
    t0 = time.perf_counter()
    emu = Emulator(builder(), cache_capacity=capacity)
    emu.run()
    wall_ms = (time.perf_counter() - t0) * 1000.0
    s = emu.stats
    fetches = s["hits"] + s["misses"]
    rate = 100.0 * s["hits"] / fetches if fetches else 0.0
    return {
        "fetches": fetches,
        "hits": s["hits"],
        "misses": s["misses"],
        "evictions": s["evictions"],
        "invalidations": s["invalidations"],
        "hit_rate_pct": round(rate, 2),
        "wall_ms": round(wall_ms, 3),
    }


def write_csv(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def sweep_capacity():
    """Hit/miss/eviction/invalidation counts per (workload, capacity)."""
    rows = []
    for name, builder in WORKLOADS:
        for cap in CAPACITIES:
            row = {"workload": name, "capacity": cap}
            row.update(run_case(builder, cap))
            rows.append(row)
    path = os.path.join(RESULTS, "capacity_sweep.csv")
    write_csv(path,
              ["workload", "capacity", "fetches", "hits", "misses",
               "evictions", "invalidations", "hit_rate_pct", "wall_ms"],
              rows)
    return rows


def sweep_size():
    """Wall time and event counts as the workload grows, at C = 8."""
    sizes = [
        ("counter", [64, 128, 255]),
        ("multi_phase", [50, 100, 200]),
        ("hub", [15, 30, 60]),
    ]
    builders = {
        "counter": lambda n: counter(n),
        "multi_phase": lambda n: multi_phase_game(n),
        "hub": lambda n: hub_game(n),
    }
    rows = []
    for name, ns in sizes:
        for n in ns:
            row = {"workload": name, "size": n}
            row.update(run_case(lambda n=n: builders[name](n), 8))
            rows.append(row)
    path = os.path.join(RESULTS, "size_sweep.csv")
    write_csv(path,
              ["workload", "size", "fetches", "hits", "misses",
               "evictions", "invalidations", "hit_rate_pct", "wall_ms"],
              rows)
    return rows


def sweep_patch():
    """Hit and invalidation rates as the patch period changes, C = 8."""
    rows = []
    for reps, cycles in PATCH_POINTS:
        row = {"reps": reps, "cycles": cycles, "total": reps * cycles}
        row.update(run_case(lambda c=cycles, r=reps: patch_game(c, r), 8))
        if row["fetches"]:
            row["invalidations_per_1000_fetches"] = round(
                1000.0 * row["invalidations"] / row["fetches"], 2)
        else:
            row["invalidations_per_1000_fetches"] = 0.0
        rows.append(row)
    path = os.path.join(RESULTS, "patch_sweep.csv")
    write_csv(path,
              ["reps", "cycles", "total", "fetches", "hits", "misses",
               "evictions", "invalidations", "hit_rate_pct",
               "invalidations_per_1000_fetches", "wall_ms"],
              rows)
    return rows


def plot_capacity(rows):
    """Hit rate vs cache capacity, one line per workload."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_workload = {}
    for r in rows:
        by_workload.setdefault(r["workload"], []).append(r)
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    for name in ("counter", "multi_phase", "hub", "patch"):
        rs = sorted(by_workload[name], key=lambda r: r["capacity"])
        ax.plot([r["capacity"] for r in rs], [r["hit_rate_pct"] for r in rs],
                marker="o", ms=3.5, label=name)
    ax.set_xlabel("Cache capacity (blocks)")
    ax.set_ylabel("Hit rate (%)")
    ax.set_title("Hit rate vs cache capacity")
    ax.set_xticks(CAPACITIES)
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)
    ax.legend()
    os.makedirs(PLOTS, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "hit_rate_vs_capacity.png"))
    plt.close(fig)


def plot_size(rows):
    """Wall time vs fetch count: the PoC should scale linearly."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_workload = {}
    for r in rows:
        by_workload.setdefault(r["workload"], []).append(r)
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    for name, rs in by_workload.items():
        rs = sorted(rs, key=lambda r: r["fetches"])
        xs = [r["fetches"] for r in rs]
        ys = [r["wall_ms"] for r in rs]
        ax.plot(xs, ys, marker="o", ms=4, label=name)
        # slope-1 reference line through the smallest point
        ax.plot([xs[0], xs[-1]], [ys[0], ys[0] * xs[-1] / xs[0]],
                "--", color=ax.lines[-1].get_color(), alpha=0.4)
    ax.set_xlabel("Block fetches")
    ax.set_ylabel("Wall time (ms)")
    ax.set_title("Wall time vs workload size (dashed: slope 1)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "wall_time_vs_size.png"))
    plt.close(fig)


def plot_patch(rows):
    """Hit rate and invalidation rate vs patch period, C = 8."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted(rows, key=lambda r: r["reps"])
    xs = [r["reps"] for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 3.0), dpi=150)
    a1.plot(xs, [r["hit_rate_pct"] for r in rows], marker="o", ms=4)
    a1.set_xlabel("Patch period (iterations per phase)")
    a1.set_ylabel("Hit rate (%)")
    a1.set_ylim(0, 100)
    a1.set_title("Hit rate vs patch period")
    a1.grid(alpha=0.3)
    a2.plot(xs, [r["invalidations_per_1000_fetches"] for r in rows],
            marker="o", ms=4)
    a2.set_xlabel("Patch period (iterations per phase)")
    a2.set_ylabel("Invalidations per 1000 fetches")
    a2.set_title("SMC invalidation rate vs patch period")
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "patch_frequency.png"))
    plt.close(fig)


def main():
    print("== EmuCache Phase 2: benchmark harness ==\n")
    cap = sweep_capacity()
    size = sweep_size()
    patch = sweep_patch()

    print("--- capacity sweep (C = 8 and C = 1) ---")
    for r in cap:
        if r["capacity"] in (1, 8):
            print(f"  {r['workload']:12s} C={r['capacity']:2d}  "
                  f"hits={r['hits']:5d}  misses={r['misses']:4d}  "
                  f"evictions={r['evictions']:4d}  "
                  f"invalidations={r['invalidations']:3d}  "
                  f"rate={r['hit_rate_pct']:6.2f}%")
    print()
    print("--- patch sweep (total = 300 iterations) ---")
    for r in patch:
        print(f"  reps={r['reps']:4d}  cycles={r['cycles']:3d}  "
              f"rate={r['hit_rate_pct']:6.2f}%  "
              f"inv/1k={r['invalidations_per_1000_fetches']:6.2f}")

    plot_capacity(cap)
    plot_size(size)
    plot_patch(patch)
    print()
    print(f"wrote {RESULTS}/capacity_sweep.csv, size_sweep.csv, "
          f"patch_sweep.csv")
    print(f"wrote {PLOTS}/hit_rate_vs_capacity.png, "
          f"wall_time_vs_size.png, patch_frequency.png")


if __name__ == "__main__":
    main()
