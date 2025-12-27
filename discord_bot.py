#!/usr/bin/env python3
"""Discord moderation bot using account scanner."""
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Final

import discord
from discord.ext import commands
import uvloop

from account_scanner import ScanConfig, ScannerAPI, SherlockScanner

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Constants
MAX_SCAN_LENGTH: Final = 50  # Maximum username length
SCAN_TIMEOUT: Final = 300  # 5 minutes timeout for scans
SCANS_DIR: Final = Path("./scans")


class ConfigurationError(Exception):
    """Raised when bot configuration is invalid."""


class BotConfig:
    """Bot configuration from environment variables."""

    def __init__(self) -> None:
        self.discord_token = os.getenv("DISCORD_BOT_TOKEN")
        self.perspective_key = os.getenv("PERSPECTIVE_API_KEY")
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv(
            "REDDIT_USER_AGENT",
            "account-scanner-bot/1.2.3",
        )
        self.admin_user_ids = self._parse_admin_ids()
        self.log_channel_id = self._parse_log_channel()

    def _parse_admin_ids(self) -> set[int]:
        """Parse admin user IDs from environment."""
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        if not admin_ids_str:
            return set()
        try:
            return {int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()}
        except ValueError:
            log.warning("Invalid ADMIN_USER_IDS format, ignoring")
            return set()

    def _parse_log_channel(self) -> int | None:
        """Parse log channel ID from environment."""
        channel_id = os.getenv("LOG_CHANNEL_ID")
        if not channel_id:
            return None
        try:
            return int(channel_id)
        except ValueError:
            log.warning("Invalid LOG_CHANNEL_ID format, ignoring")
            return None

    def validate(self) -> None:
        """Validate required configuration."""
        if not self.discord_token:
            raise ConfigurationError("DISCORD_BOT_TOKEN is required")

        # Warn about optional configs
        if not self.perspective_key:
            log.warning("PERSPECTIVE_API_KEY not set - Reddit toxicity scanning disabled")
        if not self.reddit_client_id or not self.reddit_client_secret:
            log.warning("Reddit credentials not set - Reddit scanning disabled")

    def has_reddit_config(self) -> bool:
        """Check if Reddit configuration is complete."""
        return bool(
            self.perspective_key
            and self.reddit_client_id
            and self.reddit_client_secret
        )


# Initialize bot configuration
config = BotConfig()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready() -> None:
    """Called when bot is ready."""
    log.info("Bot ready: %s (ID: %s)", bot.user.name, bot.user.id)
    log.info("Connected to %d guilds", len(bot.guilds))

    # Create scans directory
    SCANS_DIR.mkdir(exist_ok=True)
    log.info("Scans directory: %s", SCANS_DIR.absolute())

    # Log configuration status
    log.info("Sherlock available: %s", SherlockScanner.available())
    log.info("Reddit scanning available: %s", config.has_reddit_config())


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    """Global error handler for commands."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {error}")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏱️ Cooldown: try again in {error.retry_after:.1f}s")
    else:
        log.error("Command error in %s: %s", ctx.command, error, exc_info=error)
        await ctx.send("❌ An error occurred while processing your command.")


@bot.command(name="scan")
@commands.has_permissions(moderate_members=True)
@commands.cooldown(1, 30, commands.BucketType.user)  # 1 scan per 30s per user
async def scan_user(ctx: commands.Context, username: str, mode: str = "both") -> None:
    """Scan a user across platforms.

    Usage: !scan <username> [sherlock|reddit|both]

    Examples:
        !scan johndoe
        !scan johndoe sherlock
        !scan johndoe reddit
        !scan johndoe both
    """
    # Validate inputs
    if len(username) > MAX_SCAN_LENGTH:
        await ctx.send(f"❌ Username too long (max {MAX_SCAN_LENGTH} characters)")
        return

    if mode not in ("sherlock", "reddit", "both"):
        await ctx.send("❌ Mode must be: sherlock, reddit, or both")
        return

    # Check if mode is available
    if mode in ("reddit", "both") and not config.has_reddit_config():
        await ctx.send("❌ Reddit scanning not configured on this bot")
        return

    if mode in ("sherlock", "both") and not SherlockScanner.available():
        await ctx.send("❌ Sherlock not available on this bot")
        return

    # Send initial status
    status_msg = await ctx.send(f"🔍 Scanning **{username}** (mode: {mode})...")

    # Log scan request
    log.info(
        "Scan requested by %s#%s (ID: %s) for user '%s' (mode: %s)",
        ctx.author.name,
        ctx.author.discriminator,
        ctx.author.id,
        username,
        mode,
    )

    # Create scan configuration
    scan_config = ScanConfig(
        username=username,
        mode=mode,
        api_key=config.perspective_key,
        client_id=config.reddit_client_id,
        client_secret=config.reddit_client_secret,
        user_agent=config.reddit_user_agent,
        output_reddit=SCANS_DIR / f"{username}_reddit.csv",
        output_sherlock=SCANS_DIR / f"{username}_sherlock.json",
        verbose=False,
    )

    try:
        # Run scan with timeout
        results = await asyncio.wait_for(
            ScannerAPI.scan_user(username, scan_config),
            timeout=SCAN_TIMEOUT,
        )

        # Build results embed
        embed = discord.Embed(
            title=f"Scan Results: {username}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}")

        # Add Sherlock results
        if results.get("sherlock"):
            platforms = len(results["sherlock"])
            platform_list = ", ".join(
                r["platform"] for r in results["sherlock"][:5]
            )
            if platforms > 5:
                platform_list += f" ... (+{platforms - 5} more)"
            embed.add_field(
                name="🔎 Sherlock OSINT",
                value=f"Found on **{platforms}** platforms\n{platform_list}",
                inline=False,
            )

        # Add Reddit results
        if mode in ("reddit", "both"):
            if results.get("reddit"):
                flagged = len(results["reddit"])
                status = "⚠️ Toxic content detected" if flagged > 0 else "✅ Clean"
                embed.add_field(
                    name="🤖 Reddit Analysis",
                    value=f"{status} (**{flagged}** flagged items)",
                    inline=False,
                )
            elif "reddit" in results:
                embed.add_field(
                    name="🤖 Reddit Analysis",
                    value="✅ No toxic content found",
                    inline=False,
                )

        # Add errors if any
        if results.get("errors"):
            error_text = "\n".join(f"• {err}" for err in results["errors"])
            embed.add_field(
                name="⚠️ Issues",
                value=error_text[:1024],  # Discord field limit
                inline=False,
            )

        # Add data location
        if results.get("sherlock") or results.get("reddit"):
            embed.add_field(
                name="📁 Data Location",
                value=f"`{SCANS_DIR}/{username}_*`",
                inline=False,
            )

        await status_msg.edit(content=None, embed=embed)
        log.info("Scan completed for user '%s'", username)

    except asyncio.TimeoutError:
        await status_msg.edit(
            content=f"⏱️ Scan timed out after {SCAN_TIMEOUT}s. Try a simpler scan mode."
        )
        log.warning("Scan timeout for user '%s'", username)

    except Exception as e:
        log.error("Scan error for user '%s': %s", username, e, exc_info=e)
        await status_msg.edit(
            content=f"❌ Scan failed: {type(e).__name__}. Check bot logs for details."
        )


@bot.command(name="health")
async def check_health(ctx: commands.Context) -> None:
    """Check bot health and API status.

    Usage: !health
    """
    embed = discord.Embed(
        title="Bot Health Check",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )

    # Bot status
    latency_ms = bot.latency * 1000
    latency_status = "🟢" if latency_ms < 200 else "🟡" if latency_ms < 500 else "🔴"
    embed.add_field(
        name="Bot Status",
        value=f"{latency_status} Latency: {latency_ms:.0f}ms\n"
        f"🌐 Guilds: {len(bot.guilds)}\n"
        f"👥 Users: {len(bot.users)}",
        inline=False,
    )

    # Service availability
    services = []
    services.append(
        f"{'✅' if SherlockScanner.available() else '❌'} Sherlock OSINT"
    )
    services.append(
        f"{'✅' if config.perspective_key else '❌'} Perspective API"
    )
    services.append(
        f"{'✅' if config.has_reddit_config() else '❌'} Reddit API"
    )
    embed.add_field(
        name="Services",
        value="\n".join(services),
        inline=False,
    )

    # System info
    embed.add_field(
        name="System",
        value=f"📁 Scans directory: `{SCANS_DIR.absolute()}`",
        inline=False,
    )

    await ctx.send(embed=embed)


@bot.command(name="help")
async def show_help(ctx: commands.Context) -> None:
    """Show bot help and usage information.

    Usage: !help
    """
    embed = discord.Embed(
        title="Account Scanner Bot - Help",
        description="Multi-source account scanner for moderation",
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="!scan <username> [mode]",
        value=(
            "Scan a user across platforms\n"
            "**Modes:** sherlock, reddit, both (default)\n"
            "**Requires:** Moderate Members permission\n"
            "**Example:** `!scan johndoe both`"
        ),
        inline=False,
    )

    embed.add_field(
        name="!health",
        value="Check bot health and service availability",
        inline=False,
    )

    embed.add_field(
        name="!help",
        value="Show this help message",
        inline=False,
    )

    embed.set_footer(text="account-scanner v1.2.3")
    await ctx.send(embed=embed)


@bot.command(name="shutdown")
@commands.check(lambda ctx: ctx.author.id in config.admin_user_ids)
async def shutdown_bot(ctx: commands.Context) -> None:
    """Shutdown the bot (admin only).

    Usage: !shutdown
    """
    log.warning("Shutdown requested by %s (ID: %s)", ctx.author.name, ctx.author.id)
    await ctx.send("👋 Shutting down...")
    await bot.close()
    sys.exit(0)


def main() -> None:
    """Bot entry point."""
    # Validate configuration
    try:
        config.validate()
    except ConfigurationError as e:
        log.error("Configuration error: %s", e)
        sys.exit(1)

    # Install uvloop for better async performance
    try:
        uvloop.install()
        log.info("uvloop installed for better async performance")
    except Exception as e:
        log.warning("Failed to install uvloop, using default event loop: %s", e)

    log.info("Starting Discord bot...")

    # Run bot with comprehensive error handling
    try:
        bot.run(config.discord_token)
    except discord.LoginFailure as e:
        log.error("Discord login failed - invalid token: %s", e)
        sys.exit(1)
    except discord.PrivilegedIntentsRequired as e:
        log.error("Missing required Discord intents: %s", e)
        log.error("Enable 'Message Content Intent' in Discord Developer Portal")
        sys.exit(1)
    except discord.HTTPException as e:
        log.error("Discord HTTP error: %s (status: %s)", e.text, e.status)
        sys.exit(1)
    except TypeError as e:
        # Catch argument errors (like the log_handler issue)
        log.error("TypeError in bot.run(): %s", e)
        log.error("This may indicate an API compatibility issue")
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        log.error("Fatal error: %s", e, exc_info=e)
        log.error("Bot crashed - check logs above for details")
        sys.exit(1)
    finally:
        log.info("Cleaning up tasks.")
        try:
            # Clean up any pending tasks
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                log.info("Closing the event loop.")
                loop.close()
        except Exception as e:
            log.warning("Error during cleanup: %s", e)


if __name__ == "__main__":
    main()
