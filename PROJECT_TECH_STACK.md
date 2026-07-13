# AI 监控脚本项目实现方案与技术栈

## 1. 项目目标

这个项目的核心目标是做一个本地控制面板，用来管理多个工作区里的脚本、Agent 和监督脚本。

每个工作区包含三类核心进程：

- 业务启动脚本进程，例如 `python app.py`
- Agent 进程，例如 Codex、Claude Code 或其它命令行 Agent
- 监督脚本进程，用来轮询 Agent 是否持续工作

三者之间不做强代码耦合，而是通过 PID、进程状态、日志、提示词和本地进程通信协作。

## 2. 推荐整体技术栈

### 前端控制面板

推荐：

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- Zustand
- TanStack Query
- React Flow

用途：

- React + TypeScript：构建网页控制面板
- Vite：本地开发和打包
- Tailwind CSS + shadcn/ui：快速做出可维护的管理后台 UI
- Zustand：保存当前选中的工作区、Agent、运行视图状态
- TanStack Query：请求后端 API、轮询进程状态
- React Flow：画工作区、Agent、脚本、监督器之间的连接关系

### 后端控制服务

推荐：

- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic
- psutil
- SQLModel 或 SQLAlchemy
- SQLite
- WebSocket

用途：

- FastAPI：提供控制面板 API
- Uvicorn：运行本地后端服务
- Pydantic：校验工作区、Agent、进程配置
- psutil：启动进程、检查 PID、读取进程状态、停止进程
- SQLite：保存工作区配置、PID 映射、启动命令、提示词模板、运行历史
- WebSocket：实时推送日志、Agent 状态、监督脚本状态

### 进程管理

推荐：

- Python `subprocess`
- `psutil`
- 本地 PID registry
- stdout/stderr 日志文件
- 可选：Unix domain socket 或本地 HTTP callback

用途：

- 启动业务脚本、Agent、监督脚本
- 保存进程 PID
- 检查进程是否存在、是否退出、CPU/内存是否异常
- 把每个进程的 stdout/stderr 写入独立日志文件
- 通过 PID registry 建立工作区内的进程绑定关系

### Agent 适配层

推荐：

- 先实现命令行 Agent 适配器
- 每种 Agent 一个 adapter
- 使用统一接口封装启动、发送提示词、读取输出、停止

示例 Agent：

- Codex CLI
- Claude Code
- 自定义 Agent 命令
- 任意支持 stdin/stdout 或终端会话的 Agent

建议定义统一接口：

```python
class AgentAdapter:
    def start(self, workspace_id: str, config: AgentConfig) -> AgentProcess:
        ...

    def send_prompt(self, agent_pid: int, prompt: str) -> None:
        ...

    def status(self, agent_pid: int) -> AgentStatus:
        ...

    def stop(self, agent_pid: int) -> None:
        ...
```

## 3. 核心架构

推荐拆成 5 层：

```text
Web UI
  |
FastAPI Control Server
  |
Workspace Manager
  |
Process Manager + Agent Adapter + Supervisor Manager
  |
Local Processes: app.py / codex / claude / supervisor.py
```

### Web UI

负责：

- 创建工作区
- 设置项目路径
- 设置启动命令
- 选择 Agent 类型
- 设置 Agent 启动命令
- 设置监督轮询间隔
- 配置继续工作提示词
- 启动、停止、重启工作区
- 查看 PID、日志、状态、异常、运行历史

### FastAPI Control Server

负责：

- 提供 REST API
- 提供 WebSocket 实时状态推送
- 校验前端传入的配置
- 调用 Workspace Manager 执行实际动作

### Workspace Manager

负责：

- 管理多个工作区
- 保存工作区配置
- 建立业务脚本 PID、Agent PID、监督脚本 PID 的绑定关系
- 维护工作区生命周期

### Process Manager

负责：

- 启动命令
- 分配或记录 PID
- 读取进程状态
- 停止进程
- 重启进程
- 采集日志

### Supervisor Manager

负责：

- 启动每个工作区对应的监督脚本
- 设置轮询间隔
- 判断 Agent 是否工作中
- 在 Agent 空闲或失联时发送继续工作提示词
- 把监督结果写回后端

## 4. 推荐目录结构

```text
code-monitor/
  apps/
    web/
      src/
        pages/
        components/
        stores/
        api/
        flow/
      package.json
      vite.config.ts
    server/
      app/
        main.py
        api/
        core/
        models/
        services/
        adapters/
        supervisors/
      pyproject.toml
  data/
    code_monitor.db
    logs/
      workspace-a/
        app.stdout.log
        app.stderr.log
        agent.log
        supervisor.log
  examples/
    demo-python-app/
      app.py
  docs/
    architecture.md
  ai-monitor-architecture.html
  ai-monitor-architecture.png
  PROJECT_TECH_STACK.md
```

## 5. 数据模型设计

### Workspace

```text
id
name
path
status
created_at
updated_at
```

### ProcessBinding

```text
id
workspace_id
role: app | agent | supervisor | worker
pid
command
status
started_at
stopped_at
log_path
```

### AgentConfig

```text
id
workspace_id
agent_type: codex | claude | custom
start_command
default_prompt
continue_prompt
status_check_strategy
```

### SupervisorConfig

```text
id
workspace_id
poll_interval_seconds
max_idle_seconds
retry_limit
continue_prompt_template
enabled
```

### RunEvent

```text
id
workspace_id
process_id
event_type
message
payload_json
created_at
```

## 6. 关键 API 设计

### 工作区

```text
GET    /api/workspaces
POST   /api/workspaces
GET    /api/workspaces/{workspace_id}
PATCH  /api/workspaces/{workspace_id}
DELETE /api/workspaces/{workspace_id}
```

### 启动和停止

```text
POST /api/workspaces/{workspace_id}/start
POST /api/workspaces/{workspace_id}/stop
POST /api/workspaces/{workspace_id}/restart
```

### Agent

```text
POST /api/workspaces/{workspace_id}/agent/start
POST /api/workspaces/{workspace_id}/agent/stop
POST /api/workspaces/{workspace_id}/agent/prompt
GET  /api/workspaces/{workspace_id}/agent/status
```

### 监督脚本

```text
POST /api/workspaces/{workspace_id}/supervisor/start
POST /api/workspaces/{workspace_id}/supervisor/stop
PATCH /api/workspaces/{workspace_id}/supervisor/config
GET   /api/workspaces/{workspace_id}/supervisor/status
```

### 日志和事件

```text
GET /api/workspaces/{workspace_id}/logs
GET /api/workspaces/{workspace_id}/events
WS  /ws/workspaces/{workspace_id}
```

## 7. 进程连接方式

建议把 PID 绑定做成项目里的核心机制。

每个工作区启动后生成一份 PID registry：

```json
{
  "workspace_id": "workspace-a",
  "app": {
    "pid": 3001,
    "command": "python app.py"
  },
  "agent": {
    "pid": 1001,
    "type": "codex"
  },
  "supervisor": {
    "pid": 2001,
    "poll_interval_seconds": 30
  },
  "workers": [
    {
      "pid": 4001,
      "name": "background-task-1"
    }
  ]
}
```

Agent 不需要直接 import 或调用业务脚本。它通过提示词拿到目标 PID、日志路径、项目路径和预期任务。

示例提示词：

```text
你负责监控工作区 workspace-a。
项目路径：/path/to/project
启动脚本 PID：3001
启动命令：python app.py
日志路径：data/logs/workspace-a/app.stdout.log

请持续检查该进程是否正常运行。
如果发现异常退出、日志报错或服务无响应，请分析原因并修复代码。
修复后重新启动脚本，并把结果返回给监督脚本 PID：2001。
```

## 8. 监督脚本逻辑

监督脚本建议保持简单，不直接处理复杂业务。

伪代码：

```python
while True:
    registry = load_workspace_pid_registry(workspace_id)
    agent_pid = registry["agent"]["pid"]
    app_pid = registry["app"]["pid"]

    agent_state = check_agent_state(agent_pid)

    if agent_state in ["dead", "idle", "stalled"]:
        prompt = render_continue_prompt(
            workspace_id=workspace_id,
            app_pid=app_pid,
            agent_pid=agent_pid,
            supervisor_pid=os.getpid(),
        )
        send_prompt_to_agent(agent_pid, prompt)

    sleep(poll_interval_seconds)
```

监督脚本只回答三个问题：

- Agent 进程还在不在
- Agent 是否还在有效工作
- 如果不在工作，应该发什么提示词让它继续

## 9. Agent 是否工作中的判断

可以分阶段实现。

### MVP 判断方式

- Agent PID 是否存在
- Agent 日志最近 N 秒是否有新增
- Agent stdout/stderr 是否仍有输出
- 最近一次事件时间是否超过 `max_idle_seconds`

### 增强判断方式

- 给 Agent 发送轻量心跳提示词
- 检查 Agent 是否在等待用户输入
- 检查 Agent 是否正在运行命令
- 解析 Agent 输出里的状态标记
- 通过终端会话 API 或 PTY 判断交互状态

## 10. 前端页面设计

### 首页仪表盘

展示：

- 工作区总数
- 正在运行的业务脚本
- 正在运行的 Agent
- 正在运行的监督脚本
- 异常工作区
- 最近事件

### 工作区详情页

展示：

- 工作区路径
- 启动命令
- Agent 类型
- Agent PID
- 启动脚本 PID
- 监督脚本 PID
- 轮询间隔
- 当前状态
- 日志窗口
- 手动发送提示词输入框

### 架构视图

使用 React Flow 展示：

- 工作区
- Agent 节点
- 监督脚本节点
- 启动脚本节点
- PID 协调层
- 提示词通道
- 轮询通道

### 配置页

展示：

- 默认 Agent 类型
- 默认轮询时间
- 默认继续工作提示词
- 日志保留时间
- PID 自动生成策略
- 工作区扫描路径

## 11. MVP 实现路线

### 第 1 阶段：本地后端最小闭环

实现：

- FastAPI 服务
- SQLite 配置表
- 创建工作区
- 设置启动命令
- 启动业务脚本
- 记录 PID
- 查看进程状态
- 停止进程

### 第 2 阶段：Agent 启动与提示词发送

实现：

- AgentConfig
- AgentAdapter
- 启动 Codex 或 Claude Code
- 保存 Agent PID
- 向 Agent 发送提示词
- 保存 Agent 日志

### 第 3 阶段：监督脚本

实现：

- SupervisorConfig
- 监督脚本进程
- 轮询 Agent PID
- 判断 Agent 是否空闲或退出
- 自动发送继续工作提示词
- 写入 RunEvent

### 第 4 阶段：Web UI

实现：

- 工作区列表
- 工作区详情
- 启动/停止按钮
- PID 状态展示
- 日志实时查看
- 手动发送提示词
- 监督配置表单

### 第 5 阶段：架构图与可视化

实现：

- React Flow 架构视图
- 每个工作区节点实时变色
- PID 连接线
- 异常状态高亮
- 点击节点查看日志和配置

## 12. 需要注意的工程问题

### PID 不等于稳定身份

PID 会被操作系统复用，所以不能只保存 PID。建议同时保存：

- PID
- 启动时间
- 启动命令
- 工作目录
- 进程父子关系

用 `psutil.Process(pid).create_time()` 校验进程是否还是原来的进程。

### Agent 交互可能需要 PTY

Codex、Claude Code 这类命令行 Agent 可能不是普通 stdin/stdout 程序，可能需要伪终端。

推荐预留：

- `subprocess` 普通模式
- `pty` 交互模式
- 可选 `pexpect`

### 日志必须落盘

不要只依赖内存状态。每个工作区建议有固定日志目录：

```text
data/logs/{workspace_id}/
```

至少保存：

- app stdout
- app stderr
- agent log
- supervisor log
- control server event log

### 停止进程要处理进程树

业务脚本可能启动子进程。停止时建议用 `psutil` 找到 children 并按顺序终止：

```text
SIGTERM parent
SIGTERM children
等待几秒
SIGKILL 未退出进程
```

### 权限边界

因为这个项目能启动命令和控制 Agent，建议默认只监听本机：

```text
127.0.0.1
```

不要默认开放公网访问。

## 13. 推荐最终形态

最终可以做成一个本地桌面级控制系统：

- 后端：FastAPI 本地常驻服务
- 前端：React Web UI
- 数据：SQLite
- 进程：psutil + subprocess + pty/pexpect
- 实时状态：WebSocket
- 架构可视化：React Flow
- Agent 扩展：Adapter 插件机制

这个方案的重点是把 Agent 当成可替换的工作进程，而不是项目代码的一部分。监督脚本只负责确保 Agent 持续工作，Agent 再通过提示词和 PID 去监控、修复、重启具体业务脚本。
