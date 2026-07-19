# Plug-and-play setup for the Mac/Win Controller server on Windows 10/11.
# Idempotent + non-destructive: re-running never clobbers an existing .env, venv, or certificates.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a no-BOM script
# as the system ANSI codepage, so non-ASCII glyphs (checkmarks, em dashes, smart
# quotes) get mis-decoded and can prematurely terminate strings, corrupting the
# whole parse. Plain ASCII avoids any encoding dependency.

$ErrorActionPreference = "Stop"

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)  { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg){ Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Die($msg) { Write-Host "  [X] $msg" -ForegroundColor Red; exit 1 }

# Refresh this session's PATH from the machine + user scopes. winget/choco update
# PATH at those scopes but not the running shell, so a freshly installed tool
# (mkcert) is otherwise "not recognized" until you restart PowerShell.
function Update-SessionPath {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = ($machine, $user | Where-Object { $_ }) -join ";"
}

Set-Location $PSScriptRoot

# ---- 1. Check dependencies ----
Say "Checking Python and mkcert"
# Resolve a REAL Python interpreter. Prefer the 'py' launcher: it bypasses the
# Microsoft Store 'python.exe' alias stub, which resolves via Get-Command but only
# prints "install from the Microsoft Store" and cannot actually create a venv.
$PyExe  = $null
$PyArgs = @()
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $PyExe = "py"; $PyArgs = @("-3")
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $src = (Get-Command "python").Source
    if ($src -like "*\WindowsApps\*") {
        Die "Only the Microsoft Store alias for 'python' is on PATH (a stub that can't create venvs). Turn it OFF under Settings > Apps > Advanced app settings > App execution aliases (python.exe AND python3.exe), OR install Python from python.org with 'Add python.exe to PATH'. Then reopen PowerShell and re-run .\setup.ps1"
    }
    $PyExe = $src
} else {
    Die "python not found - install Python 3.12 ('winget install -e --id Python.Python.3.12' or python.org with 'Add to PATH'), reopen PowerShell, and re-run."
}
Ok "Python found ($PyExe $PyArgs)"

if (-not (Get-Command "mkcert" -ErrorAction SilentlyContinue)) {
    Say "mkcert not found. Trying to install via winget or choco..."
    if (Get-Command "winget" -ErrorAction SilentlyContinue) {
        winget install -e --id FiloSottile.mkcert --accept-source-agreements --accept-package-agreements
    } elseif (Get-Command "choco" -ErrorAction SilentlyContinue) {
        choco install mkcert -y
    } else {
        Die "mkcert not found and winget/choco not available. Please install mkcert from https://github.com/FiloSottile/mkcert"
    }

    # The installer updated PATH at the machine/user scope; pull that into this
    # session so mkcert is usable now instead of after a shell restart.
    Update-SessionPath
    if (-not (Get-Command "mkcert" -ErrorAction SilentlyContinue)) {
        Die "mkcert was installed but is not on PATH in this session. Close and reopen PowerShell, then re-run .\setup.ps1"
    }
}
Ok "mkcert present"

# Install local root CA
Say "Checking/Installing mkcert local CA (may ask for a confirmation dialog)"
mkcert -install
Ok "mkcert local CA installed"

# ---- 2. Python virtualenv + dependencies ----
if (Test-Path "venv\Scripts\python.exe") {
    Ok "venv already exists"
} else {
    if (Test-Path "venv") { Remove-Item -Recurse -Force "venv" }  # clean a half-made / broken venv
    Say "Creating Python virtualenv"
    & $PyExe @PyArgs -m venv venv
    if (-not (Test-Path "venv\Scripts\python.exe")) {
        Die "venv creation failed - '.\venv\Scripts\python.exe' is missing. The 'python' that ran was almost certainly the Microsoft Store stub. Disable the App execution aliases (Settings > Apps > Advanced app settings > App execution aliases), or install a real Python from python.org, then re-run."
    }
    Ok "venv created"
}

Say "Installing Windows dependencies (this can take a few minutes the first time)"
# $ErrorActionPreference does NOT stop on a native exe's non-zero exit, so check
# $LASTEXITCODE explicitly - otherwise a failed pip resolve prints "[OK]" and the
# server then dies on a missing module (e.g. dotenv).
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements-win.txt
if ($LASTEXITCODE -ne 0) {
    Die "pip failed to install requirements-win.txt (exit $LASTEXITCODE). Fix the error printed above and re-run .\setup.ps1"
}
Ok "Windows dependencies installed"

# ---- 3. TLS certificates ----
if ((Test-Path "cert.pem") -and (Test-Path "key.pem")) {
    Ok "TLS certs (cert.pem/key.pem) already exist - skipping"
} else {
    $LocalName = "$env:COMPUTERNAME.local"

    # Include the Tailscale FQDN as a SAN if Tailscale is installed at setup time.
    # Lets the same cert serve LAN (.local) and internet (Tailscale) entry points
    # without a follow-up regen. Silent no-op if Tailscale isn't installed.
    $TsFqdn = ""
    if (Get-Command "tailscale" -ErrorAction SilentlyContinue) {
        try {
            $tsJson = (& tailscale status --json 2>$null) | Out-String
            if ($tsJson) {
                $tsData = $tsJson | ConvertFrom-Json -ErrorAction SilentlyContinue
                if ($tsData -and $tsData.Self -and $tsData.Self.DNSName) {
                    $TsFqdn = $tsData.Self.DNSName.TrimEnd('.')
                }
            }
        } catch { $TsFqdn = "" }
    }
    if ($TsFqdn) { Ok "Tailscale detected: $TsFqdn - including as SAN" }

    $MkcertArgs = @($LocalName, "localhost", "127.0.0.1", "::1")
    if ($TsFqdn) { $MkcertArgs += $TsFqdn }
    Say ("Generating TLS cert for: " + ($MkcertArgs -join " "))
    mkcert -cert-file cert.pem -key-file key.pem @MkcertArgs
    Ok ("Wrote cert.pem + key.pem (covers $LocalName" + $(if ($TsFqdn) { " + $TsFqdn" } else { "" }) + ")")
}

# ---- 4. .env ----
if (Test-Path ".env") {
    Ok ".env already exists - leaving it untouched"
} else {
    Say "Writing .env"
    $Secret = .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
    $WebAppUrl = $env:WEB_APP_URL
    if (-not $WebAppUrl) { $WebAppUrl = "https://mac-remote.gaurangnandaniya.com" }
    $MaxDevices = $env:MAX_DEVICES
    if (-not $MaxDevices) { $MaxDevices = "5" }

    # ASCII encoding avoids a UTF-8 BOM, which would prepend bytes to the first
    # key and can trip python-dotenv's parse of AUTH_SECRET_KEY.
    @"
# Generated by setup.ps1
AUTH_SECRET_KEY=$Secret
MAX_DEVICES=$MaxDevices
WEB_APP_URL=$WebAppUrl
CERTIFICATE_PATH=./cert.pem
PRIVATE_KEY_PATH=./key.pem
"@ | Out-File -FilePath ".env" -Encoding ascii
    Ok ".env created"
}

# ---- Done ----
$CaRoot = mkcert -CAROOT
Write-Host "`nSetup complete.`n" -ForegroundColor Green
Write-Host @"
Next steps:
  1. Install the mkcert root CA on your iPhone:
       - rootCA.pem is here:  $CaRoot\rootCA.pem
       - Email/AirDrop it to the iPhone -> install profile (Settings -> Profile Downloaded -> Install)

  2. ENABLE FULL TRUST  (required on iOS):
       - Settings -> General -> About -> Certificate Trust Settings
       - Turn ON "Full Trust" for the "mkcert ..." certificate

  3. Start the server (run the venv's own Python directly - no activation needed):
       .\venv\Scripts\python.exe app.py
     Or activate the venv first, then run (PowerShell uses Activate.ps1, NOT 'activate'):
       .\venv\Scripts\Activate.ps1
       python app.py
     (If Activate.ps1 is blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

  4. Open the system tray QR code and scan it from the web app to pair.
"@
