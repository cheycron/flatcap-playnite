# QA report

What was verified for this release and how. Anything not listed here, or listed as **NOT TESTED**, was not verified. QA was done by the maintainer's build pipeline, not by an independent reviewer.

## 1. Static checks (`python3 scripts/build.py --check`)

The check is deterministic and runs offline. In this build:

<!-- build:static -->
| Check | Result in this build |
| :--- | :--- |
| Upstream files vendored and unchanged | 52 files match `SHA256SUMS` |
| Patches applied to upstream files | 25 replacements in 13 files, each matched the expected number of times |
| Shipped files per theme | 16 (Constants.xaml, CustomControls/SidebarItem.xaml, CustomControls/TopPanelItem.xaml, DefaultControls/DataGrid.xaml, DefaultControls/ListBox.xaml, DefaultControls/ProgressBar.xaml, DerivedStyles/DetailsHyperlink.xaml, DerivedStyles/GridViewItemTemplate.xaml, DerivedStyles/PlayButton.xaml, LICENSE.txt, Media.xaml, Views/DetailsViewGameOverview.xaml, Views/GridViewGameOverview.xaml, Views/SearchView.xaml, Views/TopPanel.xaml, theme.yaml) |
| Color keys mapped to tokens | 15 colors, 8 brushes, 10 added, 2 gradients replaced |
| Color literals outside `Constants.xaml` in shipped files | none |
| Contrast targets (Desktop) | 64 met (4 report-only rows) |
| Theme ids | unique, not built-in, letters, digits and underscores |
| `ThemeApiVersion` | 2.0.0 (loadable by Desktop API 2.10.0: same major, not newer) |
| **Fullscreen** upstream files vendored and unchanged | 37 files match `SHA256SUMS` |
| Fullscreen patches | 26 replacements in 13 files, each matched the expected number of times |
| Fullscreen shipped files | 16 (Constants.xaml, CustomControls/FilterPresetSelector.xaml, DefaultControls/CheckBox.xaml, DefaultControls/ComboBox.xaml, DefaultControls/ScrollViewer.xaml, DefaultControls/Slider.xaml, DefaultControls/ToggleButton.xaml, DerivedStyles/ListGameItemTemplate.xaml, LICENSE.txt, Views/FiltersView.xaml, Views/GameDetails.xaml, Views/GameMenu.xaml, Views/ItemSelection.xaml, Views/Main.xaml, Views/SettingsMenus.xaml, theme.yaml) |
| Fullscreen color literals outside `Constants.xaml` | none |
| Fullscreen text sizes | none under 18 px (FontSize, HtmlFontSize and the FontSize constants are checked) |
| Fullscreen contrast targets (text, states, focus outlines) | 61 met (2 report-only rows) |
| Fullscreen `ThemeApiVersion` | 2.0.0 (loadable by Fullscreen API 2.10.0: same major, not newer) |
<!-- /build:static -->

`--check` also verifies, for each of the two themes, that the unpacked folder and the `.pthm` match what the build generates, that `theme.yaml` has the fields Playnite needs (a valid id, a loadable `ThemeApiVersion`, a version equal to the core's), that every XAML file is well formed, that no `x:Key` is duplicated, that no shipped file contains a color literal or a named color, that every `Flatcap*` resource a file uses is defined in that theme's `Constants.xaml`, that the README has its required sections, that the screenshots exist and are 1440x900 PNG files without metadata chunks, and that no private path, IP address or host name is committed.

`python3 scripts/mutation_test.py` breaks the repository in a temporary copy, one defect per detector, and requires `--check` to fail with the expected message each time. A detector that never fails is not a detector. Last run: 121 of 121 cases behaved as expected (one unmutated baseline, which must pass, and 120 mutations, which must fail with the expected message). The new cases of this revision cover the bottom bar contrast pair, the non-colour state cues of Fullscreen (focused preset, active filter row and button, checked toggle), `FontSize` set through a `Setter`, the upstream provenance record, outdated README labels, and also: the hover and focus text contrast read from the generated XAML, color literals in every form the detector knows (hex of 3 to 8 digits, `sc#`, WPF named colors in attributes and text, `Colors.X`, `SystemColors`) with the single `OpacityMask` exception limited to `Black` and `Transparent`, the privacy patterns (generic ones and the local `.private-patterns` file), the SHA-256 pin of the core including CRLF input, and a package with a duplicated ZIP member. Earlier runs found real problems, all fixed: an extra file in a theme folder crashed the build with a traceback; some mutations of this revision did not mutate anything or expected the wrong message, and were corrected until each one failed for the intended reason. The cases cover the checks listed above; they are not a proof that no other defect goes undetected.

## 2. Package structure

<!-- build:pthmcheck -->
| Package | Members (in order) | Uncompressed bytes | Timestamp |
| :--- | :--- | ---: | :--- |
| `dist/Flatcap_Slate_Desktop_2_0_0.pthm` | `theme.yaml`, `Constants.xaml`, `CustomControls/SidebarItem.xaml`, `CustomControls/TopPanelItem.xaml`, `DefaultControls/DataGrid.xaml`, `DefaultControls/ListBox.xaml`, `DefaultControls/ProgressBar.xaml`, `DerivedStyles/DetailsHyperlink.xaml`, `DerivedStyles/GridViewItemTemplate.xaml`, `DerivedStyles/PlayButton.xaml`, `LICENSE.txt`, `Media.xaml`, `Views/DetailsViewGameOverview.xaml`, `Views/GridViewGameOverview.xaml`, `Views/SearchView.xaml`, `Views/TopPanel.xaml` | 122360 | 2026-01-01 (fixed) |
| `dist/Flatcap_Daylight_Desktop_2_0_0.pthm` | `theme.yaml`, `Constants.xaml`, `CustomControls/SidebarItem.xaml`, `CustomControls/TopPanelItem.xaml`, `DefaultControls/DataGrid.xaml`, `DefaultControls/ListBox.xaml`, `DefaultControls/ProgressBar.xaml`, `DerivedStyles/DetailsHyperlink.xaml`, `DerivedStyles/GridViewItemTemplate.xaml`, `DerivedStyles/PlayButton.xaml`, `LICENSE.txt`, `Media.xaml`, `Views/DetailsViewGameOverview.xaml`, `Views/GridViewGameOverview.xaml`, `Views/SearchView.xaml`, `Views/TopPanel.xaml` | 122369 | 2026-01-01 (fixed) |
| `dist/Flatcap_Slate_Fullscreen_2_0_0.pthm` | `theme.yaml`, `Constants.xaml`, `CustomControls/FilterPresetSelector.xaml`, `DefaultControls/CheckBox.xaml`, `DefaultControls/ComboBox.xaml`, `DefaultControls/ScrollViewer.xaml`, `DefaultControls/Slider.xaml`, `DefaultControls/ToggleButton.xaml`, `DerivedStyles/ListGameItemTemplate.xaml`, `LICENSE.txt`, `Views/FiltersView.xaml`, `Views/GameDetails.xaml`, `Views/GameMenu.xaml`, `Views/ItemSelection.xaml`, `Views/Main.xaml`, `Views/SettingsMenus.xaml` | 92517 | 2026-01-01 (fixed) |
<!-- /build:pthmcheck -->

The `.pthm` is a ZIP with `theme.yaml` first, written with fixed timestamps (2026-01-01), member order, compression level and attributes so it does not change from run to run. `--check` compares its members, content and ZIP metadata with a local rebuild.

**Playnite Toolbox 1.0.0** (`Toolbox.exe pack`, from the 10.64 release archive) was run on the unpacked folders of the **two Desktop themes only**, in an earlier revision (13 members each); it was **not** run on the Fullscreen theme nor re-run on the current Desktop packages. In that run its packages contained the same members as `dist/` of that revision, with identical content (SHA-256, 0 differences). Remaining differences were only the ZIP's internal separators (the Toolbox writes `\`, this build writes `/`) and the compression bytes. Toolbox printed *"Selected theme has not been updated to the latest supported API version"* for both, because they declare `ThemeApiVersion: 2.0.0`; the upstream Default theme declares the same value.

`Toolbox.exe verify` validates *add-on database manifests*, not `theme.yaml`, so it was not used as evidence for the theme manifest.

## 3. Real Playnite run

Environment: Windows machine reached through a remote-control server, **Playnite 10.64** portable copy (from the official `10.64.7z`, SHA-256 `a4538628d6a0f49cd337c8a8640294849d736217bf4d2d7c99c1eb1b68428611`, verified after download) extracted into a new temporary folder, **separate** from any installed Playnite. The portable copy used its own named-pipe endpoint so that it could not reach another running Playnite, and the processes that were stopped between runs were selected by their executable path inside that folder only. The machine's own Playnite, its library and its settings were not touched.

Library: 12 invented games ("Lantern Harbor", "Copper Steppe", ...) with covers drawn by a script (a flat color, a geometric shape and the title), made by a throw-away script extension that is in `qa/seed/`; it must never be installed in a real library. Playnite's `config.json` in the portable copy selected the theme under test and the view.

Procedure, per theme and view: stop the portable copy, unzip the `.pthm` built from this commit into `Themes/Desktop/<ThemeId>/`, select the theme in `config.json`, start Playnite, wait 14 s, resize the main window to 1440x900 and capture **only that window** with `PrintWindow` (so nothing else on the desktop can appear), then look at the image. Scripts: [`qa/qa-run.ps1`](../qa/qa-run.ps1), [`qa/winshot.ps1`](../qa/winshot.ps1).

Result: for both themes, Playnite started, showed the theme (palette, fonts, controls), listed and drew the 12 games in the grid and details views, and logged no error or warning about the theme or XAML. The screenshots were reviewed by eye before committing:

<!-- build:images -->
| Image | Size | SHA-256 |
| :--- | :--- | :--- |
| `images/desktop-slate-grid.png` | 1440x900 | `e5b1b3dc72a88992e6bf5c9642105c6afa1b495e3c9f560c55b2e405d13f877f` |
| `images/desktop-slate-details.png` | 1440x900 | `78867ba47aac78dfb73dfd9a31baf440e638407c7f1ebd85e252a85e3aa6f5c5` |
| `images/desktop-daylight-grid.png` | 1440x900 | `e51bcb11d9655fd1f1a7bcfee55db281331240bde0f9c751de8e993e12cd3caf` |
| `images/desktop-daylight-details.png` | 1440x900 | `118258846710d6165ff79f41d268e4c679741e4ed4043b88804f686d59a29361` |
| `images/fullscreen-slate-grid.png` | 1920x1080 | `50dd19f79011b1353af461d37f33c0ff84147e8e6312cc5ee5abee57ce2488f7` |
| `images/fullscreen-slate-details.png` | 1920x1080 | `585c762f9e3914c68715dddfe218f41d1811e3ac9fcef6b9e68c830db36c8de6` |
| `images/fullscreen-slate-menu.png` | 1920x1080 | `cd5e806fe3be75420f6604ac99bc7ae13517814fccfbebe647ccf6711b8761ae` |
<!-- /build:images -->

Observed while reviewing:

- Slate: neutral dark slate, light blue accent, Play button with dark text on the accent, readable list, details, description and links.
- Daylight: light surface, dark blue accent, dark text on every surface. **Fixed during QA:** the game title in the details view had Playnite's black drop shadow, which smudged it on a light surface; the shadow is now removed in both themes (patched files listed in docs/mapping.md).
- The Playnite logo (red game controller) is Playnite's, left as is.
- Playnite's startup message about running with elevated privileges appeared once in the portable copy (that Windows session runs elevated); it was dismissed there and is not part of the screenshots.

### Re-run for the contrast revision (2026-11-14)

The run above was repeated after the hover/focus contrast fix, with a **new** portable Playnite 10.64 (same official archive, SHA-256 verified again) in a new temporary folder, its own named-pipe endpoint and a new demo library of 12 invented games (`qa/seed/`). The theme folders were sent to the Windows machine as a compressed archive whose SHA-256 was verified there, and each package was re-zipped on that machine from those folders (same members and order as `dist/`; the bytes of `dist/*.pthm` themselves were not the ones installed). Both themes loaded, Playnite started with no theme/XAML error in its log, and all 12 games were seeded.

- **Captures.** The four 1440x900 captures taken in this run have the **same SHA-256** as the four images already in `images/`, so they were not replaced. They were not looked at again by eye in this run (the viewer could not open files on the Windows machine); the committed images are the ones reviewed earlier.
- **Hover on the Play button (observed live, by pixel measurement, not by eye).** With the mouse placed over the button, the 1 px border changed from the control border color to the primary text color (Slate `#8593A5` to `#D5DBE3`; Daylight `#6C7A89` to `#28313B`), and the fill and the label colors did not change: Slate dark `#101820` label on `#9BBFDF`; Daylight light `#FAFBFC` label on `#285D85`. The contrast of those label/fill pairs read from the generated XAML is 9.30:1 (Slate) and 6.77:1 (Daylight).
- **Keyboard focus without selection on a list item: NOT confirmed live.** In the Grid view, a click on the first cover followed by Ctrl+Right changed only about 120 pixels (a dark, shadow-like area), without the accent highlight, so that run does not show the `ListBoxItem` focus rule being used. The rule is covered only by the static contrast check (`TextBrushDark` on `GlyphBrush`: 9.30:1 and 6.77:1) and by the mutation cases.
- **Cleanup.** Only processes whose image was inside the temporary folder were stopped; the folder was then deleted. The real Playnite (PID 3088) was running before and after. One force-stop of the portable copy during its first-start wizard left a crash marker in that folder (`safestart.flag`), which produced a safe-mode prompt; it was removed and the run repeated.
- A request for a full-desktop screenshot closed the remote-control connection twice, so no desktop screenshot was used.

### What was not tested

- **Installing the `.pthm` through Playnite's own flow.** Passing the file as a command-line argument when starting the portable copy did not install it (no error was logged and the theme did not appear). The package contents were unzipped by hand into `Themes/Desktop/`, which is the layout Playnite's installer creates. The Toolbox pack comparison above supports that the package has the layout Playnite expects, but the install flow itself is **NOT TESTED**.
- Any Playnite version other than 10.64; the Desktop list view, filter panel, menus, dialogs and settings windows; high DPI; keyboard-only use; screen readers; Windows High Contrast.
- The outbound request Playnite makes for its update check was not blocked in the test.
- The privacy list kept in `.private-patterns` is local and not versioned, so what it matches is **not** checked by anyone else; the committed patterns are generic (RFC 1918 and CGNAT ranges, `*.ts.net`, Linux home and mount paths, Windows user-profile paths, UNC paths, non-noreply e-mail addresses).

## 4. Fullscreen

Flatcap Slate (Fullscreen) was run in a **new isolated portable Playnite 10.64** (same official archive, SHA-256 `a4538628d6a0f49cd337c8a8640294849d736217bf4d2d7c99c1eb1b68428611`) with its own named-pipe endpoint and the demo library of 12 invented games (`qa/seed/`). The three `.pthm` were unzipped by hand into `Themes/` (as in section 3) and Playnite was started in Fullscreen mode with `Flatcap_Slate_Fullscreen` selected. It loaded with the theme applied.

**Observed live.** Keys were sent to the Fullscreen window (arrows, A, X, Esc and others) and the screen was captured: the grid view, the details view, the game menu, the main menu and the filter screen. The grid, details and game-menu captures were looked at with an image viewer:

- Grid: the dark Slate surfaces, the top filter row, the clock and the bottom button legend are readable; the focused cover has a light-blue outline and glow that is clearly visible against the neighbours.
- Details: title, metadata, description and link are readable; the focused button (Play) has a visible light-blue outline, the other one a thin neutral border. The empty *Platform* value is data the demo game does not have.
- Game menu: the focused item (Play) has a visible light-blue outline.
- No personal data and no other window is visible; the only text from the machine is the clock.

**State cues (remediation).** In the top filter row, the focused preset shows a 3 px light-blue underline plus the accent text colour (captures after pressing Right once and twice: the underline moves from *All* to *Favorites* and is visible without relying on colour alone). The active filter row, active filter button and checked toggle cues (bold, 2 px underline or border) were **not** reviewed live; they are covered only by the static `FS_CUES` check and its mutations.

The main menu and filter screens were captured but **not reviewed by eye**; nothing is claimed about them beyond that they opened.

**Screenshots.** The captures are 2560x1440 and the committed `images/fullscreen-slate-*.png` are those captures scaled to 1920x1080 (exactly 0.75, Lanczos); they are not native 1920x1080 renders.

**Not tested.** A real game controller (the keyboard was used through window messages, so button prompts and controller navigation were not exercised), a TV or couch-distance reading, high DPI, other resolutions, other Fullscreen views and dialogs, and the install flow through Playnite itself. The contrast figures above come from the generated XAML, not from the live capture.

## 5. Maintainer decisions

- The history of this repository is kept as it is and internal names are not documented.
- Desktop `.pthm` packages and `ThemeApiVersion: 2.0.0` are kept.
- Fullscreen is developed (this section); a Daylight Fullscreen theme is a technical decision left out (see README).
