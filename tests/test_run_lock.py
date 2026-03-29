from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_lock import RunLockError, acquire_run_lock


class RunLockTests(unittest.TestCase):
    def test_acquire_run_lock_rejects_second_holder(self) -> None:
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".run.lock"
            first = acquire_run_lock(lock_path)
            try:
                with self.assertRaises(RunLockError):
                    acquire_run_lock(lock_path)
            finally:
                first.release()

    def test_release_allows_reacquire(self) -> None:
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".run.lock"
            first = acquire_run_lock(lock_path)
            first.release()

            second = acquire_run_lock(lock_path)
            second.release()


if __name__ == "__main__":
    unittest.main()
