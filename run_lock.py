from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RunLockError(RuntimeError):
    pass


def _pid_is_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(slots=True)
class RunLock:
    path: Path
    owner_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    pid: int = field(default_factory=os.getpid)
    acquired: bool = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "owner_id": self.owner_id,
            "pid": self.pid,
            "created_at": datetime.now(UTC).isoformat(),
        }
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder = self._read_lock_info()
                holder_pid = holder.get("pid") if isinstance(holder, dict) else None
                if isinstance(holder_pid, int) and _pid_is_alive(holder_pid):
                    created_at = holder.get("created_at")
                    details = f" (pid {holder_pid}"
                    if isinstance(created_at, str) and created_at:
                        details += f", since {created_at}"
                    details += ")"
                    raise RunLockError(f"Another automation run is already active for {self.path}{details}")
                self._clear_stale_lock(holder)
                continue
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, sort_keys=True)
            except Exception:
                Path(self.path).unlink(missing_ok=True)
                raise
            self.acquired = True
            return

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            info = self._read_lock_info()
            if info.get("owner_id") == self.owner_id:
                self.path.unlink(missing_ok=True)
        finally:
            self.acquired = False

    def _clear_stale_lock(self, holder: dict[str, Any]) -> None:
        if not self.path.exists():
            return
        owner_id = holder.get("owner_id")
        if owner_id is None:
            self.path.unlink(missing_ok=True)
            return
        current = self._read_lock_info()
        if current.get("owner_id") == owner_id:
            self.path.unlink(missing_ok=True)

    def _read_lock_info(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}


def acquire_run_lock(path: Path) -> RunLock:
    lock = RunLock(path=path)
    lock.acquire()
    return lock
