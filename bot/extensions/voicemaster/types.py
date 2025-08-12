from typing import TypedDict

from discord import Member, VoiceChannel, VoiceState
from bot.core import Context as BaseContext


class MemberVoice(VoiceState):
    channel: VoiceChannel


class MemberInVoice(Member):
    voice: MemberVoice


class Context(BaseContext):
    author: MemberInVoice


class ConfigRecord(TypedDict):
    guild_id: int
    category_id: int
    channel_id: int
    panel_id: int

class Record(TypedDict):
    guild_id: int
    channel_id: int
    owner_id: int
