from __future__ import annotations

from datetime import datetime
from typing import (
    Any,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
    Self,
    Tuple,
    Unpack,
    TypedDict,
    Union,
    cast,
)
import random

from discord import (
    AllowedMentions,
    ButtonStyle,
    Color,
    Guild,
    Member,
    Message,
    MessageReference,
)
import discord
from discord.ui import View, Button
from discord.ext.commands import Context as BaseContext
from discord.ext.commands.core import Command
from .help import HelpCommand

if TYPE_CHECKING:
    from bot.core import Bot


__all__ = ("Context", "Embed", "HelpCommand")

class MessageKwargs(TypedDict, total=False):
    content: Optional[str]
    tts: Optional[bool]
    allowed_mentions: Optional[AllowedMentions]
    reference: Optional[MessageReference]
    mention_author: Optional[bool]
    delete_after: Optional[float]

    # Embed Related
    url: Optional[str]
    title: Optional[str]
    color: Optional[Color]
    image: Optional[str]
    description: Optional[str]
    thumbnail: Optional[str]
    footer: Optional[FooterDict]
    author: Optional[AuthorDict]
    fields: Optional[List[FieldDict]]
    timestamp: Optional[datetime]
    view: Optional[View]
    buttons: Optional[List[ButtonDict]]


class FieldDict(TypedDict, total=False):
    name: str
    value: str
    inline: bool


class FooterDict(TypedDict, total=False):
    text: Optional[str]
    icon_url: Optional[str]


class AuthorDict(TypedDict, total=False):
    name: Optional[str]
    icon_url: Optional[str]


class ButtonDict(TypedDict, total=False):
    url: Optional[str]
    emoji: Optional[str]
    style: Optional[ButtonStyle]
    label: Optional[str]


def get_index(iterable: Optional[Tuple[Any, Any]], index: int) -> Optional[Any]:
    if not iterable or (type(iterable) is not tuple and index != 0):
        return None

    if type(iterable) is not tuple and index == 0:
        return iterable

    return iterable[index] if len(iterable) > index else None


class Context(BaseContext):
    bot: "Bot"
    guild: Guild  # type: ignore
    author: Member
    command: Command

    @property
    def clean_prefix(self) -> str:
        return super().clean_prefix or "/"

    async def send_help(self, entity: Union[Command, str, None] = None) -> Optional[Message]:
        """Send help information for the given entity.
        
        Args:
            entity: The entity to send help for. Can be a Command, string, or None.
                   If None, sends general bot help.
                   If string, looks up the command by name.
                   If Command, sends help for that command.
        
        Returns:
            Optional[Message]: The help message sent, or None if no help command is configured.
        """
        if not self.bot.help_command:
            return None
            
        try:
            help_command = self.bot.help_command
            help_command.context = self
            
            import asyncio
            
            async def _send_help():
                if entity is None:
                    await help_command.send_bot_help(help_command.get_bot_mapping())
                    
                elif isinstance(entity, str):
                    command = self.bot.get_command(entity)
                    if command is not None:
                        await help_command.send_command_help(command)
                        
                elif isinstance(entity, Command):
                    await help_command.send_command_help(entity)
            
            await asyncio.wait_for(_send_help(), timeout=30.0)
                
        except asyncio.TimeoutError:
            try:
                await self.warn("Help command timed out")
            except:
                pass
        except Exception as e:
            try:
                await self.warn(f"Help command failed: {str(e)}")
            except:
                pass
                
        return None

    async def embed(self, **kwargs: Unpack[MessageKwargs]) -> Message:
        return await self.send(**self.create(**kwargs))

    def create(self, **kwargs: Unpack[MessageKwargs]) -> Dict[str, Any]:
        """Create a message with the given keword arguments.

        Returns:
            Dict[str, Any]: The message content, embed, view and delete_after.
        """
        view = View()

        for button in kwargs.get("buttons") or []:
            if not button or not button.get("label"):
                continue

            view.add_item(
                Button(
                    label=button.get("label"),
                    style=button.get("style") or ButtonStyle.secondary,
                    emoji=button.get("emoji"),
                    url=button.get("url"),
                )
            )

        embed = (
            Embed(
                url=kwargs.get("url"),
                description=kwargs.get("description"),
                title=kwargs.get("title"),
                color=kwargs.get("color") or Color.dark_embed(),
                timestamp=kwargs.get("timestamp"),
            )
            .set_image(url=kwargs.get("image"))
            .set_thumbnail(url=kwargs.get("thumbnail"))
            .set_footer(
                text=cast(dict, kwargs.get("footer", {})).get("text"),
                icon_url=cast(dict, kwargs.get("footer", {})).get("icon_url"),
            )
            .set_author(
                name=cast(dict, kwargs.get("author", {})).get("name", ""),
                icon_url=cast(dict, kwargs.get("author", {})).get("icon_url", ""),
            )
        )

        for field in kwargs.get("fields") or []:
            if not field:
                continue

            embed.add_field(
                name=field.get("name"),
                value=field.get("value"),
                inline=field.get("inline", False),
            )

        return {
            "content": kwargs.get("content"),
            "embed": embed,
            "view": kwargs.get("view") or view,
            "delete_after": kwargs.get("delete_after"),
        }

    async def approve(
        self,
        message: str,
        tip: Optional[str] = None,
        **kwargs: Unpack[MessageKwargs],
    ) -> Message:
        emoji = "<:slain_approve:1392318903325036635>"
        message = f"{emoji} {message}"

        if tip and random.random() < 0.8:
            message += f"\n-# *{tip}*"

        kwargs["description"] = message
        kwargs["color"] = discord.Color.from_str("#7b9fb0")
        return await self.embed(**kwargs)
    
    async def config(
        self,
        message: str,
        tip: Optional[str] = None,
        **kwargs: Unpack[MessageKwargs],
    ) -> Message:
        emoji = "<:slain_Settings:1391058914816167996>"
        message = f"{emoji} {message}"

        if tip and random.random() < 0.8:
            message += f"\n-# *{tip}*"

        kwargs["description"] = message
        kwargs["color"] = discord.Color.from_str("#acacac")
        return await self.embed(**kwargs)

    async def settings(
        self,
        message: str,
        tip: Optional[str] = None,
        **kwargs: Unpack[MessageKwargs],
    ) -> Message:
        emoji = "<:mod_action:1391451706260197479>"
        message = f"{emoji} {message}"

        if tip and random.random() < 0.8:
            message += f"\n-# *{tip}*"

        kwargs["description"] = message
        kwargs["color"] = discord.Color.from_str("#acacac")
        return await self.embed(**kwargs)

    async def warn(
        self,
        message: str,
        tip: Optional[str] = None,
        **kwargs: Unpack[MessageKwargs],
    ) -> Message:
        emoji = "<:slain_error:1390898515131105431>"
        message = f"{emoji} {message}"

        if tip and random.random() < 0.8:
            message += f"\n-# *{tip}*"

        kwargs["description"] = message
        kwargs["color"] = discord.Color.from_str("#ec3c4c")  # Fixed capitalization
        return await self.embed(**kwargs)

    async def clock(
        self,
        message: str,
        tip: Optional[str] = None,
        **kwargs: Unpack[MessageKwargs],
    ) -> Message:
        emoji = "<:slain_clock:1394753370375454851>"
        message = f"{emoji} {message}"

        if tip and random.random() < 0.8:
            message += f"\n-# *{tip}*"

        kwargs["description"] = message
        kwargs["color"] = discord.Color.from_str("#7b9fb0")  # Fixed capitalization
        return await self.embed(**kwargs)


class Embed(discord.Embed):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        if self.color in (None, Color.default()):
            self.color = Color.dark_embed()

    def add_field(self, *, name: Any, value: Any, inline: bool = True) -> Self:
        return super().add_field(name=f"**{name}**", value=value, inline=inline)


discord.Embed = Embed
