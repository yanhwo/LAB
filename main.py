from processes.compositeflow import ProcessCoarseTuning, ProcessFineTuning, ProcessMultiSceneTuning
from processes.simulate import SimulationControlCenter
from mq_client import get_channel, send_message, rabbitmq_callback_with_heartbeat
from config import Service
import time
import socket
import redis
import json

HOST = socket.gethostname().upper()


@rabbitmq_callback_with_heartbeat(interval=10)
def callback(ch, method, properties, body):
    data = json.loads(body)
    print(f'Receive:', data)

    src_path = data['src path']
    mode = data['mode']

    if mode == 0:
        time.sleep(2)
        send_message(HOST, Service[HOST]["B_QUEUE"], {
            "Status": 'Get Message',
            "Details": ''
        })
    elif mode == 1:
        process = ProcessCoarseTuning(src_path)
        process.execute()
        send_message(HOST, Service[HOST]["B_QUEUE"], {
            "Status": 'Finish',
            "Details": ''
        })
    elif mode == 2:
        process = ProcessFineTuning(src_path)
        process.execute()
        send_message(HOST, Service[HOST]["B_QUEUE"], {
            "Status": 'Finish',
            "Details": ''
        })
    elif mode == 3:
        process = ProcessMultiSceneTuning(src_path)
        process.execute()
        send_message(HOST, Service[HOST]["B_QUEUE"], {
            "Status": 'Done',
            "Details": ''
        })
    elif mode == 4:
        process = SimulationControlCenter(src_path)
        process.execute()
        send_message(HOST, Service[HOST]["B_QUEUE"], {
            "Status": 'Done',
            "Details": ''
        })
    else:
        time.sleep(2)
        send_message(HOST, Service[HOST]["B_QUEUE"], {
            "Status": 'Finish',
            "Details": ''
        })
    print('succeed to send')


if __name__ == '__main__':

    rds = redis.Redis(host=HOST, port=Service[HOST]["PORT"], decode_responses=True)

    connection, channel = get_channel(HOST)
    channel.queue_declare(queue=Service[HOST]["A_QUEUE"])
    channel.queue_purge(queue=Service[HOST]["A_QUEUE"])
    channel.basic_consume(queue=Service[HOST]["A_QUEUE"], on_message_callback=callback, auto_ack=True)
    print(" [*] Waiting for PARAM. To exit press CTRL+C")

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Interrupted by user.")
        channel.stop_consuming()
    finally:
        connection.close()

