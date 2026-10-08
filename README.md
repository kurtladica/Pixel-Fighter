# Pixel Fighter

A single-file 2D versus fighter built with **pygame-ce** — no game engine. Combos with
input buffering, a super meter and special moves, an arcade run against an AI rival that
gets tougher every round, twelve stages, and full rebindable controls.

```
Play.bat          # double-click to play
python main.py    # or run it directly
```

## Requirements

- **Python 3.10+** (verified on 3.14)
- **pygame-ce** — note this is *not* plain `pygame`, which does not build on Python 3.14

```bat
pip install -r requirements.txt
```

`pyinstaller` in `requirements.txt` is only needed if you want to build a standalone
`.exe`; the game itself does not require it.

## How to run

| | |
|---|---|
| **Windows** | Double-click `Play.bat` |
| **Any platform** | `python main.py` |

The window opens at 960×540 and boots straight to the title screen. `Play.bat` changes
into the game folder first so `main.py` can find `assets/`.

## Controls

Everything is **mouse + left-hand keys** by design, so your right hand never leaves the
mouse. Every binding can be changed in **Settings → Controls**, and the live bindings are
also shown on that screen.

### Movement

| Key | Action |
|---|---|
| `A` / `D` | Move left / right (hold to sprint) |
| `W` | Jump — press again for a double jump, hold to glide |
| `S` | Dodge roll |
| `Q` *(hold)* | Block / guard |
| `Ctrl` *(hold)* | **Crouch guard** — same 25% damage behind a much smaller hitbox |

### Attacking

| Input | Action |
|---|---|
| Left click | Punch 1 |
| Right click | Punch 2 |
| Middle click | Hurt animation (animation test) |
| `E` | Kick (in mid-air: jump kick) |
| `R` | Fire kick |
| `F` | Power strike |
| `T` | Ground slam |
| `G` | Super strike — **finisher**, does double damage on a 3+ hit combo |
| `C` | Ice strike |
| `V` | Slide attack |
| `Z` | Counter / parry |
| `X` | Riposte |
| `B` | Cast spell |
| `Y` | Throw |
| `U` | Ability |
| `1` | Charge attack |
| `2` / `3` | Impact 1 / Impact 2 |
| `H` | **Special** — costs 50 meter |

### Menus & dev

| Key | Action |
|---|---|
| `Esc` | Pause menu (quit from the title screen) |
| `F1` | Debug overlay |
| `F2` | Event log |
| `F3` | Next stage |

## How it plays

- **Arcade run** — five rounds against five rivals, each with its own personality:
  Crimson Guard (balanced), Azure Duelist (rushdown), Violet Warden (evasive),
  Jade Phantom (punisher), Amber Shade (heavy). Every round won raises the rival's tier,
  so cooldowns shorten, reactions sharpen, and HP and damage climb.
- **Super meter** — fills as you deal damage, take damage, land a combo, or guard a hit.
  Press `H` to spend 50 of it on a special. The meter carries across rounds within a run
  and empties when you get knocked out.
- **Defence** — blocking cuts incoming damage to 25%, a well-timed parry turns the hit
  into a free riposte, the dodge roll repositions you, and holding `Ctrl` crouches the
  guard so the hitbox drops to about 60% height and high swings pass overhead.
- **Roster** — six playable fighters on 12 stages (cycle with `F3`): three builds of the
  prototype, then Blade, Ember and Frost. Three rival monster packs appear on the rival
  side. The prototype builds share art but not stats:

  | Fighter | HP | Speed | Palette |
  |---|---|---|---|
  | Prototype | 100 | 5.0 | stock blue |
  | Proto Mk II | 85 | 6.5 | mint — fastest, fragilest |
  | Proto Mk III | 130 | 4.0 | amber — tanky, slow |
- **High score** — saved between sessions.

## Settings

**Settings** covers Audio, Display, Gameplay (including rival difficulty: Easy / Normal /
Hard) and Accessibility. Control rebinds and all options persist to
`logs/game_settings.json`, which is created on first run.

## Project layout

```
main.py           the entire game (engine, AI, HUD, menus)
Play.bat          Windows launcher
requirements.txt  pygame-ce (+ pyinstaller for packaging)
assets/           sprites, backgrounds, sounds, UI, fonts
logs/             created at runtime: settings, high score, event log
```

Raw asset packs, scratch files and `__pycache__` are git-ignored (`_source/`,
the CraftPix cloud pack, `logs/`, `_kenney_contact_sheet.png`).

## Credits & licenses

Full breakdown in [`assets/licenses/CREDITS.txt`](assets/licenses/CREDITS.txt).

- **Art** — free packs from [CraftPix.net](https://craftpix.net/file-licenses/)
  (royalty-free for unlimited projects)
- **UI bars, plates, buttons** — [Kenney](https://kenney.nl) *UI Pack: Sci-fi*, **CC0 1.0**
- **Title wordmark** — *Free Graffiti Constructor Pixel Art* (CraftPix), font "Future Millennium"
