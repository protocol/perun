### Added
- org_settings_audit.py audits a GitHub organization (2FA requirement, Actions token defaults, installed apps, outside collaborators, self-hosted runners) and every repo via repo_settings_audit; read-only GETs, and a 403 or missing field is a NOT CHECKED row naming the scope needed.
