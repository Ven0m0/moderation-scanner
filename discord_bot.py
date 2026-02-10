#!/usr/bin/env python3
"""Discord moderation bot for account scanning and OSINT research.

This bot uses a cogs-based architecture for modular command organization,
following the Python Discord Bot Template pattern.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

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
        """Parse admin user IDs from environment variable.

        Returns:
            Set of admin user IDs.
        """
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        if not admin_ids_str:
            return set()
        try:
            return {int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()}
        except ValueError:
            log.warning("Invalid ADMIN_USER_IDS format, ignoring")
            return set()

    def _parse_log_channel(self) -> int | None:
        """Parse log channel ID from environment variable.

        Returns:
            Log channel ID or None if not set.
        """
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
        """Check if Reddit configuration is complete.

        Returns:
            True if all Reddit configuration is present.
        """
        return bool(self.perspective_key and self.reddit_client_id and self.reddit_client_secret)


class ModerationBot(commands.Bot):
    """Custom bot class with cog loading support."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the bot.

        Args:
            *args: Positional arguments to pass to commands.Bot.
            **kwargs: Keyword arguments to pass to commands.Bot.
        """
        super().__init__(*args, **kwargs)
        self.config = BotConfig()

    async def setup_hook(self) -> None:
        """Called when the bot is setting up.

        This is where we load all cogs.
        """
        log.info("Loading cogs...")

        # Load all cogs from the cogs directory
        cogs_to_load = ["cogs.general", "cogs.moderation", "cogs.admin"]

        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                log.info("✅ Loaded cog: %s", cog)
            except Exception as e:
                log.error("❌ Failed to load cog %s: %s", cog, e, exc_info=True)

    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        log.info("=" * 60)
        log.info("Bot ready: %s (ID: %s)", self.user.name, self.user.id)
        log.info("Connected to %d guilds", len(self.guilds))

        # Sync slash commands
        try:
            log.info("Syncing slash commands...")
            synced = await self.tree.sync()
            log.info(
                "✅ Synced %d slash command(s): %s",
                len(synced),
                [cmd.name for cmd in synced],
            )
        except discord.HTTPException as e:
            log.error("❌ Failed to sync commands (HTTP %s): %s", e.status, e.text)
            log.error("This may be due to invalid application configuration")
        except discord.DiscordException as e:
            log.error("❌ Failed to sync commands: %s", e)

        log.info("=" * 60)

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handle command errors.

        Args:
            ctx: The command context.
            error: The error that occurred.
        """
        # Ignore command not found errors
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument: {error}")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ Cooldown: try again in {error.retry_after:.1f}s")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
            log.error("Command error in %s: %s", ctx.command, error.original, exc_info=error.original)
            await ctx.send("❌ An error occurred while processing your command.")
        else:
            log.error("Command error in %s: %s", ctx.command, error, exc_info=error)
            await ctx.send("❌ An error occurred while processing your command.")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Handle app command (slash command) errors.

        Args:
            interaction: The interaction that triggered the error.
            error: The error that occurred.
        """
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏱️ Cooldown: try again in {error.retry_after:.1f}s",
                ephemeral=True,
            )
        elif isinstance(error, discord.app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True,
            )
        elif isinstance(error, discord.app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True,
            )
        elif isinstance(error, discord.app_commands.CommandInvokeError):
            log.error(
                "App command error in %s: %s",
                interaction.command.name if interaction.command else "unknown",
                error.original,
                exc_info=error.original,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ An error occurred while processing your command.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ An error occurred while processing your command.",
                    ephemeral=True,
                )
        else:
            log.error(
                "App command error in %s: %s",
                interaction.command.name if interaction.command else "unknown",
                error,
                exc_info=error,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ An error occurred while processing your command.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ An error occurred while processing your command.",
                    ephemeral=True,
                )


def main() -> None:
    """Main entry point for the bot."""
    # Initialize configuration
    config = BotConfig()

    # Validate configuration
    try:
        config.validate()
    except ConfigurationError as e:
        log.error("Configuration error: %s", e)
        sys.exit(1)

    # Install uvloop for better performance
    try:
        uvloop.install()
        log.info("uvloop installed for better async performance")
    except (ImportError, RuntimeError) as e:
        log.warning("Failed to install uvloop, using default event loop: %s", e)

    # Log startup information
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

    # Bot setup
    intents = discord.Intents.default()
    intents.message_content = True
    bot = ModerationBot(command_prefix="!", intents=intents, help_command=None)

    # Start the bot
    log.info("Starting Discord bot...")
    try:
        bot.run(config.discord_token, log_handler=None)
    except discord.LoginFailure as e:
        log.error("❌ Discord login failed - invalid token: %s", e)
        log.error("Check your DISCORD_BOT_TOKEN environment variable")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired as e:
        log.error("❌ Missing required Discord intents: %s", e)
        log.error("Enable MESSAGE CONTENT intent in Discord Developer Portal:")
        log.error("  1. Go to https://discord.com/developers/applications")
        log.error("  2. Select your application")
        log.error("  3. Go to 'Bot' section")
        log.error("  4. Enable 'MESSAGE CONTENT INTENT' under Privileged Gateway Intents")
        sys.exit(1)
    except discord.HTTPException as e:
        log.error("❌ Discord HTTP error: %s (status: %s)", e.text, e.status)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        sys.exit(0)
    except (OSError, RuntimeError, ValueError):
        log.exception("❌ Fatal error occurred")
        sys.exit(1)
    finally:
        log.info("Cleaning up tasks...")
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                # Close shared HTTP client
                try:
                    loop.run_until_complete(close_http_client())
                    log.info("Closed shared HTTP client.")
                except Exception as e:
                    log.warning("Error closing HTTP client: %s", e)

                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                log.info("Closing the event loop.")
                loop.close()
        except (RuntimeError, ValueError) as e:
            log.warning("Error during cleanup: %s", e)


if __name__ == "__main__":
    main()
