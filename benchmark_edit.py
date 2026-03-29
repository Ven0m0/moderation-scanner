import asyncio
import time


class MockUser:
    def __init__(self, id=1, bot=True):
        self.id = id
        self.bot = bot


class MockMessage:
    def __init__(self, content, author, delay=0.05):
        self.content = content
        self.author = author
        self._delay = delay

    async def edit(self, **kwargs):
        # Simulate network delay for editing a message
        await asyncio.sleep(self._delay)
        return self


class MockChannel:
    def __init__(self, messages, delay=0.1):
        self._messages = messages
        self._delay = delay

    async def history(self, limit=10):
        # Simulate network delay for fetching history
        await asyncio.sleep(self._delay)
        for msg in self._messages[:limit]:
            yield msg


async def benchmark():
    bot_user = MockUser(id=999, bot=True)
    messages = [
        MockMessage("Hello", MockUser(id=1, bot=False)),
        MockMessage("🔍 Scanning **test** (mode: both)...", bot_user),
        MockMessage("Another message", MockUser(id=2, bot=False)),
    ]
    channel = MockChannel(messages)

    # 1. Baseline: Fetch history and edit
    start_baseline = time.perf_counter()
    async for msg in channel.history(limit=10):
        if msg.author == bot_user and msg.content.startswith("🔍"):
            await msg.edit(content="Done!")
            break
    end_baseline = time.perf_counter()
    baseline_time = end_baseline - start_baseline

    # 2. Optimized: Direct edit using stored reference
    start_optimized = time.perf_counter()
    status_message = messages[1]  # Simulating saving the message from `await ctx.send()`
    await status_message.edit(content="Done!")
    end_optimized = time.perf_counter()
    optimized_time = end_optimized - start_optimized

    print(f"Baseline Time (History + Edit): {baseline_time:.4f}s")
    print(f"Optimized Time (Direct Edit): {optimized_time:.4f}s")
    print(f"Improvement: {(baseline_time - optimized_time) / baseline_time * 100:.2f}% faster")


if __name__ == "__main__":
    asyncio.run(benchmark())
