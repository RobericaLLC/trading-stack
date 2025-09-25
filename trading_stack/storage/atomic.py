from __future__ import annotations
import os, time, json, tempfile
from pathlib import Path
import pandas as pd

class FileLock:
    def __init__(self, path: str | Path, timeout: float = 5.0, poll: float = 0.02):
        self.lock = Path(str(path) + ".lock")
        self.timeout = timeout
        self.poll = poll
    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                # atomic create; fails if exists
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode()); os.close(fd)
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError(f"lock busy: {self.lock}")
                time.sleep(self.poll)
    def __exit__(self, exc_type, exc, tb):
        try: self.lock.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception: pass

def atomic_write_parquet(path: str | Path, df: pd.DataFrame) -> None:
    """Write to temp, then os.replace for atomic swap."""
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    # Use a simpler temp name to avoid Windows path issues
    tmp_name = str(p) + f".tmp{os.getpid()}"
    try:
        df.to_parquet(tmp_name, index=False)
        # On Windows, remove target first if it exists
        if os.name == 'nt' and p.exists():
            try: p.unlink()
            except: pass
        os.replace(tmp_name, str(p))  # atomic on NTFS/ext*
    finally:
        try: os.remove(tmp_name)
        except Exception: pass
