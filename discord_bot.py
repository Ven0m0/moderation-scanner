#!/usr/bin/env python3
"""Discord moderation bot using account scanner."""
import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
import uvloop

from account_scanner import ScanConfig, ScannerAPI

logging.basicConfig(level=logging. INFO, format="%(message)s")
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready() -> None:
  log.info("Bot ready:  %s (ID: %s)", bot.user. name, bot.user.id)

@bot.command(name="scan")
@commands.has_permissions(moderate_members=True)
async def scan_user(ctx: commands.Context, username: str, mode: str = "both") -> None:
  """Scan a user across platforms. 
  
  Usage:  !scan <username> [sherlock|reddit|both]
  """
  await ctx.send(f"🔍 Scanning **{username}** (mode: {mode})...")
  
  config = ScanConfig(
    username=username,
    mode=mode,
    api_key=os.getenv("PERSPECTIVE_API_KEY"),
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT"),
    output_reddit=Path(f"./scans/{username}_reddit.csv"),
    output_sherlock=Path(f"./scans/{username}_sherlock.json"),
  )
  
  try:
    results = await ScannerAPI.scan_user(username, config)
    
    embed = discord.Embed(title=f"Scan Results:  {username}", color=discord.Color.blue())
    
    if results. get("sherlock"):
      platforms = len(results["sherlock"])
      embed.add_field(name="🔎 Sherlock", value=f"Found on {platforms} platforms", inline=False)
    
    if results. get("reddit"):
      flagged = len(results["reddit"]) if results["reddit"] else 0
      status = "⚠️ Toxic content found" if flagged > 0 else "✅ Clean"
      embed.add_field(name="🤖 Reddit", value=f"{status} ({flagged} flagged)", inline=False)
    
    await ctx.send(embed=embed)
    
  except Exception as e:
    log.error("Scan error: %s", e)
    await ctx.send(f"❌ Scan failed: {e}")

@bot.command(name="check")
async def check_health(ctx: commands.Context) -> None:
  """Check bot health and API status."""
  status = []
  status.append(f"✅ Bot latency: {bot.latency*1000:.0f}ms")
  status.append(f"✅ Perspective:  {'✓' if os.getenv('PERSPECTIVE_API_KEY') else '✗'}")
  status.append(f"✅ Reddit:  {'✓' if os.getenv('REDDIT_CLIENT_ID') else '✗'}")
  await ctx.send("\n".join(status))

def main() -> None:
  """Bot entry point."""
  uvloop.install()
  token = os.getenv("DISCORD_BOT_TOKEN")
  if not token:
    log.error("DISCORD_BOT_TOKEN not set")
    return
  bot.run(token)


if __name__ == "__main__": 
  main()
