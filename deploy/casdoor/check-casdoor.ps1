param(
    [string]$Authority = "http://localhost:8000",
    [string]$Owner = "built-in",
    [string]$ApplicationOwner = "admin",
    [string]$ApplicationName = "osb-console",
    [string]$ClientId = "osb-console",
    [string[]]$DemoUsers = @("agent-demo", "admin-demo")
)

$ErrorActionPreference = "Stop"

function Write-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail = ""
    )
    if ($Detail) {
        Write-Output "[$Status] $Name - $Detail"
    } else {
        Write-Output "[$Status] $Name"
    }
}

$base = $Authority.TrimEnd("/")
$discoveryUrl = "$base/.well-known/openid-configuration"

try {
    $discovery = Invoke-RestMethod -Method Get -Uri $discoveryUrl -TimeoutSec 10
    Write-Check "discovery" "OK" $discoveryUrl
} catch {
    Write-Check "discovery" "FAIL" $_.Exception.Message
    exit 1
}

foreach ($field in @("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")) {
    if (-not $discovery.$field) {
        Write-Check "discovery.$field" "FAIL" "missing field"
        exit 1
    }
    Write-Check "discovery.$field" "OK" $discovery.$field
}

try {
    $jwks = Invoke-RestMethod -Method Get -Uri $discovery.jwks_uri -TimeoutSec 10
    $keyCount = @($jwks.keys).Count
    if ($keyCount -lt 1) {
        Write-Check "jwks" "FAIL" "no signing keys"
        exit 1
    }
    Write-Check "jwks" "OK" "$keyCount key(s)"
} catch {
    Write-Check "jwks" "FAIL" $_.Exception.Message
    exit 1
}

$appUrl = "$base/api/get-application?id=$ApplicationOwner/$ApplicationName"
try {
    $appResponse = Invoke-RestMethod -Method Get -Uri $appUrl -TimeoutSec 10
    if ($appResponse.status -ne "ok") {
        Write-Check "application" "WARN" "Casdoor returned status=$($appResponse.status)"
        exit 0
    }
    $app = $appResponse.data
    if ($app.clientId -ne $ClientId) {
        Write-Check "application.clientId" "WARN" "expected $ClientId, got $($app.clientId)"
    } else {
        Write-Check "application.clientId" "OK" $ClientId
    }
    Write-Check "application.redirectUris" "OK" (($app.redirectUris | ForEach-Object { $_ }) -join ", ")
    Write-Check "application.tokenFormat" "OK" $app.tokenFormat
    if ($app.grantTypes) {
        Write-Check "application.grantTypes" "OK" (($app.grantTypes | ForEach-Object { $_ }) -join ", ")
    }
    if ($app.tokenFields) {
        Write-Check "application.tokenFields" "OK" (($app.tokenFields | ForEach-Object { $_ }) -join ", ")
    }
} catch {
    Write-Check "application" "WARN" $_.Exception.Message
}

foreach ($userName in $DemoUsers) {
    $userUrl = "$base/api/get-user?id=$Owner/$userName"
    try {
        $userResponse = Invoke-RestMethod -Method Get -Uri $userUrl -TimeoutSec 10
        if ($userResponse.status -eq "ok" -and $userResponse.data.name -eq $userName) {
            Write-Check "user.$userName" "OK" $userUrl
        } else {
            Write-Check "user.$userName" "WARN" "not found or unexpected response"
        }
    } catch {
        Write-Check "user.$userName" "WARN" $_.Exception.Message
    }
}
