"""Windows microphone capture through bundled FFmpeg (no extra audio dependency)."""

import re
import subprocess
import threading
import wave

FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def input_devices():
    result = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                            capture_output=True, timeout=15, creationflags=FLAGS)
    text = result.stderr.decode("utf-8", errors="replace")
    return list(dict.fromkeys(re.findall(r'"([^"\r\n]+)"\s*\(audio\)', text)))


class MicrophoneRecorder:
    def __init__(self, device, path):
        self.device, self.path = device, path
        self.process = None
        self.ready = threading.Event()
        self.cancelled = threading.Event()
        self.errors = []

    def start(self):
        if self.cancelled.is_set():
            raise RuntimeError("Η εγγραφή ακυρώθηκε.")
        self.process = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-y", "-f", "dshow", "-audio_buffer_size", "50", "-i",
             f"audio={self.device}", "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(self.path)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=FLAGS)

        def monitor():
            for line in self.process.stderr:
                self.errors.append(line.strip())
                self.errors = self.errors[-30:]
                if "Output #0" in line:
                    self.ready.set()
        threading.Thread(target=monitor, daemon=True).start()
        if not self.ready.wait(12) or self.process.poll() is not None or self.cancelled.is_set():
            self.stop()
            raise RuntimeError("Δεν ξεκίνησε το μικρόφωνο. Έλεγξε την πρόσβαση μικροφώνου στα Windows.\n" +
                               "\n".join(self.errors[-5:]))

    def stop(self):
        self.cancelled.set()
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.stdin.write("q\n")
                process.stdin.flush()
                process.wait(timeout=8)
            except Exception:
                process.kill()
                process.wait(timeout=3)
        if self.path.exists():
            try:
                with wave.open(str(self.path), "rb") as stream:
                    return stream.getnframes() / stream.getframerate()
            except (wave.Error, EOFError):
                pass
        return 0.0
