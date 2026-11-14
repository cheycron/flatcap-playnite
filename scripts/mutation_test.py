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
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLATE = "themes/Desktop/Flatcap_Slate_Desktop"
DAY = "themes/Desktop/Flatcap_Daylight_Desktop"
PTHM_SLATE = "dist/Flatcap_Slate_Desktop_2_0_0.pthm"
PTHM_DAY = "dist/Flatcap_Daylight_Desktop_2_0_0.pthm"
UP = "upstream/playnite-10.64"
# the private strings are assembled here so that this file does not trip the privacy scan itself
WIN_PATH = "C:" + "\\" + "Users" + "\\" + "someone" + "\\" + "file"
HOME_PATH = "/ho" + "me/someone/file"
IP10, IP172, IP192 = "10." + "1.2.3", "172." + "20.4.5", "192." + "168.1.20"
HOST = "nas" + "." + "lan"


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


def lower_contrast(d: Path):
    f = d / "src/theme.json"
    j = json.loads(f.read_text(encoding="utf-8"))
    j["themes"]["slate"]["text.secondary"] = j["themes"]["slate"]["bg.surface"]
    f.write_text(json.dumps(j, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
                if mutate:
                    mutate(d)
                r = subprocess.run([sys.executable, "scripts/build.py", cmd], cwd=d, capture_output=True, text=True)
                out = (r.stdout + r.stderr).strip()
                rc = r.returncode
            except AssertionError as e:  # the mutation itself did not apply: the case is broken, not the detector
                out, rc = f"MUTATION NOT APPLIED: {e}", -1
        if want is None:
            ok = rc == 0
        else:
            ok = rc not in (0, -1) and re.search(re.escape(want), out) is not None
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
