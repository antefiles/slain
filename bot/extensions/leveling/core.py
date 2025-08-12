from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict, deque
import random


SPEED_MAP = {
    1: 0.25,
    2: 0.5,
    3: 1.0,
    4: 1.5,
    5: 2.0
}

DEFAULT_SPEED = 3
XP_COOLDOWN_SECONDS = 60

class LevelManager:
    def __init__(self, pool):
        self.pool = pool
        self.spam_tracker = defaultdict(lambda: deque(maxlen=5))  # last 5 messages per user

    def xp_for_level(self, level: int) -> int:
        if level <= 1:
            return 0
        return 15 * ((level - 1) ** 2) + 60 * (level - 1) + 100

    def generate_xp(self, speed: int = DEFAULT_SPEED) -> int:
        base = random.randint(1, 8)
        return int(base * SPEED_MAP.get(speed, 0.3))

    async def get_user_data(self, user_id: int, guild_id: int):
        return await self.pool.fetchrow(
            "SELECT xp, level, last_xp FROM user_levels WHERE user_id = $1 AND guild_id = $2",
            user_id, guild_id
        )

    def on_xp_cooldown(self, last_xp_time: Optional[datetime]) -> bool:
        if not last_xp_time:
            return False
        return (datetime.utcnow() - last_xp_time).total_seconds() < XP_COOLDOWN_SECONDS

    def get_level_from_xp(self, xp: int) -> int:
        level = 1
        while xp >= self.xp_for_level(level + 1):
            level += 1
        return level

    def is_spamming(self, user_id: int) -> bool:
        now = datetime.utcnow()
        history = self.spam_tracker[user_id]
        history.append(now)

        return len(history) >= 5 and (now - history[0]).total_seconds() < 10

    def build_progress_bar(
        self,
        current_xp: int,
        next_level_xp: int,
        length: int = 8,
        *,
        start_emoji: str = "<:slainprogress_1:1395780651705438269>",
        fill_emoji: str = "<:slainprogress_2:1395780740825878538>",
        empty_emoji: str = "<:slain_noprogress:1395780839337492552>",
        end_emoji: str = "<:slainprogress_3:1395780800028348568>",
        end_empty_emoji: str = "<:slain_end_noprogress:1395784983938859058>"
    ) -> str:
        percent = min(current_xp / next_level_xp, 1.0) if next_level_xp > 0 else 0.0
        filled = int(length * percent)
        empty = length - filled

        end = end_emoji if filled == length else end_empty_emoji
        bar = start_emoji + (fill_emoji * filled) + (empty_emoji * empty) + end
        return f"{bar} ({int(percent * 100)}%)"
