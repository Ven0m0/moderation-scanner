"""Admin cog - handles administrative commands."""

import logging
import sys

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Cog for administrative commands."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the admin cog.

        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot
        self.config = bot.config  # Access config from bot instance
        log.info("Admin cog initialized")

    @commands.command(name="shutdown")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.config.admin_user_ids)
    async def shutdown(self, ctx: commands.Context) -> None:
        """Shutdown the bot (admin only).

        Args:
            ctx: The command context.
        """
        log.warning("Shutdown requested by %s (ID: %s)", ctx.author.name, ctx.author.id)
        await ctx.send("👋 Shutting down...")
        await self.bot.close()
        sys.exit(0)

    @commands.hybrid_command(
        name="reload",
        description="Reload a cog (admin only)",
    )
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.config.admin_user_ids)
    async def reload(self, ctx: commands.Context, cog: str) -> None:
        """Reload a cog without restarting the bot.

        Args:
            ctx: The command context.
            cog: The name of the cog to reload (e.g., 'general', 'moderation', 'admin').
        """
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"✅ Successfully reloaded `{cog}` cog", ephemeral=True)
            log.info("Cog '%s' reloaded by %s (ID: %s)", cog, ctx.author.name, ctx.author.id)
        except commands.ExtensionNotFound:
            await ctx.send(f"❌ Cog `{cog}` not found", ephemeral=True)
        except commands.ExtensionNotLoaded:
            await ctx.send(f"❌ Cog `{cog}` is not loaded", ephemeral=True)
        except commands.ExtensionFailed as e:
            await ctx.send(f"❌ Failed to reload `{cog}`: {e}", ephemeral=True)
            log.error("Failed to reload cog '%s': %s", cog, e, exc_info=True)

    @commands.hybrid_command(
        name="sync",
        description="Sync slash commands (admin only)",
    )
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.config.admin_user_ids)
    async def sync(self, ctx: commands.Context) -> None:
        """Manually sync slash commands with Discord.

        Args:
            ctx: The command context.
        """
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
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to sync commands: HTTP {e.status}", ephemeral=True)
            log.error("Failed to sync commands: %s", e, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    """Load the admin cog.

    Args:
        bot: The Discord bot instance.
    """
    await bot.add_cog(AdminCog(bot))
