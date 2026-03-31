import os
import re
import json

from processes.capture import ProcessBatchCapture, ProcessQcatCapture, ProcessSingleCapture, ProcessBatchFineCapture
from processes.evaluate import ProcessEvaluate, ProcessQcatEvaluate, ProcessFineEvaluate
from processes.simulate import SimulationControlCenter, ProcessSimTuning

from devices.DXO import DXO_Light
from devices.LED import LED_Light

from config import metric_chart


class ProcessCoarseTuning(object):
    def __init__(self, task_file):
        self.task_file = task_file
        self.project_path = None
        self.task_data = None

        self.scene = None
        self.sim = None
        self.raw = None
        self.cct = None
        self.light = None

        self.metrics = []
        self.plans = None

        self.interface_check()
        self.change_bin_path()

    def interface_check(self):
        # 1. check task file
        if not os.path.isfile(self.task_file):
            raise ValueError(f"[Error] '{self.task_file}' is not a valid file path")
        self.project_path = os.path.dirname(self.task_file)

        try:
            with open(self.task_file, 'r', encoding='utf-8') as f:
                self.task_data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError(f"[Error] JSON Format")
        except Exception as e:
            raise ValueError(f"[Error] Fail to open file '{self.task_file}': {e}")

        # 2. check task field
        # 2.1 check task type
        if not isinstance(self.task_data, dict):
            raise ValueError("[Error] Task content must be of dictionary type")

        # 2.2 check scene
        if not self.task_data.get('qcat_fail_info'):
            raise ValueError("[Error] Miss necessary field: qcat_fail_info")

        if not isinstance(self.task_data['qcat_fail_info'], dict):
            raise ValueError("[Error] 'qcat_fail_info' must be of dictionary type")

        if not self.task_data.get('qcat_fail_info').get('lighting_condition'):
            raise ValueError("[Error] Miss necessary field: qcat_fail_info")
        self.scene = self.task_data.get('qcat_fail_info').get('lighting_condition')
        self.scene = self.scene.upper()
        self.scene = self.scene.replace('X', 'x')

        if self.scene not in DXO_Light.Lights and self.scene not in LED_Light.Lights:
            raise ValueError(f"[Error] Invalid lighting condition: {self.scene}")

        self.cct = self.scene.split('_')[0]
        self.light = self.scene.split('_')[1]

        # 2.3 check type
        if not self.task_data.get('type'):
            raise ValueError("[Error] Miss necessary field: type")

        self.metrics = self.task_data.get('type').split(',')
        for i in range(len(self.metrics)):
            self.metrics[i] = self.metrics[i].lower()
            self.metrics[i] = self.metrics[i].title()

            if self.metrics[i] not in metric_chart:
                raise ValueError(f"[Error] Invalid Metric: {self.metrics[i]}")

        # 2.4 check plans
        if not self.task_data.get('plan'):
            raise ValueError("[Error] Miss necessary field: plan")
        self.plans = self.task_data.get('plan')

        if len(self.plans) == 0:
            raise ValueError("[Error] No any plan")

        for i, plan in enumerate(self.plans):
            if not isinstance(plan, dict):
                raise ValueError(f"[Error] Plan{i + 1} must be of dictionary type")
            if not plan.get('tuning_bin_path'):
                raise ValueError(f"[Error] Plan{i + 1} miss necessary field: tuning_bin_path")

        # 2.4 check simulation
        if not self.task_data.get('simulation'):
            raise ValueError("[Error] Miss necessary field: simulation")
        self.sim = self.task_data.get('simulation')
        self.sim = self.sim.lower()
        self.sim = self.sim.title()

        if self.sim not in ['True', 'False']:
            raise ValueError(f"[Error] Invalid simulation: {self.sim}")

        if self.sim == 'True':
            if not self.task_data.get('raw'):
                self.task_data['raw'] = {}
            for metric in self.metrics:
                chart = metric_chart[metric]
                if not self.task_data['raw'].get(chart):
                    self.task_data['raw'][chart] = None

    def execute(self):
        if self.sim == 'False':
            Capture = ProcessBatchCapture(self.task_file)
            Capture.execute()

            Evaluation = ProcessEvaluate(self.task_file)
            Evaluation.execute()

        if self.sim == 'True':
            for metric in self.metrics:
                chart = metric_chart[metric]
                if not self.task_data.get('raw').get(chart):
                    bin0 = self.plans[0].get("tuning_bin_path")
                    raw = os.path.join(self.project_path, f'Raw_{chart}')
                    get_raw_cmd = {
                        'bin': bin0,
                        'scene': self.scene,
                        'chart': chart,
                        'output': raw
                    }
                    get_raw = ProcessSingleCapture(get_raw_cmd)
                    get_raw.execute()
                    self.task_data['raw'][chart] = raw

                    with open(self.task_file, 'w', encoding='utf-8') as f:
                        json.dump(self.task_data, f, indent=4, ensure_ascii=False)

            Sim = SimulationControlCenter(self.task_file)
            Sim.execute()

    def change_bin_path(self):
        for plan in self.plans:
            bin_old = plan.get('tuning_bin_path')
            bin_name = os.path.basename(bin_old)
            bin_folder_name = os.path.basename(os.path.dirname(bin_old))
            bin_new = os.path.join(self.project_path, bin_folder_name, bin_name)
            plan['tuning_bin_path'] = bin_new

        with open(self.task_file, 'w', encoding='utf-8') as f:
            json.dump(self.task_data, f, indent=4, ensure_ascii=False)


class ProcessFineTuning(object):
    def __init__(self, task_file):
        self.task_file = task_file
        self.project_path = None
        self.task_data = None

        self.scene = None
        self.cct = None
        self.light = None
        self.chart = None
        self.metric = None
        self.combines = None

        self.interface_check()

    def interface_check(self):
        # 1. check task file
        if not os.path.isfile(self.task_file):
            raise ValueError(f"[Error] '{self.task_file}' is not a valid file path")

        try:
            with open(self.task_file, 'r', encoding='utf-8') as f:
                self.task_data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError(f"[Error] JSON Format")
        except Exception as e:
            print(f"[Error] Fail to open file '{self.task_file}': {e}")

        # 2. check task field
        # 2.1 check task data type
        if not isinstance(self.task_data, dict):
            raise ValueError("[Error] Task content must be of dictionary type")

        # 2.2 check qcat fail info
        if 'qcat_fail_info' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: qcat_fail_info")

        if not isinstance(self.task_data['qcat_fail_info'], dict):
            raise ValueError("[Error] 'qcat_fail_info' must be of dictionary type")

        # 2.3 check lighting condition
        if 'lighting_condition' not in self.task_data['qcat_fail_info']:
            raise ValueError("[Error] Miss necessary field: qcat_fail_info")
        else:
            self.scene = self.task_data['qcat_fail_info']['lighting_condition']
            self.scene = self.scene.upper()
            self.scene = self.scene.replace('X', 'x')

        # 2.4 check cct and light
        if self.scene.count('_') != 1:
            raise ValueError(f"[Error] Invalid str: {self.scene}")
        else:
            self.cct = self.scene.split('_')[0]
            self.light = self.scene.split('_')[1]

        # 2.5 check metric
        if 'type' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: type")
        else:
            self.metric = self.task_data['type']
            self.metric = self.metric.lower()
            self.metric = self.metric.title()

        # 2.6 check chart
        if self.metric not in metric_chart:
            raise ValueError(f"[Error] Invalid Metric: {self.task_data['type']}")
        else:
            self.chart = metric_chart[self.metric]
            self.chart = self.chart.upper()

        # 2.7 check scan round
        if 'current_fine_scan_round' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: current_fine_scan_round")
        else:
            current_fine_scan_round = self.task_data['current_fine_scan_round']

        # 2.8 check scan round combines
        if f'Fine_scan_round_{current_fine_scan_round}_combines' not in self.task_data:
            raise ValueError(f"[Error] Miss necessary field: Fine_scan_round_{current_fine_scan_round}_combines")
        else:
            self.combines = self.task_data[f'Fine_scan_round_{current_fine_scan_round}_combines']

        # 2.9 check plans
        for i, combine in enumerate(self.combines):
            if 'plans' not in self.combines[combine]:
                raise ValueError(f"[Error] {combine} Miss necessary field: plans")
            if 'tuning_bin_path' not in self.combines[combine]['plans'][0]:
                raise ValueError(f"[Error] {combine} Miss necessary field: tuning_bin_path")

        # 3. standardization
        self.project_path = os.path.join(os.path.dirname(self.task_file), current_fine_scan_round)

    def execute(self):
        Capture = ProcessBatchFineCapture(self.task_file)
        Capture.execute()

        Evaluation = ProcessFineEvaluate(self.task_file)
        Evaluation.execute()


class ProcessMultiSceneTuning(object):
    def __init__(self, task_file):
        self.task_file = task_file
        self.task_data = None
        self.project_path = None

        self.metric = None
        self.chart = None
        self.plan = None

        self.interface_check()

    def interface_check(self):
        # 1. check task file
        if not os.path.isfile(self.task_file):
            raise ValueError(f"[Error] '{self.task_file}' is not a valid file path")
        else:
            self.project_path = os.path.dirname(self.task_file)

        try:
            with open(self.task_file, 'r', encoding='utf-8') as f:
                self.task_data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError(f"[Error] JSON Format")
        except Exception as e:
            print(f"[Error] Fail to open file '{self.task_file}': {e}")

        # 2. check task field
        # 2.1 check task data type
        if not isinstance(self.task_data, dict):
            raise ValueError("[Error] Task content must be of dictionary type")

        # 2.2 check type
        if 'type' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: type")
        else:
            self.metric = self.task_data['type']
            self.metric = self.metric.lower()
            self.metric = self.metric.title()

        # 2.3 check chart
        if self.metric not in metric_chart:
            raise ValueError(f"[Error] Invalid Metric: {self.task_data['type']}")
        else:
            self.chart = metric_chart[self.metric]
            self.chart = self.chart.upper()

        # 2.4 check current plan
        if 'plan' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: plan")

        if not isinstance(self.task_data['plan'], list):
            raise ValueError("[Error] Task content must be of dictionary type")

        if 'current plan' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: current plan")
        else:
            current_plan = int(self.task_data['current plan'])

        if len(self.task_data['plan']) < current_plan:
            raise ValueError(f"[Error] No found plan{current_plan}")
        else:
            self.plan = self.task_data['plan'][current_plan - 1]

        for i, plan in enumerate(self.task_data['plan']):
            if i + 1 == current_plan:
                self.plan = plan

        if not isinstance(self.plan, dict):
            raise ValueError(f"[Error] plan{current_plan} must be of dictionary type")

        if 'tuning_bin_path' not in self.plan:
            raise ValueError("[Error] Miss necessary field: tuning_bin_path")

    def execute(self):
        bin_folder_name = os.path.basename(os.path.dirname(self.plan['tuning_bin_path']))
        bin_name = os.path.basename(self.plan['tuning_bin_path'])
        bin_folder = os.path.join(self.project_path, bin_folder_name)
        bin_path = os.path.join(str(bin_folder), str(bin_name))

        image_folder = bin_folder

        # 2. do capture processing
        capture_cmd = {
            'chart': self.chart,
            'config': bin_path,
            'path': image_folder
        }
        capture_process = ProcessQcatCapture(capture_cmd)
        capture_process.execute()

        # 3. do evaluate processing
        evaluate_cmd = {
            'path': capture_process.qcat_jpg_path,
            'metric': self.metric
        }
        evaluate_process = ProcessQcatEvaluate(evaluate_cmd)
        evaluate_process.run()

        self.plan['IQ_info'] = evaluate_process.output
        self.plan['raw path'] = re.sub(r'C:\\Public', r'\\\\10.231.203.160', capture_process.qcat_raw_path)

        with open(self.task_file, 'w', encoding='utf-8') as f:
            json.dump(self.task_data, f, indent=4, ensure_ascii=False)


if __name__ == '__main__':
    a = ProcessCoarseTuning(r'C:\Public\Auto_test\capturebin\step_1_fullscan\coarse\coarse_plan.json')
    a.execute()


