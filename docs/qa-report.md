# QA report

What was verified for this release and how. Anything not listed here, or listed as **NOT TESTED**, was not verified. QA was done by the maintainer's build pipeline, not by an independent reviewer.

## 1. Static checks (`python3 scripts/build.py --check`)

The check is deterministic and runs offline. In this build:

<!-- build:static -->
| Check | Result in this build |
| :--- | :--- |
| Upstream files vendored and unchanged | 12 files match `SHA256SUMS` |
| Patches applied to upstream files | 20 replacements in 10 files, each matched the expected number of times |
| Shipped files per theme | 13 (Constants.xaml, CustomControls/SidebarItem.xaml, CustomControls/TopPanelItem.xaml, DefaultControls/DataGrid.xaml, DefaultControls/ProgressBar.xaml, DerivedStyles/GridViewItemTemplate.xaml, LICENSE.txt, Media.xaml, Views/DetailsViewGameOverview.xaml, Views/GridViewGameOverview.xaml, Views/SearchView.xaml, Views/TopPanel.xaml, theme.yaml) |
| Color keys mapped to tokens | 15 colors, 8 brushes, 10 added, 2 gradients replaced |
| Color literals outside `Constants.xaml` in shipped files | none |
| Contrast targets | 54 met (4 report-only rows) |
| Theme ids | unique, not built-in, letters, digits and underscores |
| `ThemeApiVersion` | 2.0.0 (loadable by Desktop API 2.10.0: same major, not newer) |
<!-- /build:static -->

`--check` also verifies, for each of the two themes, that the unpacked folder and the `.pthm` match what the build generates, that `theme.yaml` has the fields Playnite needs (a valid id, a loadable `ThemeApiVersion`, a version equal to the core's), that every XAML file is well formed, that no `x:Key` is duplicated, that no shipped file contains a color literal or a named color, that every `Flatcap*` resource a file uses is defined in that theme's `Constants.xaml`, that the README has its required sections, that the screenshots exist and are 1440x900 PNG files without metadata chunks, and that no private path, IP address or host name is committed.

`python3 scripts/mutation_test.py` breaks the repository in a temporary copy, one defect per detector, and requires `--check` to fail with the expected message each time. A detector that never fails is not a detector. Last run: 61 of 61 cases behaved as expected (one unmutated baseline, which must pass, and 60 mutations, which must fail with the expected message). The first run found two real problems, both fixed: an extra file in a theme folder crashed the build with a traceback instead of reporting it, and one case did not mutate anything. The cases cover the checks listed above; they are not a proof that no other defect goes undetected.

## 2. Package structure

<!-- build:pthmcheck -->
| Package | Members (in order) | Uncompressed bytes | Timestamp |
| :--- | :--- | ---: | :--- |
| `dist/Flatcap_Slate_Desktop_2_0_0.pthm` | `theme.yaml`, `Constants.xaml`, `CustomControls/SidebarItem.xaml`, `CustomControls/TopPanelItem.xaml`, `DefaultControls/DataGrid.xaml`, `DefaultControls/ProgressBar.xaml`, `DerivedStyles/GridViewItemTemplate.xaml`, `LICENSE.txt`, `Media.xaml`, `Views/DetailsViewGameOverview.xaml`, `Views/GridViewGameOverview.xaml`, `Views/SearchView.xaml`, `Views/TopPanel.xaml` | 113899 | 2026-01-01 (fixed) |
| `dist/Flatcap_Daylight_Desktop_2_0_0.pthm` | `theme.yaml`, `Constants.xaml`, `CustomControls/SidebarItem.xaml`, `CustomControls/TopPanelItem.xaml`, `DefaultControls/DataGrid.xaml`, `DefaultControls/ProgressBar.xaml`, `DerivedStyles/GridViewItemTemplate.xaml`, `LICENSE.txt`, `Media.xaml`, `Views/DetailsViewGameOverview.xaml`, `Views/GridViewGameOverview.xaml`, `Views/SearchView.xaml`, `Views/TopPanel.xaml` | 113908 | 2026-01-01 (fixed) |
<!-- /build:pthmcheck -->

The `.pthm` is a ZIP with `theme.yaml` first, written with fixed timestamps (2026-01-01), member order, compression level and attributes so it does not change from run to run. `--check` compares its members, content and ZIP metadata with a local rebuild.

**Playnite Toolbox 1.0.0** (`Toolbox.exe pack`, from the 10.64 release archive) was run on the unpacked folders of the final packages (13 members each) on a Windows machine. Its packages contain the same members as `dist/` (13 each), with identical content for every member (compared by SHA-256, 0 differences, for both themes). Differences that remain are only the ZIP's internal separators (the Toolbox writes `\`, this build writes `/`) and the compression bytes. Toolbox printed *"Selected theme has not been updated to the latest supported API version"* for both, because they declare `ThemeApiVersion: 2.0.0`; the upstream Default theme declares the same value.

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
<!-- /build:images -->

Observed while reviewing:

- Slate: neutral dark slate, light blue accent, Play button with dark text on the accent, readable list, details, description and links.
- Daylight: light surface, dark blue accent, dark text on every surface. **Fixed during QA:** the game title in the details view had Playnite's black drop shadow, which smudged it on a light surface; the shadow is now removed in both themes (patched files listed in docs/mapping.md).
- The Playnite logo (red game controller) is Playnite's, left as is.
- Playnite's startup message about running with elevated privileges appeared once in the portable copy (that Windows session runs elevated); it was dismissed there and is not part of the screenshots.

### What was not tested

- **Installing the `.pthm` through Playnite's own flow.** Passing the file as a command-line argument when starting the portable copy did not install it (no error was logged and the theme did not appear). The package contents were unzipped by hand into `Themes/Desktop/`, which is the layout Playnite's installer creates. The Toolbox pack comparison above supports that the package has the layout Playnite expects, but the install flow itself is **NOT TESTED**.
- Any Playnite version other than 10.64; Fullscreen mode; the list view, filter panel, menus, dialogs and settings windows; high DPI; keyboard-only use; screen readers; Windows High Contrast.
- The outbound request Playnite makes for its update check was not blocked in the test.

## 4. Fullscreen

Not done. Flatcap Slate for Fullscreen would need its own set of Default files (a different theme tree and API) and a separate real-run pass. It was left out of this release for time; it is not a decision of the maintainer.
