"""
Parallel task executor — runs multiple RAG/LLM tasks concurrently
using a ThreadPoolExecutor for faster batch generation.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple


def run_parallel(
    tasks: List[Tuple[str, Callable]],
    max_workers: int = 3,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, any]:
    """
    Execute multiple named tasks in parallel and collect results.

    Parameters
    ----------
    tasks : list of (name, callable) tuples
        Each callable takes no arguments and returns a result.
    max_workers : int
        Maximum concurrent threads. Keep this modest (2-4) since each
        task hits the Ollama API which is GPU-bound.
    progress_callback : callable, optional
        Called with a status string each time a task completes.

    Returns
    -------
    dict  {task_name: result_or_error_string}
    """
    results: Dict[str, any] = {}
    lock = threading.Lock()
    completed = [0]
    total = len(tasks)

    def _run_task(name: str, fn: Callable):
        try:
            return name, fn()
        except Exception as e:
            return name, f"[Error: {e}]"

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_task, name, fn): name
            for name, fn in tasks
        }

        for future in as_completed(futures):
            name, result = future.result()
            with lock:
                results[name] = result
                completed[0] += 1
                if progress_callback:
                    progress_callback(
                        f"Completed {completed[0]}/{total}: {name}"
                    )

    return results
