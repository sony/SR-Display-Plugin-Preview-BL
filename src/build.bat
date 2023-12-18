<# :
@echo off
powershell -command "Invoke-Expression (Get-Content '%0' -Raw)"
goto :EOF
#>

$regex = """version"":\s\((?<version>.*)\),"
$version = (sls -Path "srd_for_blender/__init__.py" -Pattern $regex -AllMatches | % { $_.Matches.Groups[1].Value }).ToString().Replace(" ","").Split(",") -join "_"


$pluginName = "SpatialRealityDisplayPluginBle_" + $version

New-Item $pluginName -ItemType Directory -Force > $null

$logfile = "build.log"
xcopy "srd_for_blender" $pluginName /EXCLUDE:xcopy-excludelist.txt /D /S /E /Y /R >> $logfile

Compress-Archive -Path $pluginName -DestinationPath ./$pluginName.zip -Force
