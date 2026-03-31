import os
import sys
import cv2
from onnxruntime import InferenceSession

if getattr(sys, 'frozen', False):
    current_path = os.path.realpath(sys.executable)
else:
    current_path = os.path.realpath(__file__)
current_dir = os.path.dirname(current_path)


class MCCSeg(object):
    def __init__(self, path, conf_thr=0.7, iou_thr=0.5, num_masks=32):
        self.conf_threshold = conf_thr
        self.iou_threshold = iou_thr
        self.num_masks = num_masks

        # Initialize Model
        self.onnx_model_path = os.path.join(current_dir, "best.onnx")
        self.session = None

        self.input_names = None
        self.input_height = None
        self.input_width = None

        self.output_names = None

        self.initialize_model()

    def initialize_model(self):
        # 1. load model
        self.session = InferenceSession(self.onnx_model_path,
                                        providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])

        # 2. get input details
        model_inputs = self.session.get_inputs()
        self.input_names = [model_inputs[i].name for i in range(len(model_inputs))]
        self.input_height = model_inputs[0].shape[2]
        self.input_width = model_inputs[0].shape[3]

        # 3. get output details
        model_outputs = self.session.get_outputs()
        self.output_names = [model_outputs[i].name for i in range(len(model_outputs))]

    def prepare_image(self, image):
        h, w = image.shape[:2]
        scale = self.input_width / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        resized_image = cv2.resize(image, (new_w, new_h))

        delta_w = self.input_width - new_w
        delta_h = self.input_height - new_h
        top, bottom = delta_h // 2, delta_h - (delta_h // 2)
        left, right = delta_w // 2, delta_w - (delta_w // 2)

        color = [0, 0, 0]
        padded_image = cv2.copyMakeBorder(resized_image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

        return padded_image

    def segment(self, path):
        image = cv2.imread(path)


if __name__ == "__main__":
    mcc_seg = MCCSeg(conf_thr=0.3, iou_thr=0.5)






