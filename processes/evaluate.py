from processes.base import ProcessBase

from analysis.MCC import MCC
from analysis.TE42 import TE42

from config import metric_chart

import os
import json
from pathlib import Path


class ProcessEvaluate(object):
    def __init__(self, task_file):
        self.task_file = task_file
        self.precheck_folder = os.path.join(Path(self.task_file).parent.parent, "precapture")
        self.roi_file = None

        # check task file
        with open(self.task_file, 'r', encoding='utf-8') as f:
            self.task_data = json.load(f)

        self.scene = self.task_data.get('qcat_fail_info').get('lighting_condition')
        self.scene = self.scene.upper()
        self.scene = self.scene.replace('X', 'x')
        self.cct = self.scene.split("_")[0]
        self.light = self.scene.split("_")[1]
        self.plans = self.task_data.get('plan')

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

    def execute(self):
        # pre check
        for name in os.listdir(self.precheck_folder):
            path = os.path.join(self.precheck_folder, name)
            if os.path.isfile(path):
                _, extension = os.path.splitext(name)
                if extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                    try:
                        te42 = TE42(path, 'D65', '1000Lx')
                        te42.gen_roi_file()
                        te42.read_roi()
                        self.roi_file = te42.file_roi
                    except Exception as e:
                        print(e)
                    break

        for plan in self.plans:
            images = plan.get("image")
            plan["IQ_info"] = {}
            for metric, path in images.items():
                if metric_chart[metric] == 'MCC':
                    mcc = MCC(path, self.cct, self.light)
                    mcc.evaluate(metric)
                    plan["IQ_info"] = mcc.info
                if metric_chart[metric] == 'TE42':
                    te42 = TE42(path, self.cct, self.light)
                    try:
                        te42.file_roi = self.roi_file
                        te42.evaluate(metric)
                        plan["IQ_info"] = te42.info
                    except Exception as e:
                        print(e)

        with open(self.task_file, "w", encoding="utf-8") as fm:
            json.dump(self.task_data, fm, ensure_ascii=False, indent=4)


class ProcessFineEvaluate(object):
    def __init__(self, task_file):
        self.task_file = task_file
        self.precheck_folder = os.path.join(Path(self.task_file).parent.parent, "precapture")
        self.roi_file = None

        # check task file
        with open(self.task_file, 'r', encoding='utf-8') as f:
            self.task_data = json.load(f)

        self.scene = self.task_data.get('qcat_fail_info').get('lighting_condition')
        self.scene = self.scene.upper()
        self.scene = self.scene.replace('X', 'x')
        self.cct = self.scene.split("_")[0]
        self.light = self.scene.split("_")[1]

        # check scan round
        if 'current_fine_scan_round' not in self.task_data:
            raise ValueError("[Error] Miss necessary field: current_fine_scan_round")
        else:
            self.current_fine_scan_round = self.task_data['current_fine_scan_round']

        # check scan round combines
        if f'Fine_scan_round_{self.current_fine_scan_round}_combines' not in self.task_data:
            raise ValueError(f"[Error] Miss necessary field: Fine_scan_round_{self.current_fine_scan_round}_combines")
        else:
            self.combines = self.task_data[f'Fine_scan_round_{self.current_fine_scan_round}_combines']

        # check plans
        for i, combine in enumerate(self.combines):
            if 'plans' not in self.combines[combine]:
                raise ValueError(f"[Error] {combine} Miss necessary field: plans")
            if 'tuning_bin_path' not in self.combines[combine]['plans'][0]:
                raise ValueError(f"[Error] {combine} Miss necessary field: tuning_bin_path")

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

    def execute(self):
        # precheck
        for name in os.listdir(self.precheck_folder):
            path = os.path.join(self.precheck_folder, name)
            if os.path.isfile(path):
                _, extension = os.path.splitext(name)
                if extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                    try:
                        te42 = TE42(path, 'D65', '1000Lx')
                        te42.gen_roi_file()
                        te42.read_roi()
                        self.roi_file = te42.file_roi
                    except Exception as e:
                        print(e)
                    break

        for i, combine in enumerate(self.combines):
            comb = self.combines[combine]
            plan = self.combines[combine]['plans'][0]
            images = plan.get("image")
            self.combines[combine]["IQ_info"] = {}
            for metric, path in images.items():
                if metric_chart[metric] == 'MCC':
                    mcc = MCC(path, self.cct, self.light)
                    mcc.evaluate(metric)
                    self.combines[combine]["IQ_info"] = mcc.info
                if metric_chart[metric] == 'TE42':
                    te42 = TE42(path, self.cct, self.light)
                    try:
                        te42.file_roi = self.roi_file
                        te42.evaluate(metric)
                        plan["IQ_info"] = te42.info
                        comb["IQ_info"] = te42.info
                    except Exception as e:
                        print(e)

        with open(self.task_file, "w", encoding="utf-8") as fm:
            json.dump(self.task_data, fm, ensure_ascii=False, indent=4)


class ProcessQcatEvaluate(ProcessBase):
    MCC_Metric = ['Exposure', 'White Balance', 'Color Fidelity']
    TE42_Metric = ['Resolution', 'Contrast', 'Visual Noise']

    def __init__(self, params=None):
        """
        Args:
            params (dict):
                - path (str): Address of QCAT directory structure
                - metric:
        """
        super().__init__(params)

        self.path = None
        self.metrics = None

        self._validate_params()

        self.output = {}

    def _validate_params(self):
        if not isinstance(self.params, dict):
            raise ValueError("Params must be dict type")

        if "path" not in self.params:
            raise ValueError("Missing required parameter 'path'")

        if "metric" not in self.params:
            raise ValueError("Missing required parameter 'metric'")

        self.path = self.params['path']
        self.metrics = self.params['metric']

    def run(self):
        if self.metrics in self.MCC_Metric:
            self.path = os.path.join(self.path, 'MCC')
        if self.metrics in self.TE42_Metric:
            self.path = os.path.join(self.path, 'TE42')
        for root, dirs, files in os.walk(self.path):
            for file in files:
                if file.lower().endswith('.jpg'):
                    image_path = os.path.join(root, file)
                    if self.metrics in self.MCC_Metric:
                        mcc = MCC(image_path)
                        mcc.evaluate(self.metrics)
                        self.output[mcc.cct + '_' + mcc.light] = mcc.info
                    if self.metrics in self.TE42_Metric:
                        te42 = TE42(image_path)
                        te42.evaluate(self.metrics)
                        self.output[te42.cct + '_' + te42.light] = te42.info


if __name__ == '__main__':
    Eva = ProcessFineEvaluate(r'\\10.231.203.160\Auto_test\capturebin\tuning_task_20260331_143811\step_1_fullscan\fine\fine_plan.json')
    Eva.execute()
