from discord.ext.commands import Cog, command, group, Context
from bot.core import Bot
import discord, re
from cashews import cache
from datetime import datetime, timezone, timedelta
from ...shared.paginator import Paginator
from typing import Optional, Union
from discord.ext.commands import has_permissions, CheckFailure, cooldown, CooldownMapping, BucketType, CommandOnCooldown
from discord.ext import commands
import json, humanize
from bot.shared.fakeperms import hybrid_permissions


def parse_duration(input: str) -> Optional[timedelta]:
    input = input.lower().strip()

    units = {
        "s": ["s", "sec", "secs", "second", "seconds"],
        "m": ["m", "min", "mins", "minute", "minutes"],
        "h": ["h", "hr", "hrs", "hour", "hours"],
        "d": ["d", "day", "days"],
    }

    unit_map = {alias: base for base, aliases in units.items() for alias in aliases}
    pattern = r"(\d+)\s*([a-zA-Z]+)"
    matches = re.findall(pattern, input)

    if not matches:
        return None

    total = timedelta()
    for value, unit in matches:
        base_unit = unit_map.get(unit)
        if not base_unit:
            return None

        value = int(value)
        if base_unit == "s":
            total += timedelta(seconds=value)
        elif base_unit == "m":
            total += timedelta(minutes=value)
        elif base_unit == "h":
            total += timedelta(hours=value)
        elif base_unit == "d":
            total += timedelta(days=value)

    return total if total.total_seconds() > 0 else None

class Moderation(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @group(name="warn", usage='warn [user] [reason]', invoke_without_command=True)
    @hybrid_permissions(manage_messages=True)
    @cooldown(4, 10, BucketType.user)
    async def warn(self, ctx: Context, member: discord.Member, *, reason: str):
        """
        Warn a user for misbahaving
        """
        ctx.target_member = member
        
        if member.bot:
            return await ctx.warn("You can't warn bots.")

        if member.id == ctx.author.id:
            return await ctx.warn("You **cannot warn yourself**.")

        if member.id == ctx.guild.owner_id:
            return await ctx.warn("You **cannot warn** the server owner.")

        if ctx.author.id != ctx.guild.owner_id:
            # Prevent warning members with equal or higher roles
            if member.top_role >= ctx.author.top_role:
                return await ctx.warn(
                    f"{member.mention} **cannot be warned** because their top role is higher than or equal to yours."
                )

        # Prevent warning bypassed users
        is_bypassed = await self.bot.pool.fetchval(
            """
            SELECT TRUE FROM warn_bypass
            WHERE guild_id = $1 AND (user_id = $2 OR role_id = ANY($3::BIGINT[]))
            LIMIT 1
            """,
            ctx.guild.id,
            member.id,
            [r.id for r in member.roles],
        )
        if is_bypassed:
            return await ctx.warn(f"{member.mention} is **bypassed** and cannot be warned.")

        # Prevent warning exempted (whitelisted) users
        is_exempt = await self.bot.pool.fetchval(
            """
            SELECT TRUE FROM warn_exempt
            WHERE guild_id = $1 AND (user_id = $2 OR role_id = ANY($3::BIGINT[]))
            LIMIT 1
            """,
            ctx.guild.id,
            member.id,
            [r.id for r in member.roles],
        )
        if is_exempt:
            return await ctx.warn(f"{member.mention} is **exempt** from warnings.")

        await self._warn_user_job(ctx, member, reason)

    async def _warn_user_job(self, ctx: Context, member: discord.Member, reason: str):
        is_exempt = await self.bot.pool.fetchval(
            """
            SELECT TRUE FROM warn_exempt
            WHERE guild_id = $1 AND (user_id = $2 OR role_id = ANY($3::BIGINT[]))
            LIMIT 1
            """,
            ctx.guild.id,
            member.id,
            [role.id for role in member.roles],
        )
        if is_exempt:
            return await ctx.warn(f"{member.mention} is **exempt** from warnings")

        await self.bot.pool.execute(
            """
            INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
            VALUES ($1, $2, $3, $4)
            """,
            member.id,
            ctx.guild.id,
            ctx.author.id,
            reason,
        )

        message = await ctx.approve(f"{member.mention} has been warned: **{reason}**")

        warnings = await self.bot.pool.fetchval(
            """
            SELECT COUNT(*) FROM warnings
            WHERE user_id = $1 AND guild_id = $2
            """,
            member.id,
            ctx.guild.id
        )

        config = await self.bot.pool.fetchrow(
            """
            SELECT default_threshold, default_action, timeout_duration
            FROM warn_config WHERE guild_id = $1
            """,
            ctx.guild.id
        )

        if not config or not config["default_action"]:
            return

        threshold = config["default_threshold"]
        action = config["default_action"]
        timeout_duration = config["timeout_duration"] or timedelta(minutes=10)

        if warnings < threshold:
            return

        try:
            action_text = None

            if action == "timeout":
                await member.timeout(timeout_duration, reason=f"{threshold} warnings reached.")
                action_text = f"**timed out for {humanize.precisedelta(timeout_duration, format='%0.0f')}**"
            elif action == "kick":
                await member.kick(reason=f"{threshold} warnings reached.")
                action_text = "**kicked**"
            elif action == "ban":
                await ctx.guild.ban(member, reason=f"{threshold} warnings reached.", delete_message_days=0)
                action_text = "**banned**"

            # Clear their warnings
            await self.bot.pool.execute(
                "DELETE FROM warnings WHERE user_id = $1 AND guild_id = $2",
                member.id,
                ctx.guild.id
            )

            plural = "warning" if threshold == 1 else "warnings"
            new_desc = (
                f"<:mod_action:1391451706260197479> {member.mention} has been {action_text} for reaching **{threshold} {plural}**. Their warnings have now been reset."
            )
            embed = discord.Embed(description=new_desc, color=0xacacac)
            await message.edit(embed=embed)

        except discord.Forbidden:
            if member.guild_permissions.administrator or member.top_role >= ctx.guild.me.top_role:
                return
            await ctx.warn("I don't have permission to apply that punishment")


    @warn.command(name="bypassed", usage='warn bypassed')
    @hybrid_permissions(manage_messages=True)
    async def warn_bypassed(self, ctx: Context):
        """
        View users who can bypass warn restrictions
        """
        if ctx.author.id != ctx.guild.owner_id:
            is_bypassed = await self.bot.pool.fetchval(
                """
                SELECT TRUE FROM warn_bypass
                WHERE guild_id = $1 AND (
                    user_id = $2 OR role_id = ANY($3::BIGINT[])
                )
                LIMIT 1
                """,
                ctx.guild.id,
                ctx.author.id,
                [r.id for r in ctx.author.roles],
            )
            if not is_bypassed:
                return await ctx.warn("Only the **server owner** or a **bypassed user/role** can use this command.")

        rows = await self.bot.pool.fetch(
            """
            SELECT user_id, role_id, added_by, created_at
            FROM warn_bypass
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        )

        if not rows:
            return await ctx.warn("No users or roles are bypassed from warning restrictions.")

        lines = []
        for i, row in enumerate(rows):
            target_id = row["user_id"] or row["role_id"]
            target = ctx.guild.get_member(target_id) or ctx.guild.get_role(target_id)
            display = target.mention if target else f"<@{target_id}>"

            added_by = f"<@{row['added_by']}>" if row.get("added_by") else "Unknown"
            timestamp = row["created_at"]
            when = f"<t:{int(timestamp.timestamp())}:R>" if timestamp else "Unknown"

            lines.append(f"`{i + 1}.` {display} - added by {added_by} → {when}")

        embed = discord.Embed(
            title="<:slain_Settings:1391058914816167996> Bypassed Users & Roles",
            color=0xacacac
        )

        if len(lines) > 10:
            lines = [line.replace(f"`{i + 1}.` ", "") for i, line in enumerate(lines)]
            paginator = Paginator(ctx, lines, embed=embed, per_page=10, counter=True)
            return await paginator.start()

        embed.description = "\n".join(f"> {line}" for line in lines)
        await ctx.send(embed=embed)


    @warn.command(name="bypass", usage='warn bypass [user]')
    @cooldown(5, 10, BucketType.user)
    @hybrid_permissions(manage_messages=True)
    async def warn_bypass(self, ctx: Context, target: Optional[Union[discord.Member, discord.Role]] = None):
        """
        Allow a user to bypass warn restrictions
        """
        if not target:
            return await ctx.warn("Please mention a **user** or **role** to toggle bypass status.")

        if ctx.author != ctx.guild.owner:
            return await ctx.warn("Only the **server owner** can manage bypasses.")

        if isinstance(target, discord.Member):
            if target.id == ctx.guild.owner_id:
                return await ctx.warn("You **cannot bypass or unbypass** the server owner.")

            exists = await self.bot.pool.fetchval(
                "SELECT TRUE FROM warn_bypass WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, target.id
            )
            if exists:
                await self.bot.pool.execute(
                    "DELETE FROM warn_bypass WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id, target.id
                )
                return await ctx.approve(f"{target.mention} is no longer allowed to bypass warning restrictions.")
            else:
                await self.bot.pool.execute(
                    """
                    INSERT INTO warn_bypass (guild_id, user_id, added_by, created_at)
                    VALUES ($1, $2, $3, NOW())
                    """,
                    ctx.guild.id, target.id, ctx.author.id
                )
                return await ctx.approve(f"{target.mention} can now **bypass** warning restrictions.")

        elif isinstance(target, discord.Role):
            exists = await self.bot.pool.fetchval(
                "SELECT TRUE FROM warn_bypass WHERE guild_id = $1 AND role_id = $2",
                ctx.guild.id, target.id
            )
            if exists:
                await self.bot.pool.execute(
                    "DELETE FROM warn_bypass WHERE guild_id = $1 AND role_id = $2",
                    ctx.guild.id, target.id
                )
                return await ctx.approve(f"{target.mention} is no longer allowed to bypass warning restrictions.")
            else:
                await self.bot.pool.execute(
                    """
                    INSERT INTO warn_bypass (guild_id, role_id, added_by, created_at)
                    VALUES ($1, $2, $3, NOW())
                    """,
                    ctx.guild.id, target.id, ctx.author.id
                )
                return await ctx.approve(f"{target.mention} can now **bypass** warning restrictions.")



    async def check_warn_punishment(self, ctx: Context, member: discord.Member) -> None:
        guild_id = ctx.guild.id
        user_id = member.id

        role_configs = await self.bot.pool.fetch(
            """
            SELECT role_id, threshold, action, timeout_duration
            FROM warn_role_config
            WHERE guild_id = $1
            """,
            guild_id,
        )

        matched_config = None
        for row in role_configs:
            if any(role.id == row["role_id"] for role in member.roles):
                if matched_config is None or row["threshold"] <= matched_config["threshold"]:
                    matched_config = row

        if not matched_config:
            config = await self.bot.pool.fetchrow(
                """
                SELECT default_threshold AS threshold, default_action AS action, timeout_duration
                FROM warn_config
                WHERE guild_id = $1
                """,
                guild_id,
            )
            if not config or config["action"] is None:
                return 
            matched_config = config

        warning_count = await self.bot.pool.fetchval(
            """
            SELECT COUNT(*)
            FROM warnings
            WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if warning_count < matched_config["threshold"]:
            return  

        action = matched_config["action"]
        timeout_duration = matched_config["timeout_duration"]

        try:
            if action == "timeout":
                until = discord.utils.utcnow() + timeout_duration
                await member.timeout(until, reason="Warn threshold reached")
                await ctx.approve(f"{member.mention} has been **timed out** for reaching **{warning_count} warnings**")
            elif action == "kick":
                await member.kick(reason="Warn threshold reached")
                await ctx.approve(f"{member.mention} has been **kicked** for reaching **{warning_count} warnings**")
            elif action == "ban":
                await member.ban(reason="Warn threshold reached", delete_message_days=0)
                await ctx.approve(f"{member.mention} has been **banned** for reaching **{warning_count} warnings**")
        except discord.Forbidden:
            await ctx.warn(f"I don’t have permission to {action} {member.mention}.")
        except discord.HTTPException:
            await ctx.warn(f"Failed to {action} {member.mention}")

    @warn.command(name="threshold", usage='warn threshold [amount]')
    @cooldown(2, 10, BucketType.user)
    @hybrid_permissions(manage_messages=True)
    async def warn_set_threshold(self, ctx: Context, amount: int):
        """
        Set an amount of times a user can be warned before being punished
        """
        if ctx.author.id != ctx.guild.owner_id:
            is_bypasser = await self.bot.pool.fetchval(
                """
                SELECT TRUE FROM warn_bypass
                WHERE guild_id = $1 AND (
                    user_id = $2 OR role_id = ANY($3::BIGINT[])
                )
                LIMIT 1
                """,
                ctx.guild.id,
                ctx.author.id,
                [r.id for r in ctx.author.roles],
            )
            if not is_bypasser:
                return await ctx.warn("Only the **server owner** or a **bypassed user/role** can set the threshold.")

        if amount < 2:
            return await ctx.warn("Threshold must be at least 2 warnings.")
        
        config = await self.bot.pool.fetchrow(
            """
            SELECT default_action, timeout_duration, default_threshold
            FROM warn_config
            WHERE guild_id = $1
            """,
            ctx.guild.id
        )
        if not config or not config["default_action"]:
            return await ctx.warn("You must set a **punishment** before setting the threshold.")
        
        if config["default_threshold"] == amount:
            return await ctx.warn(f"The punishment threshold is already set to **{amount}** warnings.")

        await self.bot.pool.execute(
            """
            UPDATE warn_config
            SET default_threshold = $1
            WHERE guild_id = $2
            """,
            amount,
            ctx.guild.id
        )

        action = config["default_action"]
        if action == "timeout":
            duration = config["timeout_duration"] or 1800
            delta = duration if isinstance(duration, timedelta) else timedelta(seconds=duration)
            human_time = humanize.precisedelta(delta, minimum_unit="seconds")
            punishment_str = f"timed out for {human_time}"
        elif action == "kick":
            punishment_str = "kicked"
        elif action == "ban":
            punishment_str = "banned"
        else:
            punishment_str = "punished"

        await ctx.approve(
            f"Users will now be warned **{amount}** time{'s' if amount != 1 else ''} before they are **{punishment_str}**"
        )


    @warn.command(name="config", usage='warn config')
    @cooldown(2, 10, BucketType.user)
    @hybrid_permissions(manage_messages=True)
    async def warn_punishment_view(self, ctx: Context):
        """
        View the warning configuration of the set punishment and threshold
        """
        config = await self.bot.pool.fetchrow(
            """
            SELECT default_action, timeout_duration, default_threshold
            FROM warn_config
            WHERE guild_id = $1
            """,
            ctx.guild.id
        )
        if not config or not config["default_action"]:
            return await ctx.warn(
                f"No punishment is currently configured\n-# *use **{ctx.clean_prefix}warn punishment** to set one*"
            )

        action = config["default_action"]
        threshold = config["default_threshold"]
        timeout = config["timeout_duration"]
        duration = (
            f" for **{humanize.precisedelta(timeout, format='%0.0f')}**"
            if action == "timeout" and timeout else ""
        )

        message = f"Current punishment is set to `{action}`{duration} after **{threshold} warning{'s' if threshold != 1 else ''}**"
        await ctx.config(message)

    @warn.command(name="clearall", usage='warn clearall [user]')
    @hybrid_permissions(manage_messages=True)
    async def warn_clear(self, ctx: Context, member: discord.Member):
        """
        Clear all warnings for a user
        """
        ctx.target_member = member
        
        result = await self.bot.pool.execute(
            """
            DELETE FROM warnings
            WHERE user_id = $1 AND guild_id = $2
            """,
            member.id,
            ctx.guild.id
        )
        count = int(result.split()[-1])
        await ctx.approve(f"Cleared {count} warning{'s' if count != 1 else ''} for {member.mention}")


    @warn.command(name="clearguild", usage='warn clearguild')
    @cooldown(1, 10, BucketType.user)
    @hybrid_permissions(manage_messages=True)
    async def warn_clear_guild(self, ctx: Context):
        """
        Clear all warnings for your server members
        """
        if ctx.author.id != ctx.guild.owner_id:
            is_bypasser = await self.bot.pool.fetchval(
                """
                SELECT TRUE FROM warn_bypass
                WHERE guild_id = $1 AND (
                    user_id = $2 OR role_id = ANY($3::BIGINT[])
                )
                LIMIT 1
                """,
                ctx.guild.id,
                ctx.author.id,
                [r.id for r in ctx.author.roles],
            )
            if not is_bypasser:
                return await ctx.warn("Only the **server owner** or a **bypassed user/role** can use this command.")

        row = await self.bot.pool.fetchrow(
            """
            SELECT COUNT(*) AS total, COUNT(DISTINCT user_id) AS users
            FROM warnings
            WHERE guild_id = $1
            """,
            ctx.guild.id
        )
        total = row["total"]
        users = row["users"]

        await self.bot.pool.execute(
            "DELETE FROM warnings WHERE guild_id = $1",
            ctx.guild.id
        )

        await ctx.approve(
            f"Cleared {total} warning{'s' if total != 1 else ''} for {users} user{'s' if users != 1 else ''}"
        )

    @warn.command(name="remove", usage='warn remove [user] [number]')
    @hybrid_permissions(manage_messages=True)
    async def warn_remove(self, ctx: Context, member: discord.Member, index: int):
        """
        Remove a warning from a users warnings list
        """
        ctx.target_member = member
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn(f"{member.mention} **warnings cannot be modified** because their top role is higher than or equal to yours")

        rows = await self.bot.pool.fetch(
            """
            SELECT id FROM warnings
            WHERE user_id = $1 AND guild_id = $2
            ORDER BY timestamp
            """,
            member.id,
            ctx.guild.id
        )

        if index < 1 or index > len(rows):
            return await ctx.warn("That numbered warning does not exist.")

        warning_id = rows[index - 1]["id"]

        await self.bot.pool.execute(
            "DELETE FROM warnings WHERE id = $1",
            warning_id
        )

        await ctx.approve(f"Removed warning **#{index}** for {member.mention}.")


    @command(name="warnings", usage='warnings [optional: user]')
    @hybrid_permissions(manage_messages=True)
    async def view_warnings(self, ctx: Context, member: Optional[discord.Member] = None):
        """
        View a users warnings or recently warned users
        """
        if member:
            ctx.target_member = member
            
        if member is None:
            rows = await self.bot.pool.fetch(
                """
                SELECT user_id, MAX(timestamp) AS last_warned
                FROM warnings
                WHERE guild_id = $1
                GROUP BY user_id
                ORDER BY last_warned DESC
                LIMIT 3
                """,
                ctx.guild.id
            )

            if not rows:
                return await ctx.warn("No users have been warned in this server")

            description = ""
            for idx, row in enumerate(rows, 1):
                user = ctx.guild.get_member(row["user_id"]) or f"<@{row['user_id']}>"
                unix_timestamp = int(row["last_warned"].timestamp())
                description += f"> `{idx}.` {user} - <t:{unix_timestamp}:R>\n"

            embed = discord.Embed(
                title="<:mod_action:1391451706260197479> Recently Warned Users",
                description=description.strip(),
                color=0xacacac
            )
            return await ctx.send(embed=embed)

        rows = await self.bot.pool.fetch(
            """
            SELECT moderator_id, reason, timestamp
            FROM warnings
            WHERE user_id = $1 AND guild_id = $2
            ORDER BY timestamp DESC
            """,
            member.id,
            ctx.guild.id
        )

        if not rows:
            return await ctx.warn(f"{member.mention} has no warnings")

        entries = []
        total = len(rows)
        for idx, row in enumerate(rows, 1):
            case_number = total - idx + 1
            dt = row["timestamp"]
            date = dt.strftime("%B %d, %Y")
            entries.append(
                f"__Case {case_number}__:\n"
                f"> **Date:** {date}\n"
                f"> **Reason:** {row['reason']}\n"
                f"> **Moderator:** <@{row['moderator_id']}>\n"
            )

        embed = discord.Embed(
            title=f"<:mod_action:1391451706260197479> Warning History for {member.name}",
            color=0xacacac
        )
        paginator = Paginator(ctx, entries, embed=embed, per_page=5, counter=False)
        await paginator.start()

    @warn.command(name="punishment", usage='warn punishment [ban, kick or timeout (time)]')
    @hybrid_permissions(manage_messages=True)
    async def warn_set_punishment(self, ctx: Context, action: str, *, duration: Optional[str] = None):
        """
        Set a punishment users will recieve after reaching the threshold of warnings
        """
        if ctx.author.id != ctx.guild.owner_id:
            is_bypasser = await self.bot.pool.fetchval(
                """
                SELECT TRUE FROM warn_bypass
                WHERE guild_id = $1 AND (
                    user_id = $2 OR role_id = ANY($3::BIGINT[])
                )
                LIMIT 1
                """,
                ctx.guild.id,
                ctx.author.id,
                [r.id for r in ctx.author.roles],
            )
            if not is_bypasser:
                return await ctx.warn("Only the **server owner** or a **bypassed user/role** can use this command.")

        action_lower = action.lower()
        valid_actions = ("timeout", "kick", "ban", "none")
        if action_lower not in valid_actions:
            return await ctx.warn("Punishment must be `timeout`, `kick`, `ban`, or `none`")

        timeout_interval = None
        if action_lower == "timeout":
            if not duration:
                return await ctx.warn("You must provide a duration for timeouts")

            timeout_interval = parse_duration(duration)
            if not timeout_interval:
                return await ctx.warn("Invalid duration format. Use formats like `1d`, `2h`, `30m`")

        record = await self.bot.pool.fetchrow(
            "SELECT default_action, timeout_duration FROM warn_config WHERE guild_id = $1",
            ctx.guild.id
        )

        existing_action = record["default_action"] if record else None
        existing_duration = record["timeout_duration"] if record else None

        if (
            (existing_action or "none") == (None if action_lower == "none" else action_lower)
            and (action_lower != "timeout" or timeout_interval == existing_duration)
        ):
            if action_lower == "timeout":
                return await ctx.warn(f"Punishment is already set to `timeout` with a duration of `{duration}`")
            elif action_lower == "none":
                return await ctx.warn("Punishment is already disabled")
            else:
                return await ctx.warn(f"Punishment is already set to {action_lower}")

        await self.bot.pool.execute(
            """
            INSERT INTO warn_config (guild_id, default_action, timeout_duration)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
            SET default_action = EXCLUDED.default_action,
                timeout_duration = EXCLUDED.timeout_duration
            """,
            ctx.guild.id,
            None if action_lower == "none" else action_lower,
            timeout_interval
        )

        response = (
            f"Punishment disabled"
            if action_lower == "none"
            else f"Punishment set to `{action_lower}`" +
                (f" with duration `{duration}`" if action_lower == "timeout" else "")
        )

        await ctx.approve(response)

    @warn.command(name="whitelist", usage='warn whitelist [user or role]')
    @cooldown(5, 10, BucketType.user)
    @hybrid_permissions(manage_messages=True)
    async def warn_whitelist(self, ctx: Context, target: Optional[str] = None):
        """
        Prevent a user or users with a role from being warned
        """
        if not target:
            return await ctx.warn("Please provide a **user** or **role** to toggle whitelist status.")

        member = None
        role = None

        try:
            member = await commands.MemberConverter().convert(ctx, target)
        except commands.BadArgument:
            try:
                role = await commands.RoleConverter().convert(ctx, target)
            except commands.BadArgument:
                return await ctx.warn("That **user** or **role** was not found.")

        if member:
            if member.id == ctx.guild.owner_id:
                return await ctx.warn("You **cannot exempt or unexempt the server owner** from warnings.")

            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
                return await ctx.warn(f"{member.mention} **cannot be modified** because their top role is higher than or equal to yours.")

            existing = await self.bot.pool.fetchval(
                "SELECT 1 FROM warn_exempt WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                member.id
            )
            if existing:
                await self.bot.pool.execute(
                    "DELETE FROM warn_exempt WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id,
                    member.id
                )
                return await ctx.approve(f"{member.mention} can now be warned.")
            else:
                await self.bot.pool.execute(
                    """
                    INSERT INTO warn_exempt (guild_id, user_id, exempted_by, created_at)
                    VALUES ($1, $2, $3, NOW())
                    """,
                    ctx.guild.id,
                    member.id,
                    ctx.author.id
                )
                return await ctx.approve(f"{member.mention} is now **exempt** from warnings and warning punishments.")

        if role:
            if ctx.author.id != ctx.guild.owner_id and (role >= ctx.author.top_role or role in ctx.author.roles):
                return await ctx.warn(f"{role.mention} **cannot be modified** because it's your own role or higher than yours.")

            existing = await self.bot.pool.fetchval(
                "SELECT 1 FROM warn_exempt WHERE guild_id = $1 AND role_id = $2",
                ctx.guild.id,
                role.id
            )

            if existing:
                await self.bot.pool.execute(
                    "DELETE FROM warn_exempt WHERE guild_id = $1 AND role_id = $2",
                    ctx.guild.id,
                    role.id
                )
                return await ctx.approve(f"{role.mention} can now be warned.")
            else:
                await self.bot.pool.execute(
                    """
                    INSERT INTO warn_exempt (guild_id, role_id, exempted_by, created_at)
                    VALUES ($1, $2, $3, NOW())
                    """,
                    ctx.guild.id,
                    role.id,
                    ctx.author.id
                )
                return await ctx.approve(f"{role.mention} is now **exempt** from warning punishments.")


    @warn.command(name="exempted", usage='warn exempted')
    @hybrid_permissions(manage_messages=True)
    async def warn_exempted(self, ctx: Context):
        """
        View all roles or users who cannot be warned
        """
        if ctx.author.id != ctx.guild.owner_id:
            is_bypasser = await self.bot.pool.fetchval(
                """
                SELECT TRUE FROM warn_bypass
                WHERE guild_id = $1 AND (
                    user_id = $2 OR role_id = ANY($3::BIGINT[])
                )
                LIMIT 1
                """,
                ctx.guild.id,
                ctx.author.id,
                [r.id for r in ctx.author.roles] or [0],
            )
            if not is_bypasser:
                return await ctx.warn("Only the **server owner** or a **bypassed user/role** can use this command.")

        rows = await self.bot.pool.fetch(
            """
            SELECT user_id, role_id, exempted_by, created_at
            FROM warn_exempt
            WHERE guild_id = $1
            """,
            ctx.guild.id
        )

        if not rows:
            return await ctx.warn("No users or roles are exempted from warnings or punishments.")

        lines = []
        for i, row in enumerate(rows):
            target_id = row["user_id"] or row["role_id"]
            target = ctx.guild.get_member(target_id) or ctx.guild.get_role(target_id)
            display = target.mention if target else f"<@{target_id}>"

            added_by = f"<@{row['exempted_by']}>" if row["exempted_by"] else "Unknown"
            timestamp = row["created_at"]
            when = f"<t:{int(timestamp.timestamp())}:R>" if timestamp else "Unknown"

            lines.append(f"`{i + 1}.` {display} - added by {added_by} → {when}")

        embed = discord.Embed(
            title="<:slain_Settings:1391058914816167996> Whitelisted Users & Roles",
            color=0xacacac
        )

        if len(lines) > 10:
            lines = [line.replace(f"`{i + 1}.` ", "") for i, line in enumerate(lines)]
            paginator = Paginator(ctx, lines, embed=embed, per_page=10, counter=True)
            return await paginator.start()

        embed.description = "\n".join(f"> {line}" for line in lines)
        await ctx.send(embed=embed)


    @warn.command(name="reset", usage='warn reset')
    @cooldown(1, 10, BucketType.guild)
    async def warn_reset(self, ctx: Context):
        """
        Reset all warning configurations to default
        """
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("Only the **server owner** can reset all warn settings.")

        guild_id = ctx.guild.id

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM warn_config WHERE guild_id = $1", guild_id)
                await conn.execute("DELETE FROM warn_role_config WHERE guild_id = $1", guild_id)
                await conn.execute("DELETE FROM warn_exempt WHERE guild_id = $1", guild_id)
                await conn.execute("DELETE FROM warn_bypass WHERE guild_id = $1", guild_id)

        await ctx.approve(
            "All **warnings, configuration settings, role thresholds, exemptions, and bypasses** have been fully reset."
        )

        #warn punishment 
        #set a threshold for a specific role or for all users receiving warnings
        #set the threshold for how many warnings can be given before punishment
        #set a punishment for a user reaching x amount of surpassed threshold warnings for that role, or in general as a user
        #Exclude a role from being effected by this, or member from being effected
        #enable/disable this module
        #examples: 
        # user x reached 3 warnings and are timed out for 1 day
        # OR  user x reached 3 warnings and are now kicked
        # OR  user x reached 3 warnings and are now banned
        # OR user x was warned while user has role Y and is now timed out for 1 day
        # OR user x was warned while user has role Y and is now kicked
        # OR user x was warned while user has role Y and is now banned

async def setup(bot: Bot) -> None:
    await bot.add_cog(Moderation(bot))