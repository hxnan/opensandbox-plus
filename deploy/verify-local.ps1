param(
    [string]$ComposeFile = "deploy/docker-compose.yml",
    [string]$PlusUrl = "http://localhost:8080",
    [string]$CasdoorUrl = "http://localhost:8000",
    [int]$TimeoutSeconds = 120,
    [switch]$Start,
    [switch]$Migrate,
    [switch]$ConfigOnly,
    [switch]$SkipCasdoorApplication,
    [switch]$RunBusinessFlow,
    [switch]$UseDemoTokens,
    [string]$AgentBearerToken = $env:OSB_PLUS_VERIFY_AGENT_TOKEN,
    [string]$AdminBearerToken = $env:OSB_PLUS_VERIFY_ADMIN_TOKEN,
    [string]$CasdoorClientId = "osb-console",
    [string]$CasdoorScope = "openid profile email",
    [string]$AgentUsername = "agent-demo",
    [string]$AgentPassword = "123456",
    [string]$AdminUsername = "admin-demo",
    [string]$AdminPassword = "123456",
    [string]$CasdoorApplicationOwner = "admin",
    [string]$SandboxImage = "python:3.12-slim",
    [int]$SandboxTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

function Write-Result {
    param(
        [string]$Status,
        [string]$Name,
        [string]$Detail = ""
    )
    if ($Detail) {
        Write-Output "[$Status] $Name - $Detail"
    } else {
        Write-Output "[$Status] $Name"
    }
}

function Invoke-Checked {
    param(
        [string]$Name,
        [string[]]$Command
    )
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = & $Command[0] @($Command | Select-Object -Skip 1) 2>&1
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($LASTEXITCODE -ne 0) {
            throw ($output | Out-String)
        }
        Write-Result "OK" $Name
        return $output
    } catch {
        Write-Result "FAIL" $Name $_.Exception.Message
        throw
    }
}

function Wait-HttpJson {
    param(
        [string]$Name,
        [string]$Url,
        [scriptblock]$Validate
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 5
            if (& $Validate $response) {
                Write-Result "OK" $Name $Url | Out-Host
                return $response
            }
            $lastError = "unexpected response"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    Write-Result "FAIL" $Name $lastError | Out-Host
    throw "$Name did not become ready"
}

function Wait-HttpText {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Contains
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $Url -TimeoutSec 5
            if ($response.Content -like "*$Contains*") {
                Write-Result "OK" $Name $Url
                return
            }
            $lastError = "response did not contain '$Contains'"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    Write-Result "FAIL" $Name $lastError
    throw "$Name did not become ready"
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    $command = @("docker", "compose", "-f", $ComposeFile) + $ComposeArgs
    return Invoke-Checked -Name ("docker compose " + ($ComposeArgs -join " ")) -Command $command
}

function Invoke-ComposeWarn {
    param(
        [string]$Name,
        [string[]]$ComposeArgs
    )
    try {
        $command = @("docker", "compose", "-f", $ComposeFile) + $ComposeArgs
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = & $command[0] @($command | Select-Object -Skip 1) 2>&1
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Result "WARN" $Name ($output | Out-String)
            return $false
        }
        Write-Result "OK" $Name
        return $true
    } catch {
        Write-Result "WARN" $Name $_.Exception.Message
        return $false
    }
}

function Invoke-Json {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        [object]$Body = $null
    )
    try {
        $params = @{
            Method = $Method
            Uri = $Url
            Headers = $Headers
            TimeoutSec = 30
        }
        if ($null -ne $Body) {
            $params["ContentType"] = "application/json"
            $params["Body"] = ($Body | ConvertTo-Json -Depth 20)
        }
        $response = Invoke-RestMethod @params
        Write-Result "OK" $Name $Url | Out-Host
        return $response
    } catch {
        Write-Result "FAIL" $Name $_.Exception.Message | Out-Host
        throw
    }
}

function Get-SandboxId {
    param([object]$Payload)
    if ($Payload -is [string]) {
        try {
            $Payload = $Payload | ConvertFrom-Json
        } catch {
            return $null
        }
    }
    foreach ($name in @("id", "sandboxId", "sandbox_id")) {
        if ($Payload.PSObject.Properties.Name -contains $name) {
            $value = $Payload.$name
            if ($value) {
                return [string]$value
            }
        }
    }
    if ($Payload.PSObject.Properties.Name -contains "data" -and $Payload.data) {
        return Get-SandboxId -Payload $Payload.data
    }
    return $null
}

function Test-SandboxListContains {
    param(
        [object]$Payload,
        [string]$SandboxId
    )
    if ($Payload -is [string]) {
        try {
            $Payload = $Payload | ConvertFrom-Json
        } catch {
            return $false
        }
    }
    foreach ($name in @("items", "sandboxes", "data")) {
        if ($Payload.PSObject.Properties.Name -contains $name -and $Payload.$name) {
            foreach ($item in @($Payload.$name)) {
                if ((Get-SandboxId -Payload $item) -eq $SandboxId) {
                    return $true
                }
            }
        }
    }
    return $false
}

function Assert-Unauthorized {
    param(
        [string]$Name,
        [string]$Url,
        [hashtable]$Headers
    )
    try {
        Invoke-WebRequest -UseBasicParsing -Method Get -Uri $Url -Headers $Headers -TimeoutSec 30 | Out-Null
        Write-Result "FAIL" $Name "expected HTTP 401"
        throw "$Name expected HTTP 401"
    } catch {
        $response = $_.Exception.Response
        if ($response -and [int]$response.StatusCode -eq 401) {
            Write-Result "OK" $Name "HTTP 401"
            return
        }
        Write-Result "FAIL" $Name $_.Exception.Message
        throw
    }
}

function Get-CasdoorAccessToken {
    param(
        [string]$Name,
        [string]$Username,
        [string]$Password
    )
    $tokenUrl = "$($CasdoorUrl.TrimEnd('/'))/api/login/oauth/access_token"
    $query = @{
        grant_type = "password"
        client_id = $CasdoorClientId
        username = $Username
        password = $Password
        scope = $CasdoorScope
    }.GetEnumerator() | ForEach-Object {
        "$([uri]::EscapeDataString([string]$_.Key))=$([uri]::EscapeDataString([string]$_.Value))"
    }
    try {
        $response = Invoke-RestMethod -Method Post -Uri "$tokenUrl`?$($query -join '&')" -TimeoutSec 30
        $accessToken = $response.access_token
        if (-not $accessToken -and $response.accessToken) {
            $accessToken = $response.accessToken
        }
        if (-not $accessToken) {
            Write-Result "FAIL" $Name "token response did not include access_token" | Out-Host
            throw "access_token missing"
        }
        Write-Result "OK" $Name $Username | Out-Host
        return [string]$accessToken
    } catch {
        Write-Result "FAIL" $Name $_.Exception.Message | Out-Host
        throw
    }
}

function Invoke-BusinessFlow {
    if ($UseDemoTokens) {
        if (-not $AgentBearerToken) {
            $AgentBearerToken = Get-CasdoorAccessToken `
                -Name "casdoor agent demo token" `
                -Username $AgentUsername `
                -Password $AgentPassword
        }
        if (-not $AdminBearerToken) {
            $AdminBearerToken = Get-CasdoorAccessToken `
                -Name "casdoor admin demo token" `
                -Username $AdminUsername `
                -Password $AdminPassword
        }
    }

    if (-not $AgentBearerToken) {
        Write-Result "FAIL" "business flow" "missing AgentBearerToken or OSB_PLUS_VERIFY_AGENT_TOKEN"
        throw "AgentBearerToken is required when RunBusinessFlow is set; pass -UseDemoTokens for local seed users"
    }

    $base = $PlusUrl.TrimEnd("/")
    $agentHeaders = @{ Authorization = "Bearer $AgentBearerToken" }
    $agentMe = Invoke-Json `
        -Name "agent current user" `
        -Method "GET" `
        -Url "$base/api/v1/me" `
        -Headers $agentHeaders
    if (-not $agentMe.subject_id) {
        Write-Result "FAIL" "agent current user" "response did not include subject_id"
        throw "agent subject_id missing"
    }

    $credentialName = "verify-local-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
    $credential = Invoke-Json `
        -Name "agent issue cloud sandbox key" `
        -Method "POST" `
        -Url "$base/api/v1/cloud-sandbox/credentials" `
        -Headers $agentHeaders `
        -Body @{ name = $credentialName; agent_id = "verify-local"; expires_in_days = 1 }

    if (-not $credential.key) {
        Write-Result "FAIL" "agent issue cloud sandbox key" "response did not include key"
        throw "cloud sandbox credential key missing"
    }

    $cloudHeaders = @{ "OPEN-SANDBOX-API-KEY" = [string]$credential.key }
    $sandbox = Invoke-Json `
        -Name "cloud key create sandbox" `
        -Method "POST" `
        -Url "$base/v1/sandboxes" `
        -Headers $cloudHeaders `
        -Body @{
            image = @{ uri = $SandboxImage }
            timeout = $SandboxTimeoutSeconds
            entrypoint = @("python", "-u", "-c", "import time; time.sleep(3600)")
            resourceLimits = @{ cpu = "500m"; memory = "512Mi" }
        }
    $sandboxId = Get-SandboxId -Payload $sandbox
    if (-not $sandboxId) {
        $sandboxJson = $sandbox | ConvertTo-Json -Depth 20 -Compress
        Write-Result "FAIL" "cloud key create sandbox" "response did not include sandbox id: $sandboxJson"
        throw "sandbox id missing"
    }

    $sandboxes = Invoke-Json `
        -Name "cloud key list owned sandboxes" `
        -Method "GET" `
        -Url "$base/v1/sandboxes" `
        -Headers $cloudHeaders
    if (-not (Test-SandboxListContains -Payload $sandboxes -SandboxId $sandboxId)) {
        Write-Result "FAIL" "cloud key list owned sandboxes" "created sandbox was not visible"
        throw "created sandbox not visible in list"
    }

    Invoke-Json `
        -Name "cloud key delete sandbox" `
        -Method "DELETE" `
        -Url "$base/v1/sandboxes/$sandboxId" `
        -Headers $cloudHeaders | Out-Null

    if ($AdminBearerToken) {
        $adminHeaders = @{ Authorization = "Bearer $AdminBearerToken" }
        $users = Invoke-Json `
            -Name "admin list users" `
            -Method "GET" `
            -Url "$base/api/v1/admin/users?keyword=$([uri]::EscapeDataString([string]$agentMe.subject_id))&page_size=20" `
            -Headers $adminHeaders
        if (-not $users.items -or @($users.items).Count -eq 0) {
            Write-Result "FAIL" "admin list users" "agent user was not returned"
            throw "admin users list is empty"
        }

        $ownerSubjectId = [string]$agentMe.subject_id
        $adminCredentials = Invoke-Json `
            -Name "admin list user credentials" `
            -Method "GET" `
            -Url "$base/api/v1/admin/users/$([uri]::EscapeDataString($ownerSubjectId))/credentials" `
            -Headers $adminHeaders
        if (-not $adminCredentials.items -or @($adminCredentials.items).Count -eq 0) {
            Write-Result "FAIL" "admin list user credentials" "no credentials returned"
            throw "admin user credentials list is empty"
        }

        Invoke-Json `
            -Name "admin disable credential" `
            -Method "POST" `
            -Url "$base/api/v1/admin/credentials/$([uri]::EscapeDataString([string]$credential.id)):disable" `
            -Headers $adminHeaders | Out-Null
        Assert-Unauthorized `
            -Name "disabled cloud key rejected" `
            -Url "$base/v1/sandboxes" `
            -Headers $cloudHeaders
    } else {
        Write-Result "WARN" "admin business flow" "missing AdminBearerToken or OSB_PLUS_VERIFY_ADMIN_TOKEN; admin checks skipped"
        Invoke-Json `
            -Name "agent disable credential cleanup" `
            -Method "POST" `
            -Url "$base/api/v1/cloud-sandbox/credentials/$([uri]::EscapeDataString([string]$credential.id)):disable" `
            -Headers $agentHeaders | Out-Null
        Assert-Unauthorized `
            -Name "disabled cloud key rejected" `
            -Url "$base/v1/sandboxes" `
            -Headers $cloudHeaders
    }

    Write-Result "OK" "business flow complete" $credential.id
}

Invoke-Compose -ComposeArgs @("config", "--quiet") | Out-Null

if ($ConfigOnly) {
    Write-Result "OK" "config-only"
    exit 0
}

if ($Start) {
    Invoke-Compose -ComposeArgs @("up", "-d", "--build") | Out-Null
}

if ($Migrate) {
    Invoke-Compose -ComposeArgs @("exec", "-T", "opensandbox-plus", "sh", "-c", "cd /app/server && alembic -c alembic.ini upgrade head") | Out-Null
}

Invoke-ComposeWarn -Name "postgres ready" -ComposeArgs @("exec", "-T", "postgres", "pg_isready", "-U", "opensandbox_plus", "-d", "opensandbox_plus") | Out-Null
Invoke-ComposeWarn -Name "redis ready" -ComposeArgs @("exec", "-T", "redis", "redis-cli", "ping") | Out-Null

$health = Wait-HttpJson "opensandbox-plus health" "$PlusUrl/health" {
    param($response)
    $response.status -eq "ok" -and $response.service -eq "opensandbox-plus"
}

Wait-HttpText "console static page" "$PlusUrl/" 'id="root"'

$discovery = Wait-HttpJson "casdoor discovery" "$($CasdoorUrl.TrimEnd('/'))/.well-known/openid-configuration" {
    param($response)
    $response.issuer -and $response.authorization_endpoint -and $response.token_endpoint -and $response.jwks_uri
}

Wait-HttpJson "casdoor jwks" $discovery.jwks_uri {
    param($response)
    @($response.keys).Count -gt 0
} | Out-Null

if (-not $SkipCasdoorApplication) {
    $appUrl = "$($CasdoorUrl.TrimEnd('/'))/api/get-application?id=$CasdoorApplicationOwner/osb-console"
    try {
        $app = Invoke-RestMethod -Method Get -Uri $appUrl -TimeoutSec 10
        if ($app.status -eq "ok" -and $app.data.clientId -eq "osb-console") {
            Write-Result "OK" "casdoor osb-console application" $appUrl
        } else {
            Write-Result "WARN" "casdoor osb-console application" "not configured or unexpected clientId"
        }
    } catch {
        Write-Result "WARN" "casdoor osb-console application" $_.Exception.Message
    }
}

$pythonCheck = "import os, urllib.request; base=os.environ['OSB_PLUS_OPENSANDBOX_DEFAULT_BACKEND_BASE_URL'].rstrip('/'); key=os.environ['OSB_PLUS_OPENSANDBOX_INTERNAL_API_KEY']; req=urllib.request.Request(base + '/health', headers={'OPEN-SANDBOX-API-KEY': key}); print(urllib.request.urlopen(req, timeout=10).status)"
Invoke-ComposeWarn -Name "opensandbox internal health" -ComposeArgs @("exec", "-T", "opensandbox-plus", "python", "-c", $pythonCheck) | Out-Null

if ($RunBusinessFlow) {
    Invoke-BusinessFlow
}

Write-Result "OK" "local verification complete" ("app_role=" + $health.app_role)
