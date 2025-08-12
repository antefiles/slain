from discord.ext import commands
from discord.ext.commands import Cog, Context, cooldown, BucketType
from typing import Optional
import discord, re, difflib, asyncio
from datetime import datetime
from bot.shared.paginator import Paginator
from ..embeds import replace_vars, build_embed_from_raw
from bot.shared.fakeperms import hybrid_permissions


from .core import LevelManager, DEFAULT_SPEED


class Leveling(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = LevelManager(bot.pool)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self.bot.pool.execute(
            "DELETE FROM level_roles WHERE guild_id = $1 AND role_id = $2",
            role.guild.id, role.id
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if not message.content.strip():
            return

        if len(message.content.strip()) < 5:
            return

        if self.manager.is_spamming(message.author.id):
            return

        ignored = await self.bot.pool.fetch(
            "SELECT type, target_id FROM level_ignores WHERE guild_id = $1",
            message.guild.id
        )
        ignored_channels = {r["target_id"] for r in ignored if r["type"] == "channel"}
        ignored_roles = {r["target_id"] for r in ignored if r["type"] == "role"}

        if message.channel.id in ignored_channels:
            return

        if any(role.id in ignored_roles for role in message.author.roles):
            return

        row = await self.bot.pool.fetchrow(
            "SELECT speed, enabled, stack_roles FROM leveling_settings WHERE guild_id = $1",
            message.guild.id
        )
        if not row or not row["enabled"]:
            return

        speed = row["speed"] or 3
        stack_roles = row["stack_roles"]
        data = await self.manager.get_user_data(message.author.id, message.guild.id)

        if data and self.manager.on_xp_cooldown(data["last_xp"]):
            return

        gained = self.manager.generate_xp(speed)
        old_level = data["level"] if data else 1
        old_xp = data["xp"] if data else 0
        new_total = old_xp + gained
        new_level = self.manager.get_level_from_xp(new_total)

        await self.bot.pool.execute(
            """
            INSERT INTO user_levels (user_id, guild_id, xp, level, last_xp)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET xp = $3, level = $4, last_xp = $5
            """,
            message.author.id, message.guild.id, new_total, new_level, datetime.utcnow()
        )

        if new_level > old_level:
            msg_row = await self.bot.pool.fetchrow("""
                SELECT channel_id, message FROM level_messages
                WHERE guild_id = $1
            """, message.guild.id)

            reward_row = await self.bot.pool.fetchrow(
                "SELECT role_id FROM level_roles WHERE guild_id = $1 AND level = $2",
                message.guild.id, new_level
            )
            reward_role = message.guild.get_role(reward_row["role_id"]) if reward_row else None

            if msg_row:
                channel = message.guild.get_channel(msg_row["channel_id"])
                if channel:
                    ctx = await self.bot.get_context(message)
                    content = msg_row["message"]
                    extra = {
                        "level": new_level,
                        "xp": new_total,
                        "level.reward": reward_role.name if reward_role else "",
                        "level.reward_mention": reward_role.mention if reward_role else "",
                        "level.reward_append": f" and earned {reward_role.mention}!" if reward_role else ""
                    }

                    if "{embed}" in content:
                        try:
                            msg_content, embed = await build_embed_from_raw(self.bot, ctx, content, extra=extra)
                            await channel.send(content=msg_content or None, embed=embed)
                        except Exception:
                            await channel.send(replace_vars(content, ctx, extra=extra).replace("\\n", "\n"))
                    else:
                        await channel.send(replace_vars(content, ctx, extra=extra).replace("\\n", "\n"))

            if reward_role and reward_role not in message.author.roles:
                try:
                    if not stack_roles:
                        previous_roles = await self.bot.pool.fetch(
                            "SELECT role_id FROM level_roles WHERE guild_id = $1 AND level < $2",
                            message.guild.id, new_level
                        )
                        for r in previous_roles:
                            prev = message.guild.get_role(r["role_id"])
                            if prev and prev in message.author.roles:
                                await message.author.remove_roles(prev, reason="Level-up role stacking disabled")
                    await message.author.add_roles(reward_role, reason="Level-up reward")
                except Exception:
                    pass


    @commands.hybrid_group(name="levels", usage='levels', aliases=['level'], invoke_without_command=True)
    async def levels(self, ctx: Context, member: Optional[discord.Member] = None):
        """
        View your current level in the server
        """
        settings = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not settings or not settings["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        member = member or ctx.author
        data = await self.manager.get_user_data(member.id, ctx.guild.id)
        if not data:
            return await ctx.warn("No level data found for that user")

        level = data["level"]
        xp = data["xp"]

        current_level_xp = self.manager.xp_for_level(level)
        next_level_xp = self.manager.xp_for_level(level + 1)
        progress = xp - current_level_xp
        required = next_level_xp - current_level_xp

        bar = self.manager.build_progress_bar(
            current_xp=progress,
            next_level_xp=required,
            length=8
        )

        embed = discord.Embed(
            color=0x2b2d31,
            description=f"Level: **{level}**\nXP: **{progress:,} / {required:,}**"
        )
        embed.set_author(name=f"{member.name}", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Progress", value=bar, inline=False)
        embed.set_footer(text=f"Total XP earned: {xp:,}")

        await ctx.send(embed=embed)


    @levels.command(name="sync", usage='levels sync')
    @hybrid_permissions(administrator=True)
    async def levels_sync(self, ctx: Context):
        """
        Syncronize all level roles with users based on their level
        """
        settings = await self.bot.pool.fetchrow(
            "SELECT enabled, stack_roles FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not settings or not settings["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server.")

        stack_roles = settings["stack_roles"]

        level_roles = await self.bot.pool.fetch(
            "SELECT level, role_id FROM level_roles WHERE guild_id = $1 ORDER BY level ASC",
            ctx.guild.id
        )
        if not level_roles:
            return await ctx.warn("There are no level role rewards set for this server")

        level_to_role = {row["level"]: ctx.guild.get_role(row["role_id"]) for row in level_roles}
        level_order = sorted(level_to_role.keys())

        user_levels = await self.bot.pool.fetch(
            "SELECT user_id, level FROM user_levels WHERE guild_id = $1",
            ctx.guild.id
        )

        members_to_update = [ctx.guild.get_member(row["user_id"]) for row in user_levels]
        members_to_update = [m for m in members_to_update if m is not None]

        batch_size = 3
        sleep_time = 2
        num_batches = (len(members_to_update) + batch_size - 1) // batch_size
        total_eta_sec = num_batches * sleep_time
        eta_minutes = round(total_eta_sec / 60)
        eta_display = f"{eta_minutes} minute{'s' if eta_minutes != 1 else ''}" if eta_minutes else "under a minute"

        embed = discord.Embed(
            description=f"<a:slain_load:1392313474310209537> Syncing roles for **{len(members_to_update)}** users...\n-# *Estimated time: **{eta_display}***",
            color=0x7b9fb0
        )
        msg = await ctx.send(embed=embed)

        updated = 0
        counter = 0

        for member in members_to_update:
            current_level = next((r["level"] for r in user_levels if r["user_id"] == member.id), 0)

            if stack_roles:
                roles_to_add = [
                    role for lvl, role in level_to_role.items()
                    if role and lvl <= current_level and role not in member.roles and role < ctx.guild.me.top_role
                ]
                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="Level sync (stacking)")
                        updated += 1
                    except:
                        pass
            else:
                eligible = [
                    (lvl, role) for lvl, role in level_to_role.items()
                    if lvl <= current_level and role and role < ctx.guild.me.top_role
                ]
                if not eligible:
                    continue
                highest_level, highest_role = max(eligible, key=lambda x: x[0])
                added_role = False
                removed_roles = []

                if highest_role not in member.roles:
                    try:
                        await member.add_roles(highest_role, reason="Level sync (non-stacking)")
                        added_role = True
                    except:
                        pass

                lower_roles = [
                    role for lvl, role in level_to_role.items()
                    if lvl < highest_level and role in member.roles
                ]
                if lower_roles:
                    try:
                        await member.remove_roles(*lower_roles, reason="Level sync (non-stacking cleanup)")
                        removed_roles = lower_roles
                    except:
                        pass

                if added_role or removed_roles:
                    updated += 1

            counter += 1
            if counter % batch_size == 0:
                await asyncio.sleep(sleep_time)

        embed.description = f"<:slain_approve:1392318903325036635> Synced roles for **{updated}** users"
        embed.set_footer(text="")
        await msg.edit(embed=embed)


    @levels.command(name="enable", usage='levels enable')
    @hybrid_permissions(administrator=True)
    async def levels_enable(self, ctx: Context):
        """
        Enable levels to be used in the server
        """
        row = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if row and row["enabled"]:
            return await ctx.warn("Leveling is already enabled for this server")

        await self.bot.pool.execute("""
            INSERT INTO leveling_settings (guild_id, speed, enabled)
            VALUES ($1, $2, TRUE)
            ON CONFLICT (guild_id) DO UPDATE SET enabled = TRUE
        """, ctx.guild.id, 3)

        await self.bot.pool.execute("""
            INSERT INTO level_messages (guild_id, channel_id, message)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO NOTHING
        """, ctx.guild.id, ctx.channel.id, "{user.mention} leveled up to level **{level}**{level.reward_append}")

        await ctx.approve("Leveling has been **enabled**")

    @levels.command(name="setrate", usage='levels setrate [1-5]')
    @hybrid_permissions(administrator=True)
    async def levels_setrate(self, ctx: Context, rate: int):
        """
        Set the speed for how fast users can gain XP
        """
        if rate not in (1, 2, 3, 4, 5):
            return await ctx.warn("Rate speed must be between **1 (slowest)** and **5 (fastest)**")

        row = await self.bot.pool.fetchrow(
            "SELECT enabled, speed FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not row or not row["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** for this server")

        if row["speed"] == rate:
            return await ctx.warn(f"The leveling speed is already set to **{rate}**")

        await self.bot.pool.execute(
            "UPDATE leveling_settings SET speed = $1 WHERE guild_id = $2",
            rate, ctx.guild.id
        )

        await ctx.approve(f"Leveling set to **x{rate} speed**")

    @levels.command(name="leaderboard", usage='levels leaderboard', aliases=["lb"])
    @commands.cooldown(3, 5, commands.BucketType.guild)
    async def levels_leaderboard(self, ctx: Context):
        """
        View the highest levels in the server
        """
        row = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not row or not row["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        rows = await self.bot.pool.fetch(
            """
            SELECT user_id, xp, level
            FROM user_levels
            WHERE guild_id = $1
            ORDER BY xp DESC
            LIMIT 50
            """,
            ctx.guild.id
        )

        if not rows:
            return await ctx.warn("No level data found for this server")

        entries = []
        for i, row in enumerate(rows, start=1):
            user = ctx.guild.get_member(row["user_id"]) or await self.bot.fetch_user(row["user_id"])
            tag = user.name if not hasattr(user, "mention") else user.mention
            entries.append(f"{tag} — Level `{row['level']}` • **({row['xp']:,} XP)**")

        embed = discord.Embed(
            title=f"Levels Leaderboard",
            color=0xacacac
        )

        paginator = Paginator(ctx, entries, embed=embed, per_page=10)
        await paginator.start()

    @levels.command(name="disable", usage='levels disable')
    @hybrid_permissions(administrator=True)
    async def levels_disable(self, ctx: Context):
        """
        Disables the levels module from being used in the server
        """
        row = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not row or not row["enabled"]:
            return await ctx.warn("Leveling is already **disabled** in this server")

        await self.bot.pool.execute(
            "UPDATE leveling_settings SET enabled = FALSE WHERE guild_id = $1",
            ctx.guild.id
        )

        await ctx.approve("Leveling system has been **disabled** for this server")

    @levels.command(name="message", usage='levels message [channel] [level message]')
    @hybrid_permissions(manage_messages=True)
    async def levels_message(self, ctx: Context, *, raw: Optional[str] = None):
        """
        Set a custom level up message and/or the channel it should send to
        """
        row = await self.bot.pool.fetchrow("SELECT enabled FROM leveling_settings WHERE guild_id = $1", ctx.guild.id)
        if not row or not row["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        channel = ctx.channel
        message = None

        if raw:
            mentions = ctx.message.channel_mentions
            if mentions:
                channel = mentions[0]
                message = raw.replace(f"<#{channel.id}>", "").strip()
            else:
                message = raw.strip()

        if not message:
            default = "{user.mention} leveled up to **level {level}**{level.reward_append}"
            await self.bot.pool.execute(
                """
                INSERT INTO level_messages (guild_id, channel_id, message)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, message = $3
                """,
                ctx.guild.id, channel.id, default
            )
            return await ctx.approve(f"Default level up message set to {channel.mention}")

        try:
            if "{embed}" in message:
                _msg, _embed = await build_embed_from_raw(self.bot, ctx, message)
            else:
                _ = replace_vars(message, ctx)
        except Exception as e:
            return await ctx.warn(f"Invalid message format: {e}")

        await self.bot.pool.execute(
            """
            INSERT INTO level_messages (guild_id, channel_id, message)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, message = $3
            """,
            ctx.guild.id, channel.id, message
        )

        await ctx.approve(f"Custom level up message set to {channel.mention}")

    @levels.command(name="messagetest", usage='levels messagetest')
    @hybrid_permissions(manage_messages=True)
    async def levels_messagetest(self, ctx: Context):
        """
        Preview the current level up message message
        """
        row = await self.bot.pool.fetchrow(
            "SELECT channel_id, message FROM level_messages WHERE guild_id = $1",
            ctx.guild.id
        )
        if not row or not row["message"]:
            return await ctx.warn("No level up message is currently configured")

        message = row["message"]
        channel = ctx.guild.get_channel(row["channel_id"]) or ctx.channel

        level_number = 5
        reward_append = " and earned @role!"

        message = (
            message.replace("{level}", str(level_number))
                .replace("{level.reward_append}", reward_append)
        )

        try:
            if "{embed}" in message:
                msg_content, embed = await build_embed_from_raw(self.bot, ctx, message)
                await channel.send(content=msg_content or None, embed=embed)
            else:
                content = replace_vars(message, ctx)
                await channel.send(content)
        except Exception as e:
            return await ctx.warn(f"Failed to build test message: {e}")

    @levels.command(name="addrole", usage='levels addrole [role award] [level]')
    @hybrid_permissions(manage_roles=True)
    async def levels_role(self, ctx: Context, role: str, level: int):
        """
        Add a reward role for a user reaching a specific level
        """
        if level < 3:
            return await ctx.warn("Roles can only be assigned for **level 3 or higher** to prevent alt farming")

        match = re.match(r"<@&(\d+)>", role)
        if match:
            role_obj = ctx.guild.get_role(int(match.group(1)))
        else:
            roles = [r for r in ctx.guild.roles if not r.is_bot_managed()]
            matches = difflib.get_close_matches(role.lower(), [r.name.lower() for r in roles], n=1, cutoff=0.6)
            role_obj = next((r for r in roles if r.name.lower() == matches[0]), None) if matches else None

        if not role_obj:
            return await ctx.warn("No matching role was found")

        if role_obj.is_bot_managed():
            return await ctx.warn("You cannot assign a **bot-managed role** as a level reward")

        if role_obj.is_premium_subscriber():
            return await ctx.warn("You cannot assign the **Nitro Booster role** as a level reward")

        if role_obj.managed:
            return await ctx.warn("You cannot assign an **integration managed role** as a level reward")

        perms = role_obj.permissions
        if perms.administrator or perms.manage_guild:
            return await ctx.warn("You cannot assign a role with **Administrator** or **Manage Server** permissions")

        if role_obj >= ctx.guild.me.top_role:
            return await ctx.warn(f"I cannot manage {role_obj.mention} because it is **higher or equal** to my top role")

        existing = await self.bot.pool.fetchrow(
            "SELECT role_id FROM level_roles WHERE guild_id = $1 AND level = $2",
            ctx.guild.id, level
        )
        if existing and existing["role_id"] != role_obj.id:
            current = ctx.guild.get_role(existing["role_id"])
            return await ctx.warn(
                f"Level **{level}** is already set to give **{current.mention if current else 'a role'}**"
            )

        await self.bot.pool.execute(
            """
            INSERT INTO level_roles (guild_id, level, role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, level) DO UPDATE SET role_id = $3
            """,
            ctx.guild.id, level, role_obj.id
        )

        await ctx.approve(f"{role_obj.mention} will now be **granted at level {level}**")


    @levels.command(name="removerole", usage='levels removerole [role]')
    @hybrid_permissions(manage_roles=True)
    async def levels_roleremove(self, ctx: Context, role: str):
        """
        Remove a role from being awarded to a user reaching set level
        """
        settings = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not settings or not settings["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        match = re.match(r"<@&(\d+)>", role)
        if match:
            role_obj = ctx.guild.get_role(int(match.group(1)))
        else:
            roles = [r for r in ctx.guild.roles if not r.is_bot_managed()]
            matches = difflib.get_close_matches(role.lower(), [r.name.lower() for r in roles], n=1, cutoff=0.6)
            role_obj = next((r for r in roles if r.name.lower() == matches[0]), None) if matches else None

        if not role_obj:
            return await ctx.warn("No matching role was found")

        if role_obj.is_bot_managed():
            return await ctx.warn("You cannot remove a **bot managed role** from level rewards")

        if role_obj.is_premium_subscriber():
            return await ctx.warn("You cannot remove the **Nitro Booster role** because it cannot be used in level rewards")

        if role_obj >= ctx.guild.me.top_role:
            return await ctx.warn(f"I cannot manage {role_obj.mention} because it is **higher or equal** to my top role")

        row = await self.bot.pool.fetchrow(
            "SELECT level FROM level_roles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role_obj.id
        )

        if not row:
            return await ctx.warn(f"No Level role is set for **{role_obj.mention}**")

        await self.bot.pool.execute(
            "DELETE FROM level_roles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role_obj.id
        )

        await ctx.approve(f"Removed Level role for **{role_obj.mention}**")

    @levels.command(name="reset", usage='levels reset [user]')
    @hybrid_permissions(administrator=True)
    async def levels_reset(self, ctx: Context, member: discord.Member):
        """
        Reset a users xp and level back to 0
        """
        row = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not row or not row["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        exists = await self.bot.pool.fetchval(
            "SELECT 1 FROM user_levels WHERE user_id = $1 AND guild_id = $2",
            member.id, ctx.guild.id
        )

        if not exists:
            return await ctx.warn(f"{member.mention} has no level data to reset")

        await self.bot.pool.execute(
            """
            UPDATE user_levels
            SET xp = 0, level = 1, last_xp = NULL
            WHERE user_id = $1 AND guild_id = $2
            """,
            member.id, ctx.guild.id
        )

        await ctx.approve(f"Reset level data for {member.mention}. They are now level **1** with **0 XP**")


    @levels.command(name="config", usage='levels config')
    @hybrid_permissions(administrator=True)
    async def levels_config(self, ctx: Context):
        """
        View the ignored levels and channels, along with the configured speed and state
        """
        settings = await self.bot.pool.fetchrow(
            "SELECT enabled, speed FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not settings:
            return await ctx.warn("No leveling settings found for this server")

        enabled = "Enabled" if settings["enabled"] else "Disabled"
        speed = settings["speed"] or DEFAULT_SPEED
        speed_map = {
            1: "Very Slow",
            2: "Slow",
            3: "Normal",
            4: "Fast",
            5: "Very Fast"
        }

        rows = await self.bot.pool.fetch(
            "SELECT type, target_id FROM level_ignores WHERE guild_id = $1",
            ctx.guild.id
        )

        ignored = []
        for row in rows:
            if row["type"] == "channel":
                obj = ctx.guild.get_channel(row["target_id"])
                if obj:
                    ignored.append(f"Channel: {obj.mention}")
            elif row["type"] == "role":
                obj = ctx.guild.get_role(row["target_id"])
                if obj:
                    ignored.append(f"Role: {obj.mention}")

        entries = [f"`{i+1}.` {entry}" for i, entry in enumerate(ignored)]
        pages = []

        base_embed = discord.Embed(
            title="<:slain_Settings:1391058914816167996> Leveling Configuration",
            color=0xacacac
        )
        base_embed.add_field(
            name="Settings",
            value=f"**Status:** `{enabled}`\n**Speed:** `{speed_map.get(speed, 'Unknown')}`",
            inline=False
        )

        if entries:
            chunk = entries[:8]
            base_embed.add_field(
                name="Ignored",
                value="\n".join(chunk),
                inline=False
            )
            pages.append(base_embed)

            for i in range(8, len(entries), 10):
                embed = discord.Embed(
                    title="<:slain_Settings:1391058914816167996> Leveling Configuration",
                    color=0xacacac
                )
                embed.add_field(
                    name="Ignored",
                    value="\n".join(entries[i:i + 10]),
                    inline=False
                )
                pages.append(embed)
        else:
            pages.append(base_embed)

        await Paginator(ctx, pages).start()


    @levels.command(name="roles", usage='levels roles')
    @hybrid_permissions(manage_roles=True)
    async def levels_roles(self, ctx: Context):
        """
        View all roles setup to be given to users who reaches the set level
        """
        settings = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not settings or not settings["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        rows = await self.bot.pool.fetch(
            "SELECT level, role_id FROM level_roles WHERE guild_id = $1 ORDER BY level ASC",
            ctx.guild.id
        )

        if not rows:
            return await ctx.warn("No **Level up role rewards** are currently set")

        entries = []
        for row in rows:
            role = ctx.guild.get_role(row["role_id"])
            display = role.mention if role else "*Deleted Role*"
            entries.append(f"Level **{row['level']}** - {display} is awarded")

        embed = discord.Embed(
            title="Level Roles",
            color=0xacacac
        )

        await Paginator(ctx, entries, embed=embed, per_page=10).start()


    @levels.command(name="ignore", usage='levels ignore [channel or role]')
    @hybrid_permissions(administrator=True)
    async def levels_ignore(self, ctx: Context, *, target: str):
        """
        Ignore users with a specific role, or that are talking in a specific channel, from gaining xp
        """
        if not target:
            return await ctx.warn("Mention or type a **channel** or **role** to toggle ignore")

        ignored = await self.bot.pool.fetch(
            "SELECT type, target_id FROM level_ignores WHERE guild_id = $1",
            ctx.guild.id
        )
        ignored_ids = {(r["type"], r["target_id"]) for r in ignored}

        reward_roles = await self.bot.pool.fetch(
            "SELECT role_id FROM level_roles WHERE guild_id = $1",
            ctx.guild.id
        )
        reward_role_ids = {r["role_id"] for r in reward_roles}

        role_match = re.match(r"<@&(\d+)>", target)
        chan_match = re.match(r"<#(\d+)>", target)

        role = None
        channel = None

        if role_match:
            role = ctx.guild.get_role(int(role_match.group(1)))
        elif chan_match:
            channel = ctx.guild.get_channel(int(chan_match.group(1)))
        else:
            roles = [r for r in ctx.guild.roles if not r.is_bot_managed()]
            role_names = [r.name.lower() for r in roles]
            role_match = difflib.get_close_matches(target.lower(), role_names, n=1, cutoff=0.6)
            if role_match:
                role = next((r for r in roles if r.name.lower() == role_match[0]), None)
            else:
                channels = ctx.guild.text_channels
                channel_names = [c.name.lower() for c in channels]
                chan_match = difflib.get_close_matches(target.lower(), channel_names, n=1, cutoff=0.6)
                if chan_match:
                    channel = next((c for c in channels if c.name.lower() == chan_match[0]), None)

        if role:
            if role.id in reward_role_ids:
                return await ctx.warn(f"{role.mention} is a **reward role** and cannot be ignored")
            key = ("role", role.id)
            if key in ignored_ids:
                await self.bot.pool.execute(
                    "DELETE FROM level_ignores WHERE guild_id = $1 AND type = 'role' AND target_id = $2",
                    ctx.guild.id, role.id
                )
                return await ctx.approve(f"No longer ignoring XP for: {role.mention}")
            else:
                await self.bot.pool.execute(
                    "INSERT INTO level_ignores (guild_id, type, target_id) VALUES ($1, 'role', $2)",
                    ctx.guild.id, role.id
                )
                return await ctx.approve(f"Now **ignoring XP** from: {role.mention}")

        elif channel:
            key = ("channel", channel.id)
            if key in ignored_ids:
                await self.bot.pool.execute(
                    "DELETE FROM level_ignores WHERE guild_id = $1 AND type = 'channel' AND target_id = $2",
                    ctx.guild.id, channel.id
                )
                return await ctx.approve(f"No longer ignoring XP for: {channel.mention}")
            else:
                await self.bot.pool.execute(
                    "INSERT INTO level_ignores (guild_id, type, target_id) VALUES ($1, 'channel', $2)",
                    ctx.guild.id, channel.id
                )
                return await ctx.approve(f"Now **ignoring XP** from: {channel.mention}")

        return await ctx.warn("No matching **channel or role** was found")

    @levels.command(name="stackroles", usage='levels stackroles')
    @hybrid_permissions(administrator=True)
    async def levels_stackroles(self, ctx: Context):
        """
        Toggle whether level roles stack or replace the previous one
        """
        roles_exist = await self.bot.pool.fetchval(
            "SELECT EXISTS(SELECT 1 FROM level_roles WHERE guild_id = $1)",
            ctx.guild.id
        )

        if not roles_exist:
            return await ctx.warn("You must **add at least one level role** before toggling stacking behavior")

        settings = await self.bot.pool.fetchrow(
            "SELECT enabled, stack_roles FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )

        if not settings or not settings["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server")

        current = settings["stack_roles"] if settings["stack_roles"] is not None else False
        new = not current

        await self.bot.pool.execute(
            """
            INSERT INTO leveling_settings (guild_id, stack_roles)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET stack_roles = $2
            """,
            ctx.guild.id, new
        )

        if new:
            return await ctx.approve("Users will now **keep previous roles** when receiving new level up roles")
        else:
            return await ctx.approve("Users will now **only keep the latest** level up role")


    @levels.command(name="resetconfig", usage='levels resetconfig')
    @cooldown(1, 10, BucketType.guild)
    @hybrid_permissions(administrator=True)
    async def levels_resetconfig(self, ctx: Context):
        """
        Reset all level messages, set messages and channels, level roles, and role and channel ignores
        """
        await self.bot.pool.execute("DELETE FROM leveling_settings WHERE guild_id = $1", ctx.guild.id)
        await self.bot.pool.execute("DELETE FROM level_roles WHERE guild_id = $1", ctx.guild.id)
        await self.bot.pool.execute("DELETE FROM level_ignores WHERE guild_id = $1", ctx.guild.id)
        await self.bot.pool.execute("DELETE FROM level_messages WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve("All leveling **configuration settings** have been reset for this server")

    @levels.command(name="resetguild", usage='levels resetguild')
    @cooldown(1, 10, BucketType.guild)
    @hybrid_permissions(administrator=True)
    async def levels_resetguild(self, ctx: Context):
        """
        Reset all leveling data for all users in the server
        """
        await self.bot.pool.execute("DELETE FROM user_levels WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve("All **user level data** has been reset for this server")


    @levels.command(name="setlevel", usage='levels setlevel [user] [level]')
    @cooldown(1, 10, BucketType.guild)
    @hybrid_permissions(administrator=True)
    async def levels_setlevel(self, ctx: Context, member: discord.Member, level: int):
        """
        Set a users level 
        """
        if level < 1:
            return await ctx.warn("Level must be **1 or higher**")

        settings = await self.bot.pool.fetchrow(
            "SELECT enabled FROM leveling_settings WHERE guild_id = $1",
            ctx.guild.id
        )
        if not settings or not settings["enabled"]:
            return await ctx.warn("Leveling is currently **disabled** in this server.")

        xp = self.manager.xp_for_level(level)
        await self.bot.pool.execute(
            """
            INSERT INTO user_levels (user_id, guild_id, xp, level, last_xp)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET xp = $3, level = $4, last_xp = $5
            """,
            member.id, ctx.guild.id, xp, level, datetime.utcnow()
        )
        await ctx.approve(f"Set {member.mention}'s level to **{level}** with **{xp:,} XP**")

async def setup(bot):
    await bot.add_cog(Leveling(bot))
