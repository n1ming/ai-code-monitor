<p align="center">
  <img src="images/brand-icon.png" width="128" alt="AI-Code-Monitor logo" />
</p>

<h1 align="center">AI-Code-Monitor</h1>

<p align="center">
  本地 AI 脚本监控
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
  简体中文
  ·
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="#项目概览">项目概览</a>
  ·
  <a href="#功能特性">功能特性</a>
  ·
  <a href="#快速开始">快速开始</a>
  ·
  <a href="#日志系统">日志系统</a>
</p>

---

## 项目概览

AI-Code-Monitor 是一个本地 AI 脚本监控系统，用来管理多个脚本项目、AI 代码 Agent 和监督脚本 Monitor。它适合需要让 Codex、Claude Code 或其它命令行 Agent 长时间监控、修改、测试并重启本地脚本项目的场景。

每个工作区绑定三类逻辑进程身份：

| 身份 | 说明 | 示例 |
| --- | --- | --- |
| App | 被监控的业务脚本或服务 | `python app.py` |
| Agent | AI 代码 Agent 启动命令 | `codex`, `claude`, `opencode run --prompt-file {prompt_file}` |
| Monitor | 自动生成的监督脚本 | `monitor.py` |

> `process_id` 是系统内部稳定 ID，不是操作系统 PID。OS PID 只作为运行时实例信息记录。

![AI-Code-Monitor architecture](images/ai-monitor-architecture.png)

## 功能特性

- 工作区增删改查
- 一键启动和停止 App、Agent、Monitor
- Agent 启动命令自由输入
- 内部 `process_id` 自动生成与重复校验
- 可选 AI 修改代码权限
- 自动生成运行辅助脚本：
  - `monitor.py`
  - `app_launcher.py`
  - `app_watchdog.py`
- 通过 PTY 启动交互式 Agent
- Agent 被杀掉后自动重启
- 通过 `.ai-code-monitor/app-runtime.json` 跟踪 App 运行状态
- Dashboard 显示 App、Agent、Monitor 状态
- 日志页实时刷新，支持角色、等级、日期、关键词筛选
- MySQL 热日志搜索 + gzip 归档日志搜索
- 可配置归档目录、热日志保留天数、默认显示行数、同步扫描行数

## 项目状态

| 模块 | 状态 |
| --- | --- |
| Dashboard UI | 已实现 |
| 工作区 CRUD | 已实现 |
| App / Agent / Monitor 进程控制 | 已实现 |
| PTY Agent 启动 | 已实现 |
| 实时日志页 | 已实现 |
| MySQL 热日志搜索 | 已实现 |
| gzip 归档日志搜索 | 已实现 |
| 多 Agent 命令模板 | 已实现 |

## 技术栈

### 前端

- React
- TypeScript
- Vite
- lucide-react
- CSS

前端入口：

```text
apps/web/src/main.tsx
apps/web/src/styles.css
apps/web/public/process-log.html
```

### 后端

- Python 3.11+
- FastAPI
- SQLAlchemy
- PyMySQL
- psutil
- Uvicorn
- `subprocess`
- `pty`

后端入口：

```text
apps/server/app/main.py
```

### 数据库

- MySQL

主要数据表：

- `workspaces`
- `process_identities`
- `process_links`
- `process_runtime_instances`
- `runtime_logs`
- `log_archives`
- `log_settings`

## 架构流程

工作区启动流程：

```text
用户点击启动
  |
FastAPI 启动 monitor.py
  |
monitor.py 通过 PTY 启动 Agent
  |
monitor.py 发送初始化提示词
  |
Agent 阅读项目并运行 python app_launcher.py
  |
app_launcher.py 启动 app_watchdog.py
  |
app_watchdog.py 启动用户命令
  |
App 写入日志和 app-runtime.json
  |
Monitor 持续检查 Agent 和 App 状态
```

工作区停止流程：

```text
用户点击停止
  |
FastAPI 停止 Monitor 进程树
  |
FastAPI 停止 Agent 进程树
  |
FastAPI 读取 app-runtime.json 并停止 App
  |
FastAPI 扫描残留 App 进程
  |
运行状态标记为 stopped
```

## 目录结构

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
  README.en.md
```

被管理的工作区会生成以下文件：

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

## 快速开始

### 1. 创建 MySQL 数据库

```sql
CREATE DATABASE ai_code_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 配置后端环境变量

创建或更新：

```text
apps/server/.env
```

示例：

```env
CODE_MONITOR_DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/ai_code_monitor?charset=utf8mb4
```

### 3. 安装前端依赖

```bash
cd apps/web
npm install
```

### 4. 启动后端

在项目根目录执行：

```bash
.venv/bin/uvicorn apps.server.app.main:app --host 127.0.0.1 --port 8000
```

### 5. 启动前端

```bash
cd apps/web
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## 构建

前端生产构建：

```bash
cd apps/web
npm run build
```

后端语法检查：

```bash
python -m compileall apps/server/app
```

## Agent 命令

Agent 命令由用户输入，可以是简单命令：

```text
codex
claude
```

也可以使用提示词占位符：

```text
opencode run --prompt-file {prompt_file}
some-agent --cwd {project_path} "{prompt}"
```

支持的占位符：

- `{prompt}`：完整初始化提示词
- `{prompt_file}`：生成的提示词文件路径
- `{project_path}`：工作区路径
- `{workspace_name}`：工作区名称

## 日志系统

AI-Code-Monitor 使用两层日志系统。

### 热日志

近期日志会同步到 MySQL 的 `runtime_logs` 表，用于 Dashboard、实时日志页和快速筛选。

### 归档日志

超过保留期的热日志会压缩为 gzip 文件，并通过 `log_archives` 建立索引。

默认归档位置：

```text
workspace-root/.ai-code-monitor/logs/archive/
```

日志页开启“归档”后，可以同时搜索 MySQL 热日志和 gzip 归档日志。

## 运行时文件

每个工作区通过 `.ai-code-monitor/app-runtime.json` 记录当前 App 运行状态：

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

## 注意事项

- 内部 `process_id` 是稳定逻辑 ID。
- OS PID 只用于运行时记录，可能被操作系统复用。
- 开启 AI 修改代码后，初始化提示词会要求 Agent 修改后测试并重启 App。
- 停止工作区时，系统会尝试停止 Monitor、Agent、App 以及残留子进程。

## 许可证

See [LICENSE](LICENSE).
