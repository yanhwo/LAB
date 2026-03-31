# mq_client.py for testing_service
import pika
import json
import threading
import time
from functools import wraps
from config import RABBITMQ_USERNAME, RABBITMQ_PASSWORD


def get_channel(host):
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=host,
        credentials=credentials,
        heartbeat=1200,
        blocked_connection_timeout=300,
        connection_attempts=3,
        retry_delay=5
    )
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    return connection, channel


def send_message(host, queue, message):
    connection, channel = get_channel(host)
    channel.queue_declare(queue=queue)
    channel.basic_publish(exchange='', routing_key=queue, body=json.dumps(message).encode())
    connection.close()


def rabbitmq_callback_with_heartbeat(interval=10, auto_ack=True):
    def decorator(func):
        @wraps(func)
        def wrapper(ch, method, properties, body):
            stop_event = threading.Event()
            def heartbeat():
                while not stop_event.is_set():
                    try:
                        ch.connection.process_data_events()
                    except Exception as e:
                        print(f"[Heartbeat] Error: {e}")
                    time.sleep(interval)
            thread = threading.Thread(target=heartbeat)
            thread.daemon = True
            thread.start()
            try:
                result = func(ch, method, properties, body)
                return result
            except Exception as e:
                print(f"[Callback Error] {e}")
                if not auto_ack:
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                raise
            finally:
                stop_event.set()
        return wrapper
    return decorator
