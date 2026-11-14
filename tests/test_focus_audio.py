"""No-GUI tests of timed reminders and supplied standalone audio assets."""
import tempfile
import unittest
import wave
from pathlib import Path
from yomunote.focus_logic import reminder_slot, finished_session_message
from make_jingles import render


class PomodoroAudioTests(unittest.TestCase):
    def test_reminders_only_during_first_ten_minutes(self):
        self.assertIsNone(reminder_slot(-1))
        self.assertEqual(reminder_slot(0), 0)
        self.assertEqual(reminder_slot(59.9), 0)
        self.assertEqual(reminder_slot(60), 1)
        self.assertEqual(reminder_slot(599.9), 9)
        self.assertIsNone(reminder_slot(600))
        self.assertIsNone(reminder_slot(3600))

    def test_two_distinct_session_jingles(self):
        self.assertEqual(finished_session_message('Focus')[0], 'break')
        self.assertEqual(finished_session_message('Short break')[0], 'study')
        self.assertEqual(finished_session_message('Long break')[0], 'study')

    def test_bundled_wavs_are_three_seconds_and_different(self):
        assets = Path(__file__).resolve().parents[1] / 'assets' / 'audio'
        contents = []
        for name in ('break', 'study'):
            wav_path = assets / f'{name}.wav'
            with wave.open(str(wav_path), 'rb') as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.getnframes(), 72000)
                contents.append(wav.readframes(wav.getnframes()))
        self.assertNotEqual(contents[0], contents[1])

    def test_regeneration_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            temp = Path(d) / 'break.wav'
            render('break', temp)
            self.assertEqual(temp.read_bytes(),
                             (Path(__file__).resolve().parents[1] / 'assets' / 'audio' / 'break.wav').read_bytes())


if __name__ == '__main__':
    unittest.main()
