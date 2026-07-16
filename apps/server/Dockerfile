ARG NODE_IMAGE=node:22-slim
ARG PYTHON_IMAGE=python:3.11-slim

FROM ${NODE_IMAGE} AS node-runtime

FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ARG APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG INSTALL_CODEX=true
ARG INSTALL_CLAUDE_CODE=false

WORKDIR /app

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN if [ -n "${APT_MIRROR}" ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}-security|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm config set registry "${NPM_REGISTRY}" \
    && if [ "${INSTALL_CODEX}" = "true" ]; then npm install -g @openai/codex; fi \
    && if [ "${INSTALL_CLAUDE_CODE}" = "true" ]; then npm install -g @anthropic-ai/claude-code; fi \
    && if [ "${INSTALL_CODEX}" = "true" ]; then codex --version; fi \
    && if [ "${INSTALL_CLAUDE_CODE}" = "true" ]; then claude --version; fi

COPY apps/server/requirements.txt /app/apps/server/requirements.txt
RUN if [ -n "${PIP_TRUSTED_HOST}" ]; then \
        pip install --retries 5 --timeout 120 --index-url "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" -r /app/apps/server/requirements.txt; \
    else \
        pip install --retries 5 --timeout 120 --index-url "${PIP_INDEX_URL}" -r /app/apps/server/requirements.txt; \
    fi

COPY apps/server /app/apps/server

EXPOSE 8000

CMD ["uvicorn", "apps.server.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
