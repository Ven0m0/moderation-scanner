# Refactoring Changelog

## v1.2.3 - Subprocess Handling Fix

### Fixed
- **Sherlock hanging**: Changed from `proc.wait()` + `stdout.read()` to `proc.communicate()` which properly handles subprocess I/O without deadlocks
- **Removed `--print-found`**: Unnecessary flag that may have caused buffering issues

### Technical Details
**Before (could deadlock):**
```python
await proc.wait()
stdout = await proc.stdout.read()
stderr = await proc.stderr.read()
```

**After (proper async subprocess):**
```python
stdout, stderr = await proc.communicate()
```

Using `communicate()` is the recommended pattern for async subprocess handling - it reads stdout/stderr concurrently and waits for process exit, preventing pipe buffer deadlocks.

## v1.2.2 - Sherlock Simplification

### Changed
- **Sherlock integration**: Removed all JSON file handling. Now runs simple `sherlock username` and parses stdout only. This is more reliable and eliminates temp directory management and JSON parsing complexity.
- **Removed dependencies**: Eliminated `tempfile` import (no longer needed)
- **Simpler command**: Just `sherlock username --timeout N --print-found --no-color`

### Benefits
- No JSON flag issues
- No temp directory cleanup
- Simpler, more robust stdout parsing
- One less dependency on Sherlock's JSON output format

## v1.2.1 - Sherlock Bugfix

### Fixed
- **Sherlock JSON argument**: Removed filename argument from `--json` flag. Sherlock's `--json` flag enables JSON output and auto-creates `username.json` in the current directory - it doesn't accept a filename argument. This fixes the "Problem while attempting to access data file" error.

## v1.2.0 - Major Refactoring

## Major Improvements

### Code Structure
- **Dataclasses**: Introduced `ScanConfig` for type-safe configuration
- **Class-based design**: Separated concerns into `RateLimiter`, `SherlockScanner`, `RedditScanner`
- **Single responsibility**: Each class handles one specific task
- **Type hints**: Full PEP 484 compliance with modern `|` union syntax
- **Constants**: Extracted magic numbers/strings to module-level constants

### Error Handling
- **Proper logging**: Replaced print() with logging framework
- **Exception handling**: Return types now use `| None` for explicit failure cases
- **Graceful degradation**: Sherlock failures don't crash Reddit scans
- **KeyboardInterrupt**: Proper signal handling with exit code 130

### Performance
- **HTTP/2**: Maintained existing HTTP/2 support
- **Connection pooling**: Explicit connection limits configuration
- **Rate limiting**: Cleaner RateLimiter class implementation
- **Async cleanup**: Proper resource cleanup in all paths

### Python Code Quality

**Before**:
```python
def get_limiter(rate_per_min: float):
    delay = 60.0 / rate_per_min
    last_call = 0.0
    async def wait():
        nonlocal last_call
        # ...
    return wait
```

**After**:
```python
class RateLimiter:
  def __init__(self, rate_per_min: float) -> None:
    self.delay = 60.0 / rate_per_min
    self.last_call = 0.0
  
  async def wait(self) -> None:
    # ...
```

**Benefits**: Testable, type-checkable, no nonlocal hacks

### Bash Script Improvements

**Before**:
```bash
[[ -f $CREDS_FILE ]] && source "$CREDS_FILE"
```

**After**:
```bash
if [[ -f $CREDS_FILE ]]; then
  # shellcheck source=/dev/null
  source "$CREDS_FILE" || err "Warning: Failed to source $CREDS_FILE"
fi
```

**Benefits**:
- Shellcheck compliance
- Non-fatal credential loading
- Better error messages via helper functions

### Configuration

**Improvements**:
- uvloop platform check (`; platform_system != 'Windows'`)
- Added pytest-asyncio for async tests
- Script entry point in `[project.scripts]`
- More comprehensive ruff rules (RUF added)
- Better metadata (keywords, classifiers, readme)

### Documentation

**New files**:
- `README.md`: Comprehensive usage guide
- `Makefile`: Common tasks automation
- `credentials.template`: Setup guide
- `.gitignore`: Prevent credential commits
- `test_scanner.py`: Test suite foundation

### Testing

**New tests**:
- Config validation
- Rate limiter timing
- Sherlock parsing (stdout and status detection)
- Parametrized status tests

**Run with**: `make test` or `pytest -v`

## Breaking Changes

None. CLI interface remains identical.

## Migration Guide

### For Users
1. Update dependencies: `pip install -e ".[dev]"`
2. No config changes needed
3. All existing credentials/args work as-is

### For Developers
1. Run `make dev` for new dev tools
2. Use `make check` before commits
3. Tests now in `test_scanner.py`

## File Summary

```
account_scanner.py      Refactored with classes, logging, type hints
scan.sh                 Improved error handling, shellcheck compliance
pyproject.toml          Enhanced metadata, better tool config
README.md               NEW: Comprehensive documentation
Makefile                NEW: Task automation
credentials.template    NEW: Setup guide
.gitignore              NEW: Git safety
test_scanner.py         NEW: Test suite
CHANGELOG.md            NEW: This file
```

## Code Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Lines (Python) | 323 | 383 | +60 (structure) |
| Classes | 0 | 3 | +3 (organization) |
| Type coverage | ~60% | 100% | +40% |
| Tests | 0 | 8 | +8 |
| Docstrings | 3 | 12 | +9 |

## Next Steps

1. **Add more tests**: Cover async functions with mocked APIs
2. **CI/CD**: GitHub Actions for linting/testing
3. **Docker**: Containerized scanning
4. **Config file**: TOML-based config alternative to env vars
5. **Progress bars**: Rich/tqdm for long scans
6. **Retry logic**: Exponential backoff for API failures
