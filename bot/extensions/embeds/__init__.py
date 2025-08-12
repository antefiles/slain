from discord.ext.commands import Cog, command, Context, GroupCog, group, has_permissions
from discord import Message, Embed, ButtonStyle, ui, Interaction, NotFound, PartialEmoji
from bot.core import Bot
import aiohttp, discord
from io import BytesIO
from cashews import cache
from datetime import datetime, timezone, timedelta
from babel.dates import format_date
from discord.utils import format_dt
import humanize, asyncio, asyncpg
import re , shlex
from discord.ext.commands import has_permissions, CheckFailure, cooldown, CooldownMapping, BucketType, CommandOnCooldown
from ...shared.paginator import Paginator
from bot.shared.fakeperms import hybrid_permissions
import uuid
import json


def get_vars_map(ctx: Context) -> dict:
    guild = ctx.guild
    member = ctx.author
    channel = ctx.channel

    pst = timezone(timedelta(hours=-8))
    now_utc = datetime.now(timezone.utc)
    now_pst = now_utc.astimezone(pst)

    try:
        sorted_members = sorted(guild.members, key=lambda m: m.joined_at or datetime.utcnow())
        join_position = sorted_members.index(member) + 1
        join_position_suffix = f"{join_position}th"
    except ValueError:
        join_position = "N/A"
        join_position_suffix = "N/A"

    return {
        # Guild vars
        "guild.name": guild.name,
        "guild.id": guild.id,
        "guild.member_count": guild.member_count,
        "guild.region": getattr(guild, "region", "N/A"),
        "guild.shard": guild.shard_id,
        "guild.owner_id": guild.owner_id,
        "guild.created_at": format_date(guild.created_at, format="long", locale="en"),
        "guild.created_at_timestamp": f"<t:{int(guild.created_at.timestamp())}:R>",
        "guild.created_at_humanized": humanize.naturaltime(datetime.now(timezone.utc) - guild.created_at),
        "guild.emoji_count": len(guild.emojis),
        "guild.role_count": len(guild.roles),
        "guild.boost_count": guild.premium_subscription_count,
        "guild.boost_tier": getattr(guild, "premium_tier", "No Level"),
        "guild.preferred_locale": guild.preferred_locale,
        "guild.key_features": guild.features,
        "guild.icon": guild.icon.url if guild.icon else "N/A",
        "guild.banner": guild.banner.url if guild.banner else "N/A",
        "guild.splash": guild.splash.url if guild.splash else "N/A",
        "guild.discovery": guild.discovery_splash.url if guild.discovery_splash else "N/A",
        "guild.max_presences": guild.max_presences,
        "guild.max_members": guild.max_members,
        "guild.max_video_channel_users": guild.max_video_channel_users,
        "guild.afk_timeout": guild.afk_timeout,
        "guild.afk_channel": guild.afk_channel.name if guild.afk_channel else "N/A",
        "guild.channels_count": len(guild.channels),
        "guild.text_channels_count": len(guild.text_channels),
        "guild.voice_channels_count": len(guild.voice_channels),
        "guild.category_channels_count": len(guild.categories),

        # User vars
        "user": str(member),
        "user.id": member.id,
        "user.mention": member.mention,
        "user.name": member.name,
        "user.tag": f"{member.discriminator:0>4}",
        "user.avatar": member.avatar.url if member.avatar else "N/A",
        "user.guild_avatar": member.guild_avatar.url if member.guild_avatar else "N/A",
        "user.display_avatar": member.display_avatar.url,
        "user.joined_at": format_date(member.joined_at, format="long", locale="en") if member.joined_at else "N/A",
        "user.joined_at_timestamp": f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "N/A",
        "user.created_at": format_date(member.created_at, format="long", locale="en"),
        "user.created_at_timestamp": f"<t:{int(member.created_at.timestamp())}:R>",
        "user.display_name": member.display_name,
        "user.boost": "Yes" if member.premium_since else "No",
        "user.boost_since": format_date(member.premium_since, format="long", locale="en") if member.premium_since else "N/A",
        "user.boost_since_timestamp": f"<t:{int(member.premium_since.timestamp())}:R>" if member.premium_since else "N/A",
        "user.color": str(member.top_role.color) if member.top_role else "N/A",
        "user.top_role": member.top_role.name if member.top_role else "N/A",
        "user.role_list": ", ".join(role.name for role in member.roles if role.name != "@everyone"),
        "user.role_text_list": ", ".join([r.name for r in member.roles if r.name != "@everyone"]),
        "user.bot": "Yes" if member.bot else "No",
        "user.badges_icons": "N/A",
        "user.badges": "N/A",
        "user.join_position": join_position,
        "user.join_position_suffix": join_position_suffix,

        # Channel vars
        "channel.name": channel.name,
        "channel.id": channel.id,
        "channel.mention": channel.mention,
        "channel.topic": getattr(channel, "topic", "N/A"),
        "channel.type": str(channel.type),
        "channel.category_id": channel.category_id if channel.category_id else "N/A",
        "channel.category_name": channel.category.name if channel.category else "N/A",
        "channel.position": channel.position,
        "channel.slowmode_delay": getattr(channel, "slowmode_delay", 0),

        # Date and time vars
        "date.now": now_pst.strftime("%B %d, %Y"),
        "date.utc_timestamp": int(now_utc.timestamp()),
        "date.now_proper": now_pst.strftime("%A, %B %d, %Y"),
        "date.now_short": now_pst.strftime("%b %d, %Y"),
        "date.now_shorter": now_pst.strftime("%m/%d/%y"),
        "time.now": now_pst.strftime("%I:%M %p"),
        "time.now_military": now_pst.strftime("%H:%M"),
        "date.utc_now": now_utc.strftime("%B %d, %Y"),
        "date.utc_now_proper": now_utc.strftime("%A, %B %d, %Y"),
        "date.utc_now_short": now_utc.strftime("%b %d, %Y"),
        "date.utc_now_shorter": now_utc.strftime("%m/%d/%y"),
        "time.utc_now": now_utc.strftime("%I:%M %p"),
        "time.utc_now_military": now_utc.strftime("%H:%M"),
    }

def replace_vars(text: str, ctx: Context, extra: dict = None) -> str:
    vars_map = get_vars_map(ctx)
    if extra:
        vars_map.update(extra)

    for k, v in vars_map.items():
        text = text.replace(f"{{{k}}}", str(v))

    mention_pattern = re.compile(r"<@([a-zA-Z0-9_]+)>")

    def resolve_user(match):
        name = match.group(1)
        user = discord.utils.find(lambda m: m.name == name, ctx.guild.members)
        return user.mention if user else match.group(0)

    return mention_pattern.sub(resolve_user, text)

async def build_embed_from_raw(bot: Bot, ctx: Context, raw: str, extra: dict = None) -> tuple[str, discord.Embed]:
    parts = raw.split("$v")
    data = {}
    message_content = ""

    for part in parts:
        match = re.match(r"\{([^:]+):(.+?)\}$", part.strip(), re.DOTALL)
        if match:
            key = match.group(1).strip().lower()
            value = match.group(2).strip()
            if key == "message":
                message_content = replace_vars(value, ctx, extra=extra)
            else:
                data[key] = value

    embed = discord.Embed()

    if "title" in data:
        embed.title = replace_vars(data["title"], ctx, extra=extra)
    if "description" in data:
        embed.description = replace_vars(data["description"], ctx, extra=extra)
    if "color" in data:
        try:
            embed.color = discord.Color(int(data["color"].lstrip("#"), 16))
        except ValueError:
            embed.color = discord.Color.default()
    if "footer" in data:
        if ";" in data["footer"]:
            footer_parts = dict(item.strip().split("=") for item in data["footer"].split(";") if "=" in item)
            embed.set_footer(
                text=replace_vars(footer_parts.get("text", ""), ctx, extra=extra),
                icon_url=footer_parts.get("icon")
            )
        else:
            embed.set_footer(text=replace_vars(data["footer"], ctx, extra=extra))
    if "author" in data:
        if ";" in data["author"]:
            author_parts = dict(item.strip().split("=") for item in data["author"].split(";") if "=" in item)
            embed.set_author(
                name=replace_vars(author_parts.get("name", ""), ctx, extra=extra),
                icon_url=author_parts.get("icon")
            )
        else:
            embed.set_author(name=replace_vars(data["author"], ctx, extra=extra))
    if "thumbnail" in data:
        embed.set_thumbnail(url=data["thumbnail"])
    if "image" in data:
        embed.set_image(url=data["image"])
    if "timestamp" in data and data["timestamp"].lower() == "now":
        embed.timestamp = discord.utils.utcnow()

    return message_content, embed


class Embeds(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @group(name="embed", usage='embed', invoke_without_command=False)
    async def embed_group(self, ctx: Context):
        """
        Create custom embeds
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @embed_group.command(name="create", usage='embed create {embed}$v{title: etc}$v{description: etc}')
    @hybrid_permissions(manage_messages=True)
    @cooldown(1, 10, BucketType.user)
    async def embed_create(self, ctx: Context, *, raw: str):
        """
        Create a custom embed for your server
        """
        permissions = ctx.channel.permissions_for(ctx.guild.me)

        if not permissions.send_messages:
            return await ctx.warn("I don't have permission to send messages in this channel")
        if not permissions.embed_links:
            return await ctx.warn("I don't have permission to send embeds in this channel")

        # Remove channel mention if it exists
        raw = re.sub(r"<#\d+>", "", raw).strip()

        if "{embed}" not in raw:
            final = replace_vars(raw, ctx).replace("\\n", "\n")
            return await ctx.send(final)

        parts = raw.split("$v")
        data = {}
        message_content = ""

        for part in parts:
            stripped = part.strip()
            if not stripped or stripped.lower() == "{embed}":
                continue

            # message: block handling (with or without curly braces)
            if stripped.startswith("{message:") and stripped.endswith("}"):
                message_content = replace_vars(stripped[9:-1].strip(), ctx).replace("\\n", "\n")
                continue
            if stripped.lower().startswith("message:"):
                message_content = replace_vars(stripped[8:].strip(), ctx).replace("\\n", "\n")
                continue

            if not stripped.startswith("{") or not stripped.endswith("}"):
                return await ctx.warn(f"Missing opening or closing bracket: `{stripped}`")

            content = stripped[1:-1].strip()
            if ":" not in content:
                return await ctx.warn(f"Missing colon (`:`) in block: `{stripped}`")

            key, value = content.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key.startswith("field"):
                count = sum(1 for k in data if k.startswith("field"))
                data[f"field{count + 1}"] = value
            else:
                if key in data:
                    return await ctx.warn(f"Duplicate key `{key}` detected.")
                data[key] = value

        try:
            embed = Embed()
            allowed_keys = {
                "title", "description", "color", "footer", "author",
                "thumbnail", "image", "timestamp"
            }

            for k in data:
                if not k.startswith("field") and k not in allowed_keys:
                    return await ctx.warn(f"Unknown embed key: `{k}`")

            if "title" in data:
                embed.title = replace_vars(data["title"], ctx)
            if "description" in data:
                embed.description = replace_vars(data["description"], ctx)
            if "color" in data:
                try:
                    embed.color = discord.Color(int(data["color"].lstrip("#"), 16))
                except ValueError:
                    return await ctx.warn(f"Invalid hex color: `{data['color']}`")
            if "footer" in data:
                if ";" in data["footer"]:
                    try:
                        footer_parts = dict(item.strip().split("=") for item in data["footer"].split(";") if "=" in item)
                        embed.set_footer(text=replace_vars(footer_parts.get("text", ""), ctx), icon_url=footer_parts.get("icon"))
                    except Exception:
                        return await ctx.warn("Invalid footer format. Use `text=...; icon=...`")
                else:
                    embed.set_footer(text=replace_vars(data["footer"], ctx))
            if "author" in data:
                if ";" in data["author"]:
                    try:
                        author_parts = dict(item.strip().split("=") for item in data["author"].split(";") if "=" in item)
                        embed.set_author(name=replace_vars(author_parts.get("name", ""), ctx), icon_url=author_parts.get("icon"))
                    except Exception:
                        return await ctx.warn("Invalid author format. Use `name=...; icon=...`")
                else:
                    embed.set_author(name=replace_vars(data["author"], ctx))
            if "thumbnail" in data:
                embed.set_thumbnail(url=data["thumbnail"])
            if "image" in data:
                embed.set_image(url=data["image"])
            if "timestamp" in data and data["timestamp"].lower() == "now":
                embed.timestamp = discord.utils.utcnow()

            for key in sorted(k for k in data if k.startswith("field")):
                content = data[key]
                try:
                    parts = dict(item.strip().split("=") for item in content.split(";") if "=" in item)
                    name = parts.get("name", "​")
                    value = parts.get("value", "​")
                    inline = parts.get("inline", "true").lower() == "true"
                    embed.add_field(name=replace_vars(name, ctx), value=replace_vars(value, ctx), inline=inline)
                except Exception:
                    await ctx.warn(f"Failed to parse field: `{key}`. Use format `name=...; value=...; inline=true`")
                    continue

            await ctx.send(content=message_content or None, embed=embed)

        except Exception as e:
            await ctx.warn(f"Embed error: {e}")


class Persistent(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_button_rows = []

    @group(name="button", aliases=["buttons"], usage='button', invoke_without_command=True)
    @hybrid_permissions(manage_messages=True)
    async def button_group(self, ctx: Context):
        """
        Create custom persistent buttons for slains embeded messages
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @button_group.command(name="add", usage='button add [message id or link] [name] [--message (content)]')
    @hybrid_permissions(manage_messages=True)
    async def button_add(self, ctx: Context, message_ref: str, *, raw: str):
        """
        Add a button to one of slains messages
        """
        msg_id = None
        channel_id = None
        link_match = re.match(
            r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/\d+/(\d+)/(\d+)", message_ref
        )

        if link_match:
            channel_id, msg_id = map(int, link_match.groups())
        elif message_ref.isdigit():
            msg_id = int(message_ref)
        else:
            return await ctx.warn("Message link or ID is invalid.")

        message_count = await self.bot.pool.fetchval(
            "SELECT COUNT(DISTINCT message_id) FROM persistent_buttons WHERE guild_id = $1",
            ctx.guild.id,
        )

        if message_count >= 5:
            existing = await self.bot.pool.fetchval(
                "SELECT 1 FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
                ctx.guild.id, msg_id
            )
            if not existing:
                return await ctx.warn("You can only have persistent buttons on **5 messages per server**.")

        target: Message = None
        if channel_id:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                try:
                    target = await channel.fetch_message(msg_id)
                except:
                    pass
        else:
            for channel in ctx.guild.text_channels:
                try:
                    target = await channel.fetch_message(int(msg_id))
                    if target:
                        break
                except:
                    continue

        if not target:
            return await ctx.warn("Could not find the target message.")

        sections = [s.strip() for s in raw.split("&&")]
        sections = [s.replace("—", "--").replace("–", "-") for s in sections]

        existing_count = await self.bot.pool.fetchval(
            "SELECT COUNT(*) FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, target.id
        )
        if existing_count + len(sections) > 5:
            return await ctx.warn("You can only have up to **5 buttons per message**.")
        if len(sections) > 5:
            return await ctx.warn("You can only add up to **5 buttons** per message")

        existing_labels = await self.bot.pool.fetch(
            "SELECT label FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, target.id
        )
        existing_labels = {r["label"].strip().lower() for r in existing_labels}

        for section in sections:
            match = re.search(r"--message\s+(.*?)(?:\s+--color\s+(\w+))?$", section, re.DOTALL)
            if not match:
                return await ctx.warn("Each button must include `--message [text]` and optional `--color [color]`.")

            before = section[:match.start()].strip()
            message_text = match.group(1).strip()
            color_value = (match.group(2) or "gray").lower()

            style_map = {
                "gray": ButtonStyle.secondary,
                "blurple": ButtonStyle.primary,
                "green": ButtonStyle.success,
                "red": ButtonStyle.danger,
            }
            style = style_map.get(color_value)
            if style is None:
                return await ctx.warn(f"Invalid color `{color_value}`. Use: gray, blurple, green, red.")

            emoji_pattern = re.compile(r"<a?:\w+:\d+>|[\u2600-\u27BF\uE000-\uF8FF\uD83C-\uDBFF\uDC00-\uDFFF]+")
            emoji_match = emoji_pattern.search(before)

            emoji = None
            if emoji_match:
                emoji_raw = emoji_match.group()
                if emoji_raw.startswith("<"):
                    m = re.match(r"<a?:([a-zA-Z0-9_]+):(\d+)>", emoji_raw)
                    if m:
                        name, emoji_id = m.groups()
                        emoji = PartialEmoji(name=name, id=int(emoji_id), animated=emoji_raw.startswith("<a:"))
                else:
                    emoji = emoji_raw
                label = (before[:emoji_match.start()] + before[emoji_match.end():]).strip() or "\u200b"
            else:
                label = before

            if label.strip().lower() in existing_labels:
                return await ctx.warn(f"A button with the label `{label}` already exists on [`this message`]({target.jump_url})")

            custom_id = str(uuid.uuid4())[:8]
            await self.bot.pool.execute(
                """
                INSERT INTO persistent_buttons (
                    guild_id, channel_id, message_id, custom_id,
                    label, style, emoji, response, embed_raw
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                ctx.guild.id,
                target.channel.id,
                target.id,
                custom_id,
                label[:80],
                style.value,
                str(emoji) if emoji else None,
                message_text,
                message_text if message_text.strip().startswith("{embed}") else None
            )
            existing_labels.add(label.strip().lower())

        records = await self.bot.pool.fetch(
            "SELECT custom_id, label, style, emoji, response FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, target.id
        )

        view = ui.View(timeout=None)
        for r in records:
            button = ui.Button(
                label=r["label"],
                style=ButtonStyle(r["style"]),
                emoji=r["emoji"],
                custom_id=r["custom_id"]
            )

            async def make_callback(resp: str):
                if resp.strip().startswith("{embed}"):
                    async def callback(interaction: Interaction):
                        try:
                            ctx_like = await self.bot.get_context(interaction.message)
                            embed = await build_embed_from_raw(self.bot, ctx_like, resp)
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                        except Exception as e:
                            await interaction.response.send_message(f"Failed to build embed: {e}", ephemeral=True)
                    return callback
                else:
                    async def callback(interaction: Interaction):
                        await interaction.response.send_message(resp, ephemeral=True)
                    return callback

            button.callback = await make_callback(r["response"])
            view.add_item(button)

        await target.edit(view=view)
        self.bot.add_view(view)

        count = len(sections)
        word = "button" if count == 1 else "buttons"
        await ctx.approve(f"Added **{count} {word}** to [`this message`]({target.jump_url})")


    @button_group.command(name="remove", usage='button remove [message id or link] [button name]')
    @hybrid_permissions(manage_messages=True)
    async def button_remove(self, ctx: Context, message_ref: str, *, terms: str):
        """
        Remove a button from one of slains messages
        """
        msg_id = None
        channel_id = None
        message = None

        link_match = re.match(
            r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/\d+/(\d+)/(\d+)", message_ref
        )
        if link_match:
            channel_id, msg_id = map(int, link_match.groups())
        elif message_ref.isdigit():
            msg_id = int(message_ref)
        else:
            return await ctx.warn("Message link or ID is invalid")
        if not channel_id:
            result = await self.bot.pool.fetchrow(
                "SELECT channel_id FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
                ctx.guild.id, msg_id
            )
            if not result:
                return await ctx.warn("Could not find the channel for this message")
            channel_id = result["channel_id"]

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.warn("Channel no longer exists")

        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            message = None

        buttons = await self.bot.pool.fetch(
            "SELECT custom_id, label, style, emoji, response FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, msg_id
        )
        if not buttons:
            return await ctx.warn("**No buttons found** for that message")

        terms = [t.lower() for t in terms.split()]
        to_delete = [
            b for b in buttons
            if any(t in (b["label"] or "").lower() or t in (b["emoji"] or "").lower() for t in terms)
        ]

        if not to_delete:
            return await ctx.warn("No matching buttons found")

        for b in to_delete:
            await self.bot.pool.execute(
                "DELETE FROM persistent_buttons WHERE custom_id = $1",
                b["custom_id"]
            )
        if message:
            remaining = await self.bot.pool.fetch(
                "SELECT custom_id, label, style, emoji, response FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
                ctx.guild.id, msg_id
            )

            if remaining:
                view = ui.View(timeout=None)
                for r in remaining:
                    btn = ui.Button(
                        label=r["label"],
                        style=ButtonStyle(r["style"]),
                        emoji=r["emoji"],
                        custom_id=r["custom_id"]
                    )

                    async def make_cb(resp):
                        async def cb(interaction):
                            await interaction.response.send_message(resp, ephemeral=True)
                        return cb

                    btn.callback = await make_cb(r["response"])
                    view.add_item(btn)

                await message.edit(view=view)
                self.bot.add_view(view)
            else:
                await message.edit(view=None)

        jump_url = message.jump_url if message else f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{msg_id}"
        count = len(to_delete)
        word = "button" if count == 1 else "buttons"
        await ctx.approve(f"Removed **{count}** matching {word} from [`this message`]({jump_url})")


    @button_group.command(name="clear", usage='button clear [message id or link]')
    @hybrid_permissions(manage_messages=True)
    async def button_clear(self, ctx: Context, message_ref: str):
        """
        Remove all persistent buttons from a specific message
        """
        msg_id = None
        channel_id = None

        link_match = re.match(
            r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/\d+/(\d+)/(\d+)", message_ref
        )
        if link_match:
            channel_id, msg_id = map(int, link_match.groups())
        elif message_ref.isdigit():
            msg_id = int(message_ref)
        else:
            return await ctx.warn("Message **link** or **ID** is does not exist")

        if not channel_id:
            result = await self.bot.pool.fetchrow(
                "SELECT channel_id FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
                ctx.guild.id, msg_id
            )
            if not result:
                return await ctx.warn(f"Could not **resolve the channel** for [`this message`]({message.jump_url})")
            channel_id = result["channel_id"]

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.warn("Channel no longer exists")

        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return await ctx.warn("The message no longer exists")
        try:
            await message.edit(view=None)
        except:
            return await ctx.warn("Failed to remove buttons from the message.")

        deleted = await self.bot.pool.execute(
            "DELETE FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, msg_id
        )

        await ctx.approve(f"Removed **all buttons** from [`this message`]({message.jump_url})")


    @button_group.command(name="clearguild", usage='button clearguild')
    @hybrid_permissions(manage_messages=True)
    async def button_clear_guild(self, ctx: Context):
        """
        Remove all persistent buttons from all messages in this server
        """
        rows = await self.bot.pool.fetch(
            "SELECT DISTINCT channel_id, message_id FROM persistent_buttons WHERE guild_id = $1",
            ctx.guild.id
        )

        if not rows:
            return await ctx.warn("There are no persistent buttons in this server")

        removed = 0
        for row in rows:
            channel = ctx.guild.get_channel(row["channel_id"])
            if not channel:
                continue
            try:
                msg = await channel.fetch_message(row["message_id"])
                await msg.edit(view=None)
                removed += 1
            except:
                continue

        await self.bot.pool.execute("DELETE FROM persistent_buttons WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve(f"Cleared **{removed}** message{'s' if removed != 1 else ''} with persistent buttons")


    async def start(self):
        print("[Persistent] Initializing persistent buttons...")
        try:
            rows = await self.bot.pool.fetch("SELECT guild_id, channel_id, message_id, custom_id, label, style, emoji, response FROM persistent_buttons")
            if not rows:
                print("[Persistent] No persistent buttons found")
                return

            grouped = {}
            for r in rows:
                key = (r["guild_id"], r["channel_id"], r["message_id"])
                grouped.setdefault(key, []).append(r)

            total_messages = len(grouped)
            processed = 0
            failed = 0

            print(f"[Persistent] Processing {total_messages} messages with buttons...")

            for (g_id, ch_id, msg_id), items in grouped.items():
                try:
                    guild = self.bot.get_guild(g_id)
                    if not guild:
                        failed += 1
                        continue

                    channel = guild.get_channel(ch_id)
                    if not channel:
                        failed += 1
                        continue

                    try:
                        message = await channel.fetch_message(msg_id)
                    except discord.NotFound:
                        await self.bot.pool.execute(
                            "DELETE FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
                            g_id, msg_id
                        )
                        failed += 1
                        print(f"[Persistent] Message {msg_id} in guild {g_id} not found. Removed from DB.")
                        continue
                    except Exception as e:
                        failed += 1
                        print(f"[Persistent] Failed to fetch message {msg_id} in guild {g_id}: {e}")
                        continue

                    view = ui.View(timeout=None)
                    for r in items:
                        btn = ui.Button(
                            label=r["label"],
                            style=ButtonStyle(r["style"]),
                            emoji=r["emoji"],
                            custom_id=r["custom_id"]
                        )

                        async def make_cb(response_copy):
                            if response_copy.strip().startswith("{embed}"):
                                async def cb(interaction):
                                    try:
                                        ctx_like = await self.bot.get_context(interaction.message)
                                        embed = await build_embed_from_raw(self.bot, ctx_like, response_copy)
                                        await interaction.response.send_message(embed=embed, ephemeral=True)
                                    except Exception as e:
                                        await interaction.response.send_message(f"Failed to rebuild embed: {e}", ephemeral=True)
                                return cb
                            else:
                                async def cb(interaction):
                                    await interaction.response.send_message(response_copy, ephemeral=True)
                                return cb

                        btn.callback = await make_cb(str(r["response"]))
                        view.add_item(btn)

                    try:
                        await message.edit(view=view)
                        await asyncio.sleep(3.0)
                    except discord.HTTPException as e:
                        failed += 1
                        print(f"[Persistent] Failed to reapply view to message {msg_id}: {e}")
                        if "emoji" in str(e) or "Invalid" in str(e):
                            await self.bot.pool.execute(
                                "DELETE FROM persistent_buttons WHERE guild_id = $1 AND message_id = $2",
                                g_id, msg_id
                            )
                            print(f"[Persistent] Deleted invalid buttons for message {msg_id} due to error")
                        continue

                    self.bot.add_view(view)
                    processed += 1

                except Exception as e:
                    failed += 1
                    continue

            print(f"[Persistent] Loaded {processed} button views, {failed} failed")

            if failed > 0:
                asyncio.create_task(self._cleanup_orphaned_buttons())

        except Exception as e:
            print(f"[Persistent] Failed to initialize: {e}")

    async def _cleanup_orphaned_buttons(self):
        await asyncio.sleep(30)
        try:
            rows = await self.bot.pool.fetch("SELECT DISTINCT guild_id, channel_id, message_id FROM persistent_buttons")
            to_remove = []
            
            for row in rows:
                guild = self.bot.get_guild(row['guild_id'])
                if not guild:
                    to_remove.append((row['guild_id'], row['channel_id'], row['message_id']))
                    continue
                    
                channel = guild.get_channel(row['channel_id'])
                if not channel:
                    to_remove.append((row['guild_id'], row['channel_id'], row['message_id']))
            
            if to_remove:
                for guild_id, channel_id, message_id in to_remove:
                    await self.bot.pool.execute(
                        "DELETE FROM persistent_buttons WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                        guild_id, channel_id, message_id
                    )
                print(f"[Persistent] Cleaned up {len(to_remove)} orphaned button records")
        except Exception as e:
            print(f"[Persistent] Cleanup failed: {e}")


async def setup(bot: Bot):
    persistent = Persistent(bot)
    await bot.add_cog(Embeds(bot))    
    await bot.add_cog(persistent)
    
    async def delayed_start():
        await asyncio.sleep(2)
        await persistent.start()
    
    bot.loop.create_task(delayed_start())
