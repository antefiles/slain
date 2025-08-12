import asyncio
from contextlib import suppress
from typing import Optional, cast, no_type_check
from discord import (
    Embed,
    Guild,
    HTTPException,
    Interaction as BaseInteraction,
    Member,
    RateLimited,
    Role,
    SelectOption,
    VoiceChannel,
)
from discord.ui import View, Modal, Select, TextInput, Button, button
from typing import Any
from discord.utils import format_dt
from bot.shared.formatter import plural
from config import Emojis
from bot.core import Bot
from ..types import MemberInVoice


class Interaction(BaseInteraction):
    guild: Guild
    user: MemberInVoice


emojis = Emojis.VOICEMASTER
button: Any = button

@no_type_check
class Panel(View):
    bot: Bot

    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @classmethod
    def embed(cls, guild: Guild, channel: VoiceChannel) -> Embed:
        embed = Embed(
            title="<:voicemaster_icon:1391924244098842654> VoiceMaster Panel",
            description=f"Join {channel.mention} to create a voice channel",
            color=0xacacac
        )
        embed.add_field(
            name="Member Management",
            value="\n".join(
                [
                    f"{emojis.LOCK} Lock the channel",
                    f"{emojis.UNLOCK} Unlock the channel",
                    f"{emojis.HIDE} Hide the channel",
                    f"{emojis.REVEAL} Reveal the channel",
                    f"{emojis.DISCONNECT} Disconnect members",
                ]
            ),
        )
        embed.add_field(
            name="Miscellaneous",
            value="\n".join(
                [
                    f"{emojis.CLAIM} Claim ownership",
                    f"{emojis.RENAME} Rename the channel",
                    f"{emojis.UPDATE_LIMIT} Update the user limit",
                    f"{emojis.INFORMATION} View information",
                    f"{emojis.DELETE} Delete the channel",
                ]
            ),
        )
        return embed

    async def send_response(self, interaction: Interaction, description: str, **kwargs):
        embed = Embed(description=description)
        await interaction.response.send_message(embed=embed, ephemeral=True, **kwargs)

    async def interaction_check(self, interaction: Interaction) -> bool:
        user = interaction.user
        assert isinstance(user, Member)

        if not user.voice or not user.voice.channel:
            await self.send_response(
                interaction, "You aren't connected to a voice channel"
            )
            return False

        query = "SELECT owner_id FROM voicemaster.channel WHERE channel_id = $1"
        owner_id = cast(
            Optional[int],
            await self.bot.pool.fetchval(query, user.voice.channel.id),
        )
        if not owner_id:
            await self.send_response(interaction, "You aren't in a VoiceMaster channel")
            return False

        elif (interaction.data["custom_id"] or "").endswith("claim"):  # type: ignore
            if user.id == owner_id:
                await self.send_response(
                    interaction, "You are already the owner of this voice channel"
                )
                return False

            elif owner_id in {member.id for member in user.voice.channel.members}:
                await self.send_response(
                    interaction, "The owner is still connected to this voice channel"
                )
                return False

            return True

        elif user.id != owner_id:
            await self.send_response(
                interaction, "You aren't the owner of this voice channel"
            )
            return False

        return True

    @button(emoji=emojis.LOCK, custom_id="voicemaster:lock")
    async def lock(self, interaction: Interaction, _: Button):
        """Deny members from joining your voice channel."""

        channel = interaction.user.voice.channel
        if channel.overwrites_for(interaction.guild.default_role).connect is False:
            return await self.send_response(
                interaction,
                "Your voice channel is already locked",
            )

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        with suppress(HTTPException):
            await asyncio.gather(
                *[
                    channel.set_permissions(member, connect=True)
                    for member in channel.members[:100]
                ]
            )

        return await self.send_response(
            interaction,
            "Your voice channel has been locked",
        )

    @button(emoji=emojis.UNLOCK, custom_id="voicemaster:unlock")
    async def unlock(self, interaction: Interaction, _: Button):
        """Allow members to join your voice channel."""

        channel = interaction.user.voice.channel
        if channel.overwrites_for(interaction.guild.default_role).connect is None:
            return await self.send_response(
                interaction,
                "Your voice channel is already unlocked",
            )

        await channel.set_permissions(interaction.guild.default_role, connect=None)
        return await self.send_response(
            interaction,
            "Your voice channel has been unlocked",
        )

    @button(emoji=emojis.HIDE, custom_id="voicemaster:hide")
    async def hide(self, interaction: Interaction, _: Button):
        """Hide your voice channel from the channel list."""

        channel = interaction.user.voice.channel
        if channel.overwrites_for(interaction.guild.default_role).view_channel is False:
            return await self.send_response(
                interaction,
                "Your voice channel is already hidden",
            )

        await channel.set_permissions(
            interaction.guild.default_role, view_channel=False
        )
        return await self.send_response(
            interaction,
            "Your voice channel is now hidden",
        )

    @button(emoji=emojis.REVEAL, custom_id="voicemaster:reveal")
    async def reveal(self, interaction: Interaction, _: Button):
        """Reveal your voice channel in the channel list."""

        channel = interaction.user.voice.channel
        if channel.overwrites_for(interaction.guild.default_role).view_channel is None:
            return await self.send_response(
                interaction,
                "Your voice channel is already visible",
            )

        await channel.set_permissions(interaction.guild.default_role, view_channel=None)
        return await self.send_response(
            interaction,
            "Your voice channel is now visible",
        )

    @button(emoji=emojis.DISCONNECT, custom_id="voicemaster:disconnect")
    async def disconnect(self, interaction: Interaction, _: Button):
        """Disconnect members from your voice channel."""

        view = View(timeout=None)
        view.add_item(Disconnect(self, interaction.user))
        return await self.send_response(
            interaction,
            "Select the members you want to disconnect",
            view=view,
        )

    @button(emoji=emojis.CLAIM, custom_id="voicemaster:claim")
    async def claim(self, interaction: Interaction, _: Button):
        """Claim ownership of the voice channel."""

        channel = interaction.user.voice.channel
        query = "UPDATE voicemaster.channel SET owner_id = $2 WHERE channel_id = $1"
        await self.bot.pool.execute(query, channel.id, interaction.user.id)

        if (
            channel.name.endswith("'s channel")
            and interaction.user.display_name not in channel.name
        ):

            async def callback() -> None:
                with suppress(HTTPException):
                    await channel.edit(
                        name=f"{interaction.user.display_name}'s channel"
                    )

            self.bot.loop.create_task(callback())

        return await self.send_response(
            interaction,
            f"You now have ownership of {channel.mention}",
        )

    @button(emoji=emojis.RENAME, custom_id="voicemaster:rename")
    async def rename(self, interaction: Interaction, _: Button):
        """Rename your voice channel."""

        return await interaction.response.send_modal(Rename(self, interaction.user))

    @button(emoji=emojis.UPDATE_LIMIT, custom_id="voicemaster:update_limit")
    async def update_limit(self, interaction: Interaction, _: Button):
        """Update the user limit of your voice channel."""

        return await interaction.response.send_modal(
            UpdateLimit(self, interaction.user)
        )

    @button(emoji=emojis.INFORMATION, custom_id="voicemaster:information")
    async def information(self, interaction: Interaction, _: Button):
        """View information about your voice channel."""

        channel = interaction.user.voice.channel
        embed = Embed(
            title=channel.name,
            description=f"Created {format_dt(channel.created_at, 'R')}\n>>> "
            + "\n".join(
                [
                    f"**Locked:** "
                    + (
                        "✅"
                        if channel.overwrites_for(
                            interaction.guild.default_role
                        ).connect
                        is False
                        else "❌"
                    ),
                    f"**Hidden:** "
                    + (
                        "✅"
                        if channel.overwrites_for(
                            interaction.guild.default_role
                        ).view_channel
                        is False
                        else "❌"
                    ),
                    f"**Bitrate:** `{channel.bitrate // 1000} kbps`",
                    f"**Members:** `{len(channel.members)}`"
                    + (f"/`{channel.user_limit}`" if channel.user_limit else ""),
                ]
            ),
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar,
        )

        overwrites = {
            target: overwrite
            for target, overwrite in channel.overwrites.items()
            if overwrite.connect is True
            and target not in {interaction.guild.default_role, interaction.guild.me}
        }

        if roles_permitted := {role for role in overwrites if isinstance(role, Role)}:
            embed.add_field(
                name="**Roles Permitted**",
                value=", ".join(role.mention for role in roles_permitted),
                inline=False,
            )

        if members_permitted := {
            member for member in overwrites if isinstance(member, Member)
        }:
            embed.add_field(
                name="**Members Permitted**",
                value=", ".join(member.mention for member in members_permitted),
                inline=False,
            )

        return await interaction.response.send_message(embed=embed, ephemeral=True)

    @button(emoji=emojis.DELETE, custom_id="voicemaster:delete")
    async def delete(self, interaction: Interaction, _: Button):
        """Delete your voice channel."""

        await interaction.user.voice.channel.delete()
        return await self.send_response(
            interaction,
            "Your voice channel has been deleted",
        )


class Rename(Modal, title="Rename your voice channel"):
    panel: Panel
    user: MemberInVoice

    name = TextInput(
        label="New name",
        placeholder="Enter a new name for your voice channel",
        max_length=100,
    )

    def __init__(self, panel: Panel, user: MemberInVoice) -> None:
        super().__init__()
        self.panel = panel
        self.user = user
        self.interaction_check = panel.interaction_check  # type: ignore

    async def on_submit(self, interaction: Interaction) -> None:
        channel = interaction.user.voice.channel
        try:
            await channel.edit(
                name=self.name.value,
                reason=f"{interaction.user} renamed the channel",
            )
        except RateLimited as exc:
            return await self.panel.send_response(
                interaction,
                "Your voice channel has reached its rate limit",
            )
        except HTTPException:
            return await self.panel.send_response(
                interaction,
                "The channel name provided wasn't able to be set\n"
                "Make sure the name doesn't contain vulgar language",
            )

        return await self.panel.send_response(
            interaction, "Your voice channel has been renamed"
        )


class UpdateLimit(Modal, title="Update the user limit"):
    panel: Panel
    user: MemberInVoice

    limit = TextInput(
        label="New user limit",
        placeholder="Enter a new user limit for your voice channel",
        max_length=2,
    )

    def __init__(self, panel: Panel, user: MemberInVoice) -> None:
        super().__init__()
        self.panel = panel
        self.user = user
        self.interaction_check = panel.interaction_check  # type: ignore

    async def on_submit(self, interaction: Interaction) -> None:
        if not self.limit.value.isdigit():
            return await self.panel.send_response(
                interaction,
                "The user limit provided wasn't able to be set\n"
                "Make sure the limit is a number",
            )

        limit = int(self.limit.value)
        channel = interaction.user.voice.channel
        await channel.edit(user_limit=max(0, min(99, limit)))

        return await self.panel.send_response(
            interaction,
            (
                f"Your voice channel now has a limit of {plural(limit, '`'):user}"
                if limit
                else "Removed the user limit from your voice channel"
            ),
        )


class Disconnect(Select):
    panel: Panel
    user: MemberInVoice

    def __init__(self, panel: Panel, user: MemberInVoice) -> None:
        self.panel = panel
        self.user = user
        self.channel = user.voice.channel
        super().__init__(
            placeholder="Choose members...",
            min_values=1,
            max_values=len(self.channel.members),
            options=[
                SelectOption(
                    value=str(member.id),
                    label=f"{member} ({member.id})",
                    emoji="👤",
                )
                for member in self.channel.members
            ],
        )
        self.interaction_check = panel.interaction_check  # type: ignore

    async def callback(self, interaction: Interaction):
        await interaction.response.defer()

        disconnected, failed = 0, 0
        members = [
            member
            for member_id in self.values
            if (member := interaction.guild.get_member(int(member_id)))
            if member != self.user
        ]
        for member in members:
            if not member.voice or member.voice.channel != self.channel:
                failed += 1
                continue

            try:
                await member.move_to(None)
            except:
                failed += 1
            else:
                disconnected += 1

        embed = Embed(
            description=f"Disconnected {plural(disconnected, '`'):member}"
            + (f" `{failed}` failed" if failed else "")
            + "\n".join([f"> {member.mention} [`{member.id}`]" for member in members]),
        )
        return await interaction.followup.send(embed=embed, ephemeral=True)