import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger("execution_coordinator")

PIPELINE_EXECUTION_GROUP = "pipeline_execution"


class JobExecutionConflictError(RuntimeError):
    """Raised when a new job conflicts with an already running exclusive job."""

    def __init__(
        self,
        message: str | None = None,
        *,
        active_job_id: str,
        active_job_kind: str,
        group: str,
    ) -> None:
        if message is None:
            message = (
                "Only one job can be run at the same time. "
                f"Running job: {active_job_kind} ({active_job_id})."
            )
        super().__init__(message)
        self.active_job_id = active_job_id
        self.active_job_kind = active_job_kind
        self.group = group


@dataclass(frozen=True)
class ExecutionLease:
    """Represents exclusive execution rights for one or more resource groups."""

    job_id: str
    job_kind: str
    groups: frozenset[str]


class ExecutionCoordinator:
    """Singleton coordinator for exclusive execution across job types."""

    _instance: "ExecutionCoordinator | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ExecutionCoordinator":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._state_lock = threading.Lock()
        self._active_leases_by_group: dict[str, ExecutionLease] = {}

    def acquire(
        self,
        *,
        job_id: str,
        job_kind: str,
        groups: list[str] | tuple[str, ...] | set[str],
    ) -> ExecutionLease:
        """Acquire exclusive execution rights for the given resource groups."""
        normalized_groups = frozenset(groups)
        if not normalized_groups:
            raise ValueError("ExecutionCoordinator.acquire requires at least one group.")

        with self._state_lock:
            for group in normalized_groups:
                active_lease = self._active_leases_by_group.get(group)
                if active_lease is not None:
                    logger.info(
                        "Rejecting %s job %s because %s job %s holds group %s",
                        job_kind,
                        job_id,
                        active_lease.job_kind,
                        active_lease.job_id,
                        group,
                    )
                    raise JobExecutionConflictError(
                        active_job_id=active_lease.job_id,
                        active_job_kind=active_lease.job_kind,
                        group=group,
                    )

            lease = ExecutionLease(
                job_id=job_id,
                job_kind=job_kind,
                groups=normalized_groups,
            )
            for group in normalized_groups:
                self._active_leases_by_group[group] = lease

            logger.debug(
                "Acquired execution lease for %s job %s on groups %s",
                job_kind,
                job_id,
                sorted(normalized_groups),
            )
            return lease

    def release(self, lease: ExecutionLease) -> None:
        """Release previously acquired execution rights."""
        with self._state_lock:
            for group in lease.groups:
                active_lease = self._active_leases_by_group.get(group)
                if active_lease == lease:
                    self._active_leases_by_group.pop(group, None)

            logger.debug(
                "Released execution lease for %s job %s on groups %s",
                lease.job_kind,
                lease.job_id,
                sorted(lease.groups),
            )
