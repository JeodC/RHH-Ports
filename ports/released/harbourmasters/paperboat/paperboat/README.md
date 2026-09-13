## Installation
You need to provide your own rom. The supported roms are:

| Version | SHA-1 |
|---|---|
| USA | 3837F44CDA784B466C9A2D99DF70D77C322B97A0 |

You can verify you have dumped a supported copy of the game by using the SHA-1 File Checksum Online at https://www.romhacking.net/hash/.

Legally obtain your rom and place it in `ports/paperboat/baseroms`, then start the port. It must be in **big-endian `.z64` format** — `.n64` and `.v64` are not detected. Use https://hack64.net/tools/swapper.php to convert if needed. Paperboat will offer to process any roms it finds. If none are found you will instead be prompted to pick your rom with the built-in file browser. Either way, Torch generates a `pm64.o2r` in place. This takes a few minutes, on the first boot only.

Logs are recorded automatically as `ports/paperboat/log.txt`. Please provide a log if you report an issue. HarbourMasters is not affiliated with PortMaster or RHH-Ports and this distribution is not officially supported by them. *Please report an issue to the RHH-Ports repository before going to HarbourMasters!*

## Menu Navigation
Paperboat has built-in controller navigation for the imgui menu. Press `SELECT` to open the menu and use the `D-PAD` to choose a submenu, then press `A` to switch focus to it. Press `B` to back out of a submenu.

## Credits
- Paper Mario 64 made by Nintendo
- Source port by HarbourMasters
- Linux SBC build by Jeod

Third-party licenses for the components bundled with this port are in `licenses/`.
