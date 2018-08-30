#!/usr/bin/env python3
#
# Author: Didzis Gosko <didzis.gosko@leta.lv>
#

import sys, asyncio, json, traceback, inspect
from concurrent.futures import CancelledError

from aio_pika import connect, Message, ExchangeType
import pika.exceptions

try:
    from task import NoFinalResult
except ImportError:
    class NoFinalResult(Exception): pass

try:
    from task import ErrorMessage
except ImportError:
    class ErrorMessage(Exception): pass

try:
    from task import RejectError
except ImportError:
    class RejectError(Exception): pass

try:
    from task import RejectRequeueError
except ImportError:
    class RejectRequeueError(Exception): pass

try:
    import task
except ImportError:

    if __name__ == "__main__":
        print('warning: module task not found, use "--dummy" argument to use dummy test task for RabbitMQ client', file=sys.stderr)

        import sys
        if '--dummy' not in sys.argv[1:]:
            raise

        class DummyTask:
            name = 'DUMMY-TEST-TASK'
            def setup_argparser(self, parser):
                parser.add_argument('--test', action='store_true', help='test with %s' % self.name)
            def init(self, args=None):
                print('Initializing %s ...' % self.name, file=sys.stderr)
                if args.test:
                    print('%s test mode enabled')
                self.args = args
            def shutdown(self):
                print('shutting down %s ...' % self.name, file=sys.stderr)
            def reset(self):
                print('restarting %s ...' % self.name, file=sys.stderr)
            async def process_message(self, task_data, loop=None, send_reply=None, **kwargs):
                print('%s will process input data:' % self.name, task_data)
                if self.args:
                    print('Test mode enabled')
                for i in range(5):
                    print('Waiting %i seconds for first partial result to be sent' % i)
                    await asyncio.sleep(i)
                    if send_reply:
                        await send_reply('%i. partial result from %s' % (i, self.name))
                print('%s is complete!' % self.name)
                return 'Final result of %s: SUCCESS' % self.name

        task = DummyTask()



async def on_message(message, reply, loop=None, name=task.name, verbose=True, **kwargs):
    # with message.process():   # with message auto acknowledgement
    routing_keys = message.headers['replyToRoutingKeys']
    body_dict = json.loads(message.body.decode("utf-8"))
    task_data = body_dict['taskData']
    task_metadata = body_dict['taskMetadata']

    async def send_reply(result_data, result_type='partialResult'):
        await reply(
            Message(
                bytes(json.dumps(dict(resultData=result_data, resultType=result_type, taskMetadata=task_metadata)), 'utf8'),
                headers=dict(resultProducerName=name)
            ),
            routing_keys[result_type]
        )

    try:
        item = task_metadata.get('itemId', 'unknown')
        if verbose:
            print('New job request for item %s received!' % item)
            # print(task_metadata)
            # print(task_data)

        result_data = await task.process_message(task_data, loop=loop, send_reply=send_reply, **kwargs)

        if verbose:
            print('Job for item %s completed!' % item)

        await send_reply(result_data, 'finalResult')
        message.ack()
    except NoFinalResult:
        print('Job for item %s completed!' % item)
        message.ack()
    except RejectError as e:
        if verbose:
            print('Job for item %s rejected:' % item, e)
        message.reject(requeue=False)
        return
    except RejectRequeueError as e:
        if verbose:
            print('Job for item %s rejected (and requeued):' % item, e)
        message.reject(requeue=True)
        return
    except CancelledError:
        # stop, do not send reply, requeue incomming message
        if verbose:
            print('Job for item %s cancelled!' % item)
        try:
            message.reject(requeue=True)
        except pika.exceptions.ConnectionClosed:
            pass
        # raise
        return
    except KeyboardInterrupt:
        # stop, do not send reply, requeue incomming message
        if verbose:
            print('Job for item %s cancelled!' % item)
        message.reject(requeue=True)
        # raise
        return
    except ErrorMessage as e:
        if verbose:
            print('Job for item %s failed with error:' % item, e)
        else:
            log(e)
        await send_reply(str(e), 'processingError')
        message.ack()
    except Exception as e:
        # traceback.print_exc()
        exception = ''.join(traceback.format_exception(*sys.exc_info()))
        if verbose:
            print('Job for item %s failed with error: %s\n%s' % (item, str(e), exception))
        await send_reply(exception, 'processingError')
        # await send_reply(str(e), 'processingError')
        message.ack()

    # await reply(
    #     Message(
    #         bytes(json.dumps(dict(resultData=result_data, resultType=result_type, taskMetadata=task_metadata)), 'utf8'),
    #         headers=dict(resultProducerName=name)
    #     ),
    #     routing_keys[result_type]
    # )


def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


async def run(url, input_queue, output_exchange, loop=None, num_parallel=1, reconnect_delay=5,
        on_message=None, handle_all_exceptions=True, kwargs={}):

    async def reconnect(first=True):
        nonlocal reconnect_delay
        log('Connecting' if first else 'Reconnecting', 'to', url, end=' ', flush=True)
        while True:
            try:
                if not first:
                    await asyncio.sleep(reconnect_delay)
                else:
                    first = False
                log('.', end='', flush=True)
                await _connect()
                break
            except pika.exceptions.IncompatibleProtocolError:
                # keep silent, this happens during rabbitmq startup
                pass
            except ConnectionRefusedError:
                # was unable to connect, will retry
                pass
            except ConnectionError as e:
                log('Connection error:', e)
            # except pika.exceptions.ChannelClosed as e:
            #     pass
            except KeyboardInterrupt:
                log('RECONNECT INTERRUPTED')
                raise
            except Exception as e:
                if handle_all_exceptions:
                    log('Unexpected exception at reconnect()')
                    traceback.print_exc()
                    await connection.close()
                else:
                    await connection.close()
                    if hasattr(task, 'shutdown'):
                        task.shutdown()
                    # loop.stop()
                    raise

    def on_connection_closed(future):
        try:
            future.result()
        except ConnectionError as e:
            log('Connection lost, will reconnect')
            # asyncio.sleep(connection.close())
            t = asyncio.ensure_future(reconnect(False))
            # do not await lost messages
            for t in asyncio.Task.all_tasks():
                if hasattr(t, 'must_await'):
                    t.must_await = False
                    t.cancel()
            if hasattr(task, 'reset'):
                task.reset()
        except Exception as e:
            log('Unexpected exception at on_connection_closed()')
            traceback.print_exc()

    def get_on_message():
        global on_message
        return on_message

    def message_callback(message):
        t = asyncio.ensure_future((on_message or get_on_message())(message, exchange_out.publish, loop=loop, **kwargs))
        t.must_await = True   # hack to identify on_message tasks

    async def _connect():
        nonlocal connection, queue_in, exchange_out
        connection = await connect(url, loop=loop)
        connection.add_close_callback(on_connection_closed)
        log(' connected!')

        try:

            channel_in = await connection.channel()
            await channel_in.set_qos(prefetch_count=num_parallel)
            channel_out = await connection.channel()

            exchange_out = await channel_out.declare_exchange(output_exchange, ExchangeType.TOPIC, durable=False)

            queue_in = await channel_in.declare_queue(input_queue, passive=False)

            if inspect.iscoroutinefunction(queue_in.consume):
                await queue_in.consume(message_callback)
            else:
                queue_in.consume(message_callback)
            # queue_in.consume(lambda message: asyncio.ensure_future(
            #     (on_message or get_on_message())(message, exchange_out.publish, loop=loop, **kwargs))
            # )

        # except:
        except Exception as e:
            print('_CONNNECT EXCEPTION:', e)
            # await connection.close()  # if closed, will not reconnect
            # will be handled at reconnect()
            raise

    connection = None
    queue_in = None
    exchange_out = None

    if not loop:
        loop = asyncio.get_event_loop()

    await reconnect()


def wait_for_incomplete_message_callbacks(loop):
    pending_on_message_tasks = [t for t in asyncio.Task.all_tasks() if hasattr(t, 'must_await') and t.must_await]
    loop.run_until_complete(asyncio.gather(*pending_on_message_tasks))
    # loop.run_until_complete(loop.shutdown_asyncgens())    # Python 3.6


def run_forever(url=None, queue_in=None, exchange_out=None, num_parallel=1, reconnect_delay=5, debug=False,
        on_message=None, handle_all_exceptions=True, **kwargs):
    try:
        loop = asyncio.get_event_loop()
        loop.set_debug(False)
        loop.create_task(run(url, queue_in, exchange_out, loop=loop, num_parallel=num_parallel, reconnect_delay=reconnect_delay,
            on_message=on_message, handle_all_exceptions=handle_all_exceptions, kwargs=kwargs))
        loop.run_forever()
    except KeyboardInterrupt:
        log('MAIN INTERRUPTED')
        for f in asyncio.Task.all_tasks():
            f.cancel()
            loop.stop()
            loop.run_forever()
            return
        try:
            wait_for_incomplete_message_callbacks(loop)
            if hasattr(task, 'shutdown'):
                wait_for_tasks = task.shutdown()
                if wait_for_tasks:
                    loop.run_until_complete(asyncio.gather(*wait_for_tasks))
        except CancelledError:
            pass
        except KeyboardInterrupt:
            log('MAIN INTERRUPTED')
        loop.stop()


def main(task=task):

    import os
    import argparse

    parser = argparse.ArgumentParser(description='RabbitMQ Worker', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--parallel', '-n', dest='PARALLEL', type=int, default=os.environ.get('PARALLEL',1),
            help='messages to process in parallel (or set env variable PARALLEL)')
    parser.add_argument('--reconnect-delay', type=int, default=os.environ.get('RECONNECT_DELAY', 5),
            help='number of seconds to wait before reconnect attempt (or set env variable RECONNECT_DELAY)')
    parser.add_argument('--startup-delay', type=int, default=os.environ.get('STARTUP_DELAY', 0),
            help='number of seconds to wait before starting RabbitMQ client (or set env variable STARTUP_DELAY)')
    parser.add_argument('--debug', action='store_true', help='debug mode for asyncio')
    parser.add_argument('--verbose', '-v', action='store_true', help='verbose message processing mode')
    parser.add_argument('--out', dest='EXCHANGE_OUT', type=str, default=os.environ.get('EXCHANGE_OUT'),
            help='output exchange (or set env variable EXCHANGE_OUT)')
    parser.add_argument('--in', dest='QUEUE_IN', type=str, default=os.environ.get('QUEUE_IN'),
            help='input queue (or set env variable QUEUE_IN)')
    parser.add_argument('--url', dest='RABBITMQ_URL', type=str, default=os.environ.get('RABBITMQ_URL'),
            help='RabbitMQ URL (or set env variable RABBITMQ_URL)')

    if hasattr(task, 'setup_argparser'):
        task.setup_argparser(parser)

    args = parser.parse_args()

    if not args.RABBITMQ_URL:
        log("error: RabbitMQ URL is not set")
        sys.exit(1)

    if not args.QUEUE_IN:
        log("error: RabbitMQ input queue is not set")
        sys.exit(1)

    if not args.EXCHANGE_OUT:
        log("error: RabbitMQ output exchange is not set")
        sys.exit(1)

    try:
        if hasattr(task, 'init'):
            task.init(args)

        if args.startup_delay > 0:
            import time
            log("Waiting %i seconds before starting RabbitMQ client ..." % args.startup_delay)
            time.sleep(args.startup_delay)
    except KeyboardInterrupt:
        log("INTERRUPTED")
        if hasattr(task, 'shutdown'):
            task.shutdown()
        sys.exit(1)

    log("Starting RabbitMQ client ...")

    run_forever(args.RABBITMQ_URL, args.QUEUE_IN, args.EXCHANGE_OUT, num_parallel=args.PARALLEL, reconnect_delay=args.reconnect_delay,
            debug=args.debug, verbose=args.verbose)


if __name__ == "__main__":
    main()
