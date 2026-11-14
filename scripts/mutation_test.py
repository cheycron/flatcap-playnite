#!/usr/bin/env python3
"""Prove that each detector of `scripts/build.py --check` (and the exit code of --sync) fails on a matching mutation.

    python3 scripts/mutation_test.py              # mutate a copy of the working tree (tracked and untracked, not ignored files)
    python3 scripts/mutation_test.py --ref HEAD   # mutate a copy made with `git archive HEAD`

Every case copies the repository into a fresh temporary folder, applies ONE mutation there, runs the check and expects a non-zero exit
whose output mentions the expected text. The first case is the unmutated copy and must pass. The repository itself is never modified.
Prints a table and exits 1 if any detector did not fire. Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import warnings
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLATE = "themes/Desktop/Flatcap_Slate_Desktop"
DAY = "themes/Desktop/Flatcap_Daylight_Desktop"
FS = "themes/Fullscreen/Flatcap_Slate_Fullscreen"
PTHM_FS = "dist/Flatcap_Slate_Fullscreen_2_0_0.pthm"
PTHM_SLATE = "dist/Flatcap_Slate_Desktop_2_0_0.pthm"
PTHM_DAY = "dist/Flatcap_Daylight_Desktop_2_0_0.pthm"
UP = "upstream/playnite-10.64"
# the private strings are assembled here so that this file does not trip the privacy scan itself
WIN_PATH = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "file"
HOME_PATH = "/ho" + "me/someone/file"
IP10, IP172, IP192 = "10." + "1.2.3", "172." + "20.4.5", "192." + "168.1.20"
HOST = "nas" + "." + "lan"
IPCG = "100." + "100.1.2"
TSNET = "box." + "tail1234" + "." + "ts" + "." + "net"
UNC = "\\" + "\\" + "nas" + "\\" + "share"
MNT_PATH = "/mn" + "t/data/file"
EMAIL = "some" + "one" + "@" + "example" + "." + "com"
NOREPLY = "12345+some" + "one" + "@" + "users.noreply.github.com"
PRIV_WORD = "zzprivate" + "hostzz"
PRIV_RX = "\\" + "b" + PRIV_WORD + "\\" + "b"  # \bword\b


def copy_tree(dst: Path, ref: str | None) -> None:
    if ref:
        data = subprocess.run(["git", "archive", ref], cwd=ROOT, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dst)], input=data, check=True)
        return
    names = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode().split("\0")
    for n in filter(None, names):
        if (ROOT / n).is_file():
            (dst / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / n, dst / n)


def edit(path: str, fn):
    def run(d: Path):
        f = d / path
        old = f.read_text(encoding="utf-8")
        new = fn(old)
        assert new != old, f"mutation did not change {path}"
        f.write_text(new, encoding="utf-8")
    return run


def sub(old: str, new: str, count: int = 1):
    def fn(s: str) -> str:
        if old not in s:
            raise AssertionError(f"{old!r} not found")
        return s.replace(old, new, count)
    return fn


def append(text: str):
    return lambda s: s + text


def before_close(text: str):
    """Insert before the last closing tag of the XAML root, so the file stays well formed."""
    def fn(s: str) -> str:
        i = s.rindex("</")
        return s[:i] + text + "\n" + s[i:]
    return fn


def delete(path: str):
    return lambda d: (d / path).unlink()


def add_file(path: str, data: bytes = b"x"):
    def run(d: Path):
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_bytes(data)
    return run


def both(*fns):
    """Several mutations in one case (they are one defect: a private name AND the file that lists it)."""
    def run(d: Path):
        env = None
        for fn in fns:
            env = fn(d) or env
        return env
    return run


def private_file(name: str, text: str, env_var: bool = False):
    def run(d: Path):
        f = d / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return {"FLATCAP_PRIVATE_PATTERNS": str(f)} if env_var else None
    return run


def crlf(path: str):
    def run(d: Path):
        f = d / path
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    return run


def json_edit(path: str, fn):
    def run(d: Path):
        f = d / path
        j = json.loads(f.read_text(encoding="utf-8"))
        fn(j)
        f.write_text(json.dumps(j, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return run


def upstream_edit(rel: str, fn):
    """Change a vendored upstream file AND its checksum, so that only the patch/mapping detectors can notice."""
    def run(d: Path):
        f = d / UP / "Desktop/Default" / rel
        old = f.read_bytes().decode("utf-8")
        new = fn(old)
        assert new != old
        f.write_bytes(new.encode("utf-8"))
        sums = d / UP / "SHA256SUMS"
        key = f"Desktop/Default/{rel}"
        lines = []
        for ln in sums.read_text(encoding="utf-8").splitlines():
            h, name = ln.split(None, 1)
            lines.append(f"{hashlib.sha256(new.encode('utf-8')).hexdigest()}  {name}" if name.strip() == key else ln)
        sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run


def rezip(path: str, **kw):
    """Rewrite a .pthm keeping its content but changing member metadata, names or content."""
    def run(d: Path):
        f = d / path
        with zipfile.ZipFile(f) as z:
            members = [(i.filename, z.read(i.filename)) for i in z.infolist()]
        if kw.get("content"):
            members = [(n, kw["content"](b) if n == "Constants.xaml" else b) for n, b in members]
        if kw.get("rename"):
            members[0] = (kw["rename"], members[0][1])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n, b in members:
                info = zipfile.ZipInfo(n, date_time=kw.get("date", (2026, 1, 1, 0, 0, 0)))
                info.compress_type = kw.get("compress", zipfile.ZIP_DEFLATED)
                info.create_system = 3
                info.external_attr = kw.get("attr", 0o644 << 16)
                z.writestr(info, b)
            if kw.get("extra_member"):
                z.writestr(zipfile.ZipInfo("notes.txt", date_time=(2026, 1, 1, 0, 0, 0)), b"x")
            if kw.get("dup_member"):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    z.writestr(zipfile.ZipInfo(members[1][0], date_time=(2026, 1, 1, 0, 0, 0)), members[1][1])
        f.write_bytes(buf.getvalue())
    return run


def trailing(path: str):
    def run(d: Path):
        f = d / path
        f.write_bytes(f.read_bytes() + b"\0" * 16)
    return run


def tiny_png(path: str):
    def run(d: Path):
        def chunk(t: bytes, b: bytes) -> bytes:
            return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b"")
        (d / path).write_bytes(png)
    return run


def lower_focus_contrast(d: Path):
    """The Fullscreen focus outline (accent.fill) takes the colour of the canvas it is drawn on."""
    f = d / "src/theme.json"
    j = json.loads(f.read_text(encoding="utf-8"))
    j["themes"]["slate"]["accent.fill"] = j["themes"]["slate"]["bg.canvas"]
    f.write_text(json.dumps(j, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    repin(d)


def upstream_fs_edit(rel: str):
    def run(d: Path):
        f = d / UP / "Fullscreen/Default" / rel
        f.write_bytes(f.read_bytes() + b"\n<!-- edited -->\n")
    return run


def repin(d: Path):
    """Pin the (mutated) core copy, so that only the mutation under test can fail."""
    pin = hashlib.sha256((d / "src/theme.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    f = d / "src/playnite.json"
    f.write_text(re.sub(r'("sha256": ")[0-9a-f]{64}(")', lambda m: m.group(1) + pin + m.group(2), f.read_text(encoding="utf-8")), encoding="utf-8")


def lower_contrast(d: Path):
    f = d / "src/theme.json"
    j = json.loads(f.read_text(encoding="utf-8"))
    j["themes"]["slate"]["text.secondary"] = j["themes"]["slate"]["bg.surface"]
    f.write_text(json.dumps(j, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    repin(d)


def change_token(d: Path):
    f = d / "src/playnite.json"
    s = f.read_text(encoding="utf-8")
    assert '"token": "bg.canvas"' in s
    f.write_text(s.replace('"token": "bg.canvas"', '"token": "bg.nope"', 1), encoding="utf-8")


def drop_key(d: Path):
    f = d / SLATE / "Constants.xaml"
    lines = f.read_text(encoding="utf-8").split("\n")
    n = [i for i, ln in enumerate(lines) if 'x:Key="ControlCornerRadius"' in ln]
    assert len(n) == 1
    del lines[n[0]]
    f.write_text("\n".join(lines), encoding="utf-8")


# (id, detector, mutation, command, expected text in the output)
CASES = [
    ("baseline", "unmutated copy passes", None, "--check", None),
    # upstream base
    ("up-1", "vendored upstream file changed", edit(f"{UP}/Desktop/Default/Constants.xaml", append("\n<!-- edited -->\n")), "--check", "upstream file changed"),
    ("up-2", "vendored upstream file deleted", delete(f"{UP}/Desktop/Default/Media.xaml"), "--check", "upstream file missing"),
    ("up-3", "vendored file without a checksum", add_file(f"{UP}/Desktop/Default/Extra.xaml"), "--check", "upstream file without a checksum"),
    ("up-4", "Playnite license text without the copyright holder", edit("LICENSES/Playnite-MIT.txt", sub("Josef Nemec", "Someone")), "--check", "Playnite MIT license text"),
    ("up-5", "patch no longer matches the upstream file", upstream_edit("CustomControls/SidebarItem.xaml", sub("#dbdbdb", "#dbdbdc")), "--check", "matched 0 times"),
    ("up-6", "Constants mapping no longer matches the upstream file", upstream_edit("Constants.xaml", lambda s: re.sub(r'(<Color x:Key="TextColor">)#[0-9A-Fa-f]{6,8}', r"\1red", s, count=1)), "--check", "expected exactly one"),
    # generated theme folders
    ("stale-1", "theme Constants.xaml edited by hand", edit(f"{SLATE}/Constants.xaml", append("\n<!-- hand edit -->\n")), "--check", "stale generated file: themes/Desktop/Flatcap_Slate_Desktop/Constants.xaml"),
    ("stale-2", "patched file edited by hand", edit(f"{DAY}/Media.xaml", append("\n<!-- hand edit -->\n")), "--check", "stale generated file: themes/Desktop/Flatcap_Daylight_Desktop/Media.xaml"),
    ("stale-3", "extra file in a theme folder", add_file(f"{SLATE}/Extra.xaml"), "--check", "unexpected file in theme folder"),
    ("stale-4", "file missing from a theme folder", delete(f"{DAY}/Views/TopPanel.xaml"), "--check", "missing file in theme folder"),
    ("stale-5", "theme folder missing", lambda d: shutil.rmtree(d / DAY), "--check", "missing theme folder"),
    # theme.yaml
    ("yaml-1", "built-in theme id", edit(f"{SLATE}/theme.yaml", sub("Id: Flatcap_Slate_Desktop", "Id: Playnite_builtin_DefaultDesktop")), "--check", "is a built-in theme id"),
    ("yaml-2", "duplicated theme id", edit(f"{DAY}/theme.yaml", sub("Id: Flatcap_Daylight_Desktop", "Id: Flatcap_Slate_Desktop")), "--check", "is also used by"),
    ("yaml-3", "id with a space", edit(f"{SLATE}/theme.yaml", sub("Id: Flatcap_Slate_Desktop", "Id: Flatcap Slate")), "--check", "letters, digits and underscores only"),
    ("yaml-4", "version that is not a .NET version", edit(f"{SLATE}/theme.yaml", sub("Version: 2.0.0", "Version: two")), "--check", "is not a .NET version string"),
    ("yaml-5", "ThemeApiVersion newer than the application", edit(f"{SLATE}/theme.yaml", sub("ThemeApiVersion: 2.0.0", "ThemeApiVersion: 2.11.0")), "--check", "is not loadable"),
    ("yaml-6", "ThemeApiVersion of another major", edit(f"{DAY}/theme.yaml", sub("ThemeApiVersion: 2.0.0", "ThemeApiVersion: 3.0.0")), "--check", "is not loadable"),
    ("yaml-7", "Mode that does not match the folder", edit(f"{SLATE}/theme.yaml", sub("Mode: Desktop", "Mode: Fullscreen")), "--check", "does not match the folder"),
    ("yaml-8", "Author missing", edit(f"{SLATE}/theme.yaml", sub("Author: Cheycron Blaine\n", "")), "--check", "Author is missing"),
    ("yaml-9", "version differs from the core", edit(f"{DAY}/theme.yaml", sub("Version: 2.0.0", "Version: 2.0.1")), "--check", "differs from the core"),
    # XAML
    ("xml-1", "XAML not well formed", edit(f"{SLATE}/Views/SearchView.xaml", append("\n<Unclosed>\n")), "--check", "XAML is not well formed"),
    ("xml-2", "color literal in a shipped file", edit(f"{SLATE}/CustomControls/SidebarItem.xaml", before_close('<!-- Background="#112233" -->')), "--check", "color literal #112233"),
    ("xml-3", "named color in a shipped file", edit(f"{DAY}/Media.xaml", before_close('<!-- Foreground="Red" -->')), "--check", "named color 'Red'"),
    ("xml-4", "Flatcap resource used but not defined", edit(f"{SLATE}/CustomControls/SidebarItem.xaml", sub("FlatcapBadgeBrush", "FlatcapNopeBrush")), "--check", "is used but not defined"),
    ("xml-5", "unresolved resource introduced into a patched file", edit(f"{SLATE}/Views/TopPanel.xaml", before_close('<!-- {DynamicResource BogusBrush} -->')), "--check", "BogusBrush is not defined"),
    ("xml-6", "upstream key dropped from Constants.xaml", drop_key, "--check", "upstream key ControlCornerRadius was dropped"),
    ("xml-7", "duplicated x:Key", edit(f"{SLATE}/Constants.xaml", before_close('<SolidColorBrush x:Key="TextBrush" Color="#FF000000" />')), "--check", "duplicated x:Key"),
    # tokens and contrast
    ("token-1", "mapping uses a token the core does not define", change_token, "--check", "token bg.nope is used by the mapping"),
    ("token-2", "version of the mapping differs from the core", json_edit("src/playnite.json", lambda j: j.__setitem__("version", "2.0.1")), "--check", "differs from the core"),
    ("contrast-1", "secondary text with the contrast of its own surface", lower_contrast, "--check", "contrast target missed"),
    # packages
    ("zip-1", "ZIP timestamp", rezip(PTHM_SLATE, date=(2026, 5, 5, 1, 2, 4)), "--check", "ZIP metadata date_time"),
    ("zip-2", "ZIP permissions", rezip(PTHM_SLATE, attr=0o600 << 16), "--check", "ZIP metadata external_attr"),
    ("zip-3", "ZIP compression (stored)", rezip(PTHM_DAY, compress=zipfile.ZIP_STORED), "--check", "ZIP metadata compress_type"),
    ("zip-4", "ZIP first member renamed", rezip(PTHM_DAY, rename="theme/theme.yaml"), "--check", "members are"),
    ("zip-5", "ZIP extra member", rezip(PTHM_SLATE, extra_member=True), "--check", "members are"),
    ("zip-6", "bytes outside the ZIP structure", trailing(PTHM_SLATE), "--check", "bytes outside the ZIP structure"),
    ("zip-7", "ZIP member content differs from the build", rezip(PTHM_DAY, content=lambda b: b + b"<!-- x -->"), "--check", "member Constants.xaml"),
    ("zip-8", "package missing", delete(PTHM_DAY), "--check", "missing package"),
    ("zip-9", "duplicate ZIP member", rezip(PTHM_SLATE, dup_member=True), "--check", "duplicate ZIP member"),
    # Fullscreen
    ("fs-1", "Fullscreen vendored upstream file changed", upstream_fs_edit("Constants.xaml"), "--check", "upstream file changed"),
    ("fs-2", "Fullscreen vendored upstream file deleted", delete(f"{UP}/Fullscreen/Default/Views/Main.xaml"), "--check", "upstream file missing"),
    ("fs-3", "Fullscreen theme.yaml Mode Desktop", edit(f"{FS}/theme.yaml", sub("Mode: Fullscreen", "Mode: Desktop")), "--check", "does not match the folder"),
    ("fs-4", "Fullscreen ThemeApiVersion newer than the application", edit(f"{FS}/theme.yaml", sub("ThemeApiVersion: 2.0.0", "ThemeApiVersion: 2.11.0")), "--check", "is not loadable"),
    ("fs-5", "Fullscreen Constants.xaml edited by hand", edit(f"{FS}/Constants.xaml", append("\n<!-- hand edit -->\n")), "--check", "stale generated file: themes/Fullscreen/Flatcap_Slate_Fullscreen/Constants.xaml"),
    ("fs-6", "Fullscreen theme folder missing", lambda d: shutil.rmtree(d / FS), "--check", "missing theme folder"),
    ("fs-7", "color literal in a Fullscreen shipped file", edit(f"{FS}/Views/Main.xaml", before_close('<!-- Background="#112233" -->')), "--check", "color literal #112233"),
    ("fs-8", "Fullscreen focus outline with the colour of the canvas", lower_focus_contrast, "--check", "contrast target missed"),
    ("fs-9", "Fullscreen text under the minimum size", edit(f"{FS}/Views/Main.xaml", sub('Height="110"', 'FontSize="10" Height="110"')), "--check", "under the 18 px minimum"),
    ("fs-10", "Fullscreen package edited", rezip(PTHM_FS, content=lambda b: b + b"<!-- x -->"), "--check", "member Constants.xaml"),
    ("fs-11", "Fullscreen package missing", delete(PTHM_FS), "--check", "missing package"),
    ("fs-12", "Fullscreen screenshot missing", delete("images/fullscreen-slate-grid.png"), "--check", "images/fullscreen-slate-grid.png: missing screenshot"),
    ("fs-13", "Fullscreen screenshot of the wrong size", tiny_png("images/fullscreen-slate-menu.png"), "--check", "expected a PNG of 1920x1080"),
    ("fs-14", "README does not show a Fullscreen screenshot", edit("README.md", lambda s: s.replace("images/fullscreen-slate-details.png", "images/other.png")), "--check", "README.md does not show images/fullscreen-slate-details.png"),
    # docs
    ("readme-1", "required README section missing", edit("README.md", sub("## Install\n", "## Setup\n")), "--check", "required section 'Install' is missing"),
    ("readme-2", "NOT TESTED list missing", edit("README.md", lambda s: s.replace("NOT TESTED", "untested")), "--check", "NOT TESTED list is missing"),
    ("readme-3", "upstream attribution missing", edit("README.md", lambda s: s.replace("Josef Nemec", "the author")), "--check", "Playnite attribution is missing"),
    ("readme-4", ".pthm instructions missing", edit("README.md", lambda s: s.replace(".pthm", ".pkg")), "--check", ".pthm install instructions"),
    ("docs-1", "generated block edited by hand", edit("docs/mapping.md", sub("| Constants.xaml key |", "| Key |")), "--check", "stale generated file: docs/mapping.md"),
    ("markers-1", "opening marker missing", edit("README.md", sub("<!-- build:themes -->\n", "")), "--check", "build:themes"),
    ("markers-2", "closing marker missing", edit("docs/mapping.md", sub("<!-- /build:contrast -->", "")), "--check", "build:contrast"),
    ("markers-3", "marker duplicated", edit("docs/qa-report.md", append("\n<!-- build:pthmcheck -->\n<!-- /build:pthmcheck -->\n")), "--check", "build:pthmcheck"),
    ("markers-4", "unexpected marker", edit("README.md", append("\n<!-- build:nonsense -->\n<!-- /build:nonsense -->\n")), "--check", "unexpected generated block marker"),
    ("sync-1", "--sync exits non-zero on a marker error", edit("README.md", sub("<!-- /build:themes -->", "")), "--sync", "build:themes"),
    ("sync-2", "--sync exits non-zero on a missed contrast target", lower_contrast, "--sync", "contrast target missed"),
    ("sync-3", "--sync exits non-zero on a token the core lacks", change_token, "--sync", "token bg.nope is used by the mapping"),
    # images
    ("img-1", "screenshot missing", delete("images/desktop-slate-grid.png"), "--check", "images/desktop-slate-grid.png: missing screenshot"),
    ("img-2", "screenshot of the wrong size", tiny_png("images/desktop-daylight-details.png"), "--check", "expected a PNG of 1440x900"),
    ("img-3", "screenshot with metadata chunk", lambda d: (d / "images/desktop-slate-details.png").write_bytes((d / "images/desktop-slate-details.png").read_bytes() + b"tEXtx"), "--check", "metadata chunks"),
    ("img-4", "README does not show a screenshot", edit("README.md", lambda s: s.replace("images/desktop-slate-grid.png", "images/other.png")), "--check", "README.md does not show images/desktop-slate-grid.png"),
    # privacy
    ("privacy-1", "Windows user path", edit("README.md", append(f"\n{WIN_PATH}\n")), "--check", "a Windows user path"),
    ("privacy-2", "home directory path", edit("docs/qa-report.md", append(f"\n{HOME_PATH}\n")), "--check", "a home directory path"),
    ("privacy-3", "RFC1918 10/8", edit("docs/mapping.md", append(f"\nhost {IP10}\n")), "--check", "RFC1918 10/8"),
    ("privacy-4", "RFC1918 172.16/12", edit("docs/mapping.md", append(f"\nhost {IP172}\n")), "--check", "RFC1918 172.16/12"),
    ("privacy-5", "RFC1918 192.168/16", edit("qa/qa-run.ps1", append(f"\n# {IP192}\n")), "--check", "RFC1918 192.168/16"),
    ("privacy-6", "internal host name", edit("README.md", append(f"\nsee {HOST}\n")), "--check", "an internal host name"),
    ("privacy-7", "CGNAT / Tailscale IP (100.64/10)", edit("docs/mapping.md", append(f"\nhost {IPCG}\n")), "--check", "100.64/10"),
    ("privacy-8", "Tailscale host name (*.ts.net)", edit("README.md", append(f"\nsee {TSNET}\n")), "--check", "*.ts.net"),
    ("privacy-9", "UNC path", edit("qa/qa-run.ps1", append(f"\n# {UNC}\n")), "--check", "a UNC path"),
    ("privacy-10", "email that is not a GitHub noreply one", edit("README.md", append(f"\ncontact {EMAIL}\n")), "--check", "not a GitHub noreply one"),
    ("privacy-11", "/mnt path", edit("docs/qa-report.md", append(f"\n{MNT_PATH}\n")), "--check", "a /mnt path"),
    ("privacy-12", "a GitHub noreply email is allowed", edit("README.md", append(f"\n{NOREPLY}\n")), "--check", None),
    ("privacy-13", "name listed in the local .private-patterns", both(private_file(".private-patterns", f"# local\n{PRIV_RX}\n"), edit("README.md", append(f"\nsee {PRIV_WORD}\n"))), "--check", "a private pattern (line 2 of .private-patterns)"),
    ("privacy-14", "name listed in the file FLATCAP_PRIVATE_PATTERNS points to", both(private_file(".tmp/other.txt", f"{PRIV_RX}\n", env_var=True), edit("docs/mapping.md", append(f"\nsee {PRIV_WORD}\n"))), "--check", "a private pattern (line 1 of other.txt)"),
    ("privacy-15", "private pattern that is not a regular expression", private_file(".private-patterns", "(unclosed\n"), "--check", "not a valid regular expression"),
    ("privacy-16", "FLATCAP_PRIVATE_PATTERNS points to nothing", (lambda d: {"FLATCAP_PRIVATE_PATTERNS": str(d / ".tmp" / "missing.txt")}), "--check", "points to a file that does not exist"),
    # core copy pinned
    ("core-1", "src/theme.json changed by a byte", edit("src/theme.json", append("\n")), "--check", "differs from the pinned core copy"),
    ("core-2", "src/theme.json with another accent", edit("src/theme.json", sub('"#9BBFDF"', '"#9BBFE0"')), "--check", "differs from the pinned core copy"),
    ("core-3", "pin changed in src/playnite.json", json_edit("src/playnite.json", lambda j: j["core"].__setitem__("sha256", "0" * 64)), "--check", "differs from the pinned core copy"),
    ("core-4", "pin missing", json_edit("src/playnite.json", lambda j: j.pop("core")), "--check", "core.sha256"),
    ("core-5", "CRLF line endings in src/theme.json do not change the pin", crlf("src/theme.json"), "--check", None),
    ("core-6", "--sync refuses a changed core", edit("src/theme.json", append("\n")), "--sync", "differs from the pinned core copy"),
    ("core-7", "--pin-core accepts a deliberate change and --check then passes", edit("src/theme.json", append("\n")), "--pin-core", "+pinned src/theme.json"),
    # states read from the XAML (Play button hover, list item focus)
    ("state-1", "Play button hover keeps the main text color on the accent fill", edit("scripts/build.py", sub("\\1{DynamicResource TextBrushDark}\\2", "\\1{DynamicResource TextBrush}\\2")), "--check", "Play button, hover: text.primary on accent.fill"),
    ("state-2", "focused list item without the text-on-accent patch", edit("scripts/build.py", sub('IsFocused" Value="True">\\n                <Setter Property="Foreground"', 'IsFocused" Value="True">\\n                <Setter Property="Opacity"')), "--check", "state 'List item, keyboard focus without selection'"),
    ("state-3", "mapping makes the text-on-accent color the main text color", json_edit("src/playnite.json", lambda j: j["constants"]["colors"]["TextColorDark"].__setitem__("token", "text.primary")), "--check", "Play button, hover: text.primary on accent.fill"),
    ("up-7", "vendored PlayButton.xaml changed", edit(f"{UP}/Desktop/Default/DerivedStyles/PlayButton.xaml", append("\n<!-- edited -->\n")), "--check", "upstream file changed"),
    # color literals of every spelling
    ("lit-1", "3-digit hex in a Setter value", edit(f"{SLATE}/CustomControls/SidebarItem.xaml", sub('Value="{DynamicResource TextBrush}"', 'Value="#fff"')), "--check", "color literal #fff"),
    ("lit-2", "4-digit hex (#ARGB)", edit(f"{DAY}/CustomControls/SidebarItem.xaml", sub('Value="{DynamicResource TextBrush}"', 'Value="#8fff"')), "--check", "color literal #8fff"),
    ("lit-3", "8-digit hex", edit(f"{SLATE}/Media.xaml", sub('Foreground="{DynamicResource FlatcapWarningBrush}"', 'Foreground="#80FFFFFF"')), "--check", "color literal #80FFFFFF"),
    ("lit-4", "scRGB literal", edit(f"{DAY}/Media.xaml", sub('Foreground="{DynamicResource FlatcapWarningBrush}"', 'Foreground="sc#1,0.5,0.5,0.5"')), "--check", "color literal sc#1,0.5,0.5,0.5"),
    ("lit-5", "named color in a Setter Value", edit(f"{SLATE}/Media.xaml", before_close('<Setter Property="Foreground" Value="Tomato" />')), "--check", "named color 'Tomato'"),
    ("lit-6", "named color in an attribute that is not a brush one (Stroke)", edit(f"{DAY}/Media.xaml", before_close('<Path Stroke="Orange" />')), "--check", "named color 'Orange'"),
    ("lit-7", "Colors.X static reference", edit(f"{SLATE}/Media.xaml", before_close('<Setter Property="Foreground" Value="{x:Static Colors.Crimson}" />')), "--check", "named color 'Crimson'"),
    ("lit-8", "SystemColors", edit(f"{DAY}/Media.xaml", before_close('<Setter Property="Background" Value="{DynamicResource {x:Static SystemColors.ControlBrushKey}}" />')), "--check", "SystemColors"),
    ("lit-9", "named color as element text", edit(f"{SLATE}/Media.xaml", before_close('<SolidColorBrush x:Key="ZzzBrush">Red</SolidColorBrush>')), "--check", "named color 'Red'"),
    ("lit-10", "opaque named color inside an opacity mask", edit(f"{SLATE}/Views/DetailsViewGameOverview.xaml", sub('Color="Black" Offset="0.3"', 'Color="Red" Offset="0.3"')), "--check", "named color 'Red' in an OpacityMask"),
    ("lit-11", "hex inside an opacity mask", edit(f"{DAY}/Views/DetailsViewGameOverview.xaml", sub('Color="Black" Offset="0.3"', 'Color="#FF000000" Offset="0.3"')), "--check", "color literal #FF000000 in an OpacityMask"),
    ("lit-12", "Black outside an opacity mask", edit(f"{SLATE}/Media.xaml", before_close('<Setter Property="Foreground" Value="Black" />')), "--check", "named color 'Black'"),
    ("lit-13", "LightGray text (the SearchView description) back in", edit(f"{DAY}/Views/SearchView.xaml", sub('Value="{DynamicResource TextBrushDarker}"', 'Value="LightGray"')), "--check", "named color 'LightGray'"),
    ("readme-5", "link that leaves the repository", edit("README.md", append("\n[core](../00-Flatcap)\n")), "--check", "a link leaves the repository"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", help="git ref to copy with git archive (default: the working tree)")
    a = ap.parse_args()
    rows, bad = [], 0
    for cid, what, mutate, cmd, want in CASES:
        with tempfile.TemporaryDirectory(prefix="flatcap-mut-") as t:
            d = Path(t)
            copy_tree(d, a.ref)
            try:
                env = mutate(d) if mutate else None
                env = env if isinstance(env, dict) else None  # a mutation may return extra environment variables
                r = subprocess.run([sys.executable, "scripts/build.py", cmd], cwd=d, capture_output=True, text=True, env={**os.environ, **(env or {})})
                out = (r.stdout + r.stderr).strip()
                rc = r.returncode
                if want and want.startswith("+") and rc == 0:  # a command that must succeed, after which --check must pass too
                    after = subprocess.run([sys.executable, "scripts/build.py", "--check"], cwd=d, capture_output=True, text=True, env={**os.environ, **(env or {})})
                    out += "\n" + (after.stdout + after.stderr).strip()
                    rc = after.returncode
            except AssertionError as e:  # the mutation itself did not apply: the case is broken, not the detector
                out, rc = f"MUTATION NOT APPLIED: {e}", -1
        if want is None:
            ok = rc == 0
        elif want.startswith("+"):
            ok = rc == 0 and want[1:] in out
        else:
            ok = rc not in (0, -1) and re.search(re.escape(want), out) is not None
        if cid == "privacy-13" and PRIV_WORD in out:  # a private pattern must never be echoed
            ok = False
        bad += not ok
        first = next((ln for ln in out.splitlines() if want and want in ln), out.splitlines()[0] if out else "")
        rows.append((cid, what, f"{cmd} -> exit {rc}", "PASS" if ok else "FAIL", first[:110]))
    w = [max(len(r[i]) for r in rows) for i in range(3)]
    for r in rows:
        print(f"{r[0]:<{w[0]}}  {r[1]:<{w[1]}}  {r[2]:<{w[2]}}  {r[3]}  | {r[4]}")
    print(f"{len(rows) - bad}/{len(rows)} cases as expected")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
