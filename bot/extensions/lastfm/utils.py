import discord
import re
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from .models import LastFMTrack, LastFMArtist, LastFMAlbum, LastFMUser, LastFMImage

def format_playcount(count: int) -> str:
    if count >= 1000000:
        return f"{count/1000000:.1f}M"
    elif count >= 1000:
        return f"{count/1000:.1f}K"
    else:
        return str(count)

def format_time_ago(timestamp: datetime) -> str:
    if not timestamp:
        return "Unknown"
    
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    diff = now - timestamp
    total_seconds = int(diff.total_seconds())
    
    if total_seconds < 60:
        return "Just now"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes}m ago"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours}h ago"
    elif total_seconds < 2592000:
        days = total_seconds // 86400
        return f"{days}d ago"
    else:
        months = total_seconds // 2592000
        return f"{months}mo ago"

def get_period_display(period: str) -> str:
    period_map = {
        'overall': 'All Time',
        '7day': 'Past Week',
        '1month': 'Past Month',
        '3month': 'Past 3 Months',
        '6month': 'Past 6 Months',
        '12month': 'Past Year'
    }
    return period_map.get(period.lower(), period.title())

def get_image_url(images: Optional[List[LastFMImage]], size: str = 'large') -> Optional[str]:
    if not images:
        return None
    
    size_priority = ['extralarge', 'large', 'medium', 'small']
    if size not in size_priority:
        size = 'large'
    
    for img in images:
        if img.size == size and img.url:
            return img.url
    
    for priority_size in size_priority:
        for img in images:
            if img.size == priority_size and img.url:
                return img.url
    
    return None

def parse_artist_track(query: str) -> Tuple[str, Optional[str]]:
    if ' - ' in query:
        parts = query.split(' - ', 1)
        return parts[0].strip(), parts[1].strip()
    return query.strip(), None

def create_now_playing_embed(track: LastFMTrack, user: LastFMUser) -> discord.Embed:
    if track.now_playing:
        title = f"🎵 Currently Playing"
    else:
        title = f"🎵 Last Played"
    
    embed = discord.Embed(
        title=title,
        color=0xacacac,
        description=f"**[{track.name}]({track.url})** by **{track.artist}**",
        timestamp=discord.utils.utcnow()
    )
    
    if track.album:
        embed.add_field(name="Album", value=track.album, inline=True)
    
    if track.playcount:
        embed.add_field(name="User Scrobbles", value=format_playcount(track.playcount), inline=True)
    
    if track.timestamp and not track.now_playing:
        embed.add_field(name="Played", value=format_time_ago(track.timestamp), inline=True)
    
    embed.set_author(
        name=f"{user.username}",
        url=user.url,
        icon_url=get_image_url(user.images, 'medium')
    )
    
    image_url = get_image_url(track.images)
    if image_url:
        embed.set_thumbnail(url=image_url)
    
    if user.playcount:
        embed.set_footer(text=f"Total Scrobbles: {format_playcount(user.playcount)}")
    
    return embed



def create_user_info_embed(user: LastFMUser) -> discord.Embed:
    embed = discord.Embed(
        title=f"Last.fm Profile",
        color=0xacacac,
        url=user.url,
        timestamp=discord.utils.utcnow()
    )
    
    description = f"**Username:** {user.username}\n"
    
    if user.real_name:
        description += f"**Real Name:** {user.real_name}\n"
    
    if user.country:
        description += f"**Country:** {user.country}\n"
    
    if user.playcount:
        description += f"**Total Scrobbles:** {format_playcount(user.playcount)}\n"
    
    if user.registered:
        description += f"**Registered:** {user.registered.strftime('%B %d, %Y')}\n"
    
    embed.description = description
    
    image_url = get_image_url(user.images, 'large')
    if image_url:
        embed.set_thumbnail(url=image_url)
    
    return embed

def validate_period(period: str) -> str:
    valid_periods = ['overall', '7day', '1month', '3month', '6month', '12month']
    period_aliases = {
        'week': '7day',
        'weekly': '7day',
        'month': '1month',
        'monthly': '1month',
        '3m': '3month',
        '6m': '6month',
        'year': '12month',
        'yearly': '12month',
        'all': 'overall',
        'alltime': 'overall'
    }
    
    period = period.lower().strip()
    
    if period in valid_periods:
        return period
    
    if period in period_aliases:
        return period_aliases[period]
    
    return 'overall' 