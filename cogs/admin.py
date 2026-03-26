"""Admin cog - handles administrative commands."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from discord_bot import BotConfig, ModerationBot

log = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Cog for administrative commands."""

    def __init__(self, bot: ModerationBot) -> None:
        self.bot = bot
        self.config: BotConfig = bot.config
        log.info("Admin cog initialized")

    @commands.command(name="shutdown")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.config.admin_user_ids)
    async def shutdown(self, ctx: commands.Context[Any]) -> None:
        """Shutdown the bot (admin only)."""
        log.warning("Shutdown requested by %s (ID: %s)", ctx.author.name, ctx.author.id)
        await ctx.send("👋 Shutting down...")
        await self.bot.close()
        sys.exit(0)

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="reload",
        description="Reload a cog (admin only)",
    )
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.config.admin_user_ids)
    async def reload(self, ctx: commands.Context[Any], cog: str) -> None:
        """Reload a cog without restarting the bot.

        Args:
            ctx: The command context.
            cog: The cog name (e.g. 'general', 'moderation', 'admin').
        """
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"✅ Successfully reloaded `{cog}` cog", ephemeral=True)
            log.info("Cog '%s' reloaded by %s (ID: %s)", cog, ctx.author.name, ctx.author.id)
        except commands.ExtensionNotFound:
            await ctx.send(f"❌ Cog `{cog}` not found", ephemeral=True)
        except commands.ExtensionNotLoaded:
            await ctx.send(f"❌ Cog `{cog}` is not loaded", ephemeral=True)
        except commands.ExtensionFailed as exc:
            await ctx.send(f"❌ Failed to reload `{cog}`: {exc}", ephemeral=True)
            log.error("Failed to reload cog '%s': %s", cog, exc, exc_info=True)

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="sync",
        description="Sync slash commands (admin only)",
    )
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.config.admin_user_ids)
    async def sync(self, ctx: commands.Context[Any]) -> None:
        """Manually sync slash commands with Discord."""
        await ctx.send("🔄 Syncing commands...", ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(
                f"✅ Synced {len(synced)} command(s): {[cmd.name for cmd in synced]}",
                ephemeral=True,
            )
            log.info(
                "Commands synced by %s (ID: %s): %d commands",
                ctx.author.name,
                ctx.author.id,
                len(synced),
            )
        except discord.HTTPException as exc:
            await ctx.send(f"❌ Failed to sync commands: HTTP {exc.status}", ephemeral=True)
            log.error("Failed to sync commands: %s", exc, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    """Load the admin cog."""
    await bot.add_cog(AdminCog(bot))  # type: ignore[arg-type]
