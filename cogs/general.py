"""General cog - handles general bot commands like health and help."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord
from discord.ext import commands

from account_scanner import SherlockScanner

if TYPE_CHECKING:
    from discord_bot import BotConfig, ModerationBot

log = logging.getLogger(__name__)

SCANS_DIR: Final = Path("./scans")


class GeneralCog(commands.Cog, name="General"):
    """Cog for general bot commands."""

    def __init__(self, bot: ModerationBot) -> None:
        self.bot = bot
        self.config: BotConfig = bot.config
        log.info("General cog initialized")

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="health",
        description="Check bot health and service availability",
    )
    async def health(self, ctx: commands.Context[Any]) -> None:
        """Check bot health and service availability."""
        embed = discord.Embed(
            title="Bot Health Check",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        latency_ms = self.bot.latency * 1000
        latency_status = "🟢" if latency_ms < 200 else "🟡" if latency_ms < 500 else "🔴"
        embed.add_field(
            name="Bot Status",
            value=(
                f"{latency_status} Latency: {latency_ms:.0f}ms\n"
                f"🌐 Guilds: {len(self.bot.guilds)}\n"
                f"👥 Users: {len(self.bot.users)}"
            ),
            inline=False,
        )
        services = [
            f"{'✅' if await SherlockScanner.available() else '❌'} Sherlock OSINT",
            f"{'✅' if self.config.perspective_key else '❌'} Perspective API",
            f"{'✅' if self.config.has_reddit_config() else '❌'} Reddit API",
        ]
        embed.add_field(name="Services", value="\n".join(services), inline=False)
        embed.add_field(
            name="System",
            value=f"📁 Scans directory: `{SCANS_DIR.absolute()}`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(  # type: ignore[arg-type]
        name="help",
        description="Show help and usage information",
    )
    async def help(self, ctx: commands.Context[Any]) -> None:
        """Show help and usage information."""
        embed = discord.Embed(
            title="Account Scanner Bot - Help",
            description=(
                "Multi-source account scanner for moderation\n\n"
                "**This bot uses slash commands!** Type `/` to see available commands."
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="/scan <username> [mode]",
            value="Scan a user across platforms\nModes: sherlock, reddit, both",
            inline=False,
        )
        embed.add_field(name="/health", value="Check bot health and services", inline=False)
        embed.add_field(name="/help", value="Show this help message", inline=False)
        embed.set_footer(text="account-scanner v1.3.0 • Cogs System Enabled")

        if ctx.interaction:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Load the general cog."""
    await bot.add_cog(GeneralCog(bot))  # type: ignore[arg-type]
