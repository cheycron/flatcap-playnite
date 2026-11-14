# Flatcap for Playnite

![Version](https://img.shields.io/badge/version-2.0.0-blueviolet) ![Playnite](https://img.shields.io/badge/Playnite-10.64-blue) ![License](https://img.shields.io/badge/license-MIT-blue)

Two Desktop-mode themes for [Playnite](https://playnite.link) 10.x: **Flatcap Slate** (dark) and **Flatcap Daylight** (light). They apply the [Flatcap 2.0](https://github.com/cheycron/flatcap-theme) palette, type and metrics to Playnite's own Default theme, changing only what is needed. Each theme ships sixteen small files; Playnite takes everything else from its Default theme.

This project is not affiliated with Playnite or Josef Nemec. It is a derivative of Playnite's Default theme (MIT), see [Third-party code and licenses](#third-party-code-and-licenses).

| Slate, grid view | Slate, details view |
| :--- | :--- |
| ![Flatcap Slate, grid view](images/desktop-slate-grid.png) | ![Flatcap Slate, details view](images/desktop-slate-details.png) |
| **Daylight, grid view** | **Daylight, details view** |
| ![Flatcap Daylight, grid view](images/desktop-daylight-grid.png) | ![Flatcap Daylight, details view](images/desktop-daylight-details.png) |

The screenshots show a throwaway library of invented games with generated covers, in a separate portable Playnite copy ([docs/qa-report.md](docs/qa-report.md)).

<!-- build:themes -->
| Theme | Mode | Id | Package | Accent |
| :--- | :--- | :--- | :--- | :--- |
| Flatcap Slate | dark (Playnite Desktop) | `Flatcap_Slate_Desktop` | [`dist/Flatcap_Slate_Desktop_2_0_0.pthm`](https://github.com/cheycron/flatcap-playnite/raw/main/dist/Flatcap_Slate_Desktop_2_0_0.pthm) | `#9BBFDF` |
| Flatcap Daylight | light (Playnite Desktop) | `Flatcap_Daylight_Desktop` | [`dist/Flatcap_Daylight_Desktop_2_0_0.pthm`](https://github.com/cheycron/flatcap-playnite/raw/main/dist/Flatcap_Daylight_Desktop_2_0_0.pthm) | `#285D85` |
<!-- /build:themes -->

## Install

> **Installing replaces the theme's folder.** Both methods end in `Themes/Desktop/<ThemeId>/`. If that folder exists (an earlier Flatcap, or a copy you edited), treat it as replaced: back up anything of yours and delete it first, so no file of an older version stays behind. Nothing outside that folder is touched.

Playnite packages themes as **`.pthm`** files (`.pext` is for extensions; Playnite's installer tells them apart by the extension). This repository therefore ships `.pthm` files in `dist/`. The download links in the table above use `raw/main`, which **return 404 while this repository is private** (they work only for people signed in to GitHub with access); until it is public, use a clone of the repository or GitHub's own file download.

**Manual install (the method that was tested):**

1. Close Playnite.
2. Take the theme from `dist/` (`Flatcap_Slate_Desktop_2_0_0.pthm` or `Flatcap_Daylight_Desktop_2_0_0.pthm`). A `.pthm` is a ZIP file.
3. Delete `<Playnite data folder>/Themes/Desktop/<ThemeId>/` if it exists, then unzip the package into it so that `theme.yaml` sits directly in that folder (`<ThemeId>` is `Flatcap_Slate_Desktop` or `Flatcap_Daylight_Desktop`). The unpacked folders `themes/Desktop/<ThemeId>/` in this repository are the same files; you can copy one of those instead.
4. Start Playnite, open **Settings > Appearance > Theme (Desktop)** and choose Flatcap Slate or Flatcap Daylight. Restart when Playnite asks.

For a copy installed with the installer, the data folder is `%AppData%\Playnite`; for a portable copy it is the folder of `Playnite.DesktopApp.exe`.

**Install by opening the `.pthm` with Playnite (double click): not verified.** It should use Playnite's own installer, but it was **not tested**: in the test, passing the file to Playnite's command line at start-up did not install it, and the double-click flow itself was never run. If you try it, check afterwards that `theme.yaml` is directly inside `Themes/Desktop/<ThemeId>/`; if not, use the manual install.

## Use it

Nothing to configure. Slate and Daylight are separate themes; switch between them in the same setting. Fullscreen mode is not themed for now (see Compatibility): it keeps using Playnite's Fullscreen Default.

**Cover overlay in Daylight.** The overlay Playnite draws over a game cover (the name on hover, and the *Darken uninstalled* effect for games that are not installed) is the theme's own canvas color at 80% opacity. In Slate that is dark, as in Playnite; in **Daylight it is light**, so *Darken uninstalled* lightens the cover of an uninstalled game there instead of darkening it. The text on it keeps its contrast (checked over a pure white and a pure black cover).

## Tokens and contrast

Every color, font and size comes from [`src/theme.json`](src/theme.json), a copy of the Flatcap 2.0 core. `scripts/build.py` writes each theme's `Constants.xaml` from it and `--check` fails if a color literal remains in a shipped file, if a contrast target is missed, or if a generated file is stale. The mapping of Playnite's resources to tokens is in [docs/mapping.md](docs/mapping.md). Lowest ratio per group of pairs:

<!-- build:contrast -->
| Pair group | Target | Slate (lowest) | Daylight (lowest) |
| :--- | ---: | ---: | ---: |
| Primary text on every surface | 7 | 7.95 | 10.68 |
| Secondary text on surfaces | 5 | 5.51 | 6.28 |
| Accent (button text, icons, links) on surfaces | 4.5 | 5.75 | 5.68 |
| Text on accent fill and on the badge | 4.5 | 8.36 | 5.98 |
| Control borders and scrollbar thumb | 3 | 4.32 | 4.02 |
| Status colors on canvas and surface | 4.5 | 7.20 | 5.67 |
| Cover name on the overlay (worst case) | 4.5 | 6.38 | 7.54 |
| Cover icons on the overlay (worst case) | 3 | 4.62 | 4.01 |

Every pair is listed in [docs/mapping.md](docs/mapping.md#contrast); 64 targets across both themes, all met.
<!-- /build:contrast -->

## Fonts

The themes ask for IBM Plex Sans, then Segoe UI (the core's stack without generic families, which WPF does not have). **No font is bundled.** If IBM Plex Sans is not installed, WPF falls back to Segoe UI, which Windows has. Install [IBM Plex Sans](https://github.com/IBM/plex) to get the intended look; the screenshots were taken with the machine's own fonts.

## Accessibility

- Contrast targets (WCAG 2.2 ratios): primary text 7:1 on every surface, secondary text 5:1, accent and status colors 4.5:1, control borders 3:1. All are checked by `build.py --check` for both themes.
- Text on the cover overlay (game name, Play and Info icons) is checked against the overlay over a pure white and a pure black cover, the worst cases.
- Playnite's own focus and selection logic is not changed: the themes restyle, they do not change which control takes focus or how keys move it. Two states had the normal text color on the accent fill and are patched to the text-on-accent color: the **Play button on hover** and a **list item that has keyboard focus without selection**. Both are checked by `--check` from the shipped XAML (the hover and focus states are read from the files, not assumed). Sizes are the core's, with a 13 px minimum.
- **NOT TESTED:** screen readers, Windows High Contrast mode, and keyboard-only operation of every view.

## Compatibility

- Playnite **10.64**, Desktop mode, Windows. The themes declare `ThemeApiVersion: 2.0.0`, the same as Playnite 10.64's Default Desktop theme (the application's Desktop theme API is 2.10.0 and loads 2.x themes).
- Packaging with Playnite's own Toolbox 1.0.0 (`Toolbox.exe pack`) gives a package with the same files and content as `dist/`; see [docs/qa-report.md](docs/qa-report.md). The Toolbox warns that 2.0.0 is not the latest API version; the upstream Default theme has the same value.
- Playnite loads files a theme ships and takes the rest from its Default theme. Because the shipped files are copies of the 10.64 Default files with small patches, **a different Playnite version may need a rebuild**: `--check` fails when a vendored upstream file changes, so the patches never silently drift.
- **Fullscreen mode: not included for now.** It is out of scope for this release and still pending: no Fullscreen theme was attempted, and there is no date. See docs/qa-report.md.

**NOT TESTED** (as of this commit):

- Installing the `.pthm` through Playnite's own install flow (double click or add-on installer): never run. Passing the file on the command line at start-up did not install it in the test; the packaged files were extracted by hand into `Themes/Desktop/` instead (the layout the installer is expected to produce).
- Any Playnite version other than 10.64.
- Fullscreen mode, other languages, the Playnite add-ons' own windows, high DPI and multiple monitors.
- Views other than the grid and details views of the Desktop main window (list view, the filter panel, menus, dialogs and settings were not reviewed one by one).

## Third-party code and licenses

The shipped XAML files are modified copies of files of the Default theme of [Playnite](https://github.com/JosefNemec/Playnite) 10.64, Copyright (c) 2020 Josef Nemec, MIT License. The unmodified originals are vendored in [`upstream/playnite-10.64/`](upstream/playnite-10.64/) with their SHA-256 sums, and the license text is in [`LICENSES/Playnite-MIT.txt`](LICENSES/Playnite-MIT.txt). Each theme package carries `LICENSE.txt` with both licenses. The Flatcap palette, type and metrics are the Flatcap 2.0 core.

## Contributing

`src/theme.json` is a copy of the [Flatcap core](https://github.com/cheycron/flatcap-theme) and its SHA-256 is pinned in `src/playnite.json` (`core.sha256`): `--check` fails if the copy differs. To take a core change, copy the file over, run `--pin-core`, then `--sync`. Edit `src/playnite.json` for the mapping, then:

```
python3 scripts/build.py --sync     # regenerate themes/, dist/ and the generated blocks of the docs
python3 scripts/build.py --check    # exit 1 on any drift or failed check
python3 scripts/build.py --pin-core # after copying a new core on purpose
python3 scripts/mutation_test.py    # proves each check fails when it should
```

Python 3.10+, standard library only. Do not edit anything under `themes/`, `dist/` or between `<!-- build:... -->` markers by hand.

**Private names.** `--check` refuses private paths, addresses and names. The generic patterns (private and CGNAT IP ranges, `*.ts.net`, home and `/mnt` paths, Windows user folders, UNC shares, non-noreply emails) are in `scripts/build.py`. Names that only you know (your machines, domains, user name) go in a local `.private-patterns` file, one regular expression per line, which git ignores: copy [`.private-patterns.example`](.private-patterns.example). `FLATCAP_PRIVATE_PATTERNS=<file>` points the check at another file.

## License

[MIT](LICENSE) for this repository's own work. Playnite's Default theme files it is derived from are MIT, Copyright (c) 2020 Josef Nemec.

## Support

If Flatcap makes your workspace calmer, you can support its development.

<p align="center">
  <a href="https://www.buymeacoffee.com/cheycron">
    <img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me a Coffee">
  </a>
</p>
