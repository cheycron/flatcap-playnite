#!/usr/bin/env python3
"""Build Flatcap 2.0 for Playnite (Desktop and Fullscreen modes) from src/theme.json (the Flatcap core) and src/playnite.json (port settings).

    python3 scripts/build.py --sync     write themes/Desktop/<Id>/, dist/*.pthm and the generated blocks of README.md and docs/*.md;
                                        exit 1 (after writing) if the result does not pass the checks below
    python3 scripts/build.py --check    exit 1 on: a stale generated file, a missing or duplicated <!-- build:x --> marker, an upstream
                                        Playnite file that changed, a src/theme.json that is not the pinned core copy, a theme.yaml with
                                        wrong or duplicated fields, XAML that is not well formed, a color literal (hex of 3 to 8 digits,
                                        sc#, a named color, SystemColors) or an unresolved Flatcap resource in a theme file, a .pthm whose
                                        members, content or metadata differ from the build, a README without its required sections, a
                                        missing or wrong-sized screenshot, a private path, address or host name (generic patterns plus the
                                        local, git-ignored .private-patterns), or a missed contrast target (including the hover and focus
                                        states read from the shipped XAML)
    python3 scripts/build.py --pin-core rewrite the SHA-256 of src/theme.json in src/playnite.json (after copying a new core on purpose)

What it builds
  * themes/Desktop/<Id>/   a theme folder Playnite can load as is (copy it to <Playnite>/Themes/Desktop/). It holds theme.yaml, a
                           generated Constants.xaml, a handful of Default-theme files with small documented patches, and LICENSE.txt.
                           Playnite loads only the files a theme ships and takes every other file from its own Default theme, so
                           nothing else is copied (see docs/mapping.md).
  * installer/<Id>.yaml    the installer manifest for the Playnite add-on browser (AddonId, version, API, PackageUrl of the GitHub release asset)
  * dist/<Id>_<version>.pthm   the package the Toolbox (`Toolbox.exe pack`) makes: a ZIP with theme.yaml and the shipped files. The
                           build writes it deterministically: fixed timestamp, member order and attributes.
The base of every shipped Default file is vendored, unmodified, in upstream/playnite-10.64/ with its SHA-256 in SHA256SUMS: --check fails
if one of them changes, because the patches are written against exactly those files.
Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import struct
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import color as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "src" / "theme.json"
PORT = ROOT / "src" / "playnite.json"
MODES = ("slate", "daylight", "fs_slate")  # every theme the build produces (keys of src/playnite.json "themes")
DESKTOP = ("slate", "daylight")
FULLSCREEN = ("fs_slate",)
FS_IMAGE_SIZE = (1920, 1080)
FS_MIN_TEXT = 18  # px: the smallest text a Fullscreen (TV, couch distance) theme may draw; Default Fullscreen's smallest is 18
ZIP_DATE = (2026, 1, 1, 0, 0, 0)  # fixed: the .pthm files must not change with the build date
PRIVATE_FILE = ROOT / ".private-patterns"  # local, git-ignored: one regular expression per line (see .private-patterns.example)
PRIVACY = [  # generic patterns for strings that must never be committed: personal paths, private addresses, internal names, personal emails
    (r"[A-Za-z]:\\+Users", "a Windows user path"), (r"AppData\\+(?:Local|Roaming)", "an AppData path"),
    (r"/mnt/[A-Za-z0-9_.-]", "a /mnt path"), (r"/home/[A-Za-z0-9_.-]", "a home directory path"), (r"/Users/[A-Za-z0-9_.-]", "a macOS home path"),
    (r"(?<![\w\\:.])\\\\[A-Za-z0-9_-][\w.-]*\\+[\w$]", "a UNC path"),
    (r"\.review", "the private review folder"),
    (r"(?<![\d.])10\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 10/8)"),
    (r"(?<![\d.])172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 172.16/12)"),
    (r"(?<![\d.])192\.168\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 192.168/16)"),
    (r"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}(?![\d.])", "a CGNAT / Tailscale IP (100.64/10)"),
    (r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:local|lan|internal|intranet|corp|home\.arpa)\b", "an internal host name"),
    (r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.ts\.net\b", "a Tailscale host name (*.ts.net)"),
    (r"[A-Za-z0-9._%+-]+@(?!(?:[A-Za-z0-9-]+\.)*noreply\.github\.com\b)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", "an email address that is not a GitHub noreply one"),
]
SKIP_DIRS = {".git", ".review", "__pycache__", ".tmp", "node_modules"}
BUILTIN_IDS = {"Playnite_builtin_DefaultDesktop", "Playnite_builtin_DefaultFullscreen"}
# every name of System.Windows.Media.Colors (and the Grey spellings the XAML parser accepts)
WPF_COLORS = {c.lower() for c in """AliceBlue AntiqueWhite Aqua Aquamarine Azure Beige Bisque Black BlanchedAlmond Blue BlueViolet Brown BurlyWood CadetBlue
Chartreuse Chocolate Coral CornflowerBlue Cornsilk Crimson Cyan DarkBlue DarkCyan DarkGoldenrod DarkGray DarkGreen DarkKhaki DarkMagenta
DarkOliveGreen DarkOrange DarkOrchid DarkRed DarkSalmon DarkSeaGreen DarkSlateBlue DarkSlateGray DarkTurquoise DarkViolet DeepPink DeepSkyBlue
DimGray DodgerBlue Firebrick FloralWhite ForestGreen Fuchsia Gainsboro GhostWhite Gold Goldenrod Gray Green GreenYellow Honeydew HotPink IndianRed
Indigo Ivory Khaki Lavender LavenderBlush LawnGreen LemonChiffon LightBlue LightCoral LightCyan LightGoldenrodYellow LightGray LightGreen LightPink
LightSalmon LightSeaGreen LightSkyBlue LightSlateGray LightSteelBlue LightYellow Lime LimeGreen Linen Magenta Maroon MediumAquamarine MediumBlue
MediumOrchid MediumPurple MediumSeaGreen MediumSlateBlue MediumSpringGreen MediumTurquoise MediumVioletRed MidnightBlue MintCream MistyRose
Moccasin NavajoWhite Navy OldLace Olive OliveDrab Orange OrangeRed Orchid PaleGoldenrod PaleGreen PaleTurquoise PaleVioletRed PapayaWhip PeachPuff
Peru Pink Plum PowderBlue Purple Red RosyBrown RoyalBlue SaddleBrown Salmon SandyBrown SeaGreen SeaShell Sienna Silver SkyBlue SlateBlue SlateGray
Snow SpringGreen SteelBlue Tan Teal Thistle Tomato Transparent Turquoise Violet Wheat White WhiteSmoke Yellow YellowGreen Grey DarkGrey DimGrey
LightGrey SlateGrey DarkSlateGrey LightSlateGrey""".split()}
ALLOWED_NAMED = {"transparent"}  # paints nothing: the hit-test background of a control
MASK_NAMED = {"black", "transparent"}  # an opacity mask only decides how opaque each pixel is (Black = opaque, Transparent = clear)
HEX_LITERAL = re.compile(r"(?<![&\w#])#[0-9A-Fa-f]{3,8}\b")
ATTR_VALUE = re.compile(r'[\w:.]+\s*=\s*"([^"]*)"')
README_SECTIONS = ["Install", "Use it", "Fullscreen", "Tokens and contrast", "Fonts", "Accessibility", "Compatibility", "Third-party code and licenses",
                   "Contributing", "License"]
DOC_BLOCKS = {"README.md": ["themes", "contrast", "fs-contrast"],
              "docs/mapping.md": ["upstream", "constants", "added", "patches", "files", "contrast",
                                  "fs-upstream", "fs-constants", "fs-added", "fs-patches", "fs-files", "fs-contrast"],
              "docs/qa-report.md": ["pthmcheck", "static", "images"]}
IMAGES = {"desktop-slate-grid.png": (1440, 900), "desktop-slate-details.png": (1440, 900), "desktop-daylight-grid.png": (1440, 900),
          "desktop-daylight-details.png": (1440, 900), "fullscreen-slate-grid.png": FS_IMAGE_SIZE, "fullscreen-slate-details.png": FS_IMAGE_SIZE,
          "fullscreen-slate-menu.png": FS_IMAGE_SIZE}
REPO_RAW = "https://raw.githubusercontent.com/cheycron/flatcap-playnite/main"


def load() -> dict:
    return json.loads(THEME.read_text(encoding="utf-8"))


def port() -> dict:
    return json.loads(PORT.read_text(encoding="utf-8"))


# --- tokens ---------------------------------------------------------------------------------------------------------

def tk(theme: dict, mode: str, token: str) -> str:
    return theme["themes"][mode][token]


def argb(hexrgb: str, alpha: int = 255) -> str:
    r, g, b, a = C.parse(hexrgb)
    return "#" + f"{alpha:02X}" + "".join(f"{round(v * 255):02X}" for v in (r, g, b))


def wpf_family(css: str) -> str:
    """'"IBM Plex Sans", "Segoe UI", system-ui, sans-serif' -> 'IBM Plex Sans, Segoe UI' (WPF has no generic families)."""
    out = []
    for part in re.findall(r'"[^"]*"|[^,]+', css):
        p = part.strip().strip('"').strip()
        if p and p.lower() not in {"system-ui", "sans-serif", "serif", "monospace", "ui-monospace", "ui-sans-serif"}:
            out.append(p)
    return ", ".join(out)


def px(css: str) -> str:
    m = re.fullmatch(r"([\d.]+)(rem|px)", css.strip())
    if not m:
        raise ValueError(f"not a rem or px length: {css!r}")
    v = float(m.group(1)) * (16 if m.group(2) == "rem" else 1)
    return str(int(v)) if v == int(v) else str(v)


# --- upstream (the vendored Default theme files) -------------------------------------------------------------------

def kind_of(p: dict, key: str) -> str:
    return p["themes"][key]["mode"]  # "Desktop" or "Fullscreen"


def patches_of(kind: str) -> list:
    return PATCHES if kind == "Desktop" else FS_PATCHES


def cfg_of(p: dict, kind: str) -> dict:
    """The Constants.xaml mapping of a mode."""
    return p["constants"] if kind == "Desktop" else p["fullscreen"]["constants"]


def palette(p: dict, key: str) -> str:
    """The token set (a key of src/theme.json \"themes\") a theme uses."""
    return p["themes"][key].get("palette", key)


def upstream_root(p: dict, kind: str = "Desktop") -> Path:
    return ROOT / (p["upstream"]["root"] if kind == "Desktop" else p["upstream"]["fullscreen_root"])


def upstream_sums() -> dict[str, str]:
    f = ROOT / "upstream" / "playnite-10.64" / "SHA256SUMS"
    out = {}
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                h, name = ln.split(None, 1)
                out[name.strip().lstrip("*")] = h
    return out


def upstream_text(p: dict, rel: str, kind: str = "Desktop") -> str:
    # Playnite's files use CRLF and sometimes a BOM; the build works on LF text without BOM so patches and generated output are uniform
    return (upstream_root(p, kind) / rel).read_bytes().decode("utf-8-sig").replace("\r\n", "\n")


def upstream_errors(p: dict) -> list[str]:
    errs = []
    sums = upstream_sums()
    root = upstream_root(p)
    base = ROOT / "upstream" / "playnite-10.64"
    if not sums:
        return ["upstream/playnite-10.64/SHA256SUMS is missing or empty"]
    for name, h in sorted(sums.items()):
        f = base / name
        if not f.exists():
            errs.append(f"upstream file missing: upstream/playnite-10.64/{name}")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != h:
            errs.append(f"upstream file changed: upstream/playnite-10.64/{name} no longer matches SHA256SUMS (the patches are written against Playnite 10.64's file)")
    on_disk = {x.relative_to(base).as_posix() for x in base.rglob("*") if x.is_file() and x.name not in ("SHA256SUMS", "SOURCE.txt")}
    for name in sorted(on_disk - set(sums)):
        errs.append(f"upstream file without a checksum: upstream/playnite-10.64/{name}")
    for kind, patches in (("Desktop", PATCHES), ("Fullscreen", FS_PATCHES)):
        for rel in [f for f, _ in patches] + ["Constants.xaml"]:
            if f"{kind}/Default/{rel}" not in sums:
                errs.append(f"upstream/playnite-10.64/{kind}/Default/{rel} is patched but not listed in SHA256SUMS")
        # every file a state contract reads must be vendored too
        for rel in {f for _, f, *_ in (STATE_CONTRACTS if kind == "Desktop" else FS_STATES)} | {f for _, f, *_ in (() if kind == "Desktop" else FS_FOCUS + FS_CUES)}:
            if f"{kind}/Default/{rel}" not in sums:
                errs.append(f"upstream/playnite-10.64/{kind}/Default/{rel} is read by a contrast state but not listed in SHA256SUMS")
    src = base / "SOURCE.txt"
    if not src.exists() or p["upstream"]["commit"] not in src.read_text(encoding="utf-8") or not re.fullmatch(r"[0-9a-f]{40}", p["upstream"]["commit"]):
        errs.append(f"upstream/playnite-10.64/SOURCE.txt is missing or does not name the commit of Playnite's tag {p['upstream']['tag']} ({p['upstream']['commit']})")
    lic = ROOT / p["upstream"]["license"]
    if not lic.exists() or "Josef Nemec" not in lic.read_text(encoding="utf-8") or "MIT License" not in lic.read_text(encoding="utf-8"):
        errs.append(f"{p['upstream']['license']}: the Playnite MIT license text (Josef Nemec) is missing")
    yaml = (root / "theme.yaml").read_text(encoding="utf-8-sig") if (root / "theme.yaml").exists() else ""
    if f"ThemeApiVersion: {p['playnite']['desktop_theme_api_version']}" not in yaml:
        errs.append("upstream theme.yaml does not declare the ThemeApiVersion that src/playnite.json says")
    fsroot = upstream_root(p, "Fullscreen")
    fsyaml = (fsroot / "theme.yaml").read_text(encoding="utf-8-sig") if (fsroot / "theme.yaml").exists() else ""
    if f"ThemeApiVersion: {p['playnite']['fullscreen_theme_api_version']}" not in fsyaml:
        errs.append("upstream Fullscreen theme.yaml does not declare the ThemeApiVersion that src/playnite.json says")
    if "Mode: Fullscreen" not in fsyaml:
        errs.append("upstream Fullscreen theme.yaml is not a Fullscreen theme")
    return errs


# --- Constants.xaml ----------------------------------------------------------------------------------------------------

def sub_once(text: str, pattern: str, repl: str, what: str, flags: int = 0) -> str:
    new, n = re.subn(pattern, lambda m: repl, text, flags=flags)
    if n != 1:
        raise ValueError(f"Constants.xaml: expected exactly one {what}, found {n}")
    return new


def constants_xaml(theme: dict, p: dict, mode: str) -> str:
    t = lambda tok: tk(theme, mode, tok)  # noqa: E731
    cs = p["constants"]
    text = upstream_text(p, "Constants.xaml")
    for key, spec in cs["colors"].items():
        text = sub_once(text, rf'<Color x:Key="{key}">#[0-9A-Fa-f]{{6,8}}</Color>',
                        f'<Color x:Key="{key}">{argb(t(spec["token"]))}</Color> <!-- {spec["token"]} -->', f"<Color> {key}")
    for key, spec in cs["brushes"].items():
        text = sub_once(text, rf'<SolidColorBrush x:Key="{key}" Color="[^"]*" />',
                        f'<SolidColorBrush x:Key="{key}" Color="{argb(t(spec["token"]))}" /> <!-- {spec["token"]} -->', f"<SolidColorBrush> {key}")
    text = sub_once(text, r'<LinearGradientBrush x:Key="ExpanderBackgroundBrush".*?</LinearGradientBrush>',
                    '<LinearGradientBrush x:Key="ExpanderBackgroundBrush" StartPoint="-0.1,0.5" EndPoint="1.2,1">\n'
                    f'        <GradientStop Color="{argb(t("bg.raised"))}" Offset="0"/> <!-- bg.raised -->\n'
                    f'        <GradientStop Color="{argb(t("bg.raised"), 0)}" Offset="0.7"/>\n    </LinearGradientBrush>',
                    "ExpanderBackgroundBrush", re.S)
    text = sub_once(text, r'<LinearGradientBrush x:Key="WindowBackgourndBrush".*?</LinearGradientBrush>',
                    f'<SolidColorBrush x:Key="WindowBackgourndBrush" Color="{argb(t("bg.canvas"))}" /> <!-- bg.canvas -->',
                    "WindowBackgourndBrush", re.S)
    ty, me = theme["typography"], theme["metrics"]
    for key, tok in cs["typography"].items():
        if key.startswith("FontSize"):
            text = sub_once(text, rf'<sys:Double x:Key="{key}">[^<]*</sys:Double>', f'<sys:Double x:Key="{key}">{px(ty[tok])}</sys:Double> <!-- {tok} -->', key)
        else:
            text = sub_once(text, rf'<FontFamily x:Key="{key}">[^<]*</FontFamily>', f'<FontFamily x:Key="{key}">{wpf_family(ty[tok])}</FontFamily> <!-- {tok} -->', key)
    text = sub_once(text, r'<CornerRadius x:Key="ControlCornerRadius">[^<]*</CornerRadius>',
                    f'<CornerRadius x:Key="ControlCornerRadius">{px(me["radius.control"])}</CornerRadius> <!-- radius.control -->', "ControlCornerRadius")
    for key in ("ControlBorderThickness", "PopupBorderThickness"):
        text = sub_once(text, rf'<Thickness x:Key="{key}">[^<]*</Thickness>',
                        f'<Thickness x:Key="{key}">{px(me["border.width"])}</Thickness> <!-- border.width -->', key)
    add = ["", "    <!-- Flatcap additions: brushes for the places where the Default theme hardcodes a color. See docs/mapping.md. -->"]
    for key, spec in cs["added"].items():
        add.append(f'    <SolidColorBrush x:Key="{key}" Color="{argb(t(spec["token"]), spec.get("alpha", 255))}" /> <!-- {spec["token"]} -->')
    text = text.replace("</ResourceDictionary>", "\n".join(add) + "\n</ResourceDictionary>")
    head = (f"    <!-- Flatcap for Playnite {theme['version']} ({p['themes'][mode]['name']}). Generated by scripts/build.py from src/theme.json\n"
            "         (the Flatcap 2.0 core); do not edit by hand. Based on Constants.xaml of Playnite 10.64's Default Desktop theme\n"
            "         (MIT, Copyright (c) 2020 Josef Nemec). Keys and structure are the original ones: only values change. -->\n")
    m = re.search(r"<ResourceDictionary\b[^>]*>\n", text)
    if not m:
        raise ValueError("Constants.xaml: root element not found")
    return text[:m.end()] + head + text[m.end():]


def constants_xaml_fs(theme: dict, p: dict, key: str) -> str:
    """Constants.xaml of the Fullscreen theme: the vendored Default Fullscreen file with its colors and gradients taken from the tokens.
    Fonts and sizes are NOT mapped: Fullscreen is a couch-distance interface and keeps Playnite's own sizes (18 px and up) and font."""
    pal = palette(p, key)
    t = lambda tok: tk(theme, pal, tok)  # noqa: E731
    cs = cfg_of(p, "Fullscreen")
    text = upstream_text(p, "Constants.xaml", "Fullscreen")
    for k, spec in cs["colors"].items():
        text = sub_once(text, rf'<Color x:Key="{k}">#[0-9A-Fa-f]{{6,8}}</Color>',
                        f'<Color x:Key="{k}">{argb(t(spec["token"]), spec.get("alpha", 255))}</Color> <!-- {spec["token"]} -->', f"<Color> {k}")
    for k, spec in cs["brushes"].items():
        text = sub_once(text, rf'<SolidColorBrush x:Key="{k}" Color="[^"]*" />',
                        f'<SolidColorBrush x:Key="{k}" Color="{argb(t(spec["token"]), spec.get("alpha", 255))}" /> <!-- {spec["token"]} -->', f"<SolidColorBrush> {k}")
    for k, spec in cs["solids"].items():
        a = spec.get("alpha", 255)
        text = sub_once(text, rf'<(Radial|Linear)GradientBrush x:Key="{k}".*?</\1GradientBrush>',
                        f'<SolidColorBrush x:Key="{k}" Color="{argb(t(spec["token"]), a)}" /> <!-- {spec["token"]}{" at alpha " + str(a) if a != 255 else ""} -->',
                        f"gradient {k}", re.S)
    for k, spec in cs["gradients"].items():
        m = re.search(rf'<LinearGradientBrush x:Key="{k}"[^>]*>', text)
        if not m:
            raise ValueError(f"Constants.xaml: expected exactly one gradient {k}, found 0")
        block = re.search(rf'<LinearGradientBrush x:Key="{k}"[^>]*>.*?</LinearGradientBrush>', text, re.S).group(0)
        offs = re.findall(r'<GradientStop Color="#[0-9A-Fa-f]{6,8}" Offset="([\d.]+)"', block)
        if len(offs) != 2:
            raise ValueError(f"Constants.xaml: gradient {k} is expected to have two stops, found {len(offs)}")
        text = sub_once(text, rf'<LinearGradientBrush x:Key="{k}"[^>]*>.*?</LinearGradientBrush>',
                        f'{m.group(0)}\n        <GradientStop Color="{argb(t(spec["token"]), spec["from_alpha"])}" Offset="{offs[0]}"/> <!-- {spec["token"]} -->\n'
                        f'        <GradientStop Color="{argb(t(spec["token"]), spec["to_alpha"])}" Offset="{offs[1]}"/>\n    </LinearGradientBrush>', f"gradient {k}", re.S)
    add = ["", "    <!-- Flatcap additions: brushes for the places where the Default theme hardcodes a color. See docs/mapping.md. -->"]
    for k, spec in cs["added"].items():
        add.append(f'    <SolidColorBrush x:Key="{k}" Color="{argb(t(spec["token"]), spec.get("alpha", 255))}" /> <!-- {spec["token"]} -->')
    text = text.replace("</ResourceDictionary>", "\n".join(add) + "\n</ResourceDictionary>")
    head = (f"    <!-- Flatcap for Playnite {theme['version']} ({p['themes'][key]['name']}, Fullscreen). Generated by scripts/build.py from src/theme.json\n"
            "         (the Flatcap 2.0 core); do not edit by hand. Based on Constants.xaml of Playnite 10.64's Default Fullscreen theme\n"
            "         (MIT, Copyright (c) 2020 Josef Nemec). Keys and structure are the original ones: only colors change. Sizes and fonts are\n"
            "         Playnite's own (a TV interface needs text of 18 px and up). -->\n")
    m = re.search(r"<ResourceDictionary\b[^>]*>\n", text)
    if not m:
        raise ValueError("Constants.xaml: root element not found")
    return text[:m.end()] + head + text[m.end():]


# --- patches of other Default files ----------------------------------------------------------------------------------

def lit(s: str) -> str:
    return re.escape(s)


# (file, [(regex, replacement, expected count, why)]). The replacement is a regex template (\1 etc.). Every file is the vendored upstream
# one; every Flatcap* resource used here is defined in the generated Constants.xaml.
PATCHES: list[tuple[str, list[tuple[str, str, int, str]]]] = [
    ("CustomControls/SidebarItem.xaml", [
        (lit('<Setter Property="Foreground" Value="#dbdbdb" />'), '<Setter Property="Foreground" Value="{DynamicResource TextBrush}" />', 1,
         "sidebar icons were a fixed light grey: unreadable on Daylight"),
        (lit('<Setter Property="Background" Value="OrangeRed" />'), '<Setter Property="Background" Value="{DynamicResource FlatcapBadgeBrush}" />', 1,
         "marker of an empty sidebar item")]),
    ("CustomControls/TopPanelItem.xaml", [
        (lit('<Setter Property="Background" Value="#990a0e1e" />'), '<Setter Property="Background" Value="{DynamicResource FlatcapChipBrush}" />', 1,
         "top panel buttons were a fixed translucent navy"),
        (lit('<Setter Property="Background" Value="OrangeRed" />'), '<Setter Property="Background" Value="{DynamicResource FlatcapBadgeBrush}" />', 1,
         "marker of an empty top panel item")]),
    ("Views/TopPanel.xaml", [
        (lit('<Setter Property="Background" Value="#990a0e1e" />'), '<Setter Property="Background" Value="{DynamicResource FlatcapChipBrush}" />', 1,
         "filter toggle was a fixed translucent navy"),
        (lit('Background="OrangeRed"'), 'Background="{DynamicResource FlatcapBadgeBrush}"', 1, "notification badge"),
        (r'(<TextBlock Text="\{Api Notifications\.Count\}" )FontSize="12"(\s+)Foreground="\{DynamicResource TextBrush\}"',
         r'\1FontSize="{DynamicResource FontSizeSmall}"\2Foreground="{DynamicResource FlatcapBadgeTextBrush}"', 1,
         "badge count: text on the badge color, and not under the core's 13px minimum")]),
    ("Views/SearchView.xaml", [
        (lit('Background="#003f59"'), 'Background="{DynamicResource FlatcapSelectedBrush}"', 2, "hovered and selected search result were a fixed teal"),
        (lit('<Setter Property="Foreground" Value="LightGray" />'), '<Setter Property="Foreground" Value="{DynamicResource TextBrushDarker}" />', 1,
         "description of a search result was a fixed light grey: unreadable on Daylight")]),
    ("DerivedStyles/GridViewItemTemplate.xaml", [
        (lit('Background="#99000000"'), 'Background="{DynamicResource FlatcapScrimBrush}"', 1, "name overlay on a cover: black at 60%"),
        (lit('Background="#AA000000"'), 'Background="{DynamicResource FlatcapScrimBrush}"', 1, "hover and uninstalled overlay on a cover: black at 67%"),
        (lit('TextWrapping="Wrap" Margin="5"'), 'TextWrapping="Wrap" Margin="5" Foreground="{DynamicResource FlatcapScrimTextBrush}"', 1,
         "the name drawn on the overlay must contrast with the overlay, not with the window")]),
    ("DefaultControls/DataGrid.xaml", [
        (lit('Focusable="false" Background="Black"'), 'Focusable="false" Background="{DynamicResource FlatcapSurfaceBrush}"', 1, "data grid body was black"),
        (lit('<TextBlock Foreground="Red"'), '<TextBlock Foreground="{DynamicResource FlatcapDangerBrush}"', 1, "validation mark")]),
    ("DefaultControls/ProgressBar.xaml", [
        (lit('<Setter Property="Foreground" Value="{DynamicResource HoverBrush}"/>'), '<Setter Property="Foreground" Value="{DynamicResource GlyphBrush}"/>', 1,
         "the fill used the hover color, which Flatcap makes a quiet surface; the fill must be the accent")]),
    ("Views/DetailsViewGameOverview.xaml", [
        (lit('<DropShadowEffect ShadowDepth="3" RenderingBias="Quality"/>'), '<DropShadowEffect ShadowDepth="0" Opacity="0" RenderingBias="Quality"/>', 1,
         "the game title had a black drop shadow that smudges the text on a light surface; Flatcap is flat")]),
    ("Views/GridViewGameOverview.xaml", [
        (lit('<DropShadowEffect ShadowDepth="3"/>'), '<DropShadowEffect ShadowDepth="0" Opacity="0"/>', 1, "same drop shadow on the game title of the grid view's side panel")]),
    ("DerivedStyles/PlayButton.xaml", [
        (r'(<Trigger Property="IsMouseOver" Value="true">\s*<Setter Property="Foreground" Value=")\{DynamicResource TextBrush\}(" />)',
         r'\1{DynamicResource TextBrushDark}\2', 1,
         "on hover the text turned to the main text color on the accent fill (1.38:1 in Slate, 1.88:1 in Daylight); it keeps the text-on-accent color")]),
    ("DefaultControls/ListBox.xaml", [
        (r'(<Style\.Triggers>\s*<Trigger Property="Selector\.IsSelected" Value="True">\s*<Setter Property="Foreground" Value="\{DynamicResource TextBrushDark\}" />\s*</Trigger>)',
         '\\1\n            <Trigger Property="IsFocused" Value="True">\n                <Setter Property="Foreground" Value="{DynamicResource TextBrushDark}" />\n            </Trigger>', 1,
         "an item with keyboard focus but no selection shows the accent fill with the normal text color (1.38:1 in Slate, 1.88:1 in Daylight); the text takes the text-on-accent color there too")]),
    ("DerivedStyles/DetailsHyperlink.xaml", [
        (lit('<Setter Property="Foreground" Value="LightGray" />'), '<Setter Property="Foreground" Value="{DynamicResource TextBrushDarker}" />', 1,
         "fixed light grey link text, unreadable on Daylight (no Default 10.64 view uses this style; an add-on may)"),
        (lit('<Setter Property="Foreground" Value="White" />'), '<Setter Property="Foreground" Value="{DynamicResource TextBrush}" />', 1, "same, hovered link: fixed white")]),
    ("Media.xaml", [
        (lit('Foreground="OrangeRed"'), 'Foreground="{DynamicResource FlatcapDangerBrush}"', 2, "exit and remove icons"),
        (lit('Foreground="Yellow"'), 'Foreground="{DynamicResource FlatcapWarningBrush}"', 1, "favorite icon")]),
]


# Fullscreen (Default Fullscreen 10.64). The same rules. A Fullscreen theme is navigated with a controller or the keyboard, so the patches are about two
# things: no hardcoded color (every one becomes a Constants.xaml brush) and focus that stays visible and legible (ComboBox text was Black on a dark fill).
FS_PATCHES: list[tuple[str, list[tuple[str, str, int, str]]]] = [
    ("Views/Main.xaml", [
        (lit('<Setter Property="Foreground" Value="Red" />'), '<Setter Property="Foreground" Value="{DynamicResource FlatcapDangerBrush}" />', 1,
         "critical battery icon was a fixed red"),
        (lit('Foreground="White" FontSize="30" />'), 'Foreground="{DynamicResource TextBrush}" FontSize="30" />', 1, "notifications icon was fixed white"),
        (lit('<TextBlock  Foreground="White"'), '<TextBlock  Foreground="{DynamicResource TextBrush}"', 1, "name of the active filter was fixed white")]),
    ("Views/GameDetails.xaml", [
        (lit('<DropShadowEffect Color="White" BlurRadius="20"'), '<DropShadowEffect Color="{DynamicResource TextColor}" BlurRadius="20"', 1, "glow around the cover was fixed white"),
        (lit('Foreground="White" FontFamily="{DynamicResource FontTitilliumWebBold}"'),
         'Foreground="{DynamicResource TextBrush}" FontFamily="{DynamicResource FontTitilliumWebBold}"', 1, "game title was fixed white"),
        (lit('<DropShadowEffect ShadowDepth="2" Color="Black"'), '<DropShadowEffect ShadowDepth="2" Color="{DynamicResource BlackColor}"', 1,
         "shadow under the game title: same black, now through the kept BlackColor resource"),
        (lit('HtmlFontSize="16"'), 'HtmlFontSize="20"', 1, "the description was the only text under 18 px; at couch distance it is raised to 20")]),
    ("Views/ItemSelection.xaml", [
        (lit('<Setter Property="Background" Value="#AA000000" />'), '<Setter Property="Background" Value="{DynamicResource FlatcapScrimBrush}" />', 2, "dimmed layer behind a selection menu")]),
    ("Views/GameMenu.xaml", [
        (lit('<Setter Property="Background" Value="#AA000000" />'), '<Setter Property="Background" Value="{DynamicResource FlatcapScrimBrush}" />', 1, "dimmed layer behind the game menu")]),
    ("DerivedStyles/ListGameItemTemplate.xaml", [
        (lit('<Border Background="#AA000000" x:Name="BorderDarken"'), '<Border Background="{DynamicResource FlatcapScrimBrush}" x:Name="BorderDarken"', 1,
         "darkening of the cover of an uninstalled game")]),
    ("Views/SettingsMenus.xaml", [
        (lit('BorderThickness="2" BorderBrush="{DynamicResource ControlBackgroundBrush}"'), 'BorderThickness="2" BorderBrush="{DynamicResource SelectionLightBrush}"', 1,
         "the check box outline had the contrast of the fill behind it (1.2:1); it takes the control border color (3:1)"),
        (lit('FontFamily="Marlett" Foreground="White"'), 'FontFamily="Marlett" Foreground="{DynamicResource TextBrush}"', 1, "check mark was fixed white")]),
    ("DefaultControls/CheckBox.xaml", [
        (lit('BorderThickness="2" BorderBrush="{DynamicResource ControlBackgroundBrush}"'), 'BorderThickness="2" BorderBrush="{DynamicResource SelectionLightBrush}"', 1,
         "the check box outline had the contrast of the fill behind it (1.2:1); it takes the control border color (3:1)"),
        (lit('FontFamily="Marlett" Foreground="White"'), 'FontFamily="Marlett" Foreground="{DynamicResource TextBrush}"', 1, "check mark was fixed white")]),
    ("DefaultControls/ComboBox.xaml", [
        (lit('<Setter Property="Foreground" Value="Black" />'), '<Setter Property="Foreground" Value="{DynamicResource TextBrush}" />', 4,
         "focused or hovered combo box and combo box item drew Black text on a dark fill (about 1.1:1 in the Default theme); the text keeps the main text color")]),
    ("DefaultControls/ScrollViewer.xaml", [
        (r'(<Style TargetType="\{x:Type Thumb\}">\s*<Setter Property="Background" Value=")\{DynamicResource ControlBackgroundBrush\}(" />)',
         r'\1{DynamicResource SelectionLightBrush}\2', 1, "the scroll bar thumb had the contrast of its own track (1.2:1); it takes the control border color (3:1)")]),
    ("DefaultControls/Slider.xaml", [
        (lit('<Border Height="6" Background="{DynamicResource ControlBackgroundBrush}" />'), '<Border Height="6" Background="{DynamicResource SelectionLightBrush}" />', 1,
         "the unfilled track of a slider had the contrast of the fill behind it (1.2:1); it takes the control border color (3:1)")]),
    # States the Default theme shows by color alone, with a color that is 1.2 to 1.4:1 from the resting text (a state that cannot be told apart by
    # luminance, and not at all by someone who does not see color): each gets a signal that is not a color (a 3 px underline, or a bolder weight).
    ("CustomControls/FilterPresetSelector.xaml", [
        (r'<Border Background="\{TemplateBinding Background\}"\s+Margin="10,0,10,0">',
         '<Border x:Name="MainBorder" Background="{TemplateBinding Background}" BorderBrush="Transparent" BorderThickness="0,0,0,3"\n                            Margin="10,0,10,0">', 1,
         "the template border gets a name and a transparent 3 px bottom edge (reserved at rest, so nothing moves when it is lit)"),
        (r'(<Trigger Property="IsFocused" Value="True">\s*<Setter Property="Foreground" Value="\{DynamicResource GlyphBrush\}" />)',
         '\\1\n                            <Setter Property="BorderBrush" Value="{DynamicResource SelectionBrush}" TargetName="MainBorder" />', 1,
         "a focused preset in the top bar differed from the others only by its text color (1.38:1); it also gets the accent underline (same brush as every focus outline)")]),
    ("Views/FiltersView.xaml", [
        (r'(<Trigger Property="Tag" Value="\{StaticResource True\}">\s*<Setter Property="Foreground" Value="\{DynamicResource GlyphLightBrush\}" />)(\s*<Setter Property="HorizontalContentAlignment" Value="Stretch" />)',
         '\\1\n                            <Setter Property="FontWeight" Value="Bold" />\n                            <Setter Property="BorderThickness" Value="0,0,0,2" />\n'
         '                            <Setter Property="BorderBrush" Value="{DynamicResource SelectionLightBrush}" />\\2', 1,
         "a filter with an active selection (a filter-panel row) differed from the others only by its text color (1.20:1); it also becomes bold and gets a 2 px underline (3:1)"),
        (r'(<Trigger Property="Tag" Value="\{StaticResource True\}">\s*<Setter Property="Foreground" Value="\{DynamicResource GlyphLightBrush\}" />)(\s*</Trigger>\s*</Style\.Triggers>)',
         '\\1\n                <Setter Property="FontWeight" Value="Bold" />\\2', 1,
         "the same for the filter-panel buttons that carry an active selection: bold in addition to the color")]),
    ("DefaultControls/ToggleButton.xaml", [
        (r'(<Trigger Property="IsChecked" Value="True">\s*<Setter Property="Foreground" Value="\{DynamicResource SelectionBrush\}" />)',
         '\\1\n                            <Setter Property="FontWeight" Value="Bold" />\n                            <Setter Property="BorderThickness" Value="2" />', 1,
         "a checked toggle differed from an unchecked one only by its text color (1.38:1); it also becomes bold and gets a 2 px outline in the control border color (3:1)")]),
]


def patched(p: dict, rel: str, kind: str = "Desktop") -> str:
    text = upstream_text(p, rel, kind)
    for pat, repl, count, _why in dict(patches_of(kind))[rel]:
        text, n = re.subn(pat, repl, text)
        if n != count:
            raise ValueError(f"{rel}: patch {pat[:60]!r} matched {n} times, expected {count}")
    return text


def theme_yaml(theme: dict, p: dict, mode: str) -> str:
    t = p["themes"][mode]
    api = p["playnite"]["desktop_theme_api_version" if t["mode"] == "Desktop" else "fullscreen_theme_api_version"]
    return (f"Id: {t['id']}\nName: {t['name']}\nAuthor: {p['author']}\nVersion: {theme['version']}\nMode: {t['mode']}\n"
            f"ThemeApiVersion: {api}\n")  # no Links: the Default theme has none


def license_txt(theme: dict, p: dict) -> str:
    own = (ROOT / "LICENSE").read_text(encoding="utf-8").strip()
    up = (ROOT / p["upstream"]["license"]).read_text(encoding="utf-8").strip()
    return (f"Flatcap for Playnite {theme['version']}\n\n{own}\n\n"
            "----------------------------------------------------------------------------\n"
            "Portions of the XAML files in this theme are modified copies of files of the Default theme of Playnite\n"
            "(https://github.com/JosefNemec/Playnite, tag 10.64), which is distributed under the license below.\n\n"
            f"{up}\n")


def theme_files(theme: dict, p: dict, mode: str) -> dict[str, bytes]:
    """Relative path (posix) -> bytes, for the theme folder. theme.yaml is first in the .pthm; the order here is the sorted one."""
    kind = kind_of(p, mode)
    files = {"Constants.xaml": constants_xaml(theme, p, mode) if kind == "Desktop" else constants_xaml_fs(theme, p, mode), "LICENSE.txt": license_txt(theme, p)}
    for rel, _ in patches_of(kind):
        files[rel] = patched(p, rel, kind)
    files["theme.yaml"] = theme_yaml(theme, p, mode)
    return {k: v.encode("utf-8") for k, v in sorted(files.items())}


def theme_dir(p: dict, mode: str) -> Path:
    t = p["themes"][mode]
    return ROOT / "themes" / t["mode"] / t["id"]


def pthm_path(theme: dict, p: dict, mode: str) -> Path:
    return ROOT / "dist" / f"{p['themes'][mode]['id']}_{theme['version'].replace('.', '_')}.pthm"


def pthm_members(files: dict[str, bytes]) -> list[tuple[str, bytes]]:
    """What `Toolbox.exe pack` puts in a theme package: theme.yaml first, then the other files."""
    return [("theme.yaml", files["theme.yaml"])] + [(k, v) for k, v in files.items() if k != "theme.yaml"]


def pthm_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in pthm_members(files):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix: the same on every build host
            info.external_attr = 0o644 << 16
            z.writestr(info, data, compresslevel=9)
    return buf.getvalue()


ZIP_FIELDS = ("date_time", "compress_type", "create_system", "create_version", "extract_version", "external_attr", "internal_attr", "flag_bits",
              "extra", "comment", "volume", "file_size", "CRC")


def pthm_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    for mode in MODES:
        path = pthm_path(theme, p, mode)
        rel = path.relative_to(ROOT)
        want = theme_files(theme, p, mode)
        if not path.exists():
            errs.append(f"missing package: {rel} (run --sync)")
            continue
        ref_bytes = pthm_bytes(want)
        with zipfile.ZipFile(io.BytesIO(ref_bytes)) as rz:
            ref = rz.infolist()
        raw = path.read_bytes()
        try:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is not None:
                    errs.append(f"{rel}: corrupt member {z.testzip()}")
                    continue
                infos = z.infolist()
                names = [i.filename for i in infos]
                dups = sorted({n for n in names if names.count(n) > 1})
                if dups:
                    errs.append(f"{rel}: duplicate ZIP member(s) {dups}; a package must hold each file once (run --sync)")
                    continue
                if names != [r.filename for r in ref]:
                    errs.append(f"{rel}: members are {names}, expected {[r.filename for r in ref]}")
                    continue
                for info, r in zip(infos, ref):
                    for f in ZIP_FIELDS:
                        if getattr(info, f) != getattr(r, f):
                            what = {"date_time": "timestamp altered", "external_attr": "permissions altered", "compress_type": "compression altered"}.get(f, "metadata altered")
                            errs.append(f"{rel}: ZIP metadata {f} of {info.filename} is {getattr(info, f)!r}, the build writes {getattr(r, f)!r} ({what}, not deterministic)")
                if z.comment != b"":
                    errs.append(f"{rel}: ZIP has an archive comment")
                if len(raw) != len(ref_bytes) - sum(r.compress_size for r in ref) + sum(i.compress_size for i in infos):
                    errs.append(f"{rel}: the file has bytes outside the ZIP structure (size {len(raw)})")
                for info in infos:
                    if z.read(info.filename) != want[info.filename]:
                        errs.append(f"stale generated file: {rel} member {info.filename} (run --sync)")
        except zipfile.BadZipFile as e:
            errs.append(f"{rel}: not a ZIP ({e})")
            continue
        if raw != ref_bytes and not any(e.startswith(str(rel)) or f"{rel} member" in e for e in errs):
            print(f"note: {rel} differs byte for byte from a local rebuild but has the same members, content and metadata; expected only when this "
                  f"Python's zlib compresses differently", file=sys.stderr)
    return errs


def folder_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    for mode in MODES:
        d = theme_dir(p, mode)
        want = theme_files(theme, p, mode)
        if not d.exists():
            errs.append(f"missing theme folder: {d.relative_to(ROOT)} (run --sync)")
            continue
        have = {x.relative_to(d).as_posix() for x in d.rglob("*") if x.is_file()}
        for extra in sorted(have - set(want)):
            errs.append(f"unexpected file in theme folder: {(d / extra).relative_to(ROOT)}")
        for name, data in want.items():
            f = d / name
            if not f.exists():
                errs.append(f"missing file in theme folder: {f.relative_to(ROOT)} (run --sync)")
            elif f.read_bytes() != data:
                errs.append(f"stale generated file: {f.relative_to(ROOT)} (run --sync)")
    return errs


# --- checks on the generated theme --------------------------------------------------------------------------------------

def parse_simple_yaml(text: str) -> dict[str, str]:
    out = {}
    for ln in text.splitlines():
        m = re.match(r"^([A-Za-z]+):\s*(.*)$", ln)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def yaml_errors(theme: dict, p: dict) -> list[str]:
    errs, seen = [], {}
    for mode in MODES:
        f = theme_dir(p, mode) / "theme.yaml"
        rel = f.relative_to(ROOT)
        if not f.exists():
            continue
        y = parse_simple_yaml(f.read_text(encoding="utf-8"))
        for k in ("Id", "Name", "Author", "Version", "Mode", "ThemeApiVersion"):
            if not y.get(k):
                errs.append(f"{rel}: {k} is missing")
        i = y.get("Id", "")
        if not re.fullmatch(r"[A-Za-z0-9_]+", i):
            errs.append(f"{rel}: Id {i!r} must be letters, digits and underscores only (it becomes the folder name)")
        if i in BUILTIN_IDS:
            errs.append(f"{rel}: Id {i!r} is a built-in theme id")
        if i in seen:
            errs.append(f"{rel}: Id {i!r} is also used by {seen[i]}")
        seen[i] = str(rel)
        if y.get("Mode") not in ("Desktop", "Fullscreen"):
            errs.append(f"{rel}: Mode {y.get('Mode')!r} must be Desktop or Fullscreen")
        elif y.get("Mode") != rel.parts[1]:
            errs.append(f"{rel}: Mode {y.get('Mode')} does not match the folder themes/{rel.parts[1]}")
        if not re.fullmatch(r"\d+\.\d+\.\d+(\.\d+)?", y.get("Version", "")):
            errs.append(f"{rel}: Version {y.get('Version')!r} is not a .NET version string")
        if y.get("Version") != theme["version"]:
            errs.append(f"{rel}: Version {y.get('Version')} differs from the core {theme['version']}")
        tv = y.get("ThemeApiVersion", "")
        if not re.fullmatch(r"\d+\.\d+\.\d+", tv):
            errs.append(f"{rel}: ThemeApiVersion {tv!r} is not a version")
        else:
            k = kind_of(p, mode)
            tmaj, app = int(tv.split(".")[0]), p["playnite"]["desktop_app_theme_api_version" if k == "Desktop" else "fullscreen_app_theme_api_version"]
            if tmaj != int(app.split(".")[0]) or tuple(map(int, tv.split("."))) > tuple(map(int, app.split("."))):
                errs.append(f"{rel}: ThemeApiVersion {tv} is not loadable by a Playnite whose {k} theme API is {app} (same major, not newer)")
        if y.get("Name") != p["themes"][mode]["name"]:
            errs.append(f"{rel}: Name {y.get('Name')!r} differs from src/playnite.json")
    return errs


def xml_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    defined_by_upstream_kind = {}
    for kd in ("Desktop", "Fullscreen"):
        defined_by_upstream_kind[kd] = set()
        for f in upstream_root(p, kd).rglob("*.xaml"):
            defined_by_upstream_kind[kd] |= set(re.findall(r'x:Key="([^"]+)"', f.read_text(encoding="utf-8-sig")))
    for mode in MODES:
        d = theme_dir(p, mode)
        kind = kind_of(p, mode)
        cs = cfg_of(p, kind)
        defined_by_upstream = defined_by_upstream_kind[kind]
        if not d.exists():
            continue
        const_keys = set()
        for f in sorted(d.rglob("*.xaml")):
            rel = f.relative_to(ROOT)
            text = f.read_text(encoding="utf-8")
            try:
                ET.fromstring(text.encode("utf-8"))
            except ET.ParseError as e:
                errs.append(f"{rel}: XAML is not well formed ({e})")
                continue
            keys = re.findall(r'x:Key="([^"]+)"', text)
            dup = {k for k in keys if keys.count(k) > 1}
            if dup:
                errs.append(f"{rel}: duplicated x:Key {sorted(dup)}")
            if f.name == "Constants.xaml" and f.parent == d:
                const_keys = set(keys)
        for f in sorted(d.rglob("*.xaml")):
            rel = f.relative_to(ROOT)
            text = f.read_text(encoding="utf-8")
            for k in sorted(set(re.findall(r"\{(?:Dynamic|Static)Resource (Flatcap\w+)\}", text))):
                if k not in const_keys:
                    errs.append(f"{rel}: resource {k} is used but not defined in this theme's Constants.xaml")
            if f.name == "Constants.xaml" and f.parent == d:
                continue
            errs += color_errors(rel, text)
            # Resources that Playnite's own Default files define (styles, fonts) or the app supplies (LOC*) are not vendored here: a patch may
            # only use ones the original file already used, so it cannot introduce an unresolved name
            orig_rel = f.relative_to(d).as_posix()
            orig = upstream_text(p, orig_rel, kind) if (upstream_root(p, kind) / orig_rel).exists() else ""  # an extra file is reported by folder_errors
            for k in sorted(set(re.findall(r"\{DynamicResource (\w+)\}", text)) - const_keys - defined_by_upstream - set(re.findall(r"\{DynamicResource (\w+)\}", orig))):
                errs.append(f"{rel}: resource {k} is not defined in Constants.xaml and the original file does not use it")
        cf = d / "Constants.xaml"
        if cf.exists():
            ctext = cf.read_text(encoding="utf-8")
            mapped = set(cs["colors"]) | set(cs["brushes"]) | set(cs["keep_literal"])
            for m in re.finditer(r'x:Key="(\w+)"[^>]*?(?:Color="(#[0-9A-Fa-f]{6,8})"|>(#[0-9A-Fa-f]{6,8})<)', ctext):
                key = m.group(1)
                if key not in mapped and key not in cs["added"] and key not in cs["gradients_replaced"]:
                    errs.append(f"{cf.relative_to(ROOT)}: {key} holds a color literal that no Flatcap token maps")
            for m in re.finditer(r'<GradientStop Color="(#[0-9A-Fa-f]{6,8})"', ctext):
                pass
            up = upstream_text(p, "Constants.xaml", kind)
            up_keys = re.findall(r'x:Key="(\w+)"', up)
            for k in up_keys:
                if f'x:Key="{k}"' not in ctext:
                    errs.append(f"{cf.relative_to(ROOT)}: upstream key {k} was dropped")
            if kind == "Fullscreen":
                errs += fs_size_errors(d, ctext)
        if kind == "Fullscreen":
            for f in sorted(d.rglob("*.xaml")):
                if f.parent != d or f.name != "Constants.xaml":
                    errs += fs_size_errors(d, f.read_text(encoding="utf-8"), f)
    return errs


def fs_size_errors(d: Path, text: str, f: Path | None = None) -> list[str]:
    """Fullscreen is read from a couch: no text under FS_MIN_TEXT px. Looks at FontSize and HtmlFontSize literals and at the FontSize constants."""
    rel = (f or (d / "Constants.xaml")).relative_to(ROOT)
    errs = []
    # the one exemption: the decorative dot (U+25CF) under the selected top bar preset is a shape, not text anyone reads
    text = re.sub(r'<TextBlock\b[^>]*\bText="&#x25CF;"[^>]*>', "", text)
    for m in re.finditer(r'\b(?:Html)?FontSize="(\d+(?:\.\d+)?)"|<Setter\s+Property="(?:Html)?FontSize"\s+Value="(\d+(?:\.\d+)?)"', text):
        size = m.group(1) or m.group(2)
        if float(size) < FS_MIN_TEXT:
            errs.append(f"{rel}: text size {size} px is under the {FS_MIN_TEXT} px minimum of a Fullscreen theme")
    for m in re.finditer(r'<sys:Double x:Key="(FontSize\w*)">(\d+(?:\.\d+)?)</sys:Double>', text):
        if float(m.group(2)) < FS_MIN_TEXT:
            errs.append(f"{rel}: {m.group(1)} is {m.group(2)} px, under the {FS_MIN_TEXT} px minimum of a Fullscreen theme")
    return errs


def color_errors(rel: Path, text: str) -> list[str]:
    """Color literals in a shipped XAML file (comments included: a commented-out literal is still a literal waiting to come back).
    Every color must come from a Constants.xaml brush. Flagged: hex of 3 to 8 digits, sc#, a name of System.Windows.Media.Colors in any
    attribute value or element text (Setter Value included, Colors.X references too), and SystemColors. Allowed: Transparent (it paints
    nothing) and, inside an opacity mask only, Black (a mask decides opacity, it never paints a color)."""
    errs = []
    for m in re.finditer(r"<(\w+\.\w*OpacityMask)>(.*?)</\1>", text, flags=re.S):
        for lit_ in sorted(set(HEX_LITERAL.findall(m.group(2)))):
            errs.append(f"{rel}: color literal {lit_} in an OpacityMask (only Black and Transparent are allowed there)")
        for v in ATTR_VALUE.findall(m.group(2)):
            if v.strip().lower() in WPF_COLORS and v.strip().lower() not in MASK_NAMED:
                errs.append(f"{rel}: named color {v.strip()!r} in an OpacityMask (only Black and Transparent are allowed there)")
    text = re.sub(r"<(\w+\.\w*OpacityMask)>.*?</\1>", "", text, flags=re.S)
    plain = re.sub(r"&#x?[0-9A-Fa-f]+;", "", text)
    for lit_ in sorted(set(HEX_LITERAL.findall(plain))):
        errs.append(f"{rel}: color literal {lit_} (use a Constants.xaml brush, which comes from a Flatcap token)")
    for lit_ in sorted(set(re.findall(r"\bsc#[-\d.,\s]+", plain))):
        errs.append(f"{rel}: color literal {lit_.strip()} (scRGB; use a Constants.xaml brush)")
    values = ATTR_VALUE.findall(plain) + re.findall(r">\s*([^<>\s][^<>]*?)\s*<", plain)
    named = {v.strip() for v in values if v.strip().lower() in WPF_COLORS and v.strip().lower() not in ALLOWED_NAMED}
    named |= {n for v in values for n in re.findall(r"\bColors\.([A-Za-z]+)\b", v) if n.lower() in WPF_COLORS and n.lower() not in ALLOWED_NAMED}
    for name in sorted(named):
        errs.append(f"{rel}: named color {name!r} (use a Constants.xaml brush)")
    if re.search(r"\bSystemColors\b", plain):
        errs.append(f"{rel}: SystemColors (a Windows system color follows the user's Windows theme, not the Flatcap tokens; use a Constants.xaml brush)")
    return errs


def private_patterns() -> tuple[list[tuple[re.Pattern, str]], list[str]]:
    """Names of the maintainer's own machines, domains and users: kept out of the repository, in a local file that git ignores
    (.private-patterns, or the file FLATCAP_PRIVATE_PATTERNS points to). One regular expression per line, # starts a comment."""
    env = os.environ.get("FLATCAP_PRIVATE_PATTERNS")
    path = Path(env) if env else PRIVATE_FILE
    if not path.is_file():
        return [], ([f"FLATCAP_PRIVATE_PATTERNS points to a file that does not exist ({path.name})"] if env else [])
    pats, errs = [], []
    for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            try:
                pats.append((re.compile(ln, re.I), f"a private pattern (line {n} of {path.name})"))
            except re.error as e:
                errs.append(f"{path.name} line {n}: not a valid regular expression ({e})")
    return pats, errs


def core_sha256() -> str:
    return hashlib.sha256(THEME.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # line endings must not matter on a Windows checkout


def core_errors(p: dict) -> list[str]:
    pin = p.get("core", {}).get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", pin):
        return ["src/playnite.json: core.sha256 (the pinned SHA-256 of src/theme.json) is missing or not a SHA-256"]
    got = core_sha256()
    if got != pin:
        return [f"src/theme.json differs from the pinned core copy (SHA-256 {got}, src/playnite.json pins {pin}). A core change is taken on "
                f"purpose: copy the file from {p['core']['repo']}, run --pin-core, then --sync"]
    return []


def token_errors(theme: dict, p: dict) -> list[str]:
    errs = core_errors(p)
    cs = p["constants"]
    fcs = cfg_of(p, "Fullscreen")
    for m in MODES:
        t = theme["themes"][palette(p, m)]
        need = {s["token"] for grp in ("colors", "brushes", "added") for s in cs[grp].values()} | {x for a, b, c, d in [pr[:4] for pr in pairs_raw()] for x in (b, c)}
        if kind_of(p, m) == "Fullscreen":
            need = {s["token"] for grp in ("colors", "brushes", "solids", "gradients", "added") for s in fcs[grp].values()}
        for tok in sorted(need):
            if tok not in t:
                errs.append(f"{m}: token {tok} is used by the mapping but not defined in src/theme.json")
            elif not C.is_hex(t[tok]):
                errs.append(f"{m}: token {tok} is not a hex color ({t[tok]!r})")
    for tok in set(cs["typography"].values()):
        if tok not in theme["typography"]:
            errs.append(f"typography token {tok} is not defined in src/theme.json")
    for tok in set(cs["metrics"].values()):
        if tok not in theme["metrics"]:
            errs.append(f"metric token {tok} is not defined in src/theme.json")
    if theme.get("version") != "2.0.0":
        errs.append(f"src/theme.json version is {theme.get('version')}, expected 2.0.0")
    if p.get("version") != theme.get("version"):
        errs.append(f"src/playnite.json version {p.get('version')} differs from the core {theme.get('version')}")
    ids = [p["themes"][m]["id"] for m in MODES]
    if len(set(ids)) != len(ids):
        errs.append("two themes share an id")
    return errs


# --- contrast ----------------------------------------------------------------------------------------------------------

SURFACES = [("canvas", "window, details, filter and side panels"), ("surface", "grid items, data grid"),
            ("raised", "buttons, popups, menus, tooltips, top panel buttons"), ("hover", "hovered list rows, menu items, sidebar items"),
            ("selected", "search results (hovered, selected)")]


def pairs_raw() -> list[tuple]:
    """(label, fg token, bg token, target, group, fg opacity)."""
    out = []
    for s, where in SURFACES:
        out.append((f"text.primary on bg.{s} ({where})", "text.primary", f"bg.{s}", 7.0, "text", 1.0))
    for s, where in SURFACES:
        out.append((f"text.secondary on bg.{s} ({where})", "text.secondary", f"bg.{s}", 5.0, "text", 1.0))
    for s, where in SURFACES:
        out.append((f"accent.fill on bg.{s} (button text, icons, links, selection border)", "accent.fill", f"bg.{s}", 4.5, "text", 1.0))
    out.append(("accent.on on accent.fill (selected rows, Play button: TextBrushDark on GlyphBrush)", "accent.on", "accent.fill", 4.5, "fill", 1.0))
    out.append(("accent.on on danger.fg (notification badge count)", "accent.on", "danger.fg", 4.5, "fill", 1.0))
    for s in ("canvas", "surface", "raised"):
        out.append((f"border.control on bg.{s} (control borders, scrollbar thumb)", "border.control", f"bg.{s}", 3.0, "outline", 1.0))
    for tok in ("success.fg", "warning.fg", "danger.fg"):
        for s in ("canvas", "surface"):
            out.append((f"{tok} on bg.{s} (game score, warning text, favorite and exit icons)", tok, f"bg.{s}", 4.5, "text", 1.0))
    out.append(("border.subtle on bg.canvas (panel separators, popup borders; decorative, report only)", "border.subtle", "bg.canvas", 1.0, "report", 1.0))
    out.append(("border.subtle on bg.raised (popup border on its own surface; decorative, report only)", "border.subtle", "bg.raised", 1.0, "report", 1.0))
    return out


def scrim_rows(theme: dict, p: dict) -> list[dict]:
    """Text and icons on the cover overlay, worst case: the overlay over a pure white and over a pure black cover."""
    rows = []
    alpha = p["constants"]["added"]["FlatcapScrimBrush"]["alpha"] / 255
    for m in DESKTOP:
        t = theme["themes"][m]
        scrim = C.parse(t["bg.canvas"])
        for fg_tok, target, what in (("text.primary", 4.5, "cover name"), ("accent.fill", 3.0, "Play and Info icons")):
            worst = None
            for cover, cname in (((1.0, 1.0, 1.0, 1.0), "white"), ((0.0, 0.0, 0.0, 1.0), "black")):
                flat = C.over((*scrim[:3], alpha), cover)
                fg = C.parse(t["text.primary" if fg_tok == "text.primary" else fg_tok])
                r = C.contrast(fg, flat)
                if worst is None or r < worst[0]:
                    worst = (r, cname)
            rows.append({"mode": m, "label": f"{fg_tok} on the cover overlay, worst case over a pure {worst[1]} cover ({what})", "fg": t[fg_tok],
                         "bg": "overlay", "target": target, "group": "text" if target == 4.5 else "outline", "ratio": worst[0]})
    return rows


def ratio(fg: str, bg: str, op: float = 1.0) -> float:
    f, b = C.parse(fg), C.parse(bg)
    if op < 1.0:
        f = C.over((*f[:3], op), b)
    return C.contrast(f, b)


# States whose text and fill are chosen by the XAML, not by the token pairs above. The foreground and background resources are READ from the
# shipped file (the vendored one with the patches) and resolved to tokens through src/playnite.json, so a state that keeps the wrong text color
# fails here: the pair "accent.on on accent.fill" passing says nothing about a state that draws TextBrush on GlyphBrush.
# (label, file, regex of the foreground resource, regex of the fill resource, target)
STATE_CONTRACTS = [
    ("Play button, rest", "DerivedStyles/PlayButton.xaml", r'<Setter Property="Foreground" Value="\{DynamicResource (\w+)\}" />',
     r'<Setter Property="Background" Value="\{DynamicResource (\w+)\}" />', 4.5),
    ("Play button, hover", "DerivedStyles/PlayButton.xaml",
     r'<Trigger Property="IsMouseOver" Value="true">\s*<Setter Property="Foreground" Value="\{DynamicResource (\w+)\}" />',
     r'<Setter Property="Background" Value="\{DynamicResource (\w+)\}" />', 4.5),
    ("List item, selected", "DefaultControls/ListBox.xaml",
     r'<Style\.Triggers>\s*<Trigger Property="Selector\.IsSelected" Value="True">\s*<Setter Property="Foreground" Value="\{DynamicResource (\w+)\}" />',
     r'x:Name="SelectedRectangle"[^>]*?Background="\{DynamicResource (\w+)\}"', 4.5),
    ("List item, keyboard focus without selection", "DefaultControls/ListBox.xaml",
     r'<Trigger Property="IsFocused" Value="True">\s*<Setter Property="Foreground" Value="\{DynamicResource (\w+)\}" />',
     r'x:Name="SelectedRectangle"[^>]*?Background="\{DynamicResource (\w+)\}"', 4.5),
]


def resource_token(p: dict, key: str) -> str:
    """The Flatcap token behind a Playnite brush resource, through the mapping in src/playnite.json."""
    cs = p["constants"]
    for grp in ("brushes", "added"):
        if key in cs[grp]:
            return cs[grp][key]["token"]
    m = re.fullmatch(r"(\w+?)Brush(Dark|Darker)?", key)  # TextBrush -> TextColor, TextBrushDark -> TextColorDark
    if m and f"{m.group(1)}Color{m.group(2) or ''}" in cs["colors"]:
        return cs["colors"][f"{m.group(1)}Color{m.group(2) or ''}"]["token"]
    raise KeyError(f"resource {key} has no token in src/playnite.json")


def state_rows(theme: dict, p: dict) -> tuple[list[dict], list[str]]:
    out, errs = [], []
    for label, rel, fg_re, bg_re, target in STATE_CONTRACTS:
        text = patched(p, rel) if rel in dict(PATCHES) else upstream_text(p, rel)
        fg, bg = re.search(fg_re, text), re.search(bg_re, text)
        if not fg or not bg:
            errs.append(f"state '{label}' ({rel}): no {'foreground' if not fg else 'fill'} resource found; the state keeps the text color of the control "
                        f"over a fill (contrast not guaranteed)")
            continue
        try:
            ft, bt = resource_token(p, fg.group(1)), resource_token(p, bg.group(1))
        except KeyError as e:
            errs.append(f"state '{label}' ({rel}): {e}")
            continue
        for m in DESKTOP:
            a, b = tk(theme, m, ft), tk(theme, m, bt)
            out.append({"mode": m, "label": f"{label}: {ft} on {bt} ({fg.group(1)} on {bg.group(1)}, read from {rel})", "fg": a, "bg": b,
                        "target": target, "group": "text", "ratio": ratio(a, b)})
    return out, errs


def rows(theme: dict, p: dict) -> list[dict]:
    """The Desktop rows (every Desktop theme). The Fullscreen rows are fs_rows()."""
    out = []
    for m in DESKTOP:
        for label, fg, bg, target, group, op in pairs_raw():
            a, b = tk(theme, m, fg), tk(theme, m, bg)
            out.append({"mode": m, "label": label, "fg": a, "bg": b, "target": target, "group": group, "ratio": ratio(a, b, op)})
    return out + scrim_rows(theme, p) + state_rows(theme, p)[0]


def contrast_errors(theme: dict, p: dict) -> list[str]:
    frows, ferrs = fs_rows_and_errors(theme, p)
    return ([f"{r['mode']}: {r['label']} = {r['ratio']:.2f} < {r['target']} (contrast target missed)" for r in rows(theme, p) + frows if r["ratio"] < r["target"]]
            + state_rows(theme, p)[1] + ferrs)


# --- Fullscreen contrast ------------------------------------------------------------------------------------------------
# Fullscreen is driven by a controller or the keyboard and read from a couch, so besides the text pairs it checks what the focus looks like.
# Every pair is expressed with Playnite RESOURCES (TextBrush, ControlBackgroundDarkBrush...) and resolved to tokens through the mapping in
# src/playnite.json, so a mapping that gives a surface the wrong token fails here. A surface that is translucent (the top and bottom bars,
# the game details panel) lies over the game's background art: it is checked over a pure white and a pure black picture, the worst cases.
FS_SURFACES = [("MainBackgourndBrush", "main background"), ("OverlayMenuBackgroundBrush", "menus and dialogs"),
               ("ControlBackgroundBrush", "text boxes and filter fields"), ("ControlBackgroundDarkBrush", "focused or hovered controls, game titles on covers, tooltips"),
               ("TopBarBackgroundBrush", "top bar, over the background art"), ("BottomBarBackgroundBrush", "bottom bar (button legend), over the art"),
               ("GameDetailsBackgroundBrush", "game details panel, over the art")]
# (foreground resource, what it draws, [(surface resource, target, group)], category)
FS_PAIRS = [
    ("TextBrush", "labels, titles, description text",
     [("MainBackgourndBrush", 7.0, "text"), ("OverlayMenuBackgroundBrush", 7.0, "text"), ("ControlBackgroundBrush", 7.0, "text"),
      ("ControlBackgroundDarkBrush", 7.0, "text"), ("TopBarBackgroundBrush", 4.5, "text"), ("BottomBarBackgroundBrush", 4.5, "text"),
      ("GameDetailsBackgroundBrush", 4.5, "text")], "Main text"),
    ("GlyphBrush", "accent: description links, icons, hover text",
     [("MainBackgourndBrush", 4.5, "text"), ("OverlayMenuBackgroundBrush", 4.5, "text"), ("ControlBackgroundBrush", 4.5, "text"),
      ("ControlBackgroundDarkBrush", 4.5, "text"), ("TopBarBackgroundBrush", 3.0, "outline"), ("BottomBarBackgroundBrush", 3.0, "outline"),
      ("GameDetailsBackgroundBrush", 4.5, "text")], "Accent"),
    ("GlyphLightBrush", "light accent: icons, hover text in lists",
     [("MainBackgourndBrush", 4.5, "text"), ("OverlayMenuBackgroundBrush", 4.5, "text"), ("ControlBackgroundBrush", 4.5, "text"),
      ("ControlBackgroundDarkBrush", 4.5, "text"), ("TopBarBackgroundBrush", 3.0, "outline"), ("BottomBarBackgroundBrush", 3.0, "outline"),
      ("GameDetailsBackgroundBrush", 3.0, "outline")], "Light accent"),
    ("SelectionLightBrush", "outlines of fields and check boxes, scroll thumb, slider track",
     [("MainBackgourndBrush", 3.0, "outline"), ("OverlayMenuBackgroundBrush", 3.0, "outline"), ("ControlBackgroundBrush", 3.0, "outline"),
      ("ControlBackgroundDarkBrush", 3.0, "outline")], "Control borders"),
    ("WarningBrush", "warning text",
     [("MainBackgourndBrush", 4.5, "text"), ("OverlayMenuBackgroundBrush", 4.5, "text"), ("ControlBackgroundBrush", 4.5, "text"),
      ("ControlBackgroundDarkBrush", 4.5, "text")], "Status"),
    ("FlatcapDangerBrush", "critical battery icon", [("TopBarBackgroundBrush", 3.0, "outline")], "Status"),
    ("TextBrushDark", "disabled controls (WCAG exempts inactive components; Playnite also draws them at 50% opacity); report only",
     [("MainBackgourndBrush", 1.0, "report"), ("OverlayMenuBackgroundBrush", 1.0, "report")], "Disabled"),
]
_BR = r'\{DynamicResource (\w+)\}'
FS_BTN_FG = r'<Style TargetType="Button">.*?<Setter Property="Foreground" Value="' + _BR + '"'


def _trig(prop: str, setter: str = "Background") -> str:
    return rf'<Trigger Property="{prop}" Value="True">\s*<Setter Property="{setter}" Value="{_BR}"'


# States whose text and fill are chosen by the XAML. (label, file, foreground regex, fill regex, target, regex flags, category)
# Read from the shipped (patched) file; the first group of each regex is a resource name. A foreground that is not a resource (a literal such
# as Foreground="Black") does not match and is reported: that is the defect these contracts exist for.
FS_STATES = [
    ("Button, keyboard focus", "DefaultControls/Button.xaml", FS_BTN_FG, _trig("IsFocused"), 4.5, re.S, "States"),
    ("Button, hover", "DefaultControls/Button.xaml", FS_BTN_FG, _trig("IsMouseOver"), 4.5, re.S, "States"),
    ("Toggle button, keyboard focus", "DefaultControls/ToggleButton.xaml", FS_BTN_FG.replace('"Button"', '"ToggleButton"'), _trig("IsFocused"), 4.5, re.S, "States"),
    ("Toggle button, checked and focused", "DefaultControls/ToggleButton.xaml", _trig("IsChecked", "Foreground"), _trig("IsFocused"), 4.5, re.S, "States"),
    ("Combo box, keyboard focus", "DefaultControls/ComboBox.xaml",
     r'<Trigger Property="IsFocused" Value="True">\s*<Setter Property="Background" Value="' + _BR + r'" />\s*<Setter Property="Foreground" Value="' + _BR + '"', _trig("IsFocused"), 4.5, re.S, "States"),
    ("Combo box, hover", "DefaultControls/ComboBox.xaml",
     r'<Trigger Property="IsMouseOver" Value="True">\s*<Setter Property="Background" Value="' + _BR + r'" />\s*<Setter Property="Foreground" Value="' + _BR + '"', _trig("IsMouseOver"), 4.5, re.S, "States"),
    ("Combo box item, keyboard focus", "DefaultControls/ComboBox.xaml",
     r'<ControlTemplate TargetType="\{x:Type ComboBoxItem\}">.*?<Trigger Property="IsFocused" Value="True">\s*<Setter Property="Background" Value="' + _BR + r'" />\s*<Setter Property="Foreground" Value="' + _BR + '"',
     r'<ControlTemplate TargetType="\{x:Type ComboBoxItem\}">.*?' + _trig("IsFocused"), 4.5, re.S, "States"),
    ("Combo box item, hover", "DefaultControls/ComboBox.xaml",
     r'<ControlTemplate TargetType="\{x:Type ComboBoxItem\}">.*?<Trigger Property="IsMouseOver" Value="True">\s*<Setter Property="Background" Value="' + _BR + r'" />\s*<Setter Property="Foreground" Value="' + _BR + '"',
     r'<ControlTemplate TargetType="\{x:Type ComboBoxItem\}">.*?' + _trig("IsMouseOver"), 4.5, re.S, "States"),
    ("Text box, rest", "DefaultControls/TextBox.xaml", r'<Setter Property="Foreground" Value="' + _BR + '"', r'<Setter Property="Background" Value="' + _BR + '"', 4.5, 0, "States"),
    ("Text box, keyboard focus", "DefaultControls/TextBox.xaml", r'<Setter Property="Foreground" Value="' + _BR + '"', _trig("IsFocused"), 4.5, 0, "States"),
    ("Check box, keyboard focus", "DefaultControls/CheckBox.xaml", r'<Setter Property="Foreground" Value="' + _BR + '"', _trig("IsFocused"), 4.5, 0, "States"),
    ("Check mark in a check box (graphic)", "DefaultControls/CheckBox.xaml", r'FontFamily="Marlett" Foreground="' + _BR + '"', r'<Border Background="' + _BR + '"', 3.0, 0, "States"),
    ("Check mark in the settings list (graphic)", "Views/SettingsMenus.xaml", r'FontFamily="Marlett" Foreground="' + _BR + '"', r'<Border Background="' + _BR + '"', 3.0, 0, "States"),
    ("Filter item, keyboard focus", "Views/FiltersView.xaml", r'<Setter Property="Foreground" Value="' + _BR + '"', _trig("IsFocused"), 4.5, 0, "States"),
    ("Tool tip", "DefaultControls/ToolTip.xaml", r'<Setter Property="Foreground" Value="' + _BR + '"', r'<Setter Property="Background" Value="' + _BR + '"', 4.5, 0, "States"),
    ("Game title on a cover", "DerivedStyles/ListGameItemTemplate.xaml", r'(TextBlockBaseStyle)', r'Background="' + _BR + r'"/>', 4.5, 0, "States"),
]
# What marks the focus. (label, file, regex of the resource the focus outline is drawn with, regex that proves the focused state shows it)
# Every one is a 3 to 5 px outline (a shape change, not a color change alone) and must hold 3:1 against every surface it can sit on.
_VIS = r'<Trigger Property="IsFocused" Value="True">(?:(?!</Trigger>).)*?<Setter Property="Visibility" Value="Visible" TargetName="{n}"'
_BF = r'x:Name="BorderFocus"[^>]*?BorderBrush="' + _BR + '"'
FS_FOCUS = [
    ("Button", "DefaultControls/Button.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Toggle button", "DefaultControls/ToggleButton.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Check box", "DefaultControls/CheckBox.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Combo box", "DefaultControls/ComboBox.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Text box", "DefaultControls/TextBox.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Slider", "DefaultControls/Slider.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Filter item", "Views/FiltersView.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Settings list item", "Views/SettingsMenus.xaml", _BF, _VIS.format(n="BorderFocus")),
    ("Top bar button", "DerivedStyles/ButtonTopMenu.xaml", r'<Trigger Property="IsFocused" Value="True">\s*<Setter Property="BorderBrush" Value="' + _BR + r'" TargetName="MainBorder"',
     r'<Border Background="\{TemplateBinding Background\}"\s*BorderBrush="Transparent" BorderThickness="3"\s*x:Name="MainBorder"'),
    ("Top bar preset", "CustomControls/FilterPresetSelector.xaml", r'<Trigger Property="IsFocused" Value="True">\s*<Setter Property="Foreground"[^>]*/>\s*<Setter Property="BorderBrush" Value="' + _BR + r'" TargetName="MainBorder"',
     r'<Border x:Name="MainBorder" Background="\{TemplateBinding Background\}" BorderBrush="Transparent" BorderThickness="0,0,0,3"'),
    ("Game cover", "DerivedStyles/ListGameItemStyle.xaml", r'x:Name="MainBorder" BorderThickness="5" BorderBrush="' + _BR + '"', _VIS.format(n="MainBorder")),
]


# States that Default shows by a change of text color alone. A color that is under 3:1 from the resting one cannot be told apart by luminance, and not
# at all without color vision, so such a state must also carry a signal that is not a color. (label, file, regex of the resting foreground (group 1),
# regex of the trigger of the state (named group `body` = its setters)). Colors are read from the shipped file; a state whose color is 3:1 or more from
# the resting one passes by contrast, any other must have one of the setters in NON_COLOR_CUE in its trigger.
NON_COLOR_CUE = (r'<Setter Property="(?:FontWeight|FontStyle|TextDecorations|BorderThickness)"'
                 r'|<Setter Property="BorderBrush"[^>]*TargetName="MainBorder"')  # a weight, a style, an underline or an outline
FS_CUES = [
    ("Top bar preset, keyboard focus", "CustomControls/FilterPresetSelector.xaml",
     r'<Style x:Key="ItemFilterQuickPreset".*?<Setter Property="Foreground" Value="' + _BR + '"',
     r'<ControlTemplate TargetType="CheckBoxEx">.*?<Trigger Property="IsFocused" Value="True">(?P<body>.*?)</Trigger>'),
    ("Filter row with an active selection", "Views/FiltersView.xaml",
     r'<Style x:Key="FilterPanelNagivationButton".*?<Setter Property="Foreground" Value="' + _BR + '"',
     r'<Style x:Key="FilterPanelNagivationButton".*?<Trigger Property="Tag" Value="\{StaticResource True\}">(?P<body>.*?)</Trigger>'),
    ("Filter button with an active selection", "Views/FiltersView.xaml",
     r'<Style x:Key="FilterPanelButtonEx".*?<Setter Property="Foreground" Value="' + _BR + '"',
     r'<Style x:Key="FilterPanelButtonEx".*?<Trigger Property="Tag" Value="\{StaticResource True\}">(?P<body>.*?)</Trigger>'),
    ("Toggle button, checked", "DefaultControls/ToggleButton.xaml",
     r'<Style TargetType="ToggleButton">.*?<Setter Property="Foreground" Value="' + _BR + '"',
     r'<Trigger Property="IsChecked" Value="True">(?P<body>.*?)</Trigger>'),
]


def fs_brush_colors(p: dict, key: str) -> list[tuple[str, int]]:
    """[(token, alpha)] behind a Fullscreen brush resource, through the mapping in src/playnite.json (a gradient gives one entry per stop)."""
    cs = cfg_of(p, "Fullscreen")
    for grp in ("brushes", "added", "solids"):
        if key in cs[grp]:
            return [(cs[grp][key]["token"], cs[grp][key].get("alpha", 255))]
    if key in cs["gradients"]:
        return [(cs["gradients"][key]["token"], cs["gradients"][key]["to_alpha"])]  # the opaque end of the gradient, where the text is
    up = upstream_text(p, "Constants.xaml", "Fullscreen")
    m = re.search(rf'<SolidColorBrush x:Key="{key}" Color="\{{DynamicResource (\w+)\}}"', up)
    names = [m.group(1)] if m else []
    if not names:
        g = re.search(rf'<(?:Linear|Radial)GradientBrush x:Key="{key}".*?</(?:Linear|Radial)GradientBrush>', up, re.S)
        names = re.findall(r'Color="\{DynamicResource (\w+)\}"', g.group(0)) if g else []
    if not names:
        raise KeyError(f"resource {key} is not a Fullscreen brush src/playnite.json maps")
    out = []
    for n in names:
        if n not in cs["colors"]:
            raise KeyError(f"resource {key} uses color {n}, which has no token in src/playnite.json")
        out.append((cs["colors"][n]["token"], cs["colors"][n].get("alpha", 255)))
    return out


def fs_flat(theme: dict, p: dict, key: str) -> list:
    """The opaque colors (RGBA) a Fullscreen surface can show: one when it is opaque, two (over white and over black art) when it is not."""
    pal = tk_palette(theme, p)
    tok, alpha = fs_brush_colors(p, key)[0]
    c = C.parse(pal[tok])
    if alpha >= 255:
        return [c]
    return [C.over((*c[:3], alpha / 255), (1.0, 1.0, 1.0, 1.0)), C.over((*c[:3], alpha / 255), (0.0, 0.0, 0.0, 1.0))]


def tk_palette(theme: dict, p: dict) -> dict:
    return theme["themes"][palette(p, FULLSCREEN[0])]


def fs_rows_and_errors(theme: dict, p: dict) -> tuple[list[dict], list[str]]:
    out, errs = [], []
    pal = tk_palette(theme, p)
    where = dict(FS_SURFACES)
    try:
        flats = {k: fs_flat(theme, p, k) for k, _ in FS_SURFACES}
    except KeyError as e:
        return [], [f"Fullscreen surface: {e}"]
    def worst(fg: str, bgs: list) -> tuple[float, str]:
        return min((C.contrast(C.parse(fg), b), C.fmt(b)) for b in bgs)
    for fg_key, what, specs, cat in FS_PAIRS:
        try:
            fgs = [pal[tok] for tok, _a in fs_brush_colors(p, fg_key)]
        except KeyError as e:
            errs.append(f"Fullscreen pair {fg_key}: {e}")
            continue
        for surf, target, group in specs:
            r, bgc = min(worst(f, flats[surf]) for f in fgs)
            out.append({"mode": "fullscreen", "label": f"{fg_key} ({what}) on {surf} ({where[surf]})", "fg": fgs[0], "bg": bgc, "target": target, "group": group,
                        "ratio": r, "cat": cat})
    for label, rel, fg_re, bg_re, target, flags, cat in FS_STATES:
        text = patched(p, rel, "Fullscreen") if rel in dict(FS_PATCHES) else upstream_text(p, rel, "Fullscreen")
        fg, bg = re.search(fg_re, text, flags), re.search(bg_re, text, flags)
        if not fg or not bg:
            errs.append(f"state '{label}' ({rel}): no {'foreground' if not fg else 'fill'} resource found; the state keeps a text color that is not a theme resource "
                        f"(contrast not guaranteed)")
            continue
        fgkey = fg.group(fg.lastindex)  # the foreground is the last group of its regex (the combo box ones capture the fill first)
        bgkey = bg.group(bg.lastindex)
        try:
            if fgkey == "TextBlockBaseStyle":
                fgkey = "TextBrush"  # the label is drawn with the base text style, which sets TextBrush (checked in Constants.xaml below)
                if not re.search(r'<Style x:Key="TextBlockBaseStyle".*?Property="Foreground" Value="\{DynamicResource TextBrush\}"', upstream_text(p, "Constants.xaml", "Fullscreen"), re.S):
                    errs.append(f"state '{label}': TextBlockBaseStyle no longer sets TextBrush")
            fgs = [pal[tok] for tok, _a in fs_brush_colors(p, fgkey)]
            bgs = fs_flat(theme, p, bgkey)
        except KeyError as e:
            errs.append(f"state '{label}' ({rel}): {e}")
            continue
        r, bgc = min(worst(f, bgs) for f in fgs)
        out.append({"mode": "fullscreen", "label": f"{label}: {fgkey} on {bgkey} (read from {rel})", "fg": fgs[0], "bg": bgc, "target": target, "group": "text" if target == 4.5 else "outline",
                    "ratio": r, "cat": cat})
    for label, rel, brush_re, show_re in FS_FOCUS:
        text = patched(p, rel, "Fullscreen") if rel in dict(FS_PATCHES) else upstream_text(p, rel, "Fullscreen")
        b, s = re.search(brush_re, text, re.S), re.search(show_re, text, re.S)
        if not b:
            errs.append(f"focus '{label}' ({rel}): no focus outline resource found")
            continue
        if not s:
            errs.append(f"focus '{label}' ({rel}): the focused state does not show its outline")
            continue
        try:
            fgs = [pal[tok] for tok, _a in fs_brush_colors(p, b.group(1))]
        except KeyError as e:
            errs.append(f"focus '{label}' ({rel}): {e}")
            continue
        r, bgc = min(worst(f, flats[k]) for f in fgs for k, _ in FS_SURFACES)
        out.append({"mode": "fullscreen", "label": f"Focus outline of the {label.lower()} ({b.group(1)}), worst surface (read from {rel})", "fg": fgs[0], "bg": bgc,
                    "target": 3.0, "group": "outline", "ratio": r, "cat": "Focus outline"})
    for label, rel, rest_re, body_re in FS_CUES:
        text = patched(p, rel, "Fullscreen") if rel in dict(FS_PATCHES) else upstream_text(p, rel, "Fullscreen")
        rest, st = re.search(rest_re, text, re.S), re.search(body_re, text, re.S)
        fgm = re.search(r'<Setter Property="Foreground" Value="' + _BR, st.group("body")) if st else None
        if not rest or not st or not fgm:
            errs.append(f"state '{label}' ({rel}): resting or state foreground resource not found")
            continue
        try:
            rest_c = [pal[tok] for tok, _a in fs_brush_colors(p, rest.group(1))]
            state_c = [pal[tok] for tok, _a in fs_brush_colors(p, fgm.group(1))]
        except KeyError as e:
            errs.append(f"state '{label}' ({rel}): {e}")
            continue
        r = min(C.contrast(C.parse(a), C.parse(b)) for a in state_c for b in rest_c)
        cue = re.search(NON_COLOR_CUE, st.group("body"))
        if r < 3.0 and not cue:
            errs.append(f"state '{label}' ({rel}): {fgm.group(1)} differs from the resting {rest.group(1)} by color alone ({r:.2f}:1, under 3:1) and the state "
                        f"has no signal that is not a color (a bolder weight, an underline or an outline)")
            continue
        how = ""
        if cue:
            how = " (the color alone is not enough; the state also sets " + ("an accent underline" if "BorderBrush" in cue.group(0) else cue.group(0).split('"')[1]) + ")"
        out.append({"mode": "fullscreen", "label": f"{label}: {fgm.group(1)} against the resting {rest.group(1)}{how if r < 3.0 else ''}, read from {rel}",
                    "fg": state_c[0], "bg": rest_c[0], "target": 3.0 if r >= 3.0 else 0.0, "group": "outline" if r >= 3.0 else "cue", "ratio": r,
                    "cat": "State vs state"})
    return out, errs


def fs_rows(theme: dict, p: dict) -> list[dict]:
    return fs_rows_and_errors(theme, p)[0]


# --- installer manifests (Playnite add-on browser) -----------------------------------------------------------------------

def installer_path(p: dict, mode: str) -> Path:
    return ROOT / "installer" / f"{p['themes'][mode]['id']}.yaml"


def installer_text(theme: dict, p: dict, mode: str) -> str:
    """The installer manifest of the Playnite add-on database format: AddonId and one package, which points at the release asset."""
    t = p["themes"][mode]
    api = p["playnite"]["desktop_theme_api_version" if t["mode"] == "Desktop" else "fullscreen_theme_api_version"]
    r = p["release"]
    url = f"{p['repo']}/releases/download/{r['tag_prefix']}{theme['version']}/{pthm_path(theme, p, mode).name}"
    return (f"AddonId: {t['id']}\nPackages:\n  - Version: {theme['version']}\n    RequiredApiVersion: {api}\n    ReleaseDate: {r['date']}\n"
            f"    PackageUrl: {url}\n    Changelog:\n" + "".join(f"      - {c}\n" for c in r["changelog"]))


def installer_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    r = p["release"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"]):
        errs.append("src/playnite.json: release.date must be YYYY-MM-DD")
    for mode in MODES:
        f = installer_path(p, mode)
        rel = f.relative_to(ROOT)
        if not f.exists():
            errs.append(f"{rel}: installer manifest is missing (run --sync)")
            continue
        text = f.read_text(encoding="utf-8")
        t = p["themes"][mode]
        api = p["playnite"]["desktop_theme_api_version" if t["mode"] == "Desktop" else "fullscreen_theme_api_version"]
        y = {m.group(1): m.group(2).strip() for m in re.finditer(r"^\s*(?:- )?([A-Za-z]+):[ \t]*(.*)$", text, re.M)}
        ty = parse_simple_yaml((theme_dir(p, mode) / "theme.yaml").read_text(encoding="utf-8")) if (theme_dir(p, mode) / "theme.yaml").exists() else {}
        if y.get("AddonId") != (ty.get("Id") or t["id"]):
            errs.append(f"{rel}: AddonId {y.get('AddonId')!r} differs from the theme Id {ty.get('Id') or t['id']!r}")
        if text.count("  - Version:") != 1 or y.get("Version") != (ty.get("Version") or theme["version"]):
            errs.append(f"{rel}: installer Version {y.get('Version')!r} differs from theme.yaml Version")
        if y.get("RequiredApiVersion") != (ty.get("ThemeApiVersion") or api):
            errs.append(f"{rel}: RequiredApiVersion {y.get('RequiredApiVersion')!r} differs from the theme's ThemeApiVersion")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", y.get("ReleaseDate", "")):
            errs.append(f"{rel}: ReleaseDate {y.get('ReleaseDate')!r} must be YYYY-MM-DD")
        url = y.get("PackageUrl", "")
        if url.rsplit("/", 1)[-1] != pthm_path(theme, p, mode).name or not url.endswith(".pthm"):
            errs.append(f"{rel}: PackageUrl {url!r} does not end in the dist file name {pthm_path(theme, p, mode).name}")
        if text != installer_text(theme, p, mode):
            errs.append(f"stale generated file: {rel} (run --sync)")
    return errs


# --- docs: markers, blocks, README, images, privacy -----------------------------------------------------------------

def marker_errors() -> list[str]:
    errs = []
    for rel, want in DOC_BLOCKS.items():
        path = ROOT / rel
        if not path.exists():
            errs.append(f"{rel}: missing (it carries generated blocks)")
            continue
        text = path.read_text(encoding="utf-8")
        found = re.findall(r"<!--\s*/?build:([\w-]+)\s*-->", text)
        for name in sorted(set(found) - set(want)):
            errs.append(f"{rel}: unexpected generated block marker 'build:{name}'")
        for name in want:
            o, c = text.count(f"<!-- build:{name} -->"), text.count(f"<!-- /build:{name} -->")
            if o != 1 or c != 1:
                errs.append(f"{rel}: marker <!-- build:{name} --> found {o}x and its closing marker {c}x, expected 1 and 1")
            elif text.index(f"<!-- build:{name} -->") > text.index(f"<!-- /build:{name} -->"):
                errs.append(f"{rel}: build:{name} closes before it opens")
    return errs


def png_size(path: Path) -> tuple[int, int] | None:
    d = path.read_bytes()
    if d[:8] != b"\x89PNG\r\n\x1a\n" or d[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", d[16:24])


def image_errors() -> list[str]:
    errs = []
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    for name, size in IMAGES.items():
        f = ROOT / "images" / name
        if not f.exists():
            errs.append(f"images/{name}: missing screenshot")
            continue
        if png_size(f) != size:
            errs.append(f"images/{name}: is {png_size(f)}, expected a PNG of {size[0]}x{size[1]}")
        if f"images/{name}" not in readme:
            errs.append(f"README.md does not show images/{name}")
    for ref in sorted(set(re.findall(r"(?<![\w/.-])images/([\w.-]+\.png)", readme))):
        if not (ROOT / "images" / ref).exists():
            errs.append(f"README.md references images/{ref}, which does not exist")
    return errs


def readme_errors() -> list[str]:
    f = ROOT / "README.md"
    if not f.exists():
        return ["README.md is missing"]
    text = f.read_text(encoding="utf-8")
    heads = set(re.findall(r"^#{2,3} (.+?)\s*$", text, re.M))
    errs = [f"README.md: required section '{s}' is missing" for s in README_SECTIONS if s not in heads]
    for needle, what in (("NOT TESTED", "an explicit NOT TESTED list"), ("Josef Nemec", "the Playnite attribution"), (".pthm", "the .pthm install instructions"),
                         ("not affiliated", "the not-affiliated notice")):
        if needle not in text:
            errs.append(f"README.md: {what} is missing")
    for stale in ("Theme (Desktop)", "Theme (Fullscreen)"):  # not Playnite 10.64's labels: Appearance > General > Theme / Fullscreen Theme; Fullscreen: Visuals > Theme
        if stale in text:
            errs.append(f"README.md: '{stale}' is not a setting of Playnite 10.64 (Desktop: Settings > Appearance > General > Theme / Fullscreen Theme; "
                        f"Fullscreen: Settings > Visuals > Theme)")
    if re.search(r"\]\(\.\./", text):
        errs.append("README.md: a link leaves the repository (../); use an absolute https URL")
    if not (ROOT / "LICENSE").exists() or "MIT License" not in (ROOT / "LICENSE").read_text(encoding="utf-8"):
        errs.append("LICENSE (MIT) is missing")
    return errs


def privacy_errors() -> list[str]:
    errs = []
    private, perrs = private_patterns()
    errs += perrs
    files = [x for x in ROOT.rglob("*") if x.is_file() and not SKIP_DIRS & set(x.relative_to(ROOT).parts)]
    for f in files:
        rel = f.relative_to(ROOT)
        if rel.as_posix() in ("scripts/build.py", ".gitignore", PRIVATE_FILE.name) or rel.parts[0] == "upstream":
            continue
        if f.suffix == ".pthm":
            with zipfile.ZipFile(f) as z:
                data = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
        elif f.suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"):
            data = f.read_bytes().decode("latin-1")  # text chunks (tEXt, iTXt) would show here
            if any(k in data for k in ("tEXt", "iTXt", "eXIf")):
                errs.append(f"{rel}: has metadata chunks (tEXt, iTXt or eXIf); strip them")
        else:
            data = f.read_text(encoding="utf-8", errors="replace")
        for pat, what in PRIVACY:
            if re.search(pat, data):
                errs.append(f"{rel}: contains {what} ({pat})")
        for rx, what in private:  # the pattern itself is not printed: it is private
            if rx.search(data):
                errs.append(f"{rel}: contains {what}")
    return errs


# --- generated doc blocks ----------------------------------------------------------------------------------------------

def tok_name(token: str) -> str:
    return f"`{token}`"


def md_themes(theme: dict, p: dict) -> str:
    r = ["| Theme | Mode | Id | Package | Accent |", "| :--- | :--- | :--- | :--- | :--- |"]
    for m, mode in (("slate", "dark (Playnite Desktop)"), ("daylight", "light (Playnite Desktop)"), ("fs_slate", "dark (Playnite Fullscreen)")):
        t = p["themes"][m]
        r.append(f"| {t['name']} | {mode} | `{t['id']}` | [`dist/{pthm_path(theme, p, m).name}`]({p['repo']}/raw/main/dist/{pthm_path(theme, p, m).name}) | `{tk(theme, palette(p, m), 'accent.fill')}` |")
    return "\n".join(r)


def md_contrast_readme(theme: dict, p: dict) -> str:
    L = ["| Pair group | Target | Slate (lowest) | Daylight (lowest) |", "| :--- | ---: | ---: | ---: |"]
    groups = [("Primary text on every surface", "text.primary on bg.", 7.0), ("Secondary text on surfaces", "text.secondary on bg.", 5.0),
              ("Accent (button text, icons, links) on surfaces", "accent.fill on bg.", 4.5), ("Text on accent fill and on the badge", "accent.on on ", 4.5),
              ("Control borders and scrollbar thumb", "border.control on", 3.0), ("Status colors on canvas and surface", "fg on bg.", 4.5),
              ("Cover name on the overlay (worst case)", "text.primary on the cover overlay", 4.5), ("Cover icons on the overlay (worst case)", "accent.fill on the cover overlay", 3.0)]
    rs = rows(theme, p)
    for name, key, target in groups:
        def low(m):
            sel = [r["ratio"] for r in rs if r["mode"] == m and r["group"] != "report" and (key in r["label"] or (key == "fg on bg." and re.match(r"(success|warning|danger)\.fg on", r["label"])))]
            return f"{min(sel):.2f}" if sel else "-"
        L.append(f"| {name} | {target:g} | {low('slate')} | {low('daylight')} |")
    L.append("")
    L.append(f"Every pair is listed in [docs/mapping.md](docs/mapping.md#contrast); {len([r for r in rs if r['group'] != 'report'])} targets across both themes, all met.")
    return "\n".join(L)


def md_upstream(theme: dict, p: dict, kind: str = "Desktop") -> str:
    sums = upstream_sums()
    L = [f"| Vendored {kind} file (unmodified Playnite 10.64) | SHA-256 |", "| :--- | :--- |"]
    for name, h in sorted(sums.items()):
        if not name.startswith(kind + "/"):
            continue
        L.append(f"| `upstream/playnite-10.64/{name}` | `{h}` |")
    return "\n".join(L)


def md_constants(theme: dict, p: dict) -> str:
    cs = p["constants"]
    L = ["| Constants.xaml key | Kind | Token | Slate | Daylight | Role |", "| :--- | :--- | :--- | :--- | :--- | :--- |"]
    for grp, kind in (("colors", "Color"), ("brushes", "SolidColorBrush")):
        for key, s in cs[grp].items():
            L.append(f"| `{key}` | {kind} | {tok_name(s['token'])} | `{argb(tk(theme, 'slate', s['token']))}` | `{argb(tk(theme, 'daylight', s['token']))}` | {s['role']} |")
    for key, why in cs["gradients_replaced"].items():
        L.append(f"| `{key}` | gradient replaced | (see role) | | | {why} |")
    ty, me = theme["typography"], theme["metrics"]
    for key, tok in cs["typography"].items():
        val = wpf_family(ty[tok]) if not key.startswith("FontSize") else px(ty[tok])
        L.append(f"| `{key}` | {'Double' if key.startswith('FontSize') else 'FontFamily'} | {tok_name(tok)} | `{val}` | `{val}` | {'size in device-independent pixels (rem x 16)' if key.startswith('FontSize') else 'CSS stack without generic families'} |")
    for key, tok in cs["metrics"].items():
        L.append(f"| `{key}` | {'CornerRadius' if 'Corner' in key else 'Thickness'} | {tok_name(tok)} | `{px(me[tok])}` | `{px(me[tok])}` | |")
    L.append("")
    L.append("Kept as in Playnite: " + ", ".join(f"`{k}` ({v})" for k, v in cs["keep_literal"].items()) + ". Every other key of the upstream file is untouched, and the generated file "
             "keeps the original keys and order (`--check` fails if one is dropped).")
    return "\n".join(L)


def md_added(theme: dict, p: dict) -> str:
    L = ["| New key | Token | Slate | Daylight | Used for |", "| :--- | :--- | :--- | :--- | :--- |"]
    for key, s in p["constants"]["added"].items():
        a = s.get("alpha", 255)
        L.append(f"| `{key}` | {tok_name(s['token'])}{' at alpha ' + str(a) if a != 255 else ''} | `{argb(tk(theme, 'slate', s['token']), a)}` | `{argb(tk(theme, 'daylight', s['token']), a)}` | {s['role']} |")
    return "\n".join(L)


def md_patches(theme: dict, p: dict) -> str:
    L = ["| File | Change | Times | Why |", "| :--- | :--- | ---: | :--- |"]
    for rel, items in PATCHES:
        for pat, repl, count, why in items:
            old = re.sub(r"\\(.)", r"\1", pat)
            old = re.sub(r"\(\\s\+\)|\(<TextBlock.*?\)", "", old) if "TextBlock" in pat else old
            if "IsMouseOver" in pat and "PlayButton" in rel:
                chg = "`Foreground` of the `IsMouseOver` trigger: `{DynamicResource TextBrush}` -> `{DynamicResource TextBrushDark}`"
            elif "IsFocused" in repl:
                chg = "adds to the `ListBoxItem` style triggers: `<Trigger Property=\"IsFocused\" Value=\"True\">` setting `Foreground` to `{DynamicResource TextBrushDark}`"
            elif "Notifications" in pat:
                chg = "`FontSize=\"12\"` -> `{DynamicResource FontSizeSmall}`; `Foreground=TextBrush` -> `FlatcapBadgeTextBrush` (badge count `TextBlock`)"
            else:
                chg = f"`{old}` -> `{repl}`"
            L.append(f"| `{rel}` | {chg} | {count} | {why} |")
    return "\n".join(L)


def md_files(theme: dict, p: dict) -> str:
    L = ["| Shipped file | In the package | Origin |", "| :--- | :--- | :--- |"]
    files = theme_files(theme, p, "slate")
    for name in files:
        if name == "theme.yaml":
            org = "generated: manifest"
        elif name == "Constants.xaml":
            org = "generated from the tokens, on the upstream file"
        elif name == "LICENSE.txt":
            org = "generated: MIT license of this repository and of Playnite"
        else:
            org = "upstream file with the patches above"
        L.append(f"| `{name}` | yes | {org} |")
    return "\n".join(L)


def md_contrast(theme: dict, p: dict) -> str:
    L = ["| Theme | Pair | Ratio | Target | Result |", "| :--- | :--- | ---: | ---: | :--- |"]
    for r in rows(theme, p):
        res = "report only" if r["group"] == "report" else ("pass" if r["ratio"] >= r["target"] else "**FAIL**")
        tg = "-" if r["group"] == "report" else f"{r['target']:g}"
        bg = r["bg"] if r["bg"] == "overlay" else f"`{r['bg'].upper()}`"
        L.append(f"| {r['mode']} | {r['label']} `{r['fg'].upper()}` / {bg} | {r['ratio']:.2f} | {tg} | {res} |")
    return "\n".join(L)


def md_pthmcheck(theme: dict, p: dict) -> str:
    L = ["| Package | Members (in order) | Uncompressed bytes | Timestamp |", "| :--- | :--- | ---: | :--- |"]
    for m in MODES:
        files = theme_files(theme, p, m)
        mem = pthm_members(files)
        L.append(f"| `dist/{pthm_path(theme, p, m).name}` | {', '.join(f'`{n}`' for n, _ in mem)} | {sum(len(d) for _, d in mem)} | {'-'.join(f'{x:02d}' for x in ZIP_DATE[:3])} (fixed) |")
    return "\n".join(L)


def md_static(theme: dict, p: dict) -> str:
    rs = rows(theme, p)
    n_targets = len([r for r in rs if r["group"] != "report"])
    files = theme_files(theme, p, "slate")
    L = ["| Check | Result in this build |", "| :--- | :--- |",
         f"| Upstream files vendored and unchanged | {len(upstream_sums())} files match `SHA256SUMS` |",
         f"| Patches applied to upstream files | {sum(c for _, items in PATCHES for _, _, c, _ in items)} replacements in {len(PATCHES)} files, each matched the expected number of times |",
         f"| Shipped files per theme | {len(files)} ({', '.join(files)}) |",
         f"| Color keys mapped to tokens | {len(p['constants']['colors'])} colors, {len(p['constants']['brushes'])} brushes, {len(p['constants']['added'])} added, 2 gradients replaced |",
         "| Color literals outside `Constants.xaml` in shipped files | none |",
         f"| Contrast targets (Desktop) | {n_targets} met ({len(rs) - n_targets} report-only rows) |",
         "| Theme ids | unique, not built-in, letters, digits and underscores |",
         f"| `ThemeApiVersion` | {p['playnite']['desktop_theme_api_version']} (loadable by Desktop API {p['playnite']['desktop_app_theme_api_version']}: same major, not newer) |"]
    fr = fs_rows(theme, p)
    fn = len([r for r in fr if r["group"] != "report"])
    ffiles = theme_files(theme, p, FULLSCREEN[0])
    fpt = FS_PATCHES
    L += [f"| **Fullscreen** upstream files vendored and unchanged | {len([k for k in upstream_sums() if k.startswith('Fullscreen/')])} files match `SHA256SUMS` |",
          f"| Fullscreen patches | {sum(c for _, items in fpt for _, _, c, _ in items)} replacements in {len(fpt)} files, each matched the expected number of times |",
          f"| Fullscreen shipped files | {len(ffiles)} ({', '.join(ffiles)}) |",
          "| Fullscreen color literals outside `Constants.xaml` | none |",
          f"| Fullscreen text sizes | none under {FS_MIN_TEXT} px (FontSize, HtmlFontSize and the FontSize constants are checked) |",
          f"| Fullscreen contrast targets (text, states, focus outlines) | {fn} met ({len(fr) - fn} report-only rows) |",
          f"| Fullscreen `ThemeApiVersion` | {p['playnite']['fullscreen_theme_api_version']} (loadable by Fullscreen API {p['playnite']['fullscreen_app_theme_api_version']}: same major, not newer) |"]
    return "\n".join(L)


def md_images(theme: dict, p: dict) -> str:
    L = ["| Image | Size | SHA-256 |", "| :--- | :--- | :--- |"]
    for name in IMAGES:
        f = ROOT / "images" / name
        if f.exists():
            s = png_size(f)
            L.append(f"| `images/{name}` | {s[0]}x{s[1]} | `{hashlib.sha256(f.read_bytes()).hexdigest()}` |")
        else:
            L.append(f"| `images/{name}` | (missing) | |")
    return "\n".join(L)


# --- Fullscreen blocks -------------------------------------------------------------------------------------------------

def md_fs_upstream(theme: dict, p: dict) -> str:
    return md_upstream(theme, p, "Fullscreen")


def md_fs_constants(theme: dict, p: dict) -> str:
    cs = cfg_of(p, "Fullscreen")
    pal = palette(p, FULLSCREEN[0])
    L = ["| Constants.xaml key | Kind | Token | Slate | Role |", "| :--- | :--- | :--- | :--- | :--- |"]
    for grp, kind in (("colors", "Color"), ("brushes", "SolidColorBrush"), ("solids", "gradient replaced by a SolidColorBrush")):
        for key, sp in cs[grp].items():
            a = sp.get("alpha", 255)
            L.append(f"| `{key}` | {kind} | {tok_name(sp['token'])}{' at alpha ' + str(a) if a != 255 else ''} | `{argb(tk(theme, pal, sp['token']), a)}` | {sp['role']} |")
    for key, sp in cs["gradients"].items():
        L.append(f"| `{key}` | LinearGradientBrush (geometry kept) | {tok_name(sp['token'])} alpha {sp['from_alpha']} to {sp['to_alpha']} | "
                 f"`{argb(tk(theme, pal, sp['token']), sp['from_alpha'])}` to `{argb(tk(theme, pal, sp['token']), sp['to_alpha'])}` | {sp['role']} |")
    L.append("")
    L.append("Kept as in Playnite: " + ", ".join(f"`{k}` ({v})" for k, v in cs["keep_literal"].items()) + ". `SelectionBrush` (the focus outline: a gradient from `GlyphColor` to "
             "`GlyphLightColor`) and every other key are untouched: they take their colors from the keys above. Fonts and sizes are not mapped: Fullscreen "
             f"keeps Playnite's own (text of {FS_MIN_TEXT} px and up, Titillium Web). The generated file keeps the original keys and order (`--check` fails if one is dropped).")
    return "\n".join(L)


def md_fs_added(theme: dict, p: dict) -> str:
    pal = palette(p, FULLSCREEN[0])
    L = ["| New key | Token | Slate | Used for |", "| :--- | :--- | :--- | :--- |"]
    for key, sp in cfg_of(p, "Fullscreen")["added"].items():
        a = sp.get("alpha", 255)
        L.append(f"| `{key}` | {tok_name(sp['token'])}{' at alpha ' + str(a) if a != 255 else ''} | `{argb(tk(theme, pal, sp['token']), a)}` | {sp['role']} |")
    return "\n".join(L)


def md_fs_patches(theme: dict, p: dict) -> str:
    L = ["| File | Change | Times | Why |", "| :--- | :--- | ---: | :--- |"]
    for rel, items in FS_PATCHES:
        for pat, repl, count, why in items:
            old = re.sub(r"\\(.)", r"\1", pat)
            if old.startswith("(<Style"):
                chg = "the `Thumb` style's `Background`: `{DynamicResource ControlBackgroundBrush}` -> `{DynamicResource SelectionLightBrush}`"
            elif repl.startswith("\\1"):
                chg = "adds after the matched trigger setter: `" + " ".join(re.sub(r"\\\d", "", repl).split()) + "`"
            elif "\\s" in pat:
                chg = "the matching element is replaced by `" + " ".join(repl.split()) + "`"
            else:
                chg = f"`{old}` -> `{repl}`"
            L.append(f"| `{rel}` | {chg.replace('|', '/')} | {count} | {why} |")
    return "\n".join(L)


def md_fs_files(theme: dict, p: dict) -> str:
    L = ["| Shipped file | In the package | Origin |", "| :--- | :--- | :--- |"]
    for name in theme_files(theme, p, FULLSCREEN[0]):
        org = {"theme.yaml": "generated: manifest", "Constants.xaml": "generated from the tokens, on the upstream file",
               "LICENSE.txt": "generated: MIT license of this repository and of Playnite"}.get(name, "upstream file with the patches above")
        L.append(f"| `{name}` | yes | {org} |")
    return "\n".join(L)


def md_fs_contrast(theme: dict, p: dict) -> str:
    L = ["| Category | Pair | Ratio | Target | Result |", "| :--- | :--- | ---: | ---: | :--- |"]
    for r in fs_rows(theme, p):
        res = "report only" if r["group"] == "report" else ("pass" if r["ratio"] >= r["target"] else "**FAIL**")
        tg = "-" if r["group"] == "report" else f"{r['target']:g}"
        if r["group"] == "cue":
            res, tg = "pass: has a non-color cue", "3 or a cue"
        what = f"resting color `{r['bg'].upper()}`" if r["cat"] == "State vs state" else f"worst case `{r['bg'].upper()}`"
        L.append(f"| {r['cat']} | {r['label']} ({what}) | {r['ratio']:.2f} | {tg} | {res} |")
    return "\n".join(L)


def md_fs_contrast_readme(theme: dict, p: dict) -> str:
    fr = fs_rows(theme, p)
    L = ["| Fullscreen pair group | Target | Slate (lowest) |", "| :--- | ---: | ---: |"]
    for cat, target in (("Main text", 4.5), ("Accent", 3.0), ("Light accent", 3.0), ("Control borders", 3.0), ("Status", 3.0), ("States", 3.0), ("State vs state", 3.0), ("Focus outline", 3.0)):
        sel = [r for r in fr if r["cat"] == cat and r["group"] != "report"]
        tg = {"Main text": "4.5 (7 on opaque surfaces)", "Accent": "4.5 (3 on the translucent bar)", "Light accent": "4.5 (3 on the translucent bars)",
              "Status": "4.5 (3 for the icon)", "States": "4.5 (3 for check marks)",
              "State vs state": "3, or a bolder weight / an underline"}.get(cat, f"{target:g}")
        low = f"{min(r['ratio'] for r in sel):.2f}" + (" (with a non-color cue)" if any(r["group"] == "cue" for r in sel) else "")
        L.append(f"| {cat}: {len(sel)} pairs | {tg} | {low} |")
    n = len([r for r in fr if r["group"] != "report"])
    L.append("")
    L.append(f"Every pair is listed in [docs/mapping.md](docs/mapping.md#fullscreen-contrast); {n} targets, all met. Translucent surfaces are measured over a pure white and a pure black background picture.")
    return "\n".join(L)


BLOCKS = {"themes": md_themes, "contrast": None, "upstream": md_upstream, "constants": md_constants, "added": md_added, "patches": md_patches,
          "files": md_files, "pthmcheck": md_pthmcheck, "static": md_static, "images": md_images,
          "fs-upstream": md_fs_upstream, "fs-constants": md_fs_constants, "fs-added": md_fs_added, "fs-patches": md_fs_patches, "fs-files": md_fs_files,
          "fs-contrast": None}
DOCS = [ROOT / "README.md", ROOT / "docs" / "mapping.md", ROOT / "docs" / "qa-report.md"]


def render(path: Path, theme: dict, p: dict) -> str:
    text = path.read_text(encoding="utf-8")
    for name, fn in BLOCKS.items():
        if name == "contrast":
            fn = md_contrast_readme if path.name == "README.md" else md_contrast
        if name == "fs-contrast":
            fn = md_fs_contrast_readme if path.name == "README.md" else md_fs_contrast
        if not re.search(rf"<!-- build:{name} -->", text):
            continue
        pat = re.compile(rf"(<!-- build:{name} -->)\n?.*?\n?(<!-- /build:{name} -->)", re.S)
        text = pat.sub(lambda m: m.group(1) + "\n" + fn(theme, p) + "\n" + m.group(2), text)
    return text


def all_errors(theme: dict, p: dict) -> list[str]:
    errs = token_errors(theme, p) + upstream_errors(p)
    if errs and any(e.startswith("upstream") for e in errs):
        return errs  # the generators below read the vendored files: report the cause only
    try:
        errs += pthm_errors(theme, p) + folder_errors(theme, p) + yaml_errors(theme, p) + xml_errors(theme, p)
    except (ValueError, KeyError) as e:
        errs.append(f"build error: {e}")
    return errs + installer_errors(theme, p) + readme_errors() + image_errors() + privacy_errors() + contrast_errors(theme, p)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sync", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--pin-core", action="store_true")
    a = ap.parse_args()
    if a.pin_core:
        text = PORT.read_text(encoding="utf-8")
        new, n = re.subn(r'("sha256": ")[0-9a-f]{64}(")', lambda m: m.group(1) + core_sha256() + m.group(2), text)
        if n != 1:
            print("src/playnite.json: expected exactly one core.sha256 to rewrite")
            return 1
        PORT.write_text(new, encoding="utf-8")
        print(f"pinned src/theme.json: {core_sha256()}")
        return 0
    theme, p = load(), port()
    pre = token_errors(theme, p) + upstream_errors(p)
    if pre:
        print("\n".join(sorted(set(pre))))
        return 1
    if a.sync:
        errs = marker_errors()
        for m in MODES:
            d = theme_dir(p, m)
            files = theme_files(theme, p, m)
            d.mkdir(parents=True, exist_ok=True)
            for old in [x for x in d.rglob("*") if x.is_file() and x.relative_to(d).as_posix() not in files]:
                old.unlink()
            for name, data in files.items():
                (d / name).parent.mkdir(parents=True, exist_ok=True)
                (d / name).write_bytes(data)
            pthm_path(theme, p, m).parent.mkdir(exist_ok=True)
            pthm_path(theme, p, m).write_bytes(pthm_bytes(files))
            installer_path(p, m).parent.mkdir(exist_ok=True)
            installer_path(p, m).write_text(installer_text(theme, p, m), encoding="utf-8")
        if not marker_errors():
            for d in DOCS:
                d.write_text(render(d, theme, p), encoding="utf-8")
        print("synced:", ", ".join(x.name for x in [*(pthm_path(theme, p, m) for m in MODES)]))
        errs += all_errors(theme, p)
        if errs:
            print("\n".join("ERROR " + e for e in sorted(set(errs))))
            return 1
        return 0
    errs = marker_errors()
    if not marker_errors():
        for d in DOCS:
            if d.read_text(encoding="utf-8") != render(d, theme, p):
                errs.append(f"stale generated file: {d.relative_to(ROOT)} (run --sync)")
    errs += all_errors(theme, p)
    if errs:
        print("\n".join(sorted(set(errs))))
        return 1
    rs = rows(theme, p)
    n_rows = len([r for r in rs if r["group"] != "report"])
    n_fs = len([r for r in fs_rows(theme, p) if r["group"] != "report"])
    print(f"ok: {len(MODES)} themes x {len(theme_files(theme, p, 'slate'))} shipped files (folder and .pthm as built, deterministic metadata), {len(upstream_sums())} upstream "
          f"files unchanged, theme.yaml fields and ids, XAML well formed, no color literal outside Constants.xaml, all Flatcap resources defined, "
          f"{len(DOCS)} docs current with their markers, {len(IMAGES)} screenshots (Desktop 1440x900, Fullscreen {FS_IMAGE_SIZE[0]}x{FS_IMAGE_SIZE[1]}), README sections, no private "
          f"paths, IPs or hosts, {n_rows} Desktop contrast targets and {n_fs} Fullscreen ones met ({len(rs) - n_rows + len(fs_rows(theme, p)) - n_fs} report-only rows)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError) as e:  # a patch or a mapping no longer fits the vendored upstream file
        print(f"build error: {e}")
        sys.exit(1)
