from __future__ import annotations
from typing import TYPE_CHECKING, Optional, cast
from discord.ext.commands import CommandError
from bot.core import Context

if TYPE_CHECKING:
    from discord.guild import VocalGuildChannel


def is_empty(channel: VocalGuildChannel) -> bool:
    members = filter(lambda member: not member.bot, channel.members)
    return not any(members)


async def is_in_voice(ctx: Context) -> bool:
    """Check if the invoker is in a voice channel."""

    configuration_commands = ("setup", "reset", "category")
    if not ctx.command.qualified_name.startswith("voicemaster"):
        return True

    elif not ctx.command.parent or ctx.command.name.startswith(
        configuration_commands
    ):
        return True

    elif not ctx.author.voice or not ctx.author.voice.channel:
        raise CommandError("You aren't connected to a voice channel")

    query = "SELECT owner_id FROM voicemaster.channel WHERE channel_id = $1"
    owner_id = cast(
        Optional[int],
        await ctx.bot.pool.fetchval(query, ctx.author.voice.channel.id),
    )
    if not owner_id:
        raise CommandError("You aren't in a VoiceMaster channel")

    elif ctx.command.name == "claim":
        if ctx.author.id == owner_id:
            raise CommandError("You are already the owner of this voice channel")

        elif owner_id in {member.id for member in ctx.author.voice.channel.members}:
            raise CommandError("The owner is still connected to this voice channel")

        return True

    elif ctx.author.id != owner_id:
        raise CommandError("You aren't the owner of this voice channel")

    return True
