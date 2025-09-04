param(
  [Parameter(Mandatory=$true)][string]$Run,
  [string]$BaseUrl = "http://127.0.0.1:8000"
)

Write-Host "Run: $Run`n"

Write-Host "1) summary.json"
(Invoke-RestMethod "$BaseUrl/runs/$Run/summary.json" | ConvertTo-Json -Depth 6)

Write-Host "`n2) Amber+ (label_min)"
(Invoke-RestMethod "$BaseUrl/runs/$Run/appraisals.page.json?label_min=Amber&limit=10" | ConvertTo-Json -Depth 6)

Write-Host "`n3) score_min=0.7 (numeric)"
(Invoke-RestMethod "$BaseUrl/runs/$Run/appraisals.page.json?score_min=0.7&order_by=score_final&order_dir=desc&limit=10" | ConvertTo-Json -Depth 6)

Write-Host "`n4) Has rationale"
(Invoke-RestMethod "$BaseUrl/runs/$Run/appraisals.page.json?has_reason=true&limit=5" | ConvertTo-Json -Depth 6)
