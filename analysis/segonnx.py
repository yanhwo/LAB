import numpy as np
import argparse
from onnxruntime import InferenceSession as InferenceSession
import time
import cv2
import math
import os
import sys

if getattr(sys, 'frozen', False):
    current_path = os.path.realpath(sys.executable)
else:
    current_path = os.path.realpath(__file__)
current_dir = os.path.dirname(current_path)
# print(current_dir)

class_names = ['MCC']
# Create a list of colors for each class where each color is a tuple of 3 integer values
rng = np.random.default_rng(3)
colors = rng.uniform(0, 255, size=(len(class_names), 3))

def resize_with_padding(image, target_size):
    h, w = image.shape[:2]
    scale = target_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized_image = cv2.resize(image, (new_w, new_h))

    delta_w = target_size - new_w
    delta_h = target_size - new_h
    top, bottom = delta_h // 2, delta_h - (delta_h // 2)
    left, right = delta_w // 2, delta_w - (delta_w // 2)

    color = [0, 0, 0]
    padded_image = cv2.copyMakeBorder(resized_image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    return padded_image, (new_w, new_h), (top, bottom, left, right)

def remove_padding_and_resize(mask, new_size, padding, original_size):
    new_w, new_h = new_size
    top, bottom, left, right = padding

    # Remove padding
    mask = mask[top:top+new_h, left:left+new_w]

    # Resize to original size
    original_h, original_w = original_size
    resized_mask = cv2.resize(mask, (original_w, original_h))

    return resized_mask

def nms(boxes, scores, iou_threshold):
    # Sort by score
    sorted_indices = np.argsort(scores)[::-1]

    keep_boxes = []
    while sorted_indices.size > 0:
        # Pick the last box
        box_id = sorted_indices[0]
        keep_boxes.append(box_id)

        # Compute IoU of the picked box with the rest
        ious = compute_iou(boxes[box_id, :], boxes[sorted_indices[1:], :])

        # Remove boxes with IoU over the threshold
        keep_indices = np.where(ious < iou_threshold)[0]

        # print(keep_indices.shape, sorted_indices.shape)
        sorted_indices = sorted_indices[keep_indices + 1]

    return keep_boxes

def compute_iou(box, boxes):
    # Compute xmin, ymin, xmax, ymax for both boxes
    xmin = np.maximum(box[0], boxes[:, 0])
    ymin = np.maximum(box[1], boxes[:, 1])
    xmax = np.minimum(box[2], boxes[:, 2])
    ymax = np.minimum(box[3], boxes[:, 3])

    # Compute intersection area
    intersection_area = np.maximum(0, xmax - xmin) * np.maximum(0, ymax - ymin)

    # Compute union area
    box_area = (box[2] - box[0]) * (box[3] - box[1])
    boxes_area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union_area = box_area + boxes_area - intersection_area

    # Compute IoU
    iou = intersection_area / union_area

    return iou

def xywh2xyxy(x):
    # Convert bounding box (x, y, w, h) to bounding box (x1, y1, x2, y2)
    y = np.copy(x)
    y[..., 0] = x[..., 0] - x[..., 2] / 2
    y[..., 1] = x[..., 1] - x[..., 3] / 2
    y[..., 2] = x[..., 0] + x[..., 2] / 2
    y[..., 3] = x[..., 1] + x[..., 3] / 2
    return y

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def draw_detections(image, boxes, scores, class_ids, mask_alpha=0.3, mask_maps=None):
    img_height, img_width = image.shape[:2]
    size = min([img_height, img_width]) * 0.0006
    text_thickness = int(min([img_height, img_width]) * 0.001)

    mask_img = draw_masks(image, boxes, class_ids, mask_alpha, mask_maps)

    # Draw bounding boxes and labels of detections
    for box, score, class_id in zip(boxes, scores, class_ids):
        color = colors[class_id]

        x1, y1, x2, y2 = box.astype(int)

        # Draw rectangle
        cv2.rectangle(mask_img, (x1, y1), (x2, y2), color, 2)

        label = class_names[class_id]
        caption = f'{label} {int(score * 100)}%'
        (tw, th), _ = cv2.getTextSize(text=caption, fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                                      fontScale=size, thickness=text_thickness)
        th = int(th * 1.2)

        cv2.rectangle(mask_img, (x1, y1),
                      (x1 + tw, y1 - th), color, -1)

        cv2.putText(mask_img, caption, (x1, y1),
                    cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), text_thickness, cv2.LINE_AA)
        
    # cv2.namedWindow("Output", cv2.WINDOW_NORMAL)
    # cv2.imshow("Output", mask_img)
    # cv2.waitKey(0)

    mmc_masks(image, boxes, class_ids, mask_alpha, mask_maps)

    return mask_img

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect

def mmc_detect(image, boxes, class_ids, mask_alpha=0.3, mask_maps=None):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mask_img = image.copy()
    # Draw bounding boxes and labels of detections
    for i, (box, class_id) in enumerate(zip(boxes, class_ids)):
        color = colors[class_id]
        x1, y1, x2, y2 = box.astype(int)
        # Get masks
        if mask_maps is None:
            return -1
        else:
            crop_mask = mask_maps[i][y1:y2, x1:x2, np.newaxis]
            crop_img = image[y1:y2, x1:x2, :]

            if False:
                # Display the original image and the segmented mask together
                color_mask = np.zeros_like(image)
                color_mask[mask_maps[i] > 0.5] = [0, 0, 255]  # Red color

                # Blend the color mask with the original image
                blended_image = cv2.addWeighted(image, 1, color_mask, 0.5, 0)

                # Resize the blended image to a smaller size for display
                display_image = cv2.resize(blended_image, (blended_image.shape[1] // 2, blended_image.shape[0] // 2))

                # Display the resized blended image
                # cv2.imshow("Image with Mask", display_image)
                # cv2.waitKey(0)
                # cv2.destroyAllWindows()

            # Apply Gaussian Blur to reduce noise
            blurred_mask = cv2.GaussianBlur(mask_maps[i], (5, 5), 0)
            
            # Apply morphological operations
            kernel = np.ones((5, 5), np.uint8)
            morph_mask = cv2.morphologyEx(blurred_mask, cv2.MORPH_CLOSE, kernel)

            contours, _hierarchy = cv2.findContours(
                morph_mask.astype(np.uint8), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )    

            # Find connected components
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(morph_mask.astype(np.uint8), connectivity=8)
            
            # Find the largest connected component (excluding the background)
            largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            
            # Create a mask for the largest connected component
            largest_component_mask = np.zeros_like(morph_mask)
            largest_component_mask[labels == largest_label] = 255

            # Find contours on the largest connected component mask
            contours, _hierarchy = cv2.findContours(
                largest_component_mask.astype(np.uint8), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )

            # contours, _hierarchy = cv2.findContours(
            #     mask_maps[i].astype(np.uint8), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            # )
            for contour in contours:
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                # Check if the approximated contour has 4 vertices

                if True:
                    cv2.polylines(mask_maps[i], [approx], True, (0, 0, 255), 2)
                    # cv2.imshow('Segmented Mask with Contours and Rectangles', mask_maps[i])
                    # cv2.waitKey(0)
                    # cv2.destroyAllWindows()

                # print(f"length of the vertices is {approx}")
                if len(approx) == 4:
                    # print("approx has 4 vertices")
                    working_height = 1008
                    working_width = 1440
                    src_pts = approx.reshape(4, 2).astype(np.float32)
                    src_pts = order_points(src_pts)
                    dst_pts = np.array([[0, 0], [working_width-1, 0], [working_width-1, working_height-1], [0, working_height-1]], dtype=np.float32)
                    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
                    # Apply the perspective warp
                    warped_raw = cv2.warpPerspective(image, M, (working_width, working_height))
                    samples_half = max(32 / 2, 1)
                    masks = []
                    offset_h = working_width / 6 / 2
                    offset_v = working_height / 4 / 2
                    for j in np.linspace(offset_v, working_height - offset_v, 4):
                        for i in np.linspace(offset_h, working_width - offset_h, 6):
                            masks.append(
                                    [
                                        j - samples_half,
                                        j + samples_half,
                                        i - samples_half,
                                        i + samples_half,
                                    ]
                            )
                    imgout = warped_raw[:,:,:3].astype(np.uint8)

                    return imgout, masks
                return -1
                
def mmc_masks(image, boxes, class_ids, mask_alpha=0.3, mask_maps=None):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mask_img = image.copy()

    # Draw bounding boxes and labels of detections
    for i, (box, class_id) in enumerate(zip(boxes, class_ids)):
        color = colors[class_id]

        x1, y1, x2, y2 = box.astype(int)

        # Draw fill mask image
        if mask_maps is None:
            cv2.rectangle(mask_img, (x1, y1), (x2, y2), color, -1)
        else:
            crop_mask = mask_maps[i][y1:y2, x1:x2, np.newaxis]
            crop_img = image[y1:y2, x1:x2, :]

            contours, _hierarchy = cv2.findContours(
                mask_maps[i].astype(np.uint8), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Check if the approximated contour has 4 vertices
                if len(approx) == 4:
                    
                    # print("approx has 4 vertices")
                    cv2.drawContours(image, [approx], -1, (0, 255, 0), 3)
                    # plt.figure(figsize=(10, 5))
                    # plt.imshow(image)
                    # plt.show()
                    working_height = 1008
                    working_width = 1440
                    src_pts = approx.reshape(4, 2).astype(np.float32)
                    src_pts = order_points(src_pts)
                    # print(src_pts)
                    if src_pts[0][0] > src_pts[1][0]:
                        dst_pts = []
                        dst_pts = np.array([[working_width, 0], [0, 0], [0, working_height], [working_width, working_height]], dtype=np.float32)
                    else:
                        dst_pts = np.array([[0, 0], [0, working_height], [working_width, working_height], [working_width, 0]], dtype=np.float32)

                    dst_pts = np.array([[0, 0], [working_width-1, 0], [working_width-1, working_height-1], [0, working_height-1]], dtype=np.float32)

                    M = cv2.getPerspectiveTransform(src_pts, dst_pts)

                    # Apply the perspective warp
                    warped_raw = cv2.warpPerspective(image, M, (working_width, working_height))

                    # Display the original and warped images
                    # plt.figure(figsize=(10, 5))
                    # plt.subplot(1, 2, 1)
                    # plt.title('Original Image')
                    # plt.imshow(crop_img[:,:,:3].astype(np.uint8))
                    # plt.subplot(1, 2, 2)
                    # plt.title('Warped Image')
                    # plt.imshow(warped_raw.astype(np.uint8))
                    # plt.show()

                    samples_half = max(32 / 2, 1)

                    masks = []
                    offset_h = working_width / 6 / 2
                    offset_v = working_height / 4 / 2
                    for j in np.linspace(offset_v, working_height - offset_v, 4):
                        for i in np.linspace(offset_h, working_width - offset_h, 6):
                            masks.append(
                                    [
                                        j - samples_half,
                                        j + samples_half,
                                        i - samples_half,
                                        i + samples_half,
                                    ]
                            )

                    imgout = warped_raw[:,:,:3].astype(np.uint8)

                    for rect in masks:
                        y1, y2, x1, x2 = map(int, rect)
                        cv2.rectangle(imgout, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # Display the image with rectangles
                    # plt.figure(figsize=(10, 10))
                    # plt.title('Image with Rectangles')
                    # plt.imshow(imgout)
                    # plt.show()

def draw_masks(image, boxes, class_ids, mask_alpha=0.3, mask_maps=None):
    mask_img = image.copy()

    # Draw bounding boxes and labels of detections
    for i, (box, class_id) in enumerate(zip(boxes, class_ids)):
        color = colors[class_id]

        x1, y1, x2, y2 = box.astype(int)

        # Draw fill mask image
        if mask_maps is None:
            cv2.rectangle(mask_img, (x1, y1), (x2, y2), color, -1)
        else:
            crop_mask = mask_maps[i][y1:y2, x1:x2, np.newaxis]
            crop_mask_img = mask_img[y1:y2, x1:x2]
            crop_mask_img = crop_mask_img * (1 - crop_mask) + crop_mask * color
            mask_img[y1:y2, x1:x2] = crop_mask_img

    return cv2.addWeighted(mask_img, mask_alpha, image, 1 - mask_alpha, 0)

def draw_comparison(img1, img2, name1, name2, fontsize=2.6, text_thickness=3):
    (tw, th), _ = cv2.getTextSize(text=name1, fontFace=cv2.FONT_HERSHEY_DUPLEX,
                                  fontScale=fontsize, thickness=text_thickness)
    x1 = img1.shape[1] // 3
    y1 = th
    offset = th // 5
    cv2.rectangle(img1, (x1 - offset * 2, y1 + offset),
                  (x1 + tw + offset * 2, y1 - th - offset), (0, 115, 255), -1)
    cv2.putText(img1, name1,
                (x1, y1),
                cv2.FONT_HERSHEY_DUPLEX, fontsize,
                (255, 255, 255), text_thickness)

    (tw, th), _ = cv2.getTextSize(text=name2, fontFace=cv2.FONT_HERSHEY_DUPLEX,
                                  fontScale=fontsize, thickness=text_thickness)
    x1 = img2.shape[1] // 3
    y1 = th
    offset = th // 5
    cv2.rectangle(img2, (x1 - offset * 2, y1 + offset),
                  (x1 + tw + offset * 2, y1 - th - offset), (94, 23, 235), -1)

    cv2.putText(img2, name2,
                (x1, y1),
                cv2.FONT_HERSHEY_DUPLEX, fontsize,
                (255, 255, 255), text_thickness)

    combined_img = cv2.hconcat([img1, img2])
    if combined_img.shape[1] > 3840:
        combined_img = cv2.resize(combined_img, (3840, 2160))

    return combined_img

class YOLOSeg:

    def __init__(self, path, conf_thres=0.7, iou_thres=0.5, num_masks=32):
        self.conf_threshold = conf_thres
        self.iou_threshold = iou_thres
        self.num_masks = num_masks

        # Initialize model
        self.initialize_model(path)

    def __call__(self, image):
        return self.segment_objects(image)

    def initialize_model(self, path):
        self.session = InferenceSession(path,
                                                    providers=['CUDAExecutionProvider',
                                                               'CPUExecutionProvider'])
        # Get model info
        self.get_input_details()
        self.get_output_details()

    def segment_objects(self, image):
        input_tensor = self.prepare_input(image)

        # Perform inference on the image
        outputs = self.inference(input_tensor)

        self.boxes, self.scores, self.class_ids, mask_pred = self.process_box_output(outputs[0])
        self.mask_maps = self.process_mask_output(mask_pred, outputs[1])

        return self.boxes, self.scores, self.class_ids, self.mask_maps

    def prepare_input(self, image):
        self.img_height, self.img_width = image.shape[:2]

        input_img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Resize input image
        input_img = cv2.resize(input_img, (self.input_width, self.input_height))

        # Scale input pixel values to 0 to 1
        input_img = input_img / 255.0
        input_img = input_img.transpose(2, 0, 1)
        input_tensor = input_img[np.newaxis, :, :, :].astype(np.float32)

        return input_tensor

    def inference(self, input_tensor):
        start = time.perf_counter()
        outputs = self.session.run(self.output_names, {self.input_names[0]: input_tensor})

        # print(f"Inference time: {(time.perf_counter() - start)*1000:.2f} ms")
        return outputs

    def process_box_output(self, box_output):

        predictions = np.squeeze(box_output).T
        num_classes = box_output.shape[1] - self.num_masks - 4

        # Filter out object confidence scores below threshold
        scores = np.max(predictions[:, 4:4+num_classes], axis=1)
        predictions = predictions[scores > self.conf_threshold, :]
        scores = scores[scores > self.conf_threshold]

        if len(scores) == 0:
            return [], [], [], np.array([])

        box_predictions = predictions[..., :num_classes+4]
        mask_predictions = predictions[..., num_classes+4:]

        # Get the class with the highest confidence
        class_ids = np.argmax(box_predictions[:, 4:], axis=1)

        # Get bounding boxes for each object
        boxes = self.extract_boxes(box_predictions)

        # Apply non-maxima suppression to suppress weak, overlapping bounding boxes
        indices = nms(boxes, scores, self.iou_threshold)

        return boxes[indices], scores[indices], class_ids[indices], mask_predictions[indices]

    def process_mask_output(self, mask_predictions, mask_output):

        if mask_predictions.shape[0] == 0:
            return []

        mask_output = np.squeeze(mask_output)

        # Calculate the mask maps for each box
        num_mask, mask_height, mask_width = mask_output.shape  # CHW
        masks = sigmoid(mask_predictions @ mask_output.reshape((num_mask, -1)))
        masks = masks.reshape((-1, mask_height, mask_width))

        # Downscale the boxes to match the mask size
        scale_boxes = self.rescale_boxes(self.boxes,
                                   (self.img_height, self.img_width),
                                   (mask_height, mask_width))

        # For every box/mask pair, get the mask map
        mask_maps = np.zeros((len(scale_boxes), self.img_height, self.img_width))
        blur_size = (int(self.img_width / mask_width), int(self.img_height / mask_height))
        for i in range(len(scale_boxes)):

            scale_x1 = int(math.floor(scale_boxes[i][0]))
            scale_y1 = int(math.floor(scale_boxes[i][1]))
            scale_x2 = int(math.ceil(scale_boxes[i][2]))
            scale_y2 = int(math.ceil(scale_boxes[i][3]))

            x1 = int(math.floor(self.boxes[i][0]))
            y1 = int(math.floor(self.boxes[i][1]))
            x2 = int(math.ceil(self.boxes[i][2]))
            y2 = int(math.ceil(self.boxes[i][3]))

            scale_crop_mask = masks[i][scale_y1:scale_y2, scale_x1:scale_x2]
            crop_mask = cv2.resize(scale_crop_mask,
                              (x2 - x1, y2 - y1),
                              interpolation=cv2.INTER_CUBIC)

            crop_mask = cv2.blur(crop_mask, blur_size)

            crop_mask = (crop_mask > 0.5).astype(np.uint8)
            mask_maps[i, y1:y2, x1:x2] = crop_mask

        return mask_maps

    def extract_boxes(self, box_predictions):
        # Extract boxes from predictions
        boxes = box_predictions[:, :4]

        # Scale boxes to original image dimensions
        boxes = self.rescale_boxes(boxes,
                                   (self.input_height, self.input_width),
                                   (self.img_height, self.img_width))

        # Convert boxes to xyxy format
        boxes = xywh2xyxy(boxes)

        # Check the boxes are within the image
        boxes[:, 0] = np.clip(boxes[:, 0], 0, self.img_width)
        boxes[:, 1] = np.clip(boxes[:, 1], 0, self.img_height)
        boxes[:, 2] = np.clip(boxes[:, 2], 0, self.img_width)
        boxes[:, 3] = np.clip(boxes[:, 3], 0, self.img_height)

        return boxes

    def draw_detections(self, image, draw_scores=True, mask_alpha=0.4):
        return draw_detections(image, self.boxes, self.scores,
                               self.class_ids, mask_alpha)

    def draw_masks(self, image, draw_scores=True, mask_alpha=0.5):
        return draw_detections(image, self.boxes, self.scores,
                               self.class_ids, mask_alpha, mask_maps=self.mask_maps)

    def ccm_masks(self, image, draw_scores=True, mask_alpha=0.5):
        return mmc_detect(image, self.boxes, self.class_ids, mask_alpha, self.mask_maps)

    def get_input_details(self):
        model_inputs = self.session.get_inputs()
        self.input_names = [model_inputs[i].name for i in range(len(model_inputs))]

        self.input_shape = model_inputs[0].shape
        self.input_height = self.input_shape[2]
        self.input_width = self.input_shape[3]

    def get_output_details(self):
        model_outputs = self.session.get_outputs()
        self.output_names = [model_outputs[i].name for i in range(len(model_outputs))]

    @staticmethod
    def rescale_boxes(boxes, input_shape, image_shape):
        # Rescale boxes to original image dimensions
        input_shape = np.array([input_shape[1], input_shape[0], input_shape[1], input_shape[0]])
        boxes = np.divide(boxes, input_shape, dtype=np.float32)
        boxes *= np.array([image_shape[1], image_shape[0], image_shape[1], image_shape[0]])

        return boxes
    
def main(image_path, rotate):
    # onnx model
    onnx_model_path = os.path.join(current_dir, "best.onnx")

    image = cv2.imread(image_path)

    if rotate == 'CLOCKWISE':
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif rotate == 'COUNTERCLOCKWISE':
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

    target_size = 640
    padded_image, new_size, padding = resize_with_padding(image, target_size)

    yoloseg = YOLOSeg(onnx_model_path, conf_thres=0.3, iou_thres=0.5)
    yoloseg(padded_image)
    res = yoloseg.ccm_masks(padded_image)

    if len(res) == 2:
        img = res[0]
        mask = res[1]
        mask = np.array(mask).astype(np.int32)
        image_dir = os.path.dirname(image_path)
        image_basename = os.path.basename(image_path).split('.')[0]

        image_segname = image_basename + '_seg.jpg'
        image_seg_dir = os.path.join(image_dir, image_segname)
        bgr_img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(image_seg_dir), bgr_img)

        mask_segname = image_basename + '_mask.txt'
        image_seg_dir = os.path.join(image_dir, mask_segname)
        np.savetxt(str(image_seg_dir), mask, fmt='%d')

        # import matplotlib.pyplot as plt
        # plt.figure()
        # plt.subplot(1, 2, 1)
        # plt.imshow(image)
        # plt.subplot(1, 2, 2)
        # plt.imshow(img)
        # plt.show()
        print('[Done] Succeed to segment')

        return img, mask
    else:
        print('[Error] Failed to segment')
        return res

def _scanfilesPattens(path, pattens):
    rtn = []
    for (root, dirs, files) in os.walk(path):
        for file in files:
            if True in [file.endswith(x) for x in pattens]:
                rtn.append(os.path.join(root, file))
    return rtn

def setup_args():
    parser = argparse.ArgumentParser(description='24ColorChecker Seg')
    parser.add_argument('-path', '--path',
                        action='store',
                        default='',
                        dest='path',
                        help='img path')
    parser.add_argument('-rotate', '--rotate',
                        action='store',
                        default='',
                        dest='rotate',
                        help='img rotate bool')
    return parser


if __name__ == "__main__":
    parser = setup_args()
    args = parser.parse_args()
    print('rotate: ', args.rotate)
    if not args.path:
        print('missing arguments. -path', file=sys.stderr)
        sys.exit(1)
    elif not os.path.isfile(args.path):
        print(f'{args.path} is not a file', file=sys.stderr)
        sys.exit(1)
    else:
        main(args.path, args.rotate)


