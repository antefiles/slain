from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class LastFMImage:
    size: str
    url: str

@dataclass
class LastFMTrack:
    name: str
    artist: str
    album: Optional[str] = None
    playcount: Optional[int] = None
    url: Optional[str] = None
    images: Optional[List[LastFMImage]] = None
    now_playing: bool = False
    timestamp: Optional[datetime] = None
    mbid: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LastFMTrack':
        images = []
        if 'image' in data:
            for img in data['image']:
                images.append(LastFMImage(size=img['size'], url=img['#text']))
        
        timestamp = None
        if 'date' in data and 'uts' in data['date']:
            timestamp = datetime.fromtimestamp(int(data['date']['uts']))
        
        return cls(
            name=data.get('name', ''),
            artist=data.get('artist', {}).get('#text', '') if isinstance(data.get('artist'), dict) else data.get('artist', ''),
            album=data.get('album', {}).get('#text', '') if data.get('album') else None,
            playcount=int(data.get('playcount', 0)) if data.get('playcount') else None,
            url=data.get('url', ''),
            images=images if images else None,
            now_playing=data.get('@attr', {}).get('nowplaying') == 'true',
            timestamp=timestamp,
            mbid=data.get('mbid', '')
        )

@dataclass
class LastFMArtist:
    name: str
    playcount: Optional[int] = None
    url: Optional[str] = None
    images: Optional[List[LastFMImage]] = None
    mbid: Optional[str] = None
    listeners: Optional[int] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LastFMArtist':
        images = []
        if 'image' in data:
            for img in data['image']:
                images.append(LastFMImage(size=img['size'], url=img['#text']))
        
        return cls(
            name=data.get('name', ''),
            playcount=int(data.get('playcount', 0)) if data.get('playcount') else None,
            url=data.get('url', ''),
            images=images if images else None,
            mbid=data.get('mbid', ''),
            listeners=int(data.get('listeners', 0)) if data.get('listeners') else None
        )

@dataclass
class LastFMAlbum:
    name: str
    artist: str
    playcount: Optional[int] = None
    url: Optional[str] = None
    images: Optional[List[LastFMImage]] = None
    mbid: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LastFMAlbum':
        images = []
        if 'image' in data:
            for img in data['image']:
                images.append(LastFMImage(size=img['size'], url=img['#text']))
        
        return cls(
            name=data.get('name', ''),
            artist=data.get('artist', {}).get('name', '') if isinstance(data.get('artist'), dict) else data.get('artist', ''),
            playcount=int(data.get('playcount', 0)) if data.get('playcount') else None,
            url=data.get('url', ''),
            images=images if images else None,
            mbid=data.get('mbid', '')
        )

@dataclass
class LastFMUser:
    username: str
    real_name: Optional[str] = None
    playcount: Optional[int] = None
    url: Optional[str] = None
    images: Optional[List[LastFMImage]] = None
    registered: Optional[datetime] = None
    country: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LastFMUser':
        images = []
        if 'image' in data:
            for img in data['image']:
                images.append(LastFMImage(size=img['size'], url=img['#text']))
        
        registered = None
        if 'registered' in data and 'unixtime' in data['registered']:
            registered = datetime.fromtimestamp(int(data['registered']['unixtime']))
        
        return cls(
            username=data.get('name', ''),
            real_name=data.get('realname', ''),
            playcount=int(data.get('playcount', 0)) if data.get('playcount') else None,
            url=data.get('url', ''),
            images=images if images else None,
            registered=registered,
            country=data.get('country', '')
        )

@dataclass
class WhoKnowsEntry:
    user_id: int
    username: str
    playcount: int
    lastfm_username: str 