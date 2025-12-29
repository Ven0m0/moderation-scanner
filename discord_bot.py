#!/usr/bin/env python3
"""Discord moderation bot for account scanning and OSINT research.

This Discord bot provides server moderators with tools to scan user accounts
across platforms for moderation purposes. It integrates the account_scanner
module to perform Reddit toxicity analysis and Sherlock OSINT username enumeration.

## Features

- **!scan <username> [mode]**: Scan accounts across Reddit and/or social platforms
- **!health**: Check bot health and API service availability
- **!help**: Display help and usage information
- **!shutdown**: Shutdown the bot (admin only)

## Commands

All scanning commands require the "Moderate Members" permission. Rate limiting
(1 scan per 30 seconds per user) prevents abuse.

## Configuration

The bot is configured via environment variables:

- **DISCORD_BOT_TOKEN** (required): Discord bot token from Developer Portal
- **PERSPECTIVE_API_KEY**: Google Perspective API key for toxicity analysis
- **REDDIT_CLIENT_ID**: Reddit API client ID
- **REDDIT_CLIENT_SECRET**: Reddit API client secret
- **REDDIT_USER_AGENT**: Reddit API user agent (optional)
- **ADMIN_USER_IDS**: Comma-separated Discord user IDs for admin commands
- **LOG_CHANNEL_ID**: Channel ID for bot logging (optional)

## Architecture

- Built with discord.py and commands extension
- Uses uvloop for improved async performance
- Integrates ScannerAPI from account_scanner module
- Stores scan results in local ./scans directory
- Rich embed formatting for scan results

## Running the Bot

    export DISCORD_BOT_TOKEN="your_token"
    export PERSPECTIVE_API_KEY="your_key"
    export REDDIT_CLIENT_ID="your_id"
    export REDDIT_CLIENT_SECRET="your_secret"
    python discord_bot.py

See DEPLOYMENT.md for production deployment instructions.
"""
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
    """Raised when bot configuration is invalid or incomplete."""


class BotConfig:
    """Bot configuration manager using environment variables.

    Loads and validates all bot configuration from environment variables.
    Provides helper methods to check if optional features are configured.

    Attributes:
        discord_token: Discord bot token (required).
        perspective_key: Google Perspective API key (optional).
        reddit_client_id: Reddit API client ID (optional).
        reddit_client_secret: Reddit API client secret (optional).
        reddit_user_agent: Reddit API user agent string.
        admin_user_ids: Set of Discord user IDs with admin privileges.
        log_channel_id: Channel ID for logging bot events (optional).

    Raises:
        ConfigurationError: If required configuration is missing during validate().
    """

    def __init__(self) -> None:
        """Load configuration from environment variables."""
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
        """Parse admin user IDs from ADMIN_USER_IDS environment variable.

        Expected format: Comma-separated Discord user IDs (integers).
        Example: "123456789,987654321"

        Returns:
            Set of integer user IDs. Empty set if not configured or invalid.
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
        """Parse log channel ID from LOG_CHANNEL_ID environment variable.

        Returns:
            Integer channel ID if configured and valid, None otherwise.
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
        """Validate that required configuration is present.

        Checks that DISCORD_BOT_TOKEN is set. Logs warnings for optional
        configuration that affects available features (Reddit scanning, etc.).

        Raises:
            ConfigurationError: If DISCORD_BOT_TOKEN is not set.
        """
        if not self.discord_token:
            raise ConfigurationError("DISCORD_BOT_TOKEN is required")

        # Warn about optional configs
        if not self.perspective_key:
            log.warning("PERSPECTIVE_API_KEY not set - Reddit toxicity scanning disabled")
        if not self.reddit_client_id or not self.reddit_client_secret:
            log.warning("Reddit credentials not set - Reddit scanning disabled")

    def has_reddit_config(self) -> bool:
        """Check if Reddit scanning is fully configured.

        Returns:
            True if Perspective API key and Reddit credentials are all set.
        """
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
    """Called when bot successfully connects to Discord.

    Logs bot information, creates the scans directory, and reports
    which scanning features are available based on configuration.
    """
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
    """Global error handler for all bot commands.

    Handles common command errors with user-friendly messages:
    - Permission errors
    - Missing/invalid arguments
    - Cooldown violations

    Other errors are logged and shown as generic error messages.

    Args:
        ctx: Command context containing message and author info.
        error: Exception raised during command execution.
    """
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
    """Scan a user across platforms for moderation purposes.

    Executes Reddit toxicity analysis and/or Sherlock OSINT username
    enumeration based on the mode parameter. Results are displayed in
    a rich embed with summary information.

    Permissions: Requires "Moderate Members" permission.
    Cooldown: 1 scan per 30 seconds per user.
    Timeout: Scans timeout after 5 minutes.

    Args:
        ctx: Discord command context.
        username: Target username to scan (max 50 characters).
        mode: Scan mode - "sherlock", "reddit", or "both" (default: "both").

    Usage:
        !scan <username> [sherlock|reddit|both]

    Examples:
        !scan johndoe              # Both Reddit and Sherlock
        !scan johndoe sherlock     # OSINT only
        !scan johndoe reddit       # Toxicity analysis only
        !scan johndoe both         # Explicit both modes

    Scan results are saved to the ./scans directory and include:
    - Reddit: CSV file with flagged toxic content
    - Sherlock: JSON file with found social media accounts
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
        if mode in ("sherlock", "both"):
            if results.get("sherlock"):
                platforms = len(results["sherlock"])
                embed.add_field(
                    name="🔎 Sherlock OSINT",
                    value=f"✅ Found on **{platforms}** platforms",
                    inline=False,
                )
            elif "sherlock" in results:
                embed.add_field(
                    name="🔎 Sherlock OSINT",
                    value="❌ No accounts found",
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

        # Send summary embed
        await status_msg.edit(content=None, embed=embed)

        # Send detailed results as formatted text messages
        # Sherlock results
        if results.get("sherlock"):
            sherlock_text = f"**🔎 Sherlock OSINT Results for {username}:**\n```\n"
            for account in results["sherlock"]:
                sherlock_text += f"{account['platform']}: {account['url']}\n"
            sherlock_text += "```"

            # Split if too long (Discord has 2000 char limit)
            if len(sherlock_text) > 1900:
                chunks = []
                current_chunk = f"**🔎 Sherlock OSINT Results for {username}:**\n```\n"
                for account in results["sherlock"]:
                    line = f"{account['platform']}: {account['url']}\n"
                    if len(current_chunk) + len(line) + 3 > 1900:  # +3 for ```
                        current_chunk += "```"
                        chunks.append(current_chunk)
                        current_chunk = "```\n"
                    current_chunk += line
                current_chunk += "```"
                chunks.append(current_chunk)

                for chunk in chunks:
                    await ctx.send(chunk)
            else:
                await ctx.send(sherlock_text)

        # Reddit results
        if results.get("reddit"):
            reddit_text = f"**🤖 Reddit Toxicity Analysis for {username}:**\n"

            for item in results["reddit"]:
                # Format each item
                item_text = (
                    f"```\n"
                    f"Time: {item['timestamp']}\n"
                    f"Type: {item['type']} | Subreddit: r/{item['subreddit']}\n"
                    f"Toxicity: {item['TOXICITY']:.2f} | Insult: {item['INSULT']:.2f} | "
                    f"Profanity: {item['PROFANITY']:.2f} | Sexual: {item['SEXUALLY_EXPLICIT']:.2f}\n"
                    f"Content: {item['content'][:200]}{'...' if len(item['content']) > 200 else ''}\n"
                    f"```\n"
                )

                # Check if adding this item would exceed limit
                if len(reddit_text) + len(item_text) > 1900:
                    await ctx.send(reddit_text)
                    reddit_text = ""

                reddit_text += item_text

            if reddit_text:
                await ctx.send(reddit_text)

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
    """Check bot health, latency, and API service availability.

    Displays an embed with:
    - Bot latency and connection status
    - Number of connected guilds and users
    - Availability of Sherlock, Perspective API, and Reddit API
    - Scans directory location

    This command can be used by any user to verify the bot is working
    and which scanning features are available.

    Args:
        ctx: Discord command context.

    Usage:
        !health
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
    """Display bot help and command usage information.

    Shows an embed with all available commands, their descriptions,
    requirements, and usage examples.

    Args:
        ctx: Discord command context.

    Usage:
        !help
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
    """Gracefully shutdown the bot (admin only).

    This command closes the bot connection and exits the process.
    Only users listed in ADMIN_USER_IDS can execute this command.

    The shutdown is logged with the requesting user's information.

    Args:
        ctx: Discord command context.

    Usage:
        !shutdown

    Permissions: Requires user ID to be in ADMIN_USER_IDS environment variable.
    """
    log.warning("Shutdown requested by %s (ID: %s)", ctx.author.name, ctx.author.id)
    await ctx.send("👋 Shutting down...")
    await bot.close()
    sys.exit(0)


def main() -> None:
    """Bot entry point with comprehensive error handling.

    Validates configuration, installs uvloop for performance, and starts
    the Discord bot. Handles various failure modes with specific error
    messages and appropriate exit codes.

    Exit codes:
        0: Clean shutdown
        1: Configuration error, login failure, or fatal error

    Common errors handled:
        - Invalid/missing Discord token
        - Missing Message Content Intent in Developer Portal
        - Discord API HTTP errors
        - Network connectivity issues
    """
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
