"""
PIXEL FIGHTER - a single-file arcade fighter built with pygame-ce.

Assets (CraftPix free downloads, see assets/licenses/CREDITS.txt):
  assets/hero/      Pack 2   - combat moves (Punch_1, Punch_2, Kick, Dodge, Hurt)
  assets/proto/     Pack 405285 - locomotion (idle, run, jump)
  assets/hero_alt/  Pack 3   - darker palette and attack sheets for arcade rivals

Sprite sheets are horizontal strips of 128px-wide cells. Cell height equals the
sheet height, because some sheets are 64px tall and some are 128px tall.

Current controls (also shown dynamically in the Controls screen):
  A / D move; W jump/double jump/glide; S dodge; hold Q to block;
  hold Ctrl to crouch - the guard stays up behind a smaller profile
  Mouse: left punch 1, middle hurt test, right punch 2
  E/R/F/T/G/C/V/Z/X/B/Y/U/1/2/3: combat moves
  F1 debug, F2 event log, F3 development stage, ESC pause menu (quit from title)
"""
import os
import json
import random
import time
from pathlib import Path
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import pygame

WIDTH, HEIGHT = 960, 540
GROUND_Y = 452
GRAVITY = 0.85
MOVE_SPEED = 5
JUMP_VEL = -16

CELL_W = 128         # every sheet is sliced on a 128px grid
ZOOM = 1             # 2x nearest-neighbour doublings -> 128px art becomes 256px

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE_DIR, "assets")
PACK_HERO = os.path.join(ASSETS, "hero")
PACK_PROTO = os.path.join(ASSETS, "proto")
PACK_ALT = os.path.join(ASSETS, "hero_alt")
TILESET = os.path.join(ASSETS, "tileset")
GRAFFITI_FONT = os.path.join(ASSETS, "graffiti", "font")
KENNEY_UI = os.path.join(ASSETS, "ui", "kenney")

# attack -> (reach, height, damage, knockback)  reach/height are in art pixels
ATTACKS_DEF = {
    # name: (minimum reach, hitbox height, damage, knockback)
    # reach is only a floor: the real length comes from the sprite art
    "punch1": (24, 52, 8, 4),
    "punch2": (24, 60, 12, 6),
    "kick":   (24, 46, 11, 6),
    "fire_kick":    (24, 60, 14, 5),
    "ice_strike":   (24, 58, 13, 6),
    "power_strike": (24, 66, 16, 6),
    "slide_attack": (24, 40, 11, 5),
    "ground_slam":  (24, 74, 18, 12),
    "jump_kick":    (24, 66, 12, 5),
    "super_strike": (24, 82, 20, 14),
    "counter":   (24, 56, 10, 6),
    "riposte":   (24, 60, 15, 11),
    "cast":      (24, 118, 15, 6),
    "charge":    (24, 66, 19, 13),
    "throw":     (24, 84, 11, 5),
    "impact1":   (24, 74, 17, 12),
    "impact2":   (24, 80, 23, 16),
    "special":   (36, 90, 26, 16),
    "ability":   (28, 76, 17, 9),
    "dodge":  (0, 0, 0, 0),
    "hurt":   (0, 0, 0, 0),
}

# ---- control defaults: mouse map and keyboard action names -------------
PLAYER_TAG = (90, 200, 255)
DUMMY_TAG = (255, 130, 150)

MOUSE_ACTIONS = {
    1: "punch1",      # left click
    2: "hurt",        # middle click (test animation)
    3: "punch2",      # right click
}

# pretty names for the controls screen
CONTROL_NAMES = {
    "jump": "Jump / double jump",
    "dodge": "Dodge roll",
    "kick": "Kick  (in air: jump kick)",
    "fire_kick": "Fire kick",
    "power_strike": "Power strike",
    "ground_slam": "Ground slam",
    "super_strike": "Super strike (finisher)",
    "ice_strike": "Ice strike",
    "slide_attack": "Slide attack",
    "counter": "Counter / parry",
    "riposte": "Riposte",
    "cast": "Cast spell",
    "charge": "Charge attack",
    "throw": "Throw",
    "ability": "Ability",
    "impact1": "Impact 1",
    "impact2": "Impact 2",
    "special": "Special  (costs 50 meter)",
    "punch1": "Punch 1",
    "punch2": "Punch 2",
    "hurt": "Hurt (animation test)",
}
KEY_ACTIONS = {
    pygame.K_w: "jump",
    pygame.K_s: "dodge",
    pygame.K_e: "kick",           # in mid air this becomes a jump kick
    pygame.K_r: "fire_kick",
    pygame.K_f: "power_strike",
    pygame.K_t: "ground_slam",
    pygame.K_g: "super_strike",
    pygame.K_c: "ice_strike",
    pygame.K_v: "slide_attack",
    pygame.K_z: "counter",
    pygame.K_x: "riposte",
    pygame.K_b: "cast",
    pygame.K_1: "charge",
    pygame.K_2: "impact1",
    pygame.K_3: "impact2",
    pygame.K_h: "special",       # meter-powered signature move
    pygame.K_y: "throw",
    pygame.K_u: "ability",
}

# forward step when a move starts, so strings stay connected instead of
# whiffing because the previous hit knocked the dummy out of range
LUNGE = {
    "punch1": 8, "punch2": 10, "kick": 11, "fire_kick": 10, "ice_strike": 8,
    "power_strike": 12, "slide_attack": 18, "ground_slam": 7,
    "jump_kick": 8, "super_strike": 16,
    "counter": 6, "riposte": 11, "cast": 4, "charge": 3,
    "throw": 5, "impact1": 12, "impact2": 15, "ability": 0,
    "special": 14,
}

# a super that lands on a real combo hits this much harder
FINISHER_MIN_COMBO = 3
FINISHER_MULT = 2.0
COMBO_HOLD = 150         # ticks a combo survives: outlasts the longest animation
PARRY_WINDOW = 26        # ticks after pressing counter during which a hit is parried
JUMPS_ALLOWED = 2        # ground jump plus one air jump
GLIDE_FALL_CAP = 0.22    # gravity while gliding: must be well under GRAVITY
WALL_JUMP_PUSH = 7
SPEED_RUN_AFTER = 42     # ticks of held movement before the sprint animation
SPEED_RUN_BOOST = 7      # sprint is faster than a walk

PLAYER_MAX_HP = 100
PLAYER_RESPAWN_DELAY = 70
BLOCK_KEY = pygame.K_q         # hold to guard
BLOCK_DAMAGE_MULT = 0.25      # a blocked hit does a quarter damage

# ---- super meter: every exchange feeds it, the special move spends it -----
METER_MAX = 100.0             # a full bar
METER_COST = 50.0             # what one special move costs
METER_GAIN_HIT = 0.8          # per point of damage we deal
METER_GAIN_TAKE = 0.5         # per point of damage we absorb
METER_GAIN_BLOCK = 15.0       # flat reward for guarding a hit
METER_GAIN_COMBO = 10.0       # the moment a combo becomes a real combo
METER_HINT_TICKS = 45         # how long NEED 50 METER stays on screen

# ---- versus HUD: both health bars and the energy meter sit along the top --
HUD_X = 24                    # left edge of the player's side
HUD_W = 360                   # both bars and the meter share this width
HUD_LABEL_Y = 10              # fighter names, above their bars
HUD_BAR_Y = 27                # the health bars
HUD_BAR_H = 16
HUD_METER_Y = 46              # energy bar, under the player's health
HUD_METER_H = 10
HUD_TOP_H = 54                # translucent panel behind the top HUD
HUD_BOTTOM_Y = HEIGHT - 56    # score strip takes over the old bar spot
HUD_BOTTOM_H = 26

# Runtime bindings begin with the game's existing controls. Mouse bindings
# remain the fixed entries in MOUSE_ACTIONS so they cannot be lost on reset.
#: Bump whenever a shipped default key changes. A saved binding is
#: indistinguishable from an old default, so without a version marker the
#: stale value would keep winning forever (this is how ESC kept quitting
#: after pause moved off F4). Custom settings are never discarded, only binds.
BINDS_VERSION = 2

DEFAULT_BINDINGS: dict[str, int] = {
    "move_left": pygame.K_a,
    "move_right": pygame.K_d,
    "block": BLOCK_KEY,
    "crouch_block": pygame.K_LCTRL,
    **{action: key for key, action in KEY_ACTIONS.items()},
    "debug": pygame.K_F1,
    "log": pygame.K_F2,
    "stage": pygame.K_F3,
    "pause": pygame.K_ESCAPE,
    "hero": pygame.K_F5,
    "monster": pygame.K_F6,
    "quit": pygame.K_ESCAPE,
}
CONTROL_NAMES.update({
    "move_left": "Move left",
    "move_right": "Move right",
    "block": "Block / guard",
    "crouch_block": "Crouch guard",
    "debug": "Debug information",
    "log": "Event log",
    "stage": "Next stage (development)",
    "pause": "Pause menu",
    "hero": "Next fighter",
    "monster": "Next rival monster",
    "quit": "Quit game",
})
SETTINGS_PATH = os.path.join(BASE_DIR, "logs", "game_settings.json")

DUMMY_MAX_HP = 100
DUMMY_RESPAWN_DELAY = 90
DUMMY_TINT = (255, 105, 120)     # multiply tint so the dummy never looks like the player
FLASH_ALPHA = 165

# the dummy is kept inside these walls so a knockback can never push it off screen
ARENA_LEFT = 70
ARENA_RIGHT = WIDTH - 70
DUMMY_RETURN_SPEED = 1.9       # walks back to its spot once knockback has settled
DUMMY_DRIFT_HOME = False       # True: dummy retreats to its home spot between swings
DUMMY_WALK_SPEED = 1.4         # closes the gap when it wants to hit you
DUMMY_ATTACK_RANGE = 96
DUMMY_ATTACK_CD = 120
DUMMY_HIT = {
    # name: (minimum reach, hitbox height, damage, knockback)
    "attack": (24, 60, 9, 7),
    # reactive poses: they keep the rival busy but never reach out
    "guard": (0, 0, 0, 0),
    "tell":  (0, 0, 0, 0),
    "blink": (0, 0, 0, 0),
}

# One entry per arcade round: the rival trains up as the run goes on.
#   cd      ticks between swings     react  odds of answering a live attack
#   walk    approach speed           hp     rival maximum health
#   dmg     multiplier on its hit    punish free swings while we recover
RIVAL_TIERS = (
    {"cd": 120, "react": 0.00, "walk": 1.4, "hp": 100, "dmg": 1.00, "punish": False},
    {"cd": 100, "react": 0.15, "walk": 1.5, "hp": 110, "dmg": 1.00, "punish": False},
    {"cd": 85,  "react": 0.30, "walk": 1.6, "hp": 125, "dmg": 1.15, "punish": False},
    {"cd": 70,  "react": 0.45, "walk": 1.7, "hp": 140, "dmg": 1.30, "punish": True},
    {"cd": 55,  "react": 0.60, "walk": 1.9, "hp": 150, "dmg": 1.50, "punish": True},
)

# Settings stores EASY / NORMAL / HARD as 0.5 / 1.0 / 1.5, because the loader
# clamps floats to 1.5.  Per rival style, on top of the tier:
#   approach  closing speed     spacing  gap under which it gives ground
#   blink     odds of blinking out of a swing instead of standing and guarding
PERSONALITY = {
    "balanced": {"approach": 1.00, "spacing": 0,  "blink": 0.35},
    "rushdown": {"approach": 1.30, "spacing": 0,  "blink": 0.20},
    "evasive":  {"approach": 1.00, "spacing": 55, "blink": 0.75},
    "punisher": {"approach": 0.90, "spacing": 50, "blink": 0.40},
    "heavy":    {"approach": 0.80, "spacing": 0,  "blink": 0.15},
}


def difficulty_mods(scale):
    """Turn the EASY/NORMAL/HARD value into per-stat multipliers."""
    return {
        "cd": 2.0 - scale,             # EASY is slower, HARD is twice as fast
        "react": scale,
        "walk": 0.8 + 0.2 * scale,
        "hp": 0.7 + 0.3 * scale,
        "dmg": 0.7 + 0.3 * scale,
    }

BACKGROUNDS = os.path.join(ASSETS, "backgrounds")
ROSTER = os.path.join(ASSETS, "roster")
# stage props drawn on the floor line, as (folder, file, x offset)
STAGE_PROPS = (
    ("objects", "Spikes1.png", -46),
    ("objects", "Spikes3.png", 26),
    ("objects", "Chest.png", 300),
    ("objects", "Ladder1.png", -70),
)

# state -> (pack dir, sheet filename, ticks per frame)
ANIMS = {
    "idle":   (PACK_PROTO, "Stop_Running.png", 10),
    "run":    (PACK_PROTO, "Running.png", 5),
    "jump":   (PACK_PROTO, "Jumping.png", 8),
    "punch1": (PACK_HERO, "Punch_1.png", 4),
    "punch2": (PACK_HERO, "Punch_2.png", 4),
    "kick":   (PACK_HERO, "Kick.png", 5),
    "dodge":  (PACK_HERO, "Dodge.png", 4),
    "hurt":   (PACK_HERO, "Hurt.png", 6),
    # extra moves, all from Prototype Character Pack 2
    "fire_kick":    (PACK_HERO, "Fire_Kick.png", 5),
    "ice_strike":   (PACK_HERO, "Ise_Strice.png", 5),
    "power_strike": (PACK_HERO, "Power_Strike.png", 5),
    "slide_attack": (PACK_HERO, "Slide_Attack.png", 4),
    "ground_slam":  (PACK_HERO, "Ground_Slam.png", 5),
    "jump_kick":    (PACK_HERO, "Jump_Kick.png", 5),
    "super_strike": (PACK_HERO, "Explosive_Strike.png", 5),
    "block":  (PACK_HERO, "Defensive_Stance.png", 10),
    "crouch": (PACK_PROTO, "Crouch.png", 8),
    # the remaining combat animations from the pack
    "counter":   (PACK_HERO, "Counterattack.png", 4),
    "riposte":   (PACK_HERO, "Defense attack.png", 4),
    "cast":      (PACK_HERO, "Casting Spell.png", 6),
    "charge":    (PACK_HERO, "Skill_Charging.png", 5),
    "throw":     (PACK_HERO, "Throwing.png", 4),
    "impact1":   (PACK_HERO, "Enchanced_Impact_1.png", 4),
    "impact2":   (PACK_HERO, "Enchanced_impact_2.png", 5),
    "special":   (PACK_HERO, "Casting Spell.png", 6),
    "ability":   (PACK_HERO, "Ability_Use.png", 6),
    # and the unused locomotion animations
    "fall":       (PACK_PROTO, "Falling.png", 7),
    "land":       (PACK_PROTO, "Landing.png", 5),
    "double_jump": (PACK_PROTO, "Double_Jump.png", 6),
    "glide":      (PACK_PROTO, "Gliding_Jump.png", 6),
    "wall_jump":  (PACK_PROTO, "Wall Jump.png", 6),
    "speed_run":  (PACK_PROTO, "Speed_Boost_Running.png", 5),
}

LOOPING = ("run", "jump", "fall", "glide", "speed_run")
ATTACKS = tuple(ATTACKS_DEF)

# dummy -> (pack dir, sheet filename, ticks per frame)
DUMMY_ANIMS = {
    "idle":   (PACK_ALT, "Magic_Shield.png", 8),
    "hurt":   (PACK_ALT, "Taking_Damage.png", 5),
    "dodge":  (PACK_ALT, "Bullet_Dodge.png", 4),
    "death":  (PACK_ALT, "Death.png", 7),
    "attack": (PACK_ALT, "Double_Srtike.png", 4),
    "guard":  (PACK_ALT, "Power_Boost.png", 6),
    "tell":   (PACK_ALT, "Energy_Charge.png", 5),
    "blink":  (PACK_ALT, "Teleport.png", 4),
}
DUMMY_LOOPING = ("idle",)

FALLBACK_COLORS = {
    "idle": (80, 160, 255), "run": (80, 200, 120), "jump": (180, 130, 255),
    "punch1": (255, 180, 60), "punch2": (255, 130, 60), "kick": (255, 90, 90),
    "dodge": (90, 220, 220), "hurt": (200, 60, 60),
}

_sheet_cache = {}
_persistent_sheets = {}      # id(frames) -> frames, for sheets that are never freed
_reach_cache = {}            # id(frames) -> per-frame reach, only for cached sheets
SPARSE_WARNINGS = []
SOUND_DIR = os.path.join(ASSETS, "sounds")
SOUNDS = {}
# graffiti title wordmark: warm ramp sampled from the pack palette
TITLE_LOGO_RAMP = ((255, 250, 208), (255, 205, 74), (236, 96, 44))
TITLE_LOGO_OUTLINE = (12, 12, 20)
_glyph_cache = {}
_title_logo_cache = []


def load_sounds():
    """Load only the selected effects; keep silent if audio is unavailable."""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(16)
        except pygame.error:
            return
    for name in ("swing", "punch_hit", "kick_hit", "heavy_hit", "block", "parry", "finisher"):
        path = os.path.join(SOUND_DIR, name + ".wav")
        if os.path.exists(path):
            try:
                sound = pygame.mixer.Sound(path)
                sound.set_volume(0.42)
                SOUNDS[name] = sound
            except pygame.error:
                continue


def play_sound(name):
    """Play a loaded effect at the current game event."""
    sound = SOUNDS.get(name)
    if sound is not None:
        sound.play()


class GameLog:
    """Records what the game is doing: console + logs/pixel_fighter.log"""

    def __init__(self, path, keep=9):
        self.path = path
        self.keep = keep
        self.lines = []
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.handle = open(path, "a", encoding="utf-8")

    def write(self, msg):
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        self.lines.append(line)
        if len(self.lines) > self.keep:
            self.lines.pop(0)
        print(line)
        self.handle.write(line + "\n")
        self.handle.flush()

    def close(self):
        self.handle.close()


LOG = None


def log(msg):
    if LOG is not None:
        LOG.write(msg)


def frame_coverage(surf):
    """Rough fraction of the cell that is not transparent."""
    return pygame.transform.average_color(surf)[3] / 255


def load_sheet(path, cell_w=None, zoom=None):
    """Slice a horizontal sheet into frames.

    cell_w and zoom default to the 128px / 2x prototype sheets, but the
    roster characters use their own cell sizes (42px and 32px art).
    """
    cell_w = CELL_W if cell_w is None else cell_w
    zoom = ZOOM if zoom is None else zoom
    key = (path, cell_w, zoom)
    if key in _sheet_cache:
        return _sheet_cache[key]

    frames = []
    sheet = pygame.image.load(path).convert_alpha()
    w, h = sheet.get_size()
    cell_h = h                       # one row of frames; height varies per sheet
    for x in range(0, w - cell_w + 1, cell_w):
        chunk = sheet.subsurface((x, 0, cell_w, cell_h)).copy()
        frames.append(chunk)

    # effect-only sheets (weapon summons, energy bursts) are nearly empty and
    # look like a stray speck in game, so flag them instead of using them blind
    peak = max(frame_coverage(f) for f in frames)
    if peak < 0.03:
        SPARSE_WARNINGS.append("%s (peak coverage %.3f)" % (os.path.basename(path), peak))

    for i, f in enumerate(frames):
        for _ in range(zoom):
            frames[i] = pygame.transform.scale2x(frames[i])

    _sheet_cache[key] = frames
    _persistent_sheets[id(frames)] = frames
    return frames


TEXT_CACHE_MAX = 400                 # oldest rendered strings are dropped past this
_text_cache = OrderedDict()
_placeholder_font = None


def outlined_text(font, text, color, outline=(8, 8, 12), cache=True):
    """Text with a dark outline so the HUD stays readable over bright skies.

    Results are cached (bounded, least-recently-used). Pass cache=False for
    text that changes every frame, like the debug readout.
    """
    key = (id(font), text, color, outline)
    if cache and key in _text_cache:
        _text_cache.move_to_end(key)
        return _text_cache[key]
    img = font.render(text, True, color)
    edge = font.render(text, True, outline)
    out = pygame.Surface((img.get_width() + 2, img.get_height() + 2), pygame.SRCALPHA)
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(edge, (dx, dy))
    out.blit(img, (0, 0))
    if cache:
        _text_cache[key] = out
        if len(_text_cache) > TEXT_CACHE_MAX:
            _text_cache.popitem(last=False)
    return out


_overlay_cache = {}


def translucent_rect(size, color):
    """A reusable see-through panel, so HUD backings aren't rebuilt every frame."""
    key = (size, color)
    surf = _overlay_cache.get(key)
    if surf is None:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill(color)
        _overlay_cache[key] = surf
    return surf


def measure_reach(frames):
    """Per frame, how far the opaque pixels reach right of centre.

    Measured from the real art, so a hitbox can never be longer than the
    fist or foot the player can actually see. Sprites are mirrored when
    facing left, so the right-hand extent is the one that points at the target.
    """
    is_cached_sheet = _persistent_sheets.get(id(frames)) is frames
    if is_cached_sheet and id(frames) in _reach_cache:
        return _reach_cache[id(frames)]
    reach = []
    for f in frames:
        w, h = f.get_size()
        right = 0
        for x in range(w // 2, w):
            if pygame.transform.average_color(f.subsurface((x, 0, 1, h)))[3] > 0:
                right = x - w // 2 + 1
        reach.append(right)
    if is_cached_sheet:
        _reach_cache[id(frames)] = reach
    return reach


BODY_HALF = 24          # the hitbox starts at the torso, not the centre line


def apply_tint(img, color):
    """Multiply-tint a sprite so it keeps its shading instead of going flat."""
    tinted = img.copy()
    tinted.fill((color[0], color[1], color[2], 0), special_flags=pygame.BLEND_RGB_MULT)
    return tinted


def make_placeholder(color, label=""):
    """A flat coloured cell standing in for a sheet that failed to load."""
    global _placeholder_font
    if _placeholder_font is None:
        _placeholder_font = pygame.font.SysFont("consolas", 16)
    size = CELL_W * (2 ** ZOOM)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(surf, color, surf.get_rect())
    pygame.draw.rect(surf, (20, 20, 20), surf.get_rect(), 4)
    surf.blit(_placeholder_font.render(label, True, (255, 255, 255)), (10, size - 26))
    return surf


def build_anim(pack_dir, fname, state, cell_w=None, zoom=None):
    """Frames for one animation, or placeholders if the sheet is missing."""
    path = os.path.join(pack_dir, fname)
    if os.path.exists(path):
        return load_sheet(path, cell_w, zoom)
    color = FALLBACK_COLORS.get(state, (180, 180, 180))
    return [make_placeholder(color, state), make_placeholder(color, state)]


class Player:
    """The fighter you control: movement, combat moves, blocking and respawn."""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0
        self.vy = 0
        self.on_ground = True
        self.facing_right = True
        self.state = "idle"
        self.state_time = 0
        self.anim_index = 0
        self.anims = {}
        self.flipped_anims = {}
        self.lock = {}
        self.missing = []
        self.connected = False
        self.buffer = None
        self.combo = 0
        self.combo_damage = 0
        self.combo_timer = 0

        self.reach_right = {}
        self.hp = PLAYER_MAX_HP
        self.max_hp = PLAYER_MAX_HP
        self.speed = MOVE_SPEED
        self.tint = None
        self.crouching = False
        self.blocking = False
        self.hit_vx = 0.0
        self.down_timer = 0
        self.block_flash = 0
        self.parry = 0
        self.meter = 0.0          # super meter, 0..METER_MAX
        self.meter_hint = 0       # ticks of NEED 50 METER still to show
        self.jumps_left = JUMPS_ALLOWED
        self.gliding = False
        self.move_ticks = 0
        self.land_lock = 0
        self.durations = {}          # state -> ticks per frame
        self.use_prototype()

    def _set_anim(self, state, frames, dur):
        """Store one animation along with its mirrored copy, length and reach."""
        self.anims[state] = frames
        self.flipped_anims[state] = [pygame.transform.flip(f, True, False) for f in frames]
        self.durations[state] = dur
        self.lock[state] = len(frames) * dur + 4
        self.reach_right[state] = measure_reach(frames)

    def use_prototype(self, spec=None):
        """Load a prototype variant: its palette, body and stats go with it."""
        spec = spec or PROTO_SPEC
        self.spec = spec
        self.body_w = spec.body_w
        self.body_h = spec.body_h
        self.max_hp = spec.hp or PLAYER_MAX_HP
        self.speed = spec.speed or MOVE_SPEED
        self.tint = spec.tint
        self.missing = []
        for state, (pack, fname, dur) in spec.sheets.items():
            if not os.path.exists(os.path.join(pack, fname)):
                self.missing.append(fname)
            frames = build_anim(pack, fname, state)
            if spec.tint:
                frames = [apply_tint(frame, spec.tint) for frame in frames]
            self._set_anim(state, frames, dur)
        self.hp = min(self.hp, self.max_hp)

    def set_state(self, s):
        if self.state != s:
            self.state = s
            self.state_time = 0
            self.anim_index = 0
            self.connected = False

    def begin(self, s):
        """Force a fresh move even if it is the state we are already in."""
        self.state = s
        self.state_time = 0
        self.anim_index = 0
        self.connected = False

    def _spend_for(self, name):
        """Charge the special move for its meter, refusing it when the bar is short."""
        if name != "special":
            return True
        if self.meter < METER_COST:
            self.meter_hint = METER_HINT_TICKS
            log("special needs %d meter (only %.0f stored)"
                % (METER_COST, self.meter))
            return False
        self.meter -= METER_COST
        log("special spent 50 meter (%.0f left)" % self.meter)
        return True

    def attack_stats(self, state):
        """Damage geometry for a move, with this fighter's tuning on top."""
        base = ATTACKS_DEF.get(state)
        if base is None:
            return None
        over = self.spec.attack_overrides.get(state) if self.spec else None
        if not over:
            return base
        reach, height, damage, knock = base
        return (over.get("reach", reach), over.get("height", height),
                over.get("damage", damage), over.get("knock", knock))

    def lunge_for(self, name):
        """Forward step a move takes, retuned when this fighter overrides it."""
        if self.spec:
            value = self.spec.attack_overrides.get(name, {}).get("lunge")
            if value is not None:
                return value
        return LUNGE.get(name, 0)

    def attack(self, name):
        """Start a move, or buffer the next one so attacks chain into combos."""
        if self.blocking or self.down_timer > 0:
            return
        if self.state in ATTACKS and self.state_time < self.lock[self.state]:
            if self.buffer is None:
                self.buffer = name
                log("queued %s behind %s" % (name, self.state))
            return
        if not self._spend_for(name):
            return
        self.begin(name)
        play_sound("swing")
        self.buffer = None
        if name == "counter":
            self.parry = PARRY_WINDOW
            log("parry window open for %d ticks" % PARRY_WINDOW)
        step = self.lunge_for(name)
        if step:
            self.x = max(ARENA_LEFT, min(ARENA_RIGHT,
                                         self.x + (step if self.facing_right else -step)))
        log("attack %s at x=%.0f facing=%s lunge=%d"
            % (name, self.x, "R" if self.facing_right else "L", step))

    def air_attack(self):
        """Kick pressed while airborne becomes a jump kick."""
        if not self.on_ground:
            self.attack("jump_kick")

    def register_hit(self, damage):
        self.combo += 1
        self.combo_damage += damage
        self.combo_timer = COMBO_HOLD
        self.meter = min(METER_MAX, self.meter + damage * METER_GAIN_HIT)
        if self.combo == FINISHER_MIN_COMBO:
            self.meter = min(METER_MAX, self.meter + METER_GAIN_COMBO)

    def break_combo(self):
        self.combo = 0
        self.combo_damage = 0
        self.combo_timer = 0

    def update(self, keys, bindings=None):
        """Advance one simulation tick using the active key configuration."""
        bindings = bindings or DEFAULT_BINDINGS
        if self.down_timer > 0:
            self.down_timer -= 1
            if self.down_timer == 0:
                self.hp = self.max_hp
                self.x = WIDTH // 2
                self.y = GROUND_Y
                self.vx = self.vy = self.hit_vx = 0
                self.on_ground = True
                self.facing_right = True
                self.blocking = False
                self.parry = self.block_flash = 0
                self.jumps_left = JUMPS_ALLOWED
                self.gliding = False
                self.move_ticks = self.land_lock = 0
                self.buffer = None
                self.meter = 0.0
                self.meter_hint = 0
                self.break_combo()
                self.begin("idle")
                log("player respawned with full hp")
            return

        self.state_time += 1

        if self.parry > 0:
            self.parry -= 1

        if self.meter_hint > 0:
            self.meter_hint -= 1

        if self.combo_timer > 0:
            self.combo_timer -= 1
            if self.combo_timer == 0:
                log("combo ended at %d hits / %d damage"
                    % (self.combo, self.combo_damage))
                self.break_combo()

        # a move just finished: if the player queued something, chain into it
        if self.state in ATTACKS and self.state_time >= self.lock[self.state]:
            if self.buffer is not None:
                nxt = self.buffer
                self.buffer = None
                if self._spend_for(nxt):
                    step = self.lunge_for(nxt)
                    self.begin(nxt)
                    play_sound("swing")
                    if step:
                        self.x = max(ARENA_LEFT, min(ARENA_RIGHT,
                                                     self.x + (step if self.facing_right else -step)))
                    log("chain into %s (lunge=%d)" % (nxt, step))
                else:
                    log("dropped buffered %s: meter too low" % nxt)

        busy = self.state in ATTACKS and self.state_time < self.lock[self.state]

        if self.block_flash > 0:
            self.block_flash -= 1

        # Hold the configured guard key to block; Ctrl crouches that guard.
        can_block = self.on_ground and not busy
        crouch_key = bindings.get("crouch_block")
        held_crouch = bool(crouch_key is not None) and bool(keys[crouch_key])
        self.crouching = held_crouch and can_block
        self.blocking = (bool(keys[bindings["block"]]) or self.crouching) \
            and can_block

        self.vx = 0
        if not busy and not self.blocking:
            if keys[bindings["move_left"]]:
                self.vx = -self.speed
                self.facing_right = False
            if keys[bindings["move_right"]]:
                self.vx = self.speed
                self.facing_right = True
            if self.vx:
                self.move_ticks += 1
            else:
                self.move_ticks = 0
            if self.move_ticks > SPEED_RUN_AFTER:
                sprint = self.speed + (SPEED_RUN_BOOST - MOVE_SPEED)
                self.vx = sprint if self.vx > 0 else -sprint

        # knockback from a hit the player failed to block
        if abs(self.hit_vx) > 0.1:
            self.x += self.hit_vx
            self.hit_vx *= 0.84
        else:
            self.hit_vx = 0.0

        self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x + self.vx))

        # hold jump while dropping to glide, once the air jump is spent
        self.gliding = bool(keys[bindings["jump"]]) and not self.on_ground \
            and self.vy > 0 and self.jumps_left <= 0 and not busy
        self.vy += GLIDE_FALL_CAP if self.gliding else GRAVITY
        self.y += self.vy
        if self.y >= GROUND_Y:
            hard = self.vy > 8
            self.y = GROUND_Y
            self.vy = 0
            if not self.on_ground:
                self.jumps_left = JUMPS_ALLOWED - 1
                self.gliding = False
                if hard and self.state not in ATTACKS:
                    self.begin("land")
                    self.land_lock = self.lock["land"]
            self.on_ground = True
        else:
            self.on_ground = False

        if self.land_lock > 0:
            self.land_lock -= 1

        if not busy:
            if self.blocking:
                self.set_state("crouch" if self.crouching else "block")
            elif self.land_lock > 0:
                pass
            elif not self.on_ground:
                if self.gliding:
                    self.set_state("glide")
                elif self.vy > 2:
                    self.set_state("fall")
                else:
                    self.set_state("jump")
            elif self.vx != 0:
                self.set_state("speed_run" if self.move_ticks > SPEED_RUN_AFTER
                               else "run")
            else:
                self.set_state("idle")

        dur = self.durations[self.state]
        frames = self.anims[self.state]
        step = self.state_time // dur
        if self.state in LOOPING:
            self.anim_index = step % len(frames)
        else:
            self.anim_index = min(step, len(frames) - 1)

    def try_jump(self):
        busy = self.state in ATTACKS and self.state_time < self.lock[self.state]
        if busy or self.blocking or self.down_timer > 0:
            return
        if self.on_ground:
            self.vy = JUMP_VEL
            self.on_ground = False
            self.jumps_left = JUMPS_ALLOWED - 1
            self.gliding = False
            self.move_ticks = 0
            self.begin("jump")
            log("jump at x=%.0f" % self.x)
            return
        # second jump
        if self.jumps_left > 0:
            self.vy = JUMP_VEL * 0.92
            self.jumps_left -= 1
            self.gliding = False
            self.begin("double_jump")
            log("air jump at x=%.0f" % self.x)
            return
        # wall jump off either arena wall
        if self.x <= ARENA_LEFT + 8:
            self.vy = JUMP_VEL * 0.85
            self.hit_vx = WALL_JUMP_PUSH
            self.begin("wall_jump")
            log("wall jump off the left wall")
        elif self.x >= ARENA_RIGHT - 8:
            self.vy = JUMP_VEL * 0.85
            self.hit_vx = -WALL_JUMP_PUSH
            self.begin("wall_jump")
            log("wall jump off the right wall")

    def hitbox(self):
        # The box is measured from the sprite, so it grows as the limb extends
        # and shrinks during wind up. It can never reach further than the art,
        # which is what stops hits landing while the punch is still retracted.
        if self.down_timer > 0:
            return None          # a knocked-out player can't land hits
        if self.state not in ATTACKS or self.state not in ATTACKS_DEF:
            return None
        if self.state_time >= self.lock[self.state]:
            return None
        if self.connected:
            return None
        floor, height, damage, knock = self.attack_stats(self.state)
        if floor == 0:
            return None

        frame = min(self.anim_index, len(self.anims[self.state]) - 1)
        # The sprite is mirrored when facing left, so the right hand extent is
        # the one that points at the target in both directions.
        reach = max(self.reach_right[self.state][frame], floor)

        if self.facing_right:
            rect = pygame.Rect(self.x - BODY_HALF, self.y - self.body_h + BODY_HALF,
                               reach + BODY_HALF, height)
        else:
            rect = pygame.Rect(self.x - reach, self.y - self.body_h + BODY_HALF,
                               reach + BODY_HALF, height)
        return rect, damage, knock

    def body(self):
        """Rect the dummy's hitbox must overlap to hit us.

        Crouching drops the top of the box toward the feet, so swings aimed
        high enough to clear it simply pass over us instead of landing.
        """
        width, height = self.body_w, self.body_h
        if self.crouching:
            height = max(1, int(height * 0.62))
            width = max(1, int(width * 0.9))
        return pygame.Rect(self.x - width / 2, self.y - height, width, height)

    def take_damage(self, amount, from_x, knock, texts):
        """Apply a hit from the dummy: parry, block, or take it."""
        if self.down_timer > 0:
            return               # already knocked out: don't restart the respawn timer
        # a counter that catches the hit turns it into a free riposte
        if self.parry > 0:
            self.parry = 0
            play_sound("parry")
            log("PARRIED %d and countered" % amount)
            texts.append(FloatingText(self.x, self.y - 232, "PARRY",
                                       (255, 226, 120)))
            self.begin("riposte")
            return
        blocked = self.blocking
        dmg = max(1, int(amount * BLOCK_DAMAGE_MULT)) if blocked else amount
        self.hp = max(0, self.hp - dmg)
        self.meter = min(METER_MAX,
                         self.meter + (METER_GAIN_BLOCK if blocked
                                       else dmg * METER_GAIN_TAKE))
        if blocked:
            play_sound("block")
            self.block_flash = 10
            log("BLOCKED %s hit for %d (player hp %d/%d)"
                % (amount, dmg, self.hp, PLAYER_MAX_HP))
            texts.append(FloatingText(self.x, self.y - 232, "BLOCK",
                                       (120, 200, 255)))
        else:
            play_sound("punch_hit")
            direction = 1 if self.x >= from_x else -1
            self.hit_vx = knock * direction
            log("hit player for %d -> hp %d/%d"
                % (dmg, self.hp, self.max_hp))
            texts.append(FloatingText(self.x, self.y - 232, "-%d" % dmg,
                                       (255, 90, 90)))
            if self.state not in ATTACKS or self.state_time >= self.lock[self.state]:
                self.set_state("hurt")
                self.break_combo()
        if self.hp == 0:
            self.down_timer = PLAYER_RESPAWN_DELAY
            self.blocking = False
            log("PLAYER KNOCKED OUT - back up in %d frames"
                % PLAYER_RESPAWN_DELAY)

    def draw(self, screen, hit_flash=True):
        frames = self.anims if self.facing_right else self.flipped_anims
        img = frames[self.state][self.anim_index]
        if hit_flash and self.block_flash > 0:
            glow = img.copy()
            glow.fill((120, 200, 255, 0), special_flags=pygame.BLEND_RGB_MAX)
            glow.set_alpha(FLASH_ALPHA)
            img = glow
        screen.blit(img, img.get_rect(midbottom=(int(self.x), int(self.y))))

    def draw_health(self, screen, font):
        x, y, w, h = HUD_X, HUD_BAR_Y, HUD_W, HUD_BAR_H
        ratio = max(0, self.hp) / max(1, self.max_hp)
        draw_health_bar(screen, x, y, w, h, ratio)
        label = outlined_text(font, "PLAYER %d/%d" % (max(0, self.hp), self.max_hp),
                               (245, 245, 245))
        screen.blit(label, (x, HUD_LABEL_Y))
        self.draw_meter(screen, font)

    def draw_meter(self, screen, font):
        """Super meter, sitting directly under the player's health bar."""
        w, h = HUD_W, HUD_METER_H
        x, y = HUD_X, HUD_METER_Y
        ready = self.meter >= METER_COST
        span = max(0, min(w, int(round(w * self.meter / METER_MAX))))
        track = kenney_bar("Grey", w, h)
        fill = kenney_bar("Yellow" if ready else "Blue", w, h)
        if track is not None and fill is not None:
            screen.blit(track, (x, y))
            if span:
                screen.blit(fill, (x, y), pygame.Rect(0, 0, span, h))
        else:
            pygame.draw.rect(screen, (59, 63, 77), (x, y, w, h))
            if span:
                pygame.draw.rect(screen, (255, 204, 0) if ready else (28, 159, 215),
                                 (x, y, span, h))
        pygame.draw.rect(screen, (9, 10, 16), (x, y, w, h), 1)
        if not ready and self.meter_hint > 0:
            text, colour = "NEED 50 METER", (255, 120, 120)
        elif ready:
            text, colour = "SPECIAL READY", (255, 214, 90)
        else:
            text, colour = "SPECIAL %d%%" % round(self.meter), (150, 156, 172)
        screen.blit(outlined_text(font, text, colour), (x + w + 10, y - 1))

    def set_character(self, spec):
        """Swap in a different fighter's art, keeping position and health."""
        if spec is None or not spec.exists:
            return False
        self.spec = spec
        self.body_w = spec.body_w
        self.body_h = spec.body_h
        self.max_hp = spec.hp or PLAYER_MAX_HP
        self.speed = spec.speed or MOVE_SPEED
        self.tint = spec.tint
        self.hp = min(self.hp, self.max_hp)
        self.missing = []
        for state, entry in spec.sheets.items():
            pack, fname, dur = entry if len(entry) == 3 \
                else (spec.folder, entry[0], entry[1])
            path = os.path.join(pack, fname)
            if not os.path.exists(path):
                self.missing.append(fname)
            self._set_anim(state, build_anim(pack, fname, state,
                                             spec.cell_w, spec.zoom), dur)
        self.set_state("idle")
        log("player character -> %s (%d sheets)" % (spec.label, len(spec.sheets)))
        return True


class FloatingText:
    """Short-lived text that drifts upward (damage numbers, PARRY, FINISHER)."""

    def __init__(self, x, y, text, color):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = 45

    def update(self):
        self.y -= 1.4
        self.life -= 1

    def draw(self, screen, font):
        if self.life > 0:
            img = outlined_text(font, self.text, self.color).copy()
            img.set_alpha(min(255, self.life * 6))
            screen.blit(img, (self.x - img.get_width() / 2, self.y))


class Dummy:
    """Current arcade rival: closes distance, attacks, takes hits, and respawns."""

    def __init__(self, x, y):
        self.home_x = float(x)
        self.x = float(x)
        self.y = float(y)
        self.vx = 0
        self.hp = DUMMY_MAX_HP
        self.facing_right = False
        self.state = "idle"
        self.state_time = 0
        self.anim_index = 0
        self.flash = 0
        self.respawn = 0
        self.label = "Training Dummy"
        self.tint = DUMMY_TINT
        self.anims = {}
        self.tinted_anims = {}
        self.tinted_flipped_anims = {}
        self.lock = {}
        self.reach_right = {}
        self.atk_cd = 40
        self.connected = False
        self.max_hp = DUMMY_MAX_HP
        self.personality = "balanced"
        self.tier_key = None        # last (round, difficulty) already applied
        self.atk_cd_max = DUMMY_ATTACK_CD
        self.react_chance = 0.0
        self.walk_speed = DUMMY_WALK_SPEED
        self.dmg_mult = 1.0
        self.punish_ok = False
        self.decision_cd = 0
        self.body_w = 88
        self.body_h = 148
        self.spec = None
        self.missing = []

        self.durations = {}          # state -> ticks per frame
        for state, (pack, fname, dur) in DUMMY_ANIMS.items():
            self._set_anim(state, build_anim(pack, fname, state), dur)
        self._retint()

    def _set_anim(self, state, frames, dur):
        """Store one animation with its length (lock) and attack reach."""
        self.anims[state] = frames
        self.durations[state] = dur
        self.lock[state] = len(frames) * dur + 4
        self.reach_right[state] = measure_reach(frames)

    def _retint(self):
        """Rebuild the tinted (and mirrored) frames after the art or tint changed."""
        self.tinted_anims = {
            state: [apply_tint(frame, self.tint) for frame in frames]
            for state, frames in self.anims.items()
        }
        self.tinted_flipped_anims = {
            state: [pygame.transform.flip(frame, True, False) for frame in frames]
            for state, frames in self.tinted_anims.items()
        }

    def set_character(self, spec):
        """Swap the rival for a monster, keeping the fight running."""
        if spec is None or not spec.exists:
            return False
        self.spec = spec
        self.label = spec.label
        self.body_w = spec.body_w
        self.body_h = spec.body_h
        self.missing = []
        for state, (fname, dur) in spec.sheets.items():
            if not os.path.exists(os.path.join(spec.folder, fname)):
                self.missing.append(fname)
            self._set_anim(state, build_anim(spec.folder, fname, state,
                                             spec.cell_w, spec.zoom), dur)
        # Monster packs have no dedicated "attack" or "death" sheet. Without
        # these aliases the rival would keep the previous rival's big sprite
        # for those two moves.
        for state, source in (("attack", "punch1"), ("death", "hurt")):
            if state not in spec.sheets and source in self.anims:
                self._set_anim(state, self.anims[source], self.durations[source])
        self._retint()
        self.set_state("idle")
        log("rival -> %s (%d sheets)" % (spec.label, len(spec.sheets)))
        return True

    def set_rival(self, label, tint, attack_sheet, personality="balanced"):
        """Load a rival's attack art, fighting style and tinted frames."""
        self.label = label
        self.tint = tint
        self.personality = personality
        if self.spec is None:        # a monster keeps its own attack art
            self._set_anim("attack", build_anim(PACK_ALT, attack_sheet, "attack"),
                           DUMMY_ANIMS["attack"][2])
        self._retint()

    def sync_tier(self, tier_index, difficulty_scale):
        """Apply an arcade round's tier, retuning only when the inputs change."""
        key = (max(0, min(len(RIVAL_TIERS) - 1, int(tier_index))), difficulty_scale)
        if key == self.tier_key:
            return
        self.tier_key = key
        base = RIVAL_TIERS[key[0]]
        mod = difficulty_mods(difficulty_scale)
        self.atk_cd_max = max(20, int(round(base["cd"] * mod["cd"])))
        self.react_chance = min(0.9, base["react"] * mod["react"])
        self.walk_speed = base["walk"] * mod["walk"]
        self.max_hp = max(40, int(round(base["hp"] * mod["hp"])))
        self.dmg_mult = base["dmg"] * mod["dmg"]
        self.punish_ok = bool(base["punish"])
        self.hp = min(self.hp, self.max_hp)
        self.atk_cd = min(self.atk_cd, self.atk_cd_max)
        self.decision_cd = 0
        log("rival tier %d at difficulty %.1f: cd %d react %.0f%% hp %d dmg %.2f"
            % (key[0] + 1, difficulty_scale, self.atk_cd_max,
               self.react_chance * 100, self.max_hp, self.dmg_mult))

    def set_state(self, s):
        if self.state != s:
            self.state = s
            self.state_time = 0
            self.anim_index = 0
            self.connected = False

    def begin(self, s):
        """Force a fresh move even if it is the state we are already in."""
        self.state = s
        self.state_time = 0
        self.anim_index = 0
        self.connected = False

    @property
    def alive(self):
        return self.hp > 0

    def busy(self):
        return self.state in DUMMY_HIT and self.state_time < self.lock[self.state]

    def hitbox(self):
        """Dummy attack box, measured from its own art like the player's."""
        if not self.busy() or self.connected:
            return None
        floor, height, damage, knock = DUMMY_HIT[self.state]
        if floor == 0:
            return None          # reactive pose: it never reaches out
        damage = max(1, int(round(damage * self.dmg_mult)))
        frame = min(self.anim_index, len(self.anims[self.state]) - 1)
        reach = max(self.reach_right[self.state][frame], floor)
        if self.facing_right:
            rect = pygame.Rect(self.x - BODY_HALF, self.y - self.body_h + BODY_HALF,
                               reach + BODY_HALF, height)
        else:
            rect = pygame.Rect(self.x - reach, self.y - self.body_h + BODY_HALF,
                               reach + BODY_HALF, height)
        return rect, damage, knock

    def body(self):
        """Rect the player's hitbox must overlap."""
        return pygame.Rect(self.x - self.body_w / 2, self.y - self.body_h,
                           self.body_w, self.body_h)

    def take_hit(self, from_x, damage, knock, texts, move="hit"):
        if not self.alive:
            return
        guarded = self.state == "guard" and self.busy()
        if guarded:
            damage = max(1, int(round(damage * BLOCK_DAMAGE_MULT)))
        self.hp = max(0, self.hp - damage)
        if guarded:
            play_sound("block")
        elif move == "super_strike" and self.hp > 0:
            play_sound("heavy_hit")
        elif "kick" in move or move == "slide_attack":
            play_sound("kick_hit")
        elif move in ("punch1", "punch2"):
            play_sound("punch_hit")
        else:
            play_sound("heavy_hit")
        direction = 1 if self.x >= from_x else -1
        if guarded:
            self.vx = 0
            self.flash = 6
            texts.append(FloatingText(self.x, self.y - 240, "BLOCK",
                                      (120, 200, 255)))
            log("%s guarded for %d -> dummy hp %d/%d"
                % (move, damage, self.hp, self.max_hp))
        else:
            self.vx = knock * direction
            self.flash = 8
            texts.append(FloatingText(self.x, self.y - 232, f"-{damage}",
                                      (255, 90, 90)))
            log("%s dealt %d -> dummy hp %d/%d (knock %.0f)"
                % (move, damage, self.hp, self.max_hp, knock))
        if self.hp == 0:
            play_sound("finisher")
            self.set_state("death")
            self.vx = 7 * direction
            log("KNOCKOUT - dummy down, respawn in %d frames" % DUMMY_RESPAWN_DELAY)
        elif not guarded:
            self.set_state("hurt")

    def update(self, player=None):
        """Advance the dummy one tick: knockback, respawn, approach and swing."""
        self.state_time += 1
        if self.flash > 0:
            self.flash -= 1
        if self.atk_cd > 0:
            self.atk_cd -= 1
        if self.decision_cd > 0:
            self.decision_cd -= 1

        if not self.alive:
            self.x += self.vx
            self.vx *= 0.90
            self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))
            if self.respawn == 0 and self.state == "death" and self.state_time >= self.lock["death"]:
                self.respawn = DUMMY_RESPAWN_DELAY
            if self.respawn > 0:
                self.respawn -= 1
                if self.respawn == 0:
                    self.hp = self.max_hp
                    self.x = self.home_x
                    self.vx = 0
                    self.set_state("idle")
                    log("dummy respawned at x=%.0f with full hp" % self.x)
            dur = self.durations[self.state]
            self.anim_index = min(self.state_time // dur, len(self.anims[self.state]) - 1)
            return

        # knockback slide, never past the arena walls
        if abs(self.vx) > 0.1:
            self.x += self.vx
            self.vx *= 0.86
            if self.x <= ARENA_LEFT or self.x >= ARENA_RIGHT:
                self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))
                self.vx = 0
        else:
            self.vx = 0

        if self.state in ("hurt", "guard", "blink") and \
                self.state_time >= self.lock[self.state]:
            self.set_state("idle")

        self.think(player)

        # Optional retreat: only while idle and no longer sliding from a hit.
        if DUMMY_DRIFT_HOME and self.state == "idle" and abs(self.vx) <= 0.1:
            if self.x > self.home_x + 2:
                self.x -= DUMMY_RETURN_SPEED
            elif self.x < self.home_x - 2:
                self.x += DUMMY_RETURN_SPEED

        dur = self.durations[self.state]
        frames = self.anims[self.state]
        step = self.state_time // dur
        if self.state in DUMMY_LOOPING:
            self.anim_index = step % len(frames)
        else:
            self.anim_index = min(step, len(frames) - 1)

    def think(self, player):
        """Rival brain: spacing, telegraphed swings, tier-scaled reactions."""
        if player is None or not self.alive:
            return
        if self.state in ("hurt", "death") or self.busy():
            return
        # a wind-up that has run its course always commits to the swing
        if self.state == "tell":
            self.begin("attack")
            play_sound("swing")
            self.atk_cd = self.atk_cd_max
            log("%s commits after the tell" % self.label)
            return

        style = PERSONALITY.get(self.personality, PERSONALITY["balanced"])
        self.facing_right = player.x > self.x
        gap = abs(player.x - self.x)

        # locomotion runs every frame so closing in never looks stuttered
        if gap > DUMMY_ATTACK_RANGE:
            step = self.walk_speed * style["approach"]
            self.x += step if self.facing_right else -step
        elif style["spacing"] and gap < style["spacing"]:
            step = self.walk_speed * 0.7
            self.x -= step if self.facing_right else -step
        self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))

        # choices are rationed so it reads as decisions rather than twitching
        if self.decision_cd > 0:
            return
        self.decision_cd = 8

        recovering = player.down_timer > 0 or player.state == "hurt"
        if self.punish_ok and recovering and self.atk_cd <= 0:
            self.begin("attack")
            play_sound("swing")
            self.atk_cd = self.atk_cd_max
            log("%s punishes the recovery" % self.label)
            return

        swinging = (player.state in ATTACKS
                    and player.state_time < player.lock[player.state])
        if (swinging and self.react_chance > 0
                and gap <= DUMMY_ATTACK_RANGE + 60
                and random.random() < self.react_chance):
            if random.random() < style["blink"]:
                self.begin("blink")
                self.x += 90 if self.x < player.x else -90
                self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))
                log("%s blinks clear" % self.label)
            else:
                self.begin("guard")
                log("%s guards the swing" % self.label)
            self.decision_cd = 10
            return

        if self.atk_cd <= 0 and gap <= DUMMY_ATTACK_RANGE:
            self.begin("tell")           # readable wind-up before the hit
            self.decision_cd = 0

    def draw(self, screen, hit_flash=True):
        if not self.alive and self.respawn > 0 and self.state == "death":
            if self.respawn % 6 < 3:
                return
        frames = self.tinted_flipped_anims if self.facing_right else self.tinted_anims
        img = frames[self.state][self.anim_index]
        pos = img.get_rect(midbottom=(int(self.x), int(self.y)))
        screen.blit(img, pos)
        if hit_flash and self.flash > 0:
            flash = img.copy()
            flash.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGB_MAX)
            flash.set_alpha(FLASH_ALPHA)
            screen.blit(flash, pos)

    def draw_health(self, screen, font):
        if not self.alive:
            return
        w, h = HUD_W, HUD_BAR_H
        x = WIDTH - HUD_X - w
        y = HUD_BAR_Y
        draw_health_bar(screen, x, y, w, h,
                        self.hp / max(1, self.max_hp), mirror=True)
        label = outlined_text(font, "%s  %d/%d" % (self.label.upper(),
                                                   self.hp, self.max_hp),
                              (245, 245, 245))
        screen.blit(label, (x + w - label.get_width(), HUD_LABEL_Y))


class CharacterSpec:
    """One playable fighter: where its art lives and how it maps to moves.

    The CraftPix prototype sheets are 128px cells; the tiny hero sheets are
    42px and the monsters are 32px, so each spec carries its own cell size,
    zoom and body dimensions.
    """

    def __init__(self, key, label, folder, cell_w, zoom, sheets,
                 body_w, body_h, tint=None, hp=None, speed=None,
                 attack_overrides=None):
        self.key = key
        self.label = label
        self.folder = folder
        self.cell_w = cell_w
        self.zoom = zoom
        self.sheets = sheets          # state -> (filename, ticks per frame)
        self.body_w = body_w
        self.body_h = body_h
        self.tint = tint
        self.hp = hp                  # None -> PLAYER_MAX_HP
        self.speed = speed            # None -> MOVE_SPEED
        # state -> {reach/height/damage/knock/lunge: value}, on top of ATTACKS_DEF
        self.attack_overrides = attack_overrides or {}

    @property
    def exists(self):
        return os.path.isdir(self.folder)


def _roster_folder(*parts):
    return os.path.join(ROSTER, *parts)


def _hero_sheets(prefix, special="Attack2"):
    """Map game states onto a tiny hero's 16 named sheets.

    `special` picks the sheet shown for the meter-powered special move, so
    each fighter's signature move looks different without new art.
    """
    g = lambda n: (prefix + n + ".png", 5)  # noqa: E731
    return {
        "idle": g("Idle"), "run": g("Run"), "walk": g("Walk"),
        "jump": g("Jump"), "fall": g("FallAttack"), "land": g("Jump"),
        "glide": g("FallAttack"), "speed_run": g("Run"),
        "double_jump": g("Jump"), "wall_jump": g("Jump"),
        "punch1": g("Attack1"), "punch2": g("Attack2"),
        "kick": g("WalkAttack1"), "jump_kick": g("JumpAttack"),
        "fire_kick": g("RunAttack1"), "ice_strike": g("RunAttack2"),
        "power_strike": g("JumpAttack"), "slide_attack": g("SquatAttack"),
        "ground_slam": g("Attack2"), "super_strike": g("Attack2"),
        "special": g(special),
        "counter": g("SquatAttack"), "riposte": g("Attack1"),
        "cast": g("Attack1"), "charge": g("Squat"),
        "throw": g("Attack2"), "impact1": g("WalkAttack2"),
        "impact2": g("RunAttack2"), "ability": g("Attack1"),
        "dodge": g("Squat"), "block": g("Squat"), "hurt": g("Hurt"),
        "crouch": g("Squat"),
    }


def _monster_sheets(prefix):
    """Map game states onto a monster's named sheets."""
    g = lambda n, d=5: (prefix + n + ".png", d)  # noqa: E731
    return {
        "idle": g("Idle_4", 8), "run": g("Run_6"), "walk": g("Walk_6"),
        "jump": g("Jump_8"), "fall": g("Jump_8"), "land": g("Jump_8"),
        "glide": g("Jump_8"), "speed_run": g("Run_6"),
        "double_jump": g("Jump_8"), "wall_jump": g("Jump_8"),
        "punch1": g("Attack1_4"), "punch2": g("Attack2_6"),
        "kick": g("Walk+Attack_6"), "jump_kick": g("Jump_8"),
        "fire_kick": g("Attack2_6"), "ice_strike": g("Attack1_4"),
        "power_strike": g("Attack2_6"), "slide_attack": g("Push_6"),
        "ground_slam": g("Attack2_6"), "super_strike": g("Attack2_6"),
        "special": g("Attack2_6"),
        "counter": g("Push_6"), "riposte": g("Attack1_4"),
        "cast": g("Throw_4"), "charge": g("Push_6"),
        "throw": g("Throw_4"), "impact1": g("Attack2_6"),
        "impact2": g("Attack2_6"), "ability": g("Push_6"),
        "dodge": g("Climb_4"), "block": g("Push_6"), "hurt": g("Hurt_4"),
        "crouch": g("Push_6"),
    }


HERO_NAMES = ("Blade", "Ember", "Frost")
# (folder on disk, sheet prefix, display label)
MONSTER_PACKS = (
    ("1 Pink_Monster", "Pink_Monster_", "Pink Monster"),
    ("2 Owlet_Monster", "Owlet_Monster_", "Owlet"),
    ("3 Dude_Monster", "Dude_Monster_", "Dude Monster"),
)

# the sheet each hero shows for its meter-powered special move
HERO_SPECIAL_SHEETS = ("SquatAttack", "WalkAttack2", "RunAttack1")

PLAYER_ROSTER = tuple(
    CharacterSpec("hero_%d" % (i + 1), HERO_NAMES[i],
                  _roster_folder("heroes", "hero_%d" % (i + 1)),
                  42, 2, _hero_sheets("", HERO_SPECIAL_SHEETS[i]), 74, 150)
    for i in range(3))

RIVAL_ROSTER = tuple(
    CharacterSpec("monster_%d" % (i + 1), label, _roster_folder("monsters", folder),
                  32, 2, _monster_sheets(prefix), 62, 120)
    for i, (folder, prefix, label) in enumerate(MONSTER_PACKS))

def _proto_sheets(**overrides):
    """Prototype animation map: state -> (pack, file, ticks), plus overrides.

    The stock prototype reads every state straight from ANIMS; a variant
    swaps whole animations for sheets the base move set never touches, so
    the same key plays a visibly different move.
    """
    sheets = {state: (pack, fname, dur)
              for state, (pack, fname, dur) in ANIMS.items()}
    sheets.update(overrides)
    return sheets


# Three builds of the same prototype, each with its own move set.
# Stock is the baseline; the Striker trades power for reach and mobility;
# the Tank gives up speed for single hits that hurt.
PROTO_SPECS = (
    CharacterSpec(
        "prototype", "Prototype", PACK_HERO, CELL_W, ZOOM,
        _proto_sheets(), 88, 148, None, 100, 5.0),
    CharacterSpec(
        "prototype_2", "Mk II Striker", PACK_HERO, CELL_W, ZOOM,
        _proto_sheets(
            dodge=(PACK_PROTO, "Roll.png", 4),
            jump_kick=(PACK_PROTO, "Jump witn Strike.png", 6),
            slide_attack=(PACK_PROTO, "Crawl.png", 5),
            charge=(PACK_PROTO, "Leap.png", 6),
            double_jump=(PACK_PROTO, "Side_Jump.png", 6),
        ),
        84, 148, (140, 255, 195), 85, 6.5,
        {
            "jump_kick":    {"reach": 34, "height": 60, "damage": 15, "knock": 3},
            "slide_attack": {"reach": 40, "height": 30, "damage": 9, "knock": 4},
            "charge":       {"lunge": 26, "reach": 46, "damage": 16, "knock": 10},
        }),
    CharacterSpec(
        "prototype_3", "Mk III Tank", PACK_HERO, CELL_W, ZOOM,
        _proto_sheets(
            block=(PACK_HERO, "Protect.png", 8),
            jump_kick=(PACK_HERO, "Jump_Strike.png", 6),
            charge=(PACK_HERO, "Ice_Charge.png", 6),
            ground_slam=(PACK_PROTO, "Landing with Impact.png", 6),
            wall_jump=(PACK_PROTO, "Upward Jump.png", 6),
        ),
        96, 152, (255, 175, 95), 130, 4.0,
        {
            "ground_slam": {"reach": 46, "height": 94, "damage": 26, "knock": 22},
            "charge":      {"lunge": 10, "reach": 40, "damage": 28, "knock": 18},
            "jump_kick":   {"reach": 32, "damage": 14, "knock": 8},
        }),
)

PROTO_SPEC = PROTO_SPECS[0]
PROTO_KEYS = frozenset(spec.key for spec in PROTO_SPECS)


_kenney_cache = {}


def kenney_piece(color, name, variant="Default"):
    """Load one Kenney sci-fi UI PNG, or None when it is absent."""
    key = ("piece", color, variant, name)
    if key in _kenney_cache:
        return _kenney_cache[key]
    surface = None
    path = os.path.join(KENNEY_UI, color, variant, name + ".png")
    if os.path.exists(path):
        try:
            surface = pygame.image.load(path).convert_alpha()
        except (OSError, pygame.error):
            surface = None
    _kenney_cache[key] = surface
    return surface


def kenney_bar(color, width, height, style="square", variant="Default"):
    """Nine-slice a Kenney bar: caps stay intact, the middle tiles."""
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        return None
    size = "small" if height <= 16 else "large"
    key = ("bar", color, style, variant, size, width, height)
    if key in _kenney_cache:
        return _kenney_cache[key]

    piece = lambda suffix: kenney_piece(
        color, "bar_%s_%s_%s" % (style, size, suffix), variant)
    left, middle, right = piece("l"), piece("m"), piece("r")
    if left is None or middle is None or right is None:
        return None

    def fit(surface):
        if surface.get_height() == height:
            return surface
        return pygame.transform.scale(surface, (surface.get_width(), height))

    left, middle, right = fit(left), fit(middle), fit(right)
    if width < left.get_width() + right.get_width():
        result = pygame.transform.scale(middle, (width, height))
        _kenney_cache[key] = result
        return result

    result = pygame.Surface((width, height), pygame.SRCALPHA)
    result.blit(left, (0, 0))
    result.blit(right, (width - right.get_width(), 0))
    x = left.get_width()
    end = width - right.get_width()
    while x < end:
        span = min(middle.get_width(), end - x)
        piece_surface = middle if span == middle.get_width() else \
            pygame.transform.scale(middle, (span, height))
        result.blit(piece_surface, (x, 0))
        x += span
    _kenney_cache[key] = result
    return result


def kenney_shadow(width, height, style="square"):
    """The pack's soft drop shadow, scaled behind a bar or button."""
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        return None
    key = ("shadow", style, width, height)
    if key in _kenney_cache:
        return _kenney_cache[key]
    source = kenney_piece("Extra", "bar_shadow_%s_large" % style)
    if source is None:
        return None
    result = pygame.transform.scale(source, (width, height))
    _kenney_cache[key] = result
    return result


def draw_health_bar(screen, x, y, width, height, ratio, mirror=False):
    """Health bar: a Kenney track and fill, with the drawn bar as fallback.

    mirror anchors the fill to the right edge so the rival's bar drains
    toward the centre of the screen, the way a versus HUD reads.
    """
    ratio = max(0.0, min(1.0, ratio))
    fill_name = ("Green" if ratio > 0.5 else
                 "Yellow" if ratio > 0.2 else "Red")
    shadow = kenney_shadow(width, height)
    track = kenney_bar("Grey", width, height)
    fill = kenney_bar(fill_name, width, height)
    if shadow is not None and track is not None and fill is not None:
        left, top = int(x), int(y)
        span = int(int(width) * ratio)
        screen.blit(shadow, (left + 2, top + 3))
        screen.blit(track, (left, top))
        if span > 0:
            fx = left + int(width) - span if mirror else left
            screen.blit(fill, (fx, top),
                        pygame.Rect(0, 0, span, int(height)))
        return
    pygame.draw.rect(screen, (28, 28, 34), (x - 2, y - 2, width + 4, height + 4))
    pygame.draw.rect(screen, (70, 70, 78), (x, y, width, height))
    color = ((90, 210, 110) if ratio > 0.5 else
             (240, 190, 70) if ratio > 0.2 else (230, 80, 70))
    fx = x + width * (1 - ratio) if mirror else x
    pygame.draw.rect(screen, color, (fx, y, width * ratio, height))
    pygame.draw.rect(screen, (15, 15, 18), (x, y, width, height), 2)


class StageProps:
    """Decoration sitting on the arena floor, from the tileset objects."""

    def __init__(self):
        self.items = []
        self.back_items = []
        for folder, fname, offset in STAGE_PROPS:
            path = os.path.join(TILESET, folder, fname)
            if not os.path.exists(path):
                continue
            img = pygame.image.load(path).convert_alpha()
            w, h = img.get_size()
            if w > 160:                      # strip sheets keep their first frame
                img = img.subsurface((0, 0, min(w, 64), h)).copy()
            self.items.append((img, offset))

        # These clean target sprites frame the arena without covering fighters.
        for fname, offset in (("Target.png", -360), ("Target.png", 360)):
            path = os.path.join(TILESET, "objects", fname)
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                self.back_items.append((pygame.transform.scale2x(img), offset))

    def draw_background(self, screen):
        """Draw target props behind the fighters."""
        for img, offset in self.back_items:
            x = WIDTH // 2 + offset
            screen.blit(img, img.get_rect(midbottom=(x, GROUND_Y + 4)))

    def draw(self, screen):
        for img, offset in self.items:
            x = WIDTH // 2 + offset
            screen.blit(img, img.get_rect(midbottom=(x, GROUND_Y + 4)))


# some packs number their layers back to front, others front to back.
# Anything not listed here is simply drawn in ascending order.
LAYER_ORDER = {
    "Castle_1": [0, 1, 2, 3],
    "Castle_2": [4, 3, 0, 2, 1],
    "Castle_3": [4, 3, 2, 1, 0],
    "Castle_4": [0, 1, 2, 3],
}


_background_cache = {}


class Background:
    """Layered CraftPix stage: sky first, then each nearer layer on top."""

    def __init__(self, folder):
        if folder in _background_cache:
            self.folder, self.name, self.layers = _background_cache[folder]
            return
        self.folder = folder
        self.name = os.path.basename(folder)
        self.layers = []
        if not os.path.isdir(folder):
            _background_cache[folder] = (self.folder, self.name, self.layers)
            return
        files = {}
        for filename in os.listdir(folder):
            if not filename.lower().endswith(".png"):
                continue
            try:
                number = int(os.path.splitext(filename)[0])
            except ValueError:
                continue
            files[number] = os.path.join(folder, filename)
        order = LAYER_ORDER.get(self.name, sorted(files))
        for num in order:
            if num not in files:
                continue
            img = pygame.image.load(files[num]).convert_alpha()
            self.layers.append(pygame.transform.scale(img, (WIDTH, HEIGHT)))
        _background_cache[folder] = (self.folder, self.name, self.layers)

    @property
    def ok(self):
        return len(self.layers) > 0


def available_scenes():
    if not os.path.isdir(BACKGROUNDS):
        return []
    return sorted(os.path.join(BACKGROUNDS, d) for d in os.listdir(BACKGROUNDS)
                  if os.path.isdir(os.path.join(BACKGROUNDS, d)))


def draw_name_tag(screen, font, x, text, color):
    """Little marker under a fighter so you always know who is who."""
    y = GROUND_Y + 8
    pygame.draw.polygon(screen, (12, 12, 16),
                         [(x - 11, y - 2), (x + 11, y - 2), (x, y + 11)])
    pygame.draw.polygon(screen, color,
                         [(x - 8, y - 1), (x + 8, y - 1), (x, y + 8)])
    img = outlined_text(font, text, color)
    screen.blit(img, (x - img.get_width() / 2, y + 12))


def draw_stage(screen, background=None):
    if background is not None and background.ok:
        for layer in background.layers:
            screen.blit(layer, (0, 0))
    else:
        for y in range(0, GROUND_Y, 40):
            shade = 34 + (y // 40) * 4
            pygame.draw.rect(screen, (shade, shade, shade + 10), (0, y, WIDTH, 40))

    # the tileset's own tiles carry printed size labels, so the floor is drawn
    # plainly and the tileset is used for props only
    pygame.draw.rect(screen, (58, 50, 44), (0, GROUND_Y, WIDTH,
                               HEIGHT - GROUND_Y))
    pygame.draw.line(screen, (146, 126, 100), (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
    for x in range(0, WIDTH, 96):
        pygame.draw.line(screen, (74, 64, 56), (x, GROUND_Y + 4),
                         (x - 20, HEIGHT), 2)

    # arena walls, so it is obvious where the fighters are kept
    pygame.draw.line(screen, (90, 80, 120), (ARENA_LEFT - 14, 0), (ARENA_LEFT - 14, GROUND_Y), 2)
    pygame.draw.line(screen, (90, 80, 120), (ARENA_RIGHT + 14, 0), (ARENA_RIGHT + 14, GROUND_Y), 2)


class SettingsManager:
    """Load and save presentation options and the existing game bindings."""

    DEFAULTS = {
        "master_volume": 1.0,
        "sfx_volume": 1.0,
        "muted": False,
        "fullscreen": False,
        "show_fps": False,
        "screen_shake": False,
        "shake_intensity": 1.0,
        "damage_numbers": True,
        "hit_flash": True,
        "combat_effects": True,
        "enemy_health_bar": True,
        "debug_overlay": False,
        "text_scale": 1.0,
        "reduced_flash": False,
        "reduced_motion": False,
        "high_contrast": False,
        "difficulty": 1.0,           # 0.5 EASY / 1.0 NORMAL / 1.5 HARD
    }

    def __init__(self, path: str = SETTINGS_PATH) -> None:
        """Load saved values, falling back to the shipped controls/settings."""
        self.path = path
        self.values: dict[str, bool | float] = dict(self.DEFAULTS)
        self.keybinds: dict[str, int] = dict(DEFAULT_BINDINGS)
        try:
            saved = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            saved = {}
        if isinstance(saved, dict):
            for name, default in self.DEFAULTS.items():
                value = saved.get(name, default)
                if isinstance(default, bool):
                    if isinstance(value, bool):
                        self.values[name] = value
                elif isinstance(value, (int, float)):
                    self.values[name] = max(0.0, min(1.5, float(value)))
            raw_bindings = saved.get("keybinds", {})
            version_ok = saved.get("binds_version", 0) >= BINDS_VERSION
            if version_ok and isinstance(raw_bindings, dict):
                candidate = {}
                used = set()
                valid = True
                for action, default_key in self.keybinds.items():
                    key = raw_bindings.get(action, default_key)
                    if (not isinstance(key, int) or isinstance(key, bool) or key < 0
                            or key in used or not self._is_real_key(key)):
                        valid = False
                        break
                    candidate[action] = key
                    used.add(key)
                if valid:
                    self.keybinds = candidate
        self.apply_audio()

    @staticmethod
    def _is_real_key(key: int) -> bool:
        """True if pygame knows a name for this key code."""
        try:
            return bool(pygame.key.name(key))
        except (OverflowError, ValueError, pygame.error):
            return False

    def save(self) -> None:
        """Persist settings independently from the run log and best score."""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = dict(self.values)
            payload["keybinds"] = self.keybinds
            payload["binds_version"] = BINDS_VERSION
            Path(self.path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    def apply_audio(self) -> None:
        """Apply the supported master and sound-effects levels."""
        volume = 0.0 if self.values["muted"] else (
            0.42 * self.values["master_volume"] * self.values["sfx_volume"])
        for sound in SOUNDS.values():
            sound.set_volume(max(0.0, min(1.0, volume)))

    def set_value(self, name: str, value: bool | float) -> None:
        self.values[name] = value
        if name in ("master_volume", "sfx_volume", "muted"):
            self.apply_audio()
        self.save()

    def bind(self, action: str, key: int) -> Optional[str]:
        """Assign an unused keyboard key, returning the conflicting action."""
        conflict = next((other for other, assigned in self.keybinds.items()
                         if assigned == key and other != action), None)
        if conflict is not None:
            return conflict
        self.keybinds[action] = key
        self.save()
        return None


@dataclass
class ArcadeChallenge:
    """Score five dummy knockouts before losing all three lives."""
    rounds_total: int = 5
    lives: int = 3
    rounds_won: int = 0
    score: int = 0
    high_score: int = 0
    last_award: int = 0
    finished: bool = False
    result: str = ""

    def win_round(self, player: Player) -> None:
        """Award a win, combo, and remaining-health score bonus."""
        self.rounds_won += 1
        self.last_award = 1000 + player.combo * 100 + max(0, player.hp) * 10
        self.score += self.last_award
        if self.rounds_won >= self.rounds_total:
            self.finished = True
            self.result = "ARCADE CLEAR"

    def lose_life(self) -> None:
        """Record a knockout and end the run when no lives remain."""
        self.lives = max(0, self.lives - 1)
        if self.lives == 0:
            self.finished = True
            self.result = "GAME OVER"


ARCADE_RIVALS = (
    ("Crimson Guard", DUMMY_TINT, "Double_Srtike.png", "balanced"),
    ("Azure Duelist", (105, 165, 255), "Aerial_Strike.png", "rushdown"),
    ("Violet Warden", (205, 130, 255), "Energy_Wave.png", "evasive"),
    ("Jade Phantom", (100, 220, 160), "Attack_From_Cover.png", "punisher"),
    ("Amber Shade", (255, 190, 90), "Wind_Power.png", "heavy"),
)
HIGH_SCORE_PATH = os.path.join(BASE_DIR, "logs", "arcade_high_score.txt")


def load_high_score() -> int:
    """Read the saved arcade score, or start at zero."""
    try:
        return int(Path(HIGH_SCORE_PATH).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def save_high_score(challenge: ArcadeChallenge) -> None:
    """Persist a new best score without interrupting play on disk errors."""
    if challenge.score <= challenge.high_score:
        return
    challenge.high_score = challenge.score
    try:
        os.makedirs(os.path.dirname(HIGH_SCORE_PATH), exist_ok=True)
        Path(HIGH_SCORE_PATH).write_text(str(challenge.high_score), encoding="utf-8")
    except OSError:
        pass


@dataclass
class GameState:
    """Everything the main loop and its helpers pass around."""
    scenes: list
    scene_index: int = 0
    default_scene_index: int = 0
    background: Optional["Background"] = None
    background_cache: dict = field(default_factory=dict)
    running: bool = True
    hitstop: int = 0
    show_log: bool = True
    show_debug: bool = False
    menu_screen: str = "game"
    menu_origin: str = "pause"
    menu_index: int = 0
    settings_category: int = 0
    rebind_action: Optional[str] = None
    dialog_action: Optional[str] = None
    dialog_return_screen: Optional[str] = None
    notice: str = ""
    notice_timer: int = 0
    menu_keys_down: set = field(default_factory=set)
    suppressed_keys: set = field(default_factory=set)
    shake_frames: int = 0
    settings: SettingsManager = field(default_factory=SettingsManager)
    challenge: ArcadeChallenge = field(default_factory=ArcadeChallenge)


def cycle_player_character(player: Player, step=1) -> None:
    """Step through the player roster: the prototype plus three tiny heroes."""
    roster = list(PROTO_SPECS) + list(PLAYER_ROSTER)
    names = [spec.key for spec in roster]
    current = player.spec.key if player.spec is not None else names[0]
    index = names.index(current) if current in names else 0
    spec = roster[(index + step) % len(roster)]
    if spec.key in PROTO_KEYS:
        player.use_prototype(spec)
        player.set_state("idle")
        log("player character -> %s" % spec.label)
        return
    player.set_character(spec)


def cycle_rival_character(dummy: Dummy, step=1) -> None:
    """Step through the three monsters for the rival."""
    names = [spec.key for spec in RIVAL_ROSTER]
    current = dummy.spec.key if dummy.spec is not None else names[0]
    index = names.index(current) if current in names else 0
    dummy.set_character(RIVAL_ROSTER[(index + step) % len(RIVAL_ROSTER)])


#: Fighters the title screen lets you pick: the prototype plus the tiny heroes.
SELECTABLE_FIGHTERS = tuple(PROTO_SPECS) + tuple(PLAYER_ROSTER)

_FIGHTER_PREVIEW: dict = {}


def fighter_index(player: Player) -> int:
    """Where the player's current fighter sits in the title roster."""
    key = player.spec.key if player.spec is not None else PROTO_SPEC.key
    for index, spec in enumerate(SELECTABLE_FIGHTERS):
        if spec.key == key:
            return index
    return 0


def apply_fighter_spec(player: Player, spec) -> bool:
    """Equip one roster fighter, ignoring entries whose art is missing."""
    if spec is None or not spec.exists:
        return False
    if spec.key in PROTO_KEYS:
        player.use_prototype(spec)
        player.set_state("idle")
        return True
    return player.set_character(spec)


def apply_fighter(player: Player, index: int) -> None:
    apply_fighter_spec(player, SELECTABLE_FIGHTERS[index % len(SELECTABLE_FIGHTERS)])


def fighter_preview(spec) -> Optional[pygame.Surface]:
    """Cache a single idle frame per fighter so the select screen stays cheap."""
    cached = _FIGHTER_PREVIEW.get(spec.key)
    if cached is not None:
        return cached
    if not spec.exists:
        return None
    probe = Player(WIDTH // 2, GROUND_Y)
    if not apply_fighter_spec(probe, spec):
        return None
    frames = probe.anims.get("idle") or probe.anims.get("run")
    if not frames:
        return None
    image = frames[0]
    # Crop to the visible pixels: the prototype is drawn inside a 128px cell
    # while the heroes fill their 42px cells, so frame bounds alone make the
    # prototype render noticeably smaller than everything around it.
    box = image.get_bounding_rect()
    if box.width and box.height:
        image = image.subsurface(box).copy()
    else:
        image = image.copy()
    _FIGHTER_PREVIEW[spec.key] = image
    return image


def restart_arcade(player: Player, dummy: Dummy, texts: list, state: GameState) -> None:
    """Start a fresh run while keeping the saved high score and chosen fighter."""
    best = state.challenge.high_score
    chosen = player.spec
    Player.__init__(player, WIDTH // 2, GROUND_Y)
    if chosen is not None:
        apply_fighter_spec(player, chosen)
    Dummy.__init__(dummy, 660, GROUND_Y)
    dummy.set_rival(*ARCADE_RIVALS[0])
    texts.clear()
    state.challenge = ArcadeChallenge(high_score=best)
    state.hitstop = 0
    state.scene_index = state.default_scene_index
    if state.scenes:
        state.background = state.background_cache.get(state.scenes[state.scene_index])
    state.shake_frames = 0


SETTINGS_CATEGORIES = ("AUDIO", "DISPLAY", "GAMEPLAY", "ACCESSIBILITY")
CONTROL_ORDER = (
    "move_left", "move_right", "jump", "dodge", "block", "crouch_block", "special",
    "kick", "fire_kick",
    "power_strike", "ground_slam", "super_strike", "ice_strike", "slide_attack",
    "counter", "riposte", "cast", "charge", "throw", "ability",
    "impact1", "impact2", "debug", "log",
    "stage", "pause", "quit",
)


def control_key_name(state: GameState, action: str) -> str:
    """Return the live key name used by the game and the controls menu."""
    return pygame.key.name(state.settings.keybinds[action]).upper()


def settings_rows(state: GameState) -> list[dict[str, str]]:
    """Return the working options for the selected settings category."""
    category = SETTINGS_CATEGORIES[state.settings_category]
    by_category = {
        "AUDIO": [
            ("master_volume", "Master volume", "slider"),
            ("sfx_volume", "Sound effects", "slider"),
            ("muted", "Mute all", "toggle"),
        ],
        "DISPLAY": [
            ("fullscreen", "Display mode", "toggle_window"),
            ("show_fps", "FPS display", "toggle"),
            ("resolution", "Resolution", "info"),
        ],
        "GAMEPLAY": [
            ("screen_shake", "Screen shake", "toggle"),
            ("damage_numbers", "Damage numbers", "toggle"),
            ("hit_flash", "Hit flash", "toggle"),
            ("combat_effects", "Combat feedback effects", "toggle"),
            ("enemy_health_bar", "Rival health bar", "toggle"),
            ("difficulty", "Rival difficulty", "cycle_difficulty"),
            ("debug_overlay", "Debug overlay", "toggle"),
        ],
        "ACCESSIBILITY": [
            ("text_scale", "Text size", "cycle_text"),
            ("shake_intensity", "Screen shake intensity", "cycle_shake"),
            ("reduced_flash", "Reduced flash effects", "toggle"),
            ("reduced_motion", "Reduced motion", "toggle"),
            ("high_contrast", "High contrast interface", "toggle"),
        ],
    }
    return [{"key": key, "label": label, "kind": kind}
            for key, label, kind in by_category[category]]


def setting_display(state: GameState, row: dict[str, str]) -> str:
    """Format a setting value without introducing unsupported controls."""
    key, kind = row["key"], row["kind"]
    values = state.settings.values
    if key == "resolution":
        return "FIXED 960 x 540"
    if kind == "toggle_window":
        return "FULLSCREEN" if values[key] else "WINDOWED"
    if kind == "toggle":
        return "ON" if values[key] else "OFF"
    if kind == "slider":
        return "%d%%" % round(values[key] * 100)
    if kind == "cycle_text":
        choices = (0.9, 1.0, 1.1)
        index = min(range(len(choices)), key=lambda i: abs(choices[i] - values[key]))
        return ("SMALL", "NORMAL", "LARGE")[index]
    if kind == "cycle_shake":
        choices = (0.5, 1.0, 1.5)
        index = min(range(len(choices)), key=lambda i: abs(choices[i] - values[key]))
        return ("LOW", "MEDIUM", "HIGH")[index]
    if kind == "cycle_difficulty":
        choices = (0.5, 1.0, 1.5)
        index = min(range(len(choices)), key=lambda i: abs(choices[i] - values[key]))
        return ("EASY", "NORMAL", "HARD")[index]
    return ""


def change_setting(state: GameState, row: dict[str, str], direction: int,
                   slider_ratio: Optional[float] = None) -> None:
    """Apply a menu change to a supported option and persist it."""
    key, kind = row["key"], row["kind"]
    if kind == "info":
        return
    values = state.settings.values
    if kind == "slider":
        value = slider_ratio if slider_ratio is not None else values[key] + direction * 0.05
        state.settings.set_value(key, round(max(0.0, min(1.0, value)), 2))
    elif kind in ("toggle", "toggle_window"):
        state.settings.set_value(key, not values[key])
        if key == "debug_overlay":
            state.show_debug = state.settings.values[key]
    elif kind == "cycle_text":
        choices = (0.9, 1.0, 1.1)
        index = min(range(len(choices)), key=lambda i: abs(choices[i] - values[key]))
        state.settings.set_value(key, choices[(index + direction) % len(choices)])
    elif kind == "cycle_shake":
        choices = (0.5, 1.0, 1.5)
        index = min(range(len(choices)), key=lambda i: abs(choices[i] - values[key]))
        state.settings.set_value(key, choices[(index + direction) % len(choices)])
    elif kind == "cycle_difficulty":
        choices = (0.5, 1.0, 1.5)
        index = min(range(len(choices)), key=lambda i: abs(choices[i] - values[key]))
        state.settings.set_value(key, choices[(index + direction) % len(choices)])


def menu_option_rects(state: GameState) -> list[tuple[str, pygame.Rect]]:
    """Shared button geometry keeps mouse hit targets aligned with the art."""
    if state.menu_screen == "pause":
        labels = ("RESUME", "RESTART RUN", "SETTINGS", "CONTROLS",
                  "HOW TO PLAY", "QUIT TO MAIN MENU")
        return [(name, pygame.Rect(320, 177 + i * 45, 320, 37))
                for i, name in enumerate(labels)]
    if state.menu_screen == "title":
        labels = ("START ARCADE", "SELECT FIGHTER", "SETTINGS", "CONTROLS",
                  "HOW TO PLAY", "QUIT")
        return [(name, pygame.Rect(320, 191 + i * 45, 320, 37))
                for i, name in enumerate(labels)]
    return []


FIGHTER_CARD_W = 188
FIGHTER_CARD_H = 250
FIGHTER_CARD_GAP = 20
FIGHTER_CARD_TOP = 118


def fighter_card_rect(index: int) -> pygame.Rect:
    """Shared geometry so keyboard focus and mouse clicks agree on a card."""
    count = max(1, len(SELECTABLE_FIGHTERS))
    gap = 14
    width = min(FIGHTER_CARD_W, (872 - 40 - gap * (count - 1)) // count)
    total = count * width + gap * (count - 1)
    x0 = (WIDTH - total) // 2
    return pygame.Rect(x0 + index * (width + gap),
                       FIGHTER_CARD_TOP, width, FIGHTER_CARD_H)


def controls_rows() -> list[str]:
    """List every keyboard action while leaving the original mouse map intact.

    "quit" stays bound internally so ESC can still leave the title screen, but
    it is hidden here: pause now owns ESC and two rows sharing one key would
    make rebinding confusing. Quitting during a run is done from the menu.
    """
    skip = ("quit",)
    ordered = [action for action in CONTROL_ORDER
               if action in DEFAULT_BINDINGS and action not in skip]
    return ordered + [action for action in DEFAULT_BINDINGS
                      if action not in CONTROL_ORDER and action not in skip]


def control_row_rect(index: int) -> pygame.Rect:
    """Place all bindings into three in-panel columns."""
    column, row = divmod(index, 10)
    return pygame.Rect(72 + column * 276, 134 + row * 31, 264, 26)


def show_menu(state: GameState, screen: str) -> None:
    """Open a menu page and remember whether it belongs to pause or title."""
    if screen in ("settings", "controls", "howto", "fighters"):
        state.menu_origin = "pause" if state.menu_screen == "pause" else "title"
    state.menu_screen = screen
    state.menu_index = 0
    state.rebind_action = None


def leave_menu_for_game(state: GameState) -> None:
    """Resume cleanly and suppress keys held while menu input was captured."""
    state.suppressed_keys.update(state.menu_keys_down)
    state.menu_keys_down.clear()
    state.rebind_action = None
    state.menu_screen = "game"


def open_confirmation(state: GameState, action: str) -> None:
    """Open the shared confirmation dialog for a destructive menu choice."""
    state.dialog_return_screen = state.menu_screen
    state.dialog_action = action
    state.menu_screen = "confirm"
    state.menu_index = 0


def cancel_confirmation(state: GameState) -> None:
    """Return to the page that opened the confirmation dialog."""
    state.menu_screen = state.dialog_return_screen or "pause"
    state.dialog_action = None
    state.dialog_return_screen = None
    state.menu_index = 0


def confirm_dialog(player: Player, dummy: Dummy, texts: list,
                   state: GameState) -> None:
    """Apply the selected restart, return-to-menu, or reset-bind action."""
    action = state.dialog_action
    if action == "restart":
        restart_arcade(player, dummy, texts, state)
        leave_menu_for_game(state)
    elif action == "quit_menu":
        restart_arcade(player, dummy, texts, state)
        state.menu_screen = "title"
        state.menu_index = 0
    elif action == "reset_binds":
        state.settings.keybinds = dict(DEFAULT_BINDINGS)
        state.settings.save()
        state.menu_screen = state.dialog_return_screen or "controls"
        state.notice = "Current default controls restored."
        state.notice_timer = 120
    elif action == "quit_game":
        state.running = False
    state.dialog_action = None
    state.dialog_return_screen = None


def activate_menu_item(name: str, player: Player, dummy: Dummy,
                       texts: list, state: GameState) -> None:
    """Run the selected pause or title menu command."""
    if name == "RESUME":
        leave_menu_for_game(state)
    elif name == "RESTART RUN":
        open_confirmation(state, "restart")
    elif name == "QUIT TO MAIN MENU":
        open_confirmation(state, "quit_menu")
    elif name == "START ARCADE":
        restart_arcade(player, dummy, texts, state)
        leave_menu_for_game(state)
    elif name == "SELECT FIGHTER":
        show_menu(state, "fighters")
        state.menu_index = fighter_index(player)
    elif name == "SETTINGS":
        show_menu(state, "settings")
    elif name == "CONTROLS":
        show_menu(state, "controls")
    elif name == "HOW TO PLAY":
        show_menu(state, "howto")
    elif name == "QUIT":
        open_confirmation(state, "quit_game")


def back_from_submenu(state: GameState) -> None:
    """Return from settings/reference screens to their parent menu."""
    state.menu_screen = state.menu_origin
    state.menu_index = 0
    state.rebind_action = None


def handle_menu_event(event: pygame.event.Event, player: Player, dummy: Dummy,
                      texts: list, state: GameState) -> None:
    """Route all input to menu widgets while gameplay is frozen."""
    if event.type == pygame.KEYDOWN:
        state.menu_keys_down.add(event.key)
        if state.rebind_action is not None:
            action = state.rebind_action
            if event.key == pygame.K_ESCAPE:
                state.rebind_action = None
                state.notice = "Rebinding cancelled."
            else:
                conflict = state.settings.bind(action, event.key)
                if conflict:
                    state.notice = "That key is already assigned to %s." % (
                        CONTROL_NAMES.get(conflict, conflict))
                else:
                    state.notice = "%s set to %s." % (
                        CONTROL_NAMES.get(action, action), pygame.key.name(event.key).upper())
                    state.rebind_action = None
            state.notice_timer = 150
            return

        screen = state.menu_screen
        if screen == "confirm":
            if event.key == pygame.K_ESCAPE:
                cancel_confirmation(state)
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
                state.menu_index = 1 - state.menu_index
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if state.menu_index == 0:
                    cancel_confirmation(state)
                else:
                    confirm_dialog(player, dummy, texts, state)
            return
        if screen == "pause" and event.key == state.settings.keybinds["pause"]:
            leave_menu_for_game(state)
            return
        if screen == "title" and event.key == state.settings.keybinds["quit"]:
            open_confirmation(state, "quit_game")
            return
        if event.key == pygame.K_ESCAPE:
            if screen == "pause":
                leave_menu_for_game(state)
            elif screen in ("settings", "controls", "howto", "fighters"):
                back_from_submenu(state)
            return
        if screen in ("pause", "title"):
            count = len(menu_option_rects(state))
            if event.key in (pygame.K_UP, pygame.K_w):
                state.menu_index = (state.menu_index - 1) % count
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                state.menu_index = (state.menu_index + 1) % count
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                name = menu_option_rects(state)[state.menu_index][0]
                activate_menu_item(name, player, dummy, texts, state)
            return
        if screen == "fighters":
            count = len(SELECTABLE_FIGHTERS)
            moving = (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                      pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_s)
            if event.key in moving:
                step = -1 if event.key in (pygame.K_LEFT, pygame.K_UP,
                                           pygame.K_a, pygame.K_w) else 1
                state.menu_index = (state.menu_index + step) % count
                apply_fighter(player, state.menu_index)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                back_from_submenu(state)
            return
        if screen == "settings":
            rows = settings_rows(state)
            if event.key == pygame.K_PAGEUP:
                state.settings_category = (state.settings_category - 1) % len(SETTINGS_CATEGORIES)
                state.menu_index = 0
            elif event.key == pygame.K_PAGEDOWN:
                state.settings_category = (state.settings_category + 1) % len(SETTINGS_CATEGORIES)
                state.menu_index = 0
            elif event.key == pygame.K_UP:
                state.menu_index = (state.menu_index - 1) % len(rows)
            elif event.key == pygame.K_DOWN:
                state.menu_index = (state.menu_index + 1) % len(rows)
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_SPACE):
                row = rows[state.menu_index]
                direction = -1 if event.key == pygame.K_LEFT else 1
                if row["kind"] == "info":
                    return
                if row["kind"] == "slider" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    direction = 1
                change_setting(state, row, direction)
            return
        if screen == "controls":
            rows = controls_rows()
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                delta = -1 if event.key == pygame.K_UP else 1
                state.menu_index = (state.menu_index + delta) % (len(rows) + 1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if state.menu_index == len(rows):
                    open_confirmation(state, "reset_binds")
                else:
                    state.rebind_action = rows[state.menu_index]
                    state.notice = "PRESS A KEY...  ESC CANCELS"
                    state.notice_timer = 999999
            elif event.key == pygame.K_r:
                open_confirmation(state, "reset_binds")
            return

    if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
        return
    pos = event.pos
    screen = state.menu_screen
    if screen in ("pause", "title"):
        for index, (name, rect) in enumerate(menu_option_rects(state)):
            if rect.collidepoint(pos):
                state.menu_index = index
                activate_menu_item(name, player, dummy, texts, state)
                return
    elif screen == "settings":
        for index in range(len(SETTINGS_CATEGORIES)):
            rect = pygame.Rect(72 + index * 204, 103, 196, 34)
            if rect.collidepoint(pos):
                state.settings_category = index
                state.menu_index = 0
                return
        rows = settings_rows(state)
        for index, row in enumerate(rows):
            rect = pygame.Rect(72, 151 + index * 48, 816, 40)
            if rect.collidepoint(pos):
                state.menu_index = index
                if row["kind"] == "slider":
                    slider = setting_slider_rect(rect)
                    if slider.collidepoint(pos):
                        ratio = max(0.0, min(1.0,
                                             (pos[0] - slider.x) / max(1, slider.w - 1)))
                        change_setting(state, row, 0, ratio)
                elif row["kind"] != "info":
                    change_setting(state, row, 1)
                return
    elif screen == "controls":
        rows = controls_rows()
        for index, action in enumerate(rows):
            rect = control_row_rect(index)
            if rect.collidepoint(pos):
                state.menu_index = index
                state.rebind_action = action
                state.notice = "PRESS A KEY...  ESC CANCELS"
                state.notice_timer = 999999
                return
        if pygame.Rect(650, 455, 238, 34).collidepoint(pos):
            open_confirmation(state, "reset_binds")
    elif screen == "fighters":
        for index in range(len(SELECTABLE_FIGHTERS)):
            if fighter_card_rect(index).collidepoint(pos):
                state.menu_index = index
                apply_fighter(player, index)
                return
    elif screen == "howto":
        if pygame.Rect(766, 460, 112, 32).collidepoint(pos):
            back_from_submenu(state)
    elif screen == "confirm":
        if pygame.Rect(306, 344, 166, 39).collidepoint(pos):
            cancel_confirmation(state)
        elif pygame.Rect(488, 344, 166, 39).collidepoint(pos):
            confirm_dialog(player, dummy, texts, state)


# bindings that are handled by the menu/UI code instead of being combat actions
NON_COMBAT_BINDINGS = ("move_left", "move_right", "block", "crouch_block",
                       "debug", "log", "stage",
                       "pause", "quit", "hero", "monster")


def perform_action(player: Player, action: str) -> None:
    """Run one bound action (from a key or a mouse button) on the player."""
    if action == "jump":
        player.try_jump()
    elif action == "kick":
        if player.on_ground:
            player.attack("kick")
        else:
            player.air_attack()
    else:
        player.attack(action)


class FilteredKeys:
    """Hide keys that were held while a menu closed until they are released."""

    def __init__(self, source, blocked: set[int]) -> None:
        self.source = source
        self.blocked = blocked

    def __getitem__(self, key: int) -> bool:
        return False if key in self.blocked else self.source[key]


def handle_events(events: list, player: Player, dummy: Dummy, texts: list,
                  state: GameState) -> None:
    """Apply one frame of input to the player and the UI state."""
    menu_consumed = False
    bindings = state.settings.keybinds
    for event in events:
        if event.type == pygame.QUIT:
            state.running = False
            continue
        if menu_consumed:
            if event.type == pygame.KEYDOWN:
                if state.menu_screen == "game":
                    state.suppressed_keys.add(event.key)
                else:
                    state.menu_keys_down.add(event.key)
            continue
        if state.menu_screen != "game":
            handle_menu_event(event, player, dummy, texts, state)
            if state.menu_screen == "game":
                menu_consumed = True
            continue
        if state.challenge.finished:
            if event.type == pygame.MOUSEBUTTONDOWN:
                restart_arcade(player, dummy, texts, state)
                state.suppressed_keys.update(state.menu_keys_down)
                state.menu_keys_down.clear()
                menu_consumed = True
            elif event.type == pygame.KEYDOWN:
                if event.key == bindings["pause"]:
                    state.menu_screen = "pause"
                    state.menu_index = 0
                    state.menu_keys_down.add(event.key)
                    menu_consumed = True
                elif event.key == bindings["quit"]:
                    state.running = False
            continue
        if event.type == pygame.KEYDOWN and event.key == bindings["pause"]:
            state.menu_screen = "pause"
            state.menu_index = 0
            state.menu_keys_down.add(event.key)
            menu_consumed = True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            action = MOUSE_ACTIONS.get(event.button)
            if action:
                perform_action(player, action)
        elif event.type == pygame.KEYDOWN:
            if event.key == bindings["debug"]:
                state.show_debug = not state.show_debug
                state.settings.set_value("debug_overlay", state.show_debug)
            elif event.key == bindings["log"]:
                state.show_log = not state.show_log
            elif event.key == bindings["hero"]:
                cycle_player_character(player)
            elif event.key == bindings["monster"]:
                cycle_rival_character(dummy)
            elif event.key == bindings["stage"] and state.scenes:
                state.scene_index = (state.scene_index + 1) % len(state.scenes)
                scene = state.scenes[state.scene_index]
                if scene not in state.background_cache:
                    state.background_cache[scene] = Background(scene)
                state.background = state.background_cache[scene]
                log("stage -> %s (%d layers)"
                    % (state.background.name, len(state.background.layers)))
            elif event.key == bindings["quit"]:
                state.running = False
            else:
                action = next((name for name, key in bindings.items()
                               if key == event.key and name not in NON_COMBAT_BINDINGS),
                              None)
                if action:
                    perform_action(player, action)


def update(player: Player, dummy: Dummy, texts: list, state: GameState) -> None:
    """Advance one fixed simulation tick, preserving combat update order."""
    if state.menu_screen != "game" or state.challenge.finished:
        return

    if state.notice_timer > 0:
        state.notice_timer -= 1
    if state.hitstop > 0:
        state.hitstop -= 1
    else:
        keys = pygame.key.get_pressed()
        for key in tuple(state.suppressed_keys):
            if not keys[key]:
                state.suppressed_keys.discard(key)
        player.update(FilteredKeys(keys, state.suppressed_keys), state.settings.keybinds)
        dummy.sync_tier(state.challenge.rounds_won,
                        state.settings.values["difficulty"])
        dummy.update(player)

        dummy.facing_right = dummy.x > player.x
        hit = player.hitbox()
        if hit and dummy.alive and hit[0].colliderect(dummy.body()):
            rect, damage, knock = hit
            player.connected = True
            move = player.state
            if move == "super_strike" and player.combo >= FINISHER_MIN_COMBO:
                damage = int(damage * FINISHER_MULT)
                knock = int(knock * 1.4)
                log("FINISHER! super on a %d hit combo" % player.combo)
                texts.append(FloatingText(dummy.x, dummy.y - 258,
                                          "FINISHER", (255, 210, 90)))
            player.register_hit(damage)
            dummy.take_hit(player.x, damage, knock, texts, move)
            if move == "special":
                play_sound("finisher")
                texts.append(FloatingText(dummy.x, dummy.y - 276,
                                          "SPECIAL", (120, 220, 255)))
            if state.settings.values["screen_shake"]:
                state.shake_frames = max(state.shake_frames, 5)
            if not dummy.alive:
                state.challenge.win_round(player)
                save_high_score(state.challenge)
                log("ARCADE ROUND %d/%d SCORE +%d TOTAL %d"
                    % (state.challenge.rounds_won, state.challenge.rounds_total,
                       state.challenge.last_award, state.challenge.score))
                if not state.challenge.finished:
                    dummy.set_rival(*ARCADE_RIVALS[state.challenge.rounds_won])
            state.hitstop = 9 if move in ("ground_slam", "special") else 5
            player.x += 4 if player.facing_right else -4

        # the dummy hits back (resolved after the player's hit, as before)
        dummy_hit = dummy.hitbox()
        if (dummy_hit and player.down_timer <= 0
                and dummy_hit[0].colliderect(player.body())):
            dummy.connected = True
            player.take_damage(dummy_hit[1], dummy.x, dummy_hit[2], texts)
            if state.settings.values["screen_shake"]:
                state.shake_frames = max(state.shake_frames, 4)
            if player.down_timer > 0:
                state.challenge.lose_life()
                save_high_score(state.challenge)
                log("ARCADE LIVES %d SCORE %d"
                    % (state.challenge.lives, state.challenge.score))
            state.hitstop = 4

    if state.shake_frames > 0:
        state.shake_frames -= 1

    for floating in list(texts):
        floating.update()
        if floating.life <= 0:
            texts.remove(floating)


def ui_palette(state: GameState) -> tuple[tuple[int, int, int], ...]:
    """Return pixel-interface colors, with an optional high-contrast accent."""
    high = state.settings.values["high_contrast"]
    return ((255, 255, 0), (255, 255, 255), (220, 235, 255)) if high else (
        (255, 214, 120), (225, 230, 242), (125, 185, 240))


class UIAtlas:
    """Nine-slice the existing pixel button plates without smoothing them."""

    def __init__(self) -> None:
        self.frames: dict[str, pygame.Surface] = {}
        self.scaled: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}
        path = os.path.join(ASSETS, "ui", "00.png")
        try:
            sheet = pygame.image.load(path).convert_alpha()
        except (OSError, pygame.error):
            return
        for name, x in (("panel", 0), ("normal", 64), ("selected", 128)):
            self.frames[name] = sheet.subsurface((x, 80, 48, 20)).copy()
        self.frames["panel"].fill((0, 0, 0, 0), (8, 6, 32, 8))

    @property
    def ok(self) -> bool:
        return len(self.frames) == 3

    def image(self, name: str, size: tuple[int, int]) -> Optional[pygame.Surface]:
        """Return a cached nearest-neighbour nine-slice at the requested size."""
        if not self.ok or size[0] <= 0 or size[1] <= 0:
            return None
        key = (name, size)
        if key in self.scaled:
            return self.scaled[key]

        source = self.frames[name]
        source_w, source_h = source.get_size()
        corner_x, corner_y = 8, 6
        left, right = min(corner_x, size[0] // 2), min(corner_x, size[0] // 2)
        top, bottom = min(corner_y, size[1] // 2), min(corner_y, size[1] // 2)
        source_x = (0, corner_x, source_w - corner_x, source_w)
        source_y = (0, corner_y, source_h - corner_y, source_h)
        target_x = (0, left, size[0] - right, size[0])
        target_y = (0, top, size[1] - bottom, size[1])
        result = pygame.Surface(size, pygame.SRCALPHA)
        for row in range(3):
            for col in range(3):
                src_rect = pygame.Rect(source_x[col], source_y[row],
                                       source_x[col + 1] - source_x[col],
                                       source_y[row + 1] - source_y[row])
                dst_rect = pygame.Rect(target_x[col], target_y[row],
                                       target_x[col + 1] - target_x[col],
                                       target_y[row + 1] - target_y[row])
                if dst_rect.w and dst_rect.h:
                    piece = source.subsurface(src_rect)
                    result.blit(pygame.transform.scale(piece, dst_rect.size), dst_rect)
        self.scaled[key] = result
        return result


_ui_atlas: Optional[UIAtlas] = None


def ui_atlas() -> UIAtlas:
    """Load the shipped UI plates once, with a drawn fallback if absent."""
    global _ui_atlas
    if _ui_atlas is None:
        _ui_atlas = UIAtlas()
    return _ui_atlas


def draw_ui_panel(screen: pygame.Surface, rect: pygame.Rect,
                  state: GameState) -> None:
    """Draw the shipped pixel frame, or the simple fallback panel."""
    atlas = ui_atlas()
    if atlas.ok:
        screen.blit(translucent_rect(rect.size, (0, 0, 0, 210)), rect.move(5, 5))
        screen.blit(translucent_rect(rect.size, (12, 15, 24, 220)), rect)
        frame = atlas.image("panel", rect.size)
        if frame is not None:
            screen.blit(frame, rect)
        return

    accent, _, _ = ui_palette(state)
    pygame.draw.rect(screen, (0, 0, 0), rect.move(5, 5))
    pygame.draw.rect(screen, (17, 20, 31), rect)
    pygame.draw.rect(screen, (83, 99, 139), rect, 2)
    pygame.draw.rect(screen, accent, rect, 1)
    for x, y in ((rect.left + 7, rect.top + 7), (rect.right - 10, rect.top + 7),
                 (rect.left + 7, rect.bottom - 10), (rect.right - 10, rect.bottom - 10)):
        pygame.draw.rect(screen, accent, (x, y, 3, 3))


def draw_ui_button(screen: pygame.Surface, rect: pygame.Rect, label: str,
                   selected: bool, font: pygame.font.Font,
                   state: GameState) -> None:
    """Draw a keyboard- and mouse-selectable pixel button."""
    accent, text_color, _ = ui_palette(state)
    plate = kenney_bar("Yellow" if selected else "Blue",
                       rect.w, rect.h, "round")
    if plate is not None:
        shadow = kenney_shadow(rect.w, rect.h, "round")
        if shadow is not None:
            screen.blit(shadow, (rect.x + 2, rect.y + 3))
        screen.blit(plate, rect)
        label_color = (26, 20, 6) if selected else text_color
    else:
        image = ui_atlas().image("selected" if selected else "normal", rect.size)
        if image is None:
            fill = (48, 49, 60) if selected else (25, 29, 42)
            border = accent if selected else (75, 84, 111)
            pygame.draw.rect(screen, fill, rect)
            pygame.draw.rect(screen, border, rect, 2 if selected else 1)
        else:
            screen.blit(image, rect)
        label_color = accent if selected else text_color
    image = outlined_text(font, label, label_color)
    screen.blit(image, image.get_rect(center=rect.center))


def setting_slider_rect(row_rect: pygame.Rect) -> pygame.Rect:
    """Use identical bounds for slider drawing and mouse input."""
    return pygame.Rect(row_rect.right - 238, row_rect.y + 15, 168, 10)


def draw_setting_row(screen: pygame.Surface, rect: pygame.Rect,
                     row: dict[str, str],
                     state: GameState, selected: bool,
                     font: pygame.font.Font, small: pygame.font.Font) -> None:
    """Render a setting's label, selection state, and current value."""
    accent, text_color, muted_color = ui_palette(state)
    values = state.settings.values
    if selected:
        pygame.draw.rect(screen, (38, 42, 56), rect)
        pygame.draw.rect(screen, accent, rect, 1)
    screen.blit(outlined_text(font, row["label"], text_color if selected else muted_color),
                (rect.x + 12, rect.y + 8))
    kind = row["kind"]
    if kind == "slider":
        bar = setting_slider_rect(rect)
        track = kenney_bar("Grey", bar.w, bar.h)
        fill_plate = kenney_bar("Blue", bar.w, bar.h)
        if track is not None and fill_plate is not None:
            screen.blit(track, bar)
            span = int(bar.w * values[row["key"]])
            if span > 0:
                screen.blit(fill_plate, bar,
                            pygame.Rect(0, 0, span, bar.h))
        else:
            pygame.draw.rect(screen, (59, 63, 77), bar)
            fill = pygame.Rect(bar.x, bar.y, int(bar.w * values[row["key"]]), bar.h)
            pygame.draw.rect(screen, accent, fill)
            pygame.draw.rect(screen, (9, 10, 16), bar, 1)
        value = setting_display(state, row)
        image = outlined_text(small, value, text_color)
        screen.blit(image, (rect.right - image.get_width() - 14, rect.y + 7))
    else:
        value = setting_display(state, row)
        image = outlined_text(small, value, accent if kind != "info" else muted_color)
        screen.blit(image, (rect.right - image.get_width() - 14, rect.y + 9))


def controls_mouse_rows() -> list[tuple[str, str]]:
    """Format the fixed mouse actions from the actual mouse action map."""
    names = {1: "LMB", 2: "MMB", 3: "RMB"}
    return [(names.get(button, "BUTTON %d" % button), action)
            for button, action in sorted(MOUSE_ACTIONS.items())]


def tutorial_sections(state: GameState) -> list[tuple[str, list[str]]]:
    """Build tutorial text from the active bindings and combat constants."""
    key = lambda name: control_key_name(state, name)
    mouse = {button: name for name, action in controls_mouse_rows()
             for button, current in MOUSE_ACTIONS.items() if current == action}
    return [
        ("MOVEMENT", [
            f"{key('move_left')} / {key('move_right')} walk. Hold a direction for {SPEED_RUN_AFTER} ticks to sprint.",
            f"{key('jump')} jumps; press it again in the air for a double jump. Hold it while falling to glide.",
            f"Jump beside either arena wall for a wall jump. {key('dodge')} performs the dodge roll.",
        ]),
        ("OFFENCE", [
            f"{mouse.get(1, 'LMB')} punch 1, {mouse.get(3, 'RMB')} punch 2, and {mouse.get(2, 'MMB')} plays the hurt test animation.",
            "Keyboard attacks use the bindings on the Controls screen. Attacks pressed during a move are buffered.",
        ]),
        ("COMBOS", [
            f"Connected hits build the combo counter; it expires after {COMBO_HOLD} inactive ticks.",
            f"A Super Strike on a combo of {FINISHER_MIN_COMBO}+ becomes a finisher with extra damage and knockback.",
        ]),
        ("DEFENCE", [
            f"Hold {key('block')} while grounded and free to block; blocked hits deal one quarter damage.",
            f"Hold {key('crouch_block')} instead for a crouching guard: same protection behind a much smaller hitbox.",
            f"{key('counter')} opens a {PARRY_WINDOW}-tick parry window. A successful parry starts a riposte.",
        ]),
        ("COMBAT FEEDBACK", [
            "Hits briefly stop the action, then apply knockback. Hit flashes, damage numbers, block and parry callouts show results.",
            f"The rival closes distance and attacks when in range. {key('debug')} debug, {key('log')} event log, {key('stage')} cycles development stages.",
        ]),
        ("ARCADE RUN", [
            f"Win {state.challenge.rounds_total} rivals before losing {state.challenge.lives} lives. Wins, remaining health, and combo hits add score.",
        ]),
    ]


def wrap_ui_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    """Wrap a menu paragraph without scaling or blurring its pixel font."""
    lines, current = [], ""
    for word in text.split():
        candidate = word if not current else current + " " + word
        if current and font.size(candidate)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _ramp(stops, t):
    """Lerp between colour stops (0.0 .. 1.0)."""
    if len(stops) == 1 or t <= 0.0:
        return stops[0]
    if t >= 1.0:
        return stops[-1]
    span = 1.0 / (len(stops) - 1)
    index = min(int(t / span), len(stops) - 2)
    local = (t - index * span) / span
    a, b = stops[index], stops[index + 1]
    return tuple(round(a[i] + (b[i] - a[i]) * local) for i in range(3))


def graffiti_glyph(char):
    """Return the white silhouette for one character, or None if it is absent."""
    key = char.upper()
    if key in _glyph_cache:
        return _glyph_cache[key]
    path = None
    if key.isalpha():
        path = os.path.join(GRAFFITI_FONT, key + "1.png")
    elif key.isdigit():
        path = os.path.join(GRAFFITI_FONT, key + ".png")
    glyph = None
    if path and os.path.exists(path):
        try:
            glyph = pygame.image.load(path).convert_alpha()
        except (OSError, pygame.error):
            glyph = None
    _glyph_cache[key] = glyph
    return glyph


def compose_wordmark(text, tracking=1, space_width=6):
    """Lay glyph silhouettes out on one baseline; None when nothing loads."""
    layout = []
    width = 0
    height = 0
    for char in text:
        if char == " ":
            layout.append(("gap", space_width))
            width += space_width + tracking
            continue
        glyph = graffiti_glyph(char)
        if glyph is None:
            layout.append(("gap", 5))
            width += 5 + tracking
            continue
        layout.append(("glyph", glyph))
        width += glyph.get_width() + tracking
        height = max(height, glyph.get_height())
    if height == 0:
        return None
    width = max(1, width - tracking)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    x = 0
    for kind, item in layout:
        if kind == "glyph":
            surface.blit(item, (x, height - item.get_height()))
        x += (item.get_width() if kind == "glyph" else item) + tracking
    return surface


def tint_gradient(surface, stops):
    """Recolour a white silhouette with a vertical gradient."""
    width, height = surface.get_size()
    gradient = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(height):
        t = 0.0 if height <= 1 else y / (height - 1)
        pygame.draw.line(gradient, _ramp(stops, t), (0, y), (width, y))
    out = surface.copy()
    out.blit(gradient, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def with_outline(surface, color, width=1):
    """Grow a matching silhouette behind the glyph, then restore it on top."""
    size = surface.get_size()
    silhouette = pygame.mask.from_surface(surface).to_surface(
        setcolor=tuple(color) + (255,), unsetcolor=(0, 0, 0, 0))
    out = pygame.Surface((size[0] + width * 2, size[1] + width * 2),
                         pygame.SRCALPHA)
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy > width * width + width:
                continue
            out.blit(silhouette, (width + dx, width + dy))
    out.blit(surface, (width, width))
    return out


def build_title_logo(text="PIXEL FIGHTER", scale=3):
    """Assemble the graffiti wordmark, or None when the pack is unavailable."""
    wordmark = compose_wordmark(text)
    if wordmark is None:
        return None
    wordmark = tint_gradient(wordmark, TITLE_LOGO_RAMP)
    wordmark = with_outline(wordmark, TITLE_LOGO_OUTLINE, 1)
    if scale != 1:
        wordmark = pygame.transform.scale(
            wordmark, (wordmark.get_width() * scale, wordmark.get_height() * scale))
    return wordmark


def title_logo():
    """Cached title wordmark; None falls back to plain text."""
    if not _title_logo_cache:
        logo = build_title_logo()
        if logo is None:
            return None
        _title_logo_cache.append(logo)
    return _title_logo_cache[0]


def draw_menu_overlay(screen: pygame.Surface, font: pygame.font.Font,
                      small: pygame.font.Font, state: GameState) -> None:
    """Draw the pause, settings, controls, tutorial, and confirmation pages."""
    screen.blit(translucent_rect((WIDTH, HEIGHT),
                                 (4, 6, 12, 174 if state.menu_screen != "title" else 205)),
                (0, 0))
    accent, text_color, muted = ui_palette(state)

    if state.menu_screen in ("pause", "title"):
        rect = pygame.Rect(220, 34, 520, 475)
        draw_ui_panel(screen, rect, state)
        logo = title_logo()
        if logo is not None:
            screen.blit(logo, logo.get_rect(center=(WIDTH // 2, 74)))
        else:
            image = outlined_text(font, "PIXEL FIGHTER", (246, 247, 252))
            screen.blit(image, image.get_rect(center=(WIDTH // 2, 78)))
        subtitle = "PAUSED" if state.menu_screen == "pause" else "ARCADE FIGHTER"
        image = outlined_text(small, subtitle, accent)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 110)))
        if state.menu_screen == "title":
            score = state.challenge.high_score
            line = "HIGH SCORE  %d" % score if score else "PRESS ENTER TO FIGHT"
            image = outlined_text(small, line,
                                  (246, 247, 252) if score else muted)
            screen.blit(image, image.get_rect(center=(WIDTH // 2, 142)))
        for index, (label, button_rect) in enumerate(menu_option_rects(state)):
            draw_ui_button(screen, button_rect, label, index == state.menu_index,
                           small, state)
        hint = "UP / DOWN  SELECT      ENTER  CONFIRM      ESC  RESUME" if state.menu_screen == "pause" else (
            f"ARROWS  SELECT      ENTER  CONFIRM      {control_key_name(state, 'quit')}  QUIT")
        image = outlined_text(small, hint, muted)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 478)))

    elif state.menu_screen == "settings":
        rect = pygame.Rect(48, 29, 864, 482)
        draw_ui_panel(screen, rect, state)
        screen.blit(outlined_text(font, "SETTINGS", accent), (74, 48))
        for index, category in enumerate(SETTINGS_CATEGORIES):
            tab = pygame.Rect(72 + index * 204, 103, 196, 34)
            draw_ui_button(screen, tab, category,
                           index == state.settings_category, small, state)
        rows = settings_rows(state)
        for index, row in enumerate(rows):
            row_rect = pygame.Rect(72, 151 + index * 48, 816, 40)
            draw_setting_row(screen, row_rect, row, state,
                             index == state.menu_index, small, small)
        if SETTINGS_CATEGORIES[state.settings_category] == "AUDIO":
            note = "Music, ambient audio, and separate UI audio are not part of this build."
            screen.blit(outlined_text(small, note, muted), (84, 339))
        elif SETTINGS_CATEGORIES[state.settings_category] == "DISPLAY":
            note = "The arena stays at native 960 x 540 for crisp pixel art; VSync is unavailable in this renderer."
            screen.blit(outlined_text(small, note, muted), (84, 339))
        hint = "UP / DOWN  SELECT     LEFT / RIGHT  ADJUST     PAGE UP / DOWN  CATEGORY     ESC  BACK"
        screen.blit(outlined_text(small, hint, muted), (76, 478))

    elif state.menu_screen == "controls":
        rect = pygame.Rect(44, 27, 872, 486)
        draw_ui_panel(screen, rect, state)
        screen.blit(outlined_text(font, "CONTROLS", accent), (72, 45))
        screen.blit(outlined_text(small, "MOUSE", (120, 230, 170)), (74, 82))
        x = 148
        for button_name, action in controls_mouse_rows():
            label = f"{button_name}  {CONTROL_NAMES.get(action, action)}"
            image = outlined_text(small, label, text_color)
            screen.blit(image, (x, 82))
            x += image.get_width() + 32
        screen.blit(outlined_text(small, "KEYBOARD   (select a row and press ENTER to rebind)",
                                  (120, 230, 170)), (74, 109))
        rows = controls_rows()
        for index, action in enumerate(rows):
            row_rect = control_row_rect(index)
            selected = index == state.menu_index and state.rebind_action is None
            if selected:
                pygame.draw.rect(screen, (38, 42, 56), row_rect)
                pygame.draw.rect(screen, accent, row_rect, 1)
            label = CONTROL_NAMES.get(action, action.replace("_", " ").title())
            screen.blit(outlined_text(small, label, text_color),
                        (row_rect.x + 8, row_rect.y + 4))
            value = "PRESS A KEY..." if state.rebind_action == action else control_key_name(state, action)
            image = outlined_text(small, value, accent)
            screen.blit(image, (row_rect.right - image.get_width() - 10, row_rect.y + 4))
        reset_index = len(rows)
        reset_rect = pygame.Rect(650, 455, 238, 34)
        draw_ui_button(screen, reset_rect, "RESET TO CURRENT DEFAULTS",
                       state.menu_index == reset_index, small, state)
        if state.rebind_action is not None:
            note = "PRESS A KEY...   ESC CANCELS"
            image = outlined_text(small, note, accent)
            screen.blit(image, image.get_rect(center=(330, 470)))
        else:
            note = "Mouse bindings remain LMB / RMB / MMB as configured."
            screen.blit(outlined_text(small, note, muted), (76, 462))

    elif state.menu_screen == "howto":
        rect = pygame.Rect(44, 27, 872, 486)
        draw_ui_panel(screen, rect, state)
        screen.blit(outlined_text(font, "HOW TO PLAY", accent), (72, 45))
        y = 82
        for heading, body_lines in tutorial_sections(state):
            screen.blit(outlined_text(small, heading, (120, 230, 170)), (76, y))
            y += 19
            for body in body_lines:
                for line in wrap_ui_text(small, body, 790):
                    screen.blit(outlined_text(small, line, text_color), (92, y))
                    y += 16
            y += 3
        draw_ui_button(screen, pygame.Rect(766, 460, 112, 32), "BACK", False, small, state)

    elif state.menu_screen == "fighters":
        rect = pygame.Rect(44, 27, 872, 486)
        draw_ui_panel(screen, rect, state)
        screen.blit(outlined_text(font, "SELECT FIGHTER", accent), (74, 45))
        for index, spec in enumerate(SELECTABLE_FIGHTERS):
            card = fighter_card_rect(index)
            selected = index == state.menu_index
            pygame.draw.rect(screen, (40, 45, 60) if selected else (21, 24, 33), card)
            pygame.draw.rect(screen, accent if selected else (56, 61, 76),
                             card, 2 if selected else 1)
            preview = fighter_preview(spec)
            if preview is not None:
                # Fit to the card in both directions: the cropped prototypes are
                # far smaller than the heroes, so only scaling down left them
                # sitting in the middle of the box at wildly uneven sizes.
                image = preview
                max_h, max_w = card.h - 66, card.w - 24
                ratio = min(max_h / image.get_height(), max_w / image.get_width())
                if ratio != 1.0:
                    image = pygame.transform.scale(
                        image, (max(1, round(image.get_width() * ratio)),
                                max(1, round(image.get_height() * ratio))))
                screen.blit(image, image.get_rect(
                    midbottom=(card.centerx, card.bottom - 34)))
            label = outlined_text(small, spec.label,
                                  accent if selected else text_color)
            screen.blit(label, label.get_rect(center=(card.centerx, card.bottom - 20)))
            if selected:
                badge = outlined_text(small, "SELECTED", (120, 230, 170))
                screen.blit(badge, badge.get_rect(center=(card.centerx, card.y + 14)))
        spec = SELECTABLE_FIGHTERS[state.menu_index % len(SELECTABLE_FIGHTERS)]
        info = "BODY %dx%d   ART %dPX   HP %d   SPEED %.1f   READY" % (
            spec.body_w, spec.body_h, spec.cell_w,
            spec.hp or PLAYER_MAX_HP, spec.speed or MOVE_SPEED)
        image = outlined_text(small, info, muted)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 402)))
        hint = "LEFT / RIGHT  SELECT      ENTER  CONFIRM      ESC  BACK"
        image = outlined_text(small, hint, muted)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 478)))

    elif state.menu_screen == "confirm":
        rect = pygame.Rect(220, 137, 520, 270)
        draw_ui_panel(screen, rect, state)
        action = state.dialog_action
        title, description, affirmative = {
            "restart": ("Restart this run?", "All current run progress will be lost.", "RESTART"),
            "quit_menu": ("Quit this run?", "Current run progress will be lost.", "QUIT"),
            "quit_game": ("Quit Pixel Fighter?", "The game will close.", "QUIT"),
            "reset_binds": ("Restore the current default controls?", "Your configured bindings will be replaced.", "RESET"),
        }.get(action, ("Confirm?", "", "YES"))
        image = outlined_text(font, title, accent)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 202)))
        image = outlined_text(small, description, text_color)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 253)))
        draw_ui_button(screen, pygame.Rect(306, 344, 166, 39), "CANCEL",
                       state.menu_index == 0, small, state)
        draw_ui_button(screen, pygame.Rect(488, 344, 166, 39), affirmative,
                       state.menu_index == 1, small, state)
        hint = "LEFT / RIGHT  SELECT      ENTER  CONFIRM      ESC  CANCEL"
        image = outlined_text(small, hint, muted)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 392)))

    if state.notice and state.notice_timer > 0:
        image = outlined_text(small, state.notice, accent)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, HEIGHT - 20)))


def draw(screen: pygame.Surface, clock: pygame.time.Clock, player: Player,
         dummy: Dummy, texts: list, props: StageProps, state: GameState,
         font: pygame.font.Font, small: pygame.font.Font,
         sprite_msg: str) -> None:
    """Draw the stage, fighters, HUD, and optional overlays."""
    draw_stage(screen, state.background)
    props.draw_background(screen)
    pygame.draw.ellipse(screen, (0, 0, 0), (player.x - 46, GROUND_Y + 6, 92, 16))
    pygame.draw.ellipse(screen, (0, 0, 0), (dummy.x - 46, GROUND_Y + 6, 92, 16))
    if dummy.alive or dummy.state == "death":
        dummy.draw(screen, hit_flash=(state.settings.values["hit_flash"]
                                      and state.settings.values["combat_effects"]
                                      and not state.settings.values["reduced_flash"]))
    player.draw(screen, hit_flash=(state.settings.values["hit_flash"]
                                   and state.settings.values["combat_effects"]
                                   and not state.settings.values["reduced_flash"]))
    props.draw(screen)
    screen.blit(translucent_rect((WIDTH - 24, HUD_TOP_H), (8, 10, 17, 198)),
                (12, 6))
    pygame.draw.rect(screen, (76, 91, 128), (12, 6, WIDTH - 24, HUD_TOP_H), 1)
    draw_name_tag(screen, small, int(player.x), "YOU", PLAYER_TAG)
    draw_name_tag(screen, small, int(dummy.x), dummy.label.upper(), DUMMY_TAG)

    if dummy.alive and state.settings.values["enemy_health_bar"]:
        dummy.draw_health(screen, small)
    player.draw_health(screen, small)
    if player.combo > 1:
        combo_text = "%d HITS   %d DMG" % (player.combo, player.combo_damage)
        img = outlined_text(font, combo_text, (255, 214, 120))
        screen.blit(img, (player.x - img.get_width() / 2, player.y - 300))
    if state.settings.values["combat_effects"]:
        for floating in texts:
            is_number = floating.text.startswith("-") and floating.text[1:].isdigit()
            if state.settings.values["damage_numbers"] or not is_number:
                floating.draw(screen, font)

    facing = "R" if player.facing_right else "L"
    frame_count = len(player.anims[player.state])
    screen.blit(translucent_rect((WIDTH - 24, HUD_BOTTOM_H), (8, 10, 17, 198)),
                (12, HUD_BOTTOM_Y))
    pygame.draw.rect(screen, (76, 91, 128),
                     (12, HUD_BOTTOM_Y, WIDTH - 24, HUD_BOTTOM_H), 1)
    arcade_line = (
        f"RIVAL  {dummy.label.upper()}     "
        f"WINS  {state.challenge.rounds_won}/{state.challenge.rounds_total}     "
        f"LIVES  {state.challenge.lives}     "
        f"SCORE  {state.challenge.score:06d}     BEST  {state.challenge.high_score:06d}"
    )
    screen.blit(outlined_text(small, arcade_line, (245, 245, 252)),
                (24, HUD_BOTTOM_Y + 6))
    if state.challenge.last_award and not state.challenge.finished:
        award = outlined_text(small, f"LAST WIN +{state.challenge.last_award}",
                              (255, 214, 120))
        screen.blit(award, (WIDTH - 36 - award.get_width(), HUD_BOTTOM_Y + 6))

    if state.show_log and LOG is not None:
        rows = len(LOG.lines)
        panel = translucent_rect((440, 14 + 15 * rows), (10, 10, 16, 175))
        screen.blit(panel, (WIDTH - 452, HEIGHT - 60 - panel.get_height()))
        for i, line in enumerate(LOG.lines):
            screen.blit(outlined_text(small, line, (150, 230, 160)),
                        (WIDTH - 446, HEIGHT - 56 - 15 * rows + i * 15))

    # ESC only ever means "step back", so name the one action it performs here.
    if state.menu_screen == "title":
        tail = "%s QUIT" % control_key_name(state, "quit")
    elif state.menu_screen == "pause":
        tail = "%s RESUME" % control_key_name(state, "pause")
    else:
        tail = "%s PAUSE" % control_key_name(state, "pause")
    footer = (f"{tail}     "
              f"{control_key_name(state, 'debug')} DEBUG     "
              f"{control_key_name(state, 'log')} EVENT LOG")
    screen.blit(outlined_text(small, footer, (190, 195, 210)), (12, HEIGHT - 23))
    if state.settings.values["show_fps"] and not state.show_debug:
        fps = outlined_text(small, f"{clock.get_fps():.0f} FPS", (190, 195, 210))
        screen.blit(fps, (WIDTH - fps.get_width() - 14, 66))

    if state.show_debug:
        hitbox = player.hitbox()
        debug = [
            f"FPS {clock.get_fps():5.1f}",
            f"pos  {player.x:6.1f},{player.y:6.1f}",
            f"vel  {player.vx:5.1f},{player.vy:5.2f}",
            f"anim {player.state} {player.anim_index}/{frame_count - 1} t={player.state_time}",
            f"ground={player.on_ground} lock={player.lock[player.state]} facing={facing}",
            f"hitbox={hitbox[0] if hitbox else 'none'}",
        ]
        for i, line in enumerate(debug):
            screen.blit(outlined_text(small, line, (120, 255, 140), cache=False),
                        (WIDTH - 270, 66 + i * 18))
        if sprite_msg != "CraftPix sprites LOADED" or SPARSE_WARNINGS:
            note = sprite_msg if sprite_msg != "CraftPix sprites LOADED" else "SPARSE " + ", ".join(SPARSE_WARNINGS[:2])
            screen.blit(outlined_text(small, note, (255, 190, 130)), (12, 66))

    if state.challenge.finished:
        draw_arcade_result(screen, font, state.challenge, state)
    if state.menu_screen != "game":
        draw_menu_overlay(screen, font, small, state)


def draw_arcade_result(screen: pygame.Surface, font: pygame.font.Font,
                       challenge: ArcadeChallenge, state: GameState) -> None:
    """Show the final arcade result and its replay prompt."""
    screen.blit(translucent_rect((WIDTH, HEIGHT), (5, 7, 14, 205)), (0, 0))
    panel = pygame.Rect(170, 145, 620, 250)
    pygame.draw.rect(screen, (20, 24, 38), panel)
    pygame.draw.rect(screen, (120, 145, 220), panel, 3)
    title = outlined_text(font, challenge.result, (255, 220, 125))
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 190)))
    lines = (
        f"WINS  {challenge.rounds_won}/{challenge.rounds_total}     LIVES LEFT  {challenge.lives}",
        f"SCORE  {challenge.score:06d}     BEST  {challenge.high_score:06d}",
        "Click anywhere to start a new run",
        f"{control_key_name(state, 'quit')} to quit",
    )
    for index, line in enumerate(lines):
        color = (235, 235, 245) if index < 2 else (170, 185, 215)
        image = outlined_text(font, line, color)
        screen.blit(image, image.get_rect(center=(WIDTH // 2, 235 + index * 35)))


def main() -> None:
    """Initialize pygame and run the fixed 60-tick game loop."""
    pygame.init()
    load_sounds()
    pygame.display.set_caption("PIXEL FIGHTER")
    settings = SettingsManager()
    applied_fullscreen = settings.values["fullscreen"]
    screen = pygame.display.set_mode((WIDTH, HEIGHT),
                                     pygame.FULLSCREEN if applied_fullscreen else 0)
    clock = pygame.time.Clock()
    font_scale = settings.values["text_scale"]
    font = pygame.font.SysFont("consolas", round(18 * font_scale))
    small = pygame.font.SysFont("consolas", round(14 * font_scale))
    canvas = pygame.Surface((WIDTH, HEIGHT))

    global LOG
    LOG = GameLog(os.path.join(BASE_DIR, "logs", "pixel_fighter.log"))
    log("-" * 46)
    log("SESSION START  window=%dx%d" % (WIDTH, HEIGHT))

    scenes = available_scenes()
    default_scene = os.path.join(BACKGROUNDS, "Ocean_4")
    default_scene_index = scenes.index(default_scene) if default_scene in scenes else 0
    state = GameState(scenes=scenes, scene_index=default_scene_index,
                      default_scene_index=default_scene_index, settings=settings)
    state.show_debug = settings.values["debug_overlay"]
    state.challenge.high_score = load_high_score()
    state.menu_screen = "title"
    state.menu_origin = "title"
    state.menu_index = 0
    log("boot menu: TITLE")
    stage_key = pygame.key.name(settings.keybinds["stage"]).upper()
    log("%d stages available (%s cycles them)" % (len(scenes), stage_key))
    if scenes:
        state.background = Background(scenes[state.scene_index])
        state.background_cache[scenes[state.scene_index]] = state.background
        log("stage: %s (%d layers)" % (state.background.name, len(state.background.layers)))
    else:
        log("stage: procedural fallback (no assets/backgrounds)")

    props = StageProps()
    if props.items:
        log("stage props loaded: %d" % len(props.items))
    player = Player(WIDTH // 2, GROUND_Y)
    dummy = Dummy(660, GROUND_Y)
    dummy.set_rival(*ARCADE_RIVALS[0])
    texts: list = []
    sprite_msg = "CraftPix sprites LOADED"
    if player.missing:
        sprite_msg = "MISSING SHEETS: " + ", ".join(player.missing)

    while state.running:
        handle_events(pygame.event.get(), player, dummy, texts, state)
        update(player, dummy, texts, state)
        if state.menu_screen != "game" and state.notice_timer > 0:
            state.notice_timer -= 1
        if settings.values["text_scale"] != font_scale:
            font_scale = settings.values["text_scale"]
            font = pygame.font.SysFont("consolas", round(18 * font_scale))
            small = pygame.font.SysFont("consolas", round(14 * font_scale))
            _text_cache.clear()
        if settings.values["fullscreen"] != applied_fullscreen:
            applied_fullscreen = settings.values["fullscreen"]
            screen = pygame.display.set_mode(
                (WIDTH, HEIGHT), pygame.FULLSCREEN if applied_fullscreen else 0)
        draw(canvas, clock, player, dummy, texts, props, state, font, small, sprite_msg)
        screen.fill((0, 0, 0))
        offset = (0, 0)
        if (state.menu_screen == "game" and state.settings.values["screen_shake"]
                and not state.settings.values["reduced_motion"] and state.shake_frames > 0):
            intensity = state.settings.values["shake_intensity"]
            direction = -1 if state.shake_frames % 2 else 1
            amplitude = max(1, round(intensity * 2))
            offset = (direction * amplitude, -direction * (amplitude // 2))
        screen.blit(canvas, offset)
        pygame.display.flip()
        clock.tick(60)

    log("SESSION END")
    if LOG is not None:
        LOG.close()
    pygame.quit()


if __name__ == "__main__":
    main()
