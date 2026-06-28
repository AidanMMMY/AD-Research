"""Deployment dashboard schemas."""

from pydantic import BaseModel, Field


class DeploymentRun(BaseModel):
    """A single GitHub Actions workflow run."""

    id: int
    run_number: int
    status: str
    conclusion: str | None = None
    branch: str = Field(alias="head_branch")
    commit: str = Field(alias="head_sha")
    commit_message: str = Field(alias="display_title")
    triggered_by: str = Field(alias="actor_login")
    created_at: str
    updated_at: str
    duration_seconds: int = 0
    html_url: str


class ContainerStats(BaseModel):
    """Docker container resource usage snapshot."""

    name: str
    status: str
    state: str
    image: str
    cpu_percent: float = 0.0
    memory_usage: str = ""
    memory_limit: str = ""
    memory_percent: float = 0.0
    uptime: str = ""


class ServerHealth(BaseModel):
    """Server health and container status overview."""

    containers: list[ContainerStats]
    timestamp: str


class LogLine(BaseModel):
    """A single streamed log line."""

    timestamp: str
    container: str
    message: str
