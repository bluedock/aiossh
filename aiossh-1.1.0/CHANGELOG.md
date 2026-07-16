# Changelog

All notable changes to AIOSSH will be documented in this file.

## [1.1.0] - 2026-07-16

### Fixed
- **Critical**: `os.geteuid()` crash on Windows and non-POSIX systems in `validators.py` (port validation)
- Connection pool idle/total count accuracy after cleanup
- `stream_command` could hang indefinitely (added `asyncio.timeout`)
- `ParallelSCP` failed on systems without GNU `split` (now has graceful fallback)
- Minor race conditions in pool return logic
- Path traversal detection strengthened

### Added
- Minimum idle connection support in ConnectionPool
- Practical usage examples in the examples/ directory
- CHANGELOG.md
- Additional modules for broader feature coverage (file encryption, proxy, webhooks, Docker exec, session replay)

### Changed
- Reduced default chunk size in parallel transfers for compatibility
- Improved command streaming with timeout protection
- Updated documentation and examples
- Bumped version to 1.1.0

### Security
- Improved session name and path validation rules
- Added documentation about host key verification risks

## [1.0.0] - Initial Release

- Initial public release with core features
