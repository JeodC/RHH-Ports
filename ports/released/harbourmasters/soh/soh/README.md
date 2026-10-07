## Information
Ship of Harkinian was built from GitHub Actions at the [RHH-Ports Autobuilder](https://github.com/JeodC/RHH-Ports).

## Compatibility
TrimUI devices have a render bug where the PVR driver doesn't support NPOT (non-power-of-two) textures and therefore won't render them. The game is still playable, but several textures will be invisible. See a workaround by [modifying soh.o2r](https://github.com/Kenix3/libultraship/pull/1096)

## Installation
You need to provide your own roms. See the [Shipwright](https://github.com/HarbourMasters/Shipwright/blob/develop/docs/supportedHashes.json) repository for a list of supported rom hashes. Gather your roms and put them in the `ports/soh/baseroms` folder. 

Start the port, and on first run, your .o2r files will be generated from the roms you provide. Texture pack files and mods can be added to the `ports/soh/mods` folder. 

Logs are recorded automatically as `ports/soh/log.txt`. Please provide a log if you report an issue. HarbourMasters is not affiliated with PortMaster or RHH-Ports and this distribution is not officially supported by them. *Please report an issue to the RHH-Ports repository before going to HarbourMasters!*

## Menu Navigation
Ship of Harkinian has built-in controller navigation for the imgui menu. Press `SELECT` to open the menu and use the `D-PAD` to choose a submenu, then press `A` to switch focus to it. Press `B` to back out of a submenu.

## Default Gameplay Controls
The port uses SDL controller mapping and controls can be remapped from the imgui menu. For devices without a right analog stick, the gptk file allows for the `HOTKEY + ABXY` button combo to use the C-Buttons.

## Mods
You can find a ton of mods at [GameBanana](https://gamebanana.com/mods/games/16121?_aFilters%5BGeneric_Name%5D=contains%2C3ds&_sSort=Generic_MostDownloaded).  

## Anchor
This version of Ship of Harkinian includes Anchor support. You can modify your name and room id in the launchscript, and then connect to Anchor from the imgui menu. In the global public room, you can see other players as you play through independent save files. If you create your own room, you can play cooperatively.

## Thanks
Nintendo for the game  
HarbourMasters for the native pc port  
AkerHasReawakened for the cover art  
IanSantos for the ghibli skybox mod  