import time
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
import asyncpg
from discord.ext.commands import Context, Command

from datetime import datetime, timezone
from typing import Tuple
from discord.ext import commands
from discord.ext.commands import Context, Command
import asyncpg


class DynamicRateLimiter:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.command_weights = {
            'moderation': 1.0,
            'configuration': 2.5,
            'information': 1.0,
            'api': 1.5,
            'embeds': 2.0,
            'developer': 5.0,
            'default': 1.0,
            'welcome': 3.0,
            'fakeperms': 2.0
        }
        self.base_cooldown = 1.0
        self.max_cooldown = 30.0
        self.reputation_threshold = 50

    def _get_command_category(self, command: Command) -> str:
        if command.cog:
            return command.cog.qualified_name.lower()
        return 'default'

    def _calculate_cooldown(self, usage_count: int, reputation: int, weight: float) -> float:
        reputation_factor = max(0.5, reputation / 100.0)
        usage_factor = min(2.0, 1.0 + (usage_count / 10.0))
        cooldown = self.base_cooldown * weight * usage_factor / reputation_factor
        return min(self.max_cooldown, max(0.5, cooldown))

    def _is_excluded(self, command: Command) -> bool:
        if command is None:
            return True
        if command.cog_name and command.cog_name.lower() == "jishaku":
            return True
        mod = getattr(command.callback, "__module__", "")
        return any(mod.startswith(f"bot.extensions.{x}") for x in ("developer", "api"))

    def _get_help_target(self, ctx: Context) -> Command | None:
        # Parse message content to extract what comes after "help"
        view = commands.view.StringView(ctx.message.content)
        view.skip_string(ctx.prefix)
        base = view.get_word()  # This should be 'help'
        if base.lower() != "help":
            return None

        target = view.get_word()
        if not target:
            return None

        return ctx.bot.get_command(target)

    async def check_rate_limit(self, ctx: Context) -> Tuple[bool, float]:
        if not ctx.guild or not ctx.command:
            return True, 0.0

        # If it's help command targeting an excluded command
        if ctx.command.name == "help":
            target = self._get_help_target(ctx)
            if target and self._is_excluded(target):
                return True, 0.0

        if self._is_excluded(ctx.command):
            return True, 0.0

        category = self._get_command_category(ctx.command)
        weight = self.command_weights.get(category, self.command_weights['default'])

        query = """
        SELECT usage_count, reputation_score, last_used
        FROM user_rate_limits
        WHERE user_id = $1 AND guild_id = $2 AND command_category = $3
        """
        record = await self.pool.fetchrow(query, ctx.author.id, ctx.guild.id, category)

        if not record:
            await self._create_rate_limit_record(ctx.author.id, ctx.guild.id, category)
            return True, 0.0

        usage_count = record['usage_count']
        reputation = record['reputation_score']
        last_used = record['last_used']

        cooldown = self._calculate_cooldown(usage_count, reputation, weight)

        if last_used:
            time_since_last = (datetime.now(timezone.utc) - last_used).total_seconds()
            if time_since_last < cooldown:
                return False, cooldown - time_since_last

        await self._update_usage(ctx.author.id, ctx.guild.id, category, usage_count + 1)
        return True, 0.0

    async def _create_rate_limit_record(self, user_id: int, guild_id: int, category: str):
        query = """
        INSERT INTO user_rate_limits (user_id, guild_id, command_category)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, guild_id, command_category) DO NOTHING
        """
        await self.pool.execute(query, user_id, guild_id, category)

    async def _update_usage(self, user_id: int, guild_id: int, category: str, new_count: int):
        query = """
        UPDATE user_rate_limits
        SET usage_count = $4, last_used = NOW()
        WHERE user_id = $1 AND guild_id = $2 AND command_category = $3
        """
        await self.pool.execute(query, user_id, guild_id, category, new_count)

    async def adjust_reputation(self, user_id: int, guild_id: int, adjustment: int):
        query = """
        UPDATE user_rate_limits
        SET reputation_score = GREATEST(0, LEAST(200, reputation_score + $4))
        WHERE user_id = $1 AND guild_id = $2
        """
        await self.pool.execute(query, user_id, guild_id, adjustment)

    async def reset_daily_limits(self):
        query = """
        UPDATE user_rate_limits
        SET usage_count = 0
        WHERE last_used < NOW() - INTERVAL '24 hours'
        """
        await self.pool.execute(query)
