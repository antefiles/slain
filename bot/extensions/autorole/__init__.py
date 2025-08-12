import discord
import asyncio, re, difflib
from discord import Member, Role
from bot.core import Bot
from discord.ext import commands
from discord.ext.commands import Cog, command, group, Context
from bot.shared.fakeperms import hybrid_permissions
from datetime import datetime


class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_queues = {}
        self.bot.loop.create_task(self.queue_loop())

    async def queue_loop(self):
        while True:
            await asyncio.sleep(0.1)
            for guild_id, queue in list(self.guild_queues.items()):
                if queue.empty():
                    continue
                member = await queue.get()
                try:
                    rows = await self.bot.pool.fetch(
                        "SELECT role_id FROM autoroles WHERE guild_id = $1", guild_id
                    )
                    to_remove = []
                    role_count = 0
                    for row in rows:
                        role = member.guild.get_role(row["role_id"])
                        if not role or role >= member.guild.me.top_role:
                            to_remove.append(row["role_id"])
                            continue
                        if (
                            not role.managed
                            and not role.is_bot_managed()
                            and role < member.guild.me.top_role
                        ):
                            try:
                                await member.add_roles(role, reason="AutoRole")
                                await asyncio.sleep(0.25)
                                role_count += 1
                            except Exception:
                                continue
                    for rid in to_remove:
                        await self.bot.pool.execute(
                            "DELETE FROM autoroles WHERE guild_id = $1 AND role_id = $2",
                            guild_id, rid
                        )
                    await asyncio.sleep(max(0.75, role_count * 0.25))
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        if member.guild.id not in self.guild_queues:
            self.guild_queues[member.guild.id] = asyncio.Queue()
        await self.guild_queues[member.guild.id].put(member)

    @group(name="autorole", usage='autorole', invoke_without_command=True)
    async def autorole(self, ctx: commands.Context):
        """
        Add a role to be auto assigned to new members
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @autorole.command(name="add", usage="autorole add [role]")
    @hybrid_permissions(manage_roles=True)
    async def autorole_add(self, ctx: commands.Context, *, role: str):
        """
        Add a role to be auto assigned to new members
        """
        match = re.match(r"<@&(\d+)>", role)
        if match:
            role_obj = ctx.guild.get_role(int(match.group(1)))
        else:
            roles = [r for r in ctx.guild.roles if not r.is_bot_managed()]
            matches = difflib.get_close_matches(role.lower(), [r.name.lower() for r in roles], n=1, cutoff=0.6)
            role_obj = next((r for r in roles if r.name.lower() == matches[0]), None) if matches else None

        if not role_obj:
            return await ctx.warn("No matching role was found")

        if role_obj.managed:
            return await ctx.warn("You cannot auto assign an **integration-managed role**")

        if role_obj.is_bot_managed():
            return await ctx.warn("You cannot auto assign a **bot-managed role**")

        if role_obj.is_premium_subscriber():
            return await ctx.warn("You cannot auto assign the **Nitro Booster role**")

        if role_obj >= ctx.guild.me.top_role:
            return await ctx.warn(f"I cannot manage {role_obj.mention} because it is **higher or equal** to my top role")

        perms = role_obj.permissions
        if perms.administrator or perms.manage_guild:
            return await ctx.warn("You cannot auto assign roles with **Administrator** or **Manage Server** permissions")

        existing_roles = await self.bot.pool.fetch(
            "SELECT role_id FROM autoroles WHERE guild_id = $1",
            ctx.guild.id
        )
        if any(row["role_id"] == role_obj.id for row in existing_roles):
            return await ctx.warn(f"{role_obj.mention} is **already** being auto assigned")

        if len(existing_roles) >= 5:
            return await ctx.warn("You can only auto assign up to **5 roles** per server")

        await self.bot.pool.execute(
            "INSERT INTO autoroles (guild_id, role_id, added_by, added_at) VALUES ($1, $2, $3, $4)",
            ctx.guild.id, role_obj.id, ctx.author.id, datetime.utcnow()
        )

        await ctx.approve(f"{role_obj.mention} will now be **auto assigned** to new members")

    @autorole.command(name="list", usage="autorole list")
    @hybrid_permissions(manage_roles=True)
    async def autorole_list(self, ctx: Context):
        """
        View all roles set to be given to users on join
        """
        rows = await self.bot.pool.fetch(
            "SELECT role_id, added_by, added_at FROM autoroles WHERE guild_id = $1",
            ctx.guild.id
        )

        if not rows:
            return await ctx.warn("No **auto assigned roles** found")

        lines = []
        for i, row in enumerate(rows, start=1):
            role = ctx.guild.get_role(row["role_id"])
            added_by = ctx.guild.get_member(row["added_by"])
            user_display = added_by.mention if added_by else f"<@{row['added_by']}>"
            timestamp = f"<t:{int(row['added_at'].timestamp())}:R>" if row["added_at"] else "Unknown time"

            if role:
                line = f"`{i}.` {role.mention} - added by {user_display} - {timestamp}"
                lines.append(line)

        embed = discord.Embed(
            title="<:slain_Settings:1391058914816167996> Auto Assigned Roles",
            description="\n".join(lines),
            color=0xacacac
        )
        await ctx.send(embed=embed)

    @autorole.command(name="remove", usage="autorole remove [role]")
    @hybrid_permissions(manage_roles=True)
    async def autorole_remove(self, ctx: Context, *, role: str):
        """
        Remove a role from being auto-assigned to new members.
        """
        match = re.match(r"<@&(\d+)>", role)
        if match:
            role_obj = ctx.guild.get_role(int(match.group(1)))
        else:
            roles = [r for r in ctx.guild.roles if not r.is_bot_managed()]
            matches = difflib.get_close_matches(role.lower(), [r.name.lower() for r in roles], n=1, cutoff=0.6)
            role_obj = next((r for r in roles if r.name.lower() == matches[0]), None) if matches else None

        if not role_obj:
            return await ctx.warn("No matching role was found")

        row = await self.bot.pool.fetchrow(
            "SELECT 1 FROM autoroles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role_obj.id
        )

        if not row:
            return await ctx.warn(f"{role_obj.mention} is not currently being auto-assigned")

        await self.bot.pool.execute(
            "DELETE FROM autoroles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role_obj.id
        )

        await ctx.approve(f"{role_obj.mention} has been removed from auto-assigned roles")

    @autorole.command(name="reset", usage="autorole reset")
    @hybrid_permissions(manage_roles=True)
    async def autorole_reset(self, ctx: Context):
        """
        Clear all roles currently set to be auto-assigned.
        """
        count = await self.bot.pool.fetchval(
            "SELECT COUNT(*) FROM autoroles WHERE guild_id = $1",
            ctx.guild.id
        )

        if not count:
            return await ctx.warn("There are no **auto-assigned roles** to reset")

        await self.bot.pool.execute(
            "DELETE FROM autoroles WHERE guild_id = $1",
            ctx.guild.id
        )

        await ctx.approve(f"Removed all **{count}** auto-assigned role(s) for this server")


async def setup(bot):
    await bot.add_cog(AutoRole(bot))