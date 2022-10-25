# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS
from __future__ import annotations

import threading
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    OrderedDict,
    Tuple,
)
from inspect import iscoroutinefunction, signature
from contextlib import asynccontextmanager
import trio
from structlog import get_logger
from PyQt5.QtCore import QObject, pyqtBoundSignal
from trio_typing import TaskStatus

from parsec.core.fs import FSError
from parsec.core.mountpoint import MountpointError
from parsec.utils import open_service_nursery, split_multi_error


logger = get_logger()


JobResultSignal = Tuple[QObject, str]


class JobResultError(Exception):
    def __init__(self, status: Any, **kwargs: Any) -> None:
        self.status = status
        self.params = kwargs
        super().__init__(status, kwargs)


class JobSchedulerNotAvailable(Exception):
    pass


class QtToTrioJob:
    def __init__(
        self,
        fn: Callable[..., Any],
        args: List[Any],
        kwargs: Dict[str, Any],
        on_success: JobResultSignal,
        on_error: JobResultSignal,
    ) -> None:
        # `pyqtBoundSignal` (i.e. `pyqtSignal` connected to a QObject instance) doesn't
        # hold a strong reference on the QObject. Hence if the latter gets freed, calling
        # the signal will result in a segfault !
        # To avoid this, we should instead pass a tuple (<QObject instance>, <name of signal>).
        assert all(not isinstance(a, pyqtBoundSignal) for a in args)
        assert all(not isinstance(v, pyqtBoundSignal) for v in kwargs.values())
        assert not isinstance(on_success, pyqtBoundSignal)
        assert not isinstance(on_error, pyqtBoundSignal)

        self._on_success = on_success
        self._on_error = on_error
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.cancel_scope: Optional[trio.CancelScope] = None
        self._started = trio.Event()
        self._done = threading.Event()
        self.status: Optional[str] = None
        self.ret = None
        self.exc: Optional[Exception] = None

    def __str__(self) -> str:
        return f"{self._fn.__name__}"

    @property
    def arguments(self) -> OrderedDict[str, object]:
        bound_arguments = signature(self._fn).bind(*self._args, **self._kwargs)
        bound_arguments.apply_defaults()
        return bound_arguments.arguments

    def is_finished(self) -> bool:
        return self._done.is_set()

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def is_ok(self) -> bool:
        return self.status == "ok"

    def is_errored(self) -> bool:
        return self.status == "ko"

    def is_crashed(self) -> bool:
        return self.status == "crashed"

    async def __call__(self, *, task_status: TaskStatus[Any] = trio.TASK_STATUS_IGNORED) -> None:
        assert self.status is None
        with trio.CancelScope() as self.cancel_scope:
            task_status.started()  # type: ignore[misc]
            self._started.set()

            try:
                if not iscoroutinefunction(self._fn):
                    result = self._fn(*self._args, **self._kwargs)
                else:
                    result = await self._fn(*self._args, **self._kwargs)
                if isinstance(result, JobResultError):
                    self.set_exception(result)
                else:
                    self.set_result(result)

            except Exception as exc:
                self.set_exception(exc)

            except trio.Cancelled as exc:
                self.set_cancelled(exc)  # type: ignore[arg-type]
                raise

            except trio.MultiError as exc:
                cancelled_errors, other_exceptions = split_multi_error(exc)
                if other_exceptions:
                    self.set_exception(other_exceptions)
                else:
                    self.set_cancelled(cancelled_errors)
                if cancelled_errors:
                    raise cancelled_errors

    def set_result(self, result: Any) -> None:
        self.status = "ok"
        self.ret = result
        self._set_done()

    def set_cancelled(self, exc: Exception) -> None:
        self.status = "cancelled"
        self.exc = exc
        self._set_done()

    def set_exception(self, exc: Exception) -> None:
        if isinstance(exc, JobResultError):
            self.status = exc.status
            self.exc = exc
        elif isinstance(exc, (FSError, MountpointError)):
            self.status = "ko"
            self.exc = exc
        else:
            logger.exception("Uncatched error in Qt/trio job", exc_info=exc)
            wrapped = JobResultError("crashed", exc=exc, info=f"Unexpected error: {repr(exc)}")
            wrapped.__traceback__ = exc.__traceback__
            self.status = wrapped.status
            self.exc = wrapped
        self._set_done()

    def _set_done(self) -> None:
        self._done.set()
        signal = self._on_success if self.is_ok() else self._on_error
        if signal is not None:
            obj, name = signal
            getattr(obj, name).emit(self)

    def cancel(self) -> None:
        assert self.cancel_scope is not None
        self.cancel_scope.cancel()


class QtToTrioJobScheduler:
    def __init__(self, nursery: trio.Nursery) -> None:
        self.nursery = nursery
        self._throttling_scheduled_jobs: dict[str, QtToTrioJob] = {}
        self._throttling_last_executed: dict[str, Any] = {}

    def close(self) -> None:
        self.nursery.cancel_scope.cancel()

    def submit_throttled_job(
        self,
        throttling_id: str,
        delay: float,
        on_success: Callable[..., None],
        on_error: Callable[..., None],
        fn: Callable[..., None],
        *args: Any,
        **kwargs: Any,
    ) -> QtToTrioJob:
        """
        Throttle execution: immediatly execute `fn` unless a job with a similar
        `throttling_id` it has been already executed in the last `delay` seconds,
        in which case we schedule the execution to occur when the delay is elapsed.
        Submitting a job with an already sheduled `throttling_id` will lead to
        a single execution of the last provided job parameters at the soonest delay.
        """

        async def _throttled_execute(
            job: QtToTrioJob, task_status: TaskStatus[Any] = trio.TASK_STATUS_IGNORED
        ) -> None:
            # Only modify `_throttling_scheduled_jobs` from the trio
            # thread to avoid concurrent acces with the Qt thread
            # Note we might be overwritting another job here, it is fine given
            # we only want to execute the last scheduled one
            self._throttling_scheduled_jobs[throttling_id] = job
            task_status.started()  # type: ignore[misc]

            # Sleep the throttle delay, if last execution occurred long enough
            # this will equivalent of doing `trio.sleep(0)`
            last_executed = self._throttling_last_executed.get(throttling_id, 0)
            await trio.sleep_until(last_executed + delay)

            # It is possible our job has been executed by another `_throttled_execute`
            # that had a shorter delay. In such case we have nothing more to do.
            last_executed = self._throttling_last_executed.get(throttling_id, 0)
            if last_executed + delay > trio.current_time():
                return
            job = self._throttling_scheduled_jobs.pop(throttling_id, None)
            if not job:
                return

            # Actually start the job execution
            self._throttling_last_executed[throttling_id] = trio.current_time()
            try:
                await self.nursery.start(job)
            except trio.BrokenResourceError:
                # Job scheduler has been closed, nothing more can be done
                pass

        # Create the job but don't execute it: we have to handle throttle first !
        job = QtToTrioJob(fn, args, kwargs, on_success, on_error)  # type: ignore[arg-type]
        if self.nursery._closed:  # type: ignore[attr-defined]
            job.set_cancelled(JobSchedulerNotAvailable())
        else:
            self.nursery.start_soon(_throttled_execute, job)
        return job

    def submit_job(
        self,
        on_success: JobResultSignal,
        on_error: JobResultSignal,
        fn: Callable[..., None],
        *args: Any,
        **kwargs: Any,
    ) -> QtToTrioJob:
        job = QtToTrioJob(fn, args, kwargs, on_success, on_error)  # type: ignore[arg-type]
        if self.nursery._closed:  # type: ignore[attr-defined]
            job.set_cancelled(JobSchedulerNotAvailable())
        else:
            self.nursery.start_soon(job)
        return job


@asynccontextmanager
async def run_trio_job_scheduler() -> AsyncGenerator[QtToTrioJobScheduler, Any]:
    async with open_service_nursery() as nursery:
        yield QtToTrioJobScheduler(nursery)
