"""Central configuration. Tweak values here."""

SCREEN_W, SCREEN_H = 960, 540
FPS = 60
TITLE = "Online Fighting RPG"

GRAVITY = 1900.0
MAX_FALL_SPEED = 1200.0
LEVEL_WIDTH = 5200
GROUND_Y = 460

# Set True to enable developer shortcuts on the Home screen (see README):
# F1/F2/F3/F4 = +1/+10/+100/+1000 levels, F5 = +1000 gold and +20 of every material.
DEV_MODE = False

# Configurable difficulty / reward multipliers.
DIFFICULTY = {"enemy_hp": 1.0, "enemy_damage": 1.0, "xp": 1.0, "drop_chance": 1.0}
KILLS_PER_LEVEL = 6          # an on-level weight-1.0 enemy gives 1/6 of a level
MATERIAL_DROP_CHANCE = 0.40

PLAYER = dict(
    width=34, height=60, jump_speed=720,
    hurt_invuln=0.8, hurt_stun=0.25,
    dodge_speed=620, dodge_time=0.18, dodge_cooldown=0.8,
)

# min_level = enemy level at which the type starts appearing. tier raises its spawn weight.
# xp_weight multiplies the XP an on-level enemy gives. "ranged" enemies shoot projectiles.
ENEMY_TYPES = {
    "grunt": dict(name="Grunt", color=(190, 70, 70), width=36, height=58, hp=45, speed=95,
                  damage=10, knockback=260, aggro=420, attack_range=48, windup=0.35,
                  attack_cooldown=1.2, hurt_time=0.3, xp_weight=1.0, drop_chance=0.35,
                  item_chance=0.08, min_level=1, tier=0),
    "runner": dict(name="Runner", color=(230, 170, 50), width=30, height=50, hp=30, speed=210,
                   damage=14, knockback=300, aggro=520, attack_range=44, windup=0.2,
                   attack_cooldown=0.9, hurt_time=0.2, xp_weight=1.3, drop_chance=0.40,
                   item_chance=0.10, min_level=1, tier=0),
    "brute": dict(name="Brute", color=(110, 60, 150), width=54, height=82, hp=140, speed=60,
                  damage=30, knockback=650, aggro=380, attack_range=70, windup=0.7,
                  attack_cooldown=2.0, hurt_time=0.12, xp_weight=3.0, drop_chance=0.70,
                  item_chance=0.35, min_level=1, tier=0),
    "skeleton": dict(name="Skeleton", color=(205, 205, 190), width=36, height=60, hp=70, speed=110,
                     damage=14, knockback=280, aggro=450, attack_range=52, windup=0.30,
                     attack_cooldown=1.0, hurt_time=0.25, xp_weight=1.8, drop_chance=0.40,
                     item_chance=0.12, min_level=25, tier=1),
    "slinger": dict(name="Slinger", color=(120, 170, 90), width=32, height=56, hp=40, speed=90,
                    damage=12, knockback=160, aggro=600, attack_range=380, windup=0.5,
                    attack_cooldown=1.8, hurt_time=0.3, xp_weight=1.6, drop_chance=0.40,
                    item_chance=0.12, min_level=25, tier=1, ranged=True, proj_speed=420),
    "wraith": dict(name="Wraith", color=(120, 140, 220), width=34, height=62, hp=60, speed=230,
                   damage=24, knockback=300, aggro=600, attack_range=50, windup=0.20,
                   attack_cooldown=0.8, hurt_time=0.15, xp_weight=3.5, drop_chance=0.45,
                   item_chance=0.15, min_level=100, tier=2),
    "golem": dict(name="Golem", color=(140, 120, 90), width=70, height=100, hp=420, speed=50,
                  damage=40, knockback=900, aggro=420, attack_range=80, windup=0.9,
                  attack_cooldown=2.4, hurt_time=0.05, xp_weight=6.0, drop_chance=0.70,
                  item_chance=0.30, min_level=200, tier=3),
    "warlock": dict(name="Warlock", color=(190, 60, 160), width=34, height=64, hp=110, speed=100,
                    damage=48, knockback=300, aggro=700, attack_range=450, windup=0.6,
                    attack_cooldown=1.6, hurt_time=0.2, xp_weight=5.0, drop_chance=0.50,
                    item_chance=0.20, min_level=350, tier=4, ranged=True, proj_speed=520),
    "demon": dict(name="Demon", color=(210, 40, 40), width=60, height=90, hp=600, speed=150,
                  damage=55, knockback=700, aggro=600, attack_range=70, windup=0.45,
                  attack_cooldown=1.2, hurt_time=0.1, xp_weight=8.0, drop_chance=0.60,
                  item_chance=0.30, min_level=500, tier=5),
    "dragon": dict(name="Dragon", color=(230, 120, 30), width=90, height=110, hp=1500, speed=130,
                   damage=90, knockback=1000, aggro=700, attack_range=100, windup=0.8,
                   attack_cooldown=2.0, hurt_time=0.05, xp_weight=20.0, drop_chance=0.80,
                   item_chance=0.40, min_level=1000, tier=6),
    "titan": dict(name="Titan", color=(240, 220, 120), width=100, height=130, hp=4000, speed=110,
                  damage=150, knockback=1200, aggro=700, attack_range=110, windup=1.0,
                  attack_cooldown=2.2, hurt_time=0.02, xp_weight=40.0, drop_chance=0.90,
                  item_chance=0.50, min_level=2000, tier=7),
}
ENEMY_HIT_INVULN = 0.15
ENEMY_RESPAWN_TIME = 12.0

PLATFORMS = [(500, 380, 200), (900, 320, 180), (1350, 360, 220), (1700, 300, 200),
             (2200, 370, 260), (2650, 310, 200), (3100, 360, 220), (3600, 300, 220),
             (4100, 360, 260), (4600, 320, 200)]
PLATFORM_THICKNESS = 16

# The last spawn is the "boss" slot (the strongest type available at that dungeon level).
SPAWN_XS = [900, 1250, 1600, 1950, 2300, 2650, 3000, 3350, 3700, 4050, 4400, 4800]
PLAYER_SPAWN = (100, GROUND_Y - PLAYER["height"])

MAX_DUNGEON = 100
