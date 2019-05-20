#!/usr/bin/env python3
from __future__ import print_function
import codecs
import sys
import wave
import time

from asr import create_asr
from vad import create_vad
from lib import Transcriber


def chunks(path):
    wav = wave.open(path, "rb")

    while True:
        frames = wav.readframes(8000)
        yield frames

        if len(frames) == 0:
            break

def wav_duration(path):
    wav = wave.open(path, "rb")
    return wav.getnframes() / float(wav.getframerate())



def print_ctm(f):
    def callback(nbest, end_of_segment=False, end_of_stream=False, alignment=None, alignment_with_confidence=None, start=0.0):
        if end_of_segment:
            for (word, utterance_start, duration, confidence) in alignment_with_confidence:
                f.write(u" ".join(["%.2f" % (start + utterance_start), "%.2f" % duration, word, "%.2f" % confidence, "\n"]))

    return callback


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: transcribe.py model wav")
        sys.exit(-1)


    model = sys.argv[1]
    wav = sys.argv[2]

    asr = create_asr(model)
    frame_generator, vad = create_vad()
    transcriber = Transcriber(asr, vad, frame_generator)

    start = time.time()
    transcriber.run(chunks(wav), print_ctm(sys.stdout))
    end = time.time()

    processing_time = end - start
    duration = wav_duration(wav)

    print("%.2f" % duration, "%.2f" % processing_time,
          "%.2f" % (processing_time / duration), file=sys.stderr)
