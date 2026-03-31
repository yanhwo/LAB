import os
import subprocess


class QCAT(object):
    def __init__(self):
        qcat_address = r'C:\workspace\QCATS_v1.4.0'

        self.work_env = qcat_address
        self.qcat_exe = os.path.join(self.work_env, 'QCATS_v1.exe')

    @staticmethod
    def del_roi_xml(directory, file_extension):
        for dirpath, _, filenames in os.walk(directory):
            for file in filenames:
                if file.lower().endswith(file_extension.lower()):
                    file_path = os.path.join(dirpath, file)
                    os.remove(file_path)

    def process_single(self, term, image_path, light, cct):
        if term == "MCC":
            subprocess.check_call(fr'{self.qcat_exe} "MCC" "{image_path}" {light} {cct} "Photo"',
                                  shell=True, cwd=self.work_env)
        if term == "TE42":
            subprocess.check_call(fr'{self.qcat_exe} "TE42" "{image_path}" "0" "all" {light} {cct} "Photo"',
                                  shell=True, cwd=self.work_env)
            # Tone, Resolution, Sharpness & Noise
        if term == "LS":
            subprocess.check_call(fr'{self.qcat_exe} "LS" "{image_path}" {light} {cct} "Photo"',
                                  shell=True, cwd=self.work_env)

    def process_multiple(self, term, full_path, output):
        self.del_roi_xml(full_path, ".xml")
        self.del_roi_xml(full_path, ".mat")
        if term == "All":
            subprocess.check_call(fr'{self.qcat_exe} "ALL" "{full_path}" "{output}" "PDF" "Photo"',
                                  shell=True, cwd=self.work_env)
        if term == "MCC":
            subprocess.check_call(fr'{self.qcat_exe} "MCC" "{full_path}" "{output}" "PDF" "Photo"',
                                  shell=True, cwd=self.work_env)
        if term == "TE42":
            subprocess.check_call(fr'{self.qcat_exe} "TE42" "{full_path}" "{output}" "PDF" "Photo"',
                                  shell=True, cwd=self.work_env)
        if term == "LS":
            subprocess.check_call(fr'{self.qcat_exe} "LS" "{full_path}" "{output}" "PDF" "Photo"',
                                  shell=True, cwd=self.work_env)


if __name__ == "__main__":
    qcat = QCAT()
    qcat.process_multiple('TE42', r'C:\workspace\share_all\yanhao\IQ_TE42_1024\TE42_clone',
                          r'C:\workspace\share_all\yanhao\IQ_TE42_1024\TE42_clone')
