import asyncio
from contextlib import suppress
from typing import Optional, cast
from discord import CategoryChannel, HTTPException, Member, VoiceState
from discord.ext.commands import Cog
from bot.core import Bot
from ..types import ConfigRecord
from ..checks import is_empty
from cashews import cache
from logging import getLogger

logger = getLogger(__name__)


class Events(Cog):
    """Events for the VoiceMaster extension."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @Cog.listener("on_voice_state_update")
    async def create_voice_channel(
        self,
        member: Member,
        before: VoiceState,
        after: VoiceState,
    ) -> None:
        """Create a VoiceMaster channel for the member."""

        guild = member.guild
        if member.bot or not after.channel:
            return

        elif before.channel == after.channel:
            return

        elif not guild.me.guild_permissions.administrator:
            return

        query = "SELECT channel_id, category_id FROM voicemaster.config WHERE guild_id = $1"
        config = cast(
            Optional[ConfigRecord],
            await self.bot.pool.fetchrow(query, guild.id),
        )
        if not config or config["channel_id"] != after.channel.id:
            return

        count, guild_count = await asyncio.gather(
            cache.incr(
                f"voicemaster:{member.id}",
                expire=10,
            ),
            cache.incr(
                f"voicemaster:{guild.id}",
                expire=30,
            ),
        )
        if count > 1:
            await member.move_to(None)
            return

        elif guild_count > 10:
            return

        category: Optional[CategoryChannel] = None
        if config["category_id"] != 0:
            category = cast(
                Optional[CategoryChannel],
                guild.get_channel(config["category_id"]) or after.channel.category,
            )
        try:
            channel = await guild.create_voice_channel(
                name=f"{member.display_name}'s channel"[:100],
                category=category,
                bitrate=int(guild.bitrate_limit),
                reason=f"VoiceMaster channel for {member}",
            )
            await channel.set_permissions(
                member,
                connect=True,
                view_channel=True,
                read_messages=True,
            )
        except HTTPException as exc:
            logger.error(
                f"Failed to create channel for {member} in {guild}", exc_info=exc
            )
            return
        else:
            logger.info(f"Created voice channel for {member} in {guild}")

        try:
            await member.move_to(channel)
        except HTTPException:
            with suppress(HTTPException):
                await channel.delete()

            return

        query = "INSERT INTO voicemaster.channel VALUES ($1, $2, $3)"
        await self.bot.pool.execute(query, guild.id, channel.id, member.id)

    @Cog.listener("on_voice_state_update")
    async def delete_voice_channel(
        self,
        member: Member,
        before: VoiceState,
        after: VoiceState,
    ) -> None:
        """Delete VoiceMaster channels that are unoccupied."""

        if not before.channel or before.channel == after.channel:
            return

        elif not is_empty(before.channel):
            return

        query = "DELETE FROM voicemaster.channel WHERE channel_id = $1"
        result = await self.bot.pool.execute(query, before.channel.id)
        if result == "DELETE 0":
            return

        with suppress(HTTPException):
            await before.channel.delete()
