#!/usr/bin/env python3
#
# Author: Didzis Gosko <didzis.gosko@leta.lv>
#

import asyncio, traceback, os, sys, time
import inspect, ctypes
from multiprocessing import Value, Process, Queue
from queue import Empty


class ErrorMessage(Exception): pass


def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class WorkerProcess:

    def __init__(self, run=None, init=None, heartbeat_pause=10, init_args=(), init_kwargs={}):
        if run is not None:
            self.run = run
        if init is not None:
            self.init = init
        self.init_args = init_args
        self.init_kwargs = init_kwargs
        self.heartbeat_pause = heartbeat_pause
        self.process = None
        self.busy = False
        self.input_queue = Queue()
        self.result_queue = Queue()
        self.partial_result_queue = Queue()
        self.last_activity = Value(ctypes.c_size_t)
        self.initialized = Value(ctypes.c_bool)
        self.initialized.value = False
        self.retry = 0
        self.current_input = None
        self.started = False

    def release(self):
        self.busy = False

    def terminate(self):
        if self.process:
            self.process.terminate()

    def start(self):
        self.restart()

    def restart(self):
        if self.process:
            self.process.terminate()
        self.process = Process(target=self.main, args=())
        self.process.start()
        self.started = True

    async def watch_heartbeat(self, restart_timeout=120, refresh=5, max_retries_per_job=3):
        while True:
            await asyncio.sleep(refresh)
            if not self.started:
                continue
            if not self.initialized.value:
                continue
            since_last_activity = int(time.time()) - self.last_activity.value
            # log('seconds since last activity:', since_last_activity) 
            if since_last_activity > restart_timeout: # or (self.started and not self.process.is_alive()):
                # retry 
                if self.busy and self.current_input:
                    if self.retry < max_retries_per_job:
                        self.input_queue.put(self.current_input)
                        self.retry += 1
                    else:
                        self.result_queue.put(ErrorMessage('too many retries, worker not responding'))
                log('warning: worker process timeout reached, restarting...')
                self.restart()

    def heartbeat(self):
        self.last_activity.value = int(time.time())
        return True

    async def pulse(self, pause=10):
        try:
            while True:
                await asyncio.sleep(pause)
                self.heartbeat()
        except asyncio.CancelledError:
            log('Pulse task cancelled!')

    def main(self):
        # create new main event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # call init
        self.heartbeat()
        self.initialized.value = False
        try:
            if hasattr(self, 'init'):
                if inspect.iscoroutinefunction(self.init):
                    loop.create_task(self.init(*self.init_args, **self.init_kwargs))
                else:
                    self.init(*self.init_args, **self.init_kwargs)
            loop.create_task(self.pulse(self.heartbeat_pause))    # ensure pulse during execution of event loop
        except KeyboardInterrupt:
            log('WORKER INTERRUPTED')
            return
        self.initialized.value = True
        while True:
            try:
                self.heartbeat()
                data = self.input_queue.get(True, self.heartbeat_pause)   # get job or sleep
                self.heartbeat()
                try:
                    result = loop.run_until_complete(self.run(data,
                        lambda partial_result: self.heartbeat() and self.partial_result_queue.put(partial_result),
                        loop=loop, heartbeat=self.heartbeat))
                    self.heartbeat()
                    self.result_queue.put(result)
                except KeyboardInterrupt as e:
                    log('WORKER INTERRUPTED')
                    self.result_queue.put(e) # TODO: how to properly propagate to caller ?
                    break
                except Exception as e:
                    log('WORKER EXCEPTION')
                    # traceback.print_exc()
                    exception = ''.join(traceback.format_exception(*sys.exc_info()))
                    self.result_queue.put(ErrorMessage('Exception in worker:\n%s' % exception))
                    # self.result_queue.put(e)
                self.heartbeat()
            except KeyboardInterrupt:
                log('WORKER INTERRUPTED')
                break
            except Empty:
                pass

    async def __call__(self, data, partial_result_callback=None, refresh=1):
        def empty(queue):
            try:
                while not self.input_queue.empty():
                    self.input_queue.get(False)
            except Empty:
                pass
        # make sure all queues are empty
        empty(self.input_queue)
        empty(self.result_queue)
        empty(self.partial_result_queue)
        partial_result_callback_iscoroutine = inspect.iscoroutinefunction(partial_result_callback) if partial_result_callback else None
        # if not self.current_input:
        #     self.restart()
        self.retry = 0
        self.current_input = data
        self.input_queue.put(data)
        try:
            while True:
                try:
                    while not self.partial_result_queue.empty():
                        partial_result = self.partial_result_queue.get(False)
                        # TODO: handle partial_result Exception
                        # if isinstance(partial_result, Exception):
                        #     raise partial_result
                        if partial_result_callback_iscoroutine:
                            await partial_result_callback(partial_result)
                        elif partial_result_callback:
                            partial_result_callback(partial_result)
                    result = self.result_queue.get(False)
                    break
                except Empty:
                    await asyncio.sleep(refresh)
        except asyncio.CancelledError:
            log('Worker call cancelled!')
            # result = None
            raise
        except KeyboardInterrupt:
            log('WORKER CONTROLLER INTERRUPTED')
            raise
        except Exception as e:
            log('WORKER CONTROLLER EXCEPTION', e)
            traceback.print_exc()
            log('restarting worker')
            self.restart()  # any other way to stop a running process ?
            raise
        finally:
            self.current_input = None
            self.busy = False
        if isinstance(result, (Exception, BaseException)):
            raise result
        return result


class WorkerProcessPool:

    class AcquireContextManager:

        def __init__(self, acquire, sleep=2):
            self.acquire = acquire
            self.sleep = sleep

        async def __aenter__(self):
            self.worker = await self.acquire(self.sleep)
            return self.worker

        async def __aexit__(self, exc_type, exc_value, traceback):
            self.worker.release()

    def __init__(self, run=None, init=None, count=None, heartbeat_pause=10, worker_class=WorkerProcess, init_args=(), init_kwargs={}):
        self.worker_class = worker_class
        self.init_args = init_args
        self.init_kwargs = init_kwargs
        self.workers = [worker_class(run, init, heartbeat_pause, init_args=init_args, init_kwargs=init_kwargs) for i in range(count)]
        self._run = run
        self._init = init
        self.count = count

    def allocate(self, count):
        self.workers += [self.worker_class(self._run, self._init, self.heartbeat_pause, init_args=init_args, init_kwargs=init_kwargs)
                for i in range(count-len(self.workers))]

    def start(self):
        for worker in self.workers:
            if not worker.started:
                worker.start()

    def terminate(self):
        watcher_tasks = []
        while self.workers:
            worker = self.workers.pop()
            if hasattr(worker, 'heartbeat_watcher'):
                worker.heartbeat_watcher.cancel()
                watcher_tasks.append(worker.heartbeat_watcher)
            worker.terminate()
        return watcher_tasks

    def reset(self):
        for worker in self.workers:
            worker.restart()

    def watch_heartbeats(self, restart_timeout=120, refresh=5, max_retries_per_job=3, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        for worker in self.workers:
            if not hasattr(worker, 'heartbeat_watcher') or not worker.heartbeat_watcher:
                worker.heartbeat_watcher = loop.create_task(worker.watch_heartbeat(restart_timeout, refresh, max_retries_per_job))

    def acquire(self, sleep=2):
        return self.AcquireContextManager(self.__call__, sleep)

    # acquire idle worker instance
    async def __call__(self, sleep=2):
        while True:
            for worker in self.workers:
                if not worker.busy:
                    worker.busy = True
                    return worker
            asyncio.sleep(sleep)
