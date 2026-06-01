<#
Simple helper to remove the local test installation of this app.
Run this from the repository folder in PowerShell.
#>

$appFolder = Join-Path $PSScriptRoot 'ForensicAIAgent'
if (Test-Path $appFolder) {
    Write-Host "Removing local app folder: $appFolder"
    Remove-Item -Path $appFolder -Recurse -Force
} else {
    Write-Host "No local app folder found at: $appFolder"
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "Ollama CLI detected. To remove the downloaded model, run:"
    Write-Host "  ollama rm llama3.2:3b"
} else {
    Write-Host "Ollama CLI not found. If you installed Ollama on Windows, uninstall it from Settings > Apps."
}
