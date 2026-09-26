"""Execution policies inside an existing allocation, not job submission clients."""

from dataclasses import dataclass
import os
import shutil

from .tasks import Command, OpenSees, Python


@dataclass(frozen=True)
class TACC:
    """Use single-threaded ibrun rank slots in the current Slurm allocation.

    Machine and queue selection belong to allocation/submission settings.
    Python callbacks run on the coordinator in sequential stages only.
    """

    def capacity(self, requested: int | None) -> int:
        if os.name != "posix" or not (os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_JOBID")):
            raise ValueError("TACC execution requires a Linux Slurm compute allocation")
        try:
            slots = int(os.environ["SLURM_NTASKS"])
            threads = int(os.environ.get("SLURM_CPUS_PER_TASK", "1"))
        except (KeyError, ValueError) as exc:
            raise ValueError("TACC requires SLURM_NTASKS and valid allocation settings") from exc
        if slots < 1 or threads != 1:
            raise ValueError("TACC currently requires positive rank slots and one CPU per task")
        if requested is not None and (
            isinstance(requested, bool) or not isinstance(requested, int)
            or requested < 1 or requested > slots
        ):
            raise ValueError(f"cores must be between 1 and the allocated {slots} rank slots")
        for executable in ("ibrun", "task_affinity"):
            if shutil.which(executable) is None:
                raise ValueError(f"TACC executable not found: {executable}")
        return slots if requested is None else requested

    def validate(self, stage) -> None:
        for task in stage.tasks:
            if isinstance(task, Python):
                if stage.parallel or task.cores != 1:
                    raise ValueError("TACC Python callbacks require sequential stages and cores=1; use an MPI Command for parallel Python")
            elif isinstance(task, Command):
                if task.cores != (task.ranks or 1):
                    raise ValueError("TACC Command cores must equal ranks (or 1 for a serial command)")

    def launch(self, argv: list[str], task: Command | OpenSees, offset: int) -> list[str]:
        return ["ibrun", "-n", str(task.ranks or 1), "-o", str(offset), "task_affinity", *argv]


__all__ = ["TACC"]
