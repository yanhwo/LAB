import serial
import time
import os

current_path = os.path.abspath(__file__)
current_folder = os.path.dirname(current_path)


class DXO_Light(object):
    Lights = ['A_20Lx', 'A_100Lx',
              'D65_100Lx', 'D65_300Lx', 'D65_1000Lx',
              'TL84_20Lx', 'TL84_100Lx', 'TL84_300Lx', 'TL84_1000Lx']

    def __init__(self):
        super().__init__()
        self.DXO_Port = 'COM4'
        self.DXO_serial = serial.Serial(port=self.DXO_Port, baudrate=9600, timeout=1)

        self.DXO_packet = os.path.join(current_folder, 'Dependencies', 'DXO')
        self.DXO_command = {
            'close': os.path.join(self.DXO_packet, 'close.txt'),
            'A_20Lx': os.path.join(self.DXO_packet, 'A_20Lx.txt'),
            'A_100Lx': os.path.join(self.DXO_packet, 'A_100Lx.txt'),
            'D65_100Lx': os.path.join(self.DXO_packet, 'D65_100Lx.txt'),
            'D65_300Lx': os.path.join(self.DXO_packet, 'D65_300Lx.txt'),
            'D65_1000Lx': os.path.join(self.DXO_packet, 'D65_1000Lx.txt'),
            'TL84_20Lx': os.path.join(self.DXO_packet, 'TL84_20Lx.txt'),
            'TL84_100Lx': os.path.join(self.DXO_packet, 'TL84_100Lx.txt'),
            'TL84_300Lx': os.path.join(self.DXO_packet, 'TL84_300Lx.txt'),
            'TL84_1000Lx': os.path.join(self.DXO_packet, 'TL84_1000Lx.txt')
        }

    def connect(self):
        pass

    def open(self, light):
        with open(self.DXO_command[light], 'r') as f:
            lines = f.readlines()
        for line in lines:
            hex_data = bytes.fromhex(line.strip())
            self.DXO_serial.write(hex_data)
        time.sleep(0.8)
        waiting = self.DXO_serial.in_waiting
        response_bytes = self.DXO_serial.readline()
        if response_bytes:  # 若有数据
            response_hex = response_bytes.hex().upper()  # 转为大写十六进制字符串
            print(f"接收: {response_hex}")

        print(f'[Done] Open DXO Light: {light}')

    def close(self):
        with open(self.DXO_command['close'], 'r') as f:
            lines = f.readlines()

        for line in lines:
            hex_data = bytes.fromhex(line.strip())
            self.DXO_serial.write(hex_data)
        print('[Done] Close DXO Light')

    def disconnect(self):
        if self.DXO_serial and self.DXO_serial.is_open:  # 先判断串口是否打开，避免异常
            self.DXO_serial.close()
            self.DXO_serial = None


if __name__ == '__main__':
    # dxo = DXO_Light()
    # dxo.connect()
    # dxo.open('A_20Lx')
    # time.sleep(2)
    # dxo.close()
    # dxo.disconnect()
    #
    # time.sleep(2)

    dxo = DXO_Light()
    dxo.connect()
    dxo.open('A_20Lx')
    # time.sleep(2)
    # dxo.close()
    # dxo.disconnect()
