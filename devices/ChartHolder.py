import os
from ctypes import *
import time

current_path = os.path.abspath(__file__)
current_folder = os.path.dirname(current_path)


class Chart_Holder(object):
    Charts = ['MCC', 'BLACK', 'LS', 'KUYE', 'TE42-s', 'TE42']

    def __init__(self):
        super().__init__()
        self.Chart_dependence = os.path.join(current_folder, 'Dependencies', 'Chart')
        self.Chart_api = cdll.LoadLibrary(os.path.join(self.Chart_dependence, 'ChartSwitchPlcDriver_10X.dll'))
        self.host = "192.168.1.1"
        self.error = c_ulong(0)
        self.Chart_command = {
            'back': 0,
            'MCC': 1,
            'BLACK': 2,
            'Plain': 3,
            'KUYE': 7,
            'TE42-s': 8,
            'TE42': 9,
        }

    def connect(self):
        # connect PLC
        self.Chart_api.StartPLCControl(self.host.encode())

        # Enter API
        self.Chart_api.EnterAPIOperationMode(byref(self.error))
        time.sleep(1)

        print('[Online] Chart Holder')

    def switch(self, chart):
        current_chart = self.Chart_api.GetCurrentChartNo(byref(self.error))
        try:
            target_chart = self.Chart_command[chart]
        except KeyError as e:
            print(f'[Error] Invalid Chart: {chart}')
            exit(0)
        if current_chart != target_chart:
            self.Chart_api.SetChartSwitch(c_int(target_chart), byref(self.error))
            print("ChartHolder is moving.....")
            time.sleep(0.5)

            while self.Chart_api.GetChartSwitchIsMoving(byref(self.error)) == 1:
                pass

        print(f'[Done] Switch to: {chart}')

    def back(self):
        self.Chart_api.SetChartBackHome(byref(self.error))
        print("Chart is backing.....")
        time.sleep(0.5)

        while self.Chart_api.GetChartSwitchIsMoving(byref(self.error)) == 1:
            pass
        print('[Done] Cart Back to Home Position')

    def disconnect(self):
        self.Chart_api.ExitAPIOperationMode(byref(self.error))
        time.sleep(2)

        self.Chart_api.StopPLCControl()
        print('[Done] Disconnect Cart Holder')


if __name__ == '__main__':
    chart = Chart_Holder()
    chart.connect()
    chart.switch('MCC')
    # chart.switch('Plain')
    # time.sleep(1)
    # chart.back()
    # chart.disconnect()
