with open("cogs/moderation.py") as f:
    content = f.read()

# Replace the initial send to store the message reference
content = content.replace(
    'await ctx.send(f"🔍 Scanning **{username}** (mode: {mode})...")',
    'status_message = await ctx.send(f"🔍 Scanning **{username}** (mode: {mode})...")',
)

# Replace the editing logic
old_edit_block = """            if ctx.interaction:
                await ctx.interaction.edit_original_response(content=None, embed=embed)
            else:
                async for msg in ctx.channel.history(limit=10):
                    if msg.author == self.bot.user and msg.content.startswith("🔍"):
                        await msg.edit(content=None, embed=embed)
                        break"""

new_edit_block = """            if ctx.interaction:
                await ctx.interaction.edit_original_response(content=None, embed=embed)
            else:
                await status_message.edit(content=None, embed=embed)"""

content = content.replace(old_edit_block, new_edit_block)

with open("cogs/moderation.py", "w") as f:
    f.write(content)
