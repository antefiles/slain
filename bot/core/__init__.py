from __future__ import annotations
from contextlib import suppress
from pathlib import Path
import sys
import asyncpg
import logging
import discord
import aiohttp

from typing import List, Optional, cast
from discord import (
    ClientUser,
    Color,
    Embed,
    Interaction,
    Message,
    AllowedMentions,
    Intents,
    ActivityType,
    Permissions,
    TextChannel,
    VoiceChannel,
    Forbidden,
)
from discord.ext.commands import (
    AutoShardedBot,
    NotOwner,
    ExtensionError,
    CheckFailure,
    CommandError,
    MissingRequiredArgument,
    ConversionError,
    MissingPermissions,
    CommandNotFound,
    BadColourArgument,
    RoleNotFound,
    ChannelNotFound,
    DisabledCommand,
    ThreadNotFound,
    BadUnionArgument,
    MissingRequiredAttachment,
    BadLiteralArgument,
    UserNotFound,
    MemberNotFound,
    GuildNotFound,
    BadInviteArgument,
    UserInputError,
    CommandOnCooldown,
    when_mentioned,
    when_mentioned_or,
)

from bot.shared.formatter import human_join, hyperlink
from bot.core.cooldown_manager import CooldownManager
from aiohttp import ClientSession
from psutil import Process
from psutil._common import bytes2human as humanize_bytes

from .context import Context, HelpCommand
from .rate_limiter import DynamicRateLimiter

from cashews import cache

cache.setup("redis://localhost:6379")

async def global_permission_check(ctx: Context) -> bool:
    """Global check to ensure bot has necessary permissions and role hierarchy."""
    
    if not ctx.guild:
        return True
    
    # Allow help commands to always work
    if ctx.command and ctx.command.qualified_name.startswith('help'):
        return True
    
    bot_member = ctx.guild.me
    if not bot_member:
        return False
    
    channel_permissions = ctx.channel.permissions_for(bot_member)
    
    required_perms = [
        'send_messages',
        'embed_links',
        'read_message_history',
        'view_channel'
    ]
    
    missing_perms = []
    for perm in required_perms:
        if not getattr(channel_permissions, perm, False):
            missing_perms.append(perm)
    
    if missing_perms:
        try:
            if channel_permissions.send_messages:
                await ctx.warn(
                    f"I'm missing the following permissions: {', '.join(f'`{perm}`' for perm in missing_perms)}",
                    tip="Check my role permissions and channel overwrites"
                )
        except:
            pass
        return False
    
    if ctx.command and ctx.command.cog_name in ['Moderation', 'Warnings', 'Fakeperms']:
        if hasattr(ctx, 'target_member') and ctx.target_member:
            if ctx.target_member.top_role >= bot_member.top_role and ctx.target_member.id != ctx.guild.owner_id:
                await ctx.warn(
                    "I cannot perform this action because the target user's role is higher than or equal to mine",
                    tip="Move my role higher in the role hierarchy"
                )
                return False
    
    return True

class Bot(AutoShardedBot):
    pool: asyncpg.Pool
    session: ClientSession
    user: ClientUser
    rate_limiter: DynamicRateLimiter
    cooldown_manager = CooldownManager()

    def __init__(self) -> None:
        super().__init__(
            command_prefix=self.get_prefixes,
            strip_after_prefix=True,
            help_command=HelpCommand(),
            case_insensitive=True,
            intents=Intents.all(),
            allowed_mentions=AllowedMentions(
                everyone=False,
                users=True,
                roles=False,
                replied_user=False,
            ),
            activity=discord.Activity(
                name="feedback",
                type=ActivityType.listening,
            ),
            status=discord.Status.idle, 
            owner_ids=[
                209482725160255489
            ],
        )
        import redis.asyncio as redis
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
        self.session = None
        self.add_check(global_permission_check)

    async def startup(self):
        if not self.session:
            self.session = aiohttp.ClientSession(headers={
                "User-Agent": "SlainBot (https://slainbot.dev, v1.0)"
            })

    async def close(self):
        await self.session.close()
        await super().close()

    @property
    def version(self) -> str:
        return sys.argv[sys.argv.index("-v") + 1] if "-v" in sys.argv else "1.0.0"

    @property
    def process(self) -> Process:
        return Process()

    @property
    def ping(self) -> int:
        return round(self.latency * 1000)

    @property
    def members(self):
        return list(self.get_all_members())

    @property
    def channels(self):
        return list(self.get_all_channels())

    @property
    def text_channels(self):
        return list(
            filter(
                lambda channel: isinstance(channel, TextChannel),
                self.get_all_channels(),
            )
        )

    @property
    def voice_channels(self):
        return list(
            filter(
                lambda channel: isinstance(channel, VoiceChannel),
                self.get_all_channels(),
            )
        )

    @property
    def public_cogs(self) -> list:
        return [
            cog.qualified_name
            for cog in self.cogs.values()
            if cog.qualified_name not in ("Jishaku", "dev")
        ]

    @property
    def invite_url(self) -> str:
        return discord.utils.oauth_url(self.user.id, permissions=Permissions(8))

    @classmethod
    async def get_prefixes(cls, bot: Bot, message: Message):
        if not message.guild:
            return when_mentioned(bot, message)

        query = """
        SELECT (
            SELECT prefix
            FROM config
            WHERE guild_id = $1
        ) AS guild_prefix,
        (
            SELECT prefix
            FROM user_config
            WHERE user_id = $2
        ) AS user_prefix
        """
        record = await bot.pool.fetchrow(query, message.guild.id, message.author.id)
        prefixes = {record["guild_prefix"] or "-"}
        if record["user_prefix"]:
            prefixes.add(record["user_prefix"])

        return when_mentioned_or(*prefixes)(bot, message)

    async def setup_hook(self) -> None:
        self.session = ClientSession()
        self.tree.interaction_check = self.blacklist_check

    async def on_ready(self) -> None:
        logging.info(f"Logged in as {self.user}")
        await self.load_extensions()

    async def load_extensions(self):
        await self.load_extension("jishaku")
        for extension in Path("bot/extensions").glob("*"):
            if extension.is_file() and extension.suffix == ".py":
                package = extension.stem

            elif extension.is_dir() and (extension / "__init__.py").exists():
                package = extension.stem

            else:
                continue

            try:
                await self.load_extension(f"bot.extensions.{package}")
            except ExtensionError as exc:
                logging.error(f"Failed to load extension {package}", exc_info=exc)
            else:
                logging.info(f"Loaded extension {package}")

    async def is_blacklisted(self, target_ids: List[int]) -> bool:
        query = """
        SELECT EXISTS(
            SELECT 1
            FROM blacklist
            WHERE target_id = ANY($1::BIGINT[])
        )
        """
        return cast(bool, await self.pool.fetchval(query, target_ids))

    async def blacklist_check(self, interaction: Interaction):
        if not interaction.guild_id:
            return False

        blacklisted = await self.is_blacklisted([
            interaction.guild_id,
            interaction.user.id,
        ])
        if blacklisted:
            if hasattr(self, 'rate_limiter'):
                blacklist_category = "blacklist_notification"
                
                query = """
                SELECT last_used FROM user_rate_limits
                WHERE user_id = $1 AND guild_id = $2 AND command_category = $3
                """
                record = await self.pool.fetchrow(query, interaction.user.id, interaction.guild_id, blacklist_category)
                
                if record and record['last_used']:
                    from datetime import datetime, timezone
                    time_since_last = (datetime.now(timezone.utc) - record['last_used']).total_seconds()
                    if time_since_last < 30.0:
                        return False
                
                await self.pool.execute("""
                    INSERT INTO user_rate_limits (user_id, guild_id, command_category, last_used)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (user_id, guild_id, command_category)
                    DO UPDATE SET last_used = NOW()
                """, interaction.user.id, interaction.guild_id, blacklist_category)
            
            await interaction.response.send_message(
                "You are blacklisted from using this bot",
                ephemeral=True,
            )
            return False

        return True
    
    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        *,
        cls=None,
    ) -> Context:
        return await super().get_context(origin, cls=Context)

    async def process_commands(self, message: Message):
        ctx = await self.get_context(message)

        if not all((ctx.guild, ctx.channel, not ctx.author.bot)):
            return

        if await self.is_blacklisted([ctx.guild.id, ctx.author.id]):
            return

        permissions = ctx.channel.permissions_for(ctx.guild.me)
        if not (permissions.send_messages and permissions.embed_links):
            return

        async def process():
            # Handle mention for prefix display first, before checking ctx.valid
            if message.content == self.user.mention:
                prefix_category = "prefix_mention"

                query = """
                SELECT last_used FROM user_rate_limits
                WHERE user_id = $1 AND guild_id = $2 AND command_category = $3
                """
                record = await self.pool.fetchrow(query, ctx.author.id, ctx.guild.id, prefix_category)

                if record and record['last_used']:
                    from datetime import datetime, timezone
                    time_since_last = (datetime.now(timezone.utc) - record['last_used']).total_seconds()
                    if time_since_last < 10.0:
                        return

                await self.pool.execute("""
                    INSERT INTO user_rate_limits (user_id, guild_id, command_category, last_used)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (user_id, guild_id, command_category)
                    DO UPDATE SET last_used = NOW()
                """, ctx.author.id, ctx.guild.id, prefix_category)

                user_query = "SELECT prefix FROM user_config WHERE user_id = $1;"
                user_row = await self.pool.fetchrow(user_query, ctx.author.id)
                if user_row:
                    prefix = user_row["prefix"]
                else:
                    guild_query = "SELECT prefix FROM config WHERE guild_id = $1;"
                    guild_row = await self.pool.fetchrow(guild_query, ctx.guild.id)
                    prefix = guild_row["prefix"] if guild_row else "-"

                embed = Embed(
                    color=0xacacac,
                    description=f"<:slain_Settings:1391058914816167996> Server prefix is set to **{prefix}**",
                )
                from discord import ui
                view = ui.View()
                view.add_item(
                    ui.Button(
                        label="Website",
                        url="https://slain.bot",
                        emoji="🌐"
                    )
                )
                return await ctx.send(embed=embed)

            if ctx.valid:
                # (Optional: Admin permission check logic here)
                ...

            if hasattr(self, 'rate_limiter'):
                can_execute, remaining_time = await self.rate_limiter.check_rate_limit(ctx)
                if not can_execute:
                    cooldown_seconds = 5
                    key = (ctx.author.id, ctx.command.qualified_name)
                    last_warn = getattr(self.cooldown_manager, "warn_cache", {}).get(key)

                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)

                    if not last_warn or (now - last_warn).total_seconds() > cooldown_seconds:
                        self.cooldown_manager.warn_cache[key] = now
                        return await ctx.warn(
                            f"You're being rate limited. Try again in **{int(remaining_time)} seconds**"
                        )
                    return

            await self.invoke(ctx)

        await process()

    async def on_command_error(
        self,
        ctx: Context,
        exception: CommandError,
    ) -> Optional[Message]:
        if not (
            ctx.channel.permissions_for(ctx.guild.me).send_messages
            and ctx.channel.permissions_for(ctx.guild.me).embed_links
        ):
            return

        if hasattr(self, 'rate_limiter') and ctx.guild:
            error_category = "error_handling"
            
            query = """
            SELECT last_used FROM user_rate_limits
            WHERE user_id = $1 AND guild_id = $2 AND command_category = $3
            """
            record = await self.pool.fetchrow(query, ctx.author.id, ctx.guild.id, error_category)
            
            if record and record['last_used']:
                from datetime import datetime, timezone
                time_since_last = (datetime.now(timezone.utc) - record['last_used']).total_seconds()
                if time_since_last < 5.0:
                    return 
            
            await self.pool.execute("""
                INSERT INTO user_rate_limits (user_id, guild_id, command_category, last_used)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, guild_id, command_category)
                DO UPDATE SET last_used = NOW()
            """, ctx.author.id, ctx.guild.id, error_category)

        if isinstance(
            exception,
            (
                CommandNotFound,
                DisabledCommand,
                NotOwner,
            ),
        ):
            return

        elif isinstance(
            exception,
            (
                MissingRequiredArgument,
                MissingRequiredAttachment,
                BadLiteralArgument,
            ),
        ):
            return await ctx.send_help(ctx.command)

        elif isinstance(exception, TypeError):
            await ctx.warn(str(exception))
            return

        elif isinstance(exception, MissingRequiredArgument):
            return await ctx.send_help(ctx.command.qualified_name)

        elif isinstance(exception, ConversionError):
            await ctx.warn(str(exception.original))
            return

        elif isinstance(exception, MissingPermissions):
            permissions = human_join(
                [f"**{permission}**" for permission in exception.missing_permissions],
                final=", ",
            )
            _plural = "Permission" + (len(exception.missing_permissions) > 1) * "s"
            await ctx.warn(f"{_plural} required: {permissions}")
            return

        elif isinstance(exception, BadColourArgument):
            await ctx.warn("I was unable to find that color")
            return

        elif isinstance(exception, RoleNotFound):
            await ctx.warn("The requested role does not exist or could not be found")
            return

        elif isinstance(exception, ChannelNotFound):
            await ctx.warn("The requested channel does not exist or could not be found")
            return

        elif isinstance(exception, ThreadNotFound):
            await ctx.warn("The requested thread does not exist or could not be found")
            return

        elif isinstance(exception, BadUnionArgument):
            await ctx.send(str(exception))
            return
        
        elif isinstance(exception, UserNotFound):
            await ctx.warn("The requested user could not be found")
            return

        elif isinstance(exception, MemberNotFound):
            await ctx.warn("The requested member could not be found")
            return

        elif isinstance(exception, GuildNotFound):
            await ctx.warn("The requested guild could not be found")
            return

        elif isinstance(exception, BadInviteArgument):
            await ctx.warn("The invite code you've provided is invalid")
            return

        elif isinstance(exception, UserInputError):
            await ctx.warn(str(exception))
            return

        elif isinstance(exception, CommandOnCooldown):
            if self.cooldown_manager.should_send_cooldown_warning(ctx.author.id, ctx.command.qualified_name, exception.retry_after):
                await ctx.warn(
                    f"This command is on cooldown. Try again in **{int(exception.retry_after)} seconds**"
                )
            return
        elif isinstance(exception, Forbidden):
            return await ctx.warn(
                "I'm missing permissions to fulfill this command",
                tip="This could be due to role hierarchy or channel permissions",
            )

        elif isinstance(exception, CommandError):
            if isinstance(exception, CheckFailure):
                origin = getattr(exception, "original", exception)
                with suppress(TypeError):
                    if any(
                        forbidden in origin.args[-1]
                        for forbidden in (
                            "global check",
                            "check functions",
                            "Unknown Channel",
                            "Us",
                        )
                    ):
                        return

            arguments: List[str] = []
            for argument in exception.args:
                if isinstance(argument, str):
                    arguments.append(argument)

                elif isinstance(argument, (TypeError, ValueError)):
                    arguments.extend(argument.args)

            if arguments:
                return await ctx.warn("\n".join(arguments).split("Error:")[-1])

        await ctx.warn("Something went wrong, please contact a developer")
        raise

bot: Bot = Bot()
