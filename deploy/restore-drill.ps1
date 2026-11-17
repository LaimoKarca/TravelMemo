param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$ExpectedTripId,
    [ValidateRange(0, 100000)][int]$ExpectedEventCount = 0
)
$ErrorActionPreference = 'Stop'
$backupRoot = (Resolve-Path -LiteralPath $BackupPath).Path
$manifest = Get-Content -Raw -LiteralPath (Join-Path $backupRoot 'manifest.json') | ConvertFrom-Json
$archive = Join-Path $backupRoot 'neo4j-data.tar.gz'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) {
    throw 'Archive hash does not match manifest.'
}
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$volume = "travelmemo-restore-drill-$suffix"
$container = "travelmemo-restore-drill-$suffix"
$network = "travelmemo-restore-drill-$suffix"
$mediaVolume = "travelmemo-restore-media-$suffix"
function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed (exit $LASTEXITCODE)." }
}
$created = $false
$networkCreated = $false
$mediaCreated = $false
try {
    if ($manifest.media_sha256) {
        $mediaArchive = Join-Path $backupRoot 'photos-data.tar.gz'
        if ((Get-FileHash -LiteralPath $mediaArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.media_sha256) {
            throw 'Photo archive integrity check failed.'
        }
        Invoke-Docker -Arguments @('volume', 'create', $mediaVolume) | Out-Null
        $mediaCreated = $true
        Invoke-Docker -Arguments @('run', '--rm', '--network', 'none', '--user', '0', '--entrypoint', 'bash',
            '--mount', "type=volume,source=$mediaVolume,target=/photos",
            '--mount', "type=bind,source=$backupRoot,target=/backup,readonly", $manifest.neo4j_image_id,
            '-c', 'tar -xzf /backup/photos-data.tar.gz -C /photos && chown -R 10001:10001 /photos')
    }
    Invoke-Docker -Arguments @('network', 'create', '--internal', $network) | Out-Null
    $networkCreated = $true
    Invoke-Docker -Arguments @('volume', 'create', $volume) | Out-Null
    $created = $true
    Invoke-Docker -Arguments @('run', '--rm', '--network', 'none', '--user', '0', '--entrypoint', 'bash',
        '--mount', "type=volume,source=$volume,target=/data",
        '--mount', "type=bind,source=$backupRoot,target=/backup,readonly", $manifest.neo4j_image_id,
        '-c', 'tar -xzf /backup/neo4j-data.tar.gz -C /data && chown -R neo4j:neo4j /data')
    Invoke-Docker -Arguments @('run', '-d', '--name', $container, '--network', $network, '--memory', '1536m',
        '-e', 'NEO4J_AUTH=none', '-e', 'NEO4J_server_memory_heap_initial__size=256m',
        '-e', 'NEO4J_server_memory_heap_max__size=512m', '-e', 'NEO4J_server_memory_pagecache_size=256m',
        '--mount', "type=volume,source=$volume,target=/data", $manifest.neo4j_image_id) | Out-Null
    $ready = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        $state = docker inspect $container --format '{{.State.Status}}'
        if ($state -ne 'running') {
            docker logs --tail 50 $container
            throw "Restored database stopped unexpectedly (state=$state)."
        }
        $ErrorActionPreference = 'Continue'
        $result = docker exec $container cypher-shell --format plain 'MATCH (n) RETURN count(n) AS nodes' 2>$null
        $queryExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($queryExit -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'Isolated restored database did not become ready.' }
    $nodeCount = [long](@($result | Where-Object { $_ -match '^\d+$' })[-1])
    if ($nodeCount -ne [long]$manifest.nodes) { throw 'Restored node count differs from backup.' }
    if ($ExpectedTripId) {
        $query = "MATCH (t:Trip {id:'$ExpectedTripId'})-[:HAS_EVENT]->(e:Event) RETURN count(e) AS events"
        $result = docker exec $container cypher-shell --format plain $query
        if ($LASTEXITCODE -ne 0) { throw 'Restored trip could not be queried.' }
        $events = [long](@($result | Where-Object { $_ -match '^\d+$' })[-1])
        if ($events -ne $ExpectedEventCount) { throw 'Restored trip event count differs.' }
        if ($events -gt 1) {
            $query = "MATCH (t:Trip {id:'$ExpectedTripId'})-[:HAS_EVENT]->(a:Event)-[:NEXT]->(b:Event) WHERE b.trip_id=t.id RETURN count(b) AS links"
            $result = docker exec $container cypher-shell --format plain $query
            if ($LASTEXITCODE -ne 0) { throw 'Restored NEXT graph could not be queried.' }
            $links = [long](@($result | Where-Object { $_ -match '^\d+$' })[-1])
            if ($links -ne ($events - 1)) { throw 'Restored trip NEXT edges differ.' }
        }
        Write-Output "RESTORED_TRIP_OK events=$events"
    }
    Write-Output "RESTORE_DRILL_OK nodes=$nodeCount; production volume unchanged."
} finally {
    # Only the exact GUID-named resources created by this invocation can be removed.
    if ($created -and $container -match '^travelmemo-restore-drill-[a-f0-9]{12}$') {
        $ErrorActionPreference = 'Continue'
        docker rm -f $container 2>$null | Out-Null
        docker volume rm $volume | Out-Null
    }
    if ($networkCreated -and $network -match '^travelmemo-restore-drill-[a-f0-9]{12}$') {
        docker network rm $network | Out-Null
    }
    if ($mediaCreated -and $mediaVolume -match '^travelmemo-restore-media-[a-f0-9]{12}$') {
        docker volume rm $mediaVolume | Out-Null
    }
}
