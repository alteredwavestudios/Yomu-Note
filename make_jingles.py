"""Generate Yomu Note's two ORIGINAL offline chiptune jingles.

Execute with `python make_jingles.py` if you need to regenerate audio assets.
Both tunes are written in E-flat major, last three seconds, and use simple
soft-edged pulse/triangle synthesizer voices. No third-party audio library or
third-party music is involved. All sounds are synthesised from scratch.
"""
from __future__ import annotations
import math
import struct
import wave
from pathlib import Path

RATE = 24000
LENGTH = 3.0
PITCH = {'Eb4':311.12698, 'F4':349.2282, 'G4':391.9954, 'Ab4':415.3047,
         'Bb4':466.1638, 'C5':523.2511, 'D5':587.3295, 'Eb5':622.2540,
         'F5':698.4565, 'G5':783.9909, 'Bb5':932.3275}
# (start time, duration, pitch, intensity): original short little tunes.
MELODIES = {
    'break': [(0.00,.34,'Eb5',.75),(.34,.32,'Bb4',.72),(.66,.34,'G4',.74),
              (1.00,.34,'F4',.68),(1.34,.78,'Eb4',.78),(2.22,.34,'G4',.38),
              (2.45,.32,'Eb5',.30)],
    'study': [(0.00,.24,'Eb4',.68),(.26,.24,'G4',.72),(.52,.24,'Bb4',.72),
              (.78,.26,'C5',.77),(1.06,.52,'Eb5',.82),(1.67,.22,'G5',.59),
              (1.91,.22,'F5',.58),(2.15,.58,'Eb5',.78)]
}


def voice(seconds: float, freq: float) -> float:
    """Blend a mellow 8-bit pulse with triangle and a quiet second harmonic."""
    phase = (seconds * freq) % 1.0
    pulse = 1.0 if phase < .38 else -1.0
    triangle = 1.0 - 4.0 * abs(phase - .5)
    sparkle = math.sin(2.0 * math.pi * freq * 2 * seconds)
    return .30 * pulse + .55 * triangle + .15 * sparkle


def envelope(age: float, duration: float) -> float:
    """Short attack and smooth release to prevent pops/clicks."""
    if age < 0 or age >= duration + .16:
        return 0.0
    attack = min(1.0, age / .012)
    end = min(1.0, max(0.0, (duration + .16 - age) / .16))
    return attack * end * (0.94 - 0.12 * min(age, duration))


def render(name: str, target: Path) -> None:
    notes = MELODIES[name]
    samples = bytearray()
    for i in range(round(RATE * LENGTH)):
        t = i / RATE
        total = 0.0
        for start, duration, pitch, intensity in notes:
            age = t - start
            env = envelope(age, duration)
            if env:
                total += intensity * env * voice(age, PITCH[pitch])
        # Restrict amplitude gently. SoundEffect has a separate volume control.
        sample = math.tanh(total * .57) * .47
        samples.extend(struct.pack('<h', int(max(-1.0, min(1.0, sample)) * 32767)))
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(samples)


if __name__ == '__main__':
    folder = Path(__file__).resolve().parent / 'assets' / 'audio'
    for name in MELODIES:
        render(name, folder / f'{name}.wav')
        print(f'Created {name}.wav (3.0 seconds, E-flat major)')
