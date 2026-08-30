import asyncio

import pytest

from src.narrative.batch import BatchFailure, BatchJob, StrictBatchScheduler


@pytest.mark.asyncio
async def test_retry_callback_and_canonical_result_order():
    attempts = {}
    callbacks = []

    async def worker(job):
        attempts[job.job_id] = attempts.get(job.job_id, 0) + 1
        if attempts[job.job_id] == 1:
            raise RuntimeError("transient")
        await asyncio.sleep(0)
        return job.payload

    result = await StrictBatchScheduler[int](max_workers=3, max_retries=1).run(
        (BatchJob("b", 2), BatchJob("a", 1)),
        worker,
        retryable=lambda error: isinstance(error, RuntimeError),
        code=lambda error: "TRANSIENT",
        on_complete=callbacks.append,
    )
    assert list(result) == ["a", "b"] and attempts == {"a": 2, "b": 2}
    assert {item.job_id for item in callbacks} == {"a", "b"}


@pytest.mark.asyncio
async def test_terminal_and_exhausted_retry_abort_without_quarantine_success():
    async def terminal(job):
        raise ValueError("configuration")

    with pytest.raises(BatchFailure) as caught:
        await StrictBatchScheduler[int](max_retries=5).run(
            (BatchJob("a", 1),),
            terminal,
            retryable=lambda error: False,
            code=lambda error: "TERMINAL",
            on_complete=lambda result: None,
        )
    assert caught.value.errors[0].attempt == 1 and not caught.value.errors[0].retryable
