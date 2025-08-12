from discord.ext import commands
from discord import Member

def hybrid_permissions(**required_perms: bool):
    def decorator(func):
        setattr(func, "__hybrid_perms__", [perm for perm, val in required_perms.items() if val])

        async def predicate(ctx: commands.Context):
            member: Member = ctx.author
            guild = ctx.guild
            fakeperms = ctx.bot.get_cog("Fakeperms")

            if not fakeperms:
                raise commands.MissingPermissions(required_perms.keys())

            missing = []

            for perm, required in required_perms.items():
                if not required:
                    continue

                has_real = getattr(member.guild_permissions, perm, False)
                has_fake = await fakeperms.has_fake_permission(guild.id, member, perm)

                if not has_real and not has_fake:
                    missing.append(perm)

            if missing:
                raise commands.MissingPermissions(missing)

            return True

        return commands.check(predicate)(func)

    return decorator