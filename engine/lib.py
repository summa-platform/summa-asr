from __future__ import print_function

import json
import subprocess
import re


class Transcriber(object):

    def __init__(self, asr, vad, frame_generator):
        self.asr = asr
        self.vad = vad
        self.frame_generator = frame_generator


    def run(self, messages, callback):
        for start, end_of_stream, audio_buffer in self.messages_to_segments(messages):
            self.asr.reset()
            self.asr.recognize_chunk(audio_buffer)
            nbest, _, alignment_with_confidence = self.asr.get_final_hypothesis(compute_alignment_with_word_confidence=True)
            callback(nbest, end_of_segment=True, end_of_stream=end_of_stream, alignment_with_confidence=alignment_with_confidence, start=start)

    def messages_to_segments(self, messages):
        self.vad.reset()
        self.frame_generator.reset()
        audio_buffer = None
        start = 0.0

        for message in messages:
            for chunk, timestamp in self.frame_generator.chunks(message):
                is_speech, change, chunk, timestamp = self.vad.decide(chunk, timestamp)

                if change == "START":
                    start = timestamp
                    audio_buffer = b""

                if change == "END":
                    yield start, False, audio_buffer + chunk
                    audio_buffer = None

                if is_speech:
                    audio_buffer += chunk

        if audio_buffer is not None:
            yield start, True, audio_buffer


def video_to_pcm_chunks(url, chunk_size=16000):
    # tmp_file = "/tmp/data$$.raw"
    # cmd = "ffmpeg -i %s -y -f s16le -ar 16000 -ac 1 -acodec pcm_s16le %s; cat %s; rm %s" % (url, tmp_file, tmp_file, tmp_file)
    cmd = "ffmpeg -i %s -y -f s16le -ar 16000 -ac 1 -acodec pcm_s16le -" % url
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)

    while True:
        pcm = process.stdout.read(chunk_size)

        exit_code = process.poll()
        if exit_code is not None and exit_code != 0:
            error = re.compile(r'(error|fail)', re.I)
            message = '\n'.join(line for line in process.stderr.read().decode('utf8').split('\n') if error.search(line))
            raise ValueError('Given URL cannot be transcribed: %s\n%s\n----------------' % (url, message))

        yield pcm

        if len(pcm) == 0:
            break


def rabbitmq_callback(channel, queue, routing_keys,
                      task_metadata, publish_result):
    # accumulate segments in case a message goes missing
    segments = []

    def callback(nbest, end_of_segment=False, end_of_stream=False,
                 alignment=None, alignment_with_confidence=None, start=0.0):
        if alignment_with_confidence is not None:
            segments.append([{'word': w,
                              'time': start + t,
                              'duration': d,
                              'confidence': c}
                             for (w, t, d, c)
                             in alignment_with_confidence])

        result = {
            'end_of_segment': end_of_segment,
            'end_of_stream': end_of_stream,
            'segments': segments
        }

        # send results only one segment at a time
        if end_of_segment:
            result_type = 'finalResult' if end_of_stream else 'partialResult'
            publish_result(channel, queue, routing_keys, result_data=result,
                           task_metadata=task_metadata,
                           result_type=result_type)

    return callback


def ws_messages_generator(ws):
    while not ws.closed:
        yield ws.receive()


def ws_callback(ws):
    def callback(nbest, end_of_segment=False, end_of_stream=False, alignment=None, alignment_with_confidence=None, start=0.0):
        ws.send(format_response(nbest, end_of_segment, end_of_stream, alignment, alignment_with_confidence, start))

    return callback


def format_response(nbest, end_of_segment=False, end_of_stream=False, alignment=None, alignment_with_confidence=None, start=0.0, id=None, metadata={}):
    message = {
        'id': id,
        'metadata': metadata,
        'result': {
            'hypotheses': [
                {'confidence': confidence, 'transcript': transcript} for (confidence, transcript) in nbest
            ],
        },
        'end_of_segment': end_of_segment,
        'end_of_stream': end_of_stream,
    }

    if alignment is not None:
        message['alignment'] = [{'word': w, 'time': start + t, 'duration': d} for (w,t,d) in alignment]
    if alignment_with_confidence is not None:
        message['alignment'] = [{'word': w, 'time': start + t, 'duration': d, 'confidence': c} for (w,t,d,c) in alignment_with_confidence]

    return json.dumps(message, sort_keys=True, indent=4, separators=(',', ': '))
