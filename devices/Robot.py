# -*- coding:utf-8 -*-

import os
import time
import json
import ctypes

from contextlib import contextmanager
from ctypes import *

current_dir = os.path.dirname(os.path.abspath(__file__))
ret = c_uint16(-1)
ip = create_string_buffer(b"192.168.1.200")


if os.name == "nt":
    libc = ctypes.CDLL("msvcrt")
else:
    libc = ctypes.CDLL("libc.so.6")


@contextmanager
def suppress_c_output():
    original_stdout_fd = os.dup(1)
    original_stderr_fd = os.dup(2)

    null_fd = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(null_fd, 1)
        os.dup2(null_fd, 2)
        libc.fflush(None)
        yield
    finally:
        os.dup2(original_stdout_fd, 1)
        os.dup2(original_stderr_fd, 2)
        os.close(null_fd)
        os.close(original_stdout_fd)
        os.close(original_stderr_fd)
        libc.fflush(None)


class Robot_Arm(object):
    origin_point1 = [-90, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 右侧 负 初始位置
    origin_point2 = [0, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 前侧初始位置
    origin_point3 = [90, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 左侧 正 初始位置
    origin_point4 = [180, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 后侧 正 初始位置
    origin_point5 = [-180, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 后侧 负 初始位置
    origin_point6 = [-270, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 左侧 负 初始位置
    origin_point7 = [270, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 右侧 正 初始位置
    origin_point8 = [-359, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 前侧 左负 初始位置
    origin_point9 = [359, -3.273567, -159.556566, -156.693446, -89.951734, -71.828592]  # 前侧 右正 初始位置

    def __init__(self):
        self.Robot_dependence = os.path.join(current_dir, 'Dependencies', 'Robot')
        self.Robot_api = cdll.LoadLibrary(os.path.join(self.Robot_dependence, 'Autocontrol.dll'))
        self.Robot_points = json.load(open(os.path.join(self.Robot_dependence, 'Bot_point_value.json')))

        self.TE42_pos = self.Robot_points['point_te42']
        self.MCC_Holder_pos = self.Robot_points['point_mcc']
        self.MCC_Box_pos = self.Robot_points['point_mcc_lightbox']
        self.to_BOX_mid_pos = self.Robot_points['point_mcc_lightbox_mid']
        self.Plain_pos = self.Robot_points['point_plain']

        self.position_status = None

    def connect(self):
        self.Robot_api.RTClient(ip)
        with suppress_c_output():
            res = self.Robot_api.StartRTClient(byref(ret))
        if res == 1:
            print('[Online] Robot Arm')
        else:
            raise ValueError('[Offline] Robot Arm')

    def get_joint_position(self):
        a = c_float(0)
        b = c_float(0)
        c = c_float(0)
        d = c_float(0)
        e = c_float(0)
        f = c_float(0)

        self.Robot_api.Get_joint_position(ret, byref(a), byref(b), byref(c), byref(d), byref(e), byref(f))
        res = [a.value, b.value, c.value, d.value, e.value, f.value]
        return res

    def set_joint_move(self, args):
        current_pos = self.get_joint_position()
        move = False
        for a, b in zip(args, current_pos):
            if abs(a-b) > 0.01:
                move = True
                break
        if move:
            self.Robot_api.Set_joint_move(ret, c_float(args[0]), c_float(args[1]), c_float(args[2]),
                                          c_float(args[3]), c_float(args[4]), c_float(args[5]),
                                          c_float(30), c_float(30))
        time.sleep(1)
        while self.Robot_api.get_robot_state(ret) == 1:
            print('robot is moving')
            time.sleep(1)

        current_pos = self.get_joint_position()
        in_pos = False
        for a, b in zip(args, current_pos):
            if abs(a-b) > 0.01:
                in_pos = False
            else:
                in_pos = True
        if in_pos:
            print('[Done] ')
        time.sleep(2)

    def check_position_status(self):
        tolerance = 0.001
        current_pos = self.get_joint_position()

        if all(abs(a - b) <= tolerance for a, b in zip(self.TE42_pos, current_pos)):
            self.position_status = 'TE42'
        elif all(abs(a - b) <= tolerance for a, b in zip(self.MCC_Holder_pos, current_pos)):
            self.position_status = 'MCC_Holder'
        elif all(abs(a - b) <= tolerance for a, b in zip(self.MCC_Box_pos, current_pos)):
            self.position_status = 'MCC_Box'
        elif all(abs(a - b) <= tolerance for a, b in zip(self.Plain_pos, current_pos)):
            self.position_status = 'Plain'
        elif all(abs(a - b) <= tolerance for a, b in zip(self.origin_point2, current_pos)):
            self.position_status = 'Origin'
        else:
            self.position_status = 'others'

    def back_to_origin(self):
        current_pos = self.get_joint_position()
        if -45 <= current_pos[0] < 45:  # 回到前方（图卡架侧）初始位置
            self.set_joint_move(self.origin_point2)
        elif -135 <= current_pos[0] < -45:  # 回到灯箱侧（右侧）初始位置
            self.set_joint_move(self.origin_point1)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif -225 <= current_pos[0] < -135:  # 回到后侧初始位置
            self.set_joint_move(self.to_BOX_mid_pos)
            self.set_joint_move(self.origin_point1)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif -315 <= current_pos[0] < -225:
            self.set_joint_move(self.origin_point6)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif -315 <= current_pos[0] < -360:
            self.set_joint_move(self.origin_point8)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif 45 <= current_pos[0] < 135:
            self.set_joint_move(self.origin_point3)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif 135 <= current_pos[0] < 225:
            self.set_joint_move(self.origin_point4)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif 225 <= current_pos[0] < 315:
            self.set_joint_move(self.origin_point7)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)
        elif 315 <= current_pos[0] < 360:
            self.set_joint_move(self.origin_point9)
            time.sleep(2)
            self.set_joint_move(self.origin_point2)

    def move_to_chart(self, target_chart):
        self.check_position_status()

        if target_chart == 'TE42':
            if self.position_status == 'TE42':
                pass
            elif self.position_status == 'MCC_Holder':
                self.set_joint_move(self.TE42_pos)
            elif self.position_status == 'Origin':
                self.set_joint_move(self.TE42_pos)
            else:
                self.back_to_origin()
                self.set_joint_move(self.TE42_pos)

        if target_chart == 'MCC_Holder':
            if self.position_status == 'MCC_Holder':
                pass
            elif self.position_status == 'TE42':
                self.set_joint_move(self.MCC_Holder_pos)
            elif self.position_status == 'Origin':
                self.set_joint_move(self.MCC_Holder_pos)
            else:
                self.back_to_origin()
                self.set_joint_move(self.MCC_Holder_pos)

        if target_chart == 'MCC_Box':
            print(self.position_status)
            if self.position_status == 'MCC_Box':
                pass
            elif self.position_status == 'Plain':
                self.set_joint_move(self.MCC_Box_pos)
            else:
                self.back_to_origin()
                self.set_joint_move(self.to_BOX_mid_pos)
                self.set_joint_move(self.MCC_Box_pos)

        if target_chart == 'Plain':
            if self.position_status == 'Plain':
                pass
            elif self.position_status == 'MCC_Box':
                self.set_joint_move(self.Plain_pos)
            else:
                self.back_to_origin()
                self.set_joint_move(self.to_BOX_mid_pos)
                self.set_joint_move(self.Plain_pos)


if __name__ == '__main__':
    robot_arm = Robot_Arm()
    robot_arm.connect()
    robot_arm.back_to_origin()
    # robot_arm.move_to_chart('Plain')
    # robot_arm.move_to_chart('MCC_Box')
    # robot_arm.move_to_chart('Plain')
    # robot_arm.move_to_chart('TE42')
    # robot_arm.move_to_chart('Plain')

    # robot_arm.move_to_chart('TE42')
    # robot_arm.move_to_chart('MCC_Box')
    # robot_arm.back_to_origin()

