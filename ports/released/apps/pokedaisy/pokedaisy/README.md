# PokéDaisy
This port runs [PokéDaisy](https://github.com/lidor30/pokedaisy), a Game Boy, Game Boy Color, Game Boy Advance and DS player with a live companion for Pokémon games and romhacks. It does not distribute PokéDaisy or any games. The port downloads PokéDaisy from upstream, and you provide the games.

## Installation
Launch the port with an internet connection and 100 MB free. The download is about 15 MB.

## Adding games
The game list shows the Pokémon games in your firmware's Game Boy, Game Boy Color, Game Boy Advance and DS folders, romhack folders included, and everything in `ports/pokedaisy/roms`. Games can be `.gb`, `.gbc`, `.gba`, `.nds` or `.zip`.

Saves are in `ports/pokedaisy/saves`. To use a save from another emulator, copy it there with the game's name and a `.sav` extension. `SETTINGS > SHARED SAVES` uses RetroArch's saves instead, for games in your firmware's folders.

## Controls
| Button | Action |
|--|--|
| Menu / Guide / F | Menu |
| X | Companion (L2 in DS games) |
| L3 | Quick menu |
| R2 | Switch screens in DS games |
| Select + R2 | Fast forward |
| Select + L2 | Rewind, when `REWIND` is on |
| Start + Select | Quit |

These can be changed in the companion's `SETTINGS`. If A and B feel backwards, set `A/B BUTTONS` to `SWAPPED`. [PokéDaisy's manual](https://pokedaisy.com/docs/) covers everything else.

## Dual screen
On ROCKNIX devices with two screens, the game is on one and the companion on the other. DS games use both. `SETTINGS > SECOND SCREEN` swaps the screens or turns this off.

## Updates
The port tracks upstream's GitHub releases. When a newer one is detected on launch, the patcher runs again and installs it. Your games, saves and settings stay.

The patcher dialog asks whether to keep the update check enabled. Choose **No** to freeze the port at its current upstream version. To re-enable later, delete `pokedaisy/.update_check`.

If the device is offline at launch, the update check is skipped silently and PokéDaisy runs as-is.

## Manual / offline install
If your device has no internet connection, download `pokedaisy-portmaster-aarch64.zip` from the [PokéDaisy releases](https://github.com/lidor30/pokedaisy/releases) on a PC and place it in `ports/pokedaisy`. Don't extract it. Launch the port, then delete the zip.

To update an installed port this way, place the newer zip and delete `pokedaisy/.patch_version`. The port updates to the newest release the next time the device has internet access, unless you've disabled update checks.

## Thanks
Based on PokeDaisy by Lidor Itzhari - https://github.com/lidor30/pokedaisy

Lidor Itzhari and contributors -- PokéDaisy  
MagnominusGit -- armGBA  
mGBA team -- mGBA  
beebono, thwonp -- DSperate and its libretro core  
Jeod -- Dual-screen support and Linux port
