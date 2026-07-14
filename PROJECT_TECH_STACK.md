# AI-Code-Monitor 项目实现方案与技术栈

## 1. 项目目标

AI-Code-Monitor 是一个本地控制面板，用来管理多个代码工作区中的业务脚本、代码 Agent 和 Monitor 监督脚本。

每个工作区包含三类核心进程身份：

- App：业务启动脚本，例如 `python app.py`
- Agent：代码 Agent，例如 `codex`、`claude` 或其它命令行 Agent
- Monitor：监督脚本 `monitor.py`，负责启动 Agent、发送提示词、轮询状态、必要时重启 Agent

这里使用的 `process_id` 是系统内部稳定 ID，不是操作系统 PID。操作系统 PID 仍会被记录，但只作为运行时实例信息使用，因为系统 PID 会被复用，不适合作为长期绑定身份。

## 2. 当前技术栈

### 前端

- React
- TypeScript
- Vite
- lucide-react
- 普通 CSS

当前实现位置：

- `apps/web/src/main.tsx`
- `apps/web/src/styles.css`
- `apps/web/public/process-log.html`

前端当前能力：

- 工作区增删改查
- 工作区横条列表
- 启动、停止、编辑、删除
- 删除确认弹窗
- Agent 启动命令自由输入，例如 `codex`
- 允许 AI 修改代码时才显示提示词输入框
- 内部 `process_id` 重复校验
- App、Agent、Monitor 三类日志入口
- 日志详情页自动刷新
- 控制面板定时刷新运行状态

### 后端

- Python 3.11+
- FastAPI
- SQLAlchemy
- PyMySQL
- psutil
- subprocess
- pty / termios / select
- Uvicorn

当前实现位置：

- `apps/server/app/main.py`
- `apps/server/schema.sql`

后端当前能力：

- 工作区配置保存到 MySQL
- 内部 `process_id` 生成与重复检查
- 创建或更新工作区时生成 `monitor.py`
- 启动工作区时先启动 Monitor
- Monitor 通过 PTY 启动 Agent
- Monitor 向 Agent 发送初始化提示词
- Monitor 按轮询间隔检查 Agent 输出和存活状态
- Agent 退出后由 Monitor 自动重启
- 停止工作区时清理 Monitor、Agent、App 以及残留进程
- 读取 `.ai-code-monitor/app-runtime.json` 获取 App 真实运行信息
- 清洗终端 ANSI、OSC title、TUI 噪音日志
- Codex 命令自动转换为更适合自动化的非全屏模式
- 将 App、Agent、Monitor 文件日志同步进 MySQL `runtime_logs`
- 日志查询支持角色、等级、日期范围、关键词和行数筛选
- 超过保留期的热日志归档为 `.log.gz`，并写入 `log_archives` 索引
- 提供全局日志设置，支持归档目录、热日志保留天数、默认显示行数、同步扫描行数

### 数据库

当前使用 MySQL，本机配置：

- database：`ai_code_monitor`
- user：`root`
- password：`a2208564278`

当前主要表：

- `workspaces`
- `process_identities`
- `process_links`
- `process_runtime_instances`
- `runtime_logs`
- `log_archives`
- `log_settings`

## 3. 当前运行模型

工作区启动流程：

```text
用户点击启动
  |
FastAPI 启动 monitor.py
  |
monitor.py 启动 Agent 命令
  |
monitor.py 向 Agent 发送初始化提示词
  |
Agent 阅读项目并运行启动命令
  |
App 写入 app-runtime.json 和日志
  |
Monitor 持续轮询 Agent 状态
```

工作区停止流程：

```text
用户点击停止
  |
FastAPI 标记工作区停止
  |
停止 Monitor 进程树
  |
停止 Agent 进程树
  |
读取 app-runtime.json 停止 App
  |
按工作目录和启动命令扫描残留 App 进程
  |
更新运行状态
```

## 4. 目录结构

```text
ai-code-monitor/
  apps/
    server/
      app/
        main.py
      schema.sql
    web/
      src/
        main.tsx
        styles.css
        assets/
      public/
        process-log.html
  PROJECT_TECH_STACK.md
```

每个被管理的工作区会生成：

```text
workspace-root/
  monitor.py
  .ai-code-monitor/
    app-runtime.json
    logs/
      monitor.log
      agent.log
      agent.out.log
      agent.err.log
      app.out.log
```

## 5. 核心数据模型

### Workspace

```text
workspace_id
name
path
start_command
agent_command
poll_seconds
ai_can_edit
initial_prompt
status
created_at
updated_at
```

### ProcessIdentity

```text
id
process_id
role: app | agent | supervisor
workspace_id
display_name
created_at
```

### ProcessLink

```text
id
workspace_id
from_process_id
to_process_id
link_type
created_at
```

当前连接关系：

- Monitor -> Agent：`supervises`
- Agent -> App：`monitors_by_prompt`
- Monitor -> App：`observes`

### ProcessRuntimeInstance

```text
runtime_id
process_id
workspace_id
role
os_pid
pid_create_time
command
cwd
status
stdin_channel
stdout_log
stderr_log
heartbeat_at
started_at
stopped_at
```

## 6. 日志系统设计

长时间运行时，日志不能全部混在一起，也不能无限堆在 MySQL。推荐采用“热日志进 MySQL，冷日志归档到文件”的混合方案。

### 热日志：MySQL

MySQL 保存最近 7 天或 30 天的结构化日志，用于前端快速筛选和实时查看。

建议完善 `runtime_logs`：

```text
id
workspace_id
process_id
role: app | agent | monitor
level: DEBUG | INFO | SUCCESS | WARN | ERROR
occurred_at
message TEXT
source: stdout | stderr | monitor_prompt | agent_reply | system
created_at
```

推荐索引：

```text
(workspace_id, occurred_at)
(workspace_id, role, occurred_at)
(workspace_id, level, occurred_at)
(process_id, occurred_at)
```

前端日志筛选能力：

- 日期范围
- 日志等级
- App / Agent / Monitor
- process_id
- 关键词搜索
- 最新 N 行，默认 1000 行
- 自动刷新

### 冷日志：gzip 归档

超过保留期的日志从 MySQL 导出到工作区本地归档目录。

推荐归档目录：

```text
workspace-root/.ai-code-monitor/logs/archive/
  2026-07-14/
    app_app_xxx.log.gz
    agent_agent_xxx.log.gz
    monitor_watch_xxx.log.gz
```

已新增归档索引表：

```text
log_archives
id
workspace_id
process_id
role
date
file_path
line_count
size_bytes
created_at
```

归档流程：

```text
定时任务扫描 runtime_logs
  |
找出超过保留期的日志
  |
按 workspace / role / date 写入 .log.gz
  |
写入 log_archives 索引
  |
确认归档成功后删除 MySQL 热日志
```

### 日志清洗规则

所有进入 UI 和数据库的日志都要先清洗：

- 移除 ANSI escape sequence
- 移除 OSC terminal title
- 移除 TUI spinner 噪音
- 保留完整日期，例如 `2026-07-14 15:28:55`
- 日志等级统一大写
- 无法识别等级时默认 `INFO`

## 7. 推荐 API

### 工作区

```text
GET    /api/workspaces
POST   /api/workspaces
PUT    /api/workspaces/{workspace_id}
DELETE /api/workspaces/{workspace_id}
```

### 启动和停止

```text
POST /api/workspaces/{workspace_id}/start
POST /api/workspaces/{workspace_id}/stop
```

### process_id

```text
GET /api/process-ids/defaults
GET /api/process-ids/check
```

### 日志

当前：

```text
GET /api/workspaces/{workspace_id}/process-logs
```

建议增强：

```text
GET /api/workspaces/{workspace_id}/process-logs
  ?role=app|agent|monitor
  &level=INFO,ERROR
  &start=2026-07-14T00:00:00
  &end=2026-07-14T23:59:59
  &keyword=timeout
  &limit=1000
  &include_archive=false
```

## 8. 前端 UI 当前约定

控制面板标题：

```text
AI-Code-Monitor Dashbord
```

工作区列表：

- 每个工作区是独立横条
- 横条之间保留间距
- 横条有轻微立体阴影
- 名称、目录、启动命令、状态、运行时间、操作按钮在主横条中展示
- `process_id` 不占表格列，放在横条下面
- App、Agent、Monitor 的 `process_id` 是文字链接
- 打开网页图标紧挨着 `process_id`
- 停止后 App、Agent、Monitor 下方显示 `stopped`
- 运行中显示真实 runtime 状态，例如 `running · 12345`

日志详情页：

- 新页面打开
- 终端风格显示
- 默认最近 1000 行
- 自动刷新
- 不显示手动刷新按钮
- 标题格式：
  - `App 日志 - app_xxx`
  - `Agent 日志 - agent_xxx`
  - `Monitor 日志 - watch_xxx`

## 9. Monitor 初始化提示词规则

创建工作区后，系统在项目根目录生成 `monitor.py`。

启动时 Monitor 向 Agent 发送初始化提示词，核心内容：

```text
你是个智能脚本监控者，你开始监控【项目】这里面的脚本，请你先阅读理解。
并运行脚本项目的启动命令。启动命令是【启动命令】，进程id是【process_id】。
你开始不断监控。
```

如果用户不允许 AI 修改代码：

```text
你在监控的过程中不能修改代码。
```

如果用户允许 AI 修改代码：

```text
你在监控的过程中出现问题可以修改代码。
【用户提示词】
```

日志要求：

```text
请保留记录日志的习惯，不仅是代码内部记录日志，你自己的操作也要记录日志。
日志格式为：具体日期 + 日志等级 + 日志信息。
```

Agent 停止工作时，Monitor 发送：

```text
继续
```

## 10. Codex 适配规则

用户输入 Agent 启动命令为：

```text
codex
```

后端会转换为更适合自动化的命令。

允许 AI 修改代码：

```text
codex --no-alt-screen -a never -s workspace-write
```

不允许 AI 修改代码：

```text
codex --no-alt-screen -a never -s read-only
```

这样可以减少全屏 TUI 对日志采集和进程通信的干扰。

## 11. 近期已完成更新

- 项目迁移到 `/Users/n1ming/PycharmProjects/ai-code-monitor`
- 前端标题更新为 `AI-Code-Monitor Dashbord`
- Agent 类型选择改为 Agent 启动命令输入
- 内部 `process_id` 替代系统 PID 作为稳定身份
- `process_id` 默认生成，并支持用户编辑后实时重复校验
- MySQL 作为主配置存储
- 创建工作区时生成 `monitor.py`
- 启动时由 Monitor 启动 Agent
- Agent 通过提示词理解项目并运行 App 启动命令
- Stop 会清理 Monitor、Agent、App 相关进程
- Monitor 检查 Agent 是否被杀死，被杀死则自动重启
- App、Agent、Monitor 三类运行状态展示在 UI
- App、Agent、Monitor 日志页可点击打开
- 日志页面自动刷新
- 去除日志页手动刷新按钮
- 清洗终端乱码、spinner、OSC title 和 ANSI 控制字符
- 删除工作区时增加确认弹窗
- 允许 AI 修改代码时才显示提示词输入框
- 工作区横条改为独立卡片式条目
- `process_id` 从表格列移动到横条下方
- `process_id` 旁添加打开网页图标
- 主页搜索旁新增日志设置入口，可配置归档目录、保留天数、默认行数和同步扫描行数

## 12. 下一步实现路线

### 第 1 阶段：结构化日志 MVP（已实现）

- 将 Monitor、Agent、App 日志写入 `runtime_logs`
- 补齐 `schema.sql` 中的 `runtime_logs`
- 日志写入前统一清洗
- 日志详情页增加筛选栏
- 支持日期、等级、角色、关键词、行数筛选
- 默认显示最近 1000 行

### 第 2 阶段：日志归档（基础版已实现）

- 增加 `log_archives` 表
- 增加后台归档任务
- 超过保留期的日志写入 `.log.gz`
- MySQL 只保留热日志
- 前端支持查询归档日志

### 第 3 阶段：Agent 工作状态判断增强

- 检查 Agent 进程是否存在
- 检查 Agent 日志是否长时间无新增
- 检查 Agent 是否处于等待输入状态
- 必要时发送心跳提示词
- Agent 被杀死后重启并重新发送初始化提示词

### 第 4 阶段：更强的运行态可视化

- 工作区详情页
- App / Agent / Monitor 进程树
- CPU、内存、运行时长
- 最近错误摘要
- 最近 Agent 操作摘要

## 13. 工程注意事项

### 系统 PID 不能当作稳定 ID

操作系统 PID 会被复用，所以内部 `process_id` 才是长期身份。真实 OS PID 必须和 `pid_create_time`、工作目录、命令一起校验。

### 停止必须处理进程树

业务脚本可能拉起子进程。停止时必须：

```text
SIGTERM children
SIGTERM parent
等待退出
SIGKILL 残留进程
扫描工作目录和启动命令兜底清理
```

### 日志不要只放数据库

MySQL 适合热查询，不适合无限存原始日志。长期日志应压缩归档到文件，并在 MySQL 保留索引。

### 默认只监听本机

这个系统可以启动命令、杀进程、驱动 Agent 修改代码，默认只能监听：

```text
127.0.0.1
```

不要默认开放公网访问。
