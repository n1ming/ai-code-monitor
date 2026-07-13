CREATE DATABASE IF NOT EXISTS ai_code_monitor
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ai_code_monitor;

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
