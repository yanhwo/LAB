import os
import re
import json
import copy
import time
import redis
import shutil
import socket
import threading
import pandas as pd

from processes.base import ProcessBase
from config import metric_chart, Service
from processes.evaluate import ProcessEvaluate
from simulation.simulator import B2YFunc, Simulator
from mq_client import send_message, get_channel, rabbitmq_callback_with_heartbeat

Host = socket.gethostname().upper()


class SimulationControlCenter(ProcessBase):
    def __init__(self, task_file):
        super().__init__(task_file)
        self.task_file = task_file
        self.project_path = os.path.dirname(self.task_file)
        self.task_data = None

        self.services_all = []
        self.Nodes = []

        self.metric = None
        self.scene = None
        self.cct = None
        self.light = None

        self.timestamp = str(int(time.time()))

        self.task_results = {}
        self.lock = threading.Lock()
        self.completed_nodes = set()
        self.all_nodes_completed = threading.Event()
        self.local_task_completed = threading.Event()

    @staticmethod
    def check_node_old(service, port, queue_A, queue_B, mode, path, timeout=10):
        send_message(service, queue_A, {
            "mode": mode,
            "src path": path
        })

        message_received_event = threading.Event()
        message_data = [None]
        stop_flag = threading.Event()  # 添加停止标志

        @rabbitmq_callback_with_heartbeat(interval=10)
        def callback(ch, method, properties, body):
            if not stop_flag.is_set():  # 检查是否已经停止
                print(f"[Online] {service}")
                message_data[0] = json.loads(body)
                message_received_event.set()
                stop_flag.set()  # 设置停止标志
                # 不在回调中直接调用 stop_consuming

        def timeout_handler():
            if not stop_flag.is_set():  # 检查是否已经停止
                print(f"[Offline] {service}")
                stop_flag.set()
                message_received_event.set()  # 触发事件以退出消费循环

        timer = threading.Timer(timeout, timeout_handler)
        timer.daemon = True

        connection = None
        channel = None

        try:
            redis.Redis(host=service, port=port, decode_responses=True)
            connection, channel = get_channel(service)
            channel.queue_declare(queue=queue_B)
            channel.queue_purge(queue=queue_B)
            channel.basic_consume(queue=queue_B, on_message_callback=callback, auto_ack=True)

            print(f"[*] Checking {service}")
            timer.start()

            # 使用非阻塞方式处理消息
            while not stop_flag.is_set():
                connection.process_data_events(time_limit=0.1)

        except KeyboardInterrupt:
            print("Interrupted by user.")
        except Exception as e:
            print(f"[Error] {service}: {e}")
        finally:
            if timer.is_alive():
                timer.cancel()

            # 安全地关闭连接
            if channel and channel.is_open:
                try:
                    channel.stop_consuming()
                except:
                    pass

            if connection and connection.is_open:
                try:
                    connection.close()
                except:
                    pass

        return message_received_event.is_set() and message_data[0] is not None

    @staticmethod
    def check_node(service, port, queue_A, queue_B, mode, path, timeout=10):
        state = {"received": False}

        send_message(service, queue_A, {
            "mode": mode,
            "src path": path
        })

        @rabbitmq_callback_with_heartbeat(interval=10)
        def callback(ch, method, properties, body):
            state["received"] = True
            print(f"[Online] {service}")
            ch.stop_consuming()

        def timeout_handler():
            if not state["received"]:
                print(f"[Offline] {service}")
                try:
                    channel.stop_consuming()
                except Exception as e:
                    print(f"Error stopping consumer: {e}")

        redis.Redis(host=service, port=port, decode_responses=True)

        connection, channel = get_channel(service)
        channel.queue_declare(queue=queue_B)
        channel.queue_purge(queue=queue_B)
        channel.basic_consume(queue=queue_B, on_message_callback=callback, auto_ack=True)

        print(f"[*] Checking {service}")

        timer = threading.Timer(timeout, timeout_handler)
        timer.start()

        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            print("Interrupted by user.")
        except Exception as e:
            print(f"Error during consuming: {e}")
        finally:
            timer.cancel()
            try:
                connection.close()
            except Exception as e:
                print(f"Error closing connection: {e}")

        return state["received"]

    def run_local_task(self, node):
        try:
            process_sim = ProcessSimTuning(node["file"])
            process_sim.execute()
            process_eva = ProcessEvaluate(node["file"])
            process_eva.execute()
            with self.lock:
                self.task_results["local"] = '001'
        finally:
            self.local_task_completed.set()

    def setup_listener(self, node):
        send_message(node["name"], node["A_QUEUE"], {
            "mode": 1,
            "src path": node["file"]
        })
        print(f'send {node["name"]}')

        redis.Redis(host=node["name"], port=node["port"], decode_responses=True)

        connection, channel = get_channel(node["name"])
        channel.queue_declare(queue=node["B_QUEUE"])
        channel.queue_purge(queue=node["B_QUEUE"])
        channel.basic_consume(queue=node["B_QUEUE"], on_message_callback=self.callback, auto_ack=True)
        print(" [*] Waiting for PARAM. To exit press CTRL+C")
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            print("Interrupted by user.")
            channel.stop_consuming()
        finally:
            connection.close()

    def callback(self, ch, method, properties, body):
        data = json.loads(body)
        print(f'Receive:', data)
        ch.stop_consuming()
        with self.lock:
            self.completed_nodes.add(time.time())
            if len(self.completed_nodes) == len(self.Nodes) - 1:
                self.all_nodes_completed.set()

    def init_node(self):
        for node in self.services_all:
            if node == Host:
                res = True
            else:
                mode = 0
                path = None
                res = self.check_node(node, Service[node]['PORT'], Service[node]['A_QUEUE'],
                                      Service[node]['B_QUEUE'], mode, path)

            if res:
                project_path = fr'\\{node}\Auto_test\Sim\{self.timestamp}_{self.metric}'
                bins_path = os.path.join(project_path, 'bins')
                raw_path = os.path.join(project_path, 'raw')
                task_path = os.path.join(project_path, 'sub_plan.json')
                # os.makedirs(project_path, exist_ok=True)
                # os.makedirs(bins_path, exist_ok=True)
                # os.makedirs(raw_path, exist_ok=True)
                self.Nodes.append({
                    'name': node,
                    'port': Service[node]["PORT"],
                    'A_QUEUE': Service[node]["A_QUEUE"],
                    'B_QUEUE': Service[node]["B_QUEUE"],
                    'project': project_path,
                    'bins': bins_path,
                    'raw': raw_path,
                    'file': task_path,
                    'start': None,
                    'end': None
                })

    def setup(self):
        # 0. check task
        with open(self.task_file, 'r', encoding='utf-8') as f:
            self.task_data = json.load(f)
        plans = self.task_data['plan']

        self.metric = self.task_data['type']
        self.metric = self.metric.lower()
        self.metric = self.metric.title()

        self.scene = self.task_data['qcat_fail_info']['lighting_condition']
        self.scene = self.scene.upper()
        self.scene = self.scene.replace('X', 'x')
        self.cct = self.scene.split('_')[0]
        self.light = self.scene.split('_')[1]

        # 1. check node resource
        upper_limit = int(len(plans) / 8)
        for i, ser in enumerate(Service):
            if i + 1 <= upper_limit:
                self.services_all.append(ser)
                print(f'[*] Adding {ser} in simulation plans')
        self.init_node()

        #  2. allocate resources
        local_num = int(len(plans) / (1 + 1.25 * (len(self.Nodes) - 1)))
        remote_num = []
        if len(self.Nodes) - 1 > 0:
            base = (len(plans) - local_num) // (len(self.Nodes) - 1)
            remainder = (len(plans) - local_num) % (len(self.Nodes) - 1)
            remote_num = [base + 1] * remainder + [base] * ((len(self.Nodes) - 1) - remainder)

        end_idx = 0
        remote = 0
        for node in self.Nodes:
            print(f'[*] Setting up {node["name"]}')
            # 2.1 split task
            if node['name'] == Host:
                start_idx = end_idx
                end_idx = start_idx + local_num
            else:
                start_idx = end_idx
                end_idx = start_idx + remote_num[remote]
                remote += 1

            task_data_new = copy.deepcopy(self.task_data)
            task_data_new['plan'] = task_data_new['plan'][start_idx:end_idx]
            node["start"] = start_idx
            node["end"] = end_idx
            print(f"{node['name']}: from {node['start']} to {node['end']}")

            # 2.2 move bins
            for plan in task_data_new['plan']:
                bin_folder_name = os.path.basename(os.path.dirname(plan['tuning_bin_path']))
                bin_folder_src = os.path.join(self.project_path, bin_folder_name)

                bin_folder_dst = os.path.join(node['bins'], os.path.basename(bin_folder_src))
                bin_file_dst = os.path.join(str(bin_folder_dst), os.path.basename(plan['tuning_bin_path']))
                bin_file_dst = re.sub(fr'\\\\{node["name"]}', r'C:\\Public', bin_file_dst)
                plan['tuning_bin_path'] = bin_file_dst
                shutil.copytree(str(bin_folder_src), str(bin_folder_dst))

            # 2.3 move raw
            for chart in task_data_new['raw']:
                raw_folder_src = task_data_new['raw'][chart]
                raw_folder_dst = os.path.join(node['raw'], chart)
                shutil.copytree(str(raw_folder_src), str(raw_folder_dst))
                raw_folder_dst = re.sub(fr'\\\\{node["name"]}', r'C:\\Public', str(raw_folder_dst))
                task_data_new['raw'][chart] = raw_folder_dst

            with open(node['file'], 'w', encoding='utf-8') as f:
                json.dump(task_data_new, f, ensure_ascii=False, indent=2)

            node['file'] = re.sub(fr'\\\\{node["name"]}', r'C:\\Public', str(node['file']))

    def run(self):
        # 1.0 set listener for remote nodes
        listener_threads = []
        for node in self.Nodes:
            if node["name"] != Host:
                listener_thread = threading.Thread(target=self.setup_listener, args=(node,))
                listener_thread.daemon = True
                listener_thread.start()
                listener_threads.append(listener_thread)
            else:
                local_thread = threading.Thread(target=self.run_local_task, args=(node,))
                local_thread.start()

        if len(self.Nodes) == 1:
            self.all_nodes_completed.set()

        # 2. waiting tasks
        self.all_nodes_completed.wait()
        self.local_task_completed.wait()

        print("All tasks completed!")

        # 3. collect
        for i, node in enumerate(self.Nodes):
            node['file'] = re.sub(r'C:\\Public', fr'\\\\{node["name"]}',  str(node['file']))
            with open(node['file'], 'r', encoding='utf-8') as f:
                sub_data = json.load(f)
            for j, plan in enumerate(sub_data["plan"]):
                for chart in plan["image"]:
                    plan["image"][chart] = re.sub(r'C:\\Public', fr'\\\\{node["name"]}',
                                                  str(plan.get("image").get(chart)))
                self.task_data["plan"][j + node["start"]]["image"] = plan.get("image")
                self.task_data["plan"][j + node["start"]]["IQ_info"] = plan.get("IQ_info")

            with open(self.task_file, 'w', encoding='utf-8') as f:
                json.dump(self.task_data, f, ensure_ascii=False, indent=2)


class ProcessSimTuning(object):
    def __init__(self, task_file):
        self.task_file = task_file
        self.project_path = os.path.dirname(self.task_file)

        self.metrics = []
        self.raws = []
        self.plans = None

        # check task file
        with open(self.task_file, 'r', encoding='utf-8') as f:
            self.task_data = json.load(f)

        self.metrics = self.task_data.get('type').split(',')
        for i in range(len(self.metrics)):
            self.metrics[i] = self.metrics[i].lower()
            self.metrics[i] = self.metrics[i].title()

        self.scene = self.task_data.get('qcat_fail_info').get('lighting_condition')
        self.cct = self.scene.split("_")[0]
        self.light = self.scene.split("_")[1]
        self.plans = self.task_data.get('plan')

    @staticmethod
    def find_jpg_from_sim(path):
        jpg_name = 'Snapshot_ipeout_pps_display_FULL_0'
        jpg_path = None
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower().endswith('.jpg') and jpg_name in file:
                    full_path = os.path.join(root, file)
                    jpg_path = full_path
                    break
        return jpg_path

    @staticmethod
    def merge_dicts(dict1, dict2):
        if "score" not in dict1:
            dict1["score"] = {}
        if "score" in dict2:
            dict1["score"].update(dict2["score"])

        if "result" not in dict1:
            dict1["result"] = {}
        if "result" in dict2:
            dict1["result"].update(dict2["result"])

        return dict1

    @staticmethod
    def find_jpg(path):
        for file in os.listdir(path):
            if file.lower().endswith(".jpg"):
                return file

    def execute(self):
        simulation_cmd = []
        for plan in self.plans:
            for metric in self.metrics:
                chart = metric_chart[metric]
                raw = self.task_data.get('raw').get(chart)
                bin = plan.get("tuning_bin_path")
                jpg_name = self.find_jpg(raw)
                simulation_cmd.append({
                    "SubFolder": raw,
                    "JpgName": jpg_name,
                    "TuningBin": bin,
                    "Chart": chart,
                    "Light": self.cct,
                    "LUX": self.light
                })
                print({
                    "SubFolder": raw,
                    "JpgName": jpg_name,
                    "TuningBin": bin,
                    "Chart": chart,
                    "Light": self.cct,
                    "LUX": self.light
                })

        plan_data = pd.DataFrame(simulation_cmd)
        B2Y_func = B2YFunc()
        simulator = Simulator(plan_data, B2Y_func, self.project_path)
        simulator.preprocess_dumps()
        simulator.run_sim()
        simulator.wait_for_simulation()

        folder_name_suffix = 0
        for plan in self.plans:
            plan["image"] = {}
            for metric in self.metrics:
                sim_name = os.path.dirname(simulator.contextData['Rawcsvfile'])
                sim_out = os.path.join(self.project_path, sim_name, "sim" + str(folder_name_suffix))
                plan["image"][metric] = self.find_jpg_from_sim(sim_out)
                folder_name_suffix += 1

        with open(self.task_file, "w", encoding="utf-8") as fm:
            json.dump(self.task_data, fm, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    Sim = SimulationControlCenter(r'C:\workspace\share_all\yanhao\Sim\Contrast\plan30_sim.json')
    # Sim = ProcessSimTuning(r'C:\Public\Auto_test\Sim\1768456611_Contrast\sub_plan.json')
    Sim.execute()
