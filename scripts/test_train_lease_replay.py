#!/usr/bin/env python3
"""Deterministic replay of the train_land.sh lease protocol, before (#1777) and after.

A MODEL of the protocol, not a measurement of any production fleet: durations are seeded draws, identical for both
policies (common random numbers), so the only difference is the policy.

  before: the exclusive lease is held for the whole train; a second train that finds it held is REFUSED (exit 1)
          and its driver retries every RETRY seconds, so the gate sits idle until the next retry tick after a train ends.
  after:  the second train WAITS for the lease (FIFO) and starts the moment the landing train finishes.

Composing during another train's landing is not modelled because it is not done: that union is stale at its own land.
Run: python3 -I scripts/test_train_lease_replay.py (prints the numbers; asserts the claims; exit 1 on a regression).
"""
import heapq
import random

DRIVERS, TRAINS_EACH, RETRY, SEED = 4, 30, 300, 1777  # 120 trains; retry every 5 min
MEMBERS = 3  # PRs landed per train


def draws():
    rng = random.Random(SEED)
    return [[(rng.uniform(60, 180), rng.uniform(900, 1500), rng.uniform(300, 900)) for _ in range(TRAINS_EACH)]
            for _ in range(DRIVERS)]  # (prep, gate, land) seconds per train


def simulate(wait):
    dur = draws()
    q = [(float(d), d, 0) for d in range(DRIVERS)]  # (attempt time, driver, train index)
    heapq.heapify(q)
    free, refused, idle = 0.0, 0, 0.0
    first = None
    while q:
        t, d, k = heapq.heappop(q)
        if not wait and t < free:  # lease held: refused, retry RETRY seconds later
            refused += 1
            heapq.heappush(q, (t + RETRY, d, k))
            continue
        start = max(t, free)
        if first is None:
            first = start
        else:
            idle += start - free
        free = start + sum(dur[d][k])
        if k + 1 < TRAINS_EACH:
            heapq.heappush(q, (free, d, k + 1))
    merges = DRIVERS * TRAINS_EACH * MEMBERS
    return {"refused": refused, "idle_gate_min": round(idle / 60, 1), "merges_per_day": round(merges / (free - first) * 86400, 1)}


if __name__ == "__main__":
    before, after = simulate(False), simulate(True)
    print("before", before)
    print("after ", after)
    assert after["refused"] == 0 < before["refused"]
    assert after["idle_gate_min"] < before["idle_gate_min"]
    assert after["merges_per_day"] >= before["merges_per_day"]
