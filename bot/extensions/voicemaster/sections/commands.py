import asyncio
from contextlib import suppress
from typing import Optional, cast
from discord import (
    CategoryChannel,
    HTTPException,
    Member,
    Message,
    PermissionOverwrite,
    RateLimited,
    Role,
)
from discord.ext.commands import (
    Cog,
    Range,
    BucketType,
    hybrid_group,
    max_concurrency,
    cooldown,
)
from discord.app_commands import Choice, choices
from humanfriendly import format_timespan
from bot.shared.formatter import plural
from bot.core import Bot
from ..types import ConfigRecord, Context
from ..checks import is_in_voice
from bot.shared.fakeperms import hybrid_permissions
from .panel import Panel



class Commands(Cog):
    """Commands for the VoiceMaster extension."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: Context):
        await is_in_voice(ctx)
        return super().cog_check(ctx)
    
    @hybrid_group(aliases=("voice", "vc", "vm"), usage='voicemaster', invoke_without_command=True)
    async def voicemaster(self, ctx: Context) -> Message:
        """Manage temporary voice channels"""

        return await ctx.send_help(ctx.command)

    @voicemaster.command(name="setup", aliases=("init",), usage='voicemaster setup')
    @hybrid_permissions(manage_channels=True)
    @cooldown(1, 30, BucketType.guild)
    async def voicemaster_setup(self, ctx: Context) -> Message:
        """Setup the channel for VoiceMaster creation."""

        query = "SELECT channel_id FROM voicemaster.config WHERE guild_id = $1"
        channel_id = cast(
            Optional[int],
            await self.bot.pool.fetchval(query, ctx.guild.id),
        )
        if channel_id and (channel := ctx.guild.get_channel(channel_id)):
            return await ctx.warn(
                f"The VoiceMaster channel is already set to {channel.mention}",
                tip=f"Use `{ctx.clean_prefix}voicemaster reset` to remove it",
            )

        query = """
        INSERT INTO voicemaster.config (guild_id, category_id, channel_id, panel_id)
        VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id)
        DO UPDATE SET
            category_id = EXCLUDED.category_id,
            channel_id = EXCLUDED.channel_id,
            panel_id = EXCLUDED.panel_id
        """
        category = await ctx.guild.create_category("Voice Channels")
        channel, panel = await asyncio.gather(
            category.create_voice_channel(
                "Join to Create",
                overwrites={
                    ctx.guild.default_role: PermissionOverwrite(
                        connect=True,
                        send_messages=False,
                    ),
                },
            ),
            category.create_text_channel(
                "panel",
                overwrites={
                    ctx.guild.default_role: PermissionOverwrite(
                        send_messages=False,
                        add_reactions=False,
                        create_public_threads=False,
                        create_private_threads=False,
                    )
                },
            ),
        )
        await panel.send(embed=Panel.embed(ctx.guild, channel), view=Panel(self.bot))
        await self.bot.pool.execute(query, ctx.guild.id, category.id, channel.id, panel.id)

        return await ctx.approve(
            "The VoiceMaster channel has been created",
            tip=f"Join {channel.mention} to get started",
        )


    @voicemaster.command(name="reset", usage='voicemaster reset')
    @hybrid_permissions(manage_channels=True)
    async def voicemaster_reset(self, ctx: Context) -> Message:
        """Reset the VoiceMaster configuration."""

        query = "DELETE FROM voicemaster.config WHERE guild_id = $1 RETURNING *"
        record = cast(
            Optional[ConfigRecord],
            await self.bot.pool.fetchrow(query, ctx.guild.id),
        )
        if not record:
            return await ctx.warn(
                "The VoiceMaster channel has not been set up yet",
                tip=f"Use **{ctx.clean_prefix}voicemaster setup** to get started",
            )

        with suppress(HTTPException):
            for channel_id in {record["category_id"], record["channel_id"], record["panel_id"]}:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    await channel.delete(
                        reason=f"VoiceMaster configuration reset by {ctx.author}"
                    )

        return await ctx.approve(
            "The VoiceMaster configuration has been reset",
            tip=f"Use **{ctx.clean_prefix}voicemaster setup** to create a new VoiceMaster",
        )


    @voicemaster.command(name="category", usage='voicemaster category [name]')
    @hybrid_permissions(manage_channels=True)
    async def voicemaster_category(self, ctx: Context, *, category: Optional[CategoryChannel]) -> Message:
        """Set the category for VoiceMaster channels."""

        query = "UPDATE voicemaster.config SET category_id = $2 WHERE guild_id = $1"
        result = await self.bot.pool.execute(
            query,
            ctx.guild.id,
            category.id if category else 0,
        )
        if result == "UPDATE 0":
            return await ctx.warn(
                "The VoiceMaster channel has not been set up yet",
                tip=f"Use **{ctx.clean_prefix}voicemaster setup** to get started",
            )

        return await ctx.approve(
            f"New channels will be created under `{category.name}`"
            if isinstance(category, CategoryChannel)
            else "No longer placing voice channels under a category\n"
        )



    @voicemaster.command(name="claim", usage='voicemaster claim')
    async def voicemaster_claim(self, ctx: Context) -> Message:
        """Claim ownership of the voice channel"""

        channel = ctx.author.voice.channel
        query = "UPDATE voicemaster.channel SET owner_id = $2 WHERE channel_id = $1"
        await self.bot.pool.execute(query, channel.id, ctx.author.id)

        if (
            channel.name.endswith("'s channel")
            and ctx.author.display_name not in channel.name
        ):
            with suppress(HTTPException):
                await channel.edit(name=f"{ctx.author.display_name}'s channel")

        return await ctx.approve(f"You now have ownership of {channel.mention}")


    @voicemaster.command(name="transfer", aliases=("give",), usage='voicemaster transfer [user or id]')
    async def voicemaster_transfer(self, ctx: Context, *, member: Member) -> Message:
        """Transfer ownership of your voice channel."""

        channel = ctx.author.voice.channel
        if member == ctx.author or member.bot:
            return await ctx.warn("You can't transfer ownership to yourself or a bot")

        elif member not in channel.members:
            return await ctx.warn("That member is not in your voice channel")

        query = "UPDATE voicemaster.channel SET owner_id = $2 WHERE channel_id = $1"
        await self.bot.pool.execute(query, channel.id, member.id)
        if (
            channel.name.endswith("'s channel")
            and ctx.author.display_name not in channel.name
        ):
            with suppress(HTTPException):
                await channel.edit(name=f"{ctx.author.display_name}'s channel")

        return await ctx.approve(f"You've transferred ownership to {member.mention}")



    @voicemaster.command(name="rename", aliases=("name",), usage='voicemaster rename [new name]')
    @cooldown(1, 15, BucketType.user)
    async def voicemaster_rename(
        self,
        ctx: Context,
        *,
        name: Range[str, 1, 100],
    ) -> Optional[Message]:
        """Rename your voice channel."""

        channel = ctx.author.voice.channel
        try:
            await channel.edit(
                name=name,
                reason=f"{ctx.author} renamed the channel",
            )
        except RateLimited as exc:
            return await ctx.warn(
                "Your voice channel has reached its rate limit",
                tip=f"The rate limit will be released in {format_timespan(exc.retry_after)}",
            )

        except HTTPException:
            return await ctx.warn(
                "The channel name provided wasn't able to be set",
                tip="Make sure the name doesn't contain vulgar language",
            )

        return await ctx.approve("Your voice channel has been renamed")


    @voicemaster.command(name="status", usage='voicemaster status [description]')
    async def voicemaster_status(
        self,
        ctx: Context,
        *,
        status: Optional[Range[str, 1, 500]],
    ) -> Optional[Message]:
        """Set the status of your voice channel."""

        channel = ctx.author.voice.channel
        await channel.edit(status=status)
        return await ctx.approve(
            f"Your voice channel status has been {'updated' if status else 'removed'}"
        )


    @voicemaster.command(name="limit", usage='voicemaster limit [amount]')
    async def voicemaster_limit(
        self,
        ctx: Context,
        limit: Range[int, 0, 99],
    ) -> Message:
        """Set a user limit for your voice channel."""

        channel = ctx.author.voice.channel
        await channel.edit(user_limit=limit)
        return await ctx.approve(
            f"Your voice channel now has a limit of {plural(limit, '`'):user}"
            if limit
            else "Removed the user limit from your voice channel"
        )


    @voicemaster.command(name="music", aliases=("listen",), usage='voicemaster music')
    @cooldown(1, 30, BucketType.user)
    @max_concurrency(1, BucketType.user)
    async def voicemaster_music(self, ctx: Context) -> Message:
        """Mute everyone in the voice channel except the bot."""

        channel = ctx.author.voice.channel
        if channel.overwrites_for(ctx.guild.default_role).speak is False:
            await asyncio.gather(
                channel.set_permissions(
                    ctx.guild.default_role,
                    speak=None,
                    reason=f"{ctx.author} disabled music mode",
                ),
                *[
                    channel.set_permissions(member, speak=True)
                    for member in list(channel.members) + [ctx.guild.me]
                    if member.bot
                ],
            )
            return await ctx.approve("Now allowing everyone to speak in the channel")

        await asyncio.gather(
            channel.set_permissions(
                ctx.guild.default_role,
                speak=False,
                reason=f"{ctx.author} enabled music mode",
            ),
            *[
                channel.set_permissions(member, speak=True)
                for member in list(channel.members) + [ctx.guild.me]
                if member.bot
            ],
        )
        return await ctx.approve("Now only allowing bots to speak in the channel")


    @voicemaster.command(name="lock", usage='voicemaster lock')
    async def voicemaster_lock(self, ctx: Context) -> Optional[Message]:
        """Deny members from joining your voice channel."""

        channel = ctx.author.voice.channel
        if channel.overwrites_for(ctx.guild.default_role).connect is False:
            return await ctx.warn("Your voice channel is already locked")

        await channel.set_permissions(ctx.guild.default_role, connect=False)
        with suppress(HTTPException):
            await asyncio.gather(
                *[
                    channel.set_permissions(member, connect=True)
                    for member in channel.members[:100]
                ]
            )

        return await ctx.approve("Your voice channel has been locked")


    @voicemaster.command(name="unlock", usage='voicemaster unlock')
    async def voicemaster_unlock(self, ctx: Context) -> Optional[Message]:
        """Allow members to join your voice channel."""

        channel = ctx.author.voice.channel
        if channel.overwrites_for(ctx.guild.default_role).connect is None:
            return await ctx.warn("Your voice channel is already unlocked")

        await channel.set_permissions(ctx.guild.default_role, connect=None)
        return await ctx.approve("Your voice channel has been unlocked")


    @voicemaster.command(name="hide", aliases=("ghost",), usage='voicemaster hide')
    async def voicemaster_hide(self, ctx: Context) -> Optional[Message]:
        """Hide your voice channel from the channel list."""

        channel = ctx.author.voice.channel
        if channel.overwrites_for(ctx.guild.default_role).view_channel is False:
            return await ctx.warn("Your voice channel is already hidden")

        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        return await ctx.approve("Your voice channel is now hidden")


    @voicemaster.command(name="reveal", aliases=("show", "unhide"), usage='voicemaster reveal')
    async def voicemaster_reveal(self, ctx: Context) -> Optional[Message]:
        """Reveal your voice channel in the channel list."""

        channel = ctx.author.voice.channel
        if channel.overwrites_for(ctx.guild.default_role).view_channel is None:
            return await ctx.warn("Your voice channel is already visible")

        await channel.set_permissions(ctx.guild.default_role, view_channel=None)
        return await ctx.approve("Your voice channel is now visible")

    @voicemaster.command(name="permit", aliases=("allow", "add"), usage='voicemaster permit [user or id]')
    async def voicemaster_permit(
        self,
        ctx: Context,
        *,
        target: Member | Role,
    ) -> Optional[Message]:
        """Allow a member to join your voice channel."""

        channel = ctx.author.voice.channel
        await channel.set_permissions(target, connect=True, view_channel=True)
        return await ctx.approve(f"{target.mention} can now join your voice channel")


    @voicemaster.command(name="reject", aliases=("remove", "deny", "kick"), usage='voicemaster kick [user or id]')
    async def voicemaster_reject(
        self,
        ctx: Context,
        *,
        target: Member | Role,
    ) -> Optional[Message]:
        """Deny a member from joining your voice channel."""

        channel = ctx.author.voice.channel
        await channel.set_permissions(target, connect=False, view_channel=True)
        if isinstance(target, Member) and target in channel.members:
            with suppress(HTTPException):
                await target.move_to(None)

        return await ctx.approve(
            f"{target.mention} is no longer permitted to join your voice channel"
        )


    @voicemaster.command(name="invite", aliases=("link",), usage='voicemaster link')
    @cooldown(1, 20, BucketType.user)
    async def voicemaster_invite(self, ctx: Context) -> Message:
        """Create an invite link to your voice channel."""

        channel = ctx.author.voice.channel
        invite = await channel.create_invite(max_age=0)
        return await ctx.reply(invite.url)


    @voicemaster.command(name="nsfw", aliases=("18+",), usage='voicemaster nsfw')
    async def voicemaster_nsfw(self, ctx: Context) -> Optional[Message]:
        """Mark your voice channel as NSFW."""

        channel = ctx.author.voice.channel
        channel = await channel.edit(nsfw=not channel.is_nsfw())
        return await ctx.approve(
            f"Your voice channel is {'now' if channel.is_nsfw() else 'no longer'} marked as NSFW"
        )


    @voicemaster.command(name="region", aliases=("location",), usage='voicemaster region [location]')
    @choices(
        region=[
            Choice(name=name, value=value)
            for name, value in {
                "US Central": "us-central",
                "US East": "us-east",
                "US South": "us-south",
                "US West": "us-west",
                "Brazil": "brazil",
                "Hong Kong": "hongkong",
                "India": "india",
                "Japan": "japan",
                "Rotterdam": "rotterdam",
                "Russia": "russia",
                "Singapore": "singapore",
                "South Korea": "south-korea",
                "South Africa": "southafrica",
                "Sydney": "sydney",
            }.items()
        ],
    )
    async def voicemaster_region(
        self,
        ctx: Context,
        region: Choice[str],
    ) -> Optional[Message]:
        """Set the region of your voice channel."""

        channel = ctx.author.voice.channel
        await channel.edit(rtc_region=region.value)
        return await ctx.approve(
            f"Your voice channel region has been set to `{region.name}`"
        )
