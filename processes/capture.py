from processes.base import ProcessBase

from devices.ChartHolder import Chart_Holder
from devices.DXO import DXO_Light
from devices.LED import LED_Light, LEDLightProcess
from devices.Mobile import Mobile_Phone
from devices.Robot import Robot_Arm

from config import metric_chart

import os
import json
import time
import shutil
from pathlib import Path

current_path = os.path.abspath(__file__)
current_folder = os.path.dirname(current_path)


class ProcessSingleCapture(ProcessBase):
    def __init__(self, param):
        super().__init__(param)

        # check param
        self.bin = param.get('bin')
        self.chart = param.get('chart')
        self.scene = param.get('scene')
        self.output = param.get('output')

        self.target_light = None

        # init devices
        self.chart_holder = Chart_Holder()
        self.dxo_light = DXO_Light()
        self.led_light = LED_Light()
        self.mobile = Mobile_Phone()
        self.robot = Robot_Arm()

    def setup(self):
        if self.scene in self.led_light.Lights:
            self.led_light.connect()
            self.target_light = 'LED'
        elif self.scene in self.dxo_light.Lights:
            self.dxo_light.connect()
            self.chart_holder.connect()
            self.target_light = 'DXO'

        self.mobile.connect()
        self.robot.connect()

    def run(self):
        # 1. open the light
        if self.target_light == 'LED':
            self.led_light.open(self.scene)
        if self.target_light == 'DXO':
            self.dxo_light.open(self.scene)

        # 2. switch the chart
        if self.target_light == 'LED':
            pass
        if self.target_light == 'DXO':
            self.chart_holder.switch(self.chart)

        # 3. move robot
        if self.target_light == 'LED' and self.chart == 'MCC':
            self.robot.move_to_chart('MCC_Box')
        if self.target_light == 'DXO' and self.chart == 'MCC':
            self.robot.move_to_chart('MCC_Holder')
        if self.target_light == 'DXO' and self.chart == 'TE42':
            self.robot.move_to_chart('TE42')

        # 4. do capture
        self.mobile.take_photo(self.bin)
        self.mobile.dump_raw(self.output)

    def cleanup(self):
        self.robot.back_to_origin()
        time.sleep(0.5)
        if self.target_light == 'LED':
            self.led_light.close()
            self.led_light.disconnect()
        if self.target_light == 'DXO':
            self.chart_holder.back()
            self.chart_holder.disconnect()
            time.sleep(0.5)
            self.dxo_light.close()
            self.dxo_light.disconnect()


class ProcessBatchCapture(ProcessBase):
    def __init__(self, task_file):
        super().__init__(task_file)

        self.task_file = task_file
        self.project_path = os.path.dirname(self.task_file)

        self.metrics = []
        self.target_light = None

        # check task file
        with open(self.task_file, 'r', encoding='utf-8') as f:
            self.task_data = json.load(f)

        self.metrics = self.task_data.get('type').split(',')
        for i in range(len(self.metrics)):
            self.metrics[i] = self.metrics[i].lower()
            self.metrics[i] = self.metrics[i].title()

        self.scene = self.task_data.get('qcat_fail_info').get('lighting_condition')
        self.scene = self.scene.upper()
        self.scene = self.scene.replace('X', 'x')
        self.cct = self.scene.split("_")[0]
        self.light = self.scene.split("_")[1]

        self.plans = self.task_data.get('plan')

        # init devices
        self.chart_holder = Chart_Holder()
        self.dxo_light = DXO_Light()
        self.led_light = LED_Light()
        self.mobile = Mobile_Phone()
        self.robot = Robot_Arm()

    def setup(self):
        if self.scene in self.led_light.Lights:
            self.led_light.connect()
            self.target_light = 'LED'
        elif self.scene in self.dxo_light.Lights:
            self.dxo_light.connect()
            self.chart_holder.connect()
            self.target_light = 'DXO'
        else:
            raise ValueError(f"Invalid Env: {self.scene}")

        self.mobile.connect()
        self.robot.connect()

    def run(self):
        # 0. init output
        for plan in self.plans:
            plan["image"] = {}

        # 1. open the light
        if self.target_light == 'LED':
            self.led_light.open(self.scene)
        if self.target_light == 'DXO':
            self.dxo_light.open(self.scene)

        for metric in self.metrics:
            chart = metric_chart[metric]

            # 2. switch the chart
            if self.target_light == 'LED':
                pass
            if self.target_light == 'DXO':
                self.chart_holder.switch(chart)

            # 3. move the robot
            if self.target_light == 'LED' and chart == 'MCC':
                self.robot.move_to_chart('MCC_Box')
            if self.target_light == 'DXO' and chart == 'MCC':
                self.robot.move_to_chart('MCC_Holder')
            if self.target_light == 'DXO' and chart == 'TE42':
                self.robot.move_to_chart('TE42')

            # 4. pre check
            precheck_folder = os.path.join(Path(self.task_file).parent.parent, "precapture")
            if os.path.exists(precheck_folder):
                shutil.rmtree(precheck_folder)
            os.makedirs(precheck_folder, exist_ok=False)
            self.mobile.take_photo(r'C:\Public\capture\precheck\com.qti.tuned.qtech_imx858.canoe.bin')
            self.mobile.dump_jpg(precheck_folder)

            for plan in self.plans:
                bin = plan.get("tuning_bin_path")
                bin_folder_name = os.path.basename(os.path.dirname(bin))
                bin_name = os.path.basename(bin)
                bin_folder = os.path.join(self.project_path, bin_folder_name)
                bin_path = os.path.join(str(bin_folder), str(bin_name))

                self.mobile.take_photo(bin_path)
                self.mobile.dump_jpg(bin_folder)
                plan["image"][metric] = self.mobile.jpg

        with open(self.task_file, "w", encoding="utf-8") as fm:
            json.dump(self.task_data, fm, ensure_ascii=False, indent=4)

    def cleanup(self):
        self.robot.back_to_origin()
        time.sleep(0.5)
        if self.target_light == 'LED':
            self.led_light.close()
            self.led_light.disconnect()
        if self.target_light == 'DXO':
            self.chart_holder.back()
            self.chart_holder.disconnect()
            time.sleep(0.5)
            self.dxo_light.close()
            self.dxo_light.disconnect()


class ProcessBatchFineCapture(ProcessBase):
    def __init__(self, task_file):
        super().__init__(task_file)

        self.task_file = task_file
        self.project_path = os.path.dirname(self.task_file)

        self.metrics = []
        self.target_light = None

        # check task file
        with open(self.task_file, 'r', encoding='utf-8') as f:
            self.task_data = json.load(f)

        self.metrics = self.task_data.get('type').split(',')
        for i in range(len(self.metrics)):
            self.metrics[i] = self.metrics[i].lower()
            self.metrics[i] = self.metrics[i].title()

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

        # init devices
        self.chart_holder = Chart_Holder()
        self.dxo_light = DXO_Light()
        self.led_light = LED_Light()
        self.mobile = Mobile_Phone()
        self.robot = Robot_Arm()

    def setup(self):
        if self.scene in self.led_light.Lights:
            self.led_light.connect()
            self.target_light = 'LED'
        elif self.scene in self.dxo_light.Lights:
            self.dxo_light.connect()
            self.chart_holder.connect()
            self.target_light = 'DXO'
        else:
            raise ValueError(f"Invalid Env: {self.scene}")

        self.mobile.connect()
        self.robot.connect()

    def run(self):
        for i, combine in enumerate(self.combines):
            plan = self.combines[combine]['plans'][0]
            plan["image"] = {}
            bin_folder_name = os.path.basename(os.path.dirname(plan['tuning_bin_path']))
            bin_name = os.path.basename(plan['tuning_bin_path'])
            bin_folder = os.path.join(self.project_path, self.current_fine_scan_round, bin_folder_name)
            bin_path = os.path.join(str(bin_folder), str(bin_name))

            # 1. open the light
            if self.target_light == 'LED':
                self.led_light.open(self.scene)
            if self.target_light == 'DXO':
                self.dxo_light.open(self.scene)

            # 2. switch the chart
            for metric in self.metrics:
                chart = metric_chart[metric]
                if self.target_light == 'LED':
                    pass
                if self.target_light == 'DXO':
                    self.chart_holder.switch(chart)

                # 3. move the robot
                if self.target_light == 'LED' and chart == 'MCC':
                    self.robot.move_to_chart('MCC_Box')
                if self.target_light == 'DXO' and chart == 'MCC':
                    self.robot.move_to_chart('MCC_Holder')
                if self.target_light == 'DXO' and chart == 'TE42':
                    self.robot.move_to_chart('TE42')

                self.mobile.take_photo(bin_path)
                self.mobile.dump_jpg(bin_folder)
                plan["image"][metric] = self.mobile.jpg

        with open(self.task_file, "w", encoding="utf-8") as fm:
            json.dump(self.task_data, fm, ensure_ascii=False, indent=4)

    def cleanup(self):
        self.robot.back_to_origin()
        time.sleep(0.5)
        if self.target_light == 'LED':
            self.led_light.close()
            self.led_light.disconnect()
        if self.target_light == 'DXO':
            self.chart_holder.back()
            self.chart_holder.disconnect()
            time.sleep(0.5)
            self.dxo_light.close()
            self.dxo_light.disconnect()


class ProcessQcatCapture(ProcessBase):
    # TE42_lights = ['A_20Lx', 'TL84_20Lx']
    TE42_lights = ['A_20Lx', 'A_100Lx', 'D65_100Lx', 'D65_1000Lx', 'TL84_20Lx', 'TL84_100Lx', 'TL84_1000Lx']
    # MCC_DXO_lights = ['TL84_20Lx']
    MCC_DXO_lights = ['A_20Lx', 'A_100Lx', 'TL84_20Lx', 'TL84_100Lx', 'TL84_1000Lx', 'D65_100Lx', 'D65_1000Lx']
    # MCC_LED_lights = ['D50_100Lx', 'D50_1000Lx']
    MCC_LED_lights = ['CWF_20Lx', 'CWF_100Lx', 'CWF_1000Lx', 'D50_20Lx', 'D50_100Lx', 'D50_1000Lx', 'H_20Lx', 'H_100Lx']

    def __init__(self, params=None):
        super().__init__(params)
        self._validate_params()
        self.template_folder = os.path.join(current_folder, 'QCAT_Template')

        self.chart = params['chart']
        self.config = params['config']
        self.path = params['path']

        self.qcat_jpg_path = os.path.join(self.path, 'JPG')
        self.qcat_raw_path = os.path.join(self.path, 'RAW')

        # init devices
        self.chart_holder = Chart_Holder()
        self.dxo_light = DXO_Light()
        self.mobile = Mobile_Phone()
        self.robot = Robot_Arm()
        self.led_light = LEDLightProcess()

    def _validate_params(self):
        if "chart" not in self.params:
            raise ValueError("Missing required parameter 'chart'")

        if "config" not in self.params:
            raise ValueError("Missing required parameter 'config'")

        if "path" not in self.params:
            raise ValueError("Missing required parameter 'path'")

    def setup(self):
        if self.chart == 'All' or self.chart == 'MCC' or self.chart == 'Temp':
            self.led_light.start()
            self.led_light.connect()
            self.led_light.close()

        self.dxo_light.connect()
        self.dxo_light.close()
        self.chart_holder.connect()
        self.mobile.connect()
        self.robot.connect()

    def run(self):
        # 1. copy Qcat folders
        if os.path.exists(self.qcat_jpg_path):
            shutil.rmtree(self.qcat_jpg_path)

        shutil.copytree(self.template_folder, self.qcat_jpg_path)

        if os.path.exists(self.qcat_raw_path):
            shutil.rmtree(self.qcat_raw_path)

        shutil.copytree(self.template_folder, self.qcat_raw_path)

        # 2. capture
        if self.config:
            self.mobile.pushBin(self.config)

        if self.chart == 'All':
            for te42_light in self.TE42_lights:
                cct = te42_light.split('_')[0]
                light = te42_light.split('_')[1]
                jpg_path = os.path.join(self.qcat_jpg_path, 'TE42', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'TE42', cct, light)

                self.dxo_light.open(te42_light)
                self.chart_holder.switch('TE42')
                self.robot.move_to_chart('TE42')
                self.mobile.take_photo(self.config)
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            for mcc_light in self.MCC_DXO_lights:
                cct = mcc_light.split('_')[0]
                light = mcc_light.split('_')[1]
                jpg_path = os.path.join(self.qcat_jpg_path, 'MCC', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'MCC', cct, light)

                self.dxo_light.open(mcc_light)
                self.chart_holder.switch('MCC')
                self.robot.move_to_chart('MCC_Holder')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.dxo_light.close()

            for mcc_light in self.MCC_LED_lights:
                cct = mcc_light.split('_')[0]
                light = mcc_light.split('_')[1]
                jpg_path = os.path.join(self.qcat_jpg_path, 'MCC', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'MCC', cct, light)

                self.led_light.open(mcc_light)
                self.robot.move_to_chart('MCC_Box')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.led_light.close()

        if self.chart == 'MCC':

            for mcc_light in self.MCC_LED_lights:
                cct = mcc_light.split('_')[0]
                light = mcc_light.split('_')[1]
                jpg_path = os.path.join(self.qcat_jpg_path, 'MCC', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'MCC', cct, light)

                self.led_light.open(mcc_light)
                self.robot.move_to_chart('MCC_Box')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.led_light.close()

            for mcc_light in self.MCC_DXO_lights:
                cct = mcc_light.split('_')[0]
                light = mcc_light.split('_')[1]
                jpg_path = os.path.join(self.qcat_jpg_path, 'MCC', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'MCC', cct, light)

                self.chart_holder.connect()
                self.chart_holder.switch('MCC')
                self.dxo_light.open(mcc_light)
                self.robot.move_to_chart('MCC_Holder')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.dxo_light.close()

        if self.chart == 'TE42':

            for te42_light in self.TE42_lights:
                cct = te42_light.split('_')[0]
                light = te42_light.split('_')[1]
                jpg_path = os.path.join(self.qcat_jpg_path, 'TE42', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'TE42', cct, light)

                self.dxo_light.open(te42_light)
                self.chart_holder.switch('TE42')
                self.robot.move_to_chart('TE42')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.dxo_light.close()

        if self.chart == 'Temp':

            for mcc_light in self.MCC_DXO_lights:
                cct = mcc_light.split('_')[0]
                light = mcc_light.split('_')[1]

                jpg_path = os.path.join(self.qcat_jpg_path, 'Plain', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'Plain', cct, light)

                self.dxo_light.open(mcc_light)
                self.chart_holder.switch('Plain')
                self.robot.move_to_chart('MCC_Holder')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.dxo_light.close()

            for mcc_light in self.MCC_LED_lights:
                cct = mcc_light.split('_')[0]
                light = mcc_light.split('_')[1]

                jpg_path = os.path.join(self.qcat_jpg_path, 'Plain', cct, light)
                raw_path = os.path.join(self.qcat_raw_path, 'Plain', cct, light)

                self.led_light.open(mcc_light)
                self.robot.move_to_chart('Plain')
                self.mobile.take_photo()
                self.mobile.dump_jpg(jpg_path)
                self.mobile.dump_raw(raw_path)

            self.led_light.close()

    def cleanup(self):
        self.robot.back_to_origin()
        self.dxo_light.disconnect()
        self.chart_holder.connect()
        self.chart_holder.back()
        self.chart_holder.disconnect()
        if self.chart == 'All' or self.chart == 'MCC':
            self.led_light.disconnect()
            self.led_light.terminate()
            self.led_light.join()


if __name__ == '__main__':

    a = ProcessBatchFineCapture(r'\\10.231.203.160\Auto_test\capturebin\tuning_task_20260331_143811\step_1_fullscan\fine\fine_plan.json')
    a.execute()


