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



def print_ctm(name, f):
    def callback(nbest, end_of_segment=False, end_of_stream=False, alignment=None, alignment_with_confidence=None, start=0.0):
        if end_of_segment:
            for (word, utterance_start, duration, confidence) in alignment_with_confidence:
                f.write(u" ".join([name, "0", "%.2f" % (start + utterance_start), "%.2f" % duration, word, "%.2f" % confidence, "\n"]))

    return callback


if __name__ == '__main__':
    if len(sys.argv) != 6:
        print("Usage: python transcribe.py model wav name ctm rtf")
        sys.exit(-1)


    model = sys.argv[1]
    wav = sys.argv[2]
    name = sys.argv[3]
    output_ctm = sys.argv[4]
    output_rtf = sys.argv[5]

    asr = create_asr(model)
    frame_generator, vad = create_vad()
    transcriber = Transcriber(asr, vad, frame_generator)

    start = time.time()
    with codecs.open(output_ctm, 'w', 'utf-8') as f:
        transcriber.run(chunks(wav), print_ctm(name, f))
    end = time.time()

    with open(output_rtf, 'w') as f:
        processing_time = end - start
        duration = wav_duration(wav)

        print("%.2f" % duration, "%.2f" % processing_time, "%.2f" % (processing_time / duration), file=f)
