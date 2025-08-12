from discord.ext import commands
from discord import Embed
from bot.shared.paginator import Paginator


def wrap_description(text: str, width: int = 50) -> str:
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if len(current_line) + len(word) + (1 if current_line else 0) <= width:
            current_line += (" " if current_line else "") + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)


def is_excluded(command) -> bool:
    if command.cog_name and command.cog_name.lower() == "jishaku":
        return True

    mod = getattr(command.callback, "__module__", "")
    return any(mod.startswith(f"bot.extensions.{x}") for x in ("developer", "api"))


class HelpCommand(commands.HelpCommand):
    context: commands.Context

    def __init__(self):
        super().__init__()
        self.paginator = None

    async def send_bot_help(self, mapping: dict) -> None:
        embed = Embed(
            color=0x2b2d31,
            description="Click [here](https://slain.bot) to view the full list of commands"
        )

        total_commands = 0
        for cog, cmds in mapping.items():
            visible_cmds = [
                cmd for cmd in cmds
                if not cmd.hidden and not is_excluded(cmd)
            ]
            total_commands += len(visible_cmds)
        await self.context.send(embed=embed)

    async def send_group_help(self, group) -> None:
        if is_excluded(group):
            raise commands.CommandNotFound()
        await self.send_command_help(group)

    async def send_command_help(self, command) -> None:
        if is_excluded(command):
            raise commands.CommandNotFound()

        try:
            description = wrap_description(command.help or "No description available")

            def get_permissions(cmd):
                perms = getattr(cmd.callback, "__hybrid_perms__", [])
                if perms:
                    return perms
                perms = []
                for check in getattr(cmd, "checks", []):
                    if hasattr(check, "__qualname__") and ("has_permissions" in check.__qualname__ or "has_guild_permissions" in check.__qualname__):
                        perms += [
                            k.replace("_", " ").title()
                            for check_func in check.__closure__ or []
                            for k in (check_func.cell_contents if isinstance(check_func.cell_contents, dict) else {}).keys()
                        ]
                return perms

            if isinstance(command, commands.Group):
                embeds = []

                main_embed = Embed(
                    color=0xacacac,
                    title=f"**{command.qualified_name}**",
                    description=description
                )

                if command.aliases:
                    main_embed.add_field(
                        name="Aliases",
                        value=", ".join(f"`{alias}`" for alias in command.aliases),
                        inline=True
                    )

                if command.clean_params:
                    main_embed.add_field(
                        name="Parameters",
                        value=", ".join(f"`{param}`" for param in command.clean_params),
                        inline=True
                    )

                perms = get_permissions(command)
                if perms:
                    main_embed.add_field(
                        name="Permissions",
                        value=", ".join(f"<:slain_error:1390898515131105431> `{perm}`" for perm in perms),
                        inline=True
                    )

                main_embed.add_field(
                    name="Usage",
                    value=f"```\n{self.context.clean_prefix}{command.usage or ''}```",
                    inline=False
                )
                main_embed.set_footer(
                    text=f"Module: {command.cog_name.lower() if command.cog_name else 'none'}"
                )
                embeds.append(main_embed)

                subcommands = sorted(command.commands, key=lambda x: x.name)
                for subcmd in subcommands:
                    if is_excluded(subcmd):
                        continue

                    subcmd_embed = Embed(
                        color=0xacacac,
                        title=f"**{command.qualified_name} {subcmd.name}**",
                        description=wrap_description(subcmd.help or "No description available")
                    )

                    if subcmd.aliases:
                        subcmd_embed.add_field(
                            name="Aliases",
                            value=", ".join(f"`{alias}`" for alias in subcmd.aliases),
                            inline=True
                        )

                    if subcmd.clean_params:
                        subcmd_embed.add_field(
                            name="Parameters",
                            value=", ".join(f"`{param}`" for param in subcmd.clean_params),
                            inline=True
                        )

                    perms = get_permissions(subcmd)
                    if perms:
                        subcmd_embed.add_field(
                            name="Permissions",
                            value=", ".join(f"<:slain_error:1390898515131105431> `{perm}`" for perm in perms),
                            inline=True
                        )

                    subcmd_embed.add_field(
                        name="Usage",
                        value=f"```\n{self.context.clean_prefix}{subcmd.usage or ''}```",
                        inline=False
                    )
                    subcmd_embed.set_footer(
                        text=f"Module: {command.cog_name.lower() if command.cog_name else 'none'}"
                    )
                    embeds.append(subcmd_embed)

                if len(embeds) > 1:
                    paginator = Paginator(self.context, embeds)
                    await paginator.start()
                else:
                    await self.context.send(embed=embeds[0])

            else:
                embed = Embed(
                    color=0xacacac,
                    title=f"**{command.qualified_name}**",
                    description=description
                )

                if command.aliases:
                    embed.add_field(
                        name="Aliases",
                        value=", ".join(f"`{alias}`" for alias in command.aliases),
                        inline=True
                    )

                if command.clean_params:
                    embed.add_field(
                        name="Parameters",
                        value=", ".join(f"`{param}`" for param in command.clean_params),
                        inline=True
                    )

                perms = get_permissions(command)
                if perms:
                    embed.add_field(
                        name="Permissions",
                        value=", ".join(f"<:slain_error:1390898515131105431> `{perm}`" for perm in perms),
                        inline=True
                    )

                embed.add_field(
                    name="Usage",
                    value=f"```\n{self.context.clean_prefix}{command.usage or ''}```",
                    inline=False
                )
                embed.set_footer(
                    text=f"Module: {command.cog_name.lower() if command.cog_name else 'none'}"
                )
                await self.context.send(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await self.context.send(f"An error occurred while displaying help: {e}")