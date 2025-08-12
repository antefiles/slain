import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from os import environ
from .models import LastFMTrack, LastFMArtist, LastFMAlbum, LastFMUser

class LastFMError(Exception):
    def __init__(self, message: str, code: int = None):
        self.message = message
        self.code = code
        super().__init__(message)

class LastFMClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.api_key = environ.get('LASTFM_KEY')
        self.base_url = 'https://ws.audioscrobbler.com/2.0/'
        self.rate_limiter = asyncio.Semaphore(5)
        
        if not self.api_key:
            raise ValueError("LASTFM_KEY environment variable not set")

    async def _request(self, method: str, params: Dict[str, str]) -> Dict[str, Any]:
        params.update({
            'method': method,
            'api_key': self.api_key,
            'format': 'json'
        })
        
        async with self.rate_limiter:
            try:
                async with self.session.get(self.base_url, params=params) as response:
                    data = await response.json()
                    
                    if response.status != 200:
                        raise LastFMError(f"HTTP {response.status}", response.status)
                    
                    if 'error' in data:
                        error_messages = {
                            2: "Invalid service",
                            3: "Invalid method", 
                            4: "Authentication failed",
                            5: "Invalid format",
                            6: "Invalid parameters",
                            7: "Invalid resource specified",
                            8: "Operation failed",
                            9: "Invalid session key",
                            10: "Invalid API key",
                            11: "Service temporarily offline",
                            13: "Invalid method signature",
                            16: "Temporary error processing request",
                            26: "Suspended API key",
                            29: "Rate limit exceeded"
                        }
                        
                        error_code = data.get('error', 8)
                        error_message = error_messages.get(error_code, data.get('message', 'Unknown error'))
                        raise LastFMError(error_message, error_code)
                    
                    return data
                    
            except aiohttp.ClientError as e:
                raise LastFMError(f"Network error: {str(e)}")
            
            await asyncio.sleep(0.2)

    async def get_user_info(self, username: str) -> LastFMUser:
        data = await self._request('user.getinfo', {'user': username})
        return LastFMUser.from_dict(data['user'])

    async def get_recent_tracks(self, username: str, limit: int = 10) -> List[LastFMTrack]:
        params = {'user': username, 'limit': str(limit)}
        data = await self._request('user.getrecenttracks', params)
        
        tracks = []
        if 'recenttracks' in data and 'track' in data['recenttracks']:
            track_data = data['recenttracks']['track']
            if isinstance(track_data, dict):
                track_data = [track_data]
                
            for track in track_data:
                tracks.append(LastFMTrack.from_dict(track))
        
        return tracks

    async def get_top_artists(self, username: str, period: str = 'overall', limit: int = 10) -> List[LastFMArtist]:
        params = {'user': username, 'period': period, 'limit': str(limit)}
        data = await self._request('user.gettopartists', params)
        
        artists = []
        if 'topartists' in data and 'artist' in data['topartists']:
            artist_data = data['topartists']['artist']
            if isinstance(artist_data, dict):
                artist_data = [artist_data]
                
            for artist in artist_data:
                artists.append(LastFMArtist.from_dict(artist))
        
        return artists

    async def get_top_albums(self, username: str, period: str = 'overall', limit: int = 10) -> List[LastFMAlbum]:
        params = {'user': username, 'period': period, 'limit': str(limit)}
        data = await self._request('user.gettopalbums', params)
        
        albums = []
        if 'topalbums' in data and 'album' in data['topalbums']:
            album_data = data['topalbums']['album']
            if isinstance(album_data, dict):
                album_data = [album_data]
                
            for album in album_data:
                albums.append(LastFMAlbum.from_dict(album))
        
        return albums

    async def get_top_tracks(self, username: str, period: str = 'overall', limit: int = 10) -> List[LastFMTrack]:
        params = {'user': username, 'period': period, 'limit': str(limit)}
        data = await self._request('user.gettoptracks', params)
        
        tracks = []
        if 'toptracks' in data and 'track' in data['toptracks']:
            track_data = data['toptracks']['track']
            if isinstance(track_data, dict):
                track_data = [track_data]
                
            for track in track_data:
                tracks.append(LastFMTrack.from_dict(track))
        
        return tracks

    async def get_artist_playcount(self, username: str, artist: str) -> int:
        params = {'user': username, 'artist': artist}
        try:
            data = await self._request('artist.getinfo', params)
            stats = data.get('artist', {}).get('stats', {})
            return int(stats.get('userplaycount', 0))
        except LastFMError:
            return 0

    async def get_album_playcount(self, username: str, artist: str, album: str) -> int:
        params = {'user': username, 'artist': artist, 'album': album}
        try:
            data = await self._request('album.getinfo', params)
            stats = data.get('album', {}).get('userplaycount', 0)
            return int(stats) if stats else 0
        except LastFMError:
            return 0

    async def get_track_playcount(self, username: str, artist: str, track: str) -> int:
        params = {'user': username, 'artist': artist, 'track': track}
        try:
            data = await self._request('track.getinfo', params)
            stats = data.get('track', {}).get('userplaycount', 0)
            return int(stats) if stats else 0
        except LastFMError:
            return 0

    async def get_artist_info(self, artist: str) -> Dict[str, Any]:
        params = {'artist': artist}
        data = await self._request('artist.getinfo', params)
        return data.get('artist', {})

    async def search_artist(self, query: str, limit: int = 10) -> List[LastFMArtist]:
        params = {'artist': query, 'limit': str(limit)}
        data = await self._request('artist.search', params)
        
        artists = []
        if 'results' in data and 'artistmatches' in data['results'] and 'artist' in data['results']['artistmatches']:
            artist_data = data['results']['artistmatches']['artist']
            if isinstance(artist_data, dict):
                artist_data = [artist_data]
                
            for artist in artist_data:
                artists.append(LastFMArtist.from_dict(artist))
        
        return artists 