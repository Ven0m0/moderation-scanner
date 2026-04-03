#!/usr/bin/env python3
"""Discord moderation bot for account scanning and OSINT research.

This bot uses a cogs-based architecture for modular command organization,
following the Python Discord Bot Template pattern.
"""

import asyncio
import logging
import os
import sys
from typing import Any

import discord
import uvloop
from discord.ext import commands

from account_scanner import close_http_client

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when bot configuration is invalid or incomplete."""


class BotConfig:
    """Bot configuration manager using environment variables."""

    def __init__(self) -> None:
        """Load configuration from environment variables."""
        self.discord_token = os.getenv("DISCORD_BOT_TOKEN")
        self.perspective_key = os.getenv("PERSPECTIVE_API_KEY")
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv(
            "REDDIT_USER_AGENT",
            "account-scanner-bot/1.3.0",
        )
        self.admin_user_ids = self._parse_admin_ids()
        self.log_channel_id = self._parse_log_channel()

    def _parse_admin_ids(self) -> set[int]:
        """Parse admin user IDs from ADMIN_USER_IDS environment variable."""
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        if not admin_ids_str:
            return set()
        try:
            return {int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()}
        except ValueError:
            log.warning("Invalid ADMIN_USER_IDS format, ignoring")
            return set()

    def _parse_log_channel(self) -> int | None:
        """Parse log channel ID from LOG_CHANNEL_ID environment variable."""
        channel_id = os.getenv("LOG_CHANNEL_ID")
        if not channel_id:
            return None
        try:
            return int(channel_id)
        except ValueError:
            log.warning("Invalid LOG_CHANNEL_ID format, ignoring")
            return None

    def validate(self) -> None:
        """Validate required configuration.

        Raises:
            ConfigurationError: If required configuration is missing.
        """
        if not self.discord_token:
            log.error("DISCORD_BOT_TOKEN environment variable is not set!")
            log.error("Please set DISCORD_BOT_TOKEN in your environment:")
            log.error("  export DISCORD_BOT_TOKEN=your_token_here")
            raise ConfigurationError("DISCORD_BOT_TOKEN is required")
        if not self.perspective_key:
            log.warning("PERSPECTIVE_API_KEY not set - Reddit toxicity scanning disabled")
        if not self.reddit_client_id or not self.reddit_client_secret:
            log.warning("Reddit credentials not set - Reddit scanning disabled")

    def has_reddit_config(self) -> bool:
        """Return True if all Reddit configuration fields are present."""
        return bool(self.perspective_key and self.reddit_client_id and self.reddit_client_secret)


class ModerationBot(commands.Bot):
    """Custom bot class with cog loading support."""

    # Any is required here: commands.Bot.__init__ lacks stubs and accepts
    # arbitrary kwargs (command_prefix, intents, help_command, …).
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = BotConfig()

    async def setup_hook(self) -> None:
        """Load all cogs on startup."""
        log.info("Loading cogs...")
        for cog in ("cogs.general", "cogs.moderation", "cogs.admin"):
            try:
                await self.load_extension(cog)
                log.info("✅ Loaded cog: %s", cog)
            except Exception as exc:
                log.error("❌ Failed to load cog %s: %s", cog, exc, exc_info=True)

    async def on_ready(self) -> None:
        """Sync slash commands once the bot is fully connected."""
        assert self.user is not None  # Always set when on_ready fires
        log.info("=" * 60)
        log.info("Bot ready: %s (ID: %s)", self.user.name, self.user.id)
        log.info("Connected to %d guilds", len(self.guilds))
        try:
            log.info("Syncing slash commands...")
            synced = await self.tree.sync()
            log.info(
                "✅ Synced %d slash command(s): %s",
                len(synced),
                [cmd.name for cmd in synced],
            )
        except discord.HTTPException as exc:
            log.error("❌ Failed to sync commands (HTTP %s): %s", exc.status, exc.text)
            log.error("This may be due to invalid application configuration")
        except discord.DiscordException as exc:
            log.error("❌ Failed to sync commands: %s", exc)
        log.info("=" * 60)

    async def on_command_error(
        self,
        ctx: commands.Context[Any],
        error: Exception,
    ) -> None:
        """Handle prefix command errors."""
        if isinstance(error, commands.CommandNotFound):
            return
        match error:
            case commands.MissingPermissions() | commands.CheckFailure():
                await ctx.send("❌ You don't have permission to use this command.")
            case commands.MissingRequiredArgument():
                await ctx.send(f"❌ Missing argument: {error.param.name}")
            case commands.BadArgument():
                await ctx.send(f"❌ Invalid argument: {error}")
            case commands.CommandOnCooldown():
                await ctx.send(f"⏱️ Cooldown: try again in {error.retry_after:.1f}s")
            case commands.CommandInvokeError():
                log.error(
                    "Command error in %s: %s", ctx.command, error.original, exc_info=error.original
                )
                await ctx.send("❌ An error occurred while processing your command.")
            case _:
                log.error("Command error in %s: %s", ctx.command, error, exc_info=error)
                await ctx.send("❌ An error occurred while processing your command.")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Handle slash command errors."""
        cmd_name = interaction.command.name if interaction.command else "unknown"

        async def _reply(msg: str) -> None:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

        match error:
            case discord.app_commands.CommandOnCooldown():
                await _reply(f"⏱️ Cooldown: try again in {error.retry_after:.1f}s")
            case discord.app_commands.MissingPermissions() | discord.app_commands.CheckFailure():
                await _reply("❌ You don't have permission to use this command.")
            case discord.app_commands.CommandInvokeError():
                log.error(
                    "App command error in %s: %s", cmd_name, error.original, exc_info=error.original
                )
                await _reply("❌ An error occurred while processing your command.")
            case _:
                log.error("App command error in %s: %s", cmd_name, error, exc_info=error)
                await _reply("❌ An error occurred while processing your command.")


async def _run_bot(config: BotConfig) -> None:
    """Create and run the bot within an async context manager for clean teardown."""
    intents = discord.Intents.default()
    intents.message_content = True
    bot = ModerationBot(command_prefix="!", intents=intents, help_command=None)
    try:
        async with bot:
            await bot.start(config.discord_token or "")
    finally:
        await close_http_client()
        log.info("Closed shared HTTP client.")


def main() -> None:
    """Main entry point for the bot."""
    config = BotConfig()
    try:
        config.validate()
    except ConfigurationError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)

    try:
        uvloop.install()
        log.info("uvloop installed for better async performance")
    except (ImportError, RuntimeError) as exc:
        log.warning("Failed to install uvloop, using default event loop: %s", exc)

    log.info("=" * 60)
    log.info("Discord Account Scanner Bot v1.3.0")
    log.info("Using Cogs-Based Architecture")
    log.info("=" * 60)
    log.info("Configuration:")
    log.info("  - Discord Token: %s", "✅ Set" if config.discord_token else "❌ Missing")
    log.info("  - Perspective API: %s", "✅ Set" if config.perspective_key else "❌ Missing")
    log.info("  - Reddit API: %s", "✅ Set" if config.has_reddit_config() else "❌ Missing")
    log.info(
        "  - Admin Users: %s",
        len(config.admin_user_ids) if config.admin_user_ids else "None",
    )
    log.info("=" * 60)
    log.info("Starting Discord bot...")

    try:
        asyncio.run(_run_bot(config))
    except discord.LoginFailure as exc:
        log.error("❌ Discord login failed - invalid token: %s", exc)
        log.error("Check your DISCORD_BOT_TOKEN environment variable")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired as exc:
        log.error("❌ Missing required Discord intents: %s", exc)
        log.error("Enable MESSAGE CONTENT intent in Discord Developer Portal:")
        log.error("  1. Go to https://discord.com/developers/applications")
        log.error("  2. Select your application → 'Bot' section")
        log.error("  3. Enable 'MESSAGE CONTENT INTENT' under Privileged Gateway Intents")
        sys.exit(1)
    except discord.HTTPException as exc:
        log.error("❌ Discord HTTP error: %s (status: %s)", exc.text, exc.status)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        sys.exit(0)
    except (OSError, RuntimeError, ValueError):
        log.exception("❌ Fatal error occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()
