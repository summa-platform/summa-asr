from __future__ import print_function

from asr import create_asr
from vad import create_vad
from lib import Transcriber, video_to_pcm_chunks, rabbitmq_callback

def callback(nbest, end_of_segment=False, end_of_stream=False, alignment=None, alignment_with_confidence=None, start=0.0):
    if end_of_segment:
        print(nbest[0])


if __name__ == '__main__':
    asr = create_asr()
    frame_generator, vad = create_vad()
    transcriber = Transcriber(asr, vad, frame_generator)

    chunk_generator = video_to_pcm_chunks("http://data.cstr.inf.ed.ac.uk/summa/data/test.mp4")
    result_callback = callback

    transcriber.run(chunk_generator, result_callback)
