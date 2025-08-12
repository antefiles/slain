from __future__ import annotations
from itertools import chain
from traceback import format_exception
from typing import Annotated, List, Optional, cast
from discord import Embed, Guild, Message, User
from discord.ext.commands import Cog, command, group
from discord.utils import as_chunks, format_dt
from jishaku.modules import ExtensionConverter
from bot.shared.formatter import plural
from bot.shared.paginator import Paginator, EmbedField
from bot.core import Bot, Context
from aiohttp import web
from discord.ext.commands import Cog, command, Context
from discord import Message, ButtonStyle, Interaction, ui, PartialEmoji
import re

class Developer(Cog, command_attrs=dict(hidden=False)):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    
    async def cog_check(self, ctx: Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @command(aliases=("cleanup",))
    async def clean(self, ctx: Context) -> None:
        await ctx.message.delete()
        await ctx.channel.purge(
            limit=200,
            check=lambda m: m.author.id in (ctx.author.id, self.bot.user.id),
            before=ctx.message,
        )

    @command(aliases=("rl",))
    async def reload(
        self,
        ctx: Context,
        *extensions: Annotated[str, ExtensionConverter],
    ) -> Message:
        """Reload extensions."""

        result: list[str] = []
        for extension in chain(*extensions):
            extension = "bot.extensions." + extension.replace("extensions.", "")
            method, icon = (
                (
                    self.bot.reload_extension,
                    "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
                )
                if extension in self.bot.extensions
                else (self.bot.load_extension, "\N{INBOX TRAY}")
            )

            try:
                await method(extension)
            except Exception as exc:
                traceback_data = "".join(
                    format_exception(type(exc), exc, exc.__traceback__, 1)
                )

                result.append(
                    f"{icon}\N{WARNING SIGN} `{extension}`\n```py\n{traceback_data}\n```"
                )
            else:
                result.append(f"{icon} `{extension}`")

        return await ctx.send("\n".join(result))

    @group(aliases=("bl",), invoke_without_command=True)
    async def blacklist(
        self,
        ctx: Context,
        target: Guild | User | int,
        *,
        reason: Optional[str] = None,
    ) -> Message:
        """Blacklist a user or server from using the bot."""

        target_id = target.id if isinstance(target, (Guild, User)) else target

        query = "DELETE FROM blacklist WHERE target_id = $1"
        status = await self.bot.pool.execute(query, target_id)
        if status == "DELETE 1":
            return await ctx.approve(f"Now allowing `{target_id}` to use the bot")

        query = "INSERT INTO blacklist (target_id, reason) VALUES ($1, $2)"
        await self.bot.pool.execute(query, target_id, reason)
        async with ctx.typing():
            if isinstance(target, User):
                for guild in target.mutual_guilds:
                    if guild.owner_id == target.id:
                        await guild.leave()

            elif isinstance(target, Guild):
                await target.leave()

        return await ctx.warn(f"No longer allowing `{target}` to use the bot")

    @blacklist.command(name="view", aliases=("search", "info"))
    async def blacklist_view(self, ctx: Context, *, target: User | int) -> Message:
        """View the blacklist status of a user or server."""

        target_id = target.id if isinstance(target, User) else target
        query = "SELECT reason, created_at FROM blacklist WHERE target_id = $1"
        record = await self.bot.pool.fetchrow(query, target_id)
        if not record:
            return await ctx.send(f"`{target_id}` is not blacklisted")

        return await ctx.send(
            f"`{target_id}` was blacklisted on {format_dt(record['created_at'])}"
            + (f" for {record['reason']}" if record["reason"] else "")
        )

    @blacklist.command(name="list")
    async def blacklist_list(self, ctx: Context) -> Message:
        """View all blacklisted users and servers."""

        query = "SELECT * FROM blacklist"
        records = await self.bot.pool.fetch(query)
        if not records:
            return await ctx.send("No blacklisted users or servers")

        embed = Embed(title="Blacklist")
        targets: list[str] = []

        for record in records:
            target = self.bot.get_user(record["target_id"])
            target_id = record["target_id"]
            reason = record["reason"] or ""
            created_at = format_dt(record["created_at"])
            target_display = target or f"`{target_id}`"

            targets.append(f"{target_display} {reason} ({created_at})")

        paginator = Paginator(ctx, pages=targets, embed=embed)
        return await paginator.start()
    
    @command(name="update_prefixes")
    async def update_prefixes(self, ctx):
        """Command to update the database with new servers and add a prefix."""
        await self.bot.pool.execute("""
            CREATE TABLE IF NOT EXISTS config (
                guild_id BIGINT PRIMARY KEY,
                prefix TEXT
            );
        """)
        for guild in self.bot.guilds:
            query = "SELECT prefix FROM config WHERE guild_id = $1"
            prefix = await self.bot.pool.fetchval(query, guild.id)
            if not prefix:
                query = "INSERT INTO config (guild_id, prefix) VALUES($1, $2)"
                await self.bot.pool.execute(query, guild.id, "!")
                print(f"Default prefix set for {guild.name}")
        await ctx.approve("Prefixes updated for all servers!")

    @command(name="ratelimit")
    async def rate_limit_status(self, ctx: Context, user: Optional[User] = None):
        """View rate limit status for a user."""
        target = user or ctx.author
        
        if not ctx.guild:
            return await ctx.warn("**This command can only be used in servers**")
        
        query = """
        SELECT command_category, usage_count, reputation_score, last_used
        FROM user_rate_limits
        WHERE user_id = $1 AND guild_id = $2
        ORDER BY command_category
        """
        records = await self.bot.pool.fetch(query, target.id, ctx.guild.id)
        
        if not records:
            return await ctx.warn(f"**{target.display_name} has no rate limit data**")
        
        embed = Embed(
            color=0xacacac,
            title=f"📊 Rate Limit Status: {target.display_name}",
            description="**Reputation affects cooldowns**"
        )
        
        for record in records:
            category = record['command_category'].title()
            usage = record['usage_count']
            reputation = record['reputation_score']
            
            if hasattr(ctx.bot, 'rate_limiter'):
                weight = ctx.bot.rate_limiter.command_weights.get(record['command_category'], 1.0)
                cooldown = ctx.bot.rate_limiter._calculate_cooldown(usage, reputation, weight)
            else:
                cooldown = 2.0
            
            embed.add_field(
                name=f"{category} Commands",
                value=f"**Usage:** {usage}\n**Reputation:** {reputation}/200\n**Cooldown:** {cooldown:.1f}s",
                inline=True
            )
        
        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Developer(bot))
