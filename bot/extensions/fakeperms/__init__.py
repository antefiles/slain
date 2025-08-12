import discord
from functools import wraps
from discord import Embed, Role, Member
from datetime import datetime, timezone
from discord.ext.commands import has_permissions, Cog, group, Context, has_guild_permissions
from discord.ext import commands
from bot.core import Bot
from cashews import cache
from types import SimpleNamespace
from ...shared.formatter import compact_number
from ...shared.paginator import Paginator
from ..embeds import replace_vars, build_embed_from_raw
from bot.shared.fakeperms import hybrid_permissions

DISCORD_PERMISSIONS = {
    'create_instant_invite', 'kick_members', 'ban_members', 'administrator',
    'manage_channels', 'manage_guild', 'add_reactions', 'view_audit_log',
    'priority_speaker', 'stream', 'view_channel', 'send_messages',
    'send_tts_messages', 'manage_messages', 'embed_links', 'attach_files',
    'read_message_history', 'mention_everyone', 'use_external_emojis',
    'view_guild_insights', 'connect', 'speak', 'mute_members',
    'deafen_members', 'move_members', 'use_vad', 'change_nickname',
    'manage_nicknames', 'manage_roles', 'manage_webhooks', 'manage_emojis',
    'use_application_commands', 'request_to_speak', 'manage_events',
    'manage_threads', 'create_public_threads', 'create_private_threads',
    'send_messages_in_threads', 'use_embedded_activities', 'moderate_members',
    'use_soundboard', 'use_external_sounds', 'send_voice_messages'
}


class Fakeperms(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def has_fake_permission(self, guild_id: int, member: Member, perm: str) -> bool:
        if perm not in DISCORD_PERMISSIONS:
            return False
        role_ids = [r.id for r in member.roles]
        if not role_ids:
            return False
        query = """
        SELECT 1 FROM fake_permissions
        WHERE guild_id = $1 AND permission = $2
        AND role_id = ANY($3::BIGINT[])
        LIMIT 1;
        """
        return await self.bot.pool.fetchval(query, guild_id, perm, role_ids) is not None


    @commands.group(name="fakepermissions", aliases=["fakeperms"], usage='fakepermissions', invoke_without_command=True)
    @has_guild_permissions(administrator=True)
    async def fakepermissions(self, ctx: Context):
        """
        Allow fake permissions on roles through the bot
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @fakepermissions.command(name="create", usage='fakepermissions create [role]')
    @has_guild_permissions(administrator=True)
    async def fake_create(self, ctx: Context, role: Role):
        """
        Create a role to be used for fake permissions
        """
        if ctx.guild.me.top_role.position <= role.position:
            return await ctx.warn(f"I cannot modify the role {role.mention} because it is higher or equal to my top role")

        if ctx.author.id != ctx.guild.owner_id:
            if role.position >= ctx.author.top_role.position:
                return await ctx.warn(f"You cannot modify a role with **fake permissions** that is the same or higher than your top role.")

        exists = await self.bot.pool.fetchval(
            "SELECT TRUE FROM fake_permissions WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id
        )
        if exists:
            return await ctx.warn(f"{role.mention} already has **fake permissions**")
        
        await self.bot.pool.execute(
            "INSERT INTO fake_permissions (guild_id, role_id, permission, added_by) VALUES ($1, $2, 'manage_messages', $3)",
            ctx.guild.id, role.id, ctx.author.id
        )
        await ctx.approve(f"{role.mention} is now ready for **fake permissions**")

    @fakepermissions.command(name="delete", usage='fakepermissions delete [role]')
    @has_guild_permissions(administrator=True)
    async def fake_delete(self, ctx: Context, role: Role):
        """
        Delete a role previously created for fake permissions
        """
        if ctx.guild.me.top_role.position <= role.position:
            return await ctx.warn(f"I cannot modify the role {role.mention} because it is higher or equal to my top role.")
        
        if ctx.author.id != ctx.guild.owner_id:
            if role.position >= ctx.author.top_role.position:
                return await ctx.warn(f"You cannot modify a role with **fake permissions** that is the same or higher than your top role")

        exists = await self.bot.pool.fetchval(
            "SELECT 1 FROM fake_permissions WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id
        )

        if not exists:
            return await ctx.warn(f"{role.mention} was never setup with **fake permissions**")

        await self.bot.pool.execute(
            "DELETE FROM fake_permissions WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id
        )
        await ctx.approve(f"Fake permissions removed for {role.mention}")


    @fakepermissions.command(name="add", usage='fakepermissions add [role] [permission], +more')
    @has_guild_permissions(administrator=True)
    async def fake_add(self, ctx: Context, role: Role, *permissions: str):
        """
        Add fake permissions to a role created for fake permissions
        """
        if ctx.guild.me.top_role.position <= role.position:
            return await ctx.warn(f"I cannot modify the role {role.mention} because it is higher or equal to my top role")

        if ctx.author.id != ctx.guild.owner_id:
            if role.position >= ctx.author.top_role.position:
                return await ctx.warn(f"You cannot modify a role with **fake permissions** that is the same or higher than your top role")

        exists = await self.bot.pool.fetchval(
            "SELECT TRUE FROM fake_permissions WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id
        )
        if not exists:
            return await ctx.warn(f"{role.mention} must have **fakepermissions setup** for that role")
        flat_perms = []
        for perm_group in permissions:
            flat_perms.extend(p.strip() for p in perm_group.split(",") if p.strip())

        if not flat_perms:
            return await ctx.warn("Provide at least one permission to add")

        added = []
        for perm in flat_perms:
            if perm not in DISCORD_PERMISSIONS:
                continue
            await self.bot.pool.execute(
                """
                INSERT INTO fake_permissions (guild_id, role_id, permission, added_by)
                VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
                """,
                ctx.guild.id, role.id, perm, ctx.author.id
            )
            added.append(perm)

        if not added:
            return await ctx.warn("No valid permissions were added.")

        shown = added[:2]
        extra_count = len(added) - len(shown)
        message = f"Added `{', '.join(shown)}`"
        if extra_count > 0:
            message += f" +{extra_count} more"
        message += f" **fake permissions** to {role.mention}"

        await ctx.approve(message)

    @fakepermissions.command(name="remove", usage='fakepermissions remove [role] [permission]')
    @has_guild_permissions(administrator=True)
    async def fake_remove(self, ctx: Context, role: Role, *permissions: str):
        """
        Remove a fake permission from a role
        """
        if ctx.guild.me.top_role.position <= role.position:
            return await ctx.warn(f"I cannot modify the role {role.mention} because it is higher or equal to my top role.")

        if not permissions:
            return await ctx.warn("Provide at least one permission to remove")

        flat_perms = []
        for perm_group in permissions:
            flat_perms.extend(p.strip() for p in perm_group.split(",") if p.strip())

        removed = []
        for perm in flat_perms:
            if perm not in DISCORD_PERMISSIONS:
                continue
            await self.bot.pool.execute(
                "DELETE FROM fake_permissions WHERE guild_id = $1 AND role_id = $2 AND permission = $3",
                ctx.guild.id, role.id, perm
            )
            removed.append(perm)

        if not removed:
            return await ctx.warn("No valid permissions were removed.")

        shown = removed[:2]
        extra_count = len(removed) - len(shown)
        message = f"Removed `{', '.join(shown)}`"
        if extra_count > 0:
            message += f" +{extra_count} more"
        message += f" **fake permissions** from {role.mention}"

        await ctx.approve(message)


    @fakepermissions.command(name="view", usage='fakepermissions view [role]')
    @has_guild_permissions(administrator=True)
    async def fake_view(self, ctx: Context, role: Role):
        """
        View a roles fake permissions
        """
        rows = await self.bot.pool.fetch(
            "SELECT permission FROM fake_permissions WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id
        )
        if not rows:
            return await ctx.warn(f"{role.mention} has no **fake permissions**")

        perms = [r["permission"] for r in rows]
        embed = discord.Embed(
            title=f"<:mod_action:1391451706260197479> Fake Permissions",
            description=f"**Role:** {role.mention}",
            color=0xacacac
        )
        embed.add_field(
            name="Permissions:",
            value=f"```{', '.join(perms)}```" if perms else "No permissions found",
            inline=False
        )
        await ctx.send(embed=embed)

    @fakepermissions.command(name="roles", usage='fakepermissions roles')
    @has_guild_permissions(administrator=True)
    async def fake_roles(self, ctx: Context):
        """
        View all roles currently setup to use fake permissions
        """
        rows = await self.bot.pool.fetch(
            """
            SELECT role_id, added_by, MIN(added_at) AS since
            FROM fake_permissions
            WHERE guild_id = $1
            GROUP BY role_id, added_by
            ORDER BY since DESC
            """,
            ctx.guild.id
        )
        if not rows:
            return await ctx.warn("No roles have fake permissions")

        lines = []
        for i, row in enumerate(rows, 1):
            role = ctx.guild.get_role(row["role_id"])
            added_by = f"<@{row['added_by']}>" if row["added_by"] else "Unknown"
            timestamp = int(row["since"].timestamp())
            since = f"<t:{timestamp}:R>"
            if role:
                lines.append(f"{role.mention} • added by {added_by} • {since}")

        embed = discord.Embed(
            title="<:slain_Settings:1391058914816167996> Fake Permission Roles",
            color=0xacacac
        )

        view = Paginator(ctx, lines, embed=embed, per_page=10)
        await view.start()


async def setup(bot: Bot) -> None:
    await bot.add_cog(Fakeperms(bot))