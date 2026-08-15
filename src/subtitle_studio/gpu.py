"""VRAM discipline for the 6GB card: models load sequentially, never together.

Every stage acquires its model inside `gpu_model(loader)`; on exit the model is
deleted and the CUDA cache emptied so the next stage starts from a clean slate.
`with_oom_backoff` retries a callable at progressively smaller batch sizes when
CUDA runs out of memory.
"""

from __future__ import annotations

import gc
import logging
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def free_cuda() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


@contextmanager
def gpu_model(loader: Callable[[], T]) -> Iterator[T]:
    model: T | None = None
    try:
        model = loader()
        yield model
    finally:
        del model
        free_cuda()


def is_cuda_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or "cuda_error_out_of_memory" in text


def with_oom_backoff(fn: Callable[[int], T], batch_size: int, floor: int = 1) -> T:
    """Call fn(batch_size); halve the batch and retry on CUDA OOM until `floor`."""
    current = batch_size
    while True:
        try:
            return fn(current)
        except Exception as exc:  # torch.cuda.OutOfMemoryError subclasses RuntimeError
            if not is_cuda_oom(exc) or current <= floor:
                raise
            current = max(floor, current // 2)
            log.warning("CUDA OOM — retrying with batch_size=%d", current)
            free_cuda()
