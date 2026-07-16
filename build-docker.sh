#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ROOT_DIR}/.env.docker.local"
OVERRIDE_FILE="${ROOT_DIR}/docker-compose.override.yml"

DEFAULT_NPM_REGISTRY="https://registry.npmmirror.com"
DEFAULT_PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
DEFAULT_PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn"
DEFAULT_APT_MIRROR="https://mirrors.tuna.tsinghua.edu.cn/debian"
DEFAULT_NODE_IMAGE="docker.m.daocloud.io/library/node:22-slim"
DEFAULT_PYTHON_IMAGE="docker.m.daocloud.io/library/python:3.11-slim"
DEFAULT_WEB_NODE_IMAGE="docker.m.daocloud.io/library/node:22-alpine"
DEFAULT_NGINX_IMAGE="docker.m.daocloud.io/library/nginx:1.27-alpine"
DEFAULT_MYSQL_IMAGE="docker.m.daocloud.io/library/mysql:8.4"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '\n==> %s\n' "$*"
}

prompt_default() {
  local prompt="$1"
  local default="$2"
  local value
  if [[ -n "${default}" ]]; then
    read -r -p "${prompt} [${default}]: " value
    printf '%s' "${value:-$default}"
  else
    read -r -p "${prompt}: " value
    printf '%s' "$value"
  fi
}

prompt_secret() {
  local prompt="$1"
  local value
  read -r -s -p "${prompt}: " value
  printf '\n' >&2
  printf '%s' "$value"
}

yes_no() {
  local prompt="$1"
  local default="${2:-y}"
  local value
  read -r -p "${prompt} [${default}]: " value
  value="${value:-$default}"
  case "${value,,}" in
    y|yes|true|1) return 0 ;;
    n|no|false|0) return 1 ;;
    *) die "请输入 y 或 n。" ;;
  esac
}

escape_env() {
  local value="$1"
  value="${value//$'\n'/}"
  value="${value//$'\r'/}"
  printf '%s' "$value"
}

yaml_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "未找到命令：$1"
}

compose() {
  docker compose --env-file "$ENV_FILE" "$@"
}

check_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'WARNING: 本机端口 %s 已被占用，docker compose up 可能失败。\n' "$port" >&2
  fi
}

check_npm_package() {
  local package="$1"
  local registry="$2"
  info "检查 npm 镜像源 ${registry} 是否可获取 ${package}"
  npm view "$package" version --registry="$registry" >/dev/null
}

check_docker() {
  require_command docker
  docker info >/dev/null 2>&1 || die "Docker 未启动或当前用户无法访问 Docker。"
  docker compose version >/dev/null 2>&1 || die "当前 Docker 不支持 'docker compose'。"
}

main() {
  cd "$ROOT_DIR"

  info "检查 Docker 环境"
  check_docker
  check_port 13306
  check_port 8000
  check_port 8080

  mkdir -p docker/workspaces data

  printf '\n请选择要内置安装并默认使用的 Agent：\n'
  printf '  1) codex\n'
  printf '  2) claude code\n'
  local agent_choice
  read -r -p '输入序号 [1]: ' agent_choice
  agent_choice="${agent_choice:-1}"

  local selected_agent install_codex install_claude default_model
  case "$agent_choice" in
    1|codex|Codex|CODEX)
      selected_agent="codex"
      install_codex="true"
      install_claude="false"
      default_model="gpt-5-codex"
      ;;
    2|claude|Claude|CLAUDE)
      selected_agent="claude"
      install_codex="false"
      install_claude="true"
      default_model="sonnet"
      ;;
    *)
      die "未知 Agent 选择：${agent_choice}"
      ;;
  esac

  local npm_registry pip_index pip_host apt_mirror
  npm_registry="$(prompt_default 'npm 镜像源' "$DEFAULT_NPM_REGISTRY")"
  pip_index="$(prompt_default 'pip 镜像源' "$DEFAULT_PIP_INDEX_URL")"
  pip_host="$(prompt_default 'pip trusted-host' "$DEFAULT_PIP_TRUSTED_HOST")"
  apt_mirror="$(prompt_default 'apt Debian 镜像源' "$DEFAULT_APT_MIRROR")"

  if ! command -v npm >/dev/null 2>&1; then
    printf 'WARNING: 本机没有 npm，跳过 npm 镜像源预检查；Docker 构建时仍会在容器内安装。\n' >&2
  else
    if [[ "$selected_agent" == "codex" ]]; then
      check_npm_package "@openai/codex" "$npm_registry" || die "npm 镜像源无法获取 @openai/codex。"
    else
      check_npm_package "@anthropic-ai/claude-code" "$npm_registry" || die "npm 镜像源无法获取 @anthropic-ai/claude-code。"
    fi
  fi

  local base_url api_key model workspace_mount host_root allowed_roots
  base_url="$(prompt_default 'Agent API Base URL' '')"
  api_key="$(prompt_secret 'Agent API Key')"
  [[ -n "$api_key" ]] || die "API Key 不能为空。"
  model="$(prompt_default 'Agent 模型名' "$default_model")"

  workspace_mount="$(prompt_default '宿主机工作区挂载目录' "${ROOT_DIR}/docker/workspaces")"
  mkdir -p "$workspace_mount"
  host_root="$(prompt_default '额外挂载宿主机可浏览根目录（留空则只允许 /workspaces 和 /app/data/workspaces）' '')"
  allowed_roots="/workspaces,/app/data/workspaces"
  if [[ -n "$host_root" ]]; then
    [[ -d "$host_root" ]] || die "额外挂载宿主机可浏览根目录不存在：$host_root"
    allowed_roots="${allowed_roots},${host_root}"
  fi

  local yolo
  if yes_no '是否开启最高权限模式（Codex YOLO / Claude bypassPermissions）' y; then
    yolo="true"
  else
    yolo="false"
  fi

  local start_after_build
  if yes_no '构建完成后是否自动启动服务' y; then
    start_after_build="true"
  else
    start_after_build="false"
  fi

  info "写入本地 Docker 环境配置：${ENV_FILE}"
  umask 077
  {
    printf 'AICM_SELECTED_AGENT=%s\n' "$(escape_env "$selected_agent")"
    printf 'AICM_AGENT_BASE_URL=%s\n' "$(escape_env "$base_url")"
    printf 'AICM_AGENT_API_KEY=%s\n' "$(escape_env "$api_key")"
    printf 'AICM_AGENT_MODEL=%s\n' "$(escape_env "$model")"
    printf 'AICM_AGENT_YOLO=%s\n' "$yolo"
    printf 'AICM_CODEX_PROVIDER=aicm\n'
    printf 'INSTALL_CODEX=%s\n' "$install_codex"
    printf 'INSTALL_CLAUDE_CODE=%s\n' "$install_claude"
    printf 'NPM_REGISTRY=%s\n' "$(escape_env "$npm_registry")"
    printf 'PIP_INDEX_URL=%s\n' "$(escape_env "$pip_index")"
    printf 'PIP_TRUSTED_HOST=%s\n' "$(escape_env "$pip_host")"
    printf 'APT_MIRROR=%s\n' "$(escape_env "$apt_mirror")"
    printf 'NODE_IMAGE=%s\n' "$DEFAULT_NODE_IMAGE"
    printf 'PYTHON_IMAGE=%s\n' "$DEFAULT_PYTHON_IMAGE"
    printf 'WEB_NODE_IMAGE=%s\n' "$DEFAULT_WEB_NODE_IMAGE"
    printf 'NGINX_IMAGE=%s\n' "$DEFAULT_NGINX_IMAGE"
    printf 'MYSQL_IMAGE=%s\n' "$DEFAULT_MYSQL_IMAGE"
    printf 'AICM_ALLOWED_WORKSPACE_ROOTS=%s\n' "$allowed_roots"
    printf 'AICM_HOST_WORKSPACE_DIR=%s\n' "$(escape_env "$workspace_mount")"
  } > "$ENV_FILE"

  if [[ -n "$host_root" ]]; then
    info "写入本地 Docker 挂载覆盖配置：${OVERRIDE_FILE}"
    {
      printf '# Generated by build-docker.sh. Do not commit this file.\n'
      printf 'services:\n'
      printf '  server:\n'
      printf '    volumes:\n'
      printf '      - %s\n' "$(yaml_quote "${host_root}:${host_root}")"
    } > "$OVERRIDE_FILE"
  else
    rm -f "$OVERRIDE_FILE"
  fi

  info "停止旧容器"
  compose down --remove-orphans

  info "构建 Docker 镜像"
  compose build

  if [[ "$start_after_build" == "true" ]]; then
    info "启动 Docker 服务"
    compose up -d
    info "服务已启动"
    printf '前端地址: http://127.0.0.1:8080\n'
    printf '后端地址: http://127.0.0.1:8000\n'
    printf '查看日志: docker compose --env-file %s logs -f\n' "$ENV_FILE"
  else
    info "构建完成，未启动服务"
    printf '启动命令: docker compose --env-file %s up -d\n' "$ENV_FILE"
  fi
}

main "$@"
