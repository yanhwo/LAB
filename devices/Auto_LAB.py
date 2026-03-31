import time

from ChartHolder import Chart_Holder
from DXO import DXO_Light
from LED import LED_Light
from Mobile import Mobile_Phone
from Robot_auto import *


class Capture(object):
    OBJ = ['Mobile']

    def __init__(self, obj, scenes, charts, config, output):
        self.obj = obj
        self.scenes = scenes
        self.charts = charts
        self.config = config
        self.output = output

        self.DXO = DXO_Light()
        self.dxo_scenes = []

        self.LED = LED_Light()
        self.led_scenes = []

        self.Chart = Chart_Holder()

        self.input_check()

    def input_check(self):
        # check object
        if self.obj in self.OBJ:
            pass
        else:
            raise ValueError(f'Invalid test object: {self.obj}')

        # check scene
        for scene in self.scenes:
            if scene in self.DXO.Lights:
                self.dxo_scenes.append(scene)
            elif scene in self.LED.Lights:
                self.led_scenes.append(scene)
            else:
                raise ValueError(f'Invalid scene: {scene}')

        # check charts
        for chart in self.charts:
            if chart in self.Chart.Charts:
                pass
            else:
                raise ValueError(f'Invalid chart: {chart}')

    def process(self):
        # DXO Process
        for dxo_scene in self.dxo_scenes:
            self.DXO.open(dxo_scene)

            for chart in self.charts:
                self.Chart.switch(chart)

        time.sleep(2)
        self.DXO.close()

        # LED Process
        for led_scene in self.led_scenes:
            self.LED.open(led_scene)

        time.sleep(2)
        self.LED.close()


if __name__ == '__main__':
    auto_lab = Capture('Mobile', ['A_20Lx'], ['MCC'], None, r'C:\Public\Auto_test\6')
    auto_lab.process()







