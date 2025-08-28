# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- Initial open-source preparation: bilingual READMEs, MIT License, contributing guide, .gitignore, env example.

## [0.1.0] - 2025-08-28
### Added
- New badge for recent news items (12h window) with backend `is_new` flag and frontend display.
- Sorting: prioritize created_at desc, then published_at desc.
- Sections management UI: enable/disable, configure, manual fetch.
- Background translation scheduler (MyMemory, Gemini optional).
- Scripts: migrate_db.py, check_routes.py, check_sections.py.

### Changed
- Improved README (CN/EN) with quick start and configuration.

### Fixed
- Addressed "new data not visible after fetch" by changing ordering and adding badge.