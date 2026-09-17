# Releve les moniteurs de CETTE machine et l'ecrit la ou l'API va le lire.
#
# Pourquoi ce script : l'API releve les ecrans elle-meme (app/services/
# materiel.py), mais sur le stand elle tourne en conteneur Linux, qui ne voit
# aucun moniteur. Windows fait donc le releve, le conteneur le lit.
#
#   powershell -ExecutionPolicy Bypass -File scripts\relever-ecrans.ps1
#
# A relancer apres tout changement de disposition -- ecran debranche,
# rebranche sur une autre prise, ou deux moniteurs intervertis -- puis
# regenerer le lanceur depuis Reglages > Ecrans.
param(
  [string]$Sortie = (Join-Path $PSScriptRoot "..\.run\materiel\materiels.json")
)

Add-Type -AssemblyName System.Windows.Forms

$ecrans = [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
  [ordered]@{
    peripherique = $_.DeviceName
    modele       = ""
    x            = $_.Bounds.X
    y            = $_.Bounds.Y
    largeur      = $_.Bounds.Width
    hauteur      = $_.Bounds.Height
    principal    = $_.Primary
  } | ConvertTo-Json -Compress
}

# Un tableau d'un seul element se serialise en objet sous PowerShell 5.1 :
# on assemble le JSON nous-memes plutot que de dependre de ce piege.
$corps = @"
{
  "releve_le": "$((Get-Date).ToUniversalTime().ToString("o"))",
  "systeme": "Windows",
  "ecrans": [$($ecrans -join ",")],
  "indisponible": null
}
"@

$dossier = Split-Path -Parent $Sortie
if (-not (Test-Path $dossier)) { New-Item -ItemType Directory -Force -Path $dossier | Out-Null }
# Sans BOM : le conteneur lit ce fichier en UTF-8, et json.loads refuse un BOM.
[System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $dossier).Path + "\" + (Split-Path -Leaf $Sortie), $corps, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "$($ecrans.Count) ecran(s) releve(s) dans $Sortie"
