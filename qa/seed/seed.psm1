# QA-only Playnite script extension: fills an empty, isolated, portable library with a neutral DEMO set.
# Titles are invented; covers are drawn here (flat color, geometric shape, title). Never install it in a real library.
function OnApplicationStarted {
    $log = Join-Path $PSScriptRoot 'seed.log'
    try {
        if ($PlayniteApi.Database.Games.Count -gt 0) { 'library not empty: nothing done' | Out-File $log; return }
        Add-Type -AssemblyName System.Drawing
        $tmp = Join-Path $PSScriptRoot 'covers'
        New-Item -ItemType Directory -Force $tmp | Out-Null
        $games = @(
            @('Lantern Harbor',  'Adventure', '2019', 82, $true,  $true,  1420, 12, '#2f6f9f', 'circle'),
            @('Quiet Orbit',     'Puzzle',    '2021', 74, $true,  $false, 310,  3,  '#7a4fa3', 'ring'),
            @('Paper Tide',      'Platformer','2018', 68, $true,  $false, 5400, 21, '#2e8b6a', 'wave'),
            @('Copper Steppe',   'Strategy',  '2020', 91, $true,  $true,  18200,40, '#b5651d', 'tri'),
            @('Glass Meridian',  'Adventure', '2022', 57, $false, $false, 0,    0,  '#3a7d8c', 'ring'),
            @('Low Tide Radio',  'Simulation','2017', 79, $true,  $false, 960,  6,  '#a33f5a', 'wave'),
            @('Ember Cartographer','Strategy','2023', 88, $true,  $false, 7300, 15, '#c0562b', 'tri'),
            @('Moss and Mortar', 'Simulation','2016', 63, $false, $false, 0,    0,  '#4f7a3a', 'circle'),
            @('Static Garden',   'Puzzle',    '2024', 71, $true,  $false, 180,  2,  '#556b9c', 'ring'),
            @('Northwind Relay', 'Platformer','2015', 85, $true,  $true,  2600, 9,  '#2b5c8a', 'tri'),
            @('Saltglass',       'Adventure', '2021', 66, $false, $false, 0,    0,  '#6b8e9b', 'wave'),
            @('Tin Lantern',     'Puzzle',    '2019', 77, $true,  $false, 540,  4,  '#8a6d1f', 'circle')
        )
        $gen = @{}
        foreach ($n in ($games | % { $_[1] } | Sort-Object -Unique)) { $gen[$n] = $PlayniteApi.Database.Genres.Add($n) }
        $i = 0
        foreach ($d in $games) {
            $i++
            $g = New-Object Playnite.SDK.Models.Game $d[0]
            $g.Description = "<p><b>$($d[0])</b> is an invented title used to test the Flatcap theme. Its text, cover and numbers are made up for the demonstration.</p><p>Second paragraph: body text, <a href='https://example.org'>a link</a> and some more words to see how a description wraps in the details view.</p>"
            $g.ReleaseDate = New-Object Playnite.SDK.Models.ReleaseDate ([int]$d[2])
            $g.CommunityScore = [int]$d[3]
            $g.CriticScore = [int]$d[3] - 6
            $g.IsInstalled = [bool]$d[4]
            if ($g.IsInstalled) { $g.InstallDirectory = 'C:\Demo\' + $d[0] }
            $g.Favorite = [bool]$d[5]
            $g.Playtime = [uint64]$d[6]
            $g.PlayCount = [uint64]$d[7]
            $g.Added = (Get-Date '2026-01-01').AddDays($i * 3)
            if ($d[7] -gt 0) { $g.LastActivity = (Get-Date '2026-10-01').AddDays($i) }
            $gl = New-Object 'System.Collections.Generic.List[guid]'
            $gl.Add($gen[$d[1]].Id)
            $g.GenreIds = $gl
            $p = Join-Path $tmp ("cover$i.png")
            $bmp = New-Object System.Drawing.Bitmap 600, 900
            $gr = [System.Drawing.Graphics]::FromImage($bmp)
            $gr.SmoothingMode = 'AntiAlias'; $gr.TextRenderingHint = 'AntiAlias'
            $base = [System.Drawing.ColorTranslator]::FromHtml($d[8])
            $gr.Clear($base)
            $light = [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
            $br = New-Object System.Drawing.SolidBrush $light
            $pen = New-Object System.Drawing.Pen ($light, 26)
            switch ($d[9]) {
                'circle' { $gr.FillEllipse($br, 120, 150, 360, 360) }
                'ring'   { $gr.DrawEllipse($pen, 130, 160, 340, 340) }
                'tri'    { $gr.FillPolygon($br, [System.Drawing.Point[]]@((New-Object System.Drawing.Point 300, 130), (New-Object System.Drawing.Point 500, 520), (New-Object System.Drawing.Point 100, 520))) }
                'wave'   { for ($k = 0; $k -lt 4; $k++) { $gr.DrawArc($pen, 60 + $k * 20, 180 + $k * 70, 480 - $k * 40, 160, 0, 180) } }
            }
            $f = New-Object System.Drawing.Font 'Segoe UI', 44, ([System.Drawing.FontStyle]::Bold), 'Pixel'
            $sf = New-Object System.Drawing.StringFormat; $sf.Alignment = 'Center'; $sf.LineAlignment = 'Far'
            $gr.DrawString($d[0], $f, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF 30, 560, 540, 300), $sf)
            $gr.Dispose(); $bmp.Save($p, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
            $g.CoverImage = $PlayniteApi.Database.AddFile($p, $g.Id)
            [void]$PlayniteApi.Database.Games.Add($g)
        }
        "seeded $i games" | Out-File $log
    } catch { "ERROR: $($_ | Out-String)" | Out-File $log }
}
