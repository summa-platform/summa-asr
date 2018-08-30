#!/usr/bin/env python3

import asyncio, traceback, os, sys
import inspect
import time

from worker_pool import WorkerProcessPool, ErrorMessage

from asr import create_asr
from vad import create_vad
from lib import Transcriber, video_to_pcm_chunks, rabbitmq_callback


# class NoFinalResult(Exception): pass    # optional

name = 'SUMMA-ASR'      # required by rabbitmq module

RELATIVE_URL_ROOT = None
MODEL = None

def init(args=None):
    global pool, RELATIVE_URL_ROOT
    RELATIVE_URL_ROOT = args.root_url
    pool = WorkerProcessPool(worker_run, init_module, count=args.PARALLEL, heartbeat_pause=args.heartbeat_pause, init_args=(args,))
    pool.start()
    # give some time for workers to start
    time.sleep(5)
    pool.watch_heartbeats(args.restart_timeout, args.refresh, args.max_retries_per_job)


def setup_argparser(parser):
    parser.add_argument('--root-url', dest='root_url', type=str, default=os.environ.get('RELATIVE_URL_ROOT'),
            help='URL root for relative URLs (or set env variable RELATIVE_URL_ROOT)')
    parser.add_argument('--model', type=str, default=os.environ.get('MODEL', '/model'),
            help='URL root for relative URLs (or set env variable MODEL)')
    parser.add_argument('--heartbeat-pause', type=int, default=os.environ.get('HEARTBEAT_PAUSE', 10),
            help='pause in seconds between heartbeats (or set env variable HEARTBEAT_PAUSE)')
    parser.add_argument('--refresh', type=int, default=os.environ.get('REFRESH', 5),
            help='seconds between pulse checks (or set env variable REFRESH)')
    parser.add_argument('--restart-timeout', type=int, default=os.environ.get('RESTART_TIMEOUT', 120),
            help='max allowed seconds between heartbeats, will restart worker if exceeded (or set env variable RESTART_TIMEOUT)')
    parser.add_argument('--max-retries-per-job', type=int, default=os.environ.get('MAX_RETRIES_PER_JOB', 3),
            help='maximum retries per job (or set env variable MAX_RETRIES_PER_JOB)')


def shutdown():
    global pool
    return pool.terminate()


def reset():
    global pool
    pool.reset()


async def worker_run(url, partial_result_callback=None, loop=None, heartbeat=None, *args, **kwargs):
    global transcriber

    segments = []

    def callback(nbest, end_of_segment=False, end_of_stream=False, alignment=None, alignment_with_confidence=None, start=0.0):
        nonlocal result

        if alignment_with_confidence is not None:
            segments.append([dict(word=w, time=start+t, duration=d, confidence=c) for w,t,d,c in alignment_with_confidence])

        result = dict(end_of_segment=end_of_segment, end_of_stream=end_of_stream, segments=segments)

        # send results only one segment at a time
        if end_of_segment:
            # send only partial result here
            if not end_of_stream:
                partial_result_callback(result)

    def heartbeat_per_chunk(chunk_generator):
        for chunk in chunk_generator:
            heartbeat()
            yield chunk

    result = None
    chunk_generator = video_to_pcm_chunks(url)
    transcriber.run(heartbeat_per_chunk(chunk_generator), callback)
    return result


async def run(url, partial_result_callback=None, loop=None, heartbeat=None, *args, **kwargs):
    global pool, RELATIVE_URL_ROOT
    # worker = await pool()
    async with pool.acquire() as worker:
        url = RELATIVE_URL_ROOT + url if url.startswith('/') else url
        result = await worker(url, partial_result_callback)
        # raise NoFinalResult() # if final result is expected to be sent via send_reply(final_result, 'finalResult')
        return result


async def process_message(task_data, loop=None, send_reply=None, *args, **kwargs):
    global pool, RELATIVE_URL_ROOT
    # worker = await pool()
    async with pool.acquire() as worker:
        url = task_data['url']
        url = RELATIVE_URL_ROOT + url if url.startswith('/') else url
        result = await worker(url, send_reply)
        # raise NoFinalResult() # if final result is expected to be sent via send_reply(final_result, 'finalResult')
        # if not result:
        #     raise Exception('invalid result')
        return result


# --- private ---


def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def init_module(args):
    log('Initialize ASR ...')
    global MODEL, transcriber
    MODEL = args.model
    asr = create_asr(MODEL)
    frame_generator, vad = create_vad()
    transcriber = Transcriber(asr, vad, frame_generator)
    log('ASR worker initialized!')



if __name__ == "__main__":

    import json
    import argparse

    parser = argparse.ArgumentParser(description='ASR Task', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--parallel', '-n', dest='PARALLEL', metavar='PORT', type=int, default=os.environ.get('PARALLEL',1),
            help='messages to process in parallel (or set env variable PARALLEL)')
    parser.add_argument('url', type=str, default="http://data.cstr.inf.ed.ac.uk/summa/data/test.mp4", nargs='?',
            help='resource URL to be analyzed with ASR')

    setup_argparser(parser)

    args = parser.parse_args()

    task_data = dict(url=args.url)

    init(args)

    async def print_partial(partial_result):
        print('Partial result:')
        print(partial_result)

    try:
        loop = asyncio.get_event_loop()
        # loop.set_debug(True)
        result = loop.run_until_complete(process_message(task_data, loop=loop, send_reply=print_partial))
        print('Result:')
        print(result)
    except KeyboardInterrupt:
        print('INTERRUPTED')
    except:
        print('EXCEPTION')
        traceback.print_exc()
        # raise
    finally:
        print('Shutdown')
        shutdown()
        loop.stop()
        loop.run_forever()
