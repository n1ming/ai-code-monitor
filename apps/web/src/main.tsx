import React from "react";
import { createRoot } from "react-dom/client";
import {
  CheckCircle2,
  FileText,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
  XCircle
} from "lucide-react";
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

type ProcessIdField = "app" | "agent" | "watch";
type WorkspaceStatus = "running" | "paused" | "idle";

type Workspace = {
  id: string;
  name: string;
  path: string;
  command: string;
  agentType: string;
  pollSeconds: number;
  aiCanEdit: boolean;
  processIds: Record<ProcessIdField, string>;
  status: WorkspaceStatus;
  runtime: string;
  logs: string[];
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
    label: "监督脚本 process_id",
    role: "supervisor"
  }
};

const INITIAL_WORKSPACES: Workspace[] = [
  {
    id: "workspace_collect_service",
    name: "数据采集服务",
    path: "/Users/n1ming/projects/collect-service",
    command: "python app.py --port 8100",
    agentType: "Codex",
    pollSeconds: 30,
    aiCanEdit: true,
    processIds: {
      app: "app_collect_service",
      agent: "agent_collect_service",
      watch: "watch_collect_service"
    },
    status: "running",
    runtime: "02:18:41",
    logs: [
      "10:58:14 app process bound to app_collect_service",
      "10:58:16 agent received workspace profile",
      "10:59:02 watch poll agent state=working",
      "11:01:28 agent detected retryable timeout",
      "11:01:34 agent patch applied and service recovered"
    ]
  },
  {
    id: "workspace_order_admin",
    name: "订单后台",
    path: "/Users/n1ming/projects/order-admin",
    command: "npm run dev",
    agentType: "Claude Code",
    pollSeconds: 60,
    aiCanEdit: false,
    processIds: {
      app: "app_order_admin",
      agent: "agent_order_admin",
      watch: "watch_order_admin"
    },
    status: "idle",
    runtime: "00:00:00",
    logs: ["--:--:-- workspace created, waiting for start"]
  },
  {
    id: "workspace_report_runner",
    name: "报表任务",
    path: "/Users/n1ming/jobs/report-runner",
    command: "python run_report.py --daily",
    agentType: "Custom Agent",
    pollSeconds: 45,
    aiCanEdit: true,
    processIds: {
      app: "app_report_runner",
      agent: "agent_report_runner",
      watch: "watch_report_runner"
    },
    status: "paused",
    runtime: "00:42:09",
    logs: [
      "10:33:11 watch supervisor started",
      "10:37:44 agent paused by user",
      "10:37:45 app process kept alive, supervisor paused"
    ]
  }
];

function App() {
  const [workspaces, setWorkspaces] = React.useState<Workspace[]>(INITIAL_WORKSPACES);
  const [search, setSearch] = React.useState("");
  const [openLogs, setOpenLogs] = React.useState<Record<string, boolean>>({});
  const [logLimit, setLogLimit] = React.useState(100);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [editingWorkspace, setEditingWorkspace] = React.useState<Workspace | null>(null);
  const [toast, setToast] = React.useState<string | null>(null);

  const filtered = workspaces.filter((workspace) => {
    const text = [
      workspace.name,
      workspace.path,
      workspace.command,
      workspace.agentType,
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

  const toggleRun = (id: string) => {
    setWorkspaces((current) =>
      current.map((workspace) => {
        if (workspace.id !== id) return workspace;
        if (workspace.status === "running") return { ...workspace, status: "paused" };
        return { ...workspace, status: "running", runtime: workspace.runtime === "00:00:00" ? "00:00:01" : workspace.runtime };
      })
    );
  };

  const deleteWorkspace = (id: string) => {
    setWorkspaces((current) => current.filter((workspace) => workspace.id !== id));
  };

  const saveWorkspace = (workspace: Workspace) => {
    setWorkspaces((current) => {
      const exists = current.some((item) => item.id === workspace.id);
      if (exists) return current.map((item) => (item.id === workspace.id ? workspace : item));
      return [workspace, ...current];
    });
    setModalOpen(false);
    setToast("工作区 process_id 已保存到 MySQL。");
    window.setTimeout(() => setToast(null), 2600);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <h1>工作区监控控制面板</h1>
            <p>本地脚本、Agent 与监督脚本管理</p>
          </div>
        </div>
        <div className="top-actions">
          <label className="search-box">
            <Search className="search-icon" size={15} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索工作区、路径、命令或 process_id" />
          </label>
          <button className="btn" type="button">
            <RefreshCw size={16} />
            刷新状态
          </button>
          <button className="btn primary" type="button" onClick={openCreateModal}>
            <Plus size={17} />
            新建工作区
          </button>
        </div>
      </header>

      <main className="main">
        {toast ? (
          <section className="toast">
            <CheckCircle2 size={18} />
            {toast}
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
            <div>内部 process_id</div>
            <div>状态</div>
            <div>运行时间</div>
            <div>操作</div>
          </div>

          {filtered.map((workspace) => (
            <React.Fragment key={workspace.id}>
              <div className={`workspace-row ${workspace.status}`}>
                <div className="workspace-name">
                  <strong>{workspace.name}</strong>
                  <span>
                    {workspace.agentType} · 轮询 {workspace.pollSeconds}s · {workspace.aiCanEdit ? "AI 可修改" : "AI 只读"}
                  </span>
                </div>
                <div>
                  <span className="path">{workspace.path}</span>
                </div>
                <div>
                  <span className="command">{workspace.command}</span>
                </div>
                <div className="pid-list">
                  <span>App <b>{workspace.processIds.app}</b></span>
                  <span>Agent <b>{workspace.processIds.agent}</b></span>
                  <span>Watch <b>{workspace.processIds.watch}</b></span>
                </div>
                <div>
                  <span className={`status ${workspace.status}`}>{statusText(workspace.status)}</span>
                </div>
                <div className="cell-muted">{workspace.runtime}</div>
                <div className="row-actions">
                  <button className={`btn-icon ${workspace.status === "running" ? "pause" : "run"}`} type="button" onClick={() => toggleRun(workspace.id)} title={workspace.status === "running" ? "暂停" : "启动"}>
                    {workspace.status === "running" ? <span className="pause-bars"><span /><span /></span> : <span className="play-triangle" />}
                  </button>
                  <button className="btn-icon" type="button" onClick={() => setOpenLogs((current) => ({ ...current, [workspace.id]: !current[workspace.id] }))} title="显示日志">
                    <FileText size={17} />
                  </button>
                  <button className="btn-icon" type="button" onClick={() => openEditModal(workspace)} title="编辑">
                    <Pencil size={16} />
                  </button>
                  <button className="btn-icon" type="button" onClick={() => deleteWorkspace(workspace.id)} title="删除">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              <div className={`log-drawer ${openLogs[workspace.id] ? "open" : ""}`}>
                <div className="log-toolbar">
                  <h3>最新日志</h3>
                  <label className="log-limit">
                    显示条数
                    <input type="number" min={10} max={1000} value={logLimit} onChange={(event) => setLogLimit(Number(event.target.value))} />
                  </label>
                </div>
                <div className="logs">
                  {workspace.logs.slice(0, logLimit).map((line) => (
                    <div key={line}>{line}</div>
                  ))}
                </div>
              </div>
            </React.Fragment>
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

function WorkspaceModal({
  workspace,
  onClose,
  onSave
}: {
  workspace: Workspace | null;
  onClose: () => void;
  onSave: (workspace: Workspace) => void;
}) {
  const isEdit = Boolean(workspace);
  const [name, setName] = React.useState(workspace?.name ?? "新工作区");
  const [workspaceId, setWorkspaceId] = React.useState(workspace?.id ?? "workspace_new");
  const [path, setPath] = React.useState(workspace?.path ?? "/Users/n1ming/projects/my-app");
  const [command, setCommand] = React.useState(workspace?.command ?? "python app.py");
  const [agentType, setAgentType] = React.useState(workspace?.agentType ?? "Codex");
  const [pollSeconds, setPollSeconds] = React.useState(workspace?.pollSeconds ?? 30);
  const [aiCanEdit, setAiCanEdit] = React.useState(workspace?.aiCanEdit ?? true);
  const [processIds, setProcessIds] = React.useState<Record<ProcessIdField, string>>(workspace?.processIds ?? { app: "", agent: "", watch: "" });
  const [defaultValues, setDefaultValues] = React.useState<Record<ProcessIdField, string>>(workspace?.processIds ?? { app: "", agent: "", watch: "" });
  const [editedFields, setEditedFields] = React.useState<Record<ProcessIdField, boolean>>({ app: false, agent: false, watch: false });
  const [checks, setChecks] = React.useState<Partial<Record<ProcessIdField, ProcessIdCheck>>>({});
  const [checking, setChecking] = React.useState<Partial<Record<ProcessIdField, boolean>>>({});
  const [saving, setSaving] = React.useState(false);
  const [selectingDirectory, setSelectingDirectory] = React.useState(false);
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
      if (!isEdit) {
        const payload = (Object.keys(processIds) as ProcessIdField[]).map((field) => ({
          process_id: processIds[field].trim(),
          role: FIELD_META[field].role,
          workspace_id: workspaceId.trim(),
          display_name: `${name} ${FIELD_META[field].label}`
        }));
        const response = await fetch("/api/process-ids", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(await response.text());
      }

      onSave({
        id: workspaceId.trim(),
        name,
        path,
        command,
        agentType,
        pollSeconds,
        aiCanEdit,
        processIds,
        status: workspace?.status ?? "idle",
        runtime: workspace?.runtime ?? "00:00:00",
        logs: workspace?.logs ?? ["--:--:-- workspace created, waiting for start"]
      });
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
      const response = await fetch("/api/system/select-directory", { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as DirectorySelection;
      if (data.selected && data.path) {
        setPath(data.path);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "选择目录失败");
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
              <span>Agent 类型</span>
              <select value={agentType} onChange={(event) => setAgentType(event.target.value)}>
                <option>Codex</option>
                <option>Claude Code</option>
                <option>Custom Agent</option>
              </select>
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

            <label className="field full">
              <span>工作区初始化提示词</span>
              <textarea defaultValue="你是这个工作区的 Agent。监督脚本会把工作目录、启动命令、内部 process_id 和用户限制告诉你。你需要持续监控脚本运行，必要时修改代码、重启脚本并写日志。监督脚本只负责提醒你继续工作。" />
            </label>
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

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
