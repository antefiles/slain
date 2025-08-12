import discord
import json
import time
import asyncio
from discord import Embed
from discord.ext.commands import has_permissions, Cog, group, Context
from discord.ext import commands
from bot.core import Bot
from cashews import cache
from types import SimpleNamespace
from ...shared.formatter import compact_number
from ...shared.paginator import Paginator
from ..embeds import replace_vars, build_embed_from_raw
from bot.shared.fakeperms import hybrid_permissions
from discord import SystemChannelFlags


def make_fake_ctx(bot, guild, author, channel):
    return SimpleNamespace(
        bot=bot,
        guild=guild,
        author=author,
        channel=channel,
        clean_prefix=","  # default fallback
    )

class Welcome(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.last_query_time = {}
        self.welcome_queues = {}
        self.welcome_tasks = {}

    async def get_welcome_message(self, guild_id: int):
        cached_message = await cache.get(f"welcome:{guild_id}")
        if cached_message:
            return json.loads(cached_message)

        row = await self.bot.pool.fetchrow(
            "SELECT channel_id, raw FROM welcome_messages WHERE guild_id = $1",
            guild_id
        )
        if row:
            row_dict = dict(row)
            await cache.set(f"welcome:{guild_id}", json.dumps(row_dict), expire=3600)
            return row_dict
        return None

    @Cog.listener()
    async def on_member_join(self, member):
        guild_id = member.guild.id

        if guild_id not in self.welcome_queues:
            self.welcome_queues[guild_id] = asyncio.Queue()
            self.welcome_tasks[guild_id] = self.bot.loop.create_task(self.process_welcome_queue(guild_id))

        await self.welcome_queues[guild_id].put(member)

    async def process_welcome_queue(self, guild_id: int):
        queue = self.welcome_queues[guild_id]
        while True:
            member = await queue.get()
            try:
                row = await self.get_welcome_message(guild_id)
                if not row:
                    continue

                channel = member.guild.get_channel(row["channel_id"])
                if not channel:
                    continue

                ctx = make_fake_ctx(self.bot, member.guild, member, channel)
                raw = row.get("raw")
                if not raw:
                    continue

                if "{embed}" in raw:
                    try:
                        message_content, embed = await build_embed_from_raw(self.bot, ctx, raw)
                        await channel.send(content=message_content or None, embed=embed)
                    except Exception:
                        continue
                else:
                    content = replace_vars(raw, ctx)
                    await channel.send(content=content)

            except Exception as e:
                print(f"[Welcome Queue Error] {e}")

            await asyncio.sleep(2)

    @group(name="welcome", usage='welcome')
    async def welcome_group(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @welcome_group.command(name="create", usage='welcome create [channel or id] [message]')
    @hybrid_permissions(manage_guild=True)
    async def welcome_create(self, ctx: Context, channel: discord.TextChannel, *, raw: str):
        existing = await self.bot.pool.fetchrow(
            "SELECT channel_id FROM welcome_messages WHERE guild_id = $1",
            ctx.guild.id
        )
        if existing:
            return await ctx.warn("A welcome message is already set for this server.")

        await self.bot.pool.execute(
            """
            INSERT INTO welcome_messages (guild_id, channel_id, raw)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, raw = $3
            """,
            ctx.guild.id, channel.id, raw
        )
        await cache.set(f"welcome:{ctx.guild.id}", json.dumps({'channel_id': channel.id, 'raw': raw}), expire=3600)
        await ctx.approve(f"Welcome message has been set for {channel.mention}.")

    @welcome_group.command(name="remove", usage='welcome remove')
    @hybrid_permissions(manage_guild=True)
    async def welcome_remove(self, ctx: Context):
        row = await self.bot.pool.fetchrow(
            "SELECT channel_id FROM welcome_messages WHERE guild_id = $1",
            ctx.guild.id
        )
        if not row:
            return await ctx.warn("No welcome message is set for this server.")

        await self.bot.pool.execute("DELETE FROM welcome_messages WHERE guild_id = $1", ctx.guild.id)
        await cache.delete(f"welcome:{ctx.guild.id}")
        await ctx.approve("Welcome message has been removed.")

    @welcome_group.command(name="test", usage='welcome test')
    @hybrid_permissions(manage_guild=True)
    async def welcome_test(self, ctx: Context):
        row = await self.get_welcome_message(ctx.guild.id)
        if not row:
            return await ctx.warn("No welcome message is set for this server.")

        channel = ctx.guild.get_channel(row["channel_id"])
        if not channel:
            return await ctx.warn("The configured welcome channel no longer exists.")

        fake_ctx = make_fake_ctx(self.bot, ctx.guild, ctx.author, channel)
        raw = row.get("raw")
        if not raw:
            return await ctx.warn("This welcome message has no content to test.")

        if "{embed}" in raw:
            try:
                message_content, embed = await build_embed_from_raw(self.bot, fake_ctx, raw)
                await channel.send(content=message_content or None, embed=embed)
                await ctx.approve(f"Welcome message preview sent to {channel.mention}")
            except Exception as e:
                await ctx.warn(f"Failed to build welcome embed: `{e}`")
        else:
            try:
                content = replace_vars(raw, fake_ctx)
                await channel.send(content=content)
                await ctx.approve(f"Welcome message preview sent to {channel.mention}")
            except Exception as e:
                await ctx.warn(f"Failed to render welcome message: `{e}`")

class Boost(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def get_boost_message(self, guild_id: int):
        cached = await cache.get(f"boost:{guild_id}")
        if cached:
            return json.loads(cached)

        row = await self.bot.pool.fetchrow("SELECT channel_id, raw FROM boost_messages WHERE guild_id = $1", guild_id)
        if row:
            data = dict(row)
            await cache.set(f"boost:{guild_id}", json.dumps(data), expire=3600)
            return data
        return None

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            await self.handle_boost(after)
        elif before.premium_since is not None and after.premium_since is None:
            pass

    @Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.type != discord.MessageType.premium_guild_subscription:
            return
        
        if message.author and message.guild:
            await self.handle_boost(message.author)

    async def handle_boost(self, member: discord.Member):
        guild = member.guild
        if not guild:
            return

        row = await self.get_boost_message(guild.id)
        if not row:
            return

        channel = guild.get_channel(row["channel_id"])
        if not channel:
            return

        permissions = channel.permissions_for(guild.me)
        if not (permissions.send_messages and permissions.embed_links):
            return

        ctx = make_fake_ctx(self.bot, guild, member, channel)
        raw = row.get("raw")
        if not raw:
            return

        if "{embed}" in raw:
            try:
                message_content, embed = await build_embed_from_raw(self.bot, ctx, raw)
                await channel.send(content=message_content or None, embed=embed)
            except Exception as e:
                print(f"[Boost Message Error] {e}")
        else:
            try:
                content = replace_vars(raw, ctx)
                await channel.send(content=content)
            except Exception as e:
                print(f"[Boost Message Error] {e}")

    @group(name="boost", usage='boost')
    async def boost_group(self, ctx: Context):
        """
        Setup boost messages for your server
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @boost_group.command(name="create", usage='boost create [channel or id] [message]')
    @hybrid_permissions(manage_guild=True)
    async def boost_create(self, ctx: Context, channel: discord.TextChannel, *, raw: str):
        """
        Create a custom boost message to send when a user boosts the server
        """
        existing = await self.bot.pool.fetchrow(
            "SELECT channel_id FROM boost_messages WHERE guild_id = $1",
            ctx.guild.id
        )
        if existing:
            return await ctx.warn("A boost message is already set for this server")

        await self.bot.pool.execute(
            """
            INSERT INTO boost_messages (guild_id, channel_id, raw)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, raw = $3
            """,
            ctx.guild.id, channel.id, raw
        )
        await cache.set(f"boost:{ctx.guild.id}", json.dumps({'channel_id': channel.id, 'raw': raw}), expire=3600)

        flags = discord.SystemChannelFlags(
            join_notifications=False,
            premium_subscriptions=True,
            guild_reminder_notifications=False
        )
        try:
            await ctx.guild.edit(
                system_channel=channel,
                system_channel_flags=flags,
                reason="Boost message set"
            )
        except Exception as e:
            await ctx.warn(f"Failed to update system channel flags: `{e}`")
            return

        await ctx.approve(f"Boost message has been set for {channel.mention}")

    @boost_group.command(name="remove", usage='boost remove')
    @hybrid_permissions(manage_guild=True)
    async def boost_remove(self, ctx: Context):
        """
        Remove the custom boost message and channel
        """
        row = await self.bot.pool.fetchrow("SELECT channel_id FROM boost_messages WHERE guild_id = $1", ctx.guild.id)
        if not row:
            return await ctx.warn("No boost message is set for this server")

        await self.bot.pool.execute("DELETE FROM boost_messages WHERE guild_id = $1", ctx.guild.id)
        await cache.delete(f"boost:{ctx.guild.id}")
        await ctx.approve("Boost message has been removed")

    @boost_group.command(name="test", usage='boost test')
    @hybrid_permissions(manage_guild=True)
    async def boost_test(self, ctx: Context):
        """
        Test the boost message created for your server
        """
        row = await self.get_boost_message(ctx.guild.id)
        if not row:
            return await ctx.warn("No boost message is set for this server")

        channel = ctx.guild.get_channel(row["channel_id"])
        if not channel:
            return await ctx.warn("The configured boost channel no longer exists")

        fake_ctx = make_fake_ctx(self.bot, ctx.guild, ctx.author, channel)
        raw = row.get("raw")
        if not raw:
            return await ctx.warn("This boost message has no content to test")

        if "{embed}" in raw:
            try:
                message_content, embed = await build_embed_from_raw(self.bot, fake_ctx, raw)
                await channel.send(content=message_content or None, embed=embed)
                await ctx.approve(f"Boost message preview sent to {channel.mention}")
            except Exception as e:
                await ctx.warn(f"Failed to build boost embed: `{e}`")
        else:
            try:
                content = replace_vars(raw, fake_ctx)
                await channel.send(content=content)
                await ctx.approve(f"Boost message preview sent to {channel.mention}")
            except Exception as e:
                await ctx.warn(f"Failed to render boost message: `{e}`")

class Goodbye(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.goodbye_queues = {}
        self.goodbye_tasks = {}

    async def get_goodbye_message(self, guild_id: int):
        cached = await cache.get(f"goodbye:{guild_id}")
        if cached:
            return json.loads(cached)

        row = await self.bot.pool.fetchrow(
            "SELECT channel_id, raw FROM goodbye_messages WHERE guild_id = $1",
            guild_id
        )
        if row:
            data = dict(row)
            await cache.set(f"goodbye:{guild_id}", json.dumps(data), expire=3600)
            return data
        return None

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_id = member.guild.id

        if guild_id not in self.goodbye_queues:
            self.goodbye_queues[guild_id] = asyncio.Queue()
            self.goodbye_tasks[guild_id] = self.bot.loop.create_task(self.process_goodbye_queue(guild_id))

        await self.goodbye_queues[guild_id].put(member)

    async def process_goodbye_queue(self, guild_id: int):
        queue = self.goodbye_queues[guild_id]
        while True:
            member = await queue.get()
            try:
                row = await self.get_goodbye_message(guild_id)
                if not row:
                    continue

                channel = member.guild.get_channel(row["channel_id"])
                if not channel:
                    continue

                ctx = make_fake_ctx(self.bot, member.guild, member, channel)
                raw = row.get("raw")
                if not raw:
                    continue

                try:
                    message_content, embed = await build_embed_from_raw(self.bot, ctx, raw)
                    await channel.send(content=message_content or None, embed=embed)
                except Exception as e:
                    print(f"[Goodbye Message Error] {e}")
            except Exception as e:
                print(f"[Goodbye Queue Outer Error] {e}")
            await asyncio.sleep(2)

    @group(name="goodbye", usage='goodbye')
    async def goodbye_group(self, ctx: Context):
        """Setup messages for when users leave"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @goodbye_group.command(name="create", usage='goodbye create [channel or id] [message]')
    @hybrid_permissions(manage_guild=True)
    async def goodbye_create(self, ctx: Context, channel: discord.TextChannel, *, raw: str):
        """Create the message to send to a channel when users leave"""
        existing = await self.bot.pool.fetchrow(
            "SELECT channel_id FROM goodbye_messages WHERE guild_id = $1", ctx.guild.id
        )
        if existing:
            return await ctx.warn("A goodbye message is already set for this server")

        await self.bot.pool.execute(
            """
            INSERT INTO goodbye_messages (guild_id, channel_id, raw)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, raw = $3
            """,
            ctx.guild.id, channel.id, raw
        )
        await cache.set(f"goodbye:{ctx.guild.id}", json.dumps({'channel_id': channel.id, 'raw': raw}), expire=3600)
        await ctx.approve(f"Goodbye message has been set for {channel.mention}.")

    @goodbye_group.command(name="remove", usage='goodbye remove')
    @hybrid_permissions(manage_guild=True)
    async def goodbye_remove(self, ctx: Context):
        """Remove the channel set to send messages when a user leaves"""
        row = await self.bot.pool.fetchrow("SELECT channel_id FROM goodbye_messages WHERE guild_id = $1", ctx.guild.id)
        if not row:
            return await ctx.warn("No goodbye message is set for this server.")

        await self.bot.pool.execute("DELETE FROM goodbye_messages WHERE guild_id = $1", ctx.guild.id)
        await cache.delete(f"goodbye:{ctx.guild.id}")
        await ctx.approve("Goodbye message has been removed")

    @goodbye_group.command(name="test", usage='goodbye test')
    @hybrid_permissions(manage_guild=True)
    async def goodbye_test(self, ctx: Context):
        """Test the goodbye message created for the server"""
        row = await self.get_goodbye_message(ctx.guild.id)
        if not row:
            return await ctx.warn("No goodbye message is set for this server")

        channel = ctx.guild.get_channel(row["channel_id"])
        if not channel:
            return await ctx.warn("The configured goodbye channel no longer exists")

        fake_ctx = make_fake_ctx(self.bot, ctx.guild, ctx.author, channel)
        raw = row.get("raw")
        if not raw:
            return await ctx.warn("This goodbye message has no content to test")

        try:
            message_content, embed = await build_embed_from_raw(self.bot, fake_ctx, raw)
            await channel.send(content=message_content or None, embed=embed)
            await ctx.approve(f"Goodbye message preview sent to {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to build goodbye embed: `{e}`")



async def setup(bot: Bot) -> None:
    await bot.add_cog(Welcome(bot))
    await bot.add_cog(Boost(bot))
    await bot.add_cog(Goodbye(bot))