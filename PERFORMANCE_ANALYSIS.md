# Performance Analysis Report

## Executive Summary

This document identifies performance anti-patterns, potential N+1 queries, inefficient algorithms, and optimization opportunities in the moderation-scanner codebase.

**Overall Assessment:** The codebase shows good async practices and proper use of modern Python patterns. However, several optimization opportunities exist, particularly around HTTP connection pooling, caching, and memory management.

---

## Critical Issues (High Impact)

### 1. **HTTP Client Recreation on Every Scan** ⚠️ HIGH IMPACT
**Location:** `account_scanner.py:358-362`

```python
async with httpx.AsyncClient(
    http2=True,
    limits=HTTP2_LIMITS,
    headers=headers,
) as client:
```

**Issue:** A new HTTP client is created for every scan operation. This means:
- No connection reuse between scans
- TCP/TLS handshake overhead on every scan
- Lost HTTP/2 connection pooling benefits
- Wasted memory allocating/deallocating clients

**Impact:** For bots handling multiple scan requests, this creates significant overhead. Each Perspective API call requires a new connection setup.

**Recommendation:**
- Create a module-level or class-level shared `httpx.AsyncClient`
- Reuse the same client across all scans
- Properly manage client lifecycle (create on startup, close on shutdown)

**Estimated Performance Gain:** 20-40% reduction in Reddit scan latency for concurrent scans

---

### 2. **No Result Caching** ⚠️ HIGH IMPACT
**Location:** Entire scanner architecture

**Issue:** If the same username is scanned multiple times (common in moderation scenarios), all data is re-fetched:
- Reddit API calls repeated
- Perspective API toxicity analysis repeated
- Sherlock subprocess re-executed
- Same API quota consumed

**Impact:**
- Wasted API quota (especially Perspective API which has limits)
- Unnecessary load on external services
- Slower response times for duplicate requests
- Higher costs if using paid API tiers

**Recommendation:**
- Implement TTL-based caching (e.g., 5-15 minutes)
- Use `cachetools` or `aiocache` library
- Cache at the result level (post-processing)
- Consider Redis for distributed bot deployments

**Example:**
```python
from cachetools import TTLCache
from asyncio import Lock

# Module-level cache with 15-minute TTL
_cache = TTLCache(maxsize=100, ttl=900)
_cache_lock = Lock()
```

**Estimated Performance Gain:** 100% elimination of redundant work for cached requests

---

### 3. **Inefficient Cooldown Cleanup Algorithm** ⚠️ MEDIUM IMPACT
**Location:** `discord_bot.py:384-387`

```python
if len(_scan_cooldowns) > 1000:
    expired = [uid for uid, ts in _scan_cooldowns.items() if now - ts >= COOLDOWN_SECONDS]
    for uid in expired:
        del _scan_cooldowns[uid]
```

**Issues:**
- **O(n) iteration** over all 1000+ entries when threshold is hit
- List comprehension creates intermediate list in memory
- Cleanup only triggers at 1000 entries (can grow unbounded until then)
- Blocking operation in async context

**Impact:**
- Periodic latency spikes when cleanup runs
- Memory growth between cleanup cycles
- Poor scalability for high-traffic bots

**Recommendation:**
Use a more efficient data structure:

```python
from collections import deque
from typing import Deque, Tuple

# Store as (timestamp, user_id) sorted by time
_scan_cooldowns: dict[int, float] = {}
_cooldown_queue: Deque[Tuple[float, int]] = deque()

def check_cooldown(user_id: int) -> tuple[bool, float]:
    now = asyncio.get_event_loop().time()

    # Lazy cleanup: Remove expired entries from front of queue
    while _cooldown_queue and now - _cooldown_queue[0][0] >= COOLDOWN_SECONDS:
        ts, uid = _cooldown_queue.popleft()
        if uid in _scan_cooldowns and _scan_cooldowns[uid] == ts:
            del _scan_cooldowns[uid]

    # Check cooldown
    if user_id in _scan_cooldowns:
        elapsed = now - _scan_cooldowns[user_id]
        if elapsed < COOLDOWN_SECONDS:
            return True, COOLDOWN_SECONDS - elapsed
    return False, 0.0

def update_cooldown(user_id: int) -> None:
    now = asyncio.get_event_loop().time()
    _scan_cooldowns[user_id] = now
    _cooldown_queue.append((now, user_id))
```

**Estimated Performance Gain:** Eliminates O(n) spikes, reduces memory by 30-50%

---

## Medium Priority Issues

### 4. **String Concatenation in Loops** ⚠️ MEDIUM IMPACT
**Location:** `discord_bot.py:256-312` (`_send_detailed_results`)

```python
for account in results["sherlock"]:
    line = f"{account['platform']}: {account['url']}\n"
    if len(current_chunk) + len(line) + 3 > 1900:
        current_chunk += "```"
        chunks.append(current_chunk)
        current_chunk = "```\n"
    current_chunk += line
```

**Issue:** String concatenation using `+=` in loops creates new string objects on each iteration (strings are immutable in Python).

**Impact:** For large result sets (100+ Sherlock results), this creates unnecessary allocations and memory copies.

**Recommendation:**
```python
# Use list and join
lines = []
for account in results["sherlock"]:
    lines.append(f"{account['platform']}: {account['url']}")
sherlock_text = f"**🔎 Sherlock OSINT Results for {username}:**\n```\n" + "\n".join(lines) + "```"
```

**Estimated Performance Gain:** 15-25% faster for large result sets (100+ items)

---

### 5. **Duplicate Command Logic** ⚠️ MEDIUM IMPACT (Maintainability)
**Location:** `discord_bot.py:134-254` and `discord_bot.py:416-544`

**Issue:** The prefix command (`!scan`) and slash command (`/scan`) contain nearly identical logic (~120 lines duplicated). This is not a runtime performance issue but creates:
- Double maintenance burden
- Risk of logic divergence
- Code bloat

**Recommendation:** Extract shared logic into a common function:

```python
async def _perform_scan(username: str, mode: str, interaction_or_ctx, is_interaction: bool):
    """Shared scan logic for both prefix and slash commands."""
    # All the scanning logic here
    pass

@bot.command(name="scan")
async def scan_user(ctx: commands.Context, username: str, mode: str = "both"):
    await _perform_scan(username, mode, ctx, is_interaction=False)

@bot.tree.command(name="scan")
async def scan_slash(interaction: discord.Interaction, username: str, mode: str):
    await _perform_scan(username, mode.value if mode else "both", interaction, is_interaction=True)
```

---

### 6. **No Batching for Reddit Items Fetching** ⚠️ LOW-MEDIUM IMPACT
**Location:** `account_scanner.py:327-339`

```python
async for c in user.comments.new(limit=cfg.comments):
    items.append(("comment", c.subreddit.display_name, c.body, c.created_utc))
async for s in user.submissions.new(limit=cfg.posts):
    items.append(("post", s.subreddit.display_name, f"{s.title}\n{s.selftext}", s.created_utc))
```

**Issue:** Comments and posts are fetched sequentially. While `async for` is used, the two loops run one after another.

**Impact:** Total fetch time = comment fetch time + post fetch time

**Recommendation:** Fetch concurrently:
```python
async def _fetch_comments(user, limit):
    items = []
    async for c in user.comments.new(limit=limit):
        items.append(("comment", c.subreddit.display_name, c.body, c.created_utc))
    return items

async def _fetch_posts(user, limit):
    items = []
    async for s in user.submissions.new(limit=limit):
        items.append(("post", s.subreddit.display_name, f"{s.title}\n{s.selftext}", s.created_utc))
    return items

# Then use gather:
comments_task = _fetch_comments(user, cfg.comments)
posts_task = _fetch_posts(user, cfg.posts)
comments, posts = await asyncio.gather(comments_task, posts_task)
items = comments + posts
```

**Estimated Performance Gain:** 30-50% reduction in Reddit fetch time

---

## Good Practices Observed ✅

### Excellent Async Patterns
1. **Batched Perspective API Calls** (`account_scanner.py:363-368`)
   - Uses `asyncio.gather()` to parallelize toxicity checks
   - Avoids N+1 query pattern
   - Properly awaits all results

2. **Async File I/O** (`account_scanner.py:393-396`)
   - Uses `aiofiles` for non-blocking file writes
   - Prevents blocking event loop

3. **HTTP/2 with Connection Limits** (`account_scanner.py:45`)
   - Enables HTTP/2 for multiplexing
   - Proper connection pool limits

4. **Rate Limiting Implementation** (`account_scanner.py:53-84`)
   - Token bucket algorithm
   - Shared limiter prevents API abuse
   - Async-friendly with `await asyncio.sleep()`

### Memory Management
- Uses generators where possible (`async for`)
- Limits result set sizes (max comments/posts)
- Streams Sherlock output instead of loading entirely

---

## Performance Anti-Patterns Summary

| Issue | Location | Impact | Fix Effort | Priority |
|-------|----------|--------|------------|----------|
| HTTP client recreation | account_scanner.py:358 | High | Medium | **Critical** |
| No caching | Architecture-wide | High | High | **Critical** |
| Cooldown cleanup | discord_bot.py:384 | Medium | Low | **High** |
| String concatenation | discord_bot.py:256-312 | Medium | Low | Medium |
| Code duplication | discord_bot.py | Low (maintainability) | Medium | Medium |
| Sequential Reddit fetch | account_scanner.py:327-339 | Low-Medium | Low | Medium |

---

## Potential N+1 Query Issues: ✅ None Found

The codebase does **NOT** exhibit classic N+1 query patterns:
- Perspective API calls are batched with `asyncio.gather()` ✅
- Reddit fetching uses streaming (async for) not individual calls ✅
- Sherlock runs once per username, not per platform ✅

---

## Scalability Concerns

### High-Traffic Bot Deployment
1. **Shared Rate Limiter:** Good! Prevents API quota exhaustion
2. **Memory Growth:** Cooldown dict needs improvement
3. **File I/O:** Writing scan results to local files won't scale horizontally (use S3/object storage)
4. **No Database:** Results aren't persisted; consider PostgreSQL for history

### Recommended Architecture for Scale
```
┌─────────────┐
│ Discord Bot │ ← Multiple instances (horizontal scaling)
└──────┬──────┘
       │
       ↓
┌──────────────┐
│ Redis Cache  │ ← Shared cache + rate limiter state
└──────┬───────┘
       │
       ↓
┌──────────────┐
│ PostgreSQL   │ ← Scan history, user profiles
└──────────────┘
```

---

## Recommended Implementation Order

1. **Phase 1 - Quick Wins (1-2 hours)**
   - Fix cooldown cleanup algorithm
   - Implement shared HTTP client
   - Add concurrent Reddit fetching

2. **Phase 2 - Caching (2-4 hours)**
   - Add in-memory TTL cache
   - Add cache headers to responses

3. **Phase 3 - Refactoring (4-8 hours)**
   - Extract duplicate command logic
   - Optimize string building in result formatting

4. **Phase 4 - Infrastructure (Optional, for scale)**
   - Add Redis for distributed caching
   - Implement PostgreSQL for persistence
   - Add monitoring/metrics (Prometheus)

---

## Benchmark Recommendations

To validate optimizations, measure:
1. **Scan latency:** Time from request to response
2. **API quota usage:** Calls per user scanned
3. **Memory footprint:** Bot RSS over 24 hours
4. **Concurrent scan capacity:** Max simultaneous scans before degradation

**Tools:**
- `pytest-benchmark` for Python microbenchmarks
- `memory_profiler` for memory analysis
- `py-spy` for profiling production bot
- Prometheus + Grafana for metrics

---

## Conclusion

The codebase demonstrates strong async foundations and avoids major performance pitfalls like N+1 queries. However, three critical optimizations would significantly improve performance and scalability:

1. **Shared HTTP client reuse** (biggest impact)
2. **Result caching** (reduces external API load)
3. **Improved cooldown management** (memory efficiency)

Implementing these changes would make the bot production-ready for high-traffic Discord servers and reduce operational costs.
