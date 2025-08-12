import time
from datetime import datetime
from collections import defaultdict

class CooldownManager:
    def __init__(self):
        # Stores the timestamps of last event triggers by event name
        self.cooldowns = defaultdict(float)
        # Stores last warning timestamp per user+command to prevent spam
        self.warn_cache: dict[tuple[int, str], datetime] = {}

    def is_on_cooldown(self, event_name: str, cooldown_time: float) -> bool:
        current_time = time.time()
        return current_time - self.cooldowns[event_name] < cooldown_time

    def apply_cooldown(self, event_name: str) -> None:
        self.cooldowns[event_name] = time.time()

    def get_time_remaining(self, event_name: str, cooldown_time: float) -> float:
        current_time = time.time()
        elapsed_time = current_time - self.cooldowns[event_name]
        return max(cooldown_time - elapsed_time, 0)

    def should_send_cooldown_warning(self, user_id: int, command_name: str, cooldown_seconds: float) -> bool:
        now = datetime.utcnow()
        key = (user_id, command_name)
        last_sent = self.warn_cache.get(key)

        if not last_sent or (now - last_sent).total_seconds() > cooldown_seconds:
            self.warn_cache[key] = now
            return True
        return False