import os
import time
from ctypes import *
import ctypes
import multiprocessing
import queue

current_path = os.path.abspath(__file__)
current_folder = os.path.dirname(current_path)


class LED_Light(object):
    Lights = ['CWF_1000Lx', 'CWF_100Lx', 'CWF_20Lx',
              'D50_1000Lx', 'D50_100Lx', 'D50_20Lx',
              'H_100Lx', 'H_20Lx']

    def __init__(self):
        super().__init__()
        self.LED_dependence = os.path.join(current_folder, 'Dependencies', 'LED')
        self.LED_api = cdll.LoadLibrary(os.path.join(self.LED_dependence, 'multispectralportC.dll'))
        self.comName = ctypes.c_char_p(b"COM5")
        self.handle = ctypes.c_void_p()
        self.LED_command = {
            'CWF_1000Lx': 0,
            'CWF_100Lx': 1,
            'CWF_20Lx': 2,
            'D50_1000Lx': 3,
            'D50_100Lx': 4,
            'D50_20Lx': 5,
            'H_100Lx': 6,
            'H_20Lx': 7
        }

    def connect(self):
        state1 = self.LED_api.InitAndConnect(self.comName, ctypes.byref(self.handle))
        state2 = self.LED_api.getConnectState(ctypes.byref(self.handle))

        if state1 == 19 and state2 == 0:
            print('[Online] LED Light Device')
        else:
            print('[Offline] LED Light Device')

    def open(self, light):
        elec_get = ctypes.c_int * 32
        c_ni = elec_get()
        try:
            self.LED_command[light]
        except KeyError as e:
            print(f'[Error] Fail LED Light: {light}')
            exit(0)
        state = self.LED_api.OpenLightGroup(ctypes.byref(self.handle), ctypes.c_int(self.LED_command[light]), c_ni)
        if state == 19:
            print(f'[Done] Open LED Light: {light}')
        else:
            print(f'[Error] Fail LED Light: {light}')
            exit(0)

    def close(self):
        state = self.LED_api.controlSetLevel(ctypes.byref(self.handle),
                                (ctypes.c_int * 32)(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                                    0, 0, 0, 0, 0, 0), ctypes.c_int(32))
        if state == 19:
            print('[Done] Close LED Light')
        else:
            print('[Error] Fail to close LED Light')
            exit(0)

    def disconnect(self):
        state = self.LED_api.Disconnect(ctypes.byref(self.handle))
        if state == 0:
            print('[Done] Disconnect LED Light Device')


def led_operation():
    led = LED_Light()
    led.connect()
    led.open('D50_1000Lx')
    time.sleep(5)
    led.close()
    led.disconnect()
    time.sleep(2)


class LEDLightProcess(multiprocessing.Process):
    """
    LED灯控制进程类，继承自multiprocessing.Process
    可以作为独立进程运行，通过命令队列控制灯光
    """

    Lights = ['CWF_1000Lx', 'CWF_100Lx', 'CWF_20Lx',
              'D50_1000Lx', 'D50_100Lx', 'D50_20Lx',
              'H_100Lx', 'H_20Lx']

    def __init__(self):
        super().__init__()
        # 创建命令队列和结果队列
        self.cmd_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        self.running = multiprocessing.Value('b', True)

    def run(self):
        try:
            self._init_led()

            # 主循环，处理命令
            while self.running.value:
                try:
                    cmd, args = self.cmd_queue.get(timeout=0.5)

                    if cmd == 'connect':
                        result = self._connect()
                    elif cmd == 'open':
                        light_type = args.get('light_type', 'D50_1000Lx')
                        result = self._open(light_type)
                    elif cmd == 'close':
                        result = self._close()
                    elif cmd == 'disconnect':
                        result = self._disconnect()
                    else:
                        result = False

                    self.result_queue.put(result)

                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"[Error] Command processing error: {e}")
                    self.result_queue.put(False)

        except Exception as e:
            print(f"[Error] LED process error: {e}")
        finally:
            print("[Done] LED process terminated")

    def _init_led(self):
        self.LED_dependence = os.path.join(current_folder, 'Dependencies', 'LED')
        self.LED_api = cdll.LoadLibrary(os.path.join(self.LED_dependence, 'multispectralportC.dll'))
        self.comName = ctypes.c_char_p(b"COM5")
        self.handle = ctypes.c_void_p()
        self.LED_command = {
            'CWF_1000Lx': 0,
            'CWF_100Lx': 1,
            'CWF_20Lx': 2,
            'D50_1000Lx': 3,
            'D50_100Lx': 4,
            'D50_20Lx': 5,
            'H_100Lx': 6,
            'H_20Lx': 7
        }

    def _connect(self):
        """连接LED设备"""
        state1 = self.LED_api.InitAndConnect(self.comName, ctypes.byref(self.handle))
        state2 = self.LED_api.getConnectState(ctypes.byref(self.handle))
        if state1 == 19 and state2 == 0:
            print('[Online] LED Light Device')
            return True
        else:
            print('[Offline] LED Light Device')
            return False

    def _open(self, light):
        c_ni = (ctypes.c_int * 32)()
        try:
            self.LED_command[light]
        except KeyError as e:
            print(f'[Error] Fail LED Light: {light}')
            return False

        state = self.LED_api.OpenLightGroup(ctypes.byref(self.handle), ctypes.c_int(self.LED_command[light]), c_ni)
        if state == 19:
            print(f'[Done] Open LED Light: {light}')
            return True
        else:
            print(f'[Error] Fail LED Light: {light}')
            return False

    def _close(self):
        state = self.LED_api.controlSetLevel(ctypes.byref(self.handle),
                                             (ctypes.c_int * 32)(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                                                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                                                 0, 0, 0, 0, 0, 0), ctypes.c_int(32))
        if state == 19:
            print('[Done] Close LED Light')
            return True
        else:
            print('[Error] Fail to close LED Light')
            return False

    def _disconnect(self):
        """断开LED设备连接"""
        state = self.LED_api.Disconnect(ctypes.byref(self.handle))
        if state == 0:
            print('[Done] Disconnect LED Light Device')
            return True
        return False

    # 以下是对外提供的控制接口

    def send_command(self, cmd, **kwargs):
        """发送命令到LED进程"""
        self.cmd_queue.put((cmd, kwargs))
        return self.result_queue.get()  # 等待并返回结果

    def connect(self):
        return self.send_command('connect')

    def open(self, light_type):
        """打开指定类型的灯光"""
        return self.send_command('open', light_type=light_type)

    def close(self):
        """关闭灯光"""
        return self.send_command('close')

    def disconnect(self):
        """断开LED设备连接"""
        return self.send_command('disconnect')


# 使用示例
if __name__ == '__main__':
    # 创建并启动LED控制进程
    led_process = LEDLightProcess()
    led_process.start()
    led_process.connect()
    led_process.close()
    led_process.disconnect()
    led_process.terminate()
    led_process.join()

    # led = LED_Light()
    # led.connect()
    # time.sleep(3)
    # led.open('CWF_100Lx')
    # time.sleep(2)
    # led.open('D50_1000Lx')
    # time.sleep(2)
    # led.close()
