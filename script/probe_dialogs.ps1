<#
.SYNOPSIS
启动游戏并把运行期弹窗（System.inform）的文字抓成 UTF-8 文本。

.DESCRIPTION
本作的运行期判据只能靠「钩子/脚本里 System.inform 一段文字」暴露出来。
这个脚本负责：备份玩家设置 → 启动 nine_kokoiro.exe → 轮询窗口 → 只抓 #32770 对话框里除“确定”外的文字
→ 关掉对话框 → 写文件 → **优雅关闭**游戏（WM_CLOSE，让存档/配置落盘）。

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File script/probe_dialogs.ps1
# 结果写到 tmp/probe_dialogs.txt（同一段文字只记一次）

.NOTES
坑（都踩过）：
* 游戏是单实例锁（system/initialize.tjs 的 createAppLock）：已在运行时新进程会立刻退出，
  所以先优雅关闭旧实例；只有加 -Force 才会强杀。
* **不要强杀**：Konfig/存档来不及落盘，玩家设置（分辨率、音量、语言）会回默认。
* **不要在 after-init 里弹 inform**：阻塞对话框会让主窗口底部留一条白边，且要重启才恢复。
  能用一次启动就取到的信息就别放 after-init。
* 每次运行前都会把 %APPDATA%\ぱれっと\nine_kokoiro 备份到 tmp/backup/settings_<时间戳>，
  测完可以整目录还原。
#>
param(
  [string]$Exe = 'E:\SteamLibrary\steamapps\common\nine_kokoiro\nine_kokoiro.exe',
  [string]$Out = 'tmp\probe_dialogs.txt',
  [int]$Seconds = 20,
  [switch]$Force
)
$ErrorActionPreference = 'Continue'

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class KDialogProbe2 {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc f, IntPtr p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
}
'@

# --- 1) 备份玩家设置（Konfig / 存档）
$settings = Join-Path $env:APPDATA 'ぱれっと\nine_kokoiro'
if (Test-Path $settings) {
  $stamp = Get-Date -Format 'MMdd_HHmmss'
  $bak = Join-Path 'tmp\backup' ('settings_' + $stamp)
  New-Item -ItemType Directory -Force -Path $bak | Out-Null
  Copy-Item -Recurse -Force (Join-Path $settings '*') $bak
  Write-Output ('settings backup -> ' + $bak)
}

# --- 2) 关掉已在跑的实例（优雅；-Force 才强杀）
$running = @(Get-Process | Where-Object { $_.ProcessName -like 'nine_kokoiro*' })
if ($running.Count -gt 0) {
  if ($Force) {
    $running | Stop-Process -Force
  } else {
    $cbClose = [KDialogProbe2+EnumProc]{
      param($h, $l)
      $wpid = 0
      [void][KDialogProbe2]::GetWindowThreadProcessId($h, [ref]$wpid)
      if ($running.Id -notcontains [int]$wpid) { return $true }
      $cls = New-Object System.Text.StringBuilder 256
      [void][KDialogProbe2]::GetClassNameW($h, $cls, 256)
      if ($cls.ToString() -eq 'TVPMainWindow') {
        [void][KDialogProbe2]::PostMessageW($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
      }
      return $true
    }
    [void][KDialogProbe2]::EnumWindows($cbClose, [IntPtr]::Zero)
  }
  Start-Sleep -Seconds 5
}

$rows = New-Object System.Collections.Generic.List[string]
$seen = New-Object System.Collections.Generic.List[string]
$proc = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) -PassThru
[void]$rows.Add('started pid=' + $proc.Id)

# --- 3) 轮询弹窗文字
$iterations = [int]($Seconds * 2.5)
for ($t = 0; $t -lt $iterations; $t++) {
  Start-Sleep -Milliseconds 400
  $pids = @(Get-Process | Where-Object { $_.ProcessName -like 'nine_kokoiro*' } | ForEach-Object { [int]$_.Id })
  if ($pids.Count -eq 0) { continue }
  $cb = [KDialogProbe2+EnumProc]{
    param($h, $l)
    $wpid = 0
    [void][KDialogProbe2]::GetWindowThreadProcessId($h, [ref]$wpid)
    if ($pids -notcontains [int]$wpid) { return $true }
    $cls = New-Object System.Text.StringBuilder 256
    [void][KDialogProbe2]::GetClassNameW($h, $cls, 256)
    if ($cls.ToString() -ne '#32770') { return $true }
    $buf = New-Object System.Text.StringBuilder
    $ccb = [KDialogProbe2+EnumProc]{
      param($ch, $cl)
      $ct = New-Object System.Text.StringBuilder 8192
      [void][KDialogProbe2]::GetWindowTextW($ch, $ct, 8192)
      $s = $ct.ToString()
      if ($s.Length -gt 0 -and $s -ne '确定' -and $s -ne 'OK' -and $s -ne 'Yes' -and $s -ne '是') { [void]$buf.Append($s) }
      return $true
    }
    [void][KDialogProbe2]::EnumChildWindows($h, $ccb, [IntPtr]::Zero)
    $txt = $buf.ToString()
    if ($txt.Length -gt 0 -and -not $seen.Contains($txt)) {
      $seen.Add($txt)
      [void]$rows.Add('TEXT ' + $txt)
    }
    [void][KDialogProbe2]::PostMessageW($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    return $true
  }
  [void][KDialogProbe2]::EnumWindows($cb, [IntPtr]::Zero)
}

# --- 4) 优雅关闭（让 Konfig/存档落盘）
$live = @(Get-Process | Where-Object { $_.ProcessName -like 'nine_kokoiro*' })
if ($live.Count -gt 0) {
  $cbEnd = [KDialogProbe2+EnumProc]{
    param($h, $l)
    $wpid = 0
    [void][KDialogProbe2]::GetWindowThreadProcessId($h, [ref]$wpid)
    if ($live.Id -notcontains [int]$wpid) { return $true }
    $cls = New-Object System.Text.StringBuilder 256
    [void][KDialogProbe2]::GetClassNameW($h, $cls, 256)
    if ($cls.ToString() -eq 'TVPMainWindow') {
      [void][KDialogProbe2]::PostMessageW($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    }
    return $true
  }
  [void][KDialogProbe2]::EnumWindows($cbEnd, [IntPtr]::Zero)
  Start-Sleep -Seconds 5
  $still = @(Get-Process | Where-Object { $_.ProcessName -like 'nine_kokoiro*' })
  [void]$rows.Add('after-close remaining: ' + (($still | ForEach-Object { $_.Id }) -join ','))
}

$dir = Split-Path $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
[IO.File]::WriteAllLines($Out, $rows, (New-Object Text.UTF8Encoding($false)))
Write-Output ('dialogs=' + $seen.Count + ' -> ' + $Out)
