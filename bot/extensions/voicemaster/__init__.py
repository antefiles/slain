from contextlib import suppress
from typing import Optional, cast
from discord import HTTPException, VoiceChannel
from discord.ext.commands import Cog
from bot.core import Bot
from .types import Record
from .checks import is_empty
from logging import getLogger
from .sections import Commands, Events, Panel
from bot.shared.formatter import plural

logger = getLogger(__name__)


class VoiceMaster(Commands, Events, Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(Panel(self.bot))
        self.bot.loop.create_task(self.cleanup_channels())
        return await super().cog_load()

    async def cleanup_channels(self) -> None:
        """Delete unucupied VoiceMaster channels."""

        query = "SELECT channel_id FROM voicemaster.channel"
        records = cast(list[Record], await self.bot.pool.fetch(query))
        removed: list[int] = []

        for record in records:
            channel = cast(
                Optional[VoiceChannel],
                self.bot.get_channel(record["channel_id"]),
            )
            if not channel or is_empty(channel):
                removed.append(record["channel_id"])
                if channel:
                    with suppress(HTTPException):
                        await channel.delete()

        if removed:
            query = """
            DELETE FROM voicemaster.channel
            WHERE channel_id = ANY($1::BIGINT[])
            """
            await self.bot.pool.execute(query, removed)
            logger.info(
                f"Removed {len(removed)} unucupied VoiceMaster {plural(len(removed)):channel}"
            )

async def setup(bot: Bot) -> None:
    await bot.add_cog(VoiceMaster(bot))