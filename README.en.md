<p align="center">
  <img src="images/brand-icon.png" width="128" alt="AI-Code-Monitor logo" />
</p>

<h1 align="center">AI-Code-Monitor</h1>

<p align="center">
  Local AI Script Monitoring.
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
  <a href="README.md">简体中文</a>
  ·
  English
</p>

<p align="center">
  <a href="#overview">Overview</a>
  ·
  <a href="#features">Features</a>
  ·
  <a href="#quick-start">Quick Start</a>
  ·
  <a href="#log-system">Log System</a>
</p>

---

## Overview

AI-Code-Monitor is a local AI script monitoring system for managing script projects, AI coding agents, and monitor supervisors. It is designed for workflows where Codex, Claude Code, or any compatible CLI agent needs to continuously monitor, modify, test, and restart local script projects.

Each workspace binds three logical process identities:

| Identity | Description | Example |
| --- | --- | --- |
| App | Target script or service | `python app.py` |
| Agent | AI coding agent command | `codex`, `claude`, `opencode run --prompt-file {prompt_file}` |
| Monitor | Generated supervisor script | `monitor.py` |

> `process_id` is an internal stable identifier. It is not the operating system PID. OS PIDs are recorded only as runtime instance metadata.

![AI-Code-Monitor architecture](images/ai-monitor-architecture.png)

## Features

- Workspace CRUD from a browser UI
- One-click start and stop for App, Agent, and Monitor
- User-defined Agent launch command
- Internal `process_id` generation and duplicate validation
- Optional AI code modification permission
- Generated runtime helpers:
  - `monitor.py`
  - `app_launcher.py`
  - `app_watchdog.py`
- PTY-based Agent startup for interactive CLI agents
- Automatic Agent restart when the Agent process dies
- App runtime tracking through `.ai-code-monitor/app-runtime.json`
- App, Agent, and Monitor status visible on the dashboard
- Realtime log pages with role, level, date range, and keyword filters
- Hot log search in MySQL plus archived gzip log search
- Configurable archive path, retention days, display limit, and sync tail size

## Project Status

| Module | Status |
| --- | --- |
| Dashboard UI | Implemented |
| Workspace CRUD | Implemented |
| App / Agent / Monitor process control | Implemented |
| PTY Agent startup | Implemented |
| Realtime log pages | Implemented |
| MySQL hot log search | Implemented |
| gzip archive log search | Implemented |
| Multi-Agent command templates | Implemented |

## Tech Stack

### Frontend

- React
- TypeScript
- Vite
- lucide-react
- CSS

Frontend entry points:

```text
apps/web/src/main.tsx
apps/web/src/styles.css
apps/web/public/process-log.html
```

### Backend

- Python 3.11+
- FastAPI
- SQLAlchemy
- PyMySQL
- psutil
- Uvicorn
- `subprocess`
- `pty`

Backend entry point:

```text
apps/server/app/main.py
```

### Database

- MySQL

Main tables:

- `workspaces`
- `process_identities`
- `process_links`
- `process_runtime_instances`
- `runtime_logs`
- `log_archives`
- `log_settings`

## Architecture

Workspace startup flow:

```text
User clicks Start
  |
FastAPI starts monitor.py
  |
monitor.py starts the Agent through PTY
  |
monitor.py sends the initialization prompt
  |
Agent reads the project and runs python app_launcher.py
  |
app_launcher.py starts app_watchdog.py
  |
app_watchdog.py starts the user command
  |
App writes logs and app-runtime.json
  |
Monitor keeps checking Agent and App state
```

Workspace stop flow:

```text
User clicks Stop
  |
FastAPI stops Monitor process tree
  |
FastAPI stops Agent process tree
  |
FastAPI reads app-runtime.json and stops App
  |
FastAPI scans residual App processes
  |
Runtime state is marked stopped
```

## Repository Layout

```text
ai-code-monitor/
  apps/
    server/
      app/
        main.py
      .env.example
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
  README.en.md
```

Managed workspaces get the following generated files:

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

## Quick Start

### 1. Create MySQL Database

```sql
CREATE DATABASE ai_code_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Configure Backend Environment

Copy the example configuration and edit it as needed:

```bash
cp apps/server/.env.example apps/server/.env
```

Example:

```env
CODE_MONITOR_DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/ai_code_monitor?charset=utf8mb4
```

### 3. Install Frontend Dependencies

```bash
cd apps/web
npm install
```

### 4. Install Backend Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apps/server/requirements.txt
```

### 5. Run Backend

From the repository root:

```bash
python -m uvicorn apps.server.app.main:app --host 127.0.0.1 --port 8000
```

### 6. Run Frontend

```bash
cd apps/web
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Docker Deployment

The project includes Docker Compose configuration for MySQL, the backend API, and the frontend Nginx container:

```bash
./build-docker.sh
```

Open:

```text
http://127.0.0.1:8080
```

The backend container connects to the Compose MySQL service:

```text
mysql+pymysql://root@mysql:3306/ai_code_monitor?charset=utf8mb4
```

Note: Docker can only access paths inside the container or paths mounted into the container. The default workspace mounts are:

```text
./docker/workspaces -> /workspaces
./data -> /app/data
```

To monitor other host project directories, do not hard-code local paths into the repository `docker-compose.yml`. When running `./build-docker.sh`, enter an optional extra host root. The script generates a local-only `docker-compose.override.yml`, which is ignored by Git.

Docker and cloud server environments do not have a macOS Finder picker. When clicking "选择目录", the app falls back to browsing backend-allowed directories. By default, only these roots are allowed:

```text
/workspaces
/app/data/workspaces
```

You can change them with:

```env
AICM_ALLOWED_WORKSPACE_ROOTS=/workspaces,/app/data/workspaces
```

The build script checks Docker, Docker Compose, occupied ports, and the npm mirror, then asks for:

- `codex` or `claude code`
- Agent API Base URL
- Agent API Key
- Agent model name
- Whether to enable maximum-permission mode
- Host workspace mount directory
- Optional extra host root to browse and mount

The script writes local runtime settings to `.env.docker.local` and optional volume overrides to `docker-compose.override.yml`. Both files are ignored by Git and are not release artifacts. The backend container injects the selected settings into the Agent:

- Codex: writes an isolated `CODEX_HOME/config.toml` and uses `--dangerously-bypass-approvals-and-sandbox`
- Claude Code: uses `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` and `--permission-mode bypassPermissions --dangerously-skip-permissions`

The backend Docker image installs the selected Agent CLI through domestic mirrors:

```text
NPM_REGISTRY=https://registry.npmmirror.com
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
INSTALL_CODEX=true
INSTALL_CLAUDE_CODE=false
```

To try installing Claude Code CLI as well:

```bash
INSTALL_CLAUDE_CODE=true docker compose build server
```

Even when Claude Code installs successfully, login and API connectivity may still depend on your network environment, so it is not installed by default.

Docker Compose also uses DaoCloud base-image mirrors by default:

```bash
NODE_IMAGE=docker.m.daocloud.io/library/node:22-slim \
PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.11-slim \
WEB_NODE_IMAGE=docker.m.daocloud.io/library/node:22-alpine \
NGINX_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine \
MYSQL_IMAGE=docker.m.daocloud.io/library/mysql:8.4 \
docker compose build
```

If your network can pull from Docker Hub directly, override these variables with the official image names.

## Build

Frontend production build:

```bash
cd apps/web
npm run build
```

Backend syntax check:

```bash
python -m compileall apps/server/app
```

## Agent Commands

The Agent command is user-defined and can be a simple command:

```text
codex
claude
```

Commands can also use prompt placeholders:

```text
opencode run --prompt-file {prompt_file}
some-agent --cwd {project_path} "{prompt}"
```

Supported placeholders:

- `{prompt}`: full initialization prompt
- `{prompt_file}`: path to the generated prompt file
- `{project_path}`: workspace path
- `{workspace_name}`: workspace display name

## Log System

AI-Code-Monitor uses a two-layer log system.

### Hot Logs

Recent logs are synchronized into MySQL table `runtime_logs` for dashboard display, realtime log pages, and fast filtering.

### Archived Logs

Expired hot logs are archived as gzip files and indexed in `log_archives`.

Default archive location:

```text
workspace-root/.ai-code-monitor/logs/archive/
```

When archive search is enabled, the log page searches both MySQL hot logs and gzip archived logs.

## Runtime Files

Each workspace uses `.ai-code-monitor/app-runtime.json` to track the current App runtime:

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

## Notes

- Internal `process_id` values are stable logical IDs.
- OS PIDs are runtime-only and can be reused by the operating system.
- When AI code modification is enabled, the initialization prompt instructs the Agent to test and restart the App after code changes.
- Stopping a workspace attempts to stop Monitor, Agent, App, and residual child processes.

## License

See [LICENSE](LICENSE).
