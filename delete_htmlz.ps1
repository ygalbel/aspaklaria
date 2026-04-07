$root = "C:\code\aspaklaria\mirror_httrack\www.aspaklaria.info"
$files = Get-ChildItem -Path $root -Recurse -File -Filter "*.z.html"
$count = $files.Count
if ($count -gt 0) {
  $files | Remove-Item -Force
}
Write-Output "Deleted $count .z.html files from $root"
