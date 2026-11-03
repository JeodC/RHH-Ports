# Descent 3

## Notes
This fork of Descent 3 is tailored to retro handhelds. It renders through OpenGL ES 3.0, with no GL translation layer. Descent 3 uses SDL3, so the port bundles bmdhacks' [SDL3 shim](https://github.com/bmdhacks/SDL/tree/sdl2-backend), which runs it on your device's SDL2. The binary is built automatically from the [fork repository](https://github.com/JeodC/Descent3) on Ubuntu 20.04 (GLIBC 2.31).

The following patches have been applied to this release:

- Render natively through OpenGL ES 3.0 instead of desktop OpenGL
- Fit the game to any screen, with a choice of aspect ratio, resolution, pixel-perfect scaling and stretching
- Fill the screen with menus, loading screens and movies, or keep them 4:3
- Keep the HUD's shape on wide and square screens instead of stretching it
- Hide the mouse cursor (an option in Settings)
- Read the gamepad natively, with handheld default controls and gamepad menu navigation
- Replace the options and controller screens with a gamepad-friendly menu on SELECT
- Name new saves after the current level
- Offer every level, secret levels included, once a mission is finished
- Show levels reached after cheating in New Game, grayed out
- Put core campaign missions at the top of the mission list
- Play one hit sound at a time per ship, so beams, fast guns and scraping along walls don't stack at full volume
- Fix Level 13's engine core objective, which never completed
- Fix failing a mission counting as finishing its level
- Fix VSync, which the setting never turned on

## Installation
Unzip to ports folder e.g. `/roms/ports/`. Purchase the full game from GOG or Steam, or use CD game data patched to v1.4. Then, add the following files to `descent3/gamedata`:

Filelist for full versions:
```
├── descent3/gamedata  
│   ├── missions/  
│   │ └── any mission files (`.mn3`) and `d3voice1.hog` and `d3voice2.hog` if they came with your game  
│   ├── movies/  
│   │ └── any movie files (`.mve`) that came with your game. If you have the Linux Steam version, use steamcmd to get the windows movie files  
│   └── d3.hog  
│   └── extra.hog (this may be `merc.hog` depending on the platform you used to purchase the game)  
│   └── extra1.hog  
│   └── extra13.hog  
│   └── ppics.hog
```

## Configuration
Tap SELECT to open the menu anywhere in the game, and tap it again to close it.

- **Settings**: every option, applied as you change it, plus the game view's aspect ratio and resolution (applied when the menu closes) and whether menus and movies fill the screen.
- **Controls**: A rebinds a control, X clears it, and an axis can be inverted from its row.
- **Mission**, during a level: objectives, the TelCom's briefing and automap, cargo, ship's log, HUD messages, Guide-Bot orders, cockpit windows, saving and loading, the netgame's on-screen menu and scores, and cheats.
- **Pilot**, outside a level: difficulty, and your multiplayer ship, logo and audio taunts.

During a level, Restart Level and Quit to Menu sit beside Close.

The launchscript selects the included pilot file by default, but you can modify the name by opening the file in a text editor.

Settings are kept in `descent3/gamedata/descent3.cfg.json`, beside your pilots and saved games. The game writes it when the menu closes and when it exits, and updating the port leaves it alone.

## Multiplayer
You can play multiplayer via PXO. Go to https://pxo.nottheeye.com and register an account, then validate your email. Then, on the account details page, copy your game credentials into `TrackerLogin` and `TrackerPassword` in `descent3/gamedata/descent3.cfg.json` (run the game once first to create it). When you start Descent 3 and try to connect to PXO, your login details will be filled automatically and you can just press `Start` to log in. Now you can host or join games!

You can also play multiplayer via Direct TCP-IP. Put the IP address to connect to in `DirectIP` in the same file. Then, load your game, choose the Direct TCP-IP multiplayer protocol, and it will be prefilled for you.

## Default Gameplay Controls
In menus, the `D-PAD` or left stick moves, A accepts, B goes back, L1/R1 switch fields and L2/R2 page through lists.

| Button | Action |
|--|--| 
|A|Rear View|
|B|Use Inventory Item|
|X|Fire Flare|
|Y|Use Countermeasure|
|L1|Cycle Primary Weapon (previous player when observing)|
|R1|Cycle Secondary Weapon (next player when observing)|
|L2|Fire Secondary Weapon|
|R2|Fire Primary Weapon|
|L3|Afterburner|
|R3|Toggle Headlight|
|D-PAD UP|Slide Up|
|D-PAD DOWN|Slide Down|
|D-PAD LEFT|Previous Inventory Item|
|D-PAD RIGHT|Next Inventory Item|
|LEFT ANALOG|Accelerate/Reverse & Slide Left/Right|
|RIGHT ANALOG|Look Around (pitch inverted)|
|START|Pause / Accept (in menus)|
|SELECT|Menu|

Drop Marker has no button by default; bind one in Controls if you want it.

## Thanks
fpasteau  
InsanityBringer  
bmdhacks  
Descent Developers Team  
Outrage Entertainment  
