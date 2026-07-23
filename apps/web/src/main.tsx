import React from "react";
import { createRoot } from "react-dom/client";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  Folder,
  Pencil,
  Pause,
  Plus,
  Play,
  RefreshCw,
  Save,
  Search,
  Settings,
  Trash2,
  X,
  XCircle
} from "lucide-react";
import brandIcon from "./assets/brand-icon.png";
import "./styles.css";

type ProcessIdDefaults = {
  app_process_id: string;
  agent_process_id: string;
  supervisor_process_id: string;
  storage_available: boolean;
  warning: string | null;
};

type ProcessIdCheck = {
  process_id: string;
  available: boolean;
  reason: string;
  storage_available: boolean;
};

type DirectorySelection = {
  selected: boolean;
  path: string | null;
  message: string | null;
};

type DirectoryEntry = {
  name: string;
  path: string;
};

type DirectoryList = {
  current_path: string;
  parent_path: string | null;
  roots: string[];
  items: DirectoryEntry[];
  selectable: boolean;
  warning: string | null;
};

type ProcessIdField = "app" | "agent" | "watch";
type WorkspaceStatus = "running" | "paused" | "idle";

type RuntimeProcessStatus = {
  role: string;
  process_id: string;
  os_pid: number | null;
  status: string;
  detail: string | null;
};

type Workspace = {
  id: string;
  name: string;
  path: string;
  command: string;
  agentCommand: string;
  pollSeconds: number;
  aiCanEdit: boolean;
  initialPrompt: string;
  processIds: Record<ProcessIdField, string>;
  status: WorkspaceStatus;
  runtime: string;
  runtimeLoadedAt: number;
  logs: string[];
  runtimeStatus: Record<ProcessIdField, RuntimeProcessStatus>;
};

type ApiWorkspace = {
  id: string;
  name: string;
  path: string;
  command: string;
  agent_command: string;
  poll_seconds: number;
  ai_can_edit: boolean;
  initial_prompt: string;
  process_ids: Record<ProcessIdField, string>;
  status: WorkspaceStatus;
  runtime: string;
  logs: string[];
  runtime_status?: Record<ProcessIdField, RuntimeProcessStatus>;
};

type WorkspaceListResponse = {
  storage_available: boolean;
  items: ApiWorkspace[];
  warning: string | null;
};

type LogSettings = {
  archive_root: string;
  retention_days: number;
  default_log_limit: number;
  sync_tail_lines: number;
  search_archives_by_default: boolean;
  storage_available: boolean;
  warning: string | null;
};

const FIELD_META: Record<ProcessIdField, { label: string; role: string }> = {
  app: {
    label: "启动脚本 process_id",
    role: "app"
  },
  agent: {
    label: "Agent process_id",
    role: "agent"
  },
  watch: {
    label: "Monitor process_id",
    role: "supervisor"
  }
};

function fromApiWorkspace(workspace: ApiWorkspace): Workspace {
  return {
    id: workspace.id,
    name: workspace.name,
    path: workspace.path,
    command: workspace.command,
    agentCommand: workspace.agent_command,
    pollSeconds: workspace.poll_seconds,
    aiCanEdit: workspace.ai_can_edit,
    initialPrompt: workspace.initial_prompt,
    processIds: workspace.process_ids,
    status: workspace.status,
    runtime: workspace.runtime,
    runtimeLoadedAt: Date.now(),
    logs: workspace.logs.map(cleanLogLine).filter((line) => line.trim().length > 0),
    runtimeStatus: workspace.runtime_status ?? emptyRuntimeStatus(workspace.process_ids)
  };
}

function toApiWorkspace(workspace: Workspace): ApiWorkspace {
  return {
    id: workspace.id,
    name: workspace.name,
    path: workspace.path,
    command: workspace.command,
    agent_command: workspace.agentCommand,
    poll_seconds: workspace.pollSeconds,
    ai_can_edit: workspace.aiCanEdit,
    initial_prompt: workspace.initialPrompt,
    process_ids: workspace.processIds,
    status: workspace.status,
    runtime: workspace.runtime,
    logs: workspace.logs,
    runtime_status: workspace.runtimeStatus
  };
}

function emptyRuntimeStatus(processIds: Record<ProcessIdField, string>): Record<ProcessIdField, RuntimeProcessStatus> {
  return {
    app: { role: "app", process_id: processIds.app, os_pid: null, status: "idle", detail: null },
    agent: { role: "agent", process_id: processIds.agent, os_pid: null, status: "idle", detail: null },
    watch: { role: "supervisor", process_id: processIds.watch, os_pid: null, status: "idle", detail: null }
  };
}

async function readApiError(response: Response, fallback: string): Promise<string> {
  const text = await response.text();
  if (!text) return `${fallback}：HTTP ${response.status}`;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((item) => JSON.stringify(item)).join("\n");
  } catch {
    // Keep plain text response.
  }
  return text;
}

function App() {
  const [workspaces, setWorkspaces] = React.useState<Workspace[]>([]);
  const [search, setSearch] = React.useState("");
  const [openLogs, setOpenLogs] = React.useState<Record<string, boolean>>({});
  const [logLimit, setLogLimit] = React.useState(100);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [logSettingsOpen, setLogSettingsOpen] = React.useState(false);
  const [editingWorkspace, setEditingWorkspace] = React.useState<Workspace | null>(null);
  const [pendingDeleteWorkspace, setPendingDeleteWorkspace] = React.useState<Workspace | null>(null);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [loadingWorkspaces, setLoadingWorkspaces] = React.useState(false);
  const [actioningWorkspaces, setActioningWorkspaces] = React.useState<Record<string, boolean>>({});
  const [clockTick, setClockTick] = React.useState(() => Date.now());
  const workspaceLoadSeq = React.useRef(0);
  const workspaceMutationVersion = React.useRef(0);
  const deletedWorkspaceIds = React.useRef<Set<string>>(new Set());
  const workspaceLoadInFlight = React.useRef(false);

  const loadWorkspaces = React.useCallback(async (options: { force?: boolean } = {}) => {
    if (workspaceLoadInFlight.current && !options.force) return;
    workspaceLoadInFlight.current = true;
    const requestSeq = workspaceLoadSeq.current + 1;
    workspaceLoadSeq.current = requestSeq;
    const mutationVersionAtStart = workspaceMutationVersion.current;
    setLoadingWorkspaces(true);
    setDeleteError(null);
    try {
      const response = await fetch("/api/workspaces");
      if (!response.ok) throw new Error(await readApiError(response, "加载工作区失败"));
      const data = (await response.json()) as WorkspaceListResponse;
      if (requestSeq !== workspaceLoadSeq.current || mutationVersionAtStart !== workspaceMutationVersion.current) return;
      const deletedIds = deletedWorkspaceIds.current;
      setWorkspaces(data.items.map(fromApiWorkspace).filter((workspace) => !deletedIds.has(workspace.id)));
      if (data.warning) setDeleteError(data.warning);
    } catch (err) {
      if (requestSeq !== workspaceLoadSeq.current) return;
      setDeleteError(err instanceof Error ? err.message : "加载工作区失败");
    } finally {
      if (requestSeq === workspaceLoadSeq.current) workspaceLoadInFlight.current = false;
      if (requestSeq === workspaceLoadSeq.current) setLoadingWorkspaces(false);
    }
  }, []);

  React.useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  React.useEffect(() => {
    const loadLogSettings = async () => {
      try {
        const response = await fetch("/api/settings/logs");
        if (!response.ok) return;
        const data = (await response.json()) as LogSettings;
        setLogLimit(data.default_log_limit);
      } catch {
        // Keep the local default if settings are unavailable.
      }
    };
    void loadLogSettings();
  }, []);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      void loadWorkspaces();
    }, 1000);
    return () => window.clearInterval(timer);
  }, [loadWorkspaces]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      setClockTick(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const filtered = workspaces.filter((workspace) => {
    const text = [
      workspace.name,
      workspace.path,
      workspace.command,
      workspace.agentCommand,
      workspace.processIds.app,
      workspace.processIds.agent,
      workspace.processIds.watch
    ]
      .join(" ")
      .toLowerCase();
    return text.includes(search.trim().toLowerCase());
  });

  const runningCount = workspaces.filter((workspace) => workspace.status === "running").length;
  const editableCount = workspaces.filter((workspace) => workspace.aiCanEdit).length;
  const pausedCount = workspaces.filter((workspace) => workspace.status === "paused").length;

  const openCreateModal = () => {
    setEditingWorkspace(null);
    setModalOpen(true);
  };

  const openEditModal = (workspace: Workspace) => {
    setEditingWorkspace(workspace);
    setModalOpen(true);
  };

  const toggleRun = async (workspace: Workspace) => {
    setDeleteError(null);
    workspaceMutationVersion.current += 1;
    setActioningWorkspaces((current) => ({ ...current, [workspace.id]: true }));
    try {
      const action = workspace.status === "running" ? "stop" : "start";
      const response = await fetch(`/api/workspaces/${encodeURIComponent(workspace.id)}/${action}`, {
        method: "POST"
      });
      if (!response.ok) throw new Error(await readApiError(response, "运行状态切换失败"));
      const updated = fromApiWorkspace((await response.json()) as ApiWorkspace);
      deletedWorkspaceIds.current.delete(updated.id);
      setWorkspaces((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      workspaceMutationVersion.current += 1;
      void loadWorkspaces({ force: true });
    } catch (err) {
      workspaceMutationVersion.current += 1;
      void loadWorkspaces({ force: true });
      setDeleteError(err instanceof Error ? err.message : "运行状态切换失败");
    } finally {
      setActioningWorkspaces((current) => ({ ...current, [workspace.id]: false }));
    }
  };

  const deleteWorkspace = async (id: string) => {
    setDeleteError(null);
    workspaceMutationVersion.current += 1;
    try {
      const response = await fetch(`/api/workspaces/${encodeURIComponent(id)}`, {
        method: "DELETE"
      });
      if (!response.ok) throw new Error(await readApiError(response, "删除工作区失败"));
      deletedWorkspaceIds.current.add(id);
      setWorkspaces((current) => current.filter((workspace) => workspace.id !== id));
      setOpenLogs((current) => {
        const next = { ...current };
        delete next[id];
        return next;
      });
      workspaceMutationVersion.current += 1;
      void loadWorkspaces({ force: true });
    } catch (err) {
      workspaceMutationVersion.current += 1;
      void loadWorkspaces({ force: true });
      setDeleteError(err instanceof Error ? err.message : "删除工作区失败");
    }
  };

  const saveWorkspace = async (workspace: Workspace, isEdit: boolean) => {
    workspaceMutationVersion.current += 1;
    const response = await fetch(isEdit ? `/api/workspaces/${encodeURIComponent(workspace.id)}` : "/api/workspaces", {
      method: isEdit ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(toApiWorkspace(workspace))
    });
    if (!response.ok) throw new Error(await readApiError(response, "保存工作区失败"));
    const saved = fromApiWorkspace((await response.json()) as ApiWorkspace);
    deletedWorkspaceIds.current.delete(saved.id);
    setWorkspaces((current) => {
      const exists = current.some((item) => item.id === saved.id);
      if (exists) return current.map((item) => (item.id === saved.id ? saved : item));
      return [saved, ...current];
    });
    workspaceMutationVersion.current += 1;
    void loadWorkspaces({ force: true });
    setModalOpen(false);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img className="brand-mark" src={brandIcon} alt="AI-Code-Monitor" />
          <div>
            <h1>AI-Code-Monitor Dashbord</h1>
            <p>本地脚本、Agent 与 Monitor 管理</p>
          </div>
        </div>
        <div className="top-actions">
          <label className="search-box">
            <Search className="search-icon" size={15} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索工作区、路径、命令或 process_id" />
          </label>
          <button className="btn" type="button" onClick={() => setLogSettingsOpen(true)}>
            <Settings size={16} />
            日志设置
          </button>
          <button className="btn primary" type="button" onClick={openCreateModal}>
            <Plus size={17} />
            新建工作区
          </button>
        </div>
      </header>

      <main className="main">
        {deleteError ? (
          <section className="toast error">
            <XCircle size={18} />
            {deleteError}
          </section>
        ) : null}

        <section className="summary">
          <Metric label="工作区" value={workspaces.length} />
          <Metric label="运行中" value={runningCount} />
          <Metric label="AI 可修改" value={editableCount} />
          <Metric label="暂停/异常" value={pausedCount} />
        </section>

        <section className="workspace-panel">
          <div className="panel-head">
            <div>工作区</div>
            <div>工作目录</div>
            <div>启动命令</div>
            <div>状态</div>
            <div>运行时间</div>
            <div>操作</div>
          </div>

          {filtered.map((workspace) => (
            <article className={`workspace-item ${workspace.status}`} key={workspace.id}>
              <div className={`workspace-row ${workspace.status}`}>
                <div className="workspace-name">
                  <strong>{workspace.name}</strong>
                  <span>
                    Agent: {workspace.agentCommand} · 轮询 {workspace.pollSeconds}s · {workspace.aiCanEdit ? "AI 可修改" : "AI 只读"}
                  </span>
                </div>
                <div>
                  <span className="path">{workspace.path}</span>
                </div>
                <div>
                  <span className="command">{workspace.command}</span>
                </div>
                <div>
                  <span className={`status ${workspace.status}`}>{statusText(workspace.status)}</span>
                </div>
                <div className="cell-muted">{displayRuntime(workspace, clockTick)}</div>
                <div className="row-actions">
                  <button
                    className={`btn-icon ${workspace.status === "running" ? "pause" : "run"}`}
                    type="button"
                    onClick={() => void toggleRun(workspace)}
                    title={workspace.status === "running" ? "暂停" : "启动"}
                    disabled={Boolean(actioningWorkspaces[workspace.id])}
                  >
                    {workspace.status === "running" ? <span className="pause-bars"><span /><span /></span> : <span className="play-triangle" />}
                  </button>
                  <button className="btn-icon" type="button" onClick={() => setOpenLogs((current) => ({ ...current, [workspace.id]: !current[workspace.id] }))} title="显示日志">
                    <FileText size={17} />
                  </button>
                  <button
                    className="btn-icon"
                    type="button"
                    onClick={() => openEditModal(workspace)}
                    title={workspace.status === "running" ? "运行中不能编辑" : "编辑"}
                    disabled={workspace.status === "running"}
                  >
                    <Pencil size={16} />
                  </button>
                  <button className="btn-icon" type="button" onClick={() => setPendingDeleteWorkspace(workspace)} title="删除">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              <div className={`process-id-strip ${workspace.status}`}>
                <ProcessPidLink workspace={workspace} field="app" label="App" />
                <ProcessPidLink workspace={workspace} field="agent" label="Agent" />
                <ProcessPidLink workspace={workspace} field="watch" label="Monitor" />
              </div>
              <WorkspaceLogDrawer
                workspaceId={workspace.id}
                open={Boolean(openLogs[workspace.id])}
                logs={workspace.logs}
                logLimit={logLimit}
                onLogLimitChange={setLogLimit}
              />
            </article>
          ))}
        </section>
      </main>

      {modalOpen ? (
        <WorkspaceModal
          workspace={editingWorkspace}
          onClose={() => setModalOpen(false)}
          onSave={saveWorkspace}
        />
      ) : null}

      {logSettingsOpen ? (
        <LogSettingsModal
          onClose={() => setLogSettingsOpen(false)}
          onSaved={(settings) => {
            setLogLimit(settings.default_log_limit);
          }}
        />
      ) : null}

      {pendingDeleteWorkspace ? (
        <ConfirmDeleteModal
          workspace={pendingDeleteWorkspace}
          onCancel={() => setPendingDeleteWorkspace(null)}
          onConfirm={async () => {
            await deleteWorkspace(pendingDeleteWorkspace.id);
            setPendingDeleteWorkspace(null);
          }}
        />
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ProcessPidLink({ workspace, field, label }: { workspace: Workspace; field: ProcessIdField; label: string }) {
  const runtime = workspace.runtimeStatus[field];
  const href = `/process-log.html?workspace_id=${encodeURIComponent(workspace.id)}&process_id=${encodeURIComponent(workspace.processIds[field])}&role=${encodeURIComponent(field)}`;
  const displayStatus = workspace.status === "running" ? runtime.status : "stopped";
  return (
    <a className="pid-link" href={href} target="_blank" rel="noreferrer" title={runtime.detail ?? "查看进程日志"}>
      <span>{label}</span>
      <span className="pid-value">
        <b>{workspace.processIds[field]}</b>
        <ExternalLink className="pid-open-icon" size={14} />
      </span>
      <em className={`pid-state ${displayStatus}`}>{displayStatus}{workspace.status === "running" && runtime.os_pid ? ` · ${runtime.os_pid}` : ""}</em>
    </a>
  );
}

type ParsedLogRecord = {
  timestamp: string | null;
  level: string;
  body: string;
  summary: string;
  lineCount: number;
  collapsible: boolean;
  codeLike: boolean;
};

function WorkspaceLogDrawer({
  workspaceId,
  open,
  logs,
  logLimit,
  onLogLimitChange
}: {
  workspaceId: string;
  open: boolean;
  logs: string[];
  logLimit: number;
  onLogLimitChange: (value: number) => void;
}) {
  const feedRef = React.useRef<HTMLDivElement | null>(null);
  const [paused, setPaused] = React.useState(false);
  const [displayLogs, setDisplayLogs] = React.useState<string[]>(() => logs.slice(0, logLimit));

  const latestLogs = React.useMemo(() => logs.slice(0, logLimit), [logs, logLimit]);

  React.useEffect(() => {
    if (!open) {
      setPaused(false);
      return;
    }
    if (!paused) setDisplayLogs(latestLogs);
  }, [latestLogs, open, paused]);

  React.useEffect(() => {
    if (!open || paused || !feedRef.current) return;
    feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [displayLogs, open, paused]);

  const syncLatest = () => {
    setPaused(false);
    setDisplayLogs(latestLogs);
    if (feedRef.current) {
      requestAnimationFrame(() => {
        if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
      });
    }
  };

  const handleScroll = () => {
    const panel = feedRef.current;
    if (!panel) return;
    const atBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 24;
    if (atBottom) {
      setPaused(false);
    } else {
      setPaused(true);
    }
  };

  const handleMouseUp = () => {
    const panel = feedRef.current;
    if (!panel) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    const anchor = selection.anchorNode;
    if (anchor && panel.contains(anchor)) setPaused(true);
  };

  return (
    <div className={`log-drawer ${open ? "open" : ""}`}>
      <div className="log-toolbar">
        <div className="log-toolbar-left">
          <h3>最新日志</h3>
          <span className={`log-state ${paused ? "paused" : "live"}`}>{paused ? "已暂停刷新" : "自动跟随最新"}</span>
        </div>
        <div className="log-toolbar-actions">
          <button className="btn-icon" type="button" onClick={syncLatest} title="立即同步最新日志">
            <RefreshCw size={15} />
          </button>
          <button
            className="btn-icon"
            type="button"
            onClick={() => (paused ? syncLatest() : setPaused(true))}
            title={paused ? "恢复自动刷新" : "暂停自动刷新"}
          >
            {paused ? <Play size={15} /> : <Pause size={15} />}
          </button>
          <label className="log-limit">
            显示条数
            <input type="number" min={10} max={5000} value={logLimit} onChange={(event) => onLogLimitChange(Number(event.target.value))} />
          </label>
        </div>
      </div>
      <div className={`logs ${paused ? "paused" : ""}`} ref={feedRef} onScroll={handleScroll} onMouseUp={handleMouseUp} onCopy={() => setPaused(true)}>
        {displayLogs.map((line, index) => (
          <LogRecordView key={`${workspaceId}-${index}-${line}`} raw={line} />
        ))}
      </div>
    </div>
  );
}

function LogRecordView({ raw }: { raw: string }) {
  const record = React.useMemo(() => parseLogRecord(raw), [raw]);
  const levelClass = logLevelClass(record.level);
  const detailsClass = `log-entry ${levelClass}${record.collapsible ? " collapsible" : ""}${record.codeLike ? " code" : ""}`;
  const meta = (
    <div className="log-entry-head">
      <span className={`log-pill ${levelClass}`}>{record.level}</span>
      {record.timestamp ? <time className="log-timestamp">{record.timestamp}</time> : null}
      <span className="log-summary">{record.summary}</span>
      {record.collapsible ? <span className="log-line-count">{record.lineCount} 行</span> : null}
    </div>
  );

  if (!record.collapsible) {
    return (
      <article className={detailsClass}>
        {meta}
      </article>
    );
  }

  return (
    <details className={detailsClass}>
      <summary>
        <div className="log-entry-head">
          <ChevronRight className="log-disclosure closed" size={14} />
          <ChevronDown className="log-disclosure open" size={14} />
          <span className={`log-pill ${levelClass}`}>{record.level}</span>
          {record.timestamp ? <time className="log-timestamp">{record.timestamp}</time> : null}
          <span className="log-summary">{record.summary}</span>
          <span className="log-line-count">{record.lineCount} 行</span>
        </div>
      </summary>
      <div className="log-entry-body">{renderLogBody(record)}</div>
    </details>
  );
}

function renderLogBody(record: ParsedLogRecord) {
  if (record.codeLike) {
    return <pre className="log-code-block">{record.body}</pre>;
  }
  return <div className="log-text-block">{record.body}</div>;
}

function parseLogRecord(value: string): ParsedLogRecord {
  const clean = cleanLogLine(value);
  const lines = clean.split("\n");
  const firstLine = (lines[0] ?? "").trimStart();
  const match = firstLine.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(ERROR|WARNING|WARN|DEBUG|SUCCESS|INFO)\s+(.*)$/s);
  let timestamp: string | null = null;
  let level = "INFO";
  let body = clean;

  if (match) {
    timestamp = match[1];
    level = normalizeLogLevel(match[2]);
    body = [match[3], ...lines.slice(1)].join("\n").trimEnd();
  } else {
    const levelMatch = firstLine.match(/\b(ERROR|WARNING|WARN|DEBUG|SUCCESS|INFO)\b/);
    if (levelMatch) level = normalizeLogLevel(levelMatch[1]);
  }

  const normalizedBody = body.trimEnd();
  const lineCount = normalizedBody ? normalizedBody.split("\n").length : 0;
  const previewLines = normalizedBody
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const summaryText = previewLines.join(" ");
  const summary = summaryText.length > 160 ? `${summaryText.slice(0, 160)}…` : summaryText;
  const codeLike = looksLikeCodeBlock(normalizedBody);
  const collapsible = codeLike || lineCount > 1 || normalizedBody.length > 240;

  return {
    timestamp,
    level,
    body: normalizedBody,
    summary: summary || normalizedBody.slice(0, 160),
    lineCount,
    collapsible,
    codeLike,
  };
}

function normalizeLogLevel(level: string) {
  return level.toUpperCase() === "WARN" ? "WARNING" : level.toUpperCase();
}

function logLevelClass(level: string) {
  const normalized = normalizeLogLevel(level);
  if (normalized === "ERROR") return "error";
  if (normalized === "WARNING") return "warn";
  if (normalized === "DEBUG") return "debug";
  if (normalized === "SUCCESS") return "success";
  return "info";
}

function looksLikeCodeBlock(text: string) {
  if (!text) return false;
  if (text.includes("```")) return true;
  if (text.split("\n").length > 1) return true;
  if (text.length > 280) return true;
  return /(?:^|\s)(?:function|class|const|let|var|import|export|SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|if\s*\(|for\s*\(|while\s*\(|=>|def\s+|return\s+|print\(|console\.|async\s+function)\b/i.test(text);
}

function ConfirmDeleteModal({
  workspace,
  onCancel,
  onConfirm
}: {
  workspace: Workspace;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [deleting, setDeleting] = React.useState(false);

  const confirm = async () => {
    setDeleting(true);
    try {
      await onConfirm();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <section className="confirm-modal" role="dialog" aria-modal="true">
        <header className="modal-head">
          <h2>确认删除</h2>
          <button className="btn ghost" type="button" onClick={onCancel}>
            <X size={17} />
            关闭
          </button>
        </header>
        <div className="modal-body">
          <p className="confirm-text">
            确定要删除工作区 <strong>{workspace.name}</strong> 吗？该操作会同时删除数据库中关联的 process_id、进程关系和运行实例记录。
          </p>
        </div>
        <footer className="modal-foot">
          <button className="btn" type="button" onClick={onCancel}>取消</button>
          <button className="btn danger" type="button" onClick={() => void confirm()} disabled={deleting}>
            <Trash2 size={16} />
            {deleting ? "删除中" : "确认删除"}
          </button>
        </footer>
      </section>
    </div>
  );
}

async function trySystemDirectoryPicker(): Promise<string | null> {
  const response = await fetch("/api/system/select-directory", { method: "POST" });
  if (!response.ok) return null;
  const data = (await response.json()) as DirectorySelection;
  return data.selected && data.path ? data.path : null;
}

function DirectoryPickerModal({
  title,
  initialPath,
  onSelect,
  onClose
}: {
  title: string;
  initialPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}) {
  const [currentPath, setCurrentPath] = React.useState(initialPath);
  const [data, setData] = React.useState<DirectoryList | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async (path?: string, allowFallback = true) => {
    setLoading(true);
    setError(null);
    try {
      const query = path ? `?${new URLSearchParams({ path })}` : "";
      const response = await fetch(`/api/system/directories${query}`);
      if (!response.ok) {
        let message = await response.text();
        try {
          const parsed = JSON.parse(message) as { detail?: string };
          message = parsed.detail || message;
        } catch {
          // Keep raw response text.
        }
        if (path && allowFallback) {
          const fallbackResponse = await fetch("/api/system/directories");
          if (fallbackResponse.ok) {
            const fallback = (await fallbackResponse.json()) as DirectoryList;
            setData(fallback);
            setCurrentPath(fallback.current_path);
            setError(`${message} 已显示可选择的根目录。`);
            return;
          }
        }
        throw new Error(message);
      }
      const next = (await response.json()) as DirectoryList;
      setData(next);
      setCurrentPath(next.current_path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "目录加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load(initialPath || undefined);
  }, [initialPath, load]);

  const selectCurrent = () => {
    if (!data?.selectable) return;
    onSelect(data.current_path);
    onClose();
  };

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="confirm-modal directory-modal" role="dialog" aria-modal="true">
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="btn ghost" type="button" onClick={onClose}>
            <X size={17} />
            关闭
          </button>
        </header>
        <div className="modal-body">
          {error ? <div className="form-error">{error}</div> : null}
          {data?.warning ? <div className="form-warning">{data.warning}</div> : null}
          <div className="directory-path">{currentPath || "加载中"}</div>
          {data?.roots.length ? (
            <div className="directory-roots">
              {data.roots.map((root) => (
                <button className="btn ghost" type="button" key={root} onClick={() => void load(root)} disabled={loading || root === currentPath}>
                  {root}
                </button>
              ))}
            </div>
          ) : null}
          <div className="directory-list">
            {data?.parent_path ? (
              <button className="directory-row" type="button" onClick={() => void load(data.parent_path ?? undefined)} disabled={loading}>
                <Folder size={17} />
                ..
              </button>
            ) : null}
            {loading ? <div className="directory-empty">加载中</div> : null}
            {!loading && data && data.items.length === 0 ? <div className="directory-empty">没有子目录</div> : null}
            {!loading && data?.items.map((item) => (
              <button className="directory-row" type="button" key={item.path} onClick={() => void load(item.path)}>
                <Folder size={17} />
                {item.name}
              </button>
            ))}
          </div>
        </div>
        <footer className="modal-foot">
          <button className="btn" type="button" onClick={onClose}>取消</button>
          <button className="btn primary" type="button" onClick={selectCurrent} disabled={!data?.selectable || loading}>
            选择当前目录
          </button>
        </footer>
      </section>
    </div>
  );
}

function LogSettingsModal({
  onClose,
  onSaved
}: {
  onClose: () => void;
  onSaved: (settings: LogSettings) => void;
}) {
  const [archiveRoot, setArchiveRoot] = React.useState("");
  const [retentionDays, setRetentionDays] = React.useState(30);
  const [defaultLogLimit, setDefaultLogLimit] = React.useState(1000);
  const [syncTailLines, setSyncTailLines] = React.useState(5000);
  const [searchArchivesByDefault, setSearchArchivesByDefault] = React.useState(true);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [directoryPickerOpen, setDirectoryPickerOpen] = React.useState(false);

  React.useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/settings/logs");
        if (!response.ok) throw new Error(await readApiError(response, "日志设置加载失败"));
        const data = (await response.json()) as LogSettings;
        setArchiveRoot(data.archive_root);
        setRetentionDays(data.retention_days);
        setDefaultLogLimit(data.default_log_limit);
        setSyncTailLines(data.sync_tail_lines);
        setSearchArchivesByDefault(data.search_archives_by_default);
        if (data.warning) setError(data.warning);
      } catch (err) {
        setError(err instanceof Error ? err.message : "日志设置加载失败");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const chooseArchiveRoot = async () => {
    setError(null);
    try {
      const picked = await trySystemDirectoryPicker();
      if (picked) setArchiveRoot(picked);
      else setDirectoryPickerOpen(true);
    } catch (err) {
      setDirectoryPickerOpen(true);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/logs", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          archive_root: archiveRoot,
          retention_days: retentionDays,
          default_log_limit: defaultLogLimit,
          sync_tail_lines: syncTailLines,
          search_archives_by_default: searchArchivesByDefault
        })
      });
      if (!response.ok) throw new Error(await readApiError(response, "日志设置保存失败"));
      const saved = (await response.json()) as LogSettings;
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "日志设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="confirm-modal log-settings-modal" role="dialog" aria-modal="true">
        <header className="modal-head">
          <h2>日志设置</h2>
          <button className="btn ghost" type="button" onClick={onClose}>
            <X size={17} />
            关闭
          </button>
        </header>
        <div className="modal-body">
          {error ? <div className="form-error">{error}</div> : null}
          <div className="form-grid">
            <label className="field full">
              <span>归档目录</span>
              <div className="path-input">
                <input
                  value={archiveRoot}
                  onChange={(event) => setArchiveRoot(event.target.value)}
                  placeholder="留空则使用每个工作区的 .ai-code-monitor/logs/archive"
                  disabled={loading}
                />
                <button className="btn" type="button" onClick={() => void chooseArchiveRoot()} disabled={loading}>
                  选择目录
                </button>
              </div>
            </label>
            <label className="field">
              <span>热日志保留天数</span>
              <input type="number" min={1} max={3650} value={retentionDays} onChange={(event) => setRetentionDays(Number(event.target.value))} disabled={loading} />
            </label>
            <label className="field">
              <span>默认显示行数</span>
              <input type="number" min={10} max={5000} value={defaultLogLimit} onChange={(event) => setDefaultLogLimit(Number(event.target.value))} disabled={loading} />
            </label>
            <label className="field">
              <span>同步扫描行数</span>
              <input type="number" min={100} max={50000} value={syncTailLines} onChange={(event) => setSyncTailLines(Number(event.target.value))} disabled={loading} />
            </label>
            <label className="field check-field">
              <span>默认搜索归档</span>
              <input type="checkbox" checked={searchArchivesByDefault} onChange={(event) => setSearchArchivesByDefault(event.target.checked)} disabled={loading} />
            </label>
          </div>
        </div>
        <footer className="modal-foot">
          <button className="btn" type="button" onClick={onClose}>取消</button>
          <button className="btn primary" type="button" onClick={() => void save()} disabled={loading || saving}>
            <Save size={16} />
            {saving ? "保存中" : "保存"}
          </button>
        </footer>
      </section>
      {directoryPickerOpen ? (
        <DirectoryPickerModal
          title="选择归档目录"
          initialPath={archiveRoot}
          onSelect={setArchiveRoot}
          onClose={() => setDirectoryPickerOpen(false)}
        />
      ) : null}
    </div>
  );
}

function WorkspaceModal({
  workspace,
  onClose,
  onSave
}: {
  workspace: Workspace | null;
  onClose: () => void;
  onSave: (workspace: Workspace, isEdit: boolean) => Promise<void>;
}) {
  const isEdit = Boolean(workspace);
  const [name, setName] = React.useState(workspace?.name ?? "新工作区");
  const [workspaceId, setWorkspaceId] = React.useState(workspace?.id ?? "workspace_new");
  const [path, setPath] = React.useState(workspace?.path ?? "/workspaces/my-project");
  const [command, setCommand] = React.useState(workspace?.command ?? "python app.py");
  const [agentCommand, setAgentCommand] = React.useState(workspace?.agentCommand ?? "codex");
  const [pollSeconds, setPollSeconds] = React.useState(workspace?.pollSeconds ?? 30);
  const [aiCanEdit, setAiCanEdit] = React.useState(workspace?.aiCanEdit ?? true);
  const [initialPrompt, setInitialPrompt] = React.useState(workspace?.initialPrompt ?? "");
  const [processIds, setProcessIds] = React.useState<Record<ProcessIdField, string>>(workspace?.processIds ?? { app: "", agent: "", watch: "" });
  const [defaultValues, setDefaultValues] = React.useState<Record<ProcessIdField, string>>(workspace?.processIds ?? { app: "", agent: "", watch: "" });
  const [editedFields, setEditedFields] = React.useState<Record<ProcessIdField, boolean>>({ app: false, agent: false, watch: false });
  const [checks, setChecks] = React.useState<Partial<Record<ProcessIdField, ProcessIdCheck>>>({});
  const [checking, setChecking] = React.useState<Partial<Record<ProcessIdField, boolean>>>({});
  const [saving, setSaving] = React.useState(false);
  const [selectingDirectory, setSelectingDirectory] = React.useState(false);
  const [directoryPickerOpen, setDirectoryPickerOpen] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadDefaults = React.useCallback(async () => {
    if (isEdit) return;
    setError(null);
    try {
      const params = new URLSearchParams({ workspace_name: name });
      const response = await fetch(`/api/process-ids/defaults?${params}`);
      if (!response.ok) throw new Error(`默认 process_id 生成失败：HTTP ${response.status}`);
      const data = (await response.json()) as ProcessIdDefaults;
      const next = {
        app: data.app_process_id,
        agent: data.agent_process_id,
        watch: data.supervisor_process_id
      };
      setDefaultValues(next);
      setProcessIds(next);
      setEditedFields({ app: false, agent: false, watch: false });
      if (data.warning) setError(data.warning);
    } catch (err) {
      setError(err instanceof Error ? err.message : "默认 process_id 生成失败");
    }
  }, [isEdit, name]);

  React.useEffect(() => {
    void loadDefaults();
  }, [loadDefaults]);

  React.useEffect(() => {
    const timers = (Object.keys(processIds) as ProcessIdField[]).map((field) => {
      const value = processIds[field].trim();
      if (!value) {
        setChecks((current) => ({
          ...current,
          [field]: { process_id: value, available: false, reason: "process_id 不能为空。", storage_available: true }
        }));
        return undefined;
      }

      if (isEdit && value === workspace?.processIds[field]) {
        setChecks((current) => ({
          ...current,
          [field]: { process_id: value, available: true, reason: "当前工作区原 process_id。", storage_available: true }
        }));
        return undefined;
      }

      setChecking((current) => ({ ...current, [field]: true }));
      return window.setTimeout(async () => {
        try {
          const response = await fetch(`/api/process-ids/check?${new URLSearchParams({ process_id: value })}`);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const data = (await response.json()) as ProcessIdCheck;
          setChecks((current) => ({ ...current, [field]: data }));
        } catch (err) {
          setChecks((current) => ({
            ...current,
            [field]: {
              process_id: value,
              available: false,
              reason: err instanceof Error ? err.message : "查重失败",
              storage_available: false
            }
          }));
        } finally {
          setChecking((current) => ({ ...current, [field]: false }));
        }
      }, 280);
    });

    return () => {
      timers.forEach((timer) => {
        if (timer !== undefined) window.clearTimeout(timer);
      });
    };
  }, [isEdit, processIds, workspace?.processIds]);

  const duplicateInsideForm = (field: ProcessIdField) => {
    const value = processIds[field].trim();
    if (!value) return false;
    return (Object.keys(processIds) as ProcessIdField[]).some((other) => other !== field && processIds[other].trim() === value);
  };

  const canSave = (Object.keys(processIds) as ProcessIdField[]).every((field) => checks[field]?.available && !duplicateInsideForm(field));

  const updateProcessId = (field: ProcessIdField, value: string) => {
    setProcessIds((current) => ({ ...current, [field]: value }));
    setEditedFields((current) => ({ ...current, [field]: value !== defaultValues[field] }));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        id: workspaceId.trim(),
        name,
        path,
        command,
        agentCommand,
        pollSeconds,
        aiCanEdit,
        initialPrompt: aiCanEdit ? initialPrompt : "",
        processIds,
        runtimeStatus: workspace?.runtimeStatus ?? emptyRuntimeStatus(processIds),
        status: workspace?.status ?? "idle",
        runtime: workspace?.runtime ?? "00:00:00",
        runtimeLoadedAt: workspace?.runtimeLoadedAt ?? Date.now(),
        logs: workspace?.logs ?? ["--:--:-- workspace created, waiting for start"]
      }, isEdit);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const chooseDirectory = async () => {
    setSelectingDirectory(true);
    setError(null);
    try {
      const picked = await trySystemDirectoryPicker();
      if (picked) setPath(picked);
      else setDirectoryPickerOpen(true);
    } catch (err) {
      setDirectoryPickerOpen(true);
    } finally {
      setSelectingDirectory(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal" role="dialog" aria-modal="true">
        <header className="modal-head">
          <h2>{isEdit ? "编辑工作区" : "新建工作区"}</h2>
          <button className="btn ghost" type="button" onClick={onClose}>
            <X size={17} />
            关闭
          </button>
        </header>

        <div className="modal-body">
          {error ? <div className="form-error">{error}</div> : null}
          <div className="form-grid">
            <label className="field">
              <span>工作区名称</span>
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">
              <span>Agent 启动命令</span>
              <input value={agentCommand} onChange={(event) => setAgentCommand(event.target.value)} placeholder="codex / claude / opencode run --prompt-file {prompt_file}" />
            </label>

            <label className="field full">
              <span>工作目录</span>
              <div className="path-input">
                <input value={path} onChange={(event) => setPath(event.target.value)} />
                <button className="btn" type="button" onClick={chooseDirectory} disabled={selectingDirectory}>
                  {selectingDirectory ? "选择中" : "选择目录"}
                </button>
              </div>
            </label>

            <label className="field">
              <span>启动命令</span>
              <input value={command} onChange={(event) => setCommand(event.target.value)} />
            </label>
            <label className="field">
              <span>workspace_id</span>
              <input value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} disabled={isEdit} />
            </label>

            {(Object.keys(FIELD_META) as ProcessIdField[]).map((field) => (
              <ProcessIdInput
                key={field}
                field={field}
                value={processIds[field]}
                isDefault={!editedFields[field]}
                check={checks[field]}
                checking={Boolean(checking[field])}
                duplicateInsideForm={duplicateInsideForm(field)}
                onChange={updateProcessId}
              />
            ))}

            <label className="field">
              <span>监督轮询时间</span>
              <input type="number" min={5} value={pollSeconds} onChange={(event) => setPollSeconds(Number(event.target.value))} />
            </label>
            <label className="field">
              <span>默认日志显示条数</span>
              <input type="number" min={10} max={1000} defaultValue={100} />
            </label>

            <div className="field full">
              <div className="toggle-line">
                <div>
                  <strong>允许 AI 修改代码</strong>
                  <span>关闭后 Agent 只能监控、分析和写日志，不主动改工作目录文件。</span>
                </div>
                <label className="switch">
                  <input type="checkbox" checked={aiCanEdit} onChange={(event) => setAiCanEdit(event.target.checked)} />
                  <span className="slider" />
                </label>
              </div>
            </div>

            {aiCanEdit ? (
              <label className="field full">
                <span>提示词</span>
                <textarea
                  value={initialPrompt}
                  onChange={(event) => setInitialPrompt(event.target.value)}
                  placeholder="输入允许 AI 修改代码时使用的提示词"
                />
              </label>
            ) : null}
          </div>
        </div>

        <footer className="modal-foot">
          <button className="btn" type="button" onClick={onClose}>取消</button>
          <button className="btn primary" type="button" onClick={save} disabled={!canSave || saving}>
            <Save size={16} />
            {saving ? "保存中" : isEdit ? "保存修改" : "创建工作区"}
          </button>
        </footer>
      </section>
      {directoryPickerOpen ? (
        <DirectoryPickerModal
          title="选择工作目录"
          initialPath={path}
          onSelect={setPath}
          onClose={() => setDirectoryPickerOpen(false)}
        />
      ) : null}
    </div>
  );
}

function ProcessIdInput({
  field,
  value,
  isDefault,
  check,
  checking,
  duplicateInsideForm,
  onChange
}: {
  field: ProcessIdField;
  value: string;
  isDefault: boolean;
  check: ProcessIdCheck | undefined;
  checking: boolean;
  duplicateInsideForm: boolean;
  onChange: (field: ProcessIdField, value: string) => void;
}) {
  const invalid = duplicateInsideForm || Boolean(check && !check.available);
  const valid = !duplicateInsideForm && Boolean(check?.available);
  return (
    <label className="field process-id-field">
      <span>{FIELD_META[field].label}</span>
      <div className="process-id-input-wrap">
        <input className={isDefault ? "default-process-id" : ""} value={value} onChange={(event) => onChange(field, event.target.value)} />
        <div className="check-icon">
          {checking ? <RefreshCw size={16} /> : valid ? <CheckCircle2 size={17} /> : invalid ? <XCircle size={17} /> : null}
        </div>
      </div>
      {duplicateInsideForm ? <small className="field-error">当前表单里已经使用了这个 process_id。</small> : check ? <small className={check.available ? "field-ok" : "field-error"}>{check.reason}</small> : null}
    </label>
  );
}

function statusText(status: WorkspaceStatus) {
  if (status === "running") return "运行中";
  if (status === "paused") return "已暂停";
  return "未启动";
}

function displayRuntime(workspace: Workspace, now: number) {
  const baseSeconds = parseRuntimeSeconds(workspace.runtime);
  if (workspace.status !== "running") return formatRuntimeSeconds(baseSeconds);
  const deltaSeconds = Math.max(0, Math.floor((now - workspace.runtimeLoadedAt) / 1000));
  return formatRuntimeSeconds(baseSeconds + deltaSeconds);
}

function parseRuntimeSeconds(value: string) {
  const parts = value.split(":").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) return 0;
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function formatRuntimeSeconds(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  return [hours, minutes, remainingSeconds].map((part) => String(part).padStart(2, "0")).join(":");
}

function cleanLogLine(line: string) {
  return line
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)?/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\x1b/g, "")
    .replace(/^\s*\d{1,3}(?:\s+|(?=[^\d\s]))/, "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
    .replace(/\r\n?/g, "\n")
    .trimEnd();
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
