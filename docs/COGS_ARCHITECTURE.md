# Cogs Architecture

This document explains the cogs-based architecture implemented in the Discord bot, following patterns from the [Python Discord Bot Template](https://github.com/kkrypt0nn/Python-Discord-Bot-Template).

## Overview

The bot now uses a **modular cogs system** that separates commands into logical groups. This makes the codebase more maintainable, testable, and easier to extend.

## Architecture

### Main Bot File (`discord_bot.py`)

The main bot file handles:
- Configuration loading and validation
- Bot initialization and setup
- Cog loading through `setup_hook()`
- Global error handling for both prefix and slash commands
- Event loop management and cleanup

### Cogs Directory Structure

```
cogs/
├── __init__.py          # Package marker
├── general.py           # General commands (health, help)
├── moderation.py        # Moderation commands (scan)
└── admin.py             # Admin commands (shutdown, reload, sync)
```

## Cogs Explained

### 1. General Cog (`cogs/general.py`)

**Purpose:** Handles general-purpose bot commands.

**Commands:**
- `/health` - Check bot health and service availability
- `/help` - Show help and usage information

**Features:**
- Uses hybrid commands (works with both `/` and `!` prefixes)
- Displays service status (Sherlock, Perspective API, Reddit API)
- Shows bot latency and connection statistics

### 2. Moderation Cog (`cogs/moderation.py`)

**Purpose:** Handles account scanning and moderation features.

**Commands:**
- `/scan <username> [mode]` - Scan a user across platforms

**Features:**
- Cooldown system (30 seconds per user)
- Rate limiting (60 requests/min for Perspective API)
- Support for multiple scan modes (sherlock, reddit, both)
- Rich embed responses with detailed results
- Automatic username sanitization for file safety
- Timeout protection (5 minutes max)

### 3. Admin Cog (`cogs/admin.py`)

**Purpose:** Handles administrative commands (requires admin permission).

**Commands:**
- `!shutdown` - Shutdown the bot (prefix only)
- `/reload <cog>` - Reload a cog without restarting
- `/sync` - Manually sync slash commands with Discord

**Features:**
- Admin-only access (checks `ADMIN_USER_IDS` config)
- Hot-reload support for development
- Manual command syncing capability

## Key Features from Template

### 1. Modular Command Organization

Commands are organized into logical groups (cogs) instead of being all in one file. This provides:
- Better code organization
- Easier maintenance and testing
- Ability to reload individual cogs without restarting
- Clear separation of concerns

### 2. Hybrid Commands

Commands use the `@commands.hybrid_command()` decorator, which means they work as both:
- **Slash commands** (`/scan`, `/health`, `/help`)
- **Prefix commands** (`!scan`, `!health`, `!help`)

This provides maximum compatibility with different user preferences.

### 3. Improved Error Handling

The bot now has two separate error handlers:
- `on_command_error()` - Handles prefix command errors
- `on_app_command_error()` - Handles slash command errors

This ensures users get appropriate error messages for all command types.

### 4. Setup Hook Pattern

The bot uses the `setup_hook()` method to load cogs automatically on startup:

```python
async def setup_hook(self) -> None:
    """Called when the bot is setting up."""
    log.info("Loading cogs...")

    cogs_to_load = ["cogs.general", "cogs.moderation", "cogs.admin"]

    for cog in cogs_to_load:
        try:
            await self.load_extension(cog)
            log.info("✅ Loaded cog: %s", cog)
        except Exception as e:
            log.error("❌ Failed to load cog %s: %s", cog, e, exc_info=True)
```

### 5. Custom Bot Class

The bot uses a custom `ModerationBot` class that extends `commands.Bot`:

```python
class ModerationBot(commands.Bot):
    """Custom bot class with cog loading support."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.config = BotConfig()
```

This allows:
- Configuration to be accessible from all cogs via `self.bot.config`
- Custom initialization logic
- Better organization of bot-specific functionality

## Adding New Cogs

To add a new cog:

1. Create a new file in the `cogs/` directory (e.g., `cogs/fun.py`)
2. Define your cog class:

```python
from discord.ext import commands
import logging

log = logging.getLogger(__name__)

class FunCog(commands.Cog, name="Fun"):
    """Cog for fun commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = bot.config
        log.info("Fun cog initialized")

    @commands.hybrid_command(name="joke", description="Get a random joke")
    async def joke(self, ctx: commands.Context) -> None:
        await ctx.send("Why did the Discord bot go to therapy? It had too many issues!")

async def setup(bot: commands.Bot) -> None:
    """Load the fun cog."""
    await bot.add_cog(FunCog(bot))
```

3. Add the cog to the `cogs_to_load` list in `discord_bot.py`:

```python
cogs_to_load = ["cogs.general", "cogs.moderation", "cogs.admin", "cogs.fun"]
```

4. Restart the bot (or use `/reload fun` if it's already running)

## Development Workflow

### Testing Changes to a Cog

1. Make changes to your cog file
2. Use the `/reload <cog_name>` command (e.g., `/reload moderation`)
3. Test your changes without restarting the bot

### Adding New Commands

1. Add your command to the appropriate cog
2. Use `@commands.hybrid_command()` for commands that should work with both `/` and `!`
3. Use proper error handling and logging
4. Test with both slash and prefix versions

### Debugging

- Check bot logs for error messages
- Use `/health` to check service availability
- Use `/sync` to manually sync slash commands if they don't appear

## Benefits of This Architecture

1. **Maintainability:** Code is organized into logical modules
2. **Scalability:** Easy to add new features without touching existing code
3. **Testability:** Each cog can be tested independently
4. **Hot-reload:** Reload individual cogs without restarting the bot
5. **Team Development:** Multiple developers can work on different cogs
6. **Clean Separation:** Commands, configuration, and bot logic are separate

## Migration Notes

The bot has been migrated from a monolithic structure to a cogs-based architecture:

**Before:**
- All commands in `discord_bot.py` (~740 lines)
- Difficult to maintain and extend
- No hot-reload capability

**After:**
- Commands organized into cogs (~200-300 lines each)
- Core bot logic in `discord_bot.py` (~335 lines)
- Hot-reload support via `/reload`
- Better error handling for slash commands

## References

- [Python Discord Bot Template](https://github.com/kkrypt0nn/Python-Discord-Bot-Template)
- [discord.py Cogs Documentation](https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html)
- [discord.py Hybrid Commands](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.CommandTree.hybrid_command)
