from __future__ import annotations

import hashlib
import gzip
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent
from typing import Annotated

import psutil
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint, create_engine, delete, func, select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


load_dotenv("apps/server/.env")


class ProcessInfo(BaseModel):
    pid: int
    name: str | None = None
    status: str | None = None
    username: str | None = None
    command: str | None = None


class OsPidAvailabilityResponse(BaseModel):
    current_pid: int
    scanned_min_pid: int
    scanned_max_pid: int
    occupied_count: int
    available_count: int
    available_pids: list[int] = Field(
        description="Candidate PIDs that are not occupied at scan time. They are not reserved."
    )
    occupied_sample: list[ProcessInfo]
    warning: str


class ProcessIdAvailabilityResponse(BaseModel):
    process_id: str
    available: bool
    reason: str
    storage_available: bool


class ProcessIdDefaultsResponse(BaseModel):
    app_process_id: str
    agent_process_id: str
    supervisor_process_id: str
    storage_available: bool
    warning: str | None = None


class ProcessIdentityInfo(BaseModel):
    process_id: str
    role: str
    workspace_id: str | None
    display_name: str | None


class ProcessIdentityCreate(BaseModel):
    process_id: str
    role: str
    workspace_id: str | None = None
    display_name: str | None = None


class ProcessIdentityCreateResponse(BaseModel):
    storage_available: bool
    created: list[ProcessIdentityInfo]
    warning: str | None = None


class ProcessIdentityDeleteResponse(BaseModel):
    storage_available: bool
    workspace_id: str
    deleted_count: int
    warning: str | None = None


class ProcessIdentityListResponse(BaseModel):
    storage_available: bool
    items: list[ProcessIdentityInfo]
    warning: str | None = None


class WorkspaceProcessIds(BaseModel):
    app: str
    agent: str
    watch: str


class WorkspacePayload(BaseModel):
    id: str
    name: str
    path: str
    command: str
    agent_command: str
    poll_seconds: int
    ai_can_edit: bool
    initial_prompt: str
    process_ids: WorkspaceProcessIds


class ProcessStatusInfo(BaseModel):
    role: str
    process_id: str
    os_pid: int | None = None
    status: str
    detail: str | None = None


class WorkspaceInfo(WorkspacePayload):
    status: str
    runtime: str
    logs: list[str]
    runtime_status: dict[str, ProcessStatusInfo]


class WorkspaceListResponse(BaseModel):
    storage_available: bool
    items: list[WorkspaceInfo]
    warning: str | None = None


class WorkspaceDeleteResponse(BaseModel):
    storage_available: bool
    workspace_id: str
    deleted_process_ids: int
    deleted_links: int
    deleted_runtime_instances: int
    deleted_workspaces: int
    warning: str | None = None


class ProcessLinkInfo(BaseModel):
    from_process_id: str
    to_process_id: str
    link_type: str


class ProcessRuntimeInfo(BaseModel):
    runtime_id: int
    process_id: str
    role: str
    os_pid: int | None
    status: str
    stdin_channel: str | None
    stdout_log: str | None
    stderr_log: str | None


class WorkspaceProcessGraphResponse(BaseModel):
    storage_available: bool
    workspace_id: str
    identities: list[ProcessIdentityInfo]
    links: list[ProcessLinkInfo]
    runtime_instances: list[ProcessRuntimeInfo]
    warning: str | None = None


class DirectorySelectionResponse(BaseModel):
    selected: bool
    path: str | None = None
    message: str | None = None


class RuntimeLogCreate(BaseModel):
    workspace_id: str
    process_id: str
    role: str
    level: str = "INFO"
    log_type: str = "event"
    content: str


class RuntimeLogInfo(BaseModel):
    log_id: int
    workspace_id: str
    process_id: str
    role: str
    level: str
    log_type: str
    content: str
    occurred_at: str
    created_at: str


class RuntimeLogListResponse(BaseModel):
    storage_available: bool
    items: list[RuntimeLogInfo]
    warning: str | None = None


class LogSettingsPayload(BaseModel):
    archive_root: str = ""
    retention_days: int = Field(default=30, ge=1, le=3650)
    default_log_limit: int = Field(default=1000, ge=10, le=5000)
    sync_tail_lines: int = Field(default=5000, ge=100, le=50000)


class LogSettingsInfo(LogSettingsPayload):
    storage_available: bool
    warning: str | None = None


class WorkspaceRuntimeStatusResponse(BaseModel):
    storage_available: bool
    workspace_id: str
    items: dict[str, ProcessStatusInfo]
    warning: str | None = None


class Base(DeclarativeBase):
    pass


class ProcessIdentity(Base):
    __tablename__ = "process_identities"
    __table_args__ = (UniqueConstraint("process_id", name="uq_process_identities_process_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    process_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Workspace(Base):
    __tablename__ = "workspaces"

    workspace_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    start_command: Mapped[str] = mapped_column(Text, nullable=False)
    agent_command: Mapped[str] = mapped_column(Text, nullable=False)
    poll_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    ai_can_edit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    initial_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProcessLink(Base):
    __tablename__ = "process_links"
    __table_args__ = (
        UniqueConstraint("workspace_id", "from_process_id", "to_process_id", "link_type", name="uq_process_links_edge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    from_process_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    to_process_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessRuntimeInstance(Base):
    __tablename__ = "process_runtime_instances"

    runtime_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    process_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    os_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pid_create_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    cwd: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="starting")
    stdin_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stdout_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stopped_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeLog(Base):
    __tablename__ = "runtime_logs"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_runtime_logs_content_hash"),)

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="INFO")
    log_type: Mapped[str] = mapped_column(String(64), nullable=False, default="event")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class LogArchive(Base):
    __tablename__ = "log_archives"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    process_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    archive_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LogSettings(Base):
    __tablename__ = "log_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    archive_root: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    default_log_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    sync_tail_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


MYSQL_URL = os.getenv(
    "CODE_MONITOR_DATABASE_URL",
    "mysql+pymysql://root:root@127.0.0.1:3306/code_monitor?charset=utf8mb4",
)
LOG_RETENTION_DAYS = max(1, int(os.getenv("AICM_LOG_RETENTION_DAYS", "30")))
LOG_SYNC_LOCK = threading.Lock()

engine = create_engine(MYSQL_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

app = FastAPI(title="Code Monitor API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        _ensure_runtime_log_schema()
    except SQLAlchemyError:
        # Database health is surfaced through API responses so the UI can remain usable.
        pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _database_available(db: Session) -> bool:
    try:
        db.execute(select(1))
    except SQLAlchemyError:
        return False
    return True


def _default_log_settings() -> LogSettingsPayload:
    return LogSettingsPayload(
        archive_root=os.getenv("AICM_LOG_ARCHIVE_ROOT", ""),
        retention_days=LOG_RETENTION_DAYS,
        default_log_limit=int(os.getenv("AICM_DEFAULT_LOG_LIMIT", "1000")),
        sync_tail_lines=int(os.getenv("AICM_LOG_SYNC_TAIL_LINES", "5000")),
    )


def _get_log_settings(db: Session) -> LogSettings:
    row = db.scalar(select(LogSettings).where(LogSettings.id == 1))
    if row is not None:
        return row
    defaults = _default_log_settings()
    row = LogSettings(
        id=1,
        archive_root=defaults.archive_root,
        retention_days=defaults.retention_days,
        default_log_limit=defaults.default_log_limit,
        sync_tail_lines=defaults.sync_tail_lines,
    )
    db.add(row)
    db.flush()
    return row


def _log_settings_to_info(row: LogSettings, storage_available: bool = True, warning: str | None = None) -> LogSettingsInfo:
    return LogSettingsInfo(
        archive_root=row.archive_root,
        retention_days=row.retention_days,
        default_log_limit=row.default_log_limit,
        sync_tail_lines=row.sync_tail_lines,
        storage_available=storage_available,
        warning=warning,
    )


def _ensure_runtime_log_schema() -> None:
    statements = [
        "ALTER TABLE runtime_logs ADD COLUMN content_hash VARCHAR(64) NULL",
        "ALTER TABLE runtime_logs ADD COLUMN occurred_at TIMESTAMP NULL",
        "UPDATE runtime_logs SET content_hash = SHA2(CONCAT(workspace_id, ':', process_id, ':', role, ':', log_type, ':', log_id, ':', content), 256) WHERE content_hash IS NULL",
        "UPDATE runtime_logs SET occurred_at = created_at WHERE occurred_at IS NULL",
        "ALTER TABLE runtime_logs MODIFY content_hash VARCHAR(64) NOT NULL",
        "ALTER TABLE runtime_logs MODIFY occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "CREATE UNIQUE INDEX uq_runtime_logs_content_hash ON runtime_logs (content_hash)",
        "CREATE INDEX ix_runtime_logs_occurred_at ON runtime_logs (occurred_at)",
        "CREATE INDEX ix_runtime_logs_workspace_role_time ON runtime_logs (workspace_id, role, occurred_at)",
        "CREATE INDEX ix_runtime_logs_workspace_level_time ON runtime_logs (workspace_id, level, occurred_at)",
        "CREATE INDEX ix_runtime_logs_process_time ON runtime_logs (process_id, occurred_at)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except SQLAlchemyError:
                continue


def _normalize_process_id(process_id: str) -> str:
    return process_id.strip()


def _is_valid_process_id(process_id: str) -> bool:
    if not 3 <= len(process_id) <= 80:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    return all(char in allowed for char in process_id)


def _process_id_exists(db: Session, process_id: str) -> bool:
    existing = db.scalar(select(ProcessIdentity.id).where(ProcessIdentity.process_id == process_id))
    return existing is not None


def _validate_process_ids(process_ids: WorkspaceProcessIds) -> dict[str, str]:
    values = {
        "app": _normalize_process_id(process_ids.app),
        "agent": _normalize_process_id(process_ids.agent),
        "supervisor": _normalize_process_id(process_ids.watch),
    }
    if len(set(values.values())) != len(values):
        raise HTTPException(status_code=409, detail="Duplicate process_id in workspace form.")
    for process_id in values.values():
        if not _is_valid_process_id(process_id):
            raise HTTPException(status_code=422, detail=f"Invalid process_id: {process_id}")
    return values


def _workspace_to_info(db: Session, workspace: Workspace) -> WorkspaceInfo:
    identities = db.scalars(
        select(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace.workspace_id)
    ).all()
    by_role = {item.role: item.process_id for item in identities}
    runtime = _workspace_runtime(db, workspace.workspace_id)
    return WorkspaceInfo(
        id=workspace.workspace_id,
        name=workspace.name,
        path=workspace.path,
        command=workspace.start_command,
        agent_command=workspace.agent_command,
        poll_seconds=workspace.poll_seconds,
        ai_can_edit=workspace.ai_can_edit,
        initial_prompt=workspace.initial_prompt,
        process_ids=WorkspaceProcessIds(
            app=by_role.get("app", ""),
            agent=by_role.get("agent", ""),
            watch=by_role.get("supervisor", ""),
        ),
        status=workspace.status,
        runtime=runtime,
        logs=_workspace_logs(db, workspace),
        runtime_status=_runtime_status_for_workspace(db, workspace),
    )


def _workspace_runtime(db: Session, workspace_id: str) -> str:
    row = db.scalars(
        select(ProcessRuntimeInstance)
        .where(ProcessRuntimeInstance.workspace_id == workspace_id)
        .where(ProcessRuntimeInstance.status.in_(["running", "starting", "delegated"]))
        .order_by(ProcessRuntimeInstance.started_at.asc())
    ).first()
    if row is None:
        row = db.scalars(
            select(ProcessRuntimeInstance)
            .where(ProcessRuntimeInstance.workspace_id == workspace_id)
            .order_by(ProcessRuntimeInstance.started_at.desc())
        ).first()
    if row is None or not isinstance(row.started_at, datetime):
        return "00:00:00"

    started_at = row.started_at.replace(tzinfo=None)
    end_at = row.stopped_at if isinstance(row.stopped_at, datetime) and row.status == "stopped" else _database_now(db)
    end_at = _normalize_runtime_end(started_at, end_at.replace(tzinfo=None))
    seconds = max(0, int((end_at - started_at).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _database_now(db: Session) -> datetime:
    value = db.scalar(select(func.now()))
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.now()


def _normalize_runtime_end(started_at: datetime, end_at: datetime) -> datetime:
    if end_at >= started_at:
        return end_at

    local_utc_offset = datetime.now() - datetime.utcnow()
    corrected = end_at + local_utc_offset
    if corrected >= started_at:
        return corrected
    return end_at


ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC_PATTERN = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)?")
TUI_PREFIX_PATTERN = re.compile(r"^\s*\d{1,4}\s+")


def _strip_terminal_noise(line: str) -> str:
    line = OSC_PATTERN.sub("", line)
    line = ANSI_PATTERN.sub("", line)
    line = line.replace("\x1b", "")
    line = "".join(char for char in line if char in "\t" or ord(char) >= 32)
    line = TUI_PREFIX_PATTERN.sub("", line)
    return line.strip()


def _clean_log_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    pending_chars: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_chars
        if pending_chars:
            text = "".join(pending_chars).strip()
            if text:
                cleaned.append(text)
            pending_chars = []

    for raw in lines:
        line = _strip_terminal_noise(raw)
        if not line:
            continue
        if len(line) <= 2 and not any(token in line for token in ("INFO", "DEBUG", "SUCCESS", "ERROR")):
            pending_chars.append(line)
            continue
        flush_pending()
        cleaned.append(line)
    flush_pending()
    return cleaned


def _level_from_log_line(line: str) -> str:
    upper = line.upper()
    for level in ("ERROR", "WARN", "WARNING", "DEBUG", "SUCCESS", "INFO"):
        if f" {level} " in upper or upper.startswith(f"{level} "):
            return "WARN" if level == "WARNING" else level
    return "INFO"


def _tail_file(path: Path, limit: int = 100) -> list[str]:
    return [line for _, line in _read_log_file_entries(path, limit)]


def _read_log_file_entries(path: Path, limit: int = 1000) -> list[tuple[int, str]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            raw_lines = file.readlines()
    except OSError:
        return []
    start_line = max(1, len(raw_lines) - limit + 1)
    entries: list[tuple[int, str]] = []
    for line_number, raw in enumerate(raw_lines[-limit:], start=start_line):
        cleaned = _strip_terminal_noise(raw.rstrip("\n"))
        if cleaned:
            entries.append((line_number, cleaned))
    return entries


def _parse_log_timestamp(line: str) -> datetime:
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\b", line)
    if not match:
        return datetime.now(timezone.utc)
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _runtime_log_sources(workspace: Workspace, role: str | None = None) -> list[tuple[str, str, Path]]:
    root = Path(workspace.path)
    log_dir = root / ".ai-code-monitor" / "logs"
    sources = [
        ("app", "stdout", log_dir / "app.out.log"),
        ("agent", "agent_log", log_dir / "agent.log"),
        ("agent", "stdout", log_dir / "agent.out.log"),
        ("agent", "stderr", log_dir / "agent.err.log"),
        ("supervisor", "monitor_log", log_dir / "monitor.log"),
        ("supervisor", "stdout", log_dir / "monitor.out.log"),
        ("supervisor", "stderr", log_dir / "monitor.err.log"),
    ]
    normalized = "supervisor" if role in {"watch", "monitor"} else role
    if normalized:
        return [item for item in sources if item[0] == normalized]
    return sources


def _runtime_log_hash(workspace_id: str, process_id: str, role: str, source: str, path: Path, line_number: int, content: str) -> str:
    raw = f"{workspace_id}\0{process_id}\0{role}\0{source}\0{path}\0{line_number}\0{content}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _sync_workspace_logs_to_db(db: Session, workspace: Workspace, role: str | None = None, limit: int = 5000) -> None:
    if not LOG_SYNC_LOCK.acquire(blocking=False):
        return
    try:
        _sync_workspace_logs_to_db_locked(db, workspace, role=role, limit=limit)
    finally:
        LOG_SYNC_LOCK.release()


def _sync_workspace_logs_to_db_locked(db: Session, workspace: Workspace, role: str | None = None, limit: int = 5000) -> None:
    process_ids = _process_ids_for_workspace(db, workspace.workspace_id)
    role_to_process_id = {
        "app": process_ids.app,
        "agent": process_ids.agent,
        "supervisor": process_ids.watch,
    }
    for source_role, source_type, path in _runtime_log_sources(workspace, role):
        process_id = role_to_process_id.get(source_role, "")
        if not process_id:
            continue
        for line_number, line in _read_log_file_entries(path, limit):
            content_hash = _runtime_log_hash(workspace.workspace_id, process_id, source_role, source_type, path, line_number, line)
            db.execute(
                text(
                    """
                    INSERT IGNORE INTO runtime_logs
                      (workspace_id, process_id, `role`, level, log_type, content, content_hash, occurred_at)
                    VALUES
                      (:workspace_id, :process_id, :role, :level, :log_type, :content, :content_hash, :occurred_at)
                    """
                ),
                {
                    "workspace_id": workspace.workspace_id,
                    "process_id": process_id,
                    "role": source_role,
                    "level": _level_from_log_line(line),
                    "log_type": source_type,
                    "content": line,
                    "content_hash": content_hash,
                    "occurred_at": _parse_log_timestamp(line),
                },
            )


def _archive_expired_runtime_logs(db: Session, limit: int = 10000) -> None:
    settings = _get_log_settings(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    rows = db.scalars(
        select(RuntimeLog)
        .where(RuntimeLog.occurred_at < cutoff)
        .order_by(RuntimeLog.occurred_at.asc(), RuntimeLog.log_id.asc())
        .limit(limit)
    ).all()
    if not rows:
        return

    workspace_paths = dict(db.execute(select(Workspace.workspace_id, Workspace.path)).all())
    grouped: dict[tuple[str, str, str, date, Path], list[RuntimeLog]] = {}
    for row in rows:
        occurred_at = row.occurred_at if isinstance(row.occurred_at, datetime) else cutoff
        archive_date = occurred_at.date()
        archive_root = settings.archive_root.strip()
        if archive_root:
            archive_dir = Path(archive_root).expanduser() / row.workspace_id / archive_date.isoformat()
        else:
            root = Path(workspace_paths.get(row.workspace_id, "")).expanduser()
            if root.exists():
                archive_dir = root / ".ai-code-monitor" / "logs" / "archive" / archive_date.isoformat()
            else:
                archive_dir = Path("data") / "log-archives" / row.workspace_id / archive_date.isoformat()
        filename = f"{row.role}_{row.process_id}.log.gz"
        archive_path = archive_dir / filename
        grouped.setdefault((row.workspace_id, row.process_id, row.role, archive_date, archive_path), []).append(row)

    archived_ids: list[int] = []
    for (workspace_id, process_id, role, archive_date, archive_path), group_rows in grouped.items():
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(archive_path, "at", encoding="utf-8") as file:
            for row in group_rows:
                occurred_at = row.occurred_at.isoformat() if isinstance(row.occurred_at, datetime) else str(row.occurred_at)
                file.write(f"{occurred_at} {row.level} {row.role} {row.process_id} {row.log_type} {row.content}\n")
                archived_ids.append(row.log_id)
        db.add(
            LogArchive(
                workspace_id=workspace_id,
                process_id=process_id,
                role=role,
                archive_date=archive_date,
                file_path=str(archive_path),
                line_count=len(group_rows),
                size_bytes=archive_path.stat().st_size if archive_path.exists() else 0,
            )
        )

    if archived_ids:
        db.execute(delete(RuntimeLog).where(RuntimeLog.log_id.in_(archived_ids)))


def _runtime_log_to_info(row: RuntimeLog) -> RuntimeLogInfo:
    occurred_at = row.occurred_at.isoformat() if isinstance(row.occurred_at, datetime) else str(row.occurred_at)
    created_at = row.created_at.isoformat() if isinstance(row.created_at, datetime) else str(row.created_at)
    return RuntimeLogInfo(
        log_id=row.log_id,
        workspace_id=row.workspace_id,
        process_id=row.process_id,
        role=row.role,
        level=row.level,
        log_type=row.log_type,
        content=row.content,
        occurred_at=occurred_at,
        created_at=created_at,
    )


def _workspace_logs(db: Session, workspace: Workspace, limit: int = 100) -> list[str]:
    settings = _get_log_settings(db)
    _sync_workspace_logs_to_db(db, workspace, limit=max(limit, 300, settings.sync_tail_lines))
    _archive_expired_runtime_logs(db)
    rows = db.scalars(
        select(RuntimeLog)
        .where(RuntimeLog.workspace_id == workspace.workspace_id)
        .order_by(RuntimeLog.occurred_at.desc(), RuntimeLog.log_id.desc())
        .limit(limit)
    ).all()
    if not rows:
        return ["--:--:-- workspace loaded from database"]
    return [row.content for row in reversed(rows)]


def _pid_status(pid: int | None) -> tuple[str, str | None]:
    if pid is None:
        return "unknown", None
    try:
        process = psutil.Process(pid)
        status = process.status()
        if status == psutil.STATUS_ZOMBIE:
            return "stopped", f"OS PID {pid}, zombie"
        return "running", f"OS PID {pid}, {status}"
    except psutil.NoSuchProcess:
        return "stopped", f"OS PID {pid} not found"
    except (psutil.AccessDenied, psutil.ZombieProcess):
        return "unknown", f"OS PID {pid} inaccessible"


def _runtime_status_for_workspace(db: Session, workspace: Workspace) -> dict[str, ProcessStatusInfo]:
    identities = db.scalars(
        select(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace.workspace_id)
    ).all()
    by_role = {item.role: item.process_id for item in identities}
    status: dict[str, ProcessStatusInfo] = {
        "app": ProcessStatusInfo(role="app", process_id=by_role.get("app", ""), status="idle"),
        "agent": ProcessStatusInfo(role="agent", process_id=by_role.get("agent", ""), status="idle"),
        "watch": ProcessStatusInfo(role="supervisor", process_id=by_role.get("supervisor", ""), status="idle"),
    }

    latest = db.scalars(
        select(ProcessRuntimeInstance)
        .where(ProcessRuntimeInstance.workspace_id == workspace.workspace_id)
        .order_by(ProcessRuntimeInstance.started_at.desc())
    ).all()
    role_key = {"supervisor": "watch", "agent": "agent", "app": "app"}
    for row in latest:
        key = role_key.get(row.role)
        if key is None or status[key].os_pid is not None:
            continue
        proc_status, detail = _pid_status(row.os_pid)
        status[key] = ProcessStatusInfo(
            role=row.role,
            process_id=row.process_id,
            os_pid=row.os_pid,
            status=proc_status if row.status in {"running", "starting", "delegated"} else row.status,
            detail=detail,
        )

    app_pid = _read_app_runtime_pid(workspace)
    if app_pid is not None:
        proc_status, detail = _pid_status(app_pid)
        status["app"] = ProcessStatusInfo(
            role="app",
            process_id=by_role.get("app", ""),
            os_pid=app_pid,
            status=proc_status,
            detail=detail,
        )
    return status


def _ensure_workspace_process_graph(
    db: Session,
    workspace_id: str,
    name: str,
    process_ids: WorkspaceProcessIds,
) -> None:
    values = _validate_process_ids(process_ids)
    display_names = {
        "app": f"{name} 启动脚本",
        "agent": f"{name} Agent",
        "supervisor": f"{name} 监督脚本",
    }

    for role, process_id in values.items():
        row = db.scalar(select(ProcessIdentity).where(ProcessIdentity.process_id == process_id))
        if row is None:
            db.add(
                ProcessIdentity(
                    process_id=process_id,
                    role=role,
                    workspace_id=workspace_id,
                    display_name=display_names[role],
                )
            )
        else:
            row.role = role
            row.workspace_id = workspace_id
            row.display_name = display_names[role]

    db.execute(delete(ProcessLink).where(ProcessLink.workspace_id == workspace_id))
    db.add_all(
        [
            ProcessLink(
                workspace_id=workspace_id,
                from_process_id=values["supervisor"],
                to_process_id=values["agent"],
                link_type="supervises",
            ),
            ProcessLink(
                workspace_id=workspace_id,
                from_process_id=values["agent"],
                to_process_id=values["app"],
                link_type="monitors",
            ),
        ]
    )


def _replace_workspace_process_graph(
    db: Session,
    workspace_id: str,
    name: str,
    process_ids: WorkspaceProcessIds,
) -> None:
    values = _validate_process_ids(process_ids)
    existing_for_workspace = db.scalars(
        select(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace_id)
    ).all()
    existing_by_role = {item.role: item for item in existing_for_workspace}

    for role, process_id in values.items():
        current = existing_by_role.get(role)
        if current and current.process_id == process_id:
            continue
        conflict = db.scalar(select(ProcessIdentity).where(ProcessIdentity.process_id == process_id))
        if conflict is not None and conflict.workspace_id != workspace_id:
            raise HTTPException(status_code=409, detail=f"process_id already exists: {process_id}")

    db.execute(delete(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace_id))
    _ensure_workspace_process_graph(db=db, workspace_id=workspace_id, name=name, process_ids=process_ids)


def _generate_default_process_id(db: Session, role: str, workspace_name: str | None) -> str:
    seed = f"{role}:{workspace_name or 'workspace'}:{os.urandom(16).hex()}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    candidate = f"{role}_{digest}"

    while _process_id_exists(db, candidate):
        digest = hashlib.sha1(os.urandom(16)).hexdigest()[:8]
        candidate = f"{role}_{digest}"

    return candidate


def _workspace_root(workspace: Workspace) -> Path:
    root = Path(workspace.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=422, detail=f"工作目录不存在或不是目录: {workspace.path}")
    return root


def _runtime_paths(root: Path) -> dict[str, Path]:
    base = root / ".ai-code-monitor"
    logs = base / "logs"
    bridge = base / "bridge"
    return {
        "base": base,
        "logs": logs,
        "bridge": bridge,
        "agent_stdin": bridge / "agent.stdin",
        "agent_pid": bridge / "agent.os_pid",
        "agent_heartbeat": bridge / "agent.heartbeat",
        "monitor_log": logs / "monitor.log",
        "agent_log": logs / "agent.log",
        "agent_out_log": logs / "agent.out.log",
        "agent_err_log": logs / "agent.err.log",
        "monitor_out_log": logs / "monitor.out.log",
        "monitor_err_log": logs / "monitor.err.log",
        "app_runtime": base / "app-runtime.json",
        "codex_home": base / "codex-home",
    }


def _process_ids_for_workspace(db: Session, workspace_id: str) -> WorkspaceProcessIds:
    identities = db.scalars(
        select(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace_id)
    ).all()
    by_role = {item.role: item.process_id for item in identities}
    return WorkspaceProcessIds(
        app=by_role.get("app", ""),
        agent=by_role.get("agent", ""),
        watch=by_role.get("supervisor", ""),
    )


def _prepare_runtime_files(root: Path) -> dict[str, Path]:
    paths = _runtime_paths(root)
    paths["logs"].mkdir(parents=True, exist_ok=True)
    paths["bridge"].mkdir(parents=True, exist_ok=True)
    agent_stdin = paths["agent_stdin"]
    if agent_stdin.exists() and not agent_stdin.is_fifo():
        agent_stdin.unlink()
    if not agent_stdin.exists():
        os.mkfifo(agent_stdin)
    return paths


def _is_codex_agent_command(workspace: Workspace) -> bool:
    command = workspace.agent_command.strip()
    return command == "codex" or command.startswith("codex ")


def _strip_mcp_servers_from_codex_config(content: str) -> str:
    kept: list[str] = []
    skipping = False
    for line in content.splitlines():
        section_match = re.match(r"\s*\[([^]]+)]\s*$", line)
        if section_match:
            section_name = section_match.group(1).strip()
            skipping = section_name == "mcp_servers" or section_name.startswith("mcp_servers.")
        if not skipping:
            kept.append(line)
    return "\n".join(kept).strip() + "\n"


def _prepare_codex_home(root: Path, workspace: Workspace, paths: dict[str, Path]) -> Path | None:
    if not _is_codex_agent_command(workspace):
        return None

    source_home = Path(os.getenv("CODEX_HOME", Path.home() / ".codex")).expanduser()
    target_home = paths["codex_home"]
    target_home.mkdir(parents=True, exist_ok=True)

    auth_source = source_home / "auth.json"
    if auth_source.exists():
        shutil.copy2(auth_source, target_home / "auth.json")

    install_source = source_home / "installation_id"
    if install_source.exists():
        shutil.copy2(install_source, target_home / "installation_id")

    source_config = source_home / "config.toml"
    if source_config.exists():
        config = _strip_mcp_servers_from_codex_config(source_config.read_text(encoding="utf-8"))
    else:
        config = ""
    trusted_project = f'[projects."{root}"]\ntrust_level = "trusted"\n'
    if f'[projects."{root}"]' not in config:
        config = config.rstrip() + "\n\n" + trusted_project
    (target_home / "config.toml").write_text(config, encoding="utf-8")
    return target_home


def _app_watchdog_source(workspace: Workspace, process_ids: WorkspaceProcessIds) -> str:
    return dedent(
        f'''
        from __future__ import annotations

        import json
        import os
        import subprocess
        import time
        from datetime import datetime
        from pathlib import Path


        ROOT = Path(__file__).resolve().parent
        MONITOR_DIR = ROOT / ".ai-code-monitor"
        LOG_DIR = MONITOR_DIR / "logs"
        BRIDGE_DIR = MONITOR_DIR / "bridge"
        APP_LOG = LOG_DIR / "app.out.log"
        AGENT_LOG = LOG_DIR / "agent.log"
        RUNTIME_FILE = MONITOR_DIR / "app-runtime.json"
        HEARTBEAT_FILE = BRIDGE_DIR / "agent.heartbeat"
        COMMAND = {json.dumps(workspace.start_command)}
        PROCESS_ID = {json.dumps(process_ids.app)}
        AGENT_PROCESS_ID = {json.dumps(process_ids.agent)}
        POLL_SECONDS = {max(1, int(workspace.poll_seconds))}


        COLORS = {{
            "ERROR": "\\033[31m",
            "DEBUG": "\\033[34m",
            "SUCCESS": "\\033[32m",
            "INFO": "\\033[37m",
        }}
        RESET = "\\033[0m"


        def now() -> str:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


        def log(level: str, message: str) -> None:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            level = level.upper()
            color = COLORS.get(level, COLORS["INFO"])
            with AGENT_LOG.open("a", encoding="utf-8") as file:
                file.write(f"{{color}}{{now()}} {{level}} {{message}}{{RESET}}\\n")


        def append_app_log(level: str, message: str) -> None:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            level = level.upper()
            color = COLORS.get(level, COLORS["INFO"])
            with APP_LOG.open("a", encoding="utf-8") as file:
                file.write(f"{{color}}{{now()}} {{level}} {{message}}{{RESET}}\\n")


        def pid_alive(pid: int) -> bool:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
            except OSError:
                return False
            return True


        def read_runtime() -> dict[str, object]:
            try:
                return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {{}}


        def write_runtime(pid: int, status: str) -> None:
            existing = read_runtime()
            started_at = existing.get("started_at") if existing.get("os_pid") == pid else now()
            payload = {{
                "process_id": PROCESS_ID,
                "agent_process_id": AGENT_PROCESS_ID,
                "os_pid": pid,
                "command": COMMAND,
                "status": status,
                "started_at": started_at,
                "updated_at": now(),
                "log_file": str(APP_LOG),
                "watchdog_pid": os.getpid(),
                "watchdog_status": "running",
            }}
            MONITOR_DIR.mkdir(parents=True, exist_ok=True)
            RUNTIME_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")


        def heartbeat() -> None:
            BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
            HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")


        def start_app() -> int:
            append_app_log("INFO", f"{{AGENT_PROCESS_ID}} launching app command: {{COMMAND}}")
            output = APP_LOG.open("ab", buffering=0)
            process = subprocess.Popen(
                COMMAND,
                cwd=str(ROOT),
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
            time.sleep(1)
            if pid_alive(process.pid):
                log("SUCCESS", f"应用进程已启动，OS PID: {{process.pid}}")
                write_runtime(process.pid, "running")
            else:
                log("ERROR", f"应用进程启动后不可达，OS PID: {{process.pid}}")
                write_runtime(process.pid, "exited")
            return process.pid


        def main() -> int:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log("INFO", f"watchdog 启动，轮询间隔: {{POLL_SECONDS}}s")

            runtime = read_runtime()
            current_pid = runtime.get("os_pid")
            if isinstance(current_pid, int) and pid_alive(current_pid):
                log("DEBUG", f"复用现有应用进程，OS PID: {{current_pid}}")
                write_runtime(current_pid, "running")
            else:
                if current_pid is not None:
                    log("ERROR", f"runtime 中的应用 PID 不可用: {{current_pid}}，准备重启。")
                current_pid = start_app()

            while True:
                heartbeat()
                runtime = read_runtime()
                runtime_pid = runtime.get("os_pid")
                if not isinstance(runtime_pid, int):
                    log("ERROR", "runtime 缺少有效 os_pid，准备重启应用。")
                    current_pid = start_app()
                elif pid_alive(runtime_pid):
                    current_pid = runtime_pid
                    write_runtime(current_pid, "running")
                    log("DEBUG", f"应用健康检查通过，OS PID: {{current_pid}}")
                else:
                    log("ERROR", f"应用进程已退出，OS PID: {{runtime_pid}}，准备重启。")
                    current_pid = start_app()
                time.sleep(POLL_SECONDS)


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    ).lstrip()


def _app_launcher_source() -> str:
    return dedent(
        r'''
        from __future__ import annotations

        import subprocess
        import sys
        from pathlib import Path


        ROOT = Path(__file__).resolve().parent
        LOG_DIR = ROOT / ".ai-code-monitor" / "logs"
        AGENT_LOG = LOG_DIR / "agent.log"
        WATCHDOG = ROOT / "app_watchdog.py"


        def main() -> int:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with AGENT_LOG.open("ab", buffering=0) as log_file:
                process = subprocess.Popen(
                    [sys.executable, str(WATCHDOG)],
                    cwd=str(ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
            print(f"app_watchdog started: {process.pid}", flush=True)
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    ).lstrip()


def _write_app_runtime_helpers(workspace: Workspace, db: Session) -> None:
    root = _workspace_root(workspace)
    process_ids = _process_ids_for_workspace(db, workspace.workspace_id)
    (root / "app_watchdog.py").write_text(_app_watchdog_source(workspace, process_ids), encoding="utf-8")
    (root / "app_launcher.py").write_text(_app_launcher_source(), encoding="utf-8")


def _build_initial_prompt(workspace: Workspace, process_ids: WorkspaceProcessIds, paths: dict[str, Path]) -> str:
    if workspace.ai_can_edit:
        custom_prompt = workspace.initial_prompt.strip()
        if custom_prompt:
            edit_policy = f"你在监控的过程中出现问题可以修改代码，{custom_prompt}"
        else:
            edit_policy = "你在监控的过程中出现问题可以修改代码。"
    else:
        edit_policy = "你在监控的过程中不能修改代码。"

    return (
        f"你是个智能脚本监控者，你开始监控【{workspace.name}】这里面的脚本，请你先阅读理解。"
        f"你的第一步必须立即在项目根目录执行【python app_launcher.py】，不要等待用户确认，不要只阅读文件。"
        f"app_launcher.py 会根据用户启动命令【{workspace.start_command}】后台启动项目，并写入 runtime。"
        f"进程id是【{process_ids.app}】，你开始不断监控，{edit_policy}\n"
        f"不要直接执行【{workspace.start_command}】，必须通过【python app_launcher.py】启动。"
        f"启动后请检查 {paths['base'] / 'app-runtime.json'} 是否写入真实 OS PID、启动命令和状态。"
        "并且，你要保留记录日志的习惯，不仅是代码内部记录日志，你自己的操作也要记录日志。"
        "日志格式为具体日期 + 日志等级 + 日志信息。日志等级使用 ERROR、DEBUG、SUCCESS、INFO；"
        "错误是红色，调试是蓝色，成功是绿色，普通是白色。\n"
        f"你的逻辑 process_id 是【{process_ids.agent}】，监督脚本 process_id 是【{process_ids.watch}】。"
        f"请把你的操作日志追加写入 {paths['agent_log']}，并定期更新心跳文件 {paths['agent_heartbeat']}。"
    )


def _agent_runtime_command(workspace: Workspace) -> str:
    command = workspace.agent_command.strip()
    if command == "codex":
        sandbox = "workspace-write" if workspace.ai_can_edit else "read-only"
        return f"codex --no-alt-screen -a never -s {sandbox}"
    return command


def _monitor_script_source() -> str:
    return dedent(
        r'''
        from __future__ import annotations

        import os
        import pty
        import json
        import shlex
        import signal
        import subprocess
        import time
        from datetime import datetime
        from pathlib import Path

        WORKSPACE_NAME = os.getenv("AICM_WORKSPACE_NAME", "workspace")
        POLL_SECONDS = max(1, int(os.getenv("AICM_POLL_SECONDS", "30")))
        AGENT_COMMAND = os.getenv("AICM_AGENT_COMMAND", "codex")
        AGENT_PID_FILE = Path(os.getenv("AICM_AGENT_PID_FILE", ".ai-code-monitor/bridge/agent.os_pid"))
        AGENT_HEARTBEAT = Path(os.getenv("AICM_AGENT_HEARTBEAT", ".ai-code-monitor/bridge/agent.heartbeat"))
        MONITOR_LOG = Path(os.getenv("AICM_MONITOR_LOG", ".ai-code-monitor/logs/monitor.log"))
        AGENT_OUT_LOG = Path(os.getenv("AICM_AGENT_OUT_LOG", ".ai-code-monitor/logs/agent.out.log"))
        APP_RUNTIME_FILE = Path(os.getenv("AICM_APP_RUNTIME_FILE", ".ai-code-monitor/app-runtime.json"))
        APP_LOG_FILE = Path(os.getenv("AICM_APP_LOG_FILE", ".ai-code-monitor/logs/app.out.log"))
        APP_STALE_SECONDS = max(POLL_SECONDS * 6, int(os.getenv("AICM_APP_STALE_SECONDS", "60")))
        INITIAL_PROMPT = os.getenv("AICM_INITIAL_PROMPT", "")
        RUNNING = True

        def log(level: str, message: str) -> None:
            MONITOR_LOG.parent.mkdir(parents=True, exist_ok=True)
            level = level.upper()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{now} {level} {message}"
            with MONITOR_LOG.open("a", encoding="utf-8") as file:
                file.write(f"{line}\n")


        def mark_heartbeat() -> None:
            AGENT_HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
            AGENT_HEARTBEAT.write_text(str(time.time()), encoding="utf-8")


        def append_agent_output(data: bytes) -> None:
            AGENT_OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
            try:
                with AGENT_OUT_LOG.open("ab") as file:
                    file.write(data)
            except OSError as exc:
                log("ERROR", f"写入 Agent 输出日志失败: {exc}")


        def is_codex_command() -> bool:
            command = AGENT_COMMAND.strip()
            return command == "codex" or command.startswith("codex ")


        def start_agent(initial_prompt: str = "") -> tuple[subprocess.Popen[bytes], int]:
            master_fd, slave_fd = pty.openpty()
            if is_codex_command() and initial_prompt:
                command = shlex.split(AGENT_COMMAND) + [initial_prompt]
                shell = False
            else:
                command = AGENT_COMMAND
                shell = True
            process = subprocess.Popen(
                command,
                cwd=str(Path.cwd()),
                shell=shell,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
            os.close(slave_fd)
            os.set_blocking(master_fd, False)
            AGENT_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            AGENT_PID_FILE.write_text(str(process.pid), encoding="utf-8")
            mark_heartbeat()
            log("SUCCESS", f"Agent 已通过 PTY 启动，OS PID: {process.pid}")
            return process, master_fd


        def drain_agent_output(master_fd: int) -> None:
            while True:
                try:
                    data = os.read(master_fd, 8192)
                except BlockingIOError:
                    return
                except OSError:
                    return
                if not data:
                    return
                append_agent_output(data)
                mark_heartbeat()


        def send_to_agent(master_fd: int, message: str) -> bool:
            try:
                os.write(master_fd, (message.rstrip() + "\r").encode("utf-8"))
            except OSError as exc:
                log("ERROR", f"发送提示词失败: {exc}")
                return False
            return True


        def heartbeat_stale() -> bool:
            try:
                modified_at = AGENT_HEARTBEAT.stat().st_mtime
            except OSError:
                return True
            return time.time() - modified_at > max(POLL_SECONDS * 2, 10)


        def app_issue() -> str | None:
            try:
                payload = json.loads(APP_RUNTIME_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return f"未找到或无法读取 App runtime 文件: {APP_RUNTIME_FILE}"

            os_pid = payload.get("os_pid")
            if not isinstance(os_pid, int):
                return f"App runtime 未记录有效 OS PID: {payload!r}"

            try:
                os.kill(os_pid, 0)
            except ProcessLookupError:
                return f"App OS PID {os_pid} 不存在，说明启动脚本已经停止。"
            except PermissionError:
                pass

            try:
                result = subprocess.run(
                    ["ps", "-p", str(os_pid), "-o", "stat="],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip().startswith("Z"):
                    return f"App OS PID {os_pid} 是 zombie 进程，说明启动脚本已经退出但未被正确回收。"
            except Exception as exc:
                log("DEBUG", f"检查 App 进程状态失败: {exc}")

            try:
                age = time.time() - APP_LOG_FILE.stat().st_mtime
            except OSError:
                return f"App 日志文件不存在: {APP_LOG_FILE}"
            if age > APP_STALE_SECONDS:
                return f"App 日志超过 {int(age)} 秒没有更新，可能已经停止或卡死。"
            return None

        def handle_stop(_signum: int, _frame: object) -> None:
            global RUNNING
            RUNNING = False


        def main() -> None:
            signal.signal(signal.SIGINT, handle_stop)
            signal.signal(signal.SIGTERM, handle_stop)
            log("INFO", f"监督脚本启动，工作区: {WORKSPACE_NAME}，轮询间隔: {POLL_SECONDS}s")
            agent_process, master_fd = start_agent(INITIAL_PROMPT)
            time.sleep(1.2)
            drain_agent_output(master_fd)
            if is_codex_command():
                log("SUCCESS", f"初始化提示词已作为启动参数交给 Agent，OS PID: {agent_process.pid}")
            elif send_to_agent(master_fd, INITIAL_PROMPT):
                log("SUCCESS", f"初始化提示词已发送给 Agent，OS PID: {agent_process.pid}")

            next_poll_at = time.time() + POLL_SECONDS
            while RUNNING:
                drain_agent_output(master_fd)

                if agent_process.poll() is not None:
                    log("ERROR", f"Agent 进程已退出，退出码: {agent_process.returncode}，准备重启。")
                    try:
                        os.close(master_fd)
                    except OSError:
                        pass
                    agent_process, master_fd = start_agent(INITIAL_PROMPT)
                    time.sleep(1.2)
                    drain_agent_output(master_fd)
                    if is_codex_command():
                        log("SUCCESS", f"初始化提示词已作为重启参数交给 Agent，OS PID: {agent_process.pid}")
                    else:
                        send_to_agent(master_fd, INITIAL_PROMPT)
                    next_poll_at = time.time() + POLL_SECONDS

                if time.time() >= next_poll_at:
                    issue = app_issue()
                    if issue:
                        prompt = (
                            "继续\n"
                            f"检测到 App 运行异常：{issue}\n"
                            "请立即检查启动脚本是否真实运行。如果没有运行，请重新执行启动命令，"
                            "把新的 OS PID 写入 app-runtime.json，并把输出继续追加到 app.out.log。"
                        )
                        if send_to_agent(master_fd, prompt):
                            log("ERROR", f"检测到 App 异常，已提示 Agent 修复: {issue}")
                    elif heartbeat_stale() and send_to_agent(master_fd, "继续"):
                        log("INFO", "Agent 心跳过期，已发送提示词: 继续")
                    elif not heartbeat_stale():
                        log("DEBUG", "Agent 心跳正常。")
                    next_poll_at = time.time() + POLL_SECONDS

                time.sleep(0.25)

            log("INFO", "监督脚本正在停止 Agent。")
            try:
                agent_process.terminate()
            except OSError:
                pass
            try:
                os.close(master_fd)
            except OSError:
                pass


        if __name__ == "__main__":
            try:
                main()
            except KeyboardInterrupt:
                log("INFO", "监督脚本收到停止信号。")
        '''
    ).lstrip()


def _write_monitor_script(workspace: Workspace, db: Session) -> Path:
    root = _workspace_root(workspace)
    paths = _prepare_runtime_files(root)
    process_ids = _process_ids_for_workspace(db, workspace.workspace_id)
    initial_prompt = _build_initial_prompt(workspace, process_ids, paths)
    script_path = root / "monitor.py"
    script_path.write_text(_monitor_script_source(), encoding="utf-8")
    (paths["base"] / "workspace-config.json").write_text(
        json.dumps(
            {
                "workspace_id": workspace.workspace_id,
                "name": workspace.name,
                "path": str(root),
                "start_command": workspace.start_command,
                "agent_command": workspace.agent_command,
                "poll_seconds": workspace.poll_seconds,
                "ai_can_edit": workspace.ai_can_edit,
                "process_ids": process_ids.model_dump(),
                "initial_prompt": initial_prompt,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return script_path


def _pid_create_time(pid: int) -> str | None:
    try:
        return str(psutil.Process(pid).create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _read_pid_file(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_app_runtime_pid(workspace: Workspace) -> int | None:
    runtime_path = Path(workspace.path) / ".ai-code-monitor" / "app-runtime.json"
    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    os_pid = payload.get("os_pid")
    if isinstance(os_pid, int):
        return os_pid
    if isinstance(os_pid, str) and os_pid.isdigit():
        return int(os_pid)
    return None


def _read_app_runtime_payload(workspace: Workspace) -> dict[str, object]:
    runtime_path = Path(workspace.path) / ".ai-code-monitor" / "app-runtime.json"
    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _terminate_workspace_app_processes(workspace: Workspace) -> None:
    root = Path(workspace.path).expanduser().resolve()
    runtime_payload = _read_app_runtime_payload(workspace)
    app_pid = runtime_payload.get("os_pid")
    if isinstance(app_pid, str) and app_pid.isdigit():
        app_pid = int(app_pid)
    watchdog_pid = runtime_payload.get("watchdog_pid")
    if isinstance(watchdog_pid, str) and watchdog_pid.isdigit():
        watchdog_pid = int(watchdog_pid)
    if app_pid is not None:
        _terminate_pid_tree(app_pid if isinstance(app_pid, int) else None)
    if watchdog_pid is not None:
        _terminate_pid_tree(watchdog_pid if isinstance(watchdog_pid, int) else None)

    command_tokens = set(workspace.start_command.split())
    for process in psutil.process_iter(attrs=["pid", "cmdline", "cwd"]):
        try:
            cwd = process.info.get("cwd")
            cmdline = process.info.get("cmdline") or []
            if not cwd or Path(cwd).expanduser().resolve() != root:
                continue
            command_matches = command_tokens and command_tokens.issubset(set(cmdline))
            watchdog_matches = any("app_watchdog.py" in token for token in cmdline)
            if not command_matches and not watchdog_matches:
                continue
            _terminate_pid_tree(process.pid)
        except (OSError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def _record_runtime(
    db: Session,
    *,
    workspace_id: str,
    process_id: str,
    role: str,
    os_pid: int | None,
    command: str | None,
    cwd: Path,
    status: str,
    stdin_channel: Path | None = None,
    stdout_log: Path | None = None,
    stderr_log: Path | None = None,
) -> ProcessRuntimeInstance:
    row = ProcessRuntimeInstance(
        process_id=process_id,
        workspace_id=workspace_id,
        role=role,
        os_pid=os_pid,
        pid_create_time=_pid_create_time(os_pid) if os_pid is not None else None,
        command=command,
        cwd=str(cwd),
        status=status,
        stdin_channel=str(stdin_channel) if stdin_channel else None,
        stdout_log=str(stdout_log) if stdout_log else None,
        stderr_log=str(stderr_log) if stderr_log else None,
        heartbeat_at=func.now(),
    )
    db.add(row)
    return row


def _start_workspace_processes(db: Session, workspace: Workspace) -> None:
    if workspace.status == "running":
        raise HTTPException(status_code=409, detail="工作区已经在运行。")

    root = _workspace_root(workspace)
    paths = _prepare_runtime_files(root)
    process_ids = _process_ids_for_workspace(db, workspace.workspace_id)
    if not all([process_ids.app, process_ids.agent, process_ids.watch]):
        raise HTTPException(status_code=422, detail="工作区 process_id 关系不完整。")

    codex_home = _prepare_codex_home(root, workspace, paths)
    _write_app_runtime_helpers(workspace, db)
    _write_monitor_script(workspace, db)
    paths["agent_pid"].write_text("", encoding="utf-8")
    try:
        paths["app_runtime"].unlink()
    except FileNotFoundError:
        pass

    initial_prompt = json.loads((paths["base"] / "workspace-config.json").read_text(encoding="utf-8"))["initial_prompt"]
    monitor_env = {
        **os.environ,
        "AICM_WORKSPACE_NAME": workspace.name,
        "AICM_POLL_SECONDS": str(workspace.poll_seconds),
        "AICM_AGENT_COMMAND": _agent_runtime_command(workspace),
        "AICM_AGENT_PID_FILE": str(paths["agent_pid"]),
        "AICM_AGENT_STDIN": str(paths["agent_stdin"]),
        "AICM_AGENT_HEARTBEAT": str(paths["agent_heartbeat"]),
        "AICM_MONITOR_LOG": str(paths["monitor_log"]),
        "AICM_AGENT_OUT_LOG": str(paths["agent_out_log"]),
        "AICM_APP_RUNTIME_FILE": str(paths["base"] / "app-runtime.json"),
        "AICM_APP_LOG_FILE": str(paths["logs"] / "app.out.log"),
        "AICM_INITIAL_PROMPT": initial_prompt,
    }
    if codex_home is not None:
        monitor_env["CODEX_HOME"] = str(codex_home)

    monitor_out = paths["monitor_out_log"].open("ab")
    monitor_err = paths["monitor_err_log"].open("ab")
    try:
        monitor_process = subprocess.Popen(
            [sys.executable, "monitor.py"],
            cwd=str(root),
            stdout=monitor_out,
            stderr=monitor_err,
            env=monitor_env,
            start_new_session=True,
        )
    finally:
        monitor_out.close()
        monitor_err.close()

    agent_os_pid = None
    for _ in range(50):
        agent_os_pid = _read_pid_file(paths["agent_pid"])
        if agent_os_pid is not None:
            break
        if monitor_process.poll() is not None:
            raise HTTPException(status_code=500, detail="监督脚本启动后立即退出，Agent 未启动。")
        time.sleep(0.1)
    if agent_os_pid is None:
        _terminate_pid_tree(monitor_process.pid)
        raise HTTPException(status_code=500, detail="监督脚本未在 5 秒内写出 Agent PID。")

    _record_runtime(
        db,
        workspace_id=workspace.workspace_id,
        process_id=process_ids.watch,
        role="supervisor",
        os_pid=monitor_process.pid,
        command=f"{sys.executable} monitor.py",
        cwd=root,
        status="running",
        stdout_log=paths["monitor_out_log"],
        stderr_log=paths["monitor_err_log"],
    )
    _record_runtime(
        db,
        workspace_id=workspace.workspace_id,
        process_id=process_ids.agent,
        role="agent",
        os_pid=agent_os_pid,
        command=_agent_runtime_command(workspace),
        cwd=root,
        status="running",
        stdin_channel=paths["agent_stdin"],
        stdout_log=paths["agent_out_log"],
        stderr_log=paths["agent_err_log"],
    )
    _record_runtime(
        db,
        workspace_id=workspace.workspace_id,
        process_id=process_ids.app,
        role="app",
        os_pid=None,
        command=workspace.start_command,
        cwd=root,
        status="delegated",
    )
    workspace.status = "running"


def _terminate_pid_tree(pid: int | None) -> None:
    if pid is None:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            process = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return
        children = process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        gone, alive = psutil.wait_procs(children + [process], timeout=3)
        for item in alive:
            try:
                item.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return

    try:
        process = psutil.Process(pid)
        _, alive = psutil.wait_procs([process], timeout=3)
        for item in alive:
            item.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass


def _stop_workspace_processes(db: Session, workspace_id: str, next_status: str = "paused") -> None:
    workspace = db.scalar(select(Workspace).where(Workspace.workspace_id == workspace_id))
    if workspace is not None:
        _terminate_workspace_app_processes(workspace)

    rows = db.scalars(
        select(ProcessRuntimeInstance)
        .where(ProcessRuntimeInstance.workspace_id == workspace_id)
        .where(ProcessRuntimeInstance.status.in_(["running", "starting", "delegated"]))
        .order_by(ProcessRuntimeInstance.started_at.desc())
    ).all()

    for row in rows:
        if row.os_pid is not None:
            _terminate_pid_tree(row.os_pid)
        row.status = "stopped"
        row.stopped_at = func.now()

    if workspace is not None:
        _terminate_workspace_app_processes(workspace)
        workspace.status = next_status


def _safe_process_info(process: psutil.Process) -> ProcessInfo | None:
    try:
        info = process.as_dict(attrs=["pid", "name", "status", "username", "cmdline"])
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

    cmdline = info.get("cmdline") or []
    return ProcessInfo(
        pid=info["pid"],
        name=info.get("name"),
        status=info.get("status"),
        username=info.get("username"),
        command=" ".join(cmdline) if cmdline else None,
    )


def _occupied_processes() -> tuple[set[int], list[ProcessInfo]]:
    occupied: set[int] = set()
    sample: list[ProcessInfo] = []

    for process in psutil.process_iter(attrs=["pid", "name", "status", "username", "cmdline"]):
        try:
            occupied.add(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

        if len(sample) < 80:
            process_info = _safe_process_info(process)
            if process_info is not None:
                sample.append(process_info)

    sample.sort(key=lambda item: item.pid)
    return occupied, sample


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/system/select-directory", response_model=DirectorySelectionResponse)
def select_directory() -> DirectorySelectionResponse:
    if platform.system() != "Darwin":
        raise HTTPException(status_code=501, detail="Directory picker is currently implemented for macOS only.")

    script = (
        'try\n'
        '  set selectedFolder to choose folder with prompt "选择工作目录"\n'
        '  POSIX path of selectedFolder\n'
        'on error number -128\n'
        '  "CANCELLED"\n'
        'end try'
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return DirectorySelectionResponse(selected=False, message="目录选择超时。")

    output = result.stdout.strip()
    if output == "CANCELLED":
        return DirectorySelectionResponse(selected=False, message="用户取消选择。")
    if result.returncode != 0:
        message = result.stderr.strip() or "目录选择失败。"
        raise HTTPException(status_code=500, detail=message)

    return DirectorySelectionResponse(selected=True, path=output)


@app.get("/api/settings/logs", response_model=LogSettingsInfo)
def get_log_settings(db: Session = Depends(get_db)) -> LogSettingsInfo:
    if not _database_available(db):
        defaults = _default_log_settings()
        return LogSettingsInfo(
            **defaults.model_dump(),
            storage_available=False,
            warning="MySQL is not available. Log settings are using environment defaults.",
        )
    row = _get_log_settings(db)
    db.commit()
    return _log_settings_to_info(row)


@app.put("/api/settings/logs", response_model=LogSettingsInfo)
def update_log_settings(payload: LogSettingsPayload, db: Session = Depends(get_db)) -> LogSettingsInfo:
    if not _database_available(db):
        raise HTTPException(status_code=503, detail="MySQL is not available.")

    archive_root = payload.archive_root.strip()
    if archive_root:
        archive_path = Path(archive_root).expanduser()
        if archive_path.exists() and not archive_path.is_dir():
            raise HTTPException(status_code=422, detail="日志归档路径必须是目录。")
        try:
            archive_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"日志归档路径不可用: {exc}") from exc
        archive_root = str(archive_path)

    row = _get_log_settings(db)
    row.archive_root = archive_root
    row.retention_days = payload.retention_days
    row.default_log_limit = payload.default_log_limit
    row.sync_tail_lines = payload.sync_tail_lines
    db.commit()
    db.refresh(row)
    return _log_settings_to_info(row)


@app.get("/api/workspaces", response_model=WorkspaceListResponse)
def list_workspaces(db: Session = Depends(get_db)) -> WorkspaceListResponse:
    if not _database_available(db):
        return WorkspaceListResponse(
            storage_available=False,
            items=[],
            warning="MySQL is not available. Workspaces cannot be loaded.",
        )

    rows = db.scalars(select(Workspace).order_by(Workspace.created_at.desc())).all()
    items = [_workspace_to_info(db, row) for row in rows]
    db.commit()
    return WorkspaceListResponse(
        storage_available=True,
        items=items,
    )


@app.post("/api/workspaces", response_model=WorkspaceInfo)
def create_workspace(payload: WorkspacePayload, db: Session = Depends(get_db)) -> WorkspaceInfo:
    if not _database_available(db):
        raise HTTPException(status_code=503, detail="MySQL is not available.")

    workspace_id = payload.id.strip()
    if not _is_valid_process_id(workspace_id):
        raise HTTPException(status_code=422, detail="workspace_id must use 3-80 letters, numbers, underscores, or hyphens.")
    if db.scalar(select(Workspace).where(Workspace.workspace_id == workspace_id)) is not None:
        raise HTTPException(status_code=409, detail=f"workspace_id already exists: {workspace_id}")

    values = _validate_process_ids(payload.process_ids)
    for process_id in values.values():
        if _process_id_exists(db, process_id):
            raise HTTPException(status_code=409, detail=f"process_id already exists: {process_id}")

    workspace = Workspace(
        workspace_id=workspace_id,
        name=payload.name,
        path=payload.path,
        start_command=payload.command,
        agent_command=payload.agent_command,
        poll_seconds=payload.poll_seconds,
        ai_can_edit=payload.ai_can_edit,
        initial_prompt=payload.initial_prompt,
        status="idle",
    )
    db.add(workspace)
    _ensure_workspace_process_graph(
        db=db,
        workspace_id=workspace_id,
        name=payload.name,
        process_ids=payload.process_ids,
    )
    db.flush()
    _write_monitor_script(workspace, db)
    db.commit()
    db.refresh(workspace)
    return _workspace_to_info(db, workspace)


@app.put("/api/workspaces/{workspace_id}", response_model=WorkspaceInfo)
def update_workspace(
    workspace_id: str,
    payload: WorkspacePayload,
    db: Session = Depends(get_db),
) -> WorkspaceInfo:
    if not _database_available(db):
        raise HTTPException(status_code=503, detail="MySQL is not available.")

    workspace = db.scalar(select(Workspace).where(Workspace.workspace_id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"workspace not found: {workspace_id}")
    if payload.id != workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id cannot be changed.")
    if workspace.status == "running":
        raise HTTPException(status_code=409, detail="工作区运行中不能编辑，请先停止。")

    workspace.name = payload.name
    workspace.path = payload.path
    workspace.start_command = payload.command
    workspace.agent_command = payload.agent_command
    workspace.poll_seconds = payload.poll_seconds
    workspace.ai_can_edit = payload.ai_can_edit
    workspace.initial_prompt = payload.initial_prompt
    _replace_workspace_process_graph(
        db=db,
        workspace_id=workspace_id,
        name=payload.name,
        process_ids=payload.process_ids,
    )
    db.flush()
    _write_monitor_script(workspace, db)
    db.commit()
    db.refresh(workspace)
    return _workspace_to_info(db, workspace)


@app.post("/api/workspaces/{workspace_id}/start", response_model=WorkspaceInfo)
def start_workspace(workspace_id: str, db: Session = Depends(get_db)) -> WorkspaceInfo:
    if not _database_available(db):
        raise HTTPException(status_code=503, detail="MySQL is not available.")

    workspace = db.scalar(select(Workspace).where(Workspace.workspace_id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"workspace not found: {workspace_id}")

    _start_workspace_processes(db, workspace)
    db.commit()
    db.refresh(workspace)
    return _workspace_to_info(db, workspace)


@app.post("/api/workspaces/{workspace_id}/stop", response_model=WorkspaceInfo)
def stop_workspace(workspace_id: str, db: Session = Depends(get_db)) -> WorkspaceInfo:
    if not _database_available(db):
        raise HTTPException(status_code=503, detail="MySQL is not available.")

    workspace = db.scalar(select(Workspace).where(Workspace.workspace_id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"workspace not found: {workspace_id}")

    _stop_workspace_processes(db, workspace_id, next_status="paused")
    db.commit()
    db.refresh(workspace)
    return _workspace_to_info(db, workspace)


@app.delete("/api/workspaces/{workspace_id}", response_model=WorkspaceDeleteResponse)
def delete_workspace(workspace_id: str, db: Session = Depends(get_db)) -> WorkspaceDeleteResponse:
    if not _database_available(db):
        return WorkspaceDeleteResponse(
            storage_available=False,
            workspace_id=workspace_id,
            deleted_process_ids=0,
            deleted_links=0,
            deleted_runtime_instances=0,
            deleted_workspaces=0,
            warning="MySQL is not available. Workspace was not deleted.",
        )

    _stop_workspace_processes(db, workspace_id, next_status="paused")
    db.execute(delete(RuntimeLog).where(RuntimeLog.workspace_id == workspace_id))
    db.execute(delete(LogArchive).where(LogArchive.workspace_id == workspace_id))
    runtime_result = db.execute(delete(ProcessRuntimeInstance).where(ProcessRuntimeInstance.workspace_id == workspace_id))
    link_result = db.execute(delete(ProcessLink).where(ProcessLink.workspace_id == workspace_id))
    identity_result = db.execute(delete(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace_id))
    workspace_result = db.execute(delete(Workspace).where(Workspace.workspace_id == workspace_id))
    db.commit()
    return WorkspaceDeleteResponse(
        storage_available=True,
        workspace_id=workspace_id,
        deleted_process_ids=identity_result.rowcount or 0,
        deleted_links=link_result.rowcount or 0,
        deleted_runtime_instances=runtime_result.rowcount or 0,
        deleted_workspaces=workspace_result.rowcount or 0,
    )


@app.get("/api/workspaces/{workspace_id}/process-graph", response_model=WorkspaceProcessGraphResponse)
def get_workspace_process_graph(
    workspace_id: str,
    db: Session = Depends(get_db),
) -> WorkspaceProcessGraphResponse:
    if not _database_available(db):
        return WorkspaceProcessGraphResponse(
            storage_available=False,
            workspace_id=workspace_id,
            identities=[],
            links=[],
            runtime_instances=[],
            warning="MySQL is not available. Process graph cannot be loaded.",
        )

    identities = db.scalars(
        select(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace_id)
    ).all()
    links = db.scalars(
        select(ProcessLink).where(ProcessLink.workspace_id == workspace_id)
    ).all()
    runtime_instances = db.scalars(
        select(ProcessRuntimeInstance)
        .where(ProcessRuntimeInstance.workspace_id == workspace_id)
        .order_by(ProcessRuntimeInstance.started_at.desc())
        .limit(20)
    ).all()
    return WorkspaceProcessGraphResponse(
        storage_available=True,
        workspace_id=workspace_id,
        identities=[
            ProcessIdentityInfo(
                process_id=item.process_id,
                role=item.role,
                workspace_id=item.workspace_id,
                display_name=item.display_name,
            )
            for item in identities
        ],
        links=[
            ProcessLinkInfo(
                from_process_id=item.from_process_id,
                to_process_id=item.to_process_id,
                link_type=item.link_type,
            )
            for item in links
        ],
        runtime_instances=[
            ProcessRuntimeInfo(
                runtime_id=item.runtime_id,
                process_id=item.process_id,
                role=item.role,
                os_pid=item.os_pid,
                status=item.status,
                stdin_channel=item.stdin_channel,
                stdout_log=item.stdout_log,
                stderr_log=item.stderr_log,
            )
            for item in runtime_instances
        ],
    )


@app.get("/api/workspaces/{workspace_id}/process-logs", response_model=RuntimeLogListResponse)
def get_workspace_process_logs(
    workspace_id: str,
    role: Annotated[str | None, Query(pattern="^(app|agent|watch|monitor|supervisor)$")] = None,
    process_id: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    db: Session = Depends(get_db),
) -> RuntimeLogListResponse:
    if not _database_available(db):
        return RuntimeLogListResponse(
            storage_available=False,
            items=[],
            warning="MySQL is not available. Logs cannot be loaded.",
        )

    workspace = db.scalar(select(Workspace).where(Workspace.workspace_id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"workspace not found: {workspace_id}")

    normalized_role = "supervisor" if role in {"watch", "monitor"} else role
    settings = _get_log_settings(db)
    _sync_workspace_logs_to_db(db, workspace, role=normalized_role, limit=max(limit, settings.sync_tail_lines))
    _archive_expired_runtime_logs(db)

    query = select(RuntimeLog).where(RuntimeLog.workspace_id == workspace_id)
    if normalized_role:
        query = query.where(RuntimeLog.role == normalized_role)
    if process_id:
        query = query.where(RuntimeLog.process_id == process_id)
    if level:
        levels = [item.strip().upper() for item in level.split(",") if item.strip()]
        if levels:
            query = query.where(RuntimeLog.level.in_(levels))
    if keyword:
        query = query.where(RuntimeLog.content.like(f"%{keyword.strip()}%"))
    if start:
        query = query.where(RuntimeLog.occurred_at >= start)
    if end:
        query = query.where(RuntimeLog.occurred_at <= end)

    rows = db.scalars(
        query.order_by(RuntimeLog.occurred_at.desc(), RuntimeLog.log_id.desc()).limit(limit)
    ).all()
    db.commit()
    return RuntimeLogListResponse(
        storage_available=True,
        items=[_runtime_log_to_info(row) for row in reversed(rows)],
    )


@app.get("/api/process-ids/defaults", response_model=ProcessIdDefaultsResponse)
def get_process_id_defaults(
    workspace_name: str | None = None,
    db: Session = Depends(get_db),
) -> ProcessIdDefaultsResponse:
    if not _database_available(db):
        return ProcessIdDefaultsResponse(
            app_process_id="app_default",
            agent_process_id="agent_default",
            supervisor_process_id="watch_default",
            storage_available=False,
            warning="MySQL is not available. Start MySQL and set CODE_MONITOR_DATABASE_URL if needed.",
        )

    return ProcessIdDefaultsResponse(
        app_process_id=_generate_default_process_id(db, "app", workspace_name),
        agent_process_id=_generate_default_process_id(db, "agent", workspace_name),
        supervisor_process_id=_generate_default_process_id(db, "watch", workspace_name),
        storage_available=True,
    )


@app.get("/api/process-ids/check", response_model=ProcessIdAvailabilityResponse)
def check_process_id(
    process_id: Annotated[str, Query(min_length=1, max_length=128)],
    db: Session = Depends(get_db),
) -> ProcessIdAvailabilityResponse:
    normalized = _normalize_process_id(process_id)

    if not _is_valid_process_id(normalized):
        return ProcessIdAvailabilityResponse(
            process_id=normalized,
            available=False,
            reason="只能使用 3-80 位英文、数字、下划线或中划线。",
            storage_available=True,
        )

    if not _database_available(db):
        return ProcessIdAvailabilityResponse(
            process_id=normalized,
            available=False,
            reason="MySQL 不可用，暂时无法确认是否重复。",
            storage_available=False,
        )

    if _process_id_exists(db, normalized):
        return ProcessIdAvailabilityResponse(
            process_id=normalized,
            available=False,
            reason="该 process_id 已被占用。",
            storage_available=True,
        )

    return ProcessIdAvailabilityResponse(
        process_id=normalized,
        available=True,
        reason="该 process_id 当前可用。",
        storage_available=True,
    )


@app.get("/api/process-ids", response_model=ProcessIdentityListResponse)
def list_process_ids(db: Session = Depends(get_db)) -> ProcessIdentityListResponse:
    if not _database_available(db):
        return ProcessIdentityListResponse(
            storage_available=False,
            items=[],
            warning="MySQL is not available. Start MySQL and set CODE_MONITOR_DATABASE_URL if needed.",
        )

    rows = db.scalars(select(ProcessIdentity).order_by(ProcessIdentity.created_at.desc()).limit(80)).all()
    return ProcessIdentityListResponse(
        storage_available=True,
        items=[
            ProcessIdentityInfo(
                process_id=row.process_id,
                role=row.role,
                workspace_id=row.workspace_id,
                display_name=row.display_name,
            )
            for row in rows
        ],
    )


@app.post("/api/process-ids", response_model=ProcessIdentityCreateResponse)
def create_process_ids(
    payload: list[ProcessIdentityCreate],
    db: Session = Depends(get_db),
) -> ProcessIdentityCreateResponse:
    if not _database_available(db):
        return ProcessIdentityCreateResponse(
            storage_available=False,
            created=[],
            warning="MySQL is not available. Start MySQL and set CODE_MONITOR_DATABASE_URL if needed.",
        )

    normalized_rows: list[ProcessIdentityCreate] = []
    seen: set[str] = set()
    for item in payload:
        process_id = _normalize_process_id(item.process_id)
        if not _is_valid_process_id(process_id):
            raise HTTPException(status_code=422, detail=f"Invalid process_id: {process_id}")
        if process_id in seen:
            raise HTTPException(status_code=409, detail=f"Duplicate process_id in request: {process_id}")
        if _process_id_exists(db, process_id):
            raise HTTPException(status_code=409, detail=f"process_id already exists: {process_id}")
        seen.add(process_id)
        normalized_rows.append(
            ProcessIdentityCreate(
                process_id=process_id,
                role=item.role,
                workspace_id=item.workspace_id,
                display_name=item.display_name,
            )
        )

    created: list[ProcessIdentityInfo] = []
    for item in normalized_rows:
        row = ProcessIdentity(
            process_id=item.process_id,
            role=item.role,
            workspace_id=item.workspace_id,
            display_name=item.display_name,
        )
        db.add(row)
        created.append(
            ProcessIdentityInfo(
                process_id=item.process_id,
                role=item.role,
                workspace_id=item.workspace_id,
                display_name=item.display_name,
            )
        )

    db.commit()
    return ProcessIdentityCreateResponse(storage_available=True, created=created)


@app.delete("/api/workspaces/{workspace_id}/process-ids", response_model=ProcessIdentityDeleteResponse)
def delete_workspace_process_ids(
    workspace_id: str,
    db: Session = Depends(get_db),
) -> ProcessIdentityDeleteResponse:
    if not _database_available(db):
        return ProcessIdentityDeleteResponse(
            storage_available=False,
            workspace_id=workspace_id,
            deleted_count=0,
            warning="MySQL is not available. Process IDs were not released.",
        )

    result = db.execute(delete(ProcessIdentity).where(ProcessIdentity.workspace_id == workspace_id))
    db.commit()
    return ProcessIdentityDeleteResponse(
        storage_available=True,
        workspace_id=workspace_id,
        deleted_count=result.rowcount or 0,
    )


@app.get("/api/processes/os-pids/availability", response_model=OsPidAvailabilityResponse)
def get_os_pid_availability(
    start: Annotated[int, Query(ge=1, le=999_999)] = 100,
    end: Annotated[int, Query(ge=1, le=999_999)] = 65_535,
    limit: Annotated[int, Query(ge=1, le=500)] = 120,
) -> OsPidAvailabilityResponse:
    if start > end:
        start, end = end, start

    occupied, occupied_sample = _occupied_processes()
    available_pids: list[int] = []

    for pid in range(start, end + 1):
        if pid not in occupied:
            available_pids.append(pid)
            if len(available_pids) >= limit:
                break

    return OsPidAvailabilityResponse(
        current_pid=os.getpid(),
        scanned_min_pid=start,
        scanned_max_pid=end,
        occupied_count=len(occupied),
        available_count=len(available_pids),
        available_pids=available_pids,
        occupied_sample=occupied_sample,
        warning=(
            "These PIDs are only free at the moment of scanning. "
            "The OS may allocate them to another process later, and a normal app cannot reserve a specific OS PID."
        ),
    )
