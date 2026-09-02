import threading
from contextlib import contextmanager
from typing import Dict

class CaseLockManager:
    """
    In-memory mutual exclusion lock manager per recovery case.
    In a distributed production environment, this maps to a Redis distributed lock
    (e.g., Redlock) or a PostgreSQL advisory lock (pg_advisory_xact_lock).
    """
    def __init__(self):
        self._global_lock = threading.Lock()
        self._locks: Dict[str, threading.Lock] = {}

    def _get_lock(self, case_id: str) -> threading.Lock:
        with self._global_lock:
            if case_id not in self._locks:
                self._locks[case_id] = threading.Lock()
            return self._locks[case_id]

    @contextmanager
    def acquire(self, case_id: str, timeout: float = 5.0):
        """
        Acquires the lock for a specific case with a timeout.
        Raises TimeoutError if the lock cannot be acquired within the timeout window.
        """
        lock = self._get_lock(case_id)
        acquired = lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Could not acquire lock for case_id={case_id} within {timeout}s timeout")
        try:
            yield
        finally:
            lock.release()

    def try_acquire_nowait(self, case_id: str) -> bool:
        """Attempts to acquire lock without blocking. Returns True if acquired, False otherwise."""
        lock = self._get_lock(case_id)
        return lock.acquire(blocking=False)

    def release_nowait(self, case_id: str):
        """Releases the non-blocking acquired lock."""
        lock = self._get_lock(case_id)
        try:
            lock.release()
        except RuntimeError:
            pass # Already unlocked
