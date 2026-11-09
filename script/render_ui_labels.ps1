# Render Simplified-Chinese UI labels into a transparent PNG via GDI+ (System.Drawing).
#
# Input: a JSON spec (UTF-8):
#   { "width":221, "height":199, "size":16, "font":"<path to .otf>",
#     "color":[r,g,b], "items":[ {"text":"...","x":25,"y":-3}, ... ] }
# Output: 32bpp ARGB PNG (straight alpha).
#
# Why PowerShell: this project only depends on the Python standard library and has no
# glyph rasteriser; GDI+ is available on Windows. Label text is passed through JSON so
# the script file itself stays ASCII (Windows PowerShell would otherwise mis-read UTF-8
# without a BOM).
param(
  [Parameter(Mandatory = $true)][string]$Spec,
  [Parameter(Mandatory = $true)][string]$Out
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$json = [System.IO.File]::ReadAllText($Spec, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
# scale > 1 时先在放大画布上渲染，再由调用方做盒式降采样（超采样）：这是标准的栅格化做法，
# 和"合成粗体"不同，不改变字形设计，只让边缘与字重更平滑。
$scale = 1
if ($json.PSObject.Properties.Name -contains 'scale' -and $json.scale) { $scale = [int]$json.scale }
$pfc = New-Object System.Drawing.Text.PrivateFontCollection
$pfc.AddFontFile($json.font)
$fam = $pfc.Families[0]
# style: Regular / Bold（字体本身没有粗体时由 GDI+ 合成，与对照图的取法一致）
$styleName = 'Regular'
if ($json.PSObject.Properties.Name -contains 'style' -and $json.style) { $styleName = [string]$json.style }
$style = [System.Drawing.FontStyle]::$styleName
# 只接受真实存在的字形：字体本身没有粗体时 GDI+ 会"合成"一个假粗体（笔画被硬加粗），
# 那和真正的粗体设计不是一回事，必须报错，让调用方换真实字重的字体文件。
if (-not $fam.IsStyleAvailable($style)) {
  [Console]::Error.WriteLine(('style ' + $styleName + ' is not a real face of ' + $fam.Name + '; provide the real font file instead of relying on synthetic bold'))
  exit 2
}
$font = New-Object System.Drawing.Font -ArgumentList $fam, ([single]$json.size * $scale), $style, ([System.Drawing.GraphicsUnit]::Pixel)
$bmp = New-Object System.Drawing.Bitmap -ArgumentList ([int]$json.width * $scale), ([int]$json.height * $scale), ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::Transparent)
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
$col = [System.Drawing.Color]::FromArgb(255, [int]$json.color[0], [int]$json.color[1], [int]$json.color[2])
$brush = New-Object System.Drawing.SolidBrush -ArgumentList $col
foreach ($item in $json.items) {
  $pt = New-Object System.Drawing.PointF -ArgumentList ([single]$item.x * $scale), ([single]$item.y * $scale)
  $g.DrawString([string]$item.text, $font, $brush, $pt)
}
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("rendered " + $Out + " family=" + $fam.Name + " style=" + $styleName + " size=" + $json.size)
