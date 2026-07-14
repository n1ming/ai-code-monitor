CREATE DATABASE IF NOT EXISTS ai_code_monitor
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ai_code_monitor;

CREATE TABLE IF NOT EXISTS workspaces (
  workspace_id VARCHAR(128) NOT NULL,
  name VARCHAR(255) NOT NULL,
  path TEXT NOT NULL,
  start_command TEXT NOT NULL,
  agent_command TEXT NOT NULL,
  poll_seconds INT NOT NULL DEFAULT 30,
  ai_can_edit BOOLEAN NOT NULL DEFAULT TRUE,
  initial_prompt TEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'idle',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS process_identities (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  process_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,
  workspace_id VARCHAR(128) NULL,
  display_name VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_process_identities_process_id (process_id),
  KEY ix_process_identities_process_id (process_id),
  KEY ix_process_identities_workspace_id (workspace_id),
  KEY ix_process_identities_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS process_links (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  workspace_id VARCHAR(128) NOT NULL,
  from_process_id VARCHAR(128) NOT NULL,
  to_process_id VARCHAR(128) NOT NULL,
  link_type VARCHAR(32) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_process_links_edge (workspace_id, from_process_id, to_process_id, link_type),
  KEY ix_process_links_workspace_id (workspace_id),
  KEY ix_process_links_from_process_id (from_process_id),
  KEY ix_process_links_to_process_id (to_process_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS process_runtime_instances (
  runtime_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  process_id VARCHAR(128) NOT NULL,
  workspace_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,
  os_pid INT NULL,
  pid_create_time VARCHAR(64) NULL,
  command TEXT NULL,
  cwd TEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'starting',
  stdin_channel VARCHAR(255) NULL,
  stdout_log TEXT NULL,
  stderr_log TEXT NULL,
  heartbeat_at TIMESTAMP NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  stopped_at TIMESTAMP NULL,
  PRIMARY KEY (runtime_id),
  KEY ix_process_runtime_instances_process_id (process_id),
  KEY ix_process_runtime_instances_workspace_id (workspace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS runtime_logs (
  log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  workspace_id VARCHAR(128) NOT NULL,
  process_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,
  level VARCHAR(32) NOT NULL DEFAULT 'INFO',
  log_type VARCHAR(64) NOT NULL DEFAULT 'event',
  content TEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (log_id),
  UNIQUE KEY uq_runtime_logs_content_hash (content_hash),
  KEY ix_runtime_logs_workspace_time (workspace_id, occurred_at),
  KEY ix_runtime_logs_workspace_role_time (workspace_id, role, occurred_at),
  KEY ix_runtime_logs_workspace_level_time (workspace_id, level, occurred_at),
  KEY ix_runtime_logs_process_time (process_id, occurred_at),
  KEY ix_runtime_logs_role (role),
  KEY ix_runtime_logs_level (level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS log_archives (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  workspace_id VARCHAR(128) NOT NULL,
  process_id VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL,
  archive_date DATE NOT NULL,
  file_path TEXT NOT NULL,
  line_count INT NOT NULL DEFAULT 0,
  size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_log_archives_workspace_date (workspace_id, archive_date),
  KEY ix_log_archives_process_date (process_id, archive_date),
  KEY ix_log_archives_role_date (role, archive_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS log_settings (
  id INT NOT NULL DEFAULT 1,
  archive_root TEXT NOT NULL,
  retention_days INT NOT NULL DEFAULT 30,
  default_log_limit INT NOT NULL DEFAULT 1000,
  sync_tail_lines INT NOT NULL DEFAULT 5000,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO log_settings (id, archive_root, retention_days, default_log_limit, sync_tail_lines)
VALUES (1, '', 30, 1000, 5000)
ON DUPLICATE KEY UPDATE id = id;
