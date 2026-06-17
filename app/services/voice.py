import subprocess
from pathlib import Path


def create_voiceover(output_path: Path, text: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_text = text.replace("'", "''")
    escaped_path = str(output_path).replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0
$synth.Volume = 100
$synth.SetOutputToWaveFile('{escaped_path}')
$synth.Speak('{escaped_text}')
$synth.Dispose()
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell speech synthesis failed")
    return output_path
