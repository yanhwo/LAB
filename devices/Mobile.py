import subprocess
import time
import os
import shutil
from pathlib import Path

current_path = os.path.abspath(__file__)
current_folder = os.path.dirname(current_path)


class Mobile_Phone(object):
    def __init__(self):
        super().__init__()
        self.Mobile_override = os.path.join(current_folder, 'Dependencies', 'Mobile', 'overridesetting')
        self.jpg = None
        self.raw_folder = None

    @staticmethod
    def connect():
        result = subprocess.run(
            ['adb', 'devices'],
            capture_output=True,
            text=True,
            timeout=5
        )

        lines = result.stdout.strip().split('\n')

        devices = []
        for line in lines[1:]:  # 跳过第一行 "List of devices attached"
            if line.strip() and '\tdevice' in line:
                device_id = line.split('\t')[0]
                devices.append(device_id)
        if devices:
            for device in devices:
                print(f"[Online] Mobile Phone({device})")
            return True
        else:
            print("[Offline] Mobile Phone")
            return False

    @staticmethod
    def adbCommand(adb_command):
        # 执行命令
        process = subprocess.Popen(adb_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # 捕获输出和错误
        stdout, stderr = process.communicate()
        # 打印输出
        res_data = {'stdout': stdout.decode(), 'stderr': stderr.decode()}
        # 中止命令
        # process.terminate()
        # print(res_data)
        return res_data

    def clearCameraData(self):
        try:
            self.adbCommand('adb shell "cd /data/vendor/camera; ls | xargs -n 200 rm -fr"')
        except Exception as e:
            print(f"camera data clear error: {str(e)}")
        self.adbCommand(
            f"adb shell rm -rf /sdcard/DCIM/Camera/* && adb shell rm -rf /data/vendor/cameraDataDump/* && adb shell rm"
            f" -rf /data/vendor/camera/* && adb shell rm -rf /sdcard/Movies/*")

    def pushBin(self, bin_path):
        path = Path(bin_path)
        if not path.is_file():
            raise FileNotFoundError(f"file not exist: {bin_path}")

        if path.suffix.lower() != ".bin":
            raise ValueError(f"not bin file : {bin_path}")

        self.adbCommand('adb wait-for-device')
        self.adbCommand(f'adb root')
        self.adbCommand('adb wait-for-device')
        self.adbCommand(f'adb remount')

        self.adbCommand(f'adb push {bin_path} vendor/lib64/camera')

        self.adbCommand(f'adb shell stop vendor.camera-provider')
        self.adbCommand(f'adb shell stop cameraserver')
        self.adbCommand(f'adb shell start cameraserver')
        self.adbCommand(f'adb shell start vendor.camera-provider')
        
        self.adbCommand('timeout /T 1')
        print(f"[Done] Push bin: {bin_path}")
        return True

    def push_settings(self, mode):
        setting_path = os.path.join(self.Mobile_override, mode.upper(), 'camxoverridesettings.txt')
        if os.path.exists(setting_path):
            pass
        else:
            raise ValueError(f"No found overridesetting: {setting_path}")
        self.adbCommand('adb root')
        self.adbCommand('adb remount')
        self.adbCommand(f'adb push {setting_path} vendor/etc/camera')
        time.sleep(1)
        self.adbCommand('adb reboot')

        if not self.wait_for_phone_boot(max_wait_sec=120, interval_sec=5):
            # 检测失败，打印错误并退出
            print("********** ERROR：手机未在限定时间内启动，请检查设备是否正常。 **********")
        else:
            print("Restart Finish")

    @staticmethod
    def run_cmd(cmd, timeout=5):
        """封装一下 adb 命令调用"""
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode

    def wait_for_phone_boot(self, max_wait_sec=120, interval_sec=5):
        """等待手机正常启动，成功返回 True，超时返回 False"""
        print(f"开始检测手机启动状态，最长等待 {max_wait_sec} 秒...")

        start = time.time()
        while time.time() - start < max_wait_sec:
            # 看 adb 设备是否在线
            out, err, code = self.run_cmd(["adb", "get-state"])
            if code != 0 or out != "device":
                print("设备未在线或未连接，继续等待...")
                time.sleep(interval_sec)
                continue

            # 看 Android 是否 boot completed
            out, err, code = self.run_cmd(["adb", "shell", "getprop", "sys.boot_completed"])
            if out.strip() == "1":
                print("检测到手机已正常启动 ✅")
                return True
            print("系统尚未完成启动，请等待......")
            time.sleep(interval_sec)
        # 超时
        print("❌ 设备连接超时，请检查后重试！")
        return False
    
    def take_photo(self, bin_file=None):
        if bin_file:
            self.pushBin(bin_file)

        self.clearCameraData()

        res_data1 = self.adbCommand(f'adb shell dumpsys display | findstr "mScreenState"')
        screen_on = False
        if 'ON' in res_data1["stdout"]:
            screen_on = True
        else:
            if 'OFF' in res_data1["stdout"]:
                self.adbCommand(f'adb shell input keyevent 26')
                time.sleep(1)
                self.adbCommand(f'adb shell input keyevent 82')
                time.sleep(1)
                screen_on = True
        if screen_on:
            time.sleep(2)
            self.adbCommand(f'adb wait-for-device root')
            self.adbCommand(f'adb wait-for-device remount')
            self.adbCommand(f'adb shell input keyevent 82')
            time.sleep(1)
            self.adbCommand(f'adb shell am start -n org.codeaurora.snapcam/com.android.camera.CameraLauncher'
                            f' --activity-single-top --activity-clear-task')
            time.sleep(5)
            self.adbCommand(f'adb shell input keyevent 27')
            print('[Done] Take Photo')
            # time.sleep(2)
            # self.adbCommand(f"adb wait-for-device shell input tap 712 3017")
            time.sleep(5)

            self.adbCommand(f'adb shell input keyevent 4')
            time.sleep(1)
            self.adbCommand(f'adb shell input keyevent 26')
            time.sleep(1)
            return True
        else:
            return False

    def dump_jpg(self, path):
        if not os.path.exists(path):
            raise ValueError(f"[Error] Invalid path: {path}")

        self.adbCommand(f"adb shell ls /sdcard/DCIM/camera")
        self.adbCommand(f"adb pull /sdcard/DCIM/camera/. {path}")

        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            if os.path.isfile(file_path):
                _, extension = os.path.splitext(filename)
                if extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                    self.jpg = file_path
                    break
                else:
                    self.jpg = None

        print('[Done] Dump JPG')

    def dump_raw(self, path):
        if not os.path.exists(path):
            pass
        else:
            shutil.rmtree(path)
        os.makedirs(path)

        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)

            # try:
            #     if os.path.isfile(file_path) or os.path.islink(file_path):
            #         os.unlink(file_path)
            #     elif os.path.isdir(file_path):
            #         shutil.rmtree(file_path)
            # except Exception as e:
            #     print(f"[Warning] Fail to delete {file_path}: {e}")

        self.adbCommand(f"adb shell ls /data/vendor/camera")
        self.adbCommand(f"adb pull /data/vendor/camera/. {path}")

        self.adbCommand(f"adb shell ls /sdcard/DCIM/camera")
        self.adbCommand(f"adb pull /sdcard/DCIM/camera/. {path}")

        self.raw_folder = path
        print('[Done] Dump Raw')


if __name__ == '__main__':
    phone = Mobile_Phone()
    # phone.push_settings('b2y')
    phone.take_photo()
    phone.dump_jpg(r'C:\Public\Auto_test')
    # phone.dump_raw(r'\\10.231.203.160\Auto_test\capturebin\presets\preset_1\raw')
