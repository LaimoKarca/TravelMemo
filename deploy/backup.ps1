param(
    [Parameter(Mandatory = $true)][string]$EnvFile,
    [Parameter(Mandatory = $true)][string]$ReleaseId,
    [string]$BackupDirectory = 'backups'
)
$ErrorActionPreference = 'Stop'
$composeFile = Join-Path $PSScriptRoot 'compose.prod.yml'
$env:RELEASE_ID = $ReleaseId
$configFile = (Resolve-Path -LiteralPath $EnvFile).Path
$backupRoot = [IO.Path]::GetFullPath($BackupDirectory)
$destination = Join-Path $backupRoot ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $destination -Force | Out-Null

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed (exit $LASTEXITCODE)." }
}

$containerInfo = docker inspect travelmemo-neo4j-1 | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'TravelMemo Neo4j container was not found.' }
$dataMount = @($containerInfo[0].Mounts | Where-Object Destination -eq '/data')
if ($dataMount.Count -ne 1 -or $dataMount[0].Type -ne 'volume') { throw 'Expected one named Neo4j data volume.' }
$volume = $dataMount[0].Name
$image = $containerInfo[0].Config.Image
$imageId = $containerInfo[0].Image
$stopped = $false
try {
    # An offline archive includes both the user database and Neo4j system/auth data.
    $stopped = $true
    Invoke-Docker -Arguments @('compose', '--env-file', $configFile, '-f', $composeFile, 'stop', 'api')
    # Count only after API writes have quiesced. Credentials stay inside the Neo4j container.
    $countCode = 'export NEO4J_USERNAME=neo4j; export NEO4J_PASSWORD="${NEO4J_AUTH#*/}"; cypher-shell -d neo4j --format plain "MATCH (n) RETURN count(n) AS nodes"; # end'
    $countResult = $countCode | docker exec -i travelmemo-neo4j-1 bash
    if ($LASTEXITCODE -ne 0) { throw 'Could not capture quiescent node count.' }
    $countValues = @($countResult | Where-Object { $_ -match '^\d+$' })
    if ($countValues.Count -ne 1) { throw 'Unexpected node-count response.' }
    $nodeCount = [long]$countValues[0]
    Invoke-Docker -Arguments @('compose', '--env-file', $configFile, '-f', $composeFile, 'stop', 'neo4j')
    Invoke-Docker -Arguments @('run', '--rm', '--network', 'none', '--user', '0', '--entrypoint', 'bash',
        '--mount', "type=volume,source=$volume,target=/source,readonly",
        '--mount', "type=bind,source=$destination,target=/backup", $imageId,
        '-c', 'tar -czf /backup/neo4j-data.tar.gz -C /source .')
    $archive = Join-Path $destination 'neo4j-data.tar.gz'
    $manifest = @{
        format = 1; created_at = [DateTime]::UtcNow.ToString('o'); release_id = $ReleaseId
        source_volume = $volume; neo4j_image = $image; neo4j_image_id = $imageId
        nodes = $nodeCount; sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    [IO.File]::WriteAllText((Join-Path $destination 'manifest.json'), ($manifest | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    Write-Output "Backup created: $destination"
} finally {
    if ($stopped) {
        Invoke-Docker -Arguments @('compose', '--env-file', $configFile, '-f', $composeFile, 'up', '-d', '--wait', '--wait-timeout', '240', 'neo4j', 'api')
    }
}

# Keep EnvFile, .env.tunnel and any external service recovery codes in a separate private backup.
# They are deliberately excluded from this data archive and from Git.
