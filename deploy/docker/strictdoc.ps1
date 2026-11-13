<#
.SYNOPSIS
Runs StrictDoc in its Docker image, on the project in the current folder
(or -Project).

.DESCRIPTION
  new -Title "My project"   Set up a new project in the tracker layout.
  server [-Port 5111] [-Watch]
                            Start the web server: http://localhost:5111,
                            workspace at /workspace. Ctrl+C stops it.
  export [-Formats html,typst-pdf]
                            Export to ./output.
  shell                     A bash shell in the image, in the project.

Arguments after the command go to StrictDoc, for example
  ./strictdoc.ps1 export --formats json --output-dir build/json

The image is -Image, else $env:STRICTDOC_IMAGE, else $DefaultImage below.
The image prints this script with its own name as $DefaultImage:

  docker run --rm --entrypoint strictdoc-launcher <image> > strictdoc.ps1

The script needs only Docker and the image. The container runs as you, so
the files it writes belong to you.

.EXAMPLE
./strictdoc.ps1 new -Title "Kettle"
./strictdoc.ps1 server -Watch
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("new", "server", "export", "shell", "help")]
    [string] $Command = "help",

    [string] $Title,
    [string] $Project = (Get-Location).Path,
    [string] $Image,
    [int] $Port = 5111,
    [switch] $Watch,
    [string] $Formats = "html,typst-pdf",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $StrictDocArguments = @()
)

$ErrorActionPreference = "Stop"

# strictdoc-launcher of the image replaces this name with the image's own.
$DefaultImage = "strictdoc:local"
if (-not $Image) {
    $Image = if ($env:STRICTDOC_IMAGE) { $env:STRICTDOC_IMAGE } else { $DefaultImage }
}

function Invoke-Docker([string[]] $Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# -it with a terminal, so that Ctrl+C stops the container; -i without one.
[string[]] $Terminal = if ([Console]::IsInputRedirected) { @("-i") } else { @("-it") }

function Get-RunArguments([string[]] $Extra = @()) {
    $user = "$(& id -u):$(& id -g)"
    $projectPath = (Resolve-Path $Project).Path
    return @("run", "--rm", "-u", $user, "-v", "${projectPath}:/data") + $Extra
}

switch ($Command) {
    "help" {
        Get-Help $PSCommandPath -Detailed
    }
    "new" {
        if (-not $Title) { throw "new needs -Title, for example: new -Title 'My project'" }
        if (-not (Test-Path $Project)) { New-Item -ItemType Directory -Path $Project | Out-Null }
        Invoke-Docker ((Get-RunArguments @("--entrypoint", "strictdoc-new-project")) + @($Image, "--title", $Title))
    }
    "server" {
        $arguments = @("server", "/data", "--host", "0.0.0.0", "--port", "5111")
        if ($Watch) { $arguments += "--watch" }
        Write-Host "StrictDoc: http://localhost:$Port (workspace: http://localhost:$Port/workspace). Ctrl+C stops it."
        Invoke-Docker ((Get-RunArguments ($Terminal + @("-p", "${Port}:5111"))) + @($Image) + $arguments + $StrictDocArguments)
    }
    "export" {
        $arguments = @("export", ".")
        if ($StrictDocArguments -notcontains "--formats") { $arguments += @("--formats", $Formats) }
        Invoke-Docker ((Get-RunArguments) + @($Image) + $arguments + $StrictDocArguments)
    }
    "shell" {
        Invoke-Docker ((Get-RunArguments ($Terminal + @("--entrypoint", "bash"))) + @($Image))
    }
}
