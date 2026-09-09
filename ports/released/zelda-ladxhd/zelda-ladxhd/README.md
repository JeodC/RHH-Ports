## DISCLAIMER

**This port does not distribute LADXHD-Updated or the original game!** It is a replacement tool for the linux arm launcher that upstream provides, for accessibility. Users are expected to provide their own game assets and the tracked upstream LADXHD-Updated is necessary for the port to function.

## Installation
Place the original `Links Awakening DX HD v1.0.0.zip` file in the `zelda-ladxhd/data` folder. The port automatically extracts and patches the game to the latest [LADXHD-Updated](https://gitlab.com/bighead.0/ladxhd_updated/-/releases) release on first launch.

## Updates
The port tracks upstream's GitLab releases. When a newer release is detected on launch, the patcher re-runs from the preserved v1.0.0 base.

The patcher dialog asks whether to keep the update check enabled. Choose **No** to freeze the port at its current upstream version. To re-enable later, delete `zelda-ladxhd/data/.update_check`.

If the device is offline at launch, the update check is skipped silently and the game runs as-is.

## Manual / offline patching
If your device has no internet connection, you can pre-stage the patcher files on a PC and the port will use them instead of downloading.

1. Find the latest upstream release tag at <https://gitlab.com/bighead.0/ladxhd_updated/-/releases>.
2. Download **both** patch archives from that tag and place them in `zelda-ladxhd/data/`. Upstream splits them between the data files every platform shares and the arm64 OpenGL build's own files:
   ```
   https://gitlab.com/bighead.0/ladxhd_updated/-/raw/<tag>/ladxhd_patcher_source_code/Resources/patches_allplatforms.7z
   https://gitlab.com/bighead.0/ladxhd_updated/-/raw/<tag>/ladxhd_patcher_source_code/Resources/patches_linux_arm64_gl.7z
   ```
3. Download `file_targets_xnb.txt` from the same tag and place it at `zelda-ladxhd/data/file_targets_xnb.txt`. This file maps the upstream source files to their Linux outputs (including the game binary) and is **required** for an offline patch. Without it, the patcher cannot determine which files to patch and will stop with an error.
   ```
   https://gitlab.com/bighead.0/ladxhd_updated/-/raw/<tag>/ladxhd_patcher_source_code/Resources/file_targets_xnb.txt
   ```
4. *(Optional)* Download `achievements.7z` from the same tag and place it at `zelda-ladxhd/data/achievements.7z`. This archive contains the achievement icons. Without it, achievements still function, but their icons will be missing.
   ```
   https://gitlab.com/bighead.0/ladxhd_updated/-/raw/<tag>/ladxhd_patcher_source_code/Resources/achievements.7z
   ```
5. Place your original `Links Awakening DX HD v1.0.0.zip` in `zelda-ladxhd/data/` (same as a normal installation).
6. Launch the port. The patcher detects the local files and uses them instead of downloading.

The installed version is stamped as `manual` after an offline patch, so the port will re-patch from upstream the next time the device has internet access (unless you've disabled update checks).

## Notes
- Nintendo layout users should create a `swapabxy.txt` file in `zelda-ladxhd` and enable **Swap Confirm/Cancel** in the game's settings.
- Users with small display resolutions or unusual aspect ratios can edit the files in `zelda-ladxhd/data/Mods/LAHDMods` to adjust UI scale overrides.

## Thanks
Nintendo -- The original game  
BigheadSMZ -- LADXHD-Updated patches and compatibility improvements for retro handhelds