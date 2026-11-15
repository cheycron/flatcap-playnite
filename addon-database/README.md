# Playnite add-on database submission (ready, not submitted)

These are the three add-on manifests for the [Playnite add-on database](https://github.com/JosefNemec/PlayniteAddonDatabase), kept here so the submission can be made at any time without rebuilding anything.

| File | AddonId | Type |
|---|---|---|
| [`themes_desktop/Flatcap_Slate_Desktop.yaml`](themes_desktop/Flatcap_Slate_Desktop.yaml) | `Flatcap_Slate_Desktop` | ThemeDesktop |
| [`themes_desktop/Flatcap_Daylight_Desktop.yaml`](themes_desktop/Flatcap_Daylight_Desktop.yaml) | `Flatcap_Daylight_Desktop` | ThemeDesktop |
| [`themes_fullscreen/Flatcap_Slate_Fullscreen.yaml`](themes_fullscreen/Flatcap_Slate_Fullscreen.yaml) | `Flatcap_Slate_Fullscreen` | ThemeFullscreen |

Each one points at its installer manifest in [`../installer/`](../installer/), which in turn points at the `.pthm` attached to the [v2.0.0 release](https://github.com/cheycron/flatcap-playnite/releases/tag/v2.0.0).

## Status

**Not submitted.** As of 2026-11-14 the add-on database says new submissions are on hold until its new add-on portal ships (planned for the end of 2026, Playnite 11 with a backport to Playnite 10), except for trusted community members who contact the maintainers on Playnite's Discord.

The same three files are already committed on the branch `add-flatcap-themes` of the fork `cheycron/PlayniteAddonDatabase` (folders `addons/themes_desktop/` and `addons/themes_fullscreen/`).

## Submitting later

1. Check the database README for the current process. If the new portal is live, use it with these same fields instead of a pull request.
2. If pull requests are accepted again, refresh the fork branch against `master`, copy these files into `addons/` if they changed here, and open one pull request:

   ```
   gh pr create -R JosefNemec/PlayniteAddonDatabase --base master \
     --head cheycron:add-flatcap-themes \
     --title "Add Flatcap Slate, Flatcap Daylight (Desktop) and Flatcap Slate (Fullscreen) themes"
   ```

3. After it is merged, update the main README: remove "pending review" from the add-on browser section.

For a new theme version, bump the version, run `python3 scripts/build.py --sync` (it regenerates `installer/`), attach the new `.pthm` files to a new release and add the package to each installer manifest. The add-on database entries do not change.
