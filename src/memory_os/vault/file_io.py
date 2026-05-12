from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


async def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = f".tmp{os.getpid()}"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=path.parent)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        os.rename(tmp_name, str(path))
    except Exception:
        os.close(fd)
        Path(tmp_name).unlink(missing_ok=True)
        raise


async def safe_read(path: Path) -> str:
    loop = asyncio.get_running_loop()

    def _read() -> str:
        return path.read_text(encoding="utf-8")

    return await loop.run_in_executor(None, _read)


async def move_file(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        stem = dst.stem
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        dst = dst.with_name(f"{stem}-{ts}{dst.suffix}")
    os.rename(str(src), str(dst))
    return dst


async def list_directory(dir_path: Path, glob_pattern: str = "*.md") -> list[Path]:
    if not dir_path.exists():
        return []
    loop = asyncio.get_running_loop()

    def _glob() -> list[Path]:
        return sorted(dir_path.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    return await loop.run_in_executor(None, _glob)


async def ensure_directory(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
