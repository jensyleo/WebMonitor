# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.2] - 2026-07-14

### Changed
- Install dependencies directly with `pip install requests colorama` instead
  of a `requirements.txt` file, which was removed.

### Docs
- Translated `SESSION_NOTES.md` to English, then merged its content into
  the README under Development > Design History and removed the
  standalone file.
- Removed the resolved license TODO item and closed the code-review
  pending item after a full review pass with no new issues found.
- Added an app screenshot to the README.

## [1.0.1] - 2026-07-13

### Added
- Initial public release: terminal-based HTTP/HTTPS availability monitor
  with colored output, DNS pre-check, redirect tracking, and automatic
  retries.
