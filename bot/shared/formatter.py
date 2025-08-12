from typing import Sequence
import discord
from discord import Interaction
from discord.ext.commands import Context

class plural:
    value: str | int | list
    markdown: str

    def __init__(self, value: str | int | list, md: str = ""):
        self.value = value
        self.markdown = md

    def __format__(self, format_spec: str) -> str:
        v = self.value
        if isinstance(v, str):
            v = (
                int(v.split(" ", 1)[-1])
                if v.startswith(("CREATE", "DELETE"))
                else int(v)
            )
        elif isinstance(v, list):
            v = len(v)
        singular, _, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        return (
            f"{self.markdown}{v:,}{self.markdown} {plural}"
            if abs(v) != 1
            else f"{self.markdown}{v:,}{self.markdown} {singular}"
        )
    
def human_join(seq: Sequence[str], delim: str = ", ", final: str = "or") -> str:
    size = len(seq)
    if size == 0:
        return ""

    if size == 1:
        return seq[0]
    if size == 2:
        return f"{seq[0]} {final} {seq[1]}"

    return delim.join(seq[:-1]) + f" {final} {seq[-1]}"


def duration(value: float, ms: bool = True) -> str:
    h = int((value / (1000 * 60 * 60)) % 24) if ms else int((value / (60 * 60)) % 24)
    m = int((value / (1000 * 60)) % 60) if ms else int((value / 60) % 60)
    s = int((value / 1000) % 60) if ms else int(value % 60)

    result = ""
    if h:
        result += f"{h}:"

    result += f"{m}:" if m else "00:"
    result += f"{str(s).zfill(2)}" if s else "00"

    return result

def hyperlink(text: str, url: str) -> str:
    return f"[{text}]({url})"

def shorten(value: str, length: int = 24, remove_chars: bool = True) -> str:
    if remove_chars:
        BROKEN_HYPERLINK = ["[", "]", "(", ")"]
        for char in BROKEN_HYPERLINK:
            value = value.replace(char, "")

    value = value.replace("\n", " ")

    if len(value) <= length:
        return value

    return value[: length - 2] + ".."

def wrap_interaction_as_ctx(interaction: Interaction) -> Context:
    class FakeContext:
        def __init__(self, interaction: Interaction):
            self.guild = interaction.guild
            self.author = interaction.user
            self.channel = interaction.channel

    return FakeContext(interaction)

def compact_number(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)