#!/usr/bin/env python3
"""Build Flatcap 2.0 for Playnite (Desktop mode) from src/theme.json (the Flatcap core) and src/playnite.json (port settings).

    python3 scripts/build.py --sync     write themes/Desktop/<Id>/, dist/*.pthm and the generated blocks of README.md and docs/*.md;
                                        exit 1 (after writing) if the result does not pass the checks below
    python3 scripts/build.py --check    exit 1 on: a stale generated file, a missing or duplicated <!-- build:x --> marker, an upstream
                                        Playnite file that changed, a theme.yaml with wrong or duplicated fields, XAML that is not well
                                        formed, a color literal or an unresolved Flatcap resource in a theme file, a .pthm whose members,
                                        content or metadata differ from the build, a README without its required sections, a missing or
                                        wrong-sized screenshot, a private path, IP or host name, or a missed contrast target

What it builds
  * themes/Desktop/<Id>/   a theme folder Playnite can load as is (copy it to <Playnite>/Themes/Desktop/). It holds theme.yaml, a
                           generated Constants.xaml, a handful of Default-theme files with small documented patches, and LICENSE.txt.
                           Playnite loads only the files a theme ships and takes every other file from its own Default theme, so
                           nothing else is copied (see docs/mapping.md).
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
MODES = ("slate", "daylight")
ZIP_DATE = (2026, 1, 1, 0, 0, 0)  # fixed: the .pthm files must not change with the build date
PRIVACY = [  # strings that must never be committed (personal paths, hosts and profile data)
    (r"[A-Za-z]:\\+Users", "a Windows user path"), (r"AppData\\+(?:Local|Roaming)", "an AppData path"), (r"/mnt/appdata", "a local server path"),
    (r"/home/[A-Za-z0-9_.-]", "a home directory path"), (r"/Users/[A-Za-z0-9_.-]", "a macOS home path"),
    (r"\.review", "the private review folder"),
    (r"(?<![\d.])10\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 10/8)"),
    (r"(?<![\d.])172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 172.16/12)"),
    (r"(?<![\d.])192\.168\.\d{1,3}\.\d{1,3}(?![\d.])", "a private IP (RFC1918 192.168/16)"),
    (r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:local|lan|internal|intranet|corp|home\.arpa)\b", "an internal host name"),
    (r"\bcheycron\.com\b", "a private domain"), (r"\bSansa\b", "a private host name"), (r"\bclegane\b", "a private host name"),
]
SKIP_DIRS = {".git", ".review", "__pycache__", ".tmp", "node_modules"}
BUILTIN_IDS = {"Playnite_builtin_DefaultDesktop", "Playnite_builtin_DefaultFullscreen"}
NAMED_COLOR_ATTR = re.compile(r'\b(?:Foreground|Background|Fill|Stroke|BorderBrush|Color)="([A-Za-z]+)"')
ALLOWED_NAMED = {"Transparent"}
README_SECTIONS = ["Install", "Use it", "Tokens and contrast", "Fonts", "Accessibility", "Compatibility", "Third-party code and licenses",
                   "Contributing", "License"]
DOC_BLOCKS = {"README.md": ["themes", "contrast"],
              "docs/mapping.md": ["upstream", "constants", "added", "patches", "files", "contrast"],
              "docs/qa-report.md": ["pthmcheck", "static", "images"]}
IMAGES = ["desktop-slate-grid.png", "desktop-slate-details.png", "desktop-daylight-grid.png", "desktop-daylight-details.png"]
IMAGE_SIZE = (1440, 900)
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

def upstream_root(p: dict) -> Path:
    return ROOT / p["upstream"]["root"]


def upstream_sums() -> dict[str, str]:
    f = ROOT / "upstream" / "playnite-10.64" / "SHA256SUMS"
    out = {}
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                h, name = ln.split(None, 1)
                out[name.strip().lstrip("*")] = h
    return out


def upstream_text(p: dict, rel: str) -> str:
    # Playnite's files use CRLF and sometimes a BOM; the build works on LF text without BOM so patches and generated output are uniform
    return (upstream_root(p) / rel).read_bytes().decode("utf-8-sig").replace("\r\n", "\n")


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
    on_disk = {x.relative_to(base).as_posix() for x in base.rglob("*") if x.is_file() and x.name != "SHA256SUMS"}
    for name in sorted(on_disk - set(sums)):
        errs.append(f"upstream file without a checksum: upstream/playnite-10.64/{name}")
    for rel in [f for f, _ in PATCHES] + ["Constants.xaml"]:
        if f"Desktop/Default/{rel}" not in sums:
            errs.append(f"upstream/playnite-10.64/Desktop/Default/{rel} is patched but not listed in SHA256SUMS")
    lic = ROOT / p["upstream"]["license"]
    if not lic.exists() or "Josef Nemec" not in lic.read_text(encoding="utf-8") or "MIT License" not in lic.read_text(encoding="utf-8"):
        errs.append(f"{p['upstream']['license']}: the Playnite MIT license text (Josef Nemec) is missing")
    yaml = (root / "theme.yaml").read_text(encoding="utf-8-sig") if (root / "theme.yaml").exists() else ""
    if f"ThemeApiVersion: {p['playnite']['desktop_theme_api_version']}" not in yaml:
        errs.append("upstream theme.yaml does not declare the ThemeApiVersion that src/playnite.json says")
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
        (lit('Background="#003f59"'), 'Background="{DynamicResource FlatcapSelectedBrush}"', 2, "hovered and selected search result were a fixed teal")]),
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
    ("Media.xaml", [
        (lit('Foreground="OrangeRed"'), 'Foreground="{DynamicResource FlatcapDangerBrush}"', 2, "exit and remove icons"),
        (lit('Foreground="Yellow"'), 'Foreground="{DynamicResource FlatcapWarningBrush}"', 1, "favorite icon")]),
]


def patched(p: dict, rel: str) -> str:
    text = upstream_text(p, rel)
    for pat, repl, count, _why in dict(PATCHES)[rel]:
        text, n = re.subn(pat, repl, text)
        if n != count:
            raise ValueError(f"{rel}: patch {pat[:60]!r} matched {n} times, expected {count}")
    return text


def theme_yaml(theme: dict, p: dict, mode: str) -> str:
    t = p["themes"][mode]
    return (f"Id: {t['id']}\nName: {t['name']}\nAuthor: {p['author']}\nVersion: {theme['version']}\nMode: {t['mode']}\n"
            f"ThemeApiVersion: {p['playnite']['desktop_theme_api_version']}\n")  # no Links: the Default theme has none


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
    files = {"Constants.xaml": constants_xaml(theme, p, mode), "LICENSE.txt": license_txt(theme, p)}
    for rel, _ in PATCHES:
        files[rel] = patched(p, rel)
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
            tmaj, app = int(tv.split(".")[0]), p["playnite"]["desktop_app_theme_api_version"]
            if tmaj != int(app.split(".")[0]) or tuple(map(int, tv.split("."))) > tuple(map(int, app.split("."))):
                errs.append(f"{rel}: ThemeApiVersion {tv} is not loadable by a Playnite whose Desktop theme API is {app} (same major, not newer)")
        if y.get("Name") != p["themes"][mode]["name"]:
            errs.append(f"{rel}: Name {y.get('Name')!r} differs from src/playnite.json")
    return errs


def xml_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    defined_by_upstream = set()
    for f in upstream_root(p).rglob("*.xaml"):
        defined_by_upstream |= set(re.findall(r'x:Key="([^"]+)"', f.read_text(encoding="utf-8")))
    for mode in MODES:
        d = theme_dir(p, mode)
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
            # an opacity mask only decides how opaque each pixel is (Black = opaque, Transparent = clear), it never paints a color
            text = re.sub(r"<(\w+\.\w*OpacityMask)>.*?</\1>", "", text, flags=re.S)
            for lit_ in sorted(set(re.findall(r"#[0-9A-Fa-f]{6,8}\b", re.sub(r"&#x[0-9A-Fa-f]+;", "", text)))):
                errs.append(f"{rel}: color literal {lit_} (use a Constants.xaml brush, which comes from a Flatcap token)")
            for name in sorted(set(NAMED_COLOR_ATTR.findall(text)) - ALLOWED_NAMED):
                errs.append(f"{rel}: named color {name!r} (use a Constants.xaml brush)")
            # Resources that Playnite's own Default files define (styles, fonts) or the app supplies (LOC*) are not vendored here: a patch may
            # only use ones the original file already used, so it cannot introduce an unresolved name
            orig_rel = f.relative_to(d).as_posix()
            orig = upstream_text(p, orig_rel) if (upstream_root(p) / orig_rel).exists() else ""  # an extra file is reported by folder_errors
            for k in sorted(set(re.findall(r"\{DynamicResource (\w+)\}", text)) - const_keys - defined_by_upstream - set(re.findall(r"\{DynamicResource (\w+)\}", orig))):
                errs.append(f"{rel}: resource {k} is not defined in Constants.xaml and the original file does not use it")
        cf = d / "Constants.xaml"
        if cf.exists():
            ctext = cf.read_text(encoding="utf-8")
            mapped = set(p["constants"]["colors"]) | set(p["constants"]["brushes"]) | set(p["constants"]["keep_literal"])
            for m in re.finditer(r'x:Key="(\w+)"[^>]*?(?:Color="(#[0-9A-Fa-f]{6,8})"|>(#[0-9A-Fa-f]{6,8})<)', ctext):
                key = m.group(1)
                if key not in mapped and key not in p["constants"]["added"] and key not in p["constants"]["gradients_replaced"]:
                    errs.append(f"{cf.relative_to(ROOT)}: {key} holds a color literal that no Flatcap token maps")
            for m in re.finditer(r'<GradientStop Color="(#[0-9A-Fa-f]{6,8})"', ctext):
                pass
            up = upstream_text(p, "Constants.xaml")
            up_keys = re.findall(r'x:Key="(\w+)"', up)
            for k in up_keys:
                if f'x:Key="{k}"' not in ctext:
                    errs.append(f"{cf.relative_to(ROOT)}: upstream key {k} was dropped")
    return errs


def token_errors(theme: dict, p: dict) -> list[str]:
    errs = []
    cs = p["constants"]
    for m in MODES:
        t = theme["themes"][m]
        need = {s["token"] for grp in ("colors", "brushes", "added") for s in cs[grp].values()} | {x for a, b, c, d in [pr[:4] for pr in pairs_raw()] for x in (b, c)}
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
        errs.append("the two themes share an id")
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
    for s, where in SURFACES[:4]:
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
    for m in MODES:
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


def rows(theme: dict, p: dict) -> list[dict]:
    out = []
    for m in MODES:
        for label, fg, bg, target, group, op in pairs_raw():
            a, b = tk(theme, m, fg), tk(theme, m, bg)
            out.append({"mode": m, "label": label, "fg": a, "bg": b, "target": target, "group": group, "ratio": ratio(a, b, op)})
    return out + scrim_rows(theme, p)


def contrast_errors(theme: dict, p: dict) -> list[str]:
    return [f"{r['mode']}: {r['label']} = {r['ratio']:.2f} < {r['target']} (contrast target missed)" for r in rows(theme, p) if r["ratio"] < r["target"]]


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
    for name in IMAGES:
        f = ROOT / "images" / name
        if not f.exists():
            errs.append(f"images/{name}: missing screenshot")
            continue
        if png_size(f) != IMAGE_SIZE:
            errs.append(f"images/{name}: is {png_size(f)}, expected a PNG of {IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}")
        if f"images/{name}" not in readme:
            errs.append(f"README.md does not show images/{name}")
    for ref in sorted(set(re.findall(r"images/([\w.-]+\.png)", readme))):
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
    if not (ROOT / "LICENSE").exists() or "MIT License" not in (ROOT / "LICENSE").read_text(encoding="utf-8"):
        errs.append("LICENSE (MIT) is missing")
    return errs


def privacy_errors() -> list[str]:
    errs = []
    files = [x for x in ROOT.rglob("*") if x.is_file() and not SKIP_DIRS & set(x.relative_to(ROOT).parts)]
    for f in files:
        rel = f.relative_to(ROOT)
        if rel.as_posix() in ("scripts/build.py", ".gitignore") or rel.parts[0] == "upstream":
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
    return errs


# --- generated doc blocks ----------------------------------------------------------------------------------------------

def tok_name(token: str) -> str:
    return f"`{token}`"


def md_themes(theme: dict, p: dict) -> str:
    r = ["| Theme | Mode | Id | Package | Accent |", "| :--- | :--- | :--- | :--- | :--- |"]
    for m, mode in (("slate", "dark"), ("daylight", "light")):
        t = p["themes"][m]
        r.append(f"| {t['name']} | {mode} (Playnite Desktop) | `{t['id']}` | [`dist/{pthm_path(theme, p, m).name}`]({p['repo']}/raw/main/dist/{pthm_path(theme, p, m).name}) | `{tk(theme, m, 'accent.fill')}` |")
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


def md_upstream(theme: dict, p: dict) -> str:
    sums = upstream_sums()
    L = ["| Vendored file (unmodified Playnite 10.64) | SHA-256 |", "| :--- | :--- |"]
    for name, h in sorted(sums.items()):
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
            if "Notifications" in pat:
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
         f"| Contrast targets | {n_targets} met ({len(rs) - n_targets} report-only rows) |",
         "| Theme ids | unique, not built-in, letters, digits and underscores |",
         f"| `ThemeApiVersion` | {p['playnite']['desktop_theme_api_version']} (loadable by Desktop API {p['playnite']['desktop_app_theme_api_version']}: same major, not newer) |"]
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


BLOCKS = {"themes": md_themes, "contrast": None, "upstream": md_upstream, "constants": md_constants, "added": md_added, "patches": md_patches,
          "files": md_files, "pthmcheck": md_pthmcheck, "static": md_static, "images": md_images}
DOCS = [ROOT / "README.md", ROOT / "docs" / "mapping.md", ROOT / "docs" / "qa-report.md"]


def render(path: Path, theme: dict, p: dict) -> str:
    text = path.read_text(encoding="utf-8")
    for name, fn in BLOCKS.items():
        if name == "contrast":
            fn = md_contrast_readme if path.name == "README.md" else md_contrast
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
    return errs + readme_errors() + image_errors() + privacy_errors() + contrast_errors(theme, p)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sync", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
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
    print(f"ok: {len(MODES)} themes x {len(theme_files(theme, p, 'slate'))} shipped files (folder and .pthm as built, deterministic metadata), {len(upstream_sums())} upstream "
          f"files unchanged, theme.yaml fields and ids, XAML well formed, no color literal outside Constants.xaml, all Flatcap resources defined, "
          f"{len(DOCS)} docs current with their markers, {len(IMAGES)} screenshots of {IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}, README sections, no private "
          f"paths, IPs or hosts, {n_rows} contrast targets met ({len(rs) - n_rows} report-only rows)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError) as e:  # a patch or a mapping no longer fits the vendored upstream file
        print(f"build error: {e}")
        sys.exit(1)
