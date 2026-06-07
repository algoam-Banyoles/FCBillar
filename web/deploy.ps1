<#
.SYNOPSIS
    Desplega el frontend (web/) a Vercel (projecte seguiment-lliga-open).

.DESCRIPTION
    El projecte de Vercel està connectat al repo GitHub de fcb-opens, i Vercel
    BLOQUEJA els desplegaments fets des de dins d'un altre repo Git (adjunta
    metadades Git alienes). Per evitar-ho, aquest script copia el codi font de
    web/ a una carpeta temporal FORA de cap repo Git i desplega des d'allà.

    Requisits: `vercel login` amb el compte que té "Albert's projects".
    Les env vars (PUBLIC_SUPABASE_URL / PUBLIC_SUPABASE_ANON_KEY) ja són al
    projecte de Vercel; el build les injecta.
#>
param([switch]$Preview)

$ErrorActionPreference = 'Stop'
$web = $PSScriptRoot
$tmp = Join-Path $env:TEMP ("fcbweb_deploy_{0}" -f (Get-Random))
$scope = 'alberts-projects-92d169cf'

New-Item -ItemType Directory -Force -Path "$tmp\src", "$tmp\.vercel" | Out-Null
foreach ($f in 'package.json','svelte.config.js','vite.config.ts','tailwind.config.js','postcss.config.js','tsconfig.json','.gitignore') {
    Copy-Item (Join-Path $web $f) (Join-Path $tmp $f) -Force
}
Copy-Item (Join-Path $web 'src\*') (Join-Path $tmp 'src') -Recurse -Force
if (Test-Path (Join-Path $web 'static')) { Copy-Item (Join-Path $web 'static') $tmp -Recurse -Force }
Copy-Item (Join-Path $web '.vercel\project.json') (Join-Path $tmp '.vercel\project.json') -Force

Push-Location $tmp
try {
    $prod = if ($Preview) { '' } else { '--prod' }
    Write-Host "Desplegant des de $tmp ..." -ForegroundColor Cyan
    & vercel deploy $prod --yes --scope $scope
} finally {
    Pop-Location
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
