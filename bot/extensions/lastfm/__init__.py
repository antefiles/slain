import discord
import asyncio
from typing import Optional, List, Union
from discord.ext.commands import Cog, group, command, BucketType, cooldown
from bot.core import Bot, Context
from bot.shared.fakeperms import hybrid_permissions
from bot.shared.paginator import Paginator
from datetime import datetime, timedelta
import random

from .client import LastFMClient, LastFMError
from .utils import (
    format_playcount, format_time_ago, get_period_display, parse_artist_track,
    create_now_playing_embed, create_user_info_embed, validate_period, get_image_url
)
from .models import WhoKnowsEntry

def sanitize_variables(variables: dict) -> dict:
    """Convert problematic data types to strings for embed processing"""
    sanitized = {}
    for key, value in variables.items():
        if isinstance(value, tuple):
            sanitized[key] = ", ".join(str(item) for item in value)
        elif hasattr(value, 'to_dict') and callable(getattr(value, 'to_dict')):
            try:
                sanitized[key] = str(value.to_dict())
            except:
                sanitized[key] = str(value)
        else:
            sanitized[key] = str(value) if value is not None else ""
    return sanitized

class LastFM(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.client = LastFMClient(bot.session)

    async def get_lastfm_user(self, user_id: int) -> Optional[str]:
        result = await self.bot.pool.fetchval(
            "SELECT lastfm_username FROM lastfm_users WHERE user_id = $1",
            user_id
        )
        return result

    async def get_user_or_default(self, ctx: Context, user: Optional[discord.Member]) -> tuple[str, discord.Member]:
        target_user = user or ctx.author
        lastfm_username = await self.get_lastfm_user(target_user.id)
        
        if not lastfm_username:
            if target_user == ctx.author:
                raise ValueError("You haven't linked your Last.fm account yet. Use `lastfm login <username>` to get started.")
            else:
                raise ValueError(f"{target_user.mention} hasn't linked their Last.fm account yet.")
        
        return lastfm_username, target_user

    @group(name="lastfm", aliases=["lf", "lfm"], usage="lastfm", invoke_without_command=True)
    async def lastfm(self, ctx: Context):
        """Integrate your Last.fm account with Slain and view your scrobble stats"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command.qualified_name)

    @lastfm.command(name="login", aliases=["set"], usage="lastfm login <username>")
    @cooldown(3, 30, BucketType.user)
    async def login(self, ctx: Context, username: str):
        """Login and authenticate Slain to use your account"""
        try:
            user_info = await self.client.get_user_info(username)
            
            await self.bot.pool.execute(
                """
                INSERT INTO lastfm_users (user_id, lastfm_username)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE SET lastfm_username = $2, registered_at = NOW()
                """,
                ctx.author.id, user_info.username
            )
            
            await ctx.approve(f"Successfully linked your Last.fm account: **{user_info.username}**")
            
        except LastFMError as e:
            if e.code == 6:
                await ctx.warn("Last.fm user not found. Please check the username and try again.")
            else:
                await ctx.warn(f"Failed to verify Last.fm account: {e.message}")

    @lastfm.command(name="logout", usage="lastfm logout")
    async def logout(self, ctx: Context):
        """Remove your Last.fm account with Slain's internal system"""
        result = await self.bot.pool.execute(
            "DELETE FROM lastfm_users WHERE user_id = $1",
            ctx.author.id
        )
        
        if result == "DELETE 1":
            await ctx.approve("Successfully unlinked your Last.fm account.")
        else:
            await ctx.warn("You don't have a Last.fm account linked.")

    @lastfm.command(name="now", aliases=["fm", "nowplaying", "np"], usage="lastfm now [member]")
    @cooldown(1, 5, BucketType.user)
    async def now(self, ctx: Context, *, user: Optional[discord.Member] = None):
        """Shows your current song playing from Last.fm"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            
            custom_command = await self.bot.pool.fetchrow(
                "SELECT embed_data, is_public FROM lastfm_custom_commands WHERE guild_id = $1 AND user_id = $2 AND command_name = 'np'",
                ctx.guild.id, discord_user.id
            )
            
            if custom_command and (custom_command["is_public"] or discord_user == ctx.author):
                try:
                    lastfm_vars = await self.get_lastfm_variables(ctx, lastfm_username)
                    sanitized_vars = sanitize_variables(lastfm_vars)
                    
                    if "{embed}" in custom_command["embed_data"]:
                        from bot.extensions.embeds import build_embed_from_raw
                        embed = await build_embed_from_raw(self.bot, ctx, custom_command["embed_data"], extra=sanitized_vars)
                        message = await ctx.send(embed=embed)
                    else:
                        from bot.extensions.embeds import replace_vars
                        content = replace_vars(custom_command["embed_data"], ctx, extra=sanitized_vars)
                        message = await ctx.send(content)
                    
                    settings = await self.bot.pool.fetchrow(
                        "SELECT upvote_emoji, downvote_emoji, reactions_enabled FROM lastfm_settings WHERE guild_id = $1",
                        ctx.guild.id
                    )
                    
                    custom_reactions = await self.bot.pool.fetchrow(
                        "SELECT upvote_emoji, downvote_emoji FROM lastfm_custom_reactions WHERE user_id = $1",
                        ctx.author.id
                    )
                    
                    if settings and settings["reactions_enabled"]:
                        upvote = custom_reactions["upvote_emoji"] if custom_reactions and custom_reactions["upvote_emoji"] else settings["upvote_emoji"]
                        downvote = custom_reactions["downvote_emoji"] if custom_reactions and custom_reactions["downvote_emoji"] else settings["downvote_emoji"]
                        
                        if upvote:
                            try:
                                await message.add_reaction(upvote)
                            except:
                                pass
                        if downvote:
                            try:
                                await message.add_reaction(downvote)
                            except:
                                pass
                    return
                    
                except Exception as e:
                    await ctx.warn(f"Custom command error: {str(e)}")
                    return
            
            user_info = await self.client.get_user_info(lastfm_username)
            recent_tracks = await self.client.get_recent_tracks(lastfm_username, 1)
            
            if not recent_tracks:
                await ctx.warn(f"No recent tracks found for **{lastfm_username}**")
                return
            
            track = recent_tracks[0]
            embed = create_now_playing_embed(track, user_info)
            
            settings = await self.bot.pool.fetchrow(
                "SELECT upvote_emoji, downvote_emoji, reactions_enabled FROM lastfm_settings WHERE guild_id = $1",
                ctx.guild.id
            )
            
            custom_reactions = await self.bot.pool.fetchrow(
                "SELECT upvote_emoji, downvote_emoji FROM lastfm_custom_reactions WHERE user_id = $1",
                ctx.author.id
            )
            
            message = await ctx.send(embed=embed)
            
            if settings and settings["reactions_enabled"]:
                upvote = custom_reactions["upvote_emoji"] if custom_reactions and custom_reactions["upvote_emoji"] else settings["upvote_emoji"]
                downvote = custom_reactions["downvote_emoji"] if custom_reactions and custom_reactions["downvote_emoji"] else settings["downvote_emoji"]
                
                if upvote:
                    try:
                        await message.add_reaction(upvote)
                    except:
                        pass
                if downvote:
                    try:
                        await message.add_reaction(downvote)
                    except:
                        pass
                        
        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(name="recent", aliases=["recenttracks", "last", "lp"], usage="lastfm recent [member]")
    @cooldown(1, 5, BucketType.user)
    async def recent(self, ctx: Context, *, user: Optional[discord.Member] = None):
        """View your recent tracks"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            
            user_info = await self.client.get_user_info(lastfm_username)
            recent_tracks = await self.client.get_recent_tracks(lastfm_username, 50)
            
            if not recent_tracks:
                await ctx.warn(f"No recent tracks found for **{lastfm_username}**")
                return
            
            pages = []
            per_page = 10
            
            for i in range(0, len(recent_tracks), per_page):
                chunk = recent_tracks[i:i+per_page]
                page_content = ""
                
                for j, track in enumerate(chunk, i + 1):
                    status = "🎵 " if track.now_playing else ""
                    time_str = "Now Playing" if track.now_playing else format_time_ago(track.timestamp)
                    
                    track_line = f"`{j}.` {status}**[{track.name}]({track.url})**"
                    if track.artist:
                        track_line += f" by **{track.artist}**"
                    track_line += f" - {time_str}"
                    
                    page_content += track_line + "\n"
                
                pages.append(page_content.strip())
            
            embed = discord.Embed(
                title="Recent Tracks",
                color=0x2b2d31,
                timestamp=discord.utils.utcnow()
            )
            
            from .utils import get_image_url
            embed.set_author(
                name=f"{user_info.username}",
                url=user_info.url,
                icon_url=get_image_url(user_info.images, 'medium')
            )
            
            if len(pages) == 1:
                embed.description = pages[0]
                await ctx.send(embed=embed)
            else:
                paginator = Paginator(ctx, pages=pages, embed=embed, per_page=1)
                await paginator.start()
                
        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(
        name="topartists",
        aliases=["artists", "artist", "tar", "topartist", "ta"],
        usage="lastfm topartists [member] [period]"
    )
    @cooldown(1, 5, BucketType.user)
    async def topartists(self, ctx: Context, user: Optional[discord.Member] = None, period: str = "overall"):
        """View your most listened to artists"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            period = validate_period(period)

            user_info = await self.client.get_user_info(lastfm_username)
            artists = await self.client.get_top_artists(lastfm_username, period, 100)

            if not artists:
                return await ctx.warn(
                    f"No top artists found for **{lastfm_username}** in {get_period_display(period).lower()}"
                )

            formatted = []
            for idx, artist in enumerate(artists, start=1):
                plays_text = format_playcount(artist.playcount) if artist.playcount else "0"
                formatted.append(f"**[{artist.name}]({artist.url})** - **{plays_text}** plays")

            from .utils import get_image_url
            embed = discord.Embed(
                title=f"Top Artists - {get_period_display(period)}",
                color=0x2b2d31,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name=f"{user_info.username}",
                url=user_info.url,
                icon_url=get_image_url(user_info.images, 'medium')
            )

            paginator = Paginator(ctx, pages=formatted, embed=embed, per_page=10)
            await paginator.start()

        except Exception as e:
            await ctx.error(f"An error occurred: `{e}`")
    

    @lastfm.command(
        name="toptracks",
        aliases=["track", "tracks", "ttr", "toptrack", "tt"],
        usage="lastfm toptracks [member] [period]"
    )
    @cooldown(1, 5, BucketType.user)
    async def toptracks(self, ctx: Context, user: Optional[discord.Member] = None, period: str = "overall"):
        """View your most listened to tracks"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            period = validate_period(period)

            user_info = await self.client.get_user_info(lastfm_username)
            tracks = await self.client.get_top_tracks(lastfm_username, period, 100)

            if not tracks:
                return await ctx.warn(
                    f"No top tracks found for **{lastfm_username}** in {get_period_display(period).lower()}"
                )

            formatted = []
            for idx, track in enumerate(tracks, start=1):
                plays_text = format_playcount(track.playcount) if track.playcount else "0"
                formatted.append(
                    f"**[{track.name}]({track.url})** - **{plays_text}** plays"
                )

            from .utils import get_image_url
            embed = discord.Embed(
                title=f"Top Tracks - {get_period_display(period)}",
                color=0x2b2d31,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name=f"{user_info.username}",
                url=user_info.url,
                icon_url=get_image_url(user_info.images, 'medium')
            )

            paginator = Paginator(ctx, pages=formatted, embed=embed, per_page=10)
            await paginator.start()

        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(
        name="topalbums",
        aliases=["tab", "album", "topalbum", "albums", "tl"],
        usage="lastfm topalbums [member] [period]"
    )
    @cooldown(1, 5, BucketType.user)
    async def topalbums(self, ctx: Context, user: Optional[discord.Member] = None, period: str = "overall"):
        """View your most listened to albums"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            period = validate_period(period)

            user_info = await self.client.get_user_info(lastfm_username)
            albums = await self.client.get_top_albums(lastfm_username, period, 100)

            if not albums:
                return await ctx.warn(
                    f"No top albums found for **{lastfm_username}** in {get_period_display(period).lower()}"
                )

            formatted = []
            for idx, album in enumerate(albums, start=1):
                plays_text = format_playcount(album.playcount) if album.playcount else "0"
                formatted.append(
                    f"**[{album.name}]({album.url})** by **{album.artist}** - **{plays_text}** plays"
                )

            from .utils import get_image_url
            embed = discord.Embed(
                title=f"Top Albums - {get_period_display(period)}",
                color=0x2b2d31,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name=f"{user_info.username}",
                url=user_info.url,
                icon_url=get_image_url(user_info.images, 'medium')
            )

            paginator = Paginator(ctx, pages=formatted, embed=embed, per_page=10)
            await paginator.start()

        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")


    @lastfm.command(name="plays", usage="lastfm plays [member] <artist>")
    @cooldown(1, 5, BucketType.user)
    async def plays(self, ctx: Context, user: Optional[discord.Member] = None, *, artist: str = None):
        """Check how many plays you have for an artist"""
        if user and not artist:
            artist = str(user)
            user = ctx.author
            
        if not artist:
            await ctx.warn("Please specify an artist name")
            return
            
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            
            playcount = await self.client.get_artist_playcount(lastfm_username, artist)
            artist_info = await self.client.get_artist_info(artist)
            
            embed = discord.Embed(
                title=f"Artist Plays",
                color=0x2b2d31,
                description=f"**{discord_user.display_name}** has **{format_playcount(playcount)}** plays for **{artist_info.get('name', artist)}**",
                timestamp=discord.utils.utcnow()
            )
            
            if artist_info.get('url'):
                embed.url = artist_info['url']
            
            await ctx.send(embed=embed)
            
        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(name="whois", aliases=["profile"], usage="lastfm whois [member]")
    @cooldown(1, 5, BucketType.user)
    async def whois(self, ctx: Context, *, user: Optional[discord.Member] = None):
        """View Last.fm profile information"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            
            user_info = await self.client.get_user_info(lastfm_username)
            embed = create_user_info_embed(user_info)
            
            embed.set_author(
                name=f"{discord_user.display_name}'s Last.fm Profile",
                icon_url=discord_user.avatar.url if discord_user.avatar else None
            )
            
            await ctx.send(embed=embed)
            
        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(name="count", aliases=["total"], usage="lastfm count [member]")
    @cooldown(1, 5, BucketType.user)
    async def count(self, ctx: Context, *, user: Optional[discord.Member] = None):
        """View your total Last.fm scrobbles"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            
            user_info = await self.client.get_user_info(lastfm_username)
            
            embed = discord.Embed(
                title="Total Scrobbles",
                color=0x2b2d31,
                description=f"**{discord_user.display_name}** has **{format_playcount(user_info.playcount)}** total scrobbles",
                timestamp=discord.utils.utcnow()
            )
            
            if user_info.url:
                embed.url = user_info.url
            
            await ctx.send(embed=embed)
            
        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(name="whoknows", aliases=["wk"], usage="lastfm whoknows <artist>")
    @cooldown(2, 10, BucketType.guild)
    async def whoknows(self, ctx: Context, *, artist: str):
        """View the top listeners for an artist in a guild"""
        try:
            guild_users = await self.bot.pool.fetch(
                "SELECT user_id, lastfm_username FROM lastfm_users WHERE user_id = ANY($1::BIGINT[])",
                [member.id for member in ctx.guild.members if not member.bot]
            )
            
            if not guild_users:
                await ctx.warn("No users in this server have linked their Last.fm accounts")
                return
            
            who_knows_data = []
            tasks = []
            
            for user_row in guild_users:
                user_id = user_row["user_id"]
                lastfm_username = user_row["lastfm_username"]
                
                member = ctx.guild.get_member(user_id)
                if member:
                    task = self._get_user_playcount(lastfm_username, artist, user_id, member.display_name)
                    tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, WhoKnowsEntry) and result.playcount > 0:
                    who_knows_data.append(result)
            
            if not who_knows_data:
                await ctx.warn(f"No one in this server has listened to **{artist}**")
                return
            
            who_knows_data.sort(key=lambda x: x.playcount, reverse=True)
            
            if len(who_knows_data) <= 15:
                embed = discord.Embed(
                    title=f"{artist} Listeners",
                    color=0x2b2d31,
                    timestamp=discord.utils.utcnow()
                )
                
                description = ""
                for i, entry in enumerate(who_knows_data, 1):
                    crown = "👑 " if i == 1 else ""
                    description += f"`{i}.` {crown}**{entry.username}** - **{format_playcount(entry.playcount)}** plays\n"
                
                embed.description = description
                embed.set_footer(text=f"Total listeners: {len(who_knows_data)}")
                
                await ctx.send(embed=embed)
            else:
                pages = []
                per_page = 15
                
                for i in range(0, len(who_knows_data), per_page):
                    chunk = who_knows_data[i:i+per_page]
                    page_content = ""
                    
                    for j, entry in enumerate(chunk, i + 1):
                        crown = "👑 " if j == 1 else ""
                        page_content += f"`{j}.` {crown}**{entry.username}** - **{format_playcount(entry.playcount)}** plays\n"
                    
                    pages.append(page_content.strip())
                
                embed = discord.Embed(
                    title=f"Who Knows: {artist}",
                    color=0x2b2d31,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_footer(text=f"Total listeners: {len(who_knows_data)}")
                
                paginator = Paginator(ctx, pages=pages, embed=embed, per_page=1)
                await paginator.start()
            
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    async def _get_user_playcount(self, lastfm_username: str, artist: str, user_id: int, display_name: str) -> WhoKnowsEntry:
        try:
            playcount = await self.client.get_artist_playcount(lastfm_username, artist)
            return WhoKnowsEntry(user_id, display_name, playcount, lastfm_username)
        except:
            return WhoKnowsEntry(user_id, display_name, 0, lastfm_username)

    async def get_lastfm_variables(self, ctx: Context, lastfm_username: str) -> dict:
        try:
            user_info = await self.client.get_user_info(lastfm_username)
            recent_tracks = await self.client.get_recent_tracks(lastfm_username, 1)
            
            if recent_tracks:
                track = recent_tracks[0]
                return {
                    "lastfm.username": user_info.username,
                    "lastfm.playcount": format_playcount(user_info.playcount) if user_info.playcount else "0",
                    "lastfm.url": user_info.url or "",
                    "track.name": track.name or "",
                    "track.artist": track.artist or "",
                    "track.album": track.album or "",
                    "track.url": track.url or "",
                    "track.playcount": format_playcount(track.playcount) if track.playcount else "0",
                    "track.image": get_image_url(track.images) or "",
                    "track.status": "Now Playing" if track.now_playing else "Last Played",
                    "track.timestamp": format_time_ago(track.timestamp) if track.timestamp else "",
                    "user.avatar": ctx.author.avatar.url if ctx.author.avatar else "",
                    "user.name": ctx.author.name,
                    "user.mention": ctx.author.mention,
                    "user.display_name": ctx.author.display_name
                }
            else:
                return {
                    "lastfm.username": user_info.username,
                    "lastfm.playcount": format_playcount(user_info.playcount) if user_info.playcount else "0",
                    "lastfm.url": user_info.url or "",
                    "track.name": "",
                    "track.artist": "",
                    "track.album": "",
                    "track.url": "",
                    "track.playcount": "0",
                    "track.image": "",
                    "track.status": "No Recent Tracks",
                    "track.timestamp": "",
                    "user.avatar": ctx.author.avatar.url if ctx.author.avatar else "",
                    "user.name": ctx.author.name,
                    "user.mention": ctx.author.mention,
                    "user.display_name": ctx.author.display_name
                }
        except Exception:
            return {
                "lastfm.username": lastfm_username,
                "lastfm.playcount": "0",
                "lastfm.url": "",
                "track.name": "Error",
                "track.artist": "Error",
                "track.album": "",
                "track.url": "",
                "track.playcount": "0",
                "track.image": "",
                "track.status": "Error Loading Track",
                "track.timestamp": "",
                "user.avatar": ctx.author.avatar.url if ctx.author.avatar else "",
                "user.name": ctx.author.name,
                "user.mention": ctx.author.mention,
                "user.display_name": ctx.author.display_name
            }

    @lastfm.command(name="recommendation", aliases=["recommend"], usage="lastfm recommendation [member]")
    @cooldown(1, 10, BucketType.user)
    async def recommendation(self, ctx: Context, *, user: Optional[discord.Member] = None):
        """Recommends a random artist from your library"""
        try:
            lastfm_username, discord_user = await self.get_user_or_default(ctx, user)
            
            top_artists = await self.client.get_top_artists(lastfm_username, "overall", 100)
            
            if not top_artists:
                await ctx.warn(f"No artists found for **{lastfm_username}**")
                return
            
            recommended = random.choice(top_artists)
            
            embed = discord.Embed(
                title="Artist Recommendation",
                color=0x2b2d31,
                description=f"**[{recommended.name}]({recommended.url})** with **{format_playcount(recommended.playcount)}** plays",
                timestamp=discord.utils.utcnow()
            )
            
            embed.set_author(
                name=f"Recommended for {discord_user.display_name}",
                icon_url=discord_user.avatar.url if discord_user.avatar else None
            )
            
            await ctx.send(embed=embed)
            
        except ValueError as e:
            await ctx.warn(str(e))
        except LastFMError as e:
            await ctx.warn(f"Last.fm error: {e.message}")

    @lastfm.command(name="react", aliases=["reaction", "reactions"], usage="lastfm react <upvote reaction> <downvote reaction>")
    @hybrid_permissions(manage_guild=True)
    async def react(self, ctx: Context, upvote: str, downvote: str):
        """Set server upvote and downvote reaction for Now Playing"""
        await self.bot.pool.execute(
            """
            INSERT INTO lastfm_settings (guild_id, upvote_emoji, downvote_emoji, reactions_enabled)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (guild_id)
            DO UPDATE SET upvote_emoji = $2, downvote_emoji = $3, reactions_enabled = TRUE
            """,
            ctx.guild.id, upvote, downvote
        )
        
        await ctx.approve(f"Set server reactions: {upvote} (upvote) and {downvote} (downvote)")

    @lastfm.command(name="customreactions", aliases=["customreact", "customreaction", "cr"], usage="lastfm customreactions <upvote reaction> <downvote reaction>")
    async def customreactions(self, ctx: Context, upvote: str, downvote: str):
        """Set personal upvote and downvote reaction for Now Playing"""
        await self.bot.pool.execute(
            """
            INSERT INTO lastfm_custom_reactions (user_id, upvote_emoji, downvote_emoji)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET upvote_emoji = $2, downvote_emoji = $3
            """,
            ctx.author.id, upvote, downvote
        )
        
        await ctx.approve(f"Set your custom reactions: {upvote} (upvote) and {downvote} (downvote)")

    @group(name="customcommand", aliases=["customnp", "customfm", "cc"], usage="lastfm customcommand", invoke_without_command=True, parent=lastfm)
    async def customcommand(self, ctx: Context, *, embed_data: str = None):
        """Set your own custom Now Playing command"""
        if ctx.invoked_subcommand is not None:
            return
            
        if not embed_data:
            return await ctx.send_help(ctx.command.qualified_name)
            
        is_blacklisted = await self.bot.pool.fetchval(
            "SELECT 1 FROM lastfm_command_blacklist WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id
        )
        
        if is_blacklisted:
            return await ctx.warn("You are blacklisted from using custom commands in this server")
            
        lastfm_username = await self.get_lastfm_user(ctx.author.id)
        if not lastfm_username:
            return await ctx.warn("You need to link your Last.fm account first with `lastfm login <username>`")
        
        try:
            lastfm_vars = await self.get_lastfm_variables(ctx, lastfm_username)
            sanitized_vars = sanitize_variables(lastfm_vars)
            
            if "{embed}" in embed_data:
                from bot.extensions.embeds import build_embed_from_raw
                test_embed = await build_embed_from_raw(self.bot, ctx, embed_data, extra=sanitized_vars)
            else:
                from bot.extensions.embeds import replace_vars
                test_content = replace_vars(embed_data, ctx, extra=sanitized_vars)
                if len(test_content) > 2000:
                    raise ValueError("Content too long (max 2000 characters)")
            
            await self.bot.pool.execute(
                """
                INSERT INTO lastfm_custom_commands (guild_id, user_id, command_name, embed_data)
                VALUES ($1, $2, 'np', $3)
                ON CONFLICT (guild_id, user_id, command_name)
                DO UPDATE SET embed_data = $3
                """,
                ctx.guild.id, ctx.author.id, embed_data
            )
            
            await ctx.approve("Successfully set your custom Now Playing command")
            
        except Exception as e:
            await ctx.warn(f"Invalid embed format: {str(e)}")

    @customcommand.command(name="public", usage="lastfm customcommand public <command>")
    @hybrid_permissions(manage_guild=True)
    async def customcommand_public(self, ctx: Context, *, member: discord.Member = None):
        """Toggle public flag for a custom command"""
        target_user = member or ctx.author
        
        result = await self.bot.pool.fetchrow(
            "SELECT is_public FROM lastfm_custom_commands WHERE guild_id = $1 AND user_id = $2 AND command_name = 'np'",
            ctx.guild.id, target_user.id
        )
        
        if not result:
            return await ctx.warn(f"{target_user.display_name} doesn't have a custom command set")
        
        new_status = not result["is_public"]
        
        await self.bot.pool.execute(
            "UPDATE lastfm_custom_commands SET is_public = $1 WHERE guild_id = $2 AND user_id = $3 AND command_name = 'np'",
            new_status, ctx.guild.id, target_user.id
        )
        
        status_text = "public" if new_status else "private"
        await ctx.approve(f"Set {target_user.display_name}'s custom command to **{status_text}**")

    @customcommand.group(name="blacklist", aliases=["bl"], usage="lastfm customcommand blacklist", invoke_without_command=True)
    @hybrid_permissions(manage_guild=True)
    async def customcommand_blacklist(self, ctx: Context, member: discord.Member):
        """Blacklist users from their own Now Playing command"""
        existing = await self.bot.pool.fetchval(
            "SELECT 1 FROM lastfm_command_blacklist WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        if existing:
            return await ctx.warn(f"{member.display_name} is already blacklisted from custom commands")
        
        await self.bot.pool.execute(
            "INSERT INTO lastfm_command_blacklist (guild_id, user_id, blacklisted_by) VALUES ($1, $2, $3)",
            ctx.guild.id, member.id, ctx.author.id
        )
        
        await ctx.approve(f"Blacklisted {member.display_name} from using custom commands")

    @customcommand_blacklist.command(name="list", aliases=["view", "check"], usage="lastfm customcommand blacklist list")
    @hybrid_permissions(manage_guild=True)
    async def blacklist_list(self, ctx: Context):
        """View list of blacklisted custom command users for NP"""
        blacklisted = await self.bot.pool.fetch(
            "SELECT user_id, blacklisted_by, blacklisted_at FROM lastfm_command_blacklist WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not blacklisted:
            return await ctx.warn("No users are blacklisted from custom commands")
        
        formatted = []
        for entry in blacklisted:
            user = self.bot.get_user(entry["user_id"])
            blacklisted_by = self.bot.get_user(entry["blacklisted_by"])
            
            user_name = user.display_name if user else f"Unknown User ({entry['user_id']})"
            by_name = blacklisted_by.display_name if blacklisted_by else f"Unknown User ({entry['blacklisted_by']})"
            
            timestamp = entry["blacklisted_at"].strftime("%m/%d/%Y")
            formatted.append(f"**{user_name}** - by {by_name} ({timestamp})")
        
        embed = discord.Embed(
            title="Blacklisted Users",
            color=0x2b2d31,
            timestamp=discord.utils.utcnow()
        )
        
        paginator = Paginator(ctx, pages=formatted, embed=embed, per_page=10)
        await paginator.start()

    @customcommand.command(name="remove", usage="lastfm customcommand remove <member>")
    @hybrid_permissions(manage_guild=True)
    async def customcommand_remove(self, ctx: Context, member: discord.Member):
        """Remove a custom command for a member"""
        result = await self.bot.pool.execute(
            "DELETE FROM lastfm_custom_commands WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        blacklist_result = await self.bot.pool.execute(
            "DELETE FROM lastfm_command_blacklist WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        if result == "DELETE 0" and blacklist_result == "DELETE 0":
            return await ctx.warn(f"{member.display_name} doesn't have any custom commands or blacklist entries")
        
        await ctx.approve(f"Removed all custom commands and blacklist entries for {member.display_name}")

    @customcommand.command(name="cleanup", usage="lastfm customcommand cleanup")
    @hybrid_permissions(administrator=True)
    async def customcommand_cleanup(self, ctx: Context):
        """Clean up custom commands from absent members"""
        all_commands = await self.bot.pool.fetch(
            "SELECT DISTINCT user_id FROM lastfm_custom_commands WHERE guild_id = $1",
            ctx.guild.id
        )
        
        removed = 0
        for row in all_commands:
            member = ctx.guild.get_member(row["user_id"])
            if not member:
                await self.bot.pool.execute(
                    "DELETE FROM lastfm_custom_commands WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id, row["user_id"]
                )
                await self.bot.pool.execute(
                    "DELETE FROM lastfm_command_blacklist WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id, row["user_id"]
                )
                removed += 1
        
        await ctx.approve(f"Cleaned up {removed} custom commands from absent members")

    @customcommand.command(name="list", usage="lastfm customcommand list")
    @hybrid_permissions(manage_guild=True)
    async def customcommand_list(self, ctx: Context):
        """View list of custom commands for NP"""
        commands = await self.bot.pool.fetch(
            "SELECT user_id, is_public, created_at FROM lastfm_custom_commands WHERE guild_id = $1 ORDER BY created_at DESC",
            ctx.guild.id
        )
        
        if not commands:
            return await ctx.warn("No custom commands found in this server")
        
        formatted = []
        for cmd in commands:
            user = ctx.guild.get_member(cmd["user_id"])
            if not user:
                continue
                
            status = "Public" if cmd["is_public"] else "Private"
            timestamp = cmd["created_at"].strftime("%m/%d/%Y")
            formatted.append(f"**{user.display_name}** - {status} ({timestamp})")
        
        embed = discord.Embed(
            title="Custom Commands",
            color=0x2b2d31,
            timestamp=discord.utils.utcnow()
        )
        
        if formatted:
            paginator = Paginator(ctx, pages=formatted, embed=embed, per_page=15)
            await paginator.start()
        else:
            embed.description = "No active custom commands found"
            await ctx.send(embed=embed)

    @customcommand.command(name="reset", aliases=["clear"], usage="lastfm customcommand reset")
    @hybrid_permissions(manage_guild=True)
    async def customcommand_reset(self, ctx: Context):
        """Resets all custom commands"""
        commands_result = await self.bot.pool.execute(
            "DELETE FROM lastfm_custom_commands WHERE guild_id = $1",
            ctx.guild.id
        )
        
        blacklist_result = await self.bot.pool.execute(
            "DELETE FROM lastfm_command_blacklist WHERE guild_id = $1",
            ctx.guild.id
        )
        
        commands_count = int(commands_result.split()[-1]) if commands_result != "DELETE 0" else 0
        blacklist_count = int(blacklist_result.split()[-1]) if blacklist_result != "DELETE 0" else 0
        
        await ctx.approve(f"Reset **{commands_count}** custom commands and **{blacklist_count}** blacklist entries")

@command(name="nowplaying", aliases=["np", "fm", "now"], usage="nowplaying [member]")
@cooldown(1, 5, BucketType.user)
async def nowplaying_standalone(ctx: Context, *, user: Optional[discord.Member] = None):
    """Shows your current song playing from Last.fm"""
    lastfm_cog = ctx.bot.get_cog("LastFM")
    if lastfm_cog:
        await lastfm_cog.now(ctx, user=user)
    else:
        await ctx.warn("Last.fm functionality is not available")

async def setup(bot: Bot):
    await bot.add_cog(LastFM(bot))
    bot.add_command(nowplaying_standalone) 