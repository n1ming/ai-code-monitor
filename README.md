<p align="center">
  <img src="images/brand-icon.png" width="128" alt="AI-Code-Monitor logo" />
</p>

<h1 align="center">AI-Code-Monitor</h1>

<p align="center">
  本地 AI 工作区监控控制面板 / A local control panel for AI-monitored script workspaces.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.1.0-blue" />
  <img alt="Status" src="https://img.shields.io/badge/status-active-success" />
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" />
  <img alt="React" src="https://img.shields.io/badge/React-frontend-61DAFB?logo=react&logoColor=222" />
  <img alt="MySQL" src="https://img.shields.io/badge/MySQL-storage-4479A1?logo=mysql&logoColor=white" />
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green" />
</p>

<p align="center">
  <a href="#项目概览--overview">项目概览 / Overview</a>
  ·
  <a href="#功能特性--features">功能特性 / Features</a>
  ·
  <a href="#快速开始--quick-start">快速开始 / Quick Start</a>
  ·
  <a href="#日志系统--log-system">日志系统 / Log System</a>
</p>

---

## 项目概览 / Overview

AI-Code-Monitor 是一个本地 Web 控制面板，用来管理多个脚本工作区、AI 代码 Agent 和监督脚本 Monitor。它适合需要让 Codex、Claude Code 或其它命令行 Agent 长时间监控、修改、测试并重启本地项目的场景。

AI-Code-Monitor is a local web dashboard for managing script workspaces, AI coding agents, and monitor supervisors. It is designed for workflows where Codex, Claude Code, or any compatible CLI agent needs to continuously monitor, modify, test, and restart local projects.

每个工作区绑定三类逻辑进程身份。  
Each workspace binds three logical process identities.

| 身份 / Identity | 说明 / Description | 示例 / Example |
| --- | --- | --- |
| App | 被监控的业务脚本或服务 / Target script or service | `python app.py` |
| Agent | AI 代码 Agent 启动命令 / AI coding agent command | `codex`, `claude`, `opencode run --prompt-file {prompt_file}` |
| Monitor | 自动生成的监督脚本 / Generated supervisor script | `monitor.py` |

> `process_id` 是系统内部稳定 ID，不是操作系统 PID。OS PID 只作为运行时实例信息记录。  
> `process_id` is an internal stable identifier. It is not the operating system PID. OS PIDs are recorded only as runtime instance metadata.

![AI-Code-Monitor architecture](images/ai-monitor-architecture.png)

## 功能特性 / Features

- 工作区增删改查 / Workspace CRUD from a browser UI
- 一键启动和停止 App、Agent、Monitor / One-click start and stop for App, Agent, and Monitor
- Agent 启动命令自由输入 / User-defined Agent launch command
- 内部 `process_id` 自动生成与重复校验 / Internal `process_id` generation and duplicate validation
- 可选 AI 修改代码权限 / Optional AI code modification permission
- 自动生成运行辅助脚本 / Generated runtime helpers:
  - `monitor.py`
  - `app_launcher.py`
  - `app_watchdog.py`
- 通过 PTY 启动交互式 Agent / PTY-based Agent startup for interactive CLI agents
- Agent 被杀掉后自动重启 / Automatic Agent restart when the Agent process dies
- 通过 `.ai-code-monitor/app-runtime.json` 跟踪 App 运行状态 / App runtime tracking through `.ai-code-monitor/app-runtime.json`
- Dashboard 显示 App、Agent、Monitor 状态 / App, Agent, and Monitor status visible on the dashboard
- 日志页实时刷新，支持角色、等级、日期、关键词筛选 / Realtime log pages with role, level, date range, and keyword filters
- MySQL 热日志搜索 + gzip 归档日志搜索 / Hot log search in MySQL plus archived gzip log search
- 可配置归档目录、热日志保留天数、默认显示行数、同步扫描行数 / Configurable archive path, retention days, display limit, and sync tail size

## 项目状态 / Project Status

| 模块 / Module | 状态 / Status |
| --- | --- |
| Dashboard UI | 已实现 / Implemented |
| 工作区 CRUD / Workspace CRUD | 已实现 / Implemented |
| App / Agent / Monitor 进程控制 | 已实现 / Implemented |
| PTY Agent 启动 / PTY Agent startup | 已实现 / Implemented |
| 实时日志页 / Realtime log pages | 已实现 / Implemented |
| MySQL 热日志搜索 / MySQL hot log search | 已实现 / Implemented |
| gzip 归档日志搜索 / gzip archive log search | 已实现 / Implemented |
| 多 Agent 命令模板 / Multi-Agent command templates | 已实现 / Implemented |

## 技术栈 / Tech Stack

### 前端 / Frontend

- React
- TypeScript
- Vite
- lucide-react
- CSS

前端入口 / Frontend entry points:

```text
apps/web/src/main.tsx
apps/web/src/styles.css
apps/web/public/process-log.html
```

### 后端 / Backend

- Python 3.11+
- FastAPI
- SQLAlchemy
- PyMySQL
- psutil
- Uvicorn
- `subprocess`
- `pty`

后端入口 / Backend entry point:

```text
apps/server/app/main.py
```

### 数据库 / Database

- MySQL

主要数据表 / Main tables:

- `workspaces`
- `process_identities`
- `process_links`
- `process_runtime_instances`
- `runtime_logs`
- `log_archives`
- `log_settings`

## 架构流程 / Architecture

工作区启动流程 / Workspace startup flow:

```text
用户点击启动 / User clicks Start
  |
FastAPI 启动 monitor.py / FastAPI starts monitor.py
  |
monitor.py 通过 PTY 启动 Agent / monitor.py starts the Agent through PTY
  |
monitor.py 发送初始化提示词 / monitor.py sends the initialization prompt
  |
Agent 阅读项目并运行 python app_launcher.py / Agent reads the project and runs python app_launcher.py
  |
app_launcher.py 启动 app_watchdog.py / app_launcher.py starts app_watchdog.py
  |
app_watchdog.py 启动用户命令 / app_watchdog.py starts the user command
  |
App 写入日志和 app-runtime.json / App writes logs and app-runtime.json
  |
Monitor 持续检查 Agent 和 App 状态 / Monitor keeps checking Agent and App state
```

工作区停止流程 / Workspace stop flow:

```text
用户点击停止 / User clicks Stop
  |
FastAPI 停止 Monitor 进程树 / FastAPI stops Monitor process tree
  |
FastAPI 停止 Agent 进程树 / FastAPI stops Agent process tree
  |
FastAPI 读取 app-runtime.json 并停止 App / FastAPI reads app-runtime.json and stops App
  |
FastAPI 扫描残留 App 进程 / FastAPI scans residual App processes
  |
运行状态标记为 stopped / Runtime state is marked stopped
```

## 目录结构 / Repository Layout

```text
ai-code-monitor/
  apps/
    server/
      app/
        main.py
      .env
    web/
      src/
        main.tsx
        styles.css
        assets/
      public/
        process-log.html
  images/
    brand-icon.png
    ai-monitor-architecture.png
  PROJECT_TECH_STACK.md
  README.md
```

被管理的工作区会生成以下文件。  
Managed workspaces get the following generated files.

```text
workspace-root/
  monitor.py
  app_launcher.py
  app_watchdog.py
  .ai-code-monitor/
    app-runtime.json
    bridge/
      agent.heartbeat
      agent.os_pid
      initial-prompt.txt
    logs/
      app.out.log
      agent.log
      agent.out.log
      agent.err.log
      monitor.log
      archive/
```

## 快速开始 / Quick Start

### 1. 创建 MySQL 数据库 / Create MySQL Database

```sql
CREATE DATABASE ai_code_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 配置后端环境变量 / Configure Backend Environment

创建或更新 / Create or update:

```text
apps/server/.env
```

示例 / Example:

```env
CODE_MONITOR_DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/ai_code_monitor?charset=utf8mb4
```

### 3. 安装前端依赖 / Install Frontend Dependencies

```bash
cd apps/web
npm install
```

### 4. 启动后端 / Run Backend

在项目根目录执行 / From the repository root:

```bash
.venv/bin/uvicorn apps.server.app.main:app --host 127.0.0.1 --port 8000
```

### 5. 启动前端 / Run Frontend

```bash
cd apps/web
npm run dev
```

打开 / Open:

```text
http://127.0.0.1:5173
```

## 构建 / Build

前端生产构建 / Frontend production build:

```bash
cd apps/web
npm run build
```

后端语法检查 / Backend syntax check:

```bash
python -m compileall apps/server/app
```

## Agent 命令 / Agent Commands

Agent 命令由用户输入，可以是简单命令。  
The Agent command is user-defined and can be a simple command.

```text
codex
claude
```

也可以使用提示词占位符。  
Commands can also use prompt placeholders.

```text
opencode run --prompt-file {prompt_file}
some-agent --cwd {project_path} "{prompt}"
```

支持的占位符 / Supported placeholders:

- `{prompt}`: 完整初始化提示词 / full initialization prompt
- `{prompt_file}`: 生成的提示词文件路径 / path to the generated prompt file
- `{project_path}`: 工作区路径 / workspace path
- `{workspace_name}`: 工作区名称 / workspace display name

## 日志系统 / Log System

AI-Code-Monitor 使用两层日志系统。  
AI-Code-Monitor uses a two-layer log system.

### 热日志 / Hot Logs

近期日志会同步到 MySQL 的 `runtime_logs` 表，用于 Dashboard、实时日志页和快速筛选。  
Recent logs are synchronized into MySQL table `runtime_logs` for dashboard display, realtime log pages, and fast filtering.

### 归档日志 / Archived Logs

超过保留期的热日志会压缩为 gzip 文件，并通过 `log_archives` 建立索引。  
Expired hot logs are archived as gzip files and indexed in `log_archives`.

默认归档位置 / Default archive location:

```text
workspace-root/.ai-code-monitor/logs/archive/
```

日志页开启“归档”后，可以同时搜索 MySQL 热日志和 gzip 归档日志。  
When archive search is enabled, the log page searches both MySQL hot logs and gzip archived logs.

## 运行时文件 / Runtime Files

每个工作区通过 `.ai-code-monitor/app-runtime.json` 记录当前 App 运行状态。  
Each workspace uses `.ai-code-monitor/app-runtime.json` to track the current App runtime.

```json
{
  "process_id": "app_xxxxxxxx",
  "agent_process_id": "agent_xxxxxxxx",
  "os_pid": 12345,
  "command": "python app.py",
  "status": "running",
  "started_at": "2026-07-15 16:12:52",
  "updated_at": "2026-07-15 16:13:07",
  "watchdog_pid": 12344,
  "watchdog_status": "running"
}
```

## 注意事项 / Notes

- 内部 `process_id` 是稳定逻辑 ID。/ Internal `process_id` values are stable logical IDs.
- OS PID 只用于运行时记录，可能被操作系统复用。/ OS PIDs are runtime-only and can be reused by the operating system.
- 开启 AI 修改代码后，初始化提示词会要求 Agent 修改后测试并重启 App。/ When AI code modification is enabled, the initialization prompt instructs the Agent to test and restart the App after code changes.
- 停止工作区时，系统会尝试停止 Monitor、Agent、App 以及残留子进程。/ Stopping a workspace attempts to stop Monitor, Agent, App, and residual child processes.

## 许可证 / License

See [LICENSE](LICENSE).
