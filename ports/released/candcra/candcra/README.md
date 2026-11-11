# Command & Conquer: Red Alert (iPad)

## Installation
Unzip to ports folder e.g. `/roms/ports/`. You need your own copy as an `.ipa`. Copy it into `candcra/gamedata`. An `.app` folder extracted from one works too.

The supported and tested version is **Command & Conquer Red Alert for iPad 1.8.20**, bundle ID `com.ea.candcra.ipad.inc`. This is the iPad-only release; the iPhone release is a separate app and isn't supported. The app must be decrypted. After a launch, `log.txt` shows the version and bundle ID touchHLE found under "App bundle info".

## Notes
This port runs EA's original iPad app through [touchHLE](https://touchhle.org/), a high-level emulator for old iPhone OS apps. touchHLE runs the app's ARM code and stands in for the iOS frameworks it calls, so nothing from the game is rebuilt or modified. touchHLE is built from the [upstream repository](https://github.com/touchHLE/touchHLE) on Ubuntu 20.04 (GLIBC 2.31) with handheld patches; see [BUILDING.md](https://github.com/JeodC/RHH-Ports/blob/main/buildtools/touchhle/BUILDING.md).

The following patches have been applied to touchHLE:

- Tell the game it has rotated to landscape at launch, as iOS does, which fixes clipped panels and text
- Stretch the picture to fill the screen (`--stretch`)
- Ask for an OpenGL ES window when using native OpenGL ES 1.1, for devices without desktop OpenGL
- Move the cursor with a stick or the D-pad like a mouse, and tap with any button
- Scroll with the other stick, or by pushing the cursor against an edge
- Zoom by pinching with the triggers
- Drag-select with a button that taps the Drag-Select icon and then drags
- Draw the cursor as a red arrow pointer
- Start on devices with less than 4 GB of memory

Campaign and Skirmish are playable. Multiplayer is not: its Wi-Fi and Bluetooth games use GameKit's peer-to-peer sessions, which touchHLE doesn't have.

touchHLE runs the whole game on one CPU core, so single-core speed decides how well it plays. On an AYN Thor it holds the game's full 60 FPS. RK3326 devices such as the RG351P are too slow to play it. Throttling the Thor's small cores to stand in for an RK3566 gave about 25 FPS, with long mission loads and crackling audio.

## Default Gameplay Controls

| Button | Action |
|--|--|
| Left stick, D-pad | Move the cursor |
| A | Touch at the cursor: tap, hold still for a tooltip, or hold and move to drag |
| X | Tap to select everything on screen. Hold and move the cursor to draw a selection box. |
| Right stick | Scroll the map. Pushing the cursor against an edge also scrolls. |
| R2 / L2 | Zoom in / out |
| Y | Add to squad |
| L1 / R1 / B | Squad 1 / 2 / 3. Press twice to center the camera on it. |
| Start | In-game menu |
| Select + Start | Quit |

The game was made for a touchscreen. The cursor stands in for your finger, and A touches the screen with it: press A to tap, twice to double-tap, or hold it and move to drag, for example to place a building or pull a unit out of the build queue. Hold A still on an icon to see its tooltip.

- **Select:** tap a unit, or double-tap one to select every unit of that type on screen.
- **Move and attack:** with units selected, tap the ground to move there or tap an enemy to attack it. Retreat sends the selected units back to base.
- **Squads:** select units, then press Y to add them to a squad.
- **Build and train:** the Structures, Infantry and Mechanized icons open their lists. Tap an item to build or train it, and tap it again to queue more. Drag an item out of the queue to cancel it. New structures must go next to existing ones, and selling a building refunds half its cost.
- **Garrison:** select infantry and tap a building to move them in. Select the building and tap Evacuate to bring them out.
- **Capture:** engineers can take bonus buildings. A Radar Station reveals the whole map.

To change the sensitivity, edit `candcra/controls.json` and restart the game. Removing a setting uses the default.

| Setting | Default | Meaning |
|--|--|--|
| `cursor_speed` | 0.8 | Screen widths per second the cursor moves with the stick pushed all the way |
| `scroll_speed` | 1.2 | How fast the right stick scrolls the map |
| `edge_scroll_speed` | 1.0 | How fast pushing the cursor against an edge scrolls |
| `zoom_speed` | 0.6 | How fast the triggers zoom |
| `deadzone` | 0.1 | How far a stick moves before it counts, from 0 to 1 |

The button mapping is set in `candcra/touchHLE_options.txt`, and `touchHLE --help` lists every option. For example, `--button-to-touch=` maps a button to a spot on screen.

## Saves
touchHLE gives the game the same private folder it had on an iPad, inside the port folder: `candcra/touchHLE_sandbox/com.ea.candcra.ipad.inc/`. The game keeps its settings in `Documents/options.ini` and its progress in other files in `Documents/`. To back up or move your saves, copy the `touchHLE_sandbox` folder. Updating the port doesn't touch it.

## Thanks
hikari_no_yume and the touchHLE contributors for touchHLE. touchHLE's source is under the Mozilla Public License 2.0 and its binaries under the GNU GPL v3 or later; see `licenses/`.
