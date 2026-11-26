# AM2R - AM2ARM
This port runs [AM2ARM](https://github.com/PatchDev-AM2ARM/AM2ARM), PatchDev's 64-bit build of AM2R Community Updates 1.5.5. It includes PatchDev's game build, but none of AM2R's files. You provide AM2R 1.1, and the port builds the game from it.

## Installation
Place your original Windows AM2R 1.1 zip in `ports/am2r/assets`. Any filename works. Launch the port with an internet connection and 650 MB free. The port builds AM2ARM 1.6.2 from your zip, and downloads the HQ music (about 245 MB) from the [AM2R Community Autopatcher](https://github.com/AM2R-Community-Developers/AM2R-Autopatcher-Windows).

Keep the zip in `assets`, since updates are built from it.

## Dual screen
On devices with two screens, gameplay is on one and the map on the other. `Options > Display > Dual Screen` turns this on or off, and is greyed out without a second screen. The card can move between devices.

## Updates
New AM2ARM versions come with updates to this port.

## Manual / offline patching
Without an internet connection, the port can take the music from the Autopatcher's zip instead.

1. Download the [AM2R Community Autopatcher zip](https://github.com/AM2R-Community-Developers/AM2R-Autopatcher-Windows/archive/refs/heads/master.zip).
2. Place it in `ports/am2r/assets` with your AM2R 1.1 zip. Don't extract it.
3. Launch the port. You can delete the Autopatcher zip afterward.

## Notes
Folder sync from AM2ARM's Android version is not available. Saves are in `ports/am2r/saves`, and `Options > Data` backs them up to `saves/backup`.

Nano, in Display Options, is on by default on RK3326 devices and the RG DS.

## Runtimes

This port requires [gmloadernext.squashfs](https://github.com/JeodC/RHH-Ports/raw/main/runtimes/gmloadernext.squashfs) placed in the `PortMaster/libs/` folder. [Pharos](https://github.com/JeodC/RHH-Ports/releases/download/ports-latest/pharos.zip) fetches it automatically when installing the port.

## Thanks
DoctorM64 and the AM2R team -- The game  
AM2R Community Developers -- Community Updates and the HQ music  
PatchDev -- AM2ARM  
JohnnyOnFlame -- GMLoader-Next and original AM2R port  
Jeod -- GMLoader-Next enhancements and dual-screen plugin
