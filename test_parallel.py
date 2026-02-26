"""Quick test for the parallel execution utility."""
import time, threading, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.parallel import run_parallel


def make_task(n):
    """Simulate a task that takes 0.3s."""
    def _task():
        time.sleep(0.3)
        return f"result_{n}"
    return _task


tasks = [(f"task_{i}", make_task(i)) for i in range(6)]

t0 = time.time()
results = run_parallel(
    tasks,
    max_workers=3,
    progress_callback=lambda m: print(f"  [{threading.current_thread().name}] {m}"),
)
elapsed = time.time() - t0

print(f"\nResults: {results}")
print(f"Elapsed: {elapsed:.2f}s (sequential would be ~1.8s)")

assert len(results) == 6, f"Expected 6 results, got {len(results)}"
assert elapsed < 1.5, f"Too slow ({elapsed:.2f}s) — threading may not be working"
for i in range(6):
    assert results[f"task_{i}"] == f"result_{i}", f"Wrong result for task_{i}"

print("\n[PASS] Parallel execution test PASSED!")
