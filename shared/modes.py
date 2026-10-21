"""Match modes: 1v1..5v5 team fights, free-for-all, and cooperative PvE.
Limits are module-level so the server can override them from its command line."""
MODE_ORDER = ("1v1", "2v2", "3v3", "4v4", "5v5", "ffa", "coop")
FLEX_MODES = {"ffa": (2, 8), "coop": (2, 4)}      # mode -> (min players, max players)
FLEX_START_DELAY = 6.0                            # wait this long after the minimum is reached
FFA_MIN, FFA_MAX, FFA_START_DELAY = 2, 8, FLEX_START_DELAY
KILL_TARGET_FFA = 10
KILL_TARGET_OVERRIDE = None
TIME_LIMIT = 180.0
COOP_TIME_LIMIT = 240.0
COUNTDOWN = 3.0
RESPAWN_TIME = 3.0
ARENA_LEVEL = 30          # "normalized" ruleset: everyone fights at this level
COOP_DUNGEON = 12         # co-op enemies are those of dungeon level 12 (enemy level 29)


def configure(time_limit=None, kill_limit=None, respawn=None):
    global TIME_LIMIT, KILL_TARGET_OVERRIDE, RESPAWN_TIME
    if time_limit:
        TIME_LIMIT = float(time_limit)
    if kill_limit:
        KILL_TARGET_OVERRIDE = int(kill_limit)
    if respawn is not None:
        RESPAWN_TIME = float(respawn)


def is_team_mode(mode: str) -> bool:
    return mode in MODE_ORDER and mode not in FLEX_MODES


def is_flex_mode(mode: str) -> bool:
    return mode in FLEX_MODES


def team_size(mode: str) -> int:
    return int(mode[0]) if is_team_mode(mode) else 0


def players_needed(mode: str, allow_small: bool = False) -> int:
    """Players required to start. `allow_small` is a TESTING option: team modes then start
    with one player per team, co-op with one player (free-for-all always needs two)."""
    if is_team_mode(mode):
        return 2 if allow_small else 2 * team_size(mode)
    lo = FLEX_MODES[mode][0]
    return 1 if (allow_small and mode == "coop") else lo


def max_players(mode: str) -> int:
    return 2 * team_size(mode) if is_team_mode(mode) else FLEX_MODES[mode][1]


def kill_target(mode: str) -> int:
    if KILL_TARGET_OVERRIDE:
        return KILL_TARGET_OVERRIDE
    return 5 * team_size(mode) + 5 if is_team_mode(mode) else KILL_TARGET_FFA


def mode_label(mode: str) -> str:
    return {"ffa": "Free For All", "coop": "Co-op PvE"}.get(mode, mode)
