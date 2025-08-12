CREATE TABLE IF NOT EXISTS oauth (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    token TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE SCHEMA IF NOT EXISTS voicemaster;

CREATE TABLE IF NOT EXISTS voicemaster.config (
    guild_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    panel_id BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS voicemaster.channel (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    owner_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS config (
    guild_id BIGINT PRIMARY KEY,
    prefix TEXT
);

CREATE TABLE IF NOT EXISTS user_config (
    user_id BIGINT PRIMARY KEY,
    prefix TEXT
);


CREATE TABLE IF NOT EXISTS blacklist (
    target_id BIGINT PRIMARY KEY,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS warn_config (
    guild_id BIGINT PRIMARY KEY,
    default_threshold INTEGER DEFAULT 3,
    default_action TEXT,  -- 'timeout', 'kick', 'ban', or NULL (meaning disabled)
    timeout_duration INTERVAL  -- only used if default_action = 'timeout'
);

CREATE TABLE IF NOT EXISTS warn_role_config (
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    threshold INTEGER NOT NULL,
    action TEXT NOT NULL,  -- 'timeout', 'kick', 'ban'
    timeout_duration INTERVAL,  -- only used if action = 'timeout'
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS warn_exempt (
    guild_id BIGINT NOT NULL,
    user_id BIGINT,
    role_id BIGINT,
    exempted_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(guild_id, user_id),
    UNIQUE(guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS warn_bypass (
    guild_id BIGINT NOT NULL,
    user_id BIGINT,
    role_id BIGINT,
    added_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, user_id),
    UNIQUE(guild_id, role_id),
    CHECK (
        (user_id IS NULL AND role_id IS NOT NULL) OR
        (user_id IS NOT NULL AND role_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS embeds (
    user_id BIGINT NOT NULL,
    embed_name TEXT NOT NULL,
    embed_data JSONB NOT NULL,
    PRIMARY KEY (user_id, embed_name)
);

CREATE TABLE IF NOT EXISTS persistent_buttons (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    custom_id TEXT UNIQUE,
    label TEXT NOT NULL,
    style SMALLINT NOT NULL,
    emoji TEXT,
    response TEXT NOT NULL,
    embed_raw TEXT
);

CREATE TABLE IF NOT EXISTS user_rate_limits (
    user_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    command_category TEXT NOT NULL,
    usage_count INTEGER DEFAULT 0,
    last_used TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reputation_score INTEGER DEFAULT 100,
    current_cooldown INTERVAL DEFAULT '0 seconds',
    PRIMARY KEY (user_id, guild_id, command_category)
);

CREATE TABLE IF NOT EXISTS favorite_commands (
    user_id BIGINT NOT NULL,
    command_name TEXT NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, command_name)
);

CREATE TABLE IF NOT EXISTS emoji_limits (
    guild_id BIGINT PRIMARY KEY,
    emoji_actions INTEGER NOT NULL DEFAULT 0,
    last_reset TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS emoji_usage (
    guild_id BIGINT NOT NULL,
    emoji_id BIGINT NOT NULL,
    usage_count INTEGER DEFAULT 1,
    PRIMARY KEY (guild_id, emoji_id)
);

CREATE TABLE IF NOT EXISTS user_timezones (
    user_id BIGINT PRIMARY KEY,
    timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS welcome_messages (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    content TEXT,
    embed_data JSONB,
    raw TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS boost_messages (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goodbye_messages (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fake_permissions (
    guild_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    permission TEXT NOT NULL,
    added_by BIGINT,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, role_id, permission)
);
CREATE TABLE IF NOT EXISTS leveling_settings (
    guild_id BIGINT PRIMARY KEY,
    speed INTEGER DEFAULT 3,
    enabled BOOLEAN DEFAULT TRUE,
    stack_roles BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS user_levels (
    user_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    xp INT DEFAULT 0,
    level INT DEFAULT 0,
    last_xp TIMESTAMP,
    PRIMARY KEY (user_id, guild_id)
);
CREATE TABLE IF NOT EXISTS level_roles (
    guild_id BIGINT NOT NULL,
    level INT NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, level)
);
CREATE TABLE IF NOT EXISTS level_messages (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lastfm_users (
    user_id BIGINT PRIMARY KEY,
    lastfm_username TEXT NOT NULL,
    registered_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lastfm_settings (
    guild_id BIGINT PRIMARY KEY,
    upvote_emoji TEXT,
    downvote_emoji TEXT,
    reactions_enabled BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS lastfm_custom_reactions (
    user_id BIGINT PRIMARY KEY,
    upvote_emoji TEXT,
    downvote_emoji TEXT
);

CREATE TABLE IF NOT EXISTS lastfm_cache (
    guild_id BIGINT,
    user_id BIGINT,
    artist_name TEXT,
    playcount INTEGER,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id, artist_name)
);

CREATE TABLE IF NOT EXISTS lastfm_custom_commands (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    command_name TEXT NOT NULL,
    embed_data TEXT NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id, command_name)
);

CREATE TABLE IF NOT EXISTS lastfm_command_blacklist (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    blacklisted_by BIGINT NOT NULL,
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);