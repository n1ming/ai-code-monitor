from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from typing import Annotated

import psutil
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from sqlalchemy import DateTime, String, UniqueConstraint, create_engine, func, select
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


class ProcessIdentityListResponse(BaseModel):
    storage_available: bool
    items: list[ProcessIdentityInfo]
    warning: str | None = None


class DirectorySelectionResponse(BaseModel):
    selected: bool
    path: str | None = None
    message: str | None = None


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


MYSQL_URL = os.getenv(
    "CODE_MONITOR_DATABASE_URL",
    "mysql+pymysql://root:root@127.0.0.1:3306/code_monitor?charset=utf8mb4",
)

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
        _seed_demo_process_ids()
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


def _seed_demo_process_ids() -> None:
    demo_rows = [
        ProcessIdentity(
            process_id="app_collect_service",
            role="app",
            workspace_id="workspace_collect_service",
            display_name="数据采集服务",
        ),
        ProcessIdentity(
            process_id="agent_collect_service",
            role="agent",
            workspace_id="workspace_collect_service",
            display_name="数据采集服务 Agent",
        ),
        ProcessIdentity(
            process_id="watch_collect_service",
            role="supervisor",
            workspace_id="workspace_collect_service",
            display_name="数据采集服务监督脚本",
        ),
    ]
    with SessionLocal() as db:
        for row in demo_rows:
            exists = db.scalar(
                select(ProcessIdentity).where(ProcessIdentity.process_id == row.process_id)
            )
            if exists is None:
                db.add(row)
        db.commit()


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


def _generate_default_process_id(db: Session, role: str, workspace_name: str | None) -> str:
    seed = f"{role}:{workspace_name or 'workspace'}:{os.urandom(16).hex()}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    candidate = f"{role}_{digest}"

    while _process_id_exists(db, candidate):
        digest = hashlib.sha1(os.urandom(16)).hexdigest()[:8]
        candidate = f"{role}_{digest}"

    return candidate


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
