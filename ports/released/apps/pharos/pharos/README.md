<div align=center>
<img width="320" height="317" alt="image" src="https://raw.githubusercontent.com/JeodC/RHH-Ports/refs/heads/main/ports/released/apps/pharos/pharos/cover.png" />
</div>

# Pharos
Named after the Lighthouse of Alexandria, **Pharos** is a browser application designed to provide an alternative interface for installing ports and wine-arm64 wrappers. Pharos follows GitHub and GitLab repositories listed in a configurable file `sources.json` and presents eligible items hosted on those repositories.

<div align=center>
<img width="400" height="300" alt="pharos2" src="https://raw.githubusercontent.com/JeodC/RHH-Ports/refs/heads/main/ports/released/apps/pharos/pharos/screenshot.png" />
</div>

## How It Works

1. Pharos reads a list of repositories from `sources.json`. GitHub repositories can be `owner/name` or a URL. GitLab repositories need a URL. Set `enabled` to `false` to hide one.
2. It parses each repository and displays eligible items in its GUI.
4. Downloaded files are placed in `pharos/autoinstall`.
5. Pharos installs the port or wine bottle to either `roms/ports` or `roms/windows` folders.
6. Pharos updates `gamelist.xml` with `gameinfo.xml` included with the download.

> **Important:** For Pharos to parse and display repositories correctly, participating repositories must follow a **compatible file structure** and have a valid `ports.json` or `winecask.json` file.

## Settings
- **Filter out ports that aren't compatible with this device**: Hides ports your device can't run. When it's off, Pharos asks before downloading one.
- **Override PortMaster's device info**: Gives ports the screen size and 32-bit support Pharos measured, if PortMaster reports something different.
- **Manage Sources**: Add, edit, reorder, turn off or delete repositories.
- **List Details**: Choose what to show next to port, bottle and repository names.
- **Pharos Service**: Checks for port updates in the background.
- **Theme**: Choose Pharos's colors. See [Making a Theme](#making-a-theme).
- **Language**: Choose Pharos's language. See [Adding a Language](#adding-a-language).
- **Device Info**: Shows your device's specs.

## Making a Theme
Put a `.json` file in a `themes` folder next to `sources.json`. The file name is the theme's name. Missing colors come from the default theme.

```json
{
  "background": "#000000",
  "row_bg": "#383838",
  "row_selected": "#2f843e"
}
```

- **Screen**: `background`, `text`, `label`, `progress_bar`, `discount`
- **Header and footer**: `header_bg`, `header_text`, `header_info`, `footer_bg`, `footer_text`
- **Rows**: `row_bg`, `row_text`, `row_muted`, `row_selected`, `row_selected_text`, `row_highlight`, `row_highlight_text`
- **Popups**: `popup_bg`, `popup_border`, `popup_text`
- **Buttons**: `btn_a`, `btn_b`, `btn_x`, `btn_y`, `btn_l1`, `btn_r1`, `btn_text`

## Adding a Language
Open **Language** in the settings once to get `template.json` in the `languages` folder next to `sources.json`. Copy it to a new file in that folder and translate the text. `LANGUAGE_NAME` is the name to show in the list. Keep anything in braces, such as `{name}`. Missing text stays in English.

Pharos can draw Latin, Cyrillic and Greek letters.

## Security
Pharos does **not perform validation** on downloaded files. Users are responsible for ensuring that all sources are trusted and safe.

## Hosting Your Own Repository
To host a repository compatible with Pharos, ensure it adheres to the expected structure and `ports.json` or `winecask.json` format. For guidance, see the [template repository](https://github.com/JeodC/Pharos-Template).

## Thanks
Pharos is a python application inspired by RomM and PortMaster. Some code is based on existing functions from those applications, hence the AGPL license.
