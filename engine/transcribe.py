#!/usr/bin/env python3

import asyncio, traceback, os, sys, multiprocessing
import inspect, heapq, time

from asr import create_asr
from vad import FrameGenerator, VAD
from lib import video_to_pcm_chunks
from multiprocessing.dummy import Pool as DummyPool, Process as Thread
from multiprocessing import Queue, cpu_count, Process
from aio_pika import Message

name = 'SUMMA-ASR'      # required by rabbitmq module

# Terminology:
# TASK:
#    A TASK is the transcription of whatever a url points to, the resulting
#    transcript usually consists of several segments, as recognized by
#    voice activation detection (VAD).
# JOB:
#    The transcription of each segment is a JOB, which is posted to
#    the global job queue by process_message. Processing of each task
#    recycles one of several available global response queues.
# 
# A response_worker (async function call) listens on that reponse queue
# and ships the response when ready.  The response worker also acknowledges
# the message once the task is finished and the result has been published.

# global variables; see init below for initialization

job_queue =  None
# global job_queue that workers work from

asr_workers = None
responders = []
# pool of transcription worker processes 

response_queues = [Queue() for i in range(multiprocessing.cpu_count())]
# list of response queues, each used exclusively for one task at a time

available_response_queue = Queue()
# keeps track of available response queues

# global string variables
RELATIVE_URL_ROOT = None
MODEL = None

job_ctr = 0

def init(args,log=None):
    global asr_workers, job_queue, response_queues, available_response_queue
    w = args.PARALLEL
    job_queue = Queue(int((w+1)/2))

    # ASR workers actually run as sub-processes to the main process, to allow
    # for true parallelism
    twargs = (args.model,job_queue,args.timeout_factor,log)
    asr_workers = [Process(target=transcription_worker,args=(twargs))
                   for i in range(w)]
    for p in asr_workers:
        p.daemon = True
        p.start()
        pass
    for i in range(len(response_queues)):
        available_response_queue.put(i)
        pass
    return

class ImmediateCallback:
    def __init__(self):
        self.end_of_last = 0
        pass
    def __call__(self,job):
        if type(job).__name__ == 'CancelResponse':
            return
        for t in job.transcript():
            gap = max(0.,t['time'] - self.end_of_last)
            print("{:.2f} {:.2f} {:.2f} {:s}".format\
                  (t['time'],gap,t['confidence'], t['word']))
            self.end_of_last = t['time'] + t['duration']
            pass
        print(flush=True)
        return
    pass

def final_callback(segments):
    # print("TRANSCRIPTION FINISHED")
    pass
    
def generate_segments(url,rqid,log=None):
    """
    Chunk stream into segments for ASR depending on Voice Activation
    Detection (VAD) and schedule them for ASR. 
    @param rqid: id of the response queue to be used
    """
    vad = VAD()
    fgen = FrameGenerator()
    audio_buffer = None
    start = 0.0
    stop  = start
    seqno = 0
    # if log: log("Processing",url)
    for pcm in video_to_pcm_chunks(url):
        for chunk,tstamp in fgen.chunks(pcm):
            is_speech, change, chunk, tstamp = vad.decide(chunk, tstamp)
            # if log: log(url,seqno,change,tstamp,is_speech)
            if change == "START":
                start = tstamp
                audio_buffer = b""
            elif change == "END":
                j = Job(seqno, rqid, start, tstamp, False, audio_buffer + chunk)
                # if log: log("NEW SEGMENT # {:d}.{:d}: {:.1f}-{:.1f} ({:.1f} sec.)"\
                #             .format(j.gid, seqno, start, tstamp, tstamp-start))
                t1 = time.time()
                job_queue.put(j)
                t2 = time.time() - t1
                # if log and t2 > 2: log("new segment scheduled after %.2f sec. wait time"%(t2))
                seqno += 1
                audio_buffer = None
                pass
            if is_speech:
                audio_buffer += chunk
                stop = tstamp
                pass
            pass
        # if ctr.value == 3: break
        pass
    j = Job(seqno, rqid, start, stop, True, audio_buffer)
    job_queue.put(j)
    # if log: log("DONE SEGMENTING")
    return

class CancelResponse:
    """
    Sent to responders on the response queue to terminate it prematurely.
    """
    pass

class Job:
    gid = 0
    def __init__(self,seqno, rqid, offset_start, offset_stop, is_end_of_stream, audio_buffer):
        self.seqno = seqno # sequence number
        self.rqid  = rqid # id of response queue
        self.start = offset_start # time offset of where this segment starts
        self.stop  = offset_stop  # ... and ends
        self.end_of_stream = is_end_of_stream
        self.audio_buffer = audio_buffer
        self.init_time = time.time() # time of job creation
        self.start_time = self.init_time # start time of job execution
        self.end_time = self.init_time # end time of job execution
        # results
        self.nbest = None
        self.aln_with_conf = None
        self.timed_out = False
        self.asr = None
        self.gid = Job.gid
        Job.gid += 1
        return

    def runtime(self):
        return self.stop - self.start
    
    def asrtime(self):
        return self.end_time - self.start_time
    
    def transcript(self):
        if not self.aln_with_conf:
            return []
        return [{'word': w, 'time': self.start + t,
                 'duration': d, 'confidence': c}
                for (w,t,d,c) in self.aln_with_conf]
    
def transcribe_segment(job,asr):
    """
    Transcribe segment /job/ with ASR engine /asr/
    """
    job.start_time = time.time()
    if job.audio_buffer == None:
        job.end_time = time.time()
        return 
    asr.reset()
    asr.recognize_chunk(job.audio_buffer)
    x = asr.get_final_hypothesis(compute_alignment_with_word_confidence=True)
    job.nbest = x[0]
    job.aln_with_conf = x[2]
    job.end_time = time.time()
    return 

def transcription_worker(model,job_queue,timeout_factor,log):
    global response_queues
    asr = create_asr(args.model)
    # if log: log("ASR ready.")
    while True:
        # we use a DummyPool with a Dummy Process (i.e., simple thread wrapped
        # in the multiprocessing Process API) so that we are able to enforce
        # a time-out if things take too long.
        p = DummyPool(processes=1)
        j = job_queue.get()
        r = p.apply_async(transcribe_segment,args=(j,asr))
        try:
            r.get(args.timeout_factor * j.runtime())
        except TimeoutError:
            # print("WARNING: TIMEOUT FOR JOB #%d"%j.seqno,file=sys.stderr)
            p.terminate()
            p.join()
            j.timed_out = True
            j.end_time = time.time()
            pass
        # since all objects that are passed between processes
        # need to be pickled, we set audio_buffer to None for
        # hopefully better overall efficiency
        j.audio_buffer = None
        response_queues[j.rqid].put(j)
        pass
    return

def responder(rqid,immediate_callback=None,final_callback=None):
    """
    Collects transcriptions for an entire task. 
    Calls immediate_callback for each segment transcription received.
    Calls final_callback at the end.
    """
    global response_queues, available_response_queue
    # print("NEW RESPONDER",file=sys.stderr)
    ready = []
    heap = []
    rq = response_queues[rqid]
    seqno = 0 # sequence number
    while len(ready) == 0 or not ready[-1].end_of_stream:
        j = rq.get()
        if type(j).__name__ == 'CancelResponse':
            immediate_callback(j)
            final_callback(j)
            break
        # print("GOT RESPONSE (%d/%d)"%(j.seqno,seqno),file=sys.stderr)
        
        if j.seqno == seqno:
            ready.append(j)
            seqno += 1
            if immediate_callback:
                immediate_callback(j)
        else:
            heapq.heappush(heap,(j.seqno,j))
            pass
        while len(heap) and heap[0][0] == seqno:
            j = heapq.heappop(heap)[1]
            ready.append(j)
            seqno += 1
            if immediate_callback:
                immediate_callback(j)
            pass
        pass
    available_response_queue.put(rqid)
    if final_callback:
        final_callback(ready)
        pass
    return

class RabbitMQCallback:
    def __init__(self,message,reply_to):
        self.message = message
        self.reply_to = reply_to
        return
    
    def __call__(self,result): # _data, result_type='finalResult',action='ack'):
        routing_keys = self.message.headers['replyToRoutingKeys']
        body = json.loads(message.body.decode("utf-8"))
        task_metadata = body['taskMetadata']
        # we could add some processing statistics to the task metadata here ...

        result = dict(segments=[s.transcript() for s in result],
                      end_of_segment=True, end_of_stream=True)
        payload = dict(resultData=result,
                       result_type=result_type,
                       taskMetadata=task_metadata)
        msg = Message(bytes(json.dumps(payload),'utf8'),
                      headers=dict(resultProducer=name))
        self.reply_to(msg,routing_keys['finalResult'])
        self.message.ack()
        return
    pass

async def on_rabbitmq_message(message,reply_to,loop=None,verbose=True,**kwargs):
    final_callback = RabbitMQCallback(message,reply)
    immediate_callback = ImmediateCallback()
    body = json.loads(message.body.decode("utf-8"))
    metadata = body['taskMetadata']
    taskdata = body['taksData']
    url = taskdata['url']
    transcribe(url,immediate_callback,final_callback)
    return

                
def setup_argparser(ap):
    ap.add_argument('--root-url', dest='root_url', type=str,
                    default=os.environ.get('RELATIVE_URL_ROOT'),
                    help='URL root for relative URLs (or set env variable RELATIVE_URL_ROOT)')
    ap.add_argument('--model', '-m', type=str,
                    default=os.environ.get('MODEL', 'model'),
                    help='URL root for relative URLs (or set env variable MODEL)')
    # ap.add_argument('--heartbeat-pause', type=int, default=os.environ.get('HEARTBEAT_PAUSE', 10),
    # help='pause in seconds between heartbeats (or set env variable HEARTBEAT_PAUSE)')
    # ap.add_argument('--refresh', type=int, default=os.environ.get('REFRESH', 5),
    # help='seconds between pulse checks (or set env variable REFRESH)')
    # ap.add_argument('--restart-timeout', type=int, default=os.environ.get('RESTART_TIMEOUT', 120),
    # help='max allowed seconds between heartbeats, will restart worker if exceeded (or set env variable RESTART_TIMEOUT)')
    # ap.add_argument('--max-retries-per-job', type=int, default=os.environ.get('MAX_RETRIES_PER_JOB', 3),
    # help='maximum retries per job (or set env variable MAX_RETRIES_PER_JOB)')
    ap.add_argument("--timeout-factor",default=10,
                    help="Wait at most this many times the segment running length for a transcript")
def shutdown():
    global responders, response_queues
    for w in asr_workers:
        w.terminate()
    for q in response_queues:
        q.put(CancelResponse())
        pass
    for r in responders:
        r.join()
        pass
    pass

def reset():
    # global pool
    # pool.reset()
    pass

def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def transcribe_file(url, immediate_callback, final_callback, loop=None, log=None):
    """
    Launch an asynchroous responder, feed data into the processing queue, then return.
    """
    rqid = available_response_queue.get() # get an available response queue
    global responders
    responders = [r for r in responders if r.is_alive()]
    r = Thread(target=responder,args=(rqid,immediate_callback,final_callback))
    r.start()
    responders.append(r)
    # if log: log("Transcribing",url)
    generate_segments(url,rqid,log)
    return 
    
if __name__ == "__main__":

    import json
    from argparse import \
        ArgumentParser as AP, \
        ArgumentDefaultsHelpFormatter as HelpFormatter
    
    
    ap = AP(description='ASR Task', formatter_class=HelpFormatter)
    ap.add_argument('--parallel', '-n', dest='PARALLEL',
                    metavar='workers', type=int,
                    default=os.environ.get('PARALLEL',multiprocessing.cpu_count()),
                    help='messages to process in parallel (or set env variable PARALLEL)')
    ap.add_argument('url', type=str, default="http://data.cstr.inf.ed.ac.uk/summa/data/test.mp4", nargs='+',
                    help='resource URL to be analyzed with ASR')
    
    setup_argparser(ap)
    
    args = ap.parse_args()

    init(args)

    try:
        loop = asyncio.get_event_loop()
        for url in args.url:
            transcribe_file(url,ImmediateCallback(),final_callback,loop,log)
            pass
        for r in responders:
            r.join()
    except KeyboardInterrupt:
        print('INTERRUPTED')
        # for w in asr_workers:
        #     w.terminate()
    except:
        print('EXCEPTION')
        traceback.print_exc()
        # raise
    finally:
        # print('Shutdown')
        shutdown()
