# Jeod's Retro Handheld Ports
This repository is a large collection of ports I authored. They all require the [PortMaster Framework](https://portmaster.games/installation.html).

Whether you're new to retro handhelds, a developer who came across this repository and noticed their game has a port, or a developer seeking information, I can't recommend enough this video by WULFF DEN which encapsulates the whole idea pretty well.

<div align="center">
  <table>
    <tr>
      <td align="center">
        <p align="center">Playing Steam Games on your Retro Handheld</p>  
        <a href="https://www.youtube.com/watch?v=I4Utn3N_dZo">
          <img src="https://img.youtube.com/vi/I4Utn3N_dZo/0.jpg" alt="Playing Steam Games on your Retro Handheld by WULFF DEN" width="400"/>
        </a>
      </td>
    </tr>
  </table>
</div>

## Port Installation
You can use the [https://jeodc.github.io/RHH-Ports](https://jeodc.github.io/RHH-Ports/) website frontend to download specific ports, or use the [Pharos App](https://github.com/JeodC/RHH-Ports/releases/download/ports-latest/pharos.zip) on your retro handheld.

If you use the website frontend, clicking the blue Download button on a port will download a zip archive of the port, which you can then copy to `PortMaster/autoinstall` folder.

If you use Pharos, autoinstall is performed for you.

You should use the **BETA** branch of the PortMaster application to ensure you have all the included tools (e.g. 7zzs).

### Adding this repository to the PortMaster app
PortMaster's own app can browse and install these ports directly. Download [010_rhh.source.json](https://github.com/JeodC/RHH-Ports/releases/download/ports-latest/010_rhh.source.json) and place it in the `config` folder inside your PortMaster installation (next to `020_portmaster.source.json`), commonly:

- `/roms/ports/PortMaster/config/` (ArkOS and similar)
- `.local/share/PortMaster/config/` (ROCKNIX, muOS, Knulli, and similar)

On the next launch PortMaster will fetch this repository's catalog alongside its own. Note that a handful of ports here share names with entries in the official PortMaster or Multiverse catalogs; for those, PortMaster shows the official entry instead of mine.

## Port Capability Requirements
Some of the ports in this repository have minimum requirements. Be sure to check the `port.json` file for a port to see if it lists any of the following requirements:

- `hires`: The port will work best with a screen resolution greater than `640x480`.
- `!lowres`: The port will work best with a screen resolution that is at minimum `640x480`.
- `power`: The port will perform best with a device with more power than the `rk3326` cpu.
- `opengl`: The port requires OpenGL (not OpenGLES). This means a mainline custom firmware.
- `vulkan`: The port requires Vulkan. This typically pairs with Ultra requirements.
- `wide`: The port demands an aspect ratio above 4:3.
- `analog_#`: The port requires analog sticks.
- `!arkos`: The port will not run on ArkOS (GLIBC too old).

## Runtimes
Some of my ports require runtimes--mounted squashfs files that contain common scripts, programs, etc. These are found in the `runtimes` folder of this repository and should be placed in `PortMaster/libs` on your device.

## Troubleshooting
If you've run into a problem with one or more of these ports, feel free to raise an [issue](https://github.com/JeodC/RHH-Ports/issues) on this page. Please do not bother PortMaster community--they are not obligated to assist you and I'm unaffiliated.

## Keeping up
You can keep up with ports that I consider "complete" by checking the [commit history](https://github.com/JeodC/RHH-Ports/commits/main). I always prepend my commits with `[PORTNAME]` so it's easy to see what the commit most affects.

You can also browse the [unreleased](https://github.com/JeodC/RHH-Ports/tree/main/ports/unreleased) folder to see what I'm working on. If you star and watch this repository, you'll get GitHub notifications when I make changes.

## Contributing
If you see potential for improvements to my ports, I'm open to suggestions and pull requests--especially for unreleased ports, which are either in progress or in limbo for one reason or another. Please do not open issues to suggest new ports unless you're certain they can be ported. Although, if you're certain a game can be ported, why not do it yourself?

Please review the [Contribution Guidelines](.github/CONTRIBUTING.md) before proceeding with contributions.

## Donating
I love bringing indie games to the linux arm64 platform, and seeing people experience games through a new medium! Making legal ports with commercial indie games isn't free though. I accept donations on my [Ko-Fi](https://ko-fi.com/jeodc) page. All donations I receive go towards further port research -- mostly purchasing commercial games to develop new ports with.

## Licensing
All of these port wrappers are MIT licensed except for the following:

- Game assets as a part of "ready to run" ports are licensed for distribution through PortMaster, but the MIT license does *not* apply to the assets.
- Open source tools like [GMLoader-Next](https://github.com/PortsMaster/gmloader-next?tab=readme-ov-file) and [GMTools](https://github.com/cdeletre/gmtools) have their own licenses and are not necessarily MIT.
- Open source projects like Ship of Harkinian may also have their own licenses.
- Libraries used by the ports have their own licenses.

In short, the MIT license applies only to custom parts of the port wrappers, typically the bash files.
