param([int]$Rate = -2)
# 读取 release\_rec\scenes.json，为每个场景生成中文旁白 WAV（22050Hz/16bit/mono）。
$root = (Get-Location).Path
$scenesPath = Join-Path $root 'release\_rec\scenes.json'
$scenes = Get-Content $scenesPath -Raw -Encoding UTF8 | ConvertFrom-Json
$outDir = Join-Path $root 'release\_rec\tts'
New-Item -ItemType Directory -Force $outDir | Out-Null
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Huihui Desktop')
$s.Rate = $Rate
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($sc in $scenes) {
  $path = Join-Path $outDir ($sc.id + '.wav')
  $s.SetOutputToWaveFile($path, $fmt)
  $s.Speak($sc.narration)
  $s.SetOutputToNull()
  Write-Host ('ok ' + $sc.id)
}
$s.Dispose()
