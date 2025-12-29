#!/usr/bin/env python3
"""Discord moderation bot for account scanning and OSINT research."""

import asyncio
import logging
import os
import re
import sys
from collections import deque
from pathlib import Path
from typing import Deque, Final, Tuple

import discord
import uvloop
from discord import app_commands
from discord.ext import commands

# Fix 2: Import RateLimiter to create a global instance
from account_scanner import ScanConfig, ScannerAPI, SherlockScanner, RateLimiter, close_http_client

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

# Fix 2: Global Rate Limiter for Perspective API (60 req/min)
# This ensures we don't hit 429 errors even with multiple concurrent scans
GLOBAL_LIMITER = RateLimiter(rate_per_min=60.0)


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
            "account-scanner-bot/1.2.3",
        )
        self.admin_user_ids = self._parse_admin_ids()
        self.log_channel_id = self._parse_log_channel()

    def _parse_admin_ids(self) -> set[int]:
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        if not admin_ids_str:
            return set()
        try:
            return {int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()}
        except ValueError:
            log.warning("Invalid ADMIN_USER_IDS format, ignoring")
            return set()

    def _parse_log_channel(self) -> int | None:
        channel_id = os.getenv("LOG_CHANNEL_ID")
        if not channel_id:
            return None
        try:
            return int(channel_id)
        except ValueError:
            log.warning("Invalid LOG_CHANNEL_ID format, ignoring")
            return None

    def validate(self) -> None:
        if not self.discord_token:
            raise ConfigurationError("DISCORD_BOT_TOKEN is required")
        if not self.perspective_key:
            log.warning(
                "PERSPECTIVE_API_KEY not set - Reddit toxicity scanning disabled"
            )
        if not self.reddit_client_id or not self.reddit_client_secret:
            log.warning("Reddit credentials not set - Reddit scanning disabled")

    def has_reddit_config(self) -> bool:
        return bool(
            self.perspective_key and self.reddit_client_id and self.reddit_client_secret
        )


# Initialize bot configuration
config = BotConfig()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready() -> None:
    log.info("Bot ready: %s (ID: %s)", bot.user.name, bot.user.id)
    log.info("Connected to %d guilds", len(bot.guilds))
    SCANS_DIR.mkdir(exist_ok=True)
    log.info("Scans directory: %s", SCANS_DIR.absolute())
    try:
        log.info("Syncing slash commands...")
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s)", len(synced))
    except (discord.HTTPException, discord.DiscordException) as e:
        log.error("Failed to sync commands: %s", e)
    log.info("Sherlock available: %s", SherlockScanner.available())
    log.info("Reddit scanning available: %s", config.has_reddit_config())


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
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
@commands.cooldown(1, 30, commands.BucketType.user)
async def scan_user(ctx: commands.Context, username: str, mode: str = "both") -> None:
    """Scan a user across platforms for moderation purposes."""
    if len(username) > MAX_SCAN_LENGTH:
        await ctx.send(f"❌ Username too long (max {MAX_SCAN_LENGTH} characters)")
        return

    if mode not in ("sherlock", "reddit", "both"):
        await ctx.send("❌ Mode must be: sherlock, reddit, or both")
        return

    if mode in ("reddit", "both") and not config.has_reddit_config():
        await ctx.send("❌ Reddit scanning not configured on this bot")
        return

    if mode in ("sherlock", "both") and not SherlockScanner.available():
        await ctx.send("❌ Sherlock not available on this bot")
        return

    # FIX 4: Sanitize username for filename safety
    safe_username = re.sub(r'[^\w\-]', '_', username)

    status_msg = await ctx.send(f"🔍 Scanning **{username}** (mode: {mode})...")
    log.info(
        "Scan requested by %s#%s (ID: %s) for user '%s' (mode: %s)",
        ctx.author.name,
        ctx.author.discriminator,
        ctx.author.id,
        username,
        mode,
    )

    scan_config = ScanConfig(
        username=username,
        mode=mode,
        api_key=config.perspective_key,
        client_id=config.reddit_client_id,
        client_secret=config.reddit_client_secret,
        user_agent=config.reddit_user_agent,
        limiter=GLOBAL_LIMITER,  # Pass global limiter
        output_reddit=SCANS_DIR / f"{safe_username}_reddit.csv",
        output_sherlock=SCANS_DIR / f"{safe_username}_sherlock.json",
        verbose=True,
    )

    try:
        results = await asyncio.wait_for(
            ScannerAPI.scan_user(username, scan_config),
            timeout=SCAN_TIMEOUT,
        )

        embed = discord.Embed(
            title=f"Scan Results: {username}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}")

        if mode in ("sherlock", "both"):
            sherlock_results = results.get("sherlock")
            if sherlock_results:
                platforms = len(sherlock_results)
                embed.add_field(
                    name="🔎 Sherlock OSINT",
                    value=f"✅ Found on **{platforms}** platforms",
                    inline=False,
                )
            elif sherlock_results == []:
                embed.add_field(
                    name="🔎 Sherlock OSINT",
                    value="❌ No accounts found",
                    inline=False,
                )

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

        if results.get("errors"):
            error_text = "\n".join(f"• {err}" for err in results["errors"])
            embed.add_field(
                name="⚠️ Issues",
                value=error_text[:1024],
                inline=False,
            )

        await status_msg.edit(content=None, embed=embed)
        await _send_detailed_results(ctx, username, results)
        log.info("Scan completed for user '%s'", username)

    except TimeoutError:
        await status_msg.edit(
            content=f"⏱️ Scan timed out after {SCAN_TIMEOUT}s. Try a simpler scan mode."
        )
        log.warning("Scan timeout for user '%s'", username)
    except (discord.HTTPException, discord.DiscordException):
        log.exception("Discord error during scan for user '%s'", username)
        try:
            await ctx.send("❌ Discord API error occurred. Please try again.")
        except (discord.HTTPException, discord.DiscordException):
            pass
    except (OSError, ValueError, RuntimeError):
        log.exception("Scan error for user '%s'", username)
        await status_msg.edit(
            content="❌ Scan failed. Check bot logs for details."
        )


async def _send_detailed_results(ctx, username, results) -> None:
    """Helper to send detailed text results."""
    # Sherlock results
    if results.get("sherlock"):
        # Use list and join for better performance
        lines = [f"{account['platform']}: {account['url']}" for account in results["sherlock"]]
        sherlock_text = f"**🔎 Sherlock OSINT Results for {username}:**\n```\n" + "\n".join(lines) + "\n```"

        if len(sherlock_text) > 1900:
            chunks = []
            chunk_lines = [f"**🔎 Sherlock OSINT Results for {username}:**\n```"]
            current_length = len(chunk_lines[0])

            for line in lines:
                line_with_newline = line + "\n"
                if current_length + len(line_with_newline) + 3 > 1900:  # 3 for closing ```
                    chunk_lines.append("```")
                    chunks.append("\n".join(chunk_lines))
                    chunk_lines = ["```", line]
                    current_length = len("```\n") + len(line)
                else:
                    chunk_lines.append(line)
                    current_length += len(line_with_newline)

            chunk_lines.append("```")
            chunks.append("\n".join(chunk_lines))

            for chunk in chunks:
                if isinstance(ctx, discord.Interaction):
                    await ctx.followup.send(chunk)
                else:
                    await ctx.send(chunk)
        else:
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(sherlock_text)
            else:
                await ctx.send(sherlock_text)

    # Reddit results
    if results.get("reddit"):
        reddit_chunks = []
        current_lines = [f"**🤖 Reddit Toxicity Analysis for {username}:**"]
        current_length = len(current_lines[0]) + 1  # +1 for newline

        for item in results["reddit"]:
            content_preview = item['content'][:200] + ('...' if len(item['content']) > 200 else '')
            item_lines = [
                "```",
                f"Time: {item['timestamp']}",
                f"Type: {item['type']} | Subreddit: r/{item['subreddit']}",
                f"Toxicity: {item['TOXICITY']:.2f} | Insult: {item['INSULT']:.2f} | "
                f"Profanity: {item['PROFANITY']:.2f} | Sexual: {item['SEXUALLY_EXPLICIT']:.2f}",
                f"Content: {content_preview}",
                "```"
            ]
            item_text = "\n".join(item_lines) + "\n"

            if current_length + len(item_text) > 1900:
                reddit_chunks.append("\n".join(current_lines))
                current_lines = [item_text.rstrip()]
                current_length = len(current_lines[0])
            else:
                current_lines.append(item_text.rstrip())
                current_length += len(item_text)

        if current_lines:
            reddit_chunks.append("\n".join(current_lines))

        for chunk in reddit_chunks:
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(chunk)
            else:
                await ctx.send(chunk)


@bot.command(name="health")
async def check_health(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Bot Health Check",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    latency_ms = bot.latency * 1000
    latency_status = "🟢" if latency_ms < 200 else "🟡" if latency_ms < 500 else "🔴"
    embed.add_field(
        name="Bot Status",
        value=f"{latency_status} Latency: {latency_ms:.0f}ms\n"
        f"🌐 Guilds: {len(bot.guilds)}\n"
        f"👥 Users: {len(bot.users)}",
        inline=False,
    )
    services = []
    services.append(f"{'✅' if SherlockScanner.available() else '❌'} Sherlock OSINT")
    services.append(f"{'✅' if config.perspective_key else '❌'} Perspective API")
    services.append(f"{'✅' if config.has_reddit_config() else '❌'} Reddit API")
    embed.add_field(name="Services", value="\n".join(services), inline=False)
    embed.add_field(
        name="System",
        value=f"📁 Scans directory: `{SCANS_DIR.absolute()}`",
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.command(name="help")
async def show_help(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Account Scanner Bot - Help",
        description="Multi-source account scanner for moderation",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="!scan <username> [mode]",
        value="Scan a user across platforms\nModes: sherlock, reddit, both",
        inline=False,
    )
    embed.add_field(name="!health", value="Check health", inline=False)
    embed.add_field(name="!help", value="Show help", inline=False)
    embed.set_footer(text="account-scanner v1.2.3")
    await ctx.send(embed=embed)


@bot.command(name="shutdown")
@commands.check(lambda ctx: ctx.author.id in config.admin_user_ids)
async def shutdown_bot(ctx: commands.Context) -> None:
    log.warning("Shutdown requested by %s (ID: %s)", ctx.author.name, ctx.author.id)
    await ctx.send("👋 Shutting down...")
    await bot.close()
    sys.exit(0)


# ============================================================================
# SLASH COMMANDS (Application Commands)
# ============================================================================

# Performance-optimized cooldown system using deque for O(1) cleanup
_scan_cooldowns: dict[int, float] = {}
_cooldown_queue: Deque[Tuple[float, int]] = deque()
COOLDOWN_SECONDS = 30


def check_cooldown(user_id: int) -> tuple[bool, float]:
    """Check if user is on cooldown with lazy cleanup."""
    now = asyncio.get_event_loop().time()

    # Lazy cleanup: Remove expired entries from front of queue (O(1) amortized)
    while _cooldown_queue and now - _cooldown_queue[0][0] >= COOLDOWN_SECONDS:
        ts, uid = _cooldown_queue.popleft()
        # Only delete if this is the most recent cooldown for this user
        if uid in _scan_cooldowns and _scan_cooldowns[uid] == ts:
            del _scan_cooldowns[uid]

    # Check cooldown
    if user_id in _scan_cooldowns:
        elapsed = now - _scan_cooldowns[user_id]
        if elapsed < COOLDOWN_SECONDS:
            return True, COOLDOWN_SECONDS - elapsed
    return False, 0.0


def update_cooldown(user_id: int) -> None:
    """Update cooldown timestamp for user."""
    now = asyncio.get_event_loop().time()
    _scan_cooldowns[user_id] = now
    _cooldown_queue.append((now, user_id))


@bot.tree.command(
    name="scan", description="Scan a user across platforms for moderation purposes"
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    username="Target username to scan (max 50 characters)",
    mode="Scan mode: sherlock (OSINT), reddit (toxicity), or both",
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Both (Reddit + Sherlock)", value="both"),
        app_commands.Choice(name="Sherlock (OSINT only)", value="sherlock"),
        app_commands.Choice(name="Reddit (Toxicity only)", value="reddit"),
    ]
)
async def scan_slash(
    interaction: discord.Interaction,
    username: str,
    mode: app_commands.Choice[str] = None,
) -> None:
    scan_mode = mode.value if mode else "both"
    on_cooldown, remaining = check_cooldown(interaction.user.id)
    if on_cooldown:
        await interaction.response.send_message(
            f"⏱️ Cooldown: try again in {remaining:.1f}s", ephemeral=True
        )
        return

    if len(username) > MAX_SCAN_LENGTH:
        await interaction.response.send_message(
            f"❌ Username too long (max {MAX_SCAN_LENGTH} characters)", ephemeral=True
        )
        return

    if scan_mode in ("reddit", "both") and not config.has_reddit_config():
        await interaction.response.send_message(
            "❌ Reddit scanning not configured on this bot", ephemeral=True
        )
        return

    if scan_mode in ("sherlock", "both") and not SherlockScanner.available():
        await interaction.response.send_message(
            "❌ Sherlock not available on this bot", ephemeral=True
        )
        return

    update_cooldown(interaction.user.id)
    
    # FIX 4: Sanitize username for filename safety
    safe_username = re.sub(r'[^\w\-]', '_', username)

    await interaction.response.send_message(
        f"🔍 Scanning **{username}** (mode: {scan_mode})..."
    )
    log.info(
        "Scan requested by %s (ID: %s) for user '%s' (mode: %s)",
        interaction.user.name,
        interaction.user.id,
        username,
        scan_mode,
    )

    scan_config = ScanConfig(
        username=username,
        mode=scan_mode,
        api_key=config.perspective_key,
        client_id=config.reddit_client_id,
        client_secret=config.reddit_client_secret,
        user_agent=config.reddit_user_agent,
        limiter=GLOBAL_LIMITER,  # Pass global limiter
        output_reddit=SCANS_DIR / f"{safe_username}_reddit.csv",
        output_sherlock=SCANS_DIR / f"{safe_username}_sherlock.json",
        verbose=True,
    )

    try:
        results = await asyncio.wait_for(
            ScannerAPI.scan_user(username, scan_config),
            timeout=SCAN_TIMEOUT,
        )

        embed = discord.Embed(
            title=f"Scan Results: {username}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        if scan_mode in ("sherlock", "both"):
            sherlock_results = results.get("sherlock")
            if sherlock_results:
                platforms = len(sherlock_results)
                embed.add_field(
                    name="🔎 Sherlock OSINT",
                    value=f"✅ Found on **{platforms}** platforms",
                    inline=False,
                )
            elif sherlock_results == []:
                embed.add_field(
                    name="🔎 Sherlock OSINT",
                    value="❌ No accounts found",
                    inline=False,
                )

        if scan_mode in ("reddit", "both"):
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

        if results.get("errors"):
            error_text = "\n".join(f"• {err}" for err in results["errors"])
            embed.add_field(
                name="⚠️ Issues",
                value=error_text[:1024],
                inline=False,
            )

        await interaction.edit_original_response(content=None, embed=embed)
        await _send_detailed_results(interaction, username, results)
        log.info("Scan completed for user '%s'", username)

    except TimeoutError:
        await interaction.edit_original_response(
            content=f"⏱️ Scan timed out after {SCAN_TIMEOUT}s. Try a simpler scan mode."
        )
        log.warning("Scan timeout for user '%s'", username)
    except (discord.HTTPException, discord.DiscordException):
        log.exception("Discord error during scan for user '%s'", username)
    except (OSError, ValueError, RuntimeError):
        log.exception("Scan error for user '%s'", username)
        await interaction.edit_original_response(
            content="❌ Scan failed. Check bot logs for details."
        )


@bot.tree.command(
    name="health", description="Check bot health and service availability"
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def health_slash(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="Bot Health Check",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    latency_ms = bot.latency * 1000
    latency_status = "🟢" if latency_ms < 200 else "🟡" if latency_ms < 500 else "🔴"
    embed.add_field(
        name="Bot Status",
        value=f"{latency_status} Latency: {latency_ms:.0f}ms\n"
        f"🌐 Guilds: {len(bot.guilds)}\n"
        f"👥 Users: {len(bot.users)}",
        inline=False,
    )
    services = []
    services.append(f"{'✅' if SherlockScanner.available() else '❌'} Sherlock OSINT")
    services.append(f"{'✅' if config.perspective_key else '❌'} Perspective API")
    services.append(f"{'✅' if config.has_reddit_config() else '❌'} Reddit API")
    embed.add_field(name="Services", value="\n".join(services), inline=False)
    embed.add_field(
        name="System",
        value=f"📁 Scans directory: `{SCANS_DIR.absolute()}`",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show help and usage information")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def help_slash(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="Account Scanner Bot - Help",
        description="Multi-source account scanner for moderation\n\n"
        "**This bot uses slash commands!** Type `/` to see available commands.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="/scan <username> [mode]",
        value="Scan a user across platforms\nModes: sherlock, reddit, both",
        inline=False,
    )
    embed.add_field(name="/health", value="Check health", inline=False)
    embed.add_field(name="/help", value="Show help", inline=False)
    embed.set_footer(text="account-scanner v1.3.0 • Slash Commands Enabled")
    await interaction.response.send_message(embed=embed, ephemeral=True)


def main() -> None:
    try:
        config.validate()
    except ConfigurationError as e:
        log.error("Configuration error: %s", e)
        sys.exit(1)

    try:
        uvloop.install()
        log.info("uvloop installed for better async performance")
    except (ImportError, RuntimeError) as e:
        log.warning("Failed to install uvloop, using default event loop: %s", e)

    log.info("Starting Discord bot...")
    try:
        bot.run(config.discord_token)
    except discord.LoginFailure as e:
        log.error("Discord login failed - invalid token: %s", e)
        sys.exit(1)
    except discord.PrivilegedIntentsRequired as e:
        log.error("Missing required Discord intents: %s", e)
        sys.exit(1)
    except discord.HTTPException as e:
        log.error("Discord HTTP error: %s (status: %s)", e.text, e.status)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        sys.exit(0)
    except (OSError, RuntimeError, ValueError):
        log.exception("Fatal error")
        sys.exit(1)
    finally:
        log.info("Cleaning up tasks.")
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
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
                log.info("Closing the event loop.")
                loop.close()
        except (RuntimeError, ValueError) as e:
            log.warning("Error during cleanup: %s", e)


if __name__ == "__main__":
    main()
