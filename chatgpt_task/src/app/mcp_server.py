from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .database import JobNotFoundError, JobStore, jobs_to_response
from .scheduler import Scheduler, get_time_bucket, parse_scheduled_at


store = JobStore()
scheduler = Scheduler(store)
mcp = FastMCP("task-scheduler")


def task_create(description: str, scheduled_at: str) -> dict[str, object]:
    if not description.strip():
        raise ValueError("description is required")

    scheduled_time = parse_scheduled_at(scheduled_at)
    job = store.create_job(
        description=description.strip(),
        scheduled_at=scheduled_time,
        bucket=get_time_bucket(scheduled_time),
    )
    return job.to_dict()


def task_list() -> dict[str, object]:
    return {"jobs": jobs_to_response(store.list_jobs())}


def task_status(job_id: int) -> dict[str, object]:
    return store.get_job(int(job_id)).to_dict()


def task_cancel(job_id: int) -> dict[str, object]:
    return store.cancel_job(int(job_id)).to_dict()


TOOL_REGISTRY: dict[str, Callable[..., dict[str, object]]] = {
    "task.create": task_create,
    "task.list": task_list,
    "task.status": task_status,
    "task.cancel": task_cancel,
}


def route_tool_call(name: str, arguments: dict[str, Any] | None = None) -> dict[str, object]:
    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    try:
        return handler(**(arguments or {}))
    except JobNotFoundError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool(name="task.create")
def create_task(description: str, scheduled_at: str) -> dict[str, object]:
    """Schedule a task for future execution."""
    return route_tool_call(
        "task.create",
        {"description": description, "scheduled_at": scheduled_at},
    )


@mcp.tool(name="task.list")
def list_tasks() -> dict[str, object]:
    """List all scheduled tasks."""
    return route_tool_call("task.list")


@mcp.tool(name="task.status")
def task_status_tool(job_id: int) -> dict[str, object]:
    """Get the current status for a task."""
    return route_tool_call("task.status", {"job_id": job_id})


@mcp.tool(name="task.cancel")
def cancel_task(job_id: int) -> dict[str, object]:
    """Cancel a pending or queued task."""
    return route_tool_call("task.cancel", {"job_id": job_id})


def main() -> None:
    scheduler.start()
    try:
        mcp.run()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
