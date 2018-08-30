import webrtcvad
import collections

def create_vad():
	return FrameGenerator(), VAD()

class FrameGenerator:

	def __init__(self, sample_rate=16000, frame_duration_ms=30):
		self.sample_rate = sample_rate
		self.frame_duration_ms = frame_duration_ms / 1000.0
		self.shift = int(sample_rate * (frame_duration_ms / 1000.0) * 2)
		self.reset()

	def reset(self):
		self.audio = b""
		self.timestamp = 0.0
		self.duration = (float(self.shift) / self.sample_rate) / 2.0

	def chunks(self, audio):
		self.audio += audio
		offset = 0
		while offset + self.shift < len(self.audio):
			yield self.audio[offset:offset + self.shift], self.timestamp
			self.timestamp += self.frame_duration_ms
			offset += self.shift

		self.audio = self.audio[offset:]


class VAD:

	def __init__(self, level=0, sample_rate=16000):
		self.vad = webrtcvad.Vad(level)
		self.sample_rate = sample_rate
		self.num_padding_frames = 10
		self.reset()

	def reset(self):
		self.triggered = False
		self.ring_buffer = collections.deque(maxlen=self.num_padding_frames)

	def decide(self, frame, timestamp):
		change = None

		self.ring_buffer.append((frame, timestamp))
		if not self.triggered:
			num_voiced = len([f for f in self.ring_buffer if self.vad.is_speech(f[0], self.sample_rate)])
			if num_voiced > 0.9 * self.ring_buffer.maxlen:
				self.triggered = True
				frame = b"".join([f[0] for f in self.ring_buffer])
				timestamp = min([f[1] for f in self.ring_buffer])
				change = "START"
				self.ring_buffer.clear()
		else:
			num_unvoiced = len([f for f in self.ring_buffer if not self.vad.is_speech(f[0], self.sample_rate)])

			if num_unvoiced > 0.9 * self.ring_buffer.maxlen:
				self.triggered = False
				change = "END"
				self.ring_buffer.clear()

		return self.triggered, change, frame, timestamp
