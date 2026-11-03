# The helper's anti-throttling measures (POE_FLAGS, POE_WAKE, POE_FRONT) on and off, 6 pages each
# (both tabs take turns): which combinations draw, and how fast.  Report only.
param([string]$Exe, [string]$Drawio)
$lines = @('### Helper variants (6 pages each)', '| FLAGS | WAKE | FRONT | result | time |', '|---|---|---|---|---|')
foreach ($f in '1','0') { foreach ($w in '1','0') { foreach ($b in '1','0') {
  $env:POE_FLAGS = $f; $env:POE_WAKE = $w; $env:POE_FRONT = $b
  $files = @()
  foreach ($i in 1..6) { $files += 'ci\parity_page.drawio'; $files += "out\v_$f$w$b`_$i.png" }
  $t = Measure-Command { $o = & $Exe render --drawio $Drawio -s 5 -t @files 2>&1 | Out-String }
  $n = (Get-ChildItem "out\v_$f$w$b`_*.png" -ErrorAction SilentlyContinue).Count
  $res = if ($n -eq 6) { 'ok' } else { "$n of 6: " + (($o -split "`n" | Where-Object { $_ -match 'Error' } | Select-Object -Last 1) -replace '\|', '/').Trim() }
  $lines += "| $f | $w | $b | $res | $([math]::Round($t.TotalSeconds, 1)) s |"
  Write-Host "FLAGS=$f WAKE=$w FRONT=$b -> $res in $([math]::Round($t.TotalSeconds, 1)) s"
}}}
Remove-Item env:POE_FLAGS, env:POE_WAKE, env:POE_FRONT
$lines -join "`n" | Out-File -Append -Encoding utf8 $env:GITHUB_STEP_SUMMARY
