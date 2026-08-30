"""Strict policy-driven batch execution with structured attempts."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class BatchJob(Generic[T]):
    job_id: str
    payload: T


@dataclass(frozen=True)
class AttemptError:
    job_id: str
    attempt: int
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class BatchCompletion(Generic[T]):
    job_id: str
    value: T
    attempts: int


class BatchFailure(RuntimeError):
    def __init__(self, errors: tuple[AttemptError, ...]) -> None:
        self.errors = errors
        super().__init__(
            "strict batch failed: " + "; ".join(f"{e.job_id}:{e.code}" for e in errors)
        )


class StrictBatchScheduler(Generic[T]):
    def __init__(self, *, max_workers: int = 4, max_retries: int = 2) -> None:
        if max_workers < 1 or max_retries < 0:
            raise ValueError("invalid batch policy")
        self.max_workers, self.max_retries = max_workers, max_retries

    async def run(
        self,
        jobs: tuple[BatchJob[T], ...],
        worker: Callable[[BatchJob[T]], Awaitable[T]],
        *,
        retryable: Callable[[Exception], bool],
        code: Callable[[Exception], str],
        on_complete: Callable[[BatchCompletion[T]], None],
    ) -> dict[str, T]:
        semaphore = asyncio.Semaphore(self.max_workers)
        errors: list[AttemptError] = []
        completed: dict[str, T] = {}

        async def one(job: BatchJob[T]) -> None:
            for attempt in range(1, self.max_retries + 2):
                try:
                    async with semaphore:
                        value = await worker(job)
                    completed[job.job_id] = value
                    on_complete(BatchCompletion(job.job_id, value, attempt))
                    return
                except Exception as error:
                    can_retry = retryable(error)
                    record = AttemptError(job.job_id, attempt, code(error), str(error), can_retry)
                    errors.append(record)
                    if not can_retry:
                        raise BatchFailure((record,)) from error
                    if attempt > self.max_retries:
                        return

        tasks = [
            asyncio.create_task(one(job)) for job in sorted(jobs, key=lambda item: item.job_id)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        terminal = [result for result in results if isinstance(result, BaseException)]
        if terminal:
            for task in tasks:
                if not task.done():
                    task.cancel()
            first = terminal[0]
            if isinstance(first, BatchFailure):
                raise first
            raise RuntimeError(str(first))
        missing = sorted(job.job_id for job in jobs if job.job_id not in completed)
        if missing:
            relevant = tuple(error for error in errors if error.job_id in missing)
            raise BatchFailure(relevant)
        return {key: completed[key] for key in sorted(completed)}
