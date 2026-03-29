import asyncio

class MockInteraction:
    def __init__(self):
        self.user = type('User', (), {'id': 1})()

    async def edit_original_response(self, content=None, embed=None):
        pass

class MockContext:
    def __init__(self, interaction=None):
        self.interaction = interaction
        self.author = type('User', (), {'id': 1, 'name': 'test'})()

    async def send(self, content):
        return type('Message', (), {'edit': self.mock_edit})()

    async def mock_edit(self, content=None, embed=None):
        pass

async def test_logic():
    ctx = MockContext()
    status_message = await ctx.send("🔍 Scanning...")
    await status_message.edit(content="Done")
    print("Test passed: message reference editing works.")

asyncio.run(test_logic())
