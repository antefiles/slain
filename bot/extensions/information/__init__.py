from discord.ext.commands import Cog, command, has_permissions
from discord import Embed, Emoji, File, StickerFormatType
import discord, traceback, re, requests, asyncio, aiohttp, time, hashlib, difflib, io
import emoji, random
import pytz
from bot.core import Bot
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord.ext.commands import Cog, command, group, Context, BucketType, cooldown
from ...shared.paginator import Paginator
from ...shared.formatter import compact_number
from ..embeds import replace_vars, build_embed_from_raw
from bot.shared.fakeperms import hybrid_permissions
import json
from PIL import Image
from io import BytesIO
from collections import Counter
from typing import Optional
from difflib import get_close_matches
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

class Information(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @command(name="userinfo", usage='userinfo [optional: user]')
    async def userinfo(self, ctx, user: discord.Member = None):
        """
        View information about a user's profile
        """
        user = user or ctx.author
        created_at = user.created_at
        joined_at = user.joined_at
        roles_mentions = [role.mention for role in user.roles if role.name != "@everyone"]
        role_count = len(roles_mentions)
        mutual_servers = len([guild for guild in self.bot.guilds if user in guild.members])
        join_position = f"{list(ctx.guild.members).index(user) + 1}"
        roles_mentions.reverse()
        created_at_timestamp = int(created_at.timestamp())
        joined_at_timestamp = int(joined_at.timestamp())
        
        if role_count > 5:
            roles_display = ', '.join(roles_mentions[:5]) + f" +{role_count - 5} more"
        elif role_count:
            roles_display = ', '.join(roles_mentions)
        else:
            roles_display = None
        
        description = f"""
**Dates:**
**Created:** {created_at.strftime('%m/%d/%Y, %I:%M %p')} (<t:{created_at_timestamp}:R>)
**Joined:** {joined_at.strftime('%m/%d/%Y, %I:%M %p')} (<t:{joined_at_timestamp}:R>)
        """
        
        if roles_display:
            description += f"\n**Roles:** {roles_display}"

        embed = discord.Embed(
            description=description,
            color=0xacacac
        )
        embed.set_author(name=f"{user} ({user.id})")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        else:
            embed.set_thumbnail(url="https://example.com/default-avatar.png")
        embed.set_footer(text=f"Join Position: {join_position} | Mutual Servers: {mutual_servers}")
        
        await ctx.send(embed=embed)
  

    @command(name="serverinfo", usage='serverinfo')
    async def serverinfo(self, ctx):
        """
        View information about the server
        """
        guild = ctx.guild
        created_at = guild.created_at
        created_at_timestamp = int(created_at.timestamp())
        owner = guild.owner
        total_members = guild.member_count
        humans = len([member for member in guild.members if not member.bot])
        bots = total_members - humans
        boosts = guild.premium_subscription_count

        splash_url = guild.splash.url if guild.splash else "None"
        banner_url = guild.banner.url if guild.banner else "None"
        icon_url = guild.icon.url if guild.icon else "None"
        bio = guild.description if guild.description else "None"

        channels_count = len(guild.text_channels) + len(guild.voice_channels)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        category_channels = len(guild.categories)

        role_count = len(guild.roles)
        emoji_count = len(guild.emojis)

        splash_display = f"[Click here]({splash_url})" if splash_url != "None" else "None"
        banner_display = f"[Click here]({banner_url})" if banner_url != "None" else "None"
        icon_display = f"[Click here]({icon_url})" if icon_url != "None" else "None"

        description = f"""
**Server Created:** {created_at.strftime('%B %d, %Y')} (<t:{created_at_timestamp}:R>)
**Bio:** {bio}

**Owner:** {owner}

**__Members:__**
- Total: {total_members}
- Humans: {humans}
- Bots: {bots}

**__Design:__**
- Splash: {splash_display}
- Banner: {banner_display}
- Icon: {icon_display}

**__Channels:__** ({channels_count})
- Text: {text_channels}
- Voice: {voice_channels}
- Category: {category_channels}

**__Counts:__**
- Roles: {role_count}/250
- Emojis: {emoji_count}/500
- Boosters: {boosts}
"""
        embed = discord.Embed(
            title="Server Information",
            description=description,
            color=0xacacac
        )
        embed.set_author(name=f"{guild.name} ({guild.id})")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Guild ID: {guild.id} | {created_at.strftime('%m/%d/%Y, %I:%M %p')}")
        await ctx.send(embed=embed)


    @command(name="roleinfo", usage='roleinfo [role]')
    async def roleinfo(self, ctx, *, role_name: str = None):
        """
        View information about a specific role
        """
        role_name = role_name or ctx.author.top_role.name
        role = next(
            (r for r in ctx.guild.roles if role_name.lower() in r.name.lower()), 
            None
        )
        if not role:
            return await ctx.warn("Role not found.")
        
        created_at = role.created_at
        created_at_timestamp = int(created_at.timestamp())
        guild = ctx.guild
        role_members = [member.name for member in guild.members if role in member.roles]
        role_count = len(role_members)
        emoji_match = re.search(r"<:.*?:\d+>", role.name)
        emoji_url = None
        if emoji_match:
            emoji_url = emoji_match.group(0)

        embed = discord.Embed(
            title=f"{role.name}",
            color=role.color
        )
        embed.add_field(name="Role ID", value=f'`{role.id}`', inline=True)
        embed.add_field(name="Guild", value=f"{guild.name} (`{guild.id}`)", inline=True)
        embed.add_field(name="Color", value=f"{role.color}", inline=True)
        embed.add_field(name="Creation Date", value=f"{created_at.strftime('%B %d, %Y, %I:%M %p')} (<t:{created_at_timestamp}:R>)", inline=True)
        embed.set_author(name=f"{ctx.author.name}", url=ctx.author.display_avatar.url)
        
        if role_members:
            displayed_members = ", ".join(role_members[:8]) + ("..." if role_count > 8 else "")
            embed.add_field(name=f"{role_count} Member(s)", value=displayed_members, inline=False)
        
        if emoji_url:
            embed.set_thumbnail(url=emoji_url)
        
        embed.set_footer(text=f"Role ID: {role.id}")

        await ctx.send(embed=embed)


    @command(name="channelinfo", usage='channelinfo [channel]')
    async def channelinfo(self, ctx, *, channel_name: str = None):
        """
        View information about a specific channel
        """
        channel_name = channel_name or ctx.channel.name
        channel = next(
            (ch for ch in ctx.guild.text_channels if channel_name.lower() in ch.name.lower()), 
            next(
                (ch for ch in ctx.guild.voice_channels if channel_name.lower() in ch.name.lower()), 
                None
            )
        )
        if not channel:
            return await ctx.warn("Channel not found")
        
        created_at = channel.created_at
        created_at_timestamp = int(created_at.timestamp())
        guild = ctx.guild
        category = channel.category
        topic = channel.topic if isinstance(channel, discord.TextChannel) else "No topic on this channel"
        
        embed = discord.Embed(
            title=f"{channel.name}",
            color=0xacacac
        )
        embed.add_field(name="Channel ID", value=f'`{channel.id}`', inline=True)
        embed.add_field(name="Guild", value=f"{guild.name} (`{guild.id}`)", inline=True)
        embed.add_field(name="Type", value=f'`{channel.type}`', inline=False)
        embed.add_field(name="Category", value=category.name if category else "No category", inline=True)

        if isinstance(channel, discord.VoiceChannel):
            embed.add_field(name="Bitrate", value=f"{channel.bitrate} bps", inline=False)
            embed.add_field(name="User Limit", value=f"{channel.user_limit if channel.user_limit else 'Unlimited'}", inline=False)
        else:
            embed.add_field(name="Topic", value=topic, inline=False)
        
        embed.add_field(name="Creation Date", value=f"{created_at.strftime('%B %d, %Y, %I:%M %p')} (<t:{created_at_timestamp}:R>)", inline=True)
        embed.set_author(name=f"{ctx.author.name}", url=ctx.author.avatar.url)

        await ctx.send(embed=embed)


    @command(name="avatar", aliases=["av"], usage='avatar [Optional: user]')
    async def avatar(self, ctx, user: discord.Member = None):
        """
        View a users avatar set for their account
        """
        user = user or ctx.author
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        embed = Embed(
            title=f"{user.name}'s Avatar",
            url=avatar_url,  
            color=0x2b2d31
        )
        embed.set_image(url=avatar_url)
        
        await ctx.send(embed=embed)


    @command(name="serveravatar", aliases=["sav"], usage='serveravatar [Optional: user]')
    async def serveravatar(self, ctx, user: discord.Member = None):
        """
        View a users avatar they have set exclusively for the server
        """
        user = user or ctx.author
        server_avatar_url = user.display_avatar.url

        embed = Embed(
            title=f"{user.display_name}'s Server Avatar",
            url=server_avatar_url,
            color=0x2b2d31
        )
        embed.set_image(url=server_avatar_url)
        await ctx.send(embed=embed)


    @command(name="banner", usage='banner [Optional: user]')
    async def banner(self, ctx, user: discord.Member = None):
        """
        View a users banner they have set
        """
        user = user or ctx.author
        try:
            user = await self.bot.fetch_user(user.id)
            if user.banner:
                embed = Embed(
                    title=f"{user.display_name}'s Banner",
                    url=user.banner.url,
                    color=0x2b2d31
                )
                embed.set_image(url=user.banner.url)
                await ctx.send(embed=embed)
            else:
                await ctx.warn(f"**{user.display_name}** does not have a banner set")
    
        except discord.NotFound:
            await ctx.warn(f"**{user.display_name}** not found")
        except discord.HTTPException as e:
            print(f"Error occurred: {e}")
            await ctx.warn("There was an error fetching the banner")

    @command(name="guildicon", usage='guildicon')
    async def guildicon(self, ctx):
        """
        View the avatar set for the server
        """
        guild = ctx.guild
        icon_url = guild.icon.url if guild.icon else None
        if icon_url:
            embed = Embed(
                title=f"{guild.name}'s Guild Icon",
                url=icon_url,
                color=0x2b2d31
            )
            embed.set_image(url=icon_url)
            await ctx.send(embed=embed)
        else:
            await ctx.warn("This server does not have an icon set.")


    @command(name="guildbanner", usage='guildbanner')
    async def guildbanner(self, ctx):
        """
        View the banner set for the server
        """
        guild = ctx.guild
        banner_url = guild.banner.url if guild.banner else None
        if banner_url:
            embed = Embed(
                title=f"{guild.name}'s Guild Banner",
                url=banner_url,
                color=0x2b2d31
            )
            embed.set_image(url=banner_url)
            await ctx.send(embed=embed)
        else:
            await ctx.warn("This server does not have a banner set.")


    @command(name="guildsplash", usage='guildsplash')
    async def splash(self, ctx):
        """
        View the splash set for the server
        """
        splash_url = ctx.guild.splash.url if ctx.guild.splash else None
        if splash_url:
            embed = Embed(
                title=f"{ctx.guild.name}'s Splash Image",
                url=splash_url,
                color=0x2b2d31
            )
            embed.set_image(url=splash_url)
            await ctx.send(embed=embed)
        else:
            await ctx.warn(f"**{ctx.guild.name}** does not have a splash image set")



class Emojis(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.cooldown_time = 60
        self.last_emoji_time = {}
        self.processing = {}
        self.upload_time = {}
        self.emoji_uploads = {}
        self.rate_limited = {}
        self.emoji_removals = {}
        self.removal_time = {}
        self.locks = {}  
        self.emoji_actions = {}
        self.action_time = {}
        self.redis = bot.redis  # Assumes you have `self.bot.redis` set elsewhere
        self.sync_emoji_usage.start()

    def cog_unload(self):
        self.emoji_dump_loop.cancel()

    @tasks.loop(minutes=1)
    async def emoji_dump_loop(self):
        await self.bot.wait_until_ready()
        guild_keys = await self.redis.keys("emoji_usage:*")

        for key in guild_keys:
            try:
                guild_id = int(key.split(":")[1])
                usage_data = await self.redis.hgetall(key, encoding="utf-8")

                for emoji_id_str, count_str in usage_data.items():
                    emoji_id = int(emoji_id_str)
                    count = int(count_str)

                    await self.bot.pool.execute(
                        """
                        INSERT INTO emoji_usage (guild_id, emoji_id, usage_count)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (guild_id, emoji_id)
                        DO UPDATE SET usage_count = emoji_usage.usage_count + $3
                        """,
                        guild_id,
                        emoji_id,
                        count,
                    )

                await self.redis.delete(key)

            except Exception as e:
                print(f"[emoji_dump_loop] Failed to flush {key}: {e}")

    @group(name="emoji", usage='emoji [Optional: emoji]', invoke_without_command=True)
    async def emoji(self, ctx):
        """
        View an emoji recently sent in the server or provided
        """
        message_to_check = ctx.message.reference.message_id if ctx.message.reference else None
        messages = []

        if message_to_check:
            try:
                message = await ctx.channel.fetch_message(message_to_check)
                messages.append(message)
            except discord.NotFound:
                pass
        else:
            messages = [message async for message in ctx.channel.history(limit=10)]

        all_emojis = []
        seen_ids = set()
        min_distance = 3

        for message in messages:
            emojis_in_message = [
                (match.start(), match.group()) for match in re.finditer(r'<a?:\w+:\d+>', message.content)
            ]
            valid_emojis = [
                emoji for i, emoji in enumerate(emojis_in_message)
                if i == 0 or emoji[0] - emojis_in_message[i - 1][0] >= min_distance
            ]
            for _, raw in valid_emojis:
                emoji_id = raw.split(":")[2][:-1]
                if emoji_id not in seen_ids:
                    ext = "gif" if raw.startswith("<a:") else "png"
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                    embed = discord.Embed(
                        title="Click to view full emoji",
                        url=url,
                        color=0x2b2d31
                    )
                    embed.set_image(url=url)
                    all_emojis.append(embed)
                    seen_ids.add(emoji_id)

        if not all_emojis:
            return await ctx.warn("No emoji in the reply or within 10 messages")

        paginator = Paginator(ctx, all_emojis, per_page=1)
        await paginator.start()


    @emoji.command(name="add", usage='emoji add [emojis]')
    @hybrid_permissions(manage_emojis=True)
    async def emoji_add(self, ctx, *emojis: str):
        """
        Add custom emojis to the server
        """
        guild_id = ctx.guild.id

        if len(emojis) > 50:
            await ctx.warn("You can only add up to **50 emojis** at once")
            return

        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()

        if self.locks[guild_id].locked():
            return await ctx.warn("An **emoji task** is already in progress in this server")

        async with self.locks[guild_id]:
            self.processing[guild_id] = True
            try:
                now = datetime.utcnow()
                record = await self.bot.pool.fetchrow(
                    "SELECT emoji_actions, last_reset FROM emoji_limits WHERE guild_id = $1",
                    guild_id,
                )

                if record:
                    if (now - record["last_reset"]).total_seconds() >= 3600:
                        emoji_actions = 0
                        await self.bot.pool.execute(
                            "UPDATE emoji_limits SET emoji_actions = 0, last_reset = $1 WHERE guild_id = $2",
                            now, guild_id
                        )
                    else:
                        emoji_actions = record["emoji_actions"]
                else:
                    emoji_actions = 0
                    await self.bot.pool.execute(
                        "INSERT INTO emoji_limits (guild_id, emoji_actions, last_reset) VALUES ($1, $2, $3)",
                        guild_id, 0, now
                    )

                if emoji_actions >= 50:
                    return await ctx.warn("This server has already performed **50 emoji actions** in the past hour")

                valid_emojis = await self.process_valid_emojis(emojis)

                total_limit = 50
                if ctx.guild.premium_tier == 1:
                    total_limit = 100
                elif ctx.guild.premium_tier == 2:
                    total_limit = 150
                elif ctx.guild.premium_tier == 3:
                    total_limit = 250

                existing = len(ctx.guild.emojis)
                available_slots = total_limit - existing

                if available_slots <= 0:
                    return await ctx.warn(f"This server has no emoji slots left\n-# *Max capacity: **{total_limit} emojis***")

                if len(valid_emojis) > available_slots:
                    return await ctx.warn(f"This server only has **{available_slots} emoji slots** remaining\n-# *Please reduce your selection*")

                if not valid_emojis:
                    return await ctx.warn("Please post **valid emojis** to add.")

                available_actions = 50 - emoji_actions
                if len(valid_emojis) > available_actions:
                    return await ctx.warn(f"Server is close to a **rate limit** for emojis\n-# *You can only **add {available_actions}** more emojis for an hour*")

                eta = len(valid_emojis) * 2
                embed = discord.Embed(
                    description=f"<a:slain_load:1392313474310209537> Adding **{len(valid_emojis)} emojis** to this server\n-# *Estimated time: **{eta} seconds***",
                    color=0x7b9fb0
                )
                message = await ctx.send(embed=embed)

                success = 0
                fail = 0

                for emoji in valid_emojis:
                    record = await self.bot.pool.fetchrow(
                        "SELECT emoji_actions FROM emoji_limits WHERE guild_id = $1",
                        guild_id,
                    )
                    if record["emoji_actions"] >= 50:
                        await ctx.warn("This server has now reached the **50 emoji actions/hour** limit")
                        break

                    if self.rate_limited.get(guild_id, False):
                        await ctx.warn("This server has reached the **global emoji rate limit**")
                        break

                    result = await self.create_emoji(ctx.guild, emoji)
                    if result:
                        success += 1
                        await self.bot.pool.execute(
                            "UPDATE emoji_limits SET emoji_actions = emoji_actions + 1 WHERE guild_id = $1",
                            guild_id
                        )
                    else:
                        fail += 1

                    await asyncio.sleep(2)

                if success > 0:
                    embed.description = f"<:slain_approve:1392318903325036635> **{success} emojis** added to the server"
                    if fail > 0:
                        embed.description += f" {fail} could not be added."
                    await message.edit(embed=embed)
                else:
                    await ctx.warn("No emojis could be added.")
            finally:
                self.processing[guild_id] = False

    @emoji.command(name="create", usage="emoji create [message link or id] OR [reply] OR [image attachment]")
    @hybrid_permissions(manage_emojis=True)
    async def emoji_create(self, ctx: Context, message_input: str = None):
        """
        Create and add an emoji with a provided image
        """
        guild_id = ctx.guild.id

        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()

        if self.locks[guild_id].locked():
            return await ctx.warn("An **emoji task** is already in progress in this server")

        if not ctx.guild.me.guild_permissions.manage_emojis_and_stickers:
            return await ctx.warn("I need the **Manage Emojis and Stickers** permission to create emojis.")

        message = None
        images = []

        if ctx.message.reference:
            try:
                message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except:
                pass
        elif message_input:
            if any(message_input.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                if message_input.startswith("http"):
                    url = message_input
                else:
                    url = f"https://cdn.discordapp.com/attachments/{ctx.channel.id}/{ctx.message.id}/{message_input}"
                images.append((url, "emoji"))
            elif message_input.isdigit():
                try:
                    message = await ctx.channel.fetch_message(int(message_input))
                except:
                    return await ctx.warn("Invalid message ID")
            elif "discord.com/channels" in message_input:
                try:
                    parts = message_input.strip().split("/")
                    channel = ctx.guild.get_channel(int(parts[-2]))
                    if channel:
                        message = await channel.fetch_message(int(parts[-1]))
                except:
                    return await ctx.warn("Invalid message link")

        if not images and not message:
            message = ctx.message

        if not images and message:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image"):
                    images.append((attachment.url, attachment.filename.split(".")[0]))

        if not images:
            return await ctx.warn("No **image attachments or valid image URL** found.")

        now = datetime.utcnow()
        record = await self.bot.pool.fetchrow(
            "SELECT emoji_actions, last_reset FROM emoji_limits WHERE guild_id = $1",
            guild_id,
        )

        if record:
            if (now - record["last_reset"]).total_seconds() >= 3600:
                emoji_actions = 0
                await self.bot.pool.execute(
                    "UPDATE emoji_limits SET emoji_actions = 0, last_reset = $1 WHERE guild_id = $2",
                    now, guild_id
                )
            else:
                emoji_actions = record["emoji_actions"]
        else:
            emoji_actions = 0
            await self.bot.pool.execute(
                "INSERT INTO emoji_limits (guild_id, emoji_actions, last_reset) VALUES ($1, $2, $3)",
                guild_id, 0, now
            )

        if emoji_actions >= 50:
            return await ctx.warn("This server has already performed **50 emoji actions** in the past hour")

        total_limit = 50
        if ctx.guild.premium_tier == 1:
            total_limit = 100
        elif ctx.guild.premium_tier == 2:
            total_limit = 150
        elif ctx.guild.premium_tier == 3:
            total_limit = 250

        existing = len(ctx.guild.emojis)
        available_slots = total_limit - existing
        if available_slots <= 0:
            return await ctx.warn(f"This server has no emoji slots left\n-# *Max capacity: **{total_limit} emojis***")

        if len(images) > available_slots:
            return await ctx.warn(f"This server only has **{available_slots} emoji slots** remaining\n-# *Please reduce your selection*")

        remaining_actions = 50 - emoji_actions
        if len(images) > remaining_actions:
            return await ctx.warn(f"Server is close to a **rate limit** for emojis\n-# *You can only **add {remaining_actions}** more emojis for an hour*")

        eta = len(images) * 2
        embed = discord.Embed(
            description=f"<a:slain_load:1392313474310209537> Creating **{len(images)} emojis**...\n-# *Estimated time: **{eta} seconds***",
            color=0x7b9fb0
        )
        msg = await ctx.send(embed=embed)

        success = 0
        fail = 0

        async with self.locks[guild_id]:
            async with aiohttp.ClientSession() as session:
                for url, base_name in images:
                    if success + emoji_actions >= 50:
                        break
                    try:
                        async with session.get(url) as response:
                            if response.status == 429:
                                self.rate_limited[guild_id] = True
                                self.bot.loop.call_later(3600, lambda: self.rate_limited.pop(guild_id, None))
                                break
                            elif response.status == 200:
                                image_data = await response.read()
                                emoji = await ctx.guild.create_custom_emoji(
                                    name=f"{base_name[:30]}",
                                    image=image_data,
                                    reason=f"Added by {ctx.author}"
                                )
                                await self.bot.pool.execute(
                                    "UPDATE emoji_limits SET emoji_actions = emoji_actions + 1 WHERE guild_id = $1",
                                    guild_id
                                )
                                success += 1
                            else:
                                fail += 1
                    except Exception as e:
                        print(f"Failed to create emoji: {e}")
                        fail += 1
                    await asyncio.sleep(2)

        result = f"<:slain_approve:1392318903325036635> **{success} emojis** created"
        if fail > 0:
            result += f", **{fail}** failed"
        embed.description = result
        await msg.edit(embed=embed)


        
    @emoji.command(name="remove", aliases=["delete"], usage='emoji remove [emojis]')
    @hybrid_permissions(manage_emojis=True)
    async def emoji_remove(self, ctx, *emoji_inputs: str):
        """
        Remove custom emojis from the server
        """
        guild_id = ctx.guild.id

        if not ctx.guild.me.guild_permissions.manage_emojis_and_stickers:
            return await ctx.warn("I need the **Manage Emojis and Stickers** permission to remove emojis.")

        if not emoji_inputs:
            return await ctx.warn("You must specify emojis to remove")

        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()

        if self.locks[guild_id].locked():
            return await ctx.warn("An **emoji task** is already in progress in this server")

        now = datetime.utcnow()
        record = await self.bot.pool.fetchrow(
            "SELECT emoji_actions, last_reset FROM emoji_limits WHERE guild_id = $1",
            guild_id,
        )

        if record:
            if (now - record["last_reset"]).total_seconds() >= 3600:
                emoji_actions = 0
                await self.bot.pool.execute(
                    "UPDATE emoji_limits SET emoji_actions = 0, last_reset = $1 WHERE guild_id = $2",
                    now, guild_id
                )
            else:
                emoji_actions = record["emoji_actions"]
        else:
            emoji_actions = 0
            await self.bot.pool.execute(
                "INSERT INTO emoji_limits (guild_id, emoji_actions, last_reset) VALUES ($1, $2, $3)",
                guild_id, 0, now
            )

        if emoji_actions >= 50:
            return await ctx.warn("This server has already performed **50 emoji actions** in the past hour")

        input_string = ' '.join(emoji_inputs)
        emoji_mentions = re.findall(r"<a?:\w+:(\d+)>", input_string)
        raw_ids = re.findall(r"\b\d{17,20}\b", input_string)
        names = input_string.split()

        resolved_emojis = []

        for eid in emoji_mentions:
            emoji = ctx.guild.get_emoji(int(eid))
            if emoji and emoji not in resolved_emojis:
                resolved_emojis.append(emoji)

        for rid in raw_ids:
            emoji = ctx.guild.get_emoji(int(rid))
            if emoji and emoji not in resolved_emojis:
                resolved_emojis.append(emoji)

        for name in names:
            emoji = discord.utils.get(ctx.guild.emojis, name=name)
            if emoji and emoji not in resolved_emojis:
                resolved_emojis.append(emoji)

        if not resolved_emojis:
            return await ctx.warn("No valid custom emojis found in your input")

        remaining_actions = 50 - emoji_actions
        if len(resolved_emojis) > remaining_actions:
            return await ctx.warn(f"Server is close to a **rate limit** for emojis\n-# *You can only **remove {remaining_actions}** more emojis for an hour*")

        embed = discord.Embed(
            description=f"<a:slain_load:1392313474310209537> Removing **{len(resolved_emojis)} emojis**...\n-# *Estimated time: **{len(resolved_emojis) * 2} seconds***",
            color=0x7b9fb0
        )
        message = await ctx.send(embed=embed)

        success = 0
        fail = 0

        async with self.locks[guild_id]:
            for emoji in resolved_emojis:
                try:
                    await emoji.delete(reason=f"Removed by {ctx.author} via command")
                    await self.bot.pool.execute(
                        "UPDATE emoji_limits SET emoji_actions = emoji_actions + 1 WHERE guild_id = $1",
                        guild_id
                    )
                    success += 1
                except Exception as e:
                    print(f"Failed to delete emoji {emoji}: {e}")
                    fail += 1
                await asyncio.sleep(2)

        result = f"<:slain_approve:1392318903325036635> **{success} emojis** were removed"
        if fail > 0:
            result += f" {fail} could not be removed"
        embed.description = result

        await message.edit(embed=embed)


    @emoji.command(name="steal", usage='emoji steal')
    @hybrid_permissions(manage_emojis=True)
    async def emoji_steal(self, ctx):
        """
        Add the most recently used emoji to the server
        """
        guild_id = ctx.guild.id

        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()

        if self.locks[guild_id].locked():
            return await ctx.warn("An **emoji task** is already in progress in this server")

        now = datetime.utcnow()
        record = await self.bot.pool.fetchrow(
            "SELECT emoji_actions, last_reset FROM emoji_limits WHERE guild_id = $1", guild_id
        )

        if record:
            if (now - record["last_reset"]).total_seconds() >= 3600:
                emoji_actions = 0
                await self.bot.pool.execute(
                    "UPDATE emoji_limits SET emoji_actions = 0, last_reset = $1 WHERE guild_id = $2",
                    now, guild_id
                )
            else:
                emoji_actions = record["emoji_actions"]
        else:
            emoji_actions = 0
            await self.bot.pool.execute(
                "INSERT INTO emoji_limits (guild_id, emoji_actions, last_reset) VALUES ($1, $2, $3)",
                guild_id, 0, now
            )

        if emoji_actions >= 50:
            return await ctx.warn("This server has already performed **50 emoji actions** in the past hour")

        target = ctx.message
        if ctx.message.reference:
            try:
                target = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except:
                pass

        emoji_match = re.findall(r"<(a?):(\w+):(\d+)>", target.content)
        if not emoji_match:
            async for msg in ctx.channel.history(limit=20):
                emoji_match = re.findall(r"<(a?):(\w+):(\d+)>", msg.content)
                if emoji_match:
                    target = msg
                    break

        if not emoji_match:
            return await ctx.warn("No custom emoji found in recent messages")

        animated, name, emoji_id = emoji_match[0]
        ext = "gif" if animated else "png"
        emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"

        embed = discord.Embed(title=name, url=emoji_url, color=0x7b9fb0)
        embed.set_image(url=emoji_url)

        class StealEmojiView(discord.ui.View):
            def __init__(self, *, ctx, name, emoji_url, guild_id, pool, locks, embed_message):
                super().__init__()
                self.ctx = ctx
                self.name = name
                self.emoji_url = emoji_url
                self.guild_id = guild_id
                self.pool = pool
                self.locks = locks
                self.message = embed_message
                self.author_id = ctx.author.id

            @discord.ui.button(label="Steal", style=discord.ButtonStyle.gray)
            async def steal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    return await interaction.response.send_message("You can't use this button.", ephemeral=True)

                record = await self.pool.fetchrow(
                    "SELECT emoji_actions, last_reset FROM emoji_limits WHERE guild_id = $1", self.guild_id
                )
                now = datetime.utcnow()

                if record and (now - record["last_reset"]).total_seconds() < 3600:
                    if record["emoji_actions"] >= 50:
                        return await interaction.response.send_message(
                            "This server has reached the **50 emoji actions/hour** limit.", ephemeral=True
                        )

                async with self.locks[self.guild_id]:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(self.emoji_url) as response:
                                image_data = await response.read()
                                await interaction.guild.create_custom_emoji(name=self.name, image=image_data)

                        await self.pool.execute(
                            "UPDATE emoji_limits SET emoji_actions = emoji_actions + 1 WHERE guild_id = $1", self.guild_id
                        )

                        success_embed = discord.Embed(
                            description=f"<:slain_approve:1392318903325036635> [`:{self.name}:`]({self.emoji_url}) has been added to the server",
                            color=0x7b9fb0,
                        )

                        await self.message.edit(embed=success_embed, view=None)
                        await interaction.response.defer()

                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"Failed to add emoji: {e}", ephemeral=True)

        # Send the initial message with the embed + steal button
        sent = await ctx.send(embed=embed)
        view = StealEmojiView(
            ctx=ctx,
            name=name,
            emoji_url=emoji_url,
            guild_id=guild_id,
            pool=self.bot.pool,
            locks=self.locks,
            embed_message=sent
        )
        await sent.edit(view=view)

    async def create_emoji(self, guild: discord.Guild, emoji: str):
        if self.rate_limited.get(guild.id, False):
            print(f"Server {guild.name} is rate-limited, skipping emoji creation.")
            return False
        try:
            emoji_id = emoji.split(":")[2][:-1]
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 429:
                        print(f"Received 429 for {guild.name}. Marking as rate-limited.")
                        self.rate_limited[guild.id] = True
                        self.bot.loop.call_later(3600, lambda: self.rate_limited.pop(guild.id, None))
                        return False
                    elif response.status == 200:
                        image_data = await response.read()
                        await guild.create_custom_emoji(name=f"emoji_{emoji_id}", image=image_data)
                        return True
                    else:
                        return False
        except Exception as e:
            print(f"Failed to create emoji {emoji}: {e}")
            return False

    async def process_valid_emojis(self, emojis):
        valid_emojis = []
        min_distance = 3
        last_pos = -min_distance
        emoji_regex = re.compile(r'(<a?:\w+:\d+>)')
        joined_emojis = ''.join(emojis)
        detected_emojis = emoji_regex.findall(joined_emojis)

        for emoji in detected_emojis:
            emoji_pos = len(' '.join(valid_emojis))
            if emoji_pos - last_pos >= min_distance and (emoji.startswith("<:") or emoji.startswith("<a:")):
                valid_emojis.append(emoji)
                last_pos = emoji_pos
        return valid_emojis

    @emoji.command(name="removeduplicates", aliases=["clearduplicates", "dupes"], usage='emoji removeduplicates')
    @hybrid_permissions(manage_emojis=True)
    async def emoji_removeduplicates(self, ctx: Context):
        """
        Remove emojis that are the same from the server, leaving one copy
        """
        guild_id = ctx.guild.id

        if not ctx.guild.me.guild_permissions.manage_emojis_and_stickers:
            return await ctx.warn("I need the **Manage Emojis and Stickers** permission to remove emojis.")

        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()

        if self.locks[guild_id].locked():
            return await ctx.warn("An **emoji task** is already in progress in this server")

        async with self.locks[guild_id]:
            now = datetime.utcnow()
            record = await self.bot.pool.fetchrow(
                "SELECT emoji_actions, last_reset FROM emoji_limits WHERE guild_id = $1", guild_id
            )

            if record:
                if (now - record["last_reset"]).total_seconds() >= 3600:
                    emoji_actions = 0
                    await self.bot.pool.execute(
                        "UPDATE emoji_limits SET emoji_actions = 0, last_reset = $1 WHERE guild_id = $2",
                        now, guild_id
                    )
                else:
                    emoji_actions = record["emoji_actions"]
            else:
                emoji_actions = 0
                await self.bot.pool.execute(
                    "INSERT INTO emoji_limits (guild_id, emoji_actions, last_reset) VALUES ($1, $2, $3)",
                    guild_id, 0, now
                )

            if emoji_actions >= 50:
                return await ctx.warn("This server has already performed **50 emoji actions** in the past hour")
            seen = {}
            to_remove = []
            async with aiohttp.ClientSession() as session:
                for emoji in ctx.guild.emojis:
                    async with session.get(str(emoji.url)) as resp:
                        if resp.status != 200:
                            continue
                        image_bytes = await resp.read()
                        image_hash = hashlib.sha256(image_bytes).hexdigest()
                        key = (emoji.name, image_hash)
                        if key in seen:
                            to_remove.append(emoji)
                        else:
                            seen[key] = emoji
            if not to_remove:
                return await ctx.warn("No duplicate emojis were found to remove")

            if len(to_remove) > (50 - emoji_actions):
                return await ctx.warn(f"There are only **{50 - emoji_actions}** emoji actions remaining for this hour. Too many duplicates.")
            eta = len(to_remove) * 2
            embed = discord.Embed(
                description=f"<a:slain_load:1392313474310209537> Removing **{len(to_remove)} duplicates**...\n-# *Estimated time: **{eta} seconds***",
                color=0x7b9fb0
            )
            message = await ctx.send(embed=embed)
            success = 0
            fail = 0
            for emoji in to_remove:
                try:
                    await emoji.delete(reason=f"Duplicate emoji removed by {ctx.author}")
                    success += 1
                    await self.bot.pool.execute(
                        "UPDATE emoji_limits SET emoji_actions = emoji_actions + 1 WHERE guild_id = $1",
                        guild_id
                    )
                except Exception as e:
                    print(f"Failed to delete duplicate emoji {emoji}: {e}")
                    fail += 1
                await asyncio.sleep(2)

            result = f"<:slain_approve:1392318903325036635> **{success} duplicate emojis** removed"
            if fail > 0:
                result += f", **{fail}** failed"
            embed.description = result
            await message.edit(embed=embed)




    @emoji.command(name="rename", usage='emoji rename [emoji or name] [new name]')
    @hybrid_permissions(manage_emojis=True)
    async def emoji_rename(self, ctx: Context, emoji_input: str = None, *, new_name: str = None):
        """
        Rename an existing emoji
        """        
        if not emoji_input or not new_name:
            return await ctx.warn("Provide a valid emoji or name")

        if not re.fullmatch(r"^[a-zA-Z0-9_]{2,32}$", new_name):
            return await ctx.warn("New name must be **2–32 characters** using only letters, numbers, or underscores")

        target_emoji: Emoji | None = None
        match = re.search(r"<a?:\w+:(\d+)>", emoji_input)
        if match:
            emoji_id = int(match.group(1))
            target_emoji = ctx.guild.get_emoji(emoji_id)

        if not target_emoji:
            emojis = ctx.guild.emojis
            names = [e.name for e in emojis]
            closest = difflib.get_close_matches(emoji_input.lower(), names, n=1, cutoff=0.3)
            if closest:
                target_emoji = discord.utils.get(emojis, name=closest[0])

        if not target_emoji:
            return await ctx.warn("Couldn't find any emoji matching that input in this server")

        old_name = target_emoji.name
        try:
            await target_emoji.edit(name=new_name, reason=f"Renamed by {ctx.author}")
        except discord.Forbidden:
            return await ctx.warn("I don't have permission to rename that emoji")
        except discord.HTTPException:
            return await ctx.warn("Failed to rename the emoji due to an API error")

        await ctx.approve(f"Emoji `{old_name}` has been renamed to **{new_name}**")


    @emoji.command(name="information", aliases=["info"], usage='emoji information [emoji]')
    async def emoji_info(self, ctx: Context, emoji: str = None):
        """
        View information on a specific emoji
        """ 
        if not emoji:
            return await ctx.warn("Please provide a **custom emoji**")

        match = re.match(r"<a?:\w+:(\d+)>", emoji)
        if not match:
            return await ctx.warn("That doesn't appear to be a valid **custom emoji** format.")

        emoji_id = int(match.group(1))
        guild_emoji = ctx.guild.get_emoji(emoji_id)
        if not guild_emoji:
            return await ctx.warn("That emoji does not belong to **this server**")

        created_at = guild_emoji.created_at.replace(tzinfo=timezone.utc)
        timestamp = int(created_at.timestamp())
        ext = "gif" if guild_emoji.animated else "png"
        emoji_url = f"https://cdn.discordapp.com/emojis/{guild_emoji.id}.{ext}"
        dominant_color = 0xacacac

        if not guild_emoji.animated:
            try:
                response = requests.get(emoji_url)
                image = Image.open(BytesIO(response.content)).convert("RGB")
                pixels = list(image.getdata())
                most_common = Counter(pixels).most_common(1)[0][0]
                dominant_color = discord.Color.from_rgb(*most_common)
            except Exception:
                pass

        added_by = "Unknown"
        if ctx.guild.me.guild_permissions.view_audit_log:
            async for entry in ctx.guild.audit_logs(limit=50, action=discord.AuditLogAction.emoji_create):
                if entry.target.id == guild_emoji.id:
                    added_by = f"{entry.user.mention}"
                    break

        embed = discord.Embed(
            title=f":{guild_emoji.name}:",
            url=emoji_url,
            color=dominant_color,
            description=(
                f"**ID:** `{guild_emoji.id}`\n"
                f"**Created:** <t:{timestamp}:F> (<t:{timestamp}:R>)\n"
                f"**Added By:** {added_by}"
            )
        )
        embed.set_thumbnail(url=emoji_url)
        await ctx.send(embed=embed)

    @commands.command(name="emojis", usage='emojis')
    async def list_emojis(self, ctx: Context):
        """
        View a list of emojis added to this server
        """      
        if not ctx.guild.emojis:
            return await ctx.warn("This server has no custom emojis.")
        formatted = []
        for idx, emoji in enumerate(ctx.guild.emojis, start=1):
            created_at = emoji.created_at.replace(tzinfo=timezone.utc)
            timestamp = int(created_at.timestamp())
            ext = "gif" if emoji.animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{emoji.id}.{ext}"
            display_name = emoji.name
            if len(display_name) > 9:
                display_name = display_name[:9] + "..."
            formatted.append(
                f"`{idx}.` {str(emoji)} - [{display_name}]({url}) (<t:{timestamp}:R>)"
            )
        embed = discord.Embed(
            title=f"Emojis in {ctx.guild.name}",
            color=0x2b2d31,
        )
        paginator = Paginator(ctx, pages=formatted, embed=embed, per_page=10, counter=False)
        await paginator.start()


    def cog_unload(self):
        self.sync_emoji_usage.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        custom_emojis = re.findall(r"<a?:\w+:(\d+)>", message.content)
        if not custom_emojis:
            return

        guild_id = message.guild.id
        for emoji_id in custom_emojis:
            emoji_id = int(emoji_id)
            await self.bot.redis.hincrby(f"emoji_usage:{guild_id}", emoji_id, 1)

        await self.bot.redis.sadd("emoji_dirty_guilds", guild_id)

    @tasks.loop(minutes=5)
    async def sync_emoji_usage(self):
        guild_ids = await self.bot.redis.smembers("emoji_dirty_guilds")
        for raw_id in guild_ids:
            guild_id = int(raw_id.decode())
            key = f"emoji_usage:{guild_id}"
            usage_data = await self.bot.redis.hgetall(key)
            if not usage_data:
                continue

            for emoji_id, count in usage_data.items():
                await self.bot.pool.execute(
                    """
                    INSERT INTO emoji_usage (guild_id, emoji_id, usage_count)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, emoji_id)
                    DO UPDATE SET usage_count = emoji_usage.usage_count + $3
                    """,
                    guild_id,
                    int(emoji_id),
                    int(count),
                )

            # Clear Redis after sync
            await self.bot.redis.delete(key)
            await self.bot.redis.srem("emoji_dirty_guilds", guild_id)

    @emoji.command(name="stats", usage='emoji stats')
    @hybrid_permissions(manage_emojis=True)
    async def emoji_stats(self, ctx: Context):
        """
        View emoji usage statistics
        """      
        rows = await self.bot.pool.fetch(
            """
            SELECT emoji_id, usage_count
            FROM emoji_usage
            WHERE guild_id = $1
            ORDER BY usage_count DESC
            """,
            ctx.guild.id,
        )

        if not rows:
            return await ctx.warn("No emoji usage data available for this server")

        lines = []
        for i, row in enumerate(rows, start=1):
            emoji = ctx.guild.get_emoji(row["emoji_id"])
            if emoji:
                usage = compact_number(row["usage_count"])
                lines.append(f"{emoji} — **{usage}** uses")

        embed = discord.Embed(
            title="Emoji Usage",
            color=0x2b2d31,
        )
        paginator = Paginator(ctx, lines, embed=embed, per_page=10)
        await paginator.start()


    async def create_emoji(self, guild: discord.Guild, emoji: str):
        if self.rate_limited.get(guild.id, False):
            print(f"Server {guild.name} is rate-limited, skipping emoji creation.")  
            return False
        try:
            emoji_id = emoji.split(":")[2][:-1]
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 429:
                        print(f"Received 429 for {guild.name}. Marking as rate-limited.")
                        self.rate_limited[guild.id] = True
                        return False  # No retry
                    elif response.status == 200:
                        image_data = await response.read()
                        await guild.create_custom_emoji(name=f"emoji_{emoji_id}", image=image_data)
                        return True
                    else:
                        return False
        except Exception as e:
            print(f"Failed to create emoji {emoji}: {e}")
            return False

    async def process_valid_emojis(self, emojis):
        valid_emojis = []
        min_distance = 3
        last_pos = -min_distance
        emoji_regex = re.compile(r'(<a?:\w+:\d+>)')
        joined_emojis = ''.join(emojis)
        detected_emojis = emoji_regex.findall(joined_emojis)

        for emoji in detected_emojis:
            emoji_pos = len(' '.join(valid_emojis))
            if emoji_pos - last_pos >= min_distance and (emoji.startswith("<:") or emoji.startswith("<a:")):
                valid_emojis.append(emoji)
                last_pos = emoji_pos
        return valid_emojis


class Stickers(Cog):
    def __init__(self, bot):
        self.bot = bot

    @group(name="sticker", usage='sticker',invoke_without_command=True)
    async def sticker_group(self, ctx: Context):
        """
        Manage stickers for the server
        """      
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)
            
    @sticker_group.command(name="add", usage='sticker add [attached sticker] OR [message link or id] OR [reply] [name]')
    @cooldown(4, 10, BucketType.guild)
    @hybrid_permissions(manage_expressions=True)
    async def sticker_add(self, ctx: Context, image_or_message: str = None, name: str = None):
        """
        Add a sticker to the server
        """      
        url = None
        def get_sticker_url(sticker):
            return str(sticker.url)
        replied_message = None
        if ctx.message.reference:
            try:
                replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except:
                pass
        if (ctx.message.attachments or replied_message) and not name:
            name = image_or_message

        if image_or_message and image_or_message.startswith("http") and "discord.com/channels" not in image_or_message:
            url = image_or_message
        elif image_or_message and "discord.com/channels" in image_or_message:
            try:
                parts = image_or_message.strip().split("/")
                channel_id, message_id = int(parts[-2]), int(parts[-1])
                channel = ctx.guild.get_channel(channel_id)
                if not channel:
                    return await ctx.warn("Invalid channel")
                msg = await channel.fetch_message(message_id)
                if msg.stickers:
                    url = get_sticker_url(msg.stickers[0])
                elif msg.attachments:
                    url = msg.attachments[0].url
                else:
                    return await ctx.warn("Message has no **image** or **sticker**.")
            except:
                return await ctx.warn("Failed to fetch message from link.")
        elif image_or_message and image_or_message.isdigit():
            try:
                msg = await ctx.channel.fetch_message(int(image_or_message))
                if msg.stickers:
                    url = get_sticker_url(msg.stickers[0])
                elif msg.attachments:
                    url = msg.attachments[0].url
                else:
                    return await ctx.warn("Message has no **image** or **sticker**.")
            except discord.NotFound:
                try:
                    sticker_obj = await self.bot.fetch_sticker(int(image_or_message))
                    url = get_sticker_url(sticker_obj)
                except:
                    return await ctx.warn("Invalid message or sticker ID")
            except:
                return await ctx.warn("Could not resolve message or sticker")
        if not url and replied_message:
            try:
                if replied_message.stickers:
                    url = get_sticker_url(replied_message.stickers[0])
                elif replied_message.attachments:
                    url = replied_message.attachments[0].url
                else:
                    return await ctx.warn("Replied message has no **image** or **sticker**")
            except:
                return await ctx.warn("Could not resolve replied message")
        if not url and ctx.message.attachments:
            url = ctx.message.attachments[0].url
        if not url:
            return await ctx.warn("Usage: `sticker add [image, sticker, message ID/link] [name]`")
        if not name or not (2 <= len(name) <= 30) or not name.islower() or " " in name:
            return await ctx.warn("Sticker name must be **2–30 lowercase characters** with **no spaces**")
        try:
            async with self.bot.session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.warn("Failed to convert into a sticker")
                data = await resp.read()
        except:
            return await ctx.warn("Failed to convert into a sticker")

        if len(data) > 512 * 1024:
            return await ctx.warn("Sticker must be under **512KB** in size")
        
        limit = {
            0: 5,
            1: 15,
            2: 30,
            3: 60
        }.get(ctx.guild.premium_tier, 5)

        if len(await ctx.guild.fetch_stickers()) >= limit:
            return await ctx.warn(f"This server has reached the **maximum of {limit} stickers**")

        try:
            sticker = await ctx.guild.create_sticker(
                name=name,
                description=f"Uploaded by {ctx.author}",
                emoji="✨",
                file=File(io.BytesIO(data), filename=f"sticker.{url.split('.')[-1]}"),
                reason=f"Sticker added by {ctx.author} ({ctx.author.id})"
            )
        except discord.HTTPException as e:
            if e.code == 50046:
                return await ctx.warn("Image must be **PNG/APNG/JSON** and under **512KB**")
            return await ctx.warn(f"Failed to create sticker: `{e}`")
        except Exception as e:
            return await ctx.warn(f"Unexpected error: `{e}`")

        ext = url.split('.')[-1]
        cdn_url = f"https://cdn.discordapp.com/stickers/{sticker.id}.{ext}"
        await ctx.approve(f"Created a sticker: [`{sticker.name}`]({cdn_url})")


    @sticker_group.command(name="rename", usage='sticker rename [name] or [reply] [new name]')
    @hybrid_permissions(manage_expressions=True)
    async def sticker_rename(self, ctx: Context, new_name: str = None):
        """
        Rename a sticker added to the server
        """      
        if not new_name or not (2 <= len(new_name) <= 30) or not new_name.islower() or " " in new_name:
            return await ctx.warn("New name must be **2–30 lowercase characters** with **no spaces**")

        sticker_item = None
        if ctx.message.reference:
            try:
                replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if replied.stickers:
                    sticker_item = replied.stickers[0]
            except Exception:
                pass

        if not sticker_item and ctx.message.stickers:
            sticker_item = ctx.message.stickers[0]

        if not sticker_item:
            return await ctx.warn("Please reply to or attach a sticker from this server to rename.")

        sticker = discord.utils.get(ctx.guild.stickers, id=sticker_item.id)
        if not sticker:
            return await ctx.warn("That sticker isn't from this server or is a built-in sticker and can't be renamed.")

        try:
            await sticker.edit(name=new_name, reason=f"Renamed by {ctx.author} ({ctx.author.id})")
            sticker = await ctx.guild.fetch_sticker(sticker.id)
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to rename sticker: `{e}`")
        except Exception as e:
            return await ctx.warn(f"Unexpected error: `{e}`")

        ext = (
            "json" if sticker.format == discord.StickerFormatType.lottie else
            "png" if sticker.format == discord.StickerFormatType.png else
            "gif"
        )
        cdn_url = f"https://cdn.discordapp.com/stickers/{sticker.id}.{ext}"
        return await ctx.approve(f"Sticker name has been changed to: [`{sticker.name}`]({cdn_url})")

    @sticker_group.command(name="remove", aliases=["delete"], usage='sticker remove [name or id]')
    @hybrid_permissions(manage_expressions=True)
    async def sticker_delete(self, ctx: Context, *, identifier: str = None):
        """
        Remove a sticker added to the server
        """      
        if not identifier:
            return await ctx.warn("Provide a **sticker ID** or **name** to delete.")

        sticker = None
        if identifier.isdigit():
            sticker = discord.utils.get(ctx.guild.stickers, id=int(identifier))

        if not sticker:
            matching = [s for s in ctx.guild.stickers if s.name.lower() == identifier.lower()]
            if not matching:
                return await ctx.warn("No sticker found with that **name or ID**.")
            elif len(matching) > 1:
                return await ctx.warn(f"Multiple stickers found with the name `{identifier}`. Use the ID instead.")
            sticker = matching[0]

        try:
            await sticker.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
            return await ctx.approve(f"Deleted sticker: `{sticker.name}` (`{sticker.id}`)")
        except discord.Forbidden:
            return await ctx.warn("I don't have permission to delete that sticker.")
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to delete sticker: `{e}`")



class Timezone(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @group(name="timezone", aliases=['tz'], usage='timezone [Optional: user]', invoke_without_command=True)
    @cooldown(3, 10, BucketType.user)
    async def timezone_group(self, ctx: Context, user: commands.MemberConverter = None):
        """
        View the current timezone of a user
        """      
        user = user or ctx.author
        record = await self.bot.pool.fetchrow("SELECT timezone FROM user_timezones WHERE user_id = $1", user.id)
        if not record:
            return await ctx.warn("That user has not set a timezone")
        try:
            now = datetime.now(pytz.timezone(record["timezone"]))
        except pytz.UnknownTimeZoneError:
            return await ctx.warn("Invalid timezone saved for user.")

        hour_min = now.strftime('%I:%M').lstrip('0')
        weekday = now.strftime('%A')
        suffix = "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
        if now.hour >= 21 or now.hour < 5:
            suffix = "night"

        return await ctx.clock(f"{user.display_name}'s time is **{hour_min}** **{weekday.lower()}** **{suffix}**")

    @timezone_group.command(name="set", usage='timezone set [location]')
    @cooldown(1, 10, BucketType.user)
    async def timezone_set(self, ctx: Context, *, timezone_input: str = None):
        """
        Set a timezone for yourself so others can know your time
        """    
        if not timezone_input:
            return await ctx.warn("Please provide a timezone\n-# ***America/New_York** or a city like **new york***")

        timezone = timezone_input
        if timezone not in pytz.all_timezones:
            resolved = await self.resolve_timezone(timezone_input)
            if not resolved or resolved not in pytz.all_timezones:
                return await ctx.warn("Please provide a valid timezone\n-# ***America/New_York** or a city like **new york***")
            timezone = resolved
        await self.bot.pool.execute(
            "INSERT INTO user_timezones (user_id, timezone) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone",
            ctx.author.id, timezone
        )

        return await ctx.approve(f"Your timezone has been set to: `{timezone}`")

    async def resolve_timezone(self, location_name: str) -> str | None:
        geolocator = Nominatim(user_agent="SlainTimezoneResolver", timeout=5)
        try:
            location = geolocator.geocode(location_name)
            if not location:
                return None

            tf = TimezoneFinder()
            return tf.timezone_at(lng=location.longitude, lat=location.latitude)
        except Exception:
            return None

    @timezone_group.command(name="list", aliases=["all"], usage='timezone list')
    @cooldown(5, 10, BucketType.guild)
    async def timezone_list(self, ctx: Context):
        """
        View all users timezones that has one set in the current server
        """    
        records = await self.bot.pool.fetch("SELECT user_id, timezone FROM user_timezones")
        if not records:
            return await ctx.warn("No users have set a timezone.")

        now_utc = datetime.utcnow()
        lines = []

        for record in records:
            try:
                user = ctx.guild.get_member(record["user_id"]) or await self.bot.fetch_user(record["user_id"])
                tz = pytz.timezone(record["timezone"])
                current_time = now_utc.astimezone(tz).strftime('%I:%M %p')
                lines.append(f"{user} - **{record['timezone']}** → `{current_time}`")
            except Exception:
                lines.append(f"<@{record['user_id']}> → Invalid timezone")

        embed = discord.Embed(color=0xacacac)
        await Paginator(ctx, lines, embed=embed).start()

    @timezone_group.command(name="remove", usage='timezone remove')
    async def timezone_remove(self, ctx: Context):
        """
        Remove your currently set timezone
        """    
        result = await self.bot.pool.execute(
            "DELETE FROM user_timezones WHERE user_id = $1",
            ctx.author.id,
        )
        if result == "DELETE 0":
            return await ctx.warn("You don’t have a timezone set")
        return await ctx.approve("Your timezone has been removed")


class Prefix(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @group(invoke_without_command=True, usage='prefix')
    async def prefix(self, ctx: Context):
        """View the current prefix for the guild"""
        query = "SELECT prefix FROM config WHERE guild_id = $1"
        prefix = await self.bot.pool.fetchval(query, ctx.guild.id) or "!"  
        return await ctx.config(f"The prefix for this server is `{prefix}`")

    @prefix.command(name="set", aliases=("change", "update"), usage='prefix set [prefix]')
    @hybrid_permissions(manage_guild=True)
    async def prefix_set(self, ctx: Context, prefix: str):
        """Set a new prefix for the guild"""
        prefix_ = prefix.strip()
        if len(prefix_) > 3:
            return await ctx.warn("The prefix cannot exceed 3 characters")

        query = """
        INSERT INTO config (guild_id, prefix)
        VALUES($1, $2) ON CONFLICT(guild_id)
        DO UPDATE SET prefix = excluded.prefix
        """
        await self.bot.pool.execute(query, ctx.guild.id, prefix_)
        return await ctx.approve(f"Now using `{prefix_}` as the server prefix")

    @prefix.command(name="remove", aliases=("reset", "clear"), usage='prefix remove')
    @hybrid_permissions(manage_guild=True)
    async def prefix_remove(self, ctx: Context):
        """Remove the custom prefix and use the default prefix"""
        query = "SELECT prefix FROM config WHERE guild_id = $1"
        prefix = await self.bot.pool.fetchval(query, ctx.guild.id)
        if not prefix:
            return await ctx.warn("There isn't a custom prefix set")

        query = "UPDATE config SET prefix = NULL WHERE guild_id = $1"
        await self.bot.pool.execute(query, ctx.guild.id)
        return await ctx.approve("The server prefix has been reset")

    @prefix.group(name="self", aliases=("me",), invoke_without_command=True, usage='prefix self [prefix]')
    async def prefix_self(self, ctx: Context, prefix: str):
        """Set a custom prefix for yourself"""
        prefix_ = prefix.strip()
        if len(prefix_) > 3:
            return await ctx.warn("The prefix cannot exceed 3 characters")

        query = """
        INSERT INTO user_config (user_id, prefix)
        VALUES($1, $2) ON CONFLICT(user_id)
        DO UPDATE SET prefix = excluded.prefix
        """
        await self.bot.pool.execute(query, ctx.author.id, prefix_)
        return await ctx.approve(f"Your prefix has been set to `{prefix_}`")

    @prefix_self.command(name="remove", aliases=("reset", "clear"), usage='prefix self remove')
    async def prefix_self_remove(self, ctx: Context):
        """Remove your custom prefix and use the server prefix"""
        query = "UPDATE user_config SET prefix = NULL WHERE user_id = $1"
        await self.bot.pool.execute(query, ctx.author.id)
        return await ctx.approve("Your prefix has been reset")


    @Cog.listener()
    async def on_guild_join(self, guild):
        """Set a default prefix when the bot joins a new guild."""
        query = "SELECT prefix FROM config WHERE guild_id = $1"
        prefix = await self.bot.pool.fetchval(query, guild.id)

        if not prefix:
            query = "INSERT INTO config (guild_id, prefix) VALUES($1, $2)"
            await self.bot.pool.execute(query, guild.id, "!")
            print(f"[AUTO-PREFIX] Set default prefix '!' for {guild.name} ({guild.id}) - {guild.member_count} members")

    @Cog.listener()
    async def on_ready(self):
        """Ensure all servers have a default prefix set when the bot starts up."""
        
        await self.bot.pool.execute("""
            CREATE TABLE IF NOT EXISTS config (
                guild_id BIGINT PRIMARY KEY,
                prefix TEXT
            );
        """)
        
        await self.bot.pool.execute("""
            CREATE TABLE IF NOT EXISTS user_config (
                user_id BIGINT PRIMARY KEY,
                prefix TEXT
            );
        """)

        missing_prefixes = 0
        for guild in self.bot.guilds:
            query = "SELECT prefix FROM config WHERE guild_id = $1"
            prefix = await self.bot.pool.fetchval(query, guild.id)
            
            if not prefix:
                query = "INSERT INTO config (guild_id, prefix) VALUES($1, $2)"
                await self.bot.pool.execute(query, guild.id, "!")
                missing_prefixes += 1
        
        if missing_prefixes > 0:
            print(f"[AUTO-PREFIX] Set default prefix '!' for {missing_prefixes} guilds on startup")

                
async def setup(bot: Bot) -> None:
    await bot.add_cog(Information(bot))
    await bot.add_cog(Emojis(bot))
    await bot.add_cog(Prefix(bot))
    await bot.add_cog(Stickers(bot))
    await bot.add_cog(Timezone(bot))
