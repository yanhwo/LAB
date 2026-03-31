import numpy as np
import cv2
import json
import os
import shutil
import warnings
import math
import matplotlib.pyplot as plt
from scipy.fft import fft2, ifft2, fftshift, ifftshift
from colour import XYZ_to_Luv, CCS_ILLUMINANTS


class TE42(object):
    def __init__(self, path_image, cct=None, light=None):
        self.path_image = path_image
        self.image = cv2.imread(path_image)
        self.image_display = self.image.copy()

        self.height, self.width, _ = self.image.shape
        self.path_data = os.path.join(os.path.dirname(path_image), 'data')
        self.path_txt = os.path.join(self.path_data, 'data.txt')
        self.path_display = os.path.join(self.path_data, 'roi.png')
        self.data_roi = {}
        self.file_roi = os.path.join(self.path_data, 'roi.json')

        if os.path.exists(self.path_data):
            shutil.rmtree(self.path_data)
        os.makedirs(self.path_data, exist_ok=False)

        if cct:
            self.cct = cct
        else:
            self.cct = os.path.basename(os.path.dirname(os.path.dirname(path_image)))

        if light:
            self.light = light
        else:
            self.light = os.path.basename(os.path.dirname(path_image))

        print(f'Process TE42: {self.path_image} {self.cct} {self.light}')

        # siemens star
        self.star_center = (0, 0)
        self.star_out_radius = 0
        self.star_inner_radius = 0

        self.star_roi = None
        self.star_roi_image = None
        self.star_roi_center = (None, None)

        # gray scale
        self.gray_scale_roi = None
        self.gray_scale_value = None

        self.mtf10 = None
        self.vmtf = None
        self.mtf10_score = None
        self.vmtf_score = None
        self.mtf10_result = None
        self.vmtf_result = None
        self.resolution_result = None

        self.contrast = None

        # output
        self.info = {
            'score': {},
            'result': {}
                     }

    def eva_contrast(self):
        self.contrast = Contrast(self.image, self.gray_scale_roi, self.cct, self.light)
        self.contrast.eva_contrast()

        self.info['score']['Global Contrast'] = self.contrast.global_contrast_score
        self.info['result']['Global Contrast'] = self.contrast.global_contrast_result

        self.info['score']['Avg Local Contrast'] = self.contrast.local_contrast_score
        self.info['result']['Avg Local Contrast'] = self.contrast.local_contrast_result

        self.info['score']['Min Local Contrast'] = self.contrast.min_local_contrast_score
        self.info['result']['Min Local Contrast'] = self.contrast.min_local_contrast_result

        self.info['score']['Dark Level'] = self.contrast.black_level_score
        self.info['result']['Dark Level'] = self.contrast.black_level_result

        self.info['score']['Bright Level'] = self.contrast.saturation_score
        self.info['result']['Bright Level'] = self.contrast.saturation_result

    def eva_visual_noise(self):
        vn = VisualNoise(self.image, self.gray_scale_roi, self.cct, self.light)
        vn.eva_visual_noise()

        self.info['score']['VN_Mean'] = vn.vn_mean_score
        self.info['result']['VN_Mean'] = vn.vn_mean_result

        self.info['score']['VN_Max'] = vn.vn_max_score
        self.info['result']['VN_Max'] = vn.vn_max_result

    def eva_resolution(self):
        self.get_gray_value()

        self.star_roi_image = self.image[self.star_roi[0]: self.star_roi[1], self.star_roi[2]: self.star_roi[3]]
        resolution = Resolution(self.star_roi_image, self.star_roi_center, self.star_out_radius, self.star_inner_radius,
                                self.height, self.gray_scale_value, self.cct, self.light, self.height)
        resolution.eva_resolution()

        self.info['score']['MTF10'] = resolution.mtf10_score
        self.info['result']['MTF10'] = resolution.mtf10_result

        self.info['score']['vMTF'] = resolution.vmtf_score
        self.info['result']['vMTF'] = resolution.vmtf_result

    def get_gray_value(self):
        average_gray_value = []
        for i in range(20):
            x1 = self.gray_scale_roi[f'{i + 1}'][0] - self.gray_scale_roi[f'{i + 1}'][2]
            x2 = self.gray_scale_roi[f'{i + 1}'][0] + self.gray_scale_roi[f'{i + 1}'][2]
            y1 = self.gray_scale_roi[f'{i + 1}'][1] - self.gray_scale_roi[f'{i + 1}'][2]
            y2 = self.gray_scale_roi[f'{i + 1}'][1] + self.gray_scale_roi[f'{i + 1}'][2]

            if x2 <= x1 or y2 <= y1:
                # print(f"Warning")
                return None

            roi = self.image[y1:y2, x1:x2]
            yuv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2YUV)
            y_channel = yuv_roi[:, :, 0]
            average_gray_value.append(round(np.mean(y_channel), 1))
        self.gray_scale_value = np.array(average_gray_value)

    @staticmethod
    def get_centroids(point_p, center_c):
        x_p, y_p = point_p
        x_c, y_c = center_c

        x_sym = 2 * x_c - x_p
        y_sym = 2 * y_c - y_p
        symmetric_point = (x_sym, y_sym)

        V_cp_x = x_p - x_c
        V_cp_y = y_p - y_c

        if V_cp_x == 0 and V_cp_y == 0:
            orthogonal_point1 = center_c
            orthogonal_point2 = center_c
            return symmetric_point, orthogonal_point1, orthogonal_point2

        V_rot1_x = -V_cp_y
        V_rot1_y = V_cp_x

        V_rot2_x = V_cp_y
        V_rot2_y = -V_cp_x

        orthogonal_point1 = (x_c + V_rot1_x, y_c + V_rot1_y)
        orthogonal_point2 = (x_c + V_rot2_x, y_c + V_rot2_y)

        return symmetric_point, orthogonal_point1, orthogonal_point2

    @staticmethod
    def get_left_right(lower_rect, center):
        """
        将矩形沿着指定中心点旋转90度，返回顺时针和逆时针旋转后的矩形

        参数:
        rect: 元组 (x1, y1, x2, y2) 表示矩形的左上角和右下角坐标
        center: 元组 (x0, y0) 表示旋转中心点

        返回:
        clockwise_rect: 顺时针旋转90度后的矩形 (x1', y1', x2', y2')
        counterclockwise_rect: 逆时针旋转90度后的矩形 (x1', y1', x2', y2')
        """
        x1, y1, x2, y2 = lower_rect
        x0, y0 = center

        # 计算矩形的四个角点
        corners = [
            (x1, y1),  # 左上
            (x2, y1),  # 右上
            (x2, y2),  # 右下
            (x1, y2)  # 左下
        ]

        # 顺时针旋转90度 (x', y') = (y0 - y + x0, x - x0 + y0)
        clockwise_corners = []
        for x, y in corners:
            # 将点平移到以旋转中心为原点的坐标系
            x_shifted = x - x0
            y_shifted = y - y0

            # 顺时针旋转90度
            x_rotated = y_shifted
            y_rotated = -x_shifted

            # 平移回原来的坐标系
            x_final = x_rotated + x0
            y_final = y_rotated + y0

            clockwise_corners.append((x_final, y_final))

        # 逆时针旋转90度 (x', y') = (x0 - y + y0, x - x0 + y0)
        counterclockwise_corners = []
        for x, y in corners:
            # 将点平移到以旋转中心为原点的坐标系
            x_shifted = x - x0
            y_shifted = y - y0

            # 逆时针旋转90度
            x_rotated = -y_shifted
            y_rotated = x_shifted

            # 平移回原来的坐标系
            x_final = x_rotated + x0
            y_final = y_rotated + y0

            counterclockwise_corners.append((x_final, y_final))

        # 计算旋转后矩形的边界框
        clockwise_x_coords = [p[0] for p in clockwise_corners]
        clockwise_y_coords = [p[1] for p in clockwise_corners]
        clockwise_rect = (
            min(clockwise_x_coords),
            min(clockwise_y_coords),
            max(clockwise_x_coords),
            max(clockwise_y_coords)
        )

        counterclockwise_x_coords = [p[0] for p in counterclockwise_corners]
        counterclockwise_y_coords = [p[1] for p in counterclockwise_corners]
        counterclockwise_rect = (
            min(counterclockwise_x_coords),
            min(counterclockwise_y_coords),
            max(counterclockwise_x_coords),
            max(counterclockwise_y_coords)
        )

        return clockwise_rect, counterclockwise_rect

    def roi_center_siemens_star(self, show=False):
        # 1. get edges
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        most_frequent_value = np.mean(gray)
        if most_frequent_value < 80:
            gray = cv2.equalizeHist(gray)
        most_frequent_value = np.mean(gray)
        thr = most_frequent_value - 30

        _, binary = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY)
        blur = cv2.medianBlur(binary, 3)
        blur = cv2.GaussianBlur(blur, (5, 5), 0)

        kernel_sharpen = np.array([[-1, -1, -1],
                                   [-1, 9, -1],
                                   [-1, -1, -1]])
        sharpened = cv2.filter2D(blur, -1, kernel_sharpen)

        edges = cv2.Canny(sharpened, 60, 150)

        # 2. find contours
        contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 3. get max area contour 1
        max_rect_area = 0
        contour1 = None
        rect1_x, rect1_y, rect1_w, rect1_h = 0, 0, 0, 0

        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            area = w * h
            if area > max_rect_area and 0.75 < w / h < 1.25:
                max_rect_area = area
                contour1 = c
                rect1_x, rect1_y, rect1_w, rect1_h = x, y, w, h

        # 4. get close contour n
        filtered_contours = []
        for c in contours:
            if c is contour1:
                continue

            # Calculate the center point of the contour
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            center_point = (cx, cy)

            # Condition 1: The center point is within the bounding rectangle of contour 1
            center_in_rect1 = (rect1_x <= cx <= rect1_x + rect1_w and
                               rect1_y <= cy <= rect1_y + rect1_h)

            if not center_in_rect1:
                continue

            # Condition 2: The center point is outside the closed shape formed by contour 1
            # Cv2.pointPolygonTest return value:
            # 0: The point is inside the contour
            # =0: Point on contour edge
            # <0: Point outside the contour
            # We need to point externally, so check if the return value is less than 0
            # False means there is no need to calculate distance, only the inside and outside are judged
            distance_to_contour1 = cv2.pointPolygonTest(contour1, center_point, False)

            if distance_to_contour1:
                filtered_contours.append(c)

        # 5. get four crosses
        reference_point_left_upper = (rect1_x, rect1_y)
        reference_point_left_lower = (rect1_x, rect1_y + rect1_h)
        reference_point_right_upper = (rect1_x + rect1_w, rect1_y)
        reference_point_right_lower = (rect1_x + rect1_w, rect1_y + rect1_h)

        distance_left_upper = 0
        distance_left_lower = 0
        distance_right_upper = 0
        distance_right_lower = 0

        point_left_upper = (0, 0)
        point_left_lower = (0, 0)
        point_right_upper = (0, 0)
        point_right_lower = (0, 0)
        rec_left_upper = [0, 0, 0, 0]
        rec_left_lower = [0, 0, 0, 0]
        rec_right_upper = [0, 0, 0, 0]
        rec_right_lower = [0, 0, 0, 0]

        for c in filtered_contours:
            x, y, w, h = cv2.boundingRect(c)
            center_x = x + w / 2
            center_y = y + h / 2
            center_x = int(center_x)
            center_y = int(center_y)
            # cv2.rectangle(self.image_display, (x, y), (x + w, y + h),
            #               (255, 255, 0), 4)
            if w * h > rect1_w + rect1_h and 0.75 < w / h < 1.25:
                if math.sqrt((center_x - reference_point_left_upper[0]) ** 2 + (
                        center_y - reference_point_left_upper[1]) ** 2) > distance_left_upper:
                    distance_left_upper = math.sqrt(
                        (center_x - reference_point_left_upper[0]) ** 2 +
                        (center_y - reference_point_left_upper[1]) ** 2)
                    point_left_upper = (center_x, center_y)
                    rec_left_upper = [x, y, x + w, y + h]

                if math.sqrt((center_x - reference_point_left_lower[0]) ** 2 + (
                        center_y - reference_point_left_lower[1]) ** 2) > distance_left_lower:
                    distance_left_lower = math.sqrt(
                        (center_x - reference_point_left_lower[0]) ** 2 +
                        (center_y - reference_point_left_lower[1]) ** 2)
                    point_left_lower = (center_x, center_y)
                    rec_left_lower = [x, y, x + w, y + h]

                if math.sqrt((center_x - reference_point_right_upper[0]) ** 2 + (
                        center_y - reference_point_right_upper[1]) ** 2) > distance_right_upper:
                    distance_right_upper = math.sqrt(
                        (center_x - reference_point_right_upper[0]) ** 2 +
                        (center_y - reference_point_right_upper[1]) ** 2)
                    point_right_upper = (center_x, center_y)
                    rec_right_upper = [x, y, x + w, y + h]

                if math.sqrt((center_x - reference_point_right_lower[0]) ** 2 + (
                        center_y - reference_point_right_lower[1]) ** 2) > distance_right_lower:
                    distance_right_lower = math.sqrt(
                        (center_x - reference_point_right_lower[0]) ** 2 +
                        (center_y - reference_point_right_lower[1]) ** 2)
                    point_right_lower = (center_x, center_y)
                    rec_right_lower = [x, y, x + w, y + h]

        # 6. get out radius
        x_coords = [point_left_upper[0], point_left_lower[0],
                    point_right_upper[0], point_right_lower[0]]
        y_coords = [point_left_upper[1], point_left_lower[1],
                    point_right_upper[1], point_right_lower[1]]

        center_x_float = sum(x_coords) / len(x_coords)
        center_y_float = sum(y_coords) / len(y_coords)

        center_x = int(center_x_float)
        center_y = int(center_y_float)
        self.star_center = (center_x, center_y)

        radius_x = np.mean(np.abs(np.array(x_coords) - center_x))
        radius_y = np.mean(np.abs(np.array(y_coords) - center_y))
        out_radius = int(np.mean([radius_x, radius_y]))
        self.star_out_radius = out_radius

        # 7. get inner radius
        self.star_roi = [min(y_coords), max(y_coords), min(x_coords), max(x_coords)]
        self.star_roi_image = self.image[min(y_coords): max(y_coords), min(x_coords): max(x_coords)]
        self.star_roi_center = (center_x - min(x_coords), center_y - min(y_coords))

        cropped_gray = cv2.cvtColor(self.star_roi_image, cv2.COLOR_BGR2GRAY)
        _, cropped_binary = cv2.threshold(cropped_gray, 30, 255, cv2.THRESH_BINARY)
        cropped_binary = cv2.bitwise_not(cropped_binary)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(cropped_binary, connectivity=8)

        distances = []
        for i in range(1, num_labels):
            component_center_x, component_center_y = centroids[i]

            dist = math.sqrt(
                (component_center_x - self.star_roi_center[0]) ** 2 +
                (component_center_y - self.star_roi_center[1]) ** 2
            )
            distances.append((dist, i))

        distances.sort(key=lambda item: item[0])
        closest_component_1_idx = distances[0][1]
        closest_component_2_idx = distances[1][1]

        stat1 = stats[closest_component_1_idx]
        x1, y1, w1, h1, area1 = stat1
        x1_min, y1_min, x1_max, y1_max = x1, y1, x1 + w1, y1 + h1

        stat2 = stats[closest_component_2_idx]
        x2, y2, w2, h2, area2 = stat2
        x2_min, y2_min, x2_max, y2_max = x2, y2, x2 + w2, y2 + h2

        inner_radius = 0.25 * (max(x1_max, x2_max) - min(x1_min, x2_min) + max(y1_max, y2_max) - min(y2_min, y1_min))
        self.star_inner_radius = int(inner_radius)
        # show
        if show:
            img_2 = self.star_roi_image.copy()
            cv2.circle(img_2, self.star_roi_center, self.star_inner_radius, (0, 0, 255), 4)
            cv2.circle(img_2, self.star_roi_center, 5, (0, 0, 255), -1)

            plt.figure(figsize=(15, 10))

            plt.subplot(221)
            plt.imshow(sharpened, cmap='gray')
            plt.title(f'sharpened')
            plt.axis('off')

            plt.subplot(222)
            plt.imshow(edges, cmap='gray')
            plt.title(f'edges')
            plt.axis('off')

            plt.subplot(223)
            plt.imshow(cv2.cvtColor(self.image_display, cv2.COLOR_BGR2RGB))
            plt.title(f'out radius')
            plt.axis('off')

            plt.subplot(224)
            plt.imshow(cv2.cvtColor(img_2, cv2.COLOR_BGR2RGB))
            plt.title(f'roi')
            plt.axis('off')

            plt.tight_layout()
            plt.show(block=False)  # 非阻塞显示
            plt.pause(3000)  # 暂停3秒
            plt.close()

        self.data_roi["star_roi"] = self.star_roi
        self.data_roi["star_center"] = self.star_center
        self.data_roi["star_out_radius"] = self.star_out_radius
        self.data_roi["star_inner_radius"] = self.star_inner_radius
        self.data_roi["point_left_upper"] = point_left_upper
        self.data_roi["point_left_lower"] = point_left_lower
        self.data_roi["point_right_upper"] = point_right_upper
        self.data_roi["point_right_lower"] = point_right_lower
        self.data_roi["rec_left_upper"] = rec_left_upper
        self.data_roi["rec_left_lower"] = rec_left_lower
        self.data_roi["rec_right_upper"] = rec_right_upper
        self.data_roi["rec_right_lower"] = rec_right_lower

    def roi_gray_scale(self, show=False):
        # 1. resize image
        max_height = 800
        max_width = 1200
        scale = min(max_height / self.height, max_width / self.width)

        new_height = int(self.height * scale)
        new_width = int(self.width * scale)
        new_image = cv2.resize(self.image, (new_width, new_height))
        new_center = (int(self.star_center[0] * scale), int(self.star_center[1] * scale))

        # 2. do pre-process
        gray = cv2.cvtColor(new_image, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        if mean_brightness < 80:
            gray = cv2.equalizeHist(gray)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        # 3. find contours
        contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 4. filter fot 4 rects
        d1 = np.inf
        d2 = np.inf
        rect1 = None
        rect2 = None
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            if 4 < w / h < 6:
                center_rect = (x + int(w / 2), y + int(h / 2))
                d = math.sqrt((center_rect[0] - new_center[0]) ** 2 + (center_rect[1] - new_center[1]) ** 2)
                if d < d1:
                    rect2 = rect1
                    rect1 = int(x / scale), int(y / scale), int(x / scale) + int(w / scale), int(y / scale) + int(
                        h / scale)
                    d2 = d1
                    d1 = d
                elif d < d2:
                    d2 = d
                    rect2 = int(x / scale), int(y / scale), int(x / scale) + int(w / scale), int(y / scale) + int(
                        h / scale)

        if not rect1 and not rect2:
            raise ValueError(f'rect1 and rect')

        if rect1[1] < rect2[1]:
            gray_upper = rect1
            gray_lower = rect2
        else:
            gray_lower = rect1
            gray_upper = rect2

        gray_left, gray_right = self.get_left_right(gray_upper, self.star_center)

        # 5. process data
        center_gray_scale = {}
        if gray_lower:
            x_interval = int(0.1*(gray_lower[2] - gray_lower[0]))
            y_center = int(0.5*(gray_lower[1] + gray_lower[3]))
            ps = int(0.31*(gray_lower[3] - gray_lower[1]))
            center_gray_scale['16'] = (gray_lower[0] + x_interval, y_center, ps)
            center_gray_scale['18'] = (gray_lower[0] + 3*x_interval, y_center, ps)
            center_gray_scale['20'] = (gray_lower[0] + 5*x_interval, y_center, ps)
            center_gray_scale['19'] = (gray_lower[0] + 7*x_interval, y_center, ps)
            center_gray_scale['17'] = (gray_lower[0] + 9*x_interval, y_center, ps)
        if gray_upper:
            x_interval = int(0.1*(gray_upper[2] - gray_upper[0]))
            y_center = int(0.5*(gray_upper[1] + gray_upper[3]))
            ps = int(0.31 * (gray_upper[3] - gray_upper[1]))
            center_gray_scale['4'] = (gray_upper[0] + x_interval, y_center, ps)
            center_gray_scale['2'] = (gray_upper[0] + 3*x_interval, y_center, ps)
            center_gray_scale['1'] = (gray_upper[0] + 5*x_interval, y_center, ps)
            center_gray_scale['3'] = (gray_upper[0] + 7*x_interval, y_center, ps)
            center_gray_scale['5'] = (gray_upper[0] + 9*x_interval, y_center, ps)
        if gray_left:
            y_interval = int(0.1*(gray_left[3] - gray_left[1]))
            x_center = int(0.5*(gray_left[0] + gray_left[2]))
            ps = int(0.31 * (gray_left[2] - gray_left[0]))
            center_gray_scale['6'] = (x_center, gray_left[1] + y_interval, ps)
            center_gray_scale['8'] = (x_center, gray_left[1] + 3*y_interval, ps)
            center_gray_scale['10'] = (x_center, gray_left[1] + 5*y_interval, ps)
            center_gray_scale['12'] = (x_center, gray_left[1] + 7*y_interval, ps)
            center_gray_scale['14'] = (x_center, gray_left[1] + 9*y_interval, ps)
        if gray_right:
            y_interval = int(0.1*(gray_right[3] - gray_right[1]))
            x_center = int(0.5*(gray_right[0] + gray_right[2]))
            ps = int(0.31 * (gray_right[2] - gray_right[0]))
            center_gray_scale['7'] = (x_center, gray_right[1] + y_interval, ps)
            center_gray_scale['9'] = (x_center, gray_right[1] + 3*y_interval, ps)
            center_gray_scale['11'] = (x_center, gray_right[1] + 5*y_interval, ps)
            center_gray_scale['13'] = (x_center, gray_right[1] + 7*y_interval, ps)
            center_gray_scale['15'] = (x_center, gray_right[1] + 9*y_interval, ps)

        gray_scale_roi = dict(sorted(center_gray_scale.items(), key=lambda item: int(item[0])))

        if show:
            plt.figure(figsize=(15, 10))

            plt.subplot(221)
            plt.imshow(cv2.cvtColor(new_image, cv2.COLOR_BGR2RGB))
            plt.title('src')
            plt.axis('off')

            plt.subplot(222)
            plt.imshow(edges, cmap='gray')
            plt.title('edges')
            plt.axis('off')

            plt.subplot(223)
            plt.imshow(gray, cmap='gray')
            plt.title(f'gray')
            plt.axis('off')

            plt.subplot(224)
            plt.imshow(cv2.cvtColor(self.image_display, cv2.COLOR_BGR2RGB))
            plt.title(f'find out ')
            plt.axis('off')

            plt.tight_layout()
            plt.show(block=False)  # 非阻塞显示
            plt.pause(3)  # 暂停3秒
            plt.close()

        self.data_roi["gray_lower"] = gray_lower
        self.data_roi["gray_upper"] = gray_upper
        self.data_roi["gray_left"] = gray_left
        self.data_roi["gray_right"] = gray_right
        self.data_roi["gray_scale_roi"] = gray_scale_roi

    def read_roi(self):
        with open(self.file_roi, 'r', encoding='utf-8') as f:
            self.data_roi = json.load(f)
        self.gray_scale_roi = self.data_roi["gray_scale_roi"]
        self.star_roi = self.data_roi["star_roi"]
        self.star_center = self.data_roi["star_center"]
        self.star_out_radius = self.data_roi["star_out_radius"]
        self.star_inner_radius = self.data_roi["star_inner_radius"]

        star_center = self.data_roi["star_center"]
        star_out_radius = self.data_roi["star_out_radius"]
        star_inner_radius = self.data_roi["star_inner_radius"]
        point_left_upper = self.data_roi["point_left_upper"]
        point_left_lower = self.data_roi["point_left_lower"]
        point_right_upper = self.data_roi["point_right_upper"]
        point_right_lower = self.data_roi["point_right_lower"]
        rec_left_upper = self.data_roi["rec_left_upper"]
        rec_left_lower = self.data_roi["rec_left_lower"]
        rec_right_upper = self.data_roi["rec_right_upper"]
        rec_right_lower = self.data_roi["rec_right_lower"]
        gray_lower = self.data_roi["gray_lower"]
        gray_upper = self.data_roi["gray_upper"]
        gray_left = self.data_roi["gray_left"]
        gray_right = self.data_roi["gray_right"]

        cv2.rectangle(self.image_display, (rec_left_upper[0], rec_left_upper[1]),
                      (rec_left_upper[2], rec_left_upper[3]), (0, 255, 0), 10)
        cv2.rectangle(self.image_display, (rec_left_lower[0], rec_left_lower[1]),
                      (rec_left_lower[2], rec_left_lower[3]), (0, 255, 0), 10)
        cv2.rectangle(self.image_display, (rec_right_upper[0], rec_right_upper[1]),
                      (rec_right_upper[2], rec_right_upper[3]), (0, 255, 0), 10)
        cv2.rectangle(self.image_display, (rec_right_lower[0], rec_right_lower[1]),
                      (rec_right_lower[2], rec_right_lower[3]), (0, 255, 0), 10)

        cv2.circle(self.image_display, point_left_upper, 5, (0, 0, 255), 6)
        cv2.circle(self.image_display, point_left_lower, 5, (0, 0, 255), 6)
        cv2.circle(self.image_display, point_right_upper, 5, (0, 0, 255), 6)
        cv2.circle(self.image_display, point_right_lower, 5, (0, 0, 255), 6)
        cv2.circle(self.image_display, star_center, star_out_radius, (0, 0, 255), 6)
        cv2.circle(self.image_display, star_center, star_inner_radius, (0, 0, 255), 6)

        cv2.rectangle(self.image_display, (gray_lower[0], gray_lower[1]), (gray_lower[2], gray_lower[3]),
                      (0, 255, 0), 10)
        cv2.rectangle(self.image_display, (gray_upper[0], gray_upper[1]), (gray_upper[2], gray_upper[3]),
                      (0, 255, 0), 10)
        cv2.rectangle(self.image_display, (gray_left[0], gray_left[1]), (gray_left[2], gray_left[3]),
                      (0, 255, 0), 10)
        cv2.rectangle(self.image_display, (gray_right[0], gray_right[1]), (gray_right[2], gray_right[3]),
                      (0, 255, 0), 10)

        for point in self.gray_scale_roi.values():
            cv2.circle(self.image_display, (point[0], point[1]), 55, (167, 160, 10), 10)

        cv2.imwrite(self.path_display, self.image_display)

    def gen_roi_file(self):
        self.roi_center_siemens_star()
        self.roi_gray_scale()
        with open(self.file_roi, "w", encoding="utf-8") as fm:
            json.dump(self.data_roi, fm, ensure_ascii=False, indent=4)

    def evaluate(self, metric=('Resolution', 'Contrast', 'Noise')):
        self.read_roi()

        if 'Resolution' in metric:
            self.eva_resolution()
        if 'Contrast' in metric:
            self.eva_contrast()
        if 'Noise' in metric:
            self.eva_visual_noise()


class Resolution(object):
    def __init__(self, roi_image, center, out_radius, inner_radius, image_h, x_cam_measured, cct, light, height):
        self.roi_image = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
        self.center = center
        self.out_radius = out_radius
        self.inner_radius = inner_radius
        self.image_h = image_h
        self.x_cam_measured = np.round(x_cam_measured[::-1])
        self.cct = cct
        self.light = light
        self.height = height

        self.Num_points = 100.0
        self.Nc = 144.0

        self.out_height = 120
        self.view_dis = 68

        self.DeGamma_LUT_MAP_Polyfit = None

        self.mtf10_criteria = {
            'D65': {
                '1000Lx': 85,
                '100Lx': 75
            },
            'TL84': {
                '1000Lx': 85,
                '100Lx': 75,
                '20Lx': 70
            },
            'A': {
                '100Lx': 75,
                '20Lx': 70
            }
        }
        self.vmtf_criteria = {
            'D65': {
                '1000Lx': 70,
                '100Lx': 60
            },
            'TL84': {
                '1000Lx': 70,
                '100Lx': 60,
                '20Lx': 50
            },
            'A': {
                '100Lx': 60,
                '20Lx': 50
            }
        }

        self.mtf10 = None
        self.mtf10_score = None
        self.mtf10_result = None

        self.vmtf = None
        self.vmtf_score = None
        self.vmtf_result = None

    def get_gamma_lut_map_polyfit(self):
        # 4th-order polynomial fitting (np.polyfit) for De-gamma
        try:
            ref_value = np.array(
                [0.31831, 1.15571, 2.20217, 4.19614, 6.96386, 11.03698, 16.32488, 23.05951, 31.10643, 41.006, 52.82629,
                 66.5, 83.72, 103, 123.83, 148.88, 174.924, 205.51, 241.46, 277.236])
            ref_value = ref_value / ref_value.max() * round(np.max(self.x_cam_measured) - np.min(self.x_cam_measured))

            # Use degree 4 as requested
            poly_coefficient = np.polyfit(self.x_cam_measured, ref_value, 4)

            # 0 to 255 input values for the LUT
            x_for_lut = np.arange(256, dtype=np.float32)
            DeGamma_LUT_MAP_Polyfit = np.polyval(poly_coefficient, x_for_lut)

            self.DeGamma_LUT_MAP_Polyfit = np.clip(DeGamma_LUT_MAP_Polyfit, 0, 255).astype(np.uint8)
        except np.linalg.LinAlgError as e:
            warnings.warn(
                f"Polynomial fitting failed (np.polyfit): {e}. Polynomial De-gamma LUT will not be available.")
            self.DeGamma_LUT_MAP_Polyfit = None  # Indicate failure
        except Exception as e:
            warnings.warn(
                f"An unexpected error occurred during polynomial fitting: {e}."
                f" Polynomial De-gamma LUT will not be available.")
            self.DeGamma_LUT_MAP_Polyfit = None

    @staticmethod
    def _group_average_mtf_curves(all_mtf_curves, group_size=3):
        """
        Averages MTF curves in groups.
        Args:
            all_mtf_curves (np.array): A 2D array where rows are MTF curves for segments.
                                       Expected shape (N_segments, N_frequencies).
            group_size (int): Number of segments to average together.
        Returns:
            np.array: A 2D array with averaged MTF curves.
                      Expected shape (N_segments / group_size, N_frequencies).
        """
        num_segments = all_mtf_curves.shape[0]
        num_frequencies = all_mtf_curves.shape[1]

        if num_segments % group_size != 0:
            warnings.warn(
                f"Number of segments ({num_segments}) is not perfectly divisible by group_size ({group_size}). "
                f"The last group might contain fewer segments or some segments might be ignored.")

        num_averaged_curves = num_segments // group_size
        averaged_mtf_curves = np.zeros((num_averaged_curves, num_frequencies), dtype=np.float64)

        for i in range(num_averaged_curves):
            start_idx = i * group_size
            end_idx = min((i + 1) * group_size, num_segments)

            averaged_mtf_curves[i, :] = np.mean(all_mtf_curves[start_idx:end_idx, :], axis=0)

        return averaged_mtf_curves

    @staticmethod
    def find_x_for_y_value(data_array):
        if data_array.ndim != 2 or data_array.shape[1] < 9:
            raise ValueError("Input data_array must be a 2D array with at least 9 columns.")

        results = []

        f = data_array[:, 0]
        for col_idx in range(1, 9):
            y_values = data_array[:, col_idx]
            for i, y in enumerate(y_values):
                if (y < 0.1) and (y_values[i - 1] > 0.1):
                    results.append(f[i - 1] + (f[i] - f[i - 1]) * (0.1 - y) / (y_values[i - 1] - y))
        return sum(results) / len(results)

    def compute_csf(self, freq_pp):
        freq_pd = freq_pp * np.pi * self.image_h * self.view_dis / (180 * self.out_height)

        a = 75
        b = 0.2
        c = 0.9
        K = 46

        CSF = (K + a * freq_pd ** c) * np.exp(-b * freq_pd) / K

        return CSF

    def compute_vmtf(self, MTF, freq, nf=0.5):
        freq = np.array(freq)
        MTF = np.squeeze(MTF)

        index = np.where(freq >= nf)[0]
        if len(index) == 0:
            return 0.0
        cutoff = index[0]

        csf = self.compute_csf(freq[:cutoff])

        delta_f = np.diff(freq[:cutoff])
        num = np.sum((MTF[:cutoff - 1] * csf[:-1] + MTF[1:cutoff] * csf[1:cutoff]) / 2 * delta_f)
        den = np.sum((csf[:-1] + csf[1:cutoff]) / 2 * delta_f)

        return num / den if den != 0 else 0.0

    def compute_all_vmtf(self, freq, mtf_data):
        vmtf_values = []
        for i in range(mtf_data.shape[1]):
            vmtf = self.compute_vmtf(mtf_data[:, i], freq)
            vmtf_values.append(round(vmtf, 2))
        return vmtf_values

    def calc_mtf(self):
        img = self.roi_image.copy()

        # 1.0 get De-Gamma and make correction
        self.get_gamma_lut_map_polyfit()
        img = self.DeGamma_LUT_MAP_Polyfit[img.astype(np.uint8)]

        # 2.0 MTF calculation
        hfCutOff = int(self.Num_points * 0.7)

        img = img.astype(np.float32)
        all_sampling_points_coords = []

        # 2.1 Generate log-spaced radial sampling points
        if self.inner_radius <= 0 or self.out_radius <= self.inner_radius:
            raise ValueError(f"Invalid radii: innerRadius ({self.inner_radius}) must be > 0"
                             f" and < outerRadius ({self.out_radius}).")

        start_log_rad_val = math.ceil(self.inner_radius) + 5
        end_log_rad_val = math.floor(self.out_radius) - 10

        rad_list = np.linspace(start_log_rad_val, end_log_rad_val, int(self.Num_points))
        num_radii = len(rad_list)

        # 2.2 Define 24 angular segments
        num_segments = 24
        segment_angle_size = 2 * math.pi / num_segments
        segments_raw = np.zeros((num_segments, 2), dtype=np.float64)

        for i in range(num_segments):
            start_angle = (i * segment_angle_size) - (segment_angle_size / 2)
            end_angle = ((i + 1) * segment_angle_size) - (segment_angle_size / 2)

            segments_raw[i, 0] = start_angle
            segments_raw[i, 1] = end_angle

        # 2.3 Initialize MTF storage matrix
        MTF = np.zeros((num_segments, num_radii), dtype=np.float64)
        MTF1 = np.zeros((num_segments, num_radii), dtype=np.float64)
        res_freq_low_to_high = np.zeros(num_radii, dtype=np.float64)

        # 2.4 Main loop: Iterate through radii (from largest to smallest) and segments
        for i_rev_idx, r in enumerate(reversed(rad_list)):
            res_freq_low_to_high[i_rev_idx] = self.image_h * 144 / 2 / math.pi / r

            col_idx = num_radii - 1 - i_rev_idx
            if col_idx < 0:
                continue

            for j_idx in range(num_segments):
                A_mat_rows = []
                b_vec_values = []

                k_start = segments_raw[j_idx, 0]
                k_end = segments_raw[j_idx, 1]

                if k_end < k_start:
                    k_end += 2 * math.pi

                current_angle = k_start
                angle_step = math.pi / 256.0

                # 2.5 Inner loop: Sample pixels along the arc
                while current_angle <= k_end + 1e-9:
                    x_offset = r * math.cos(current_angle)
                    y_offset = r * math.sin(current_angle)

                    pixel_x = int(round(self.center[0] + x_offset))
                    pixel_y = int(round(self.center[1] - y_offset))

                    all_sampling_points_coords.append((pixel_x, pixel_y))

                    if 0 <= pixel_y < img.shape[0] and 0 <= pixel_x < img.shape[1]:
                        pixel_val = img[pixel_y, pixel_x]  # Use float image here
                        b_vec_values.append(float(pixel_val))

                        phi_for_regression = current_angle

                        A_mat_rows.append([1.0, math.sin(self.Nc * phi_for_regression),
                                           math.cos(self.Nc * phi_for_regression)])
                    current_angle += angle_step

                # 2.6 quick test (simple contrast)
                if b_vec_values:
                    pixel_values = np.array(b_vec_values, dtype=np.float64)
                    max_val = pixel_values.max()
                    min_val = pixel_values.min()
                    if (max_val + min_val) != 0:
                        MTF1[j_idx, col_idx] = (max_val - min_val) / (max_val + min_val)
                    else:
                        MTF1[j_idx, col_idx] = 0.0
                else:
                    MTF1[j_idx, col_idx] = 0.0

                # 2.7 Perform linear regression
                if A_mat_rows and len(A_mat_rows) >= 3:
                    A_mat = np.array(A_mat_rows, dtype=np.float64)
                    b_vec = np.array(b_vec_values, dtype=np.float64).reshape(-1, 1)
                    try:
                        U, s, Vh = np.linalg.svd(A_mat, full_matrices=False)
                        s_inv = np.zeros_like(s)
                        s_inv[s > 1e-10] = 1.0 / s[s > 1e-10]
                        invA = Vh.T @ np.diag(s_inv) @ U.T

                        coefficients = invA @ b_vec

                        dc_offset = coefficients[0, 0]
                        sine_amp = coefficients[1, 0]
                        cosine_amp = coefficients[2, 0]

                        current_mtf_val = 0.0
                        if dc_offset > 1e-6:
                            current_mtf_val = math.sqrt(sine_amp ** 2 + cosine_amp ** 2) / dc_offset
                        MTF[j_idx, col_idx] = current_mtf_val
                    except np.linalg.LinAlgError as e:
                        warnings.warn(f"LinAlgError for radius {r:.2f}, segment {j_idx}: {e}. Setting MTF to 0.")
                        MTF[j_idx, col_idx] = 0.0
                    except Exception as e:
                        warnings.warn(f"General error for radius {r:.2f}, segment {j_idx}: {e}. Setting MTF to 0.")
                        MTF[j_idx, col_idx] = 0.0
                else:
                    MTF[j_idx, col_idx] = 0.0

        # 2.8 Compute High-Frequency Area MTF
        resMTFAreaPerSeg = np.zeros(num_segments)
        for j_idx in range(num_segments):
            if hfCutOff >= MTF.shape[1] or hfCutOff < 0:
                warnings.warn(
                    f"hfCutOff ({hfCutOff}) is out of bounds for MTF data (size {MTF.shape[1]})."
                    f" HF Area for segment {j_idx} will be 0.")
                resMTFAreaPerSeg[j_idx] = 0.0
            else:
                resMTFAreaPerSeg[j_idx] = np.sum(MTF[j_idx, hfCutOff:])
        np.mean(resMTFAreaPerSeg)

        # 2.9 Normalize MTF values
        res_mtf_norm = np.zeros_like(MTF, dtype=np.float64)
        for j_idx in range(num_segments):
            normalization_val = MTF[j_idx, num_radii - 1]  # MTF for largest radius (lowest frequency)
            if normalization_val > 1e-6:
                res_mtf_norm[j_idx, :] = MTF[j_idx, :] / normalization_val
            else:
                warnings.warn(
                    f"MTF value at lowest frequency for segment {j_idx} is near zero. Cannot normalize."
                    f" Segment {j_idx} MTF set to zero.")
                res_mtf_norm[j_idx, :] = 0.0

        res_mtf_norm_flipped = np.flip(res_mtf_norm, axis=1)

        # 3.0 Group and average the MTF curves themselves (24 -> 8 curves)
        averaged_res_mtf_curves = self._group_average_mtf_curves(res_mtf_norm_flipped, group_size=3)

        result = np.concat([np.expand_dims(res_freq_low_to_high.T, axis=1), averaged_res_mtf_curves.T], axis=1)
        self.mtf10 = self.find_x_for_y_value(result)

        # 4.0 Calculate vMTF for each of the 24 segments
        mtf_data = np.vstack((res_freq_low_to_high.reshape(1, -1), averaged_res_mtf_curves))
        mtf_data = mtf_data.T
        res_freq = mtf_data[:, 0]
        res_mtf = mtf_data[:, 1:9]
        res_freq_rad = res_freq / self.image_h
        vmtf_values = self.compute_all_vmtf(res_freq_rad, res_mtf)
        self.vmtf = np.mean(vmtf_values)

    def eva_resolution(self):
        self.calc_mtf()

        self.mtf10_score = int(100 * (self.mtf10 * 2 / self.height))
        if self.mtf10_score >= 100:
            self.mtf10_score = 100
        if self.mtf10_score >= self.mtf10_criteria[self.cct][self.light]:
            self.mtf10_result = 'Pass'
        else:
            self.mtf10_result = 'Fail'

        self.vmtf_score = self.vmtf * 100
        if self.vmtf_score >= 100:
            self.vmtf_score = 100
        if self.vmtf_score >= self.vmtf_criteria[self.cct][self.light]:
            self.vmtf_result = 'Pass'
        else:
            self.vmtf_result = 'Fail'


class Contrast(object):
    def __init__(self, image, rois, cct, light):
        self.image = image
        self.rois = rois
        self.cct = cct
        self.light = light

        self.TH = {
            "D65_1000Lx": {"Global": 80, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
            "D65_100Lx": {"Global": 80, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
            "TL84_1000Lx": {"Global": 80, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
            "TL84_100Lx": {"Global": 80, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
            "TL84_20Lx": {"Global": 75, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
            "A_100Lx": {"Global": 80, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
            "A_20Lx": {"Global": 75, "Local": 85, "MinLocal": 100, "Dark": 50, "Saturation": 100},
        }
        self.contrasts = None
        self.L_list = []

        self.global_contrast_score = None
        self.global_contrast_result = None

        self.local_contrast_score = None
        self.local_contrast_result = None

        self.black_level_score = None
        self.black_level_result = None

        self.saturation_score = None
        self.saturation_result = None

        self.min_local_contrast_score = None
        self.min_local_contrast_result = None

    @staticmethod
    def _srgb_to_linear(c):
        c = np.asarray(c, dtype=np.float64)
        return np.where(c <= 0.04045, c/12.92, ((c+0.055)/1.055)**2.4)

    def _rgb_to_xyz(self, rgb01):  # [...,3], in [0,1] sRGB (D65)
        M = np.array([[0.4124564, 0.3575761, 0.1804375],
                      [0.2126729, 0.7151522, 0.0721750],
                      [0.0193339, 0.1191920, 0.9503041]], dtype=np.float64)
        rgb_lin = self._srgb_to_linear(rgb01)
        return np.dot(rgb_lin, M.T)

    @staticmethod
    def _f_lab(t):
        d = 6/29
        return np.where(t > d**3, np.cbrt(t), t/(3*d**2) + 4/29)

    def rgb_to_lab_L(self, rgb_mean_255):
        if np.any(np.isnan(rgb_mean_255)):
            return float('nan')
        rgb01 = np.asarray(rgb_mean_255, dtype=np.float64) / 255.0
        xyz = self._rgb_to_xyz(rgb01)
        Xn, Yn, Zn = 0.95047, 1.00000, 1.08883  # D65
        x, y, z = xyz[..., 0]/Xn, xyz[..., 1]/Yn, xyz[..., 2]/Zn
        fy = self._f_lab(y)

        # print(f"rgb_mean_255={rgb_mean_255},rgb01={rgb01},xyz={xyz},x={x}, y={y}, z={z},fy={fy}")

        L = 116*fy - 16

        return float(np.clip(L, 0, 100))

    @staticmethod
    def local_contrast_to_score(lc: float) -> float:
        if np.isnan(lc):
            return 0.0
        if lc <= 1.0:
            return 0.0
        if lc >= 2.0:
            return 100.0
        return (lc - 1.0) * 100.0

    @staticmethod
    def dark_score_from_L(L: float, good_at: float, bad_at: float) -> float:
        """Lower-is-better，good_at→100, bad_at→0（线性）"""
        if math.isnan(L):
            return 0.0
        if L <= good_at:
            return 100.0
        if L >= bad_at:
            return 0.0
        return 100.0 * (bad_at - L) / (bad_at - good_at)

    @staticmethod
    def score_to_result(score, criteria):
        if score >= criteria:
            return 'Pass'
        else:
            return 'Fail'

    def eva_contrast(self):
        rgb_img = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        for i in self.rois:
            cx, cy, radius = self.rois[i]
            x1 = cx - radius
            x2 = cx + radius
            y1 = cy - radius
            y2 = cy + radius
            roi = rgb_img[y1:y2, x1:x2, :]
            roi_rgb = roi.reshape(-1, 3).mean(axis=0)
            L = self.rgb_to_lab_L(roi_rgb)
            self.L_list.append(float(np.round(L, 2)))

        # Contrast（1~19）
        self.contrasts = []
        for i in range(20):
            if i < 19 and (not np.isnan(self.L_list[i])) and (not np.isnan(self.L_list[i + 1])):
                self.contrasts.append(float(np.round(self.L_list[i] - self.L_list[i + 1], 2)))
            else:
                self.contrasts.append(float('nan'))

        # Local Contrast （1~17）
        LC_value = []
        LC_scores = []
        for i in range(17):
            LC_value.append(self.contrasts[i])
            LC_scores.append(self.local_contrast_to_score(self.contrasts[i]))

        L1 = self.L_list[0]
        L2 = self.L_list[1]
        L19 = self.L_list[18]
        L20 = self.L_list[19]
        print(self.L_list)

        # Global Contrast
        self.global_contrast_score = float(np.round(L1 - L20, 2))
        self.global_contrast_result = self.score_to_result(self.global_contrast_score,
                                                           self.TH[self.cct+'_'+self.light]["Global"])

        # Local Contrast
        self.local_contrast_score = float(np.round(np.nanmean(LC_scores), 2))
        self.local_contrast_result = self.score_to_result(self.local_contrast_score,
                                                          self.TH[self.cct+'_'+self.light]["Local"])

        # Dark Level L19
        dark19_score = self.dark_score_from_L(L19, good_at=4.0, bad_at=5.0)
        dark20_score = self.dark_score_from_L(L20, good_at=2.0, bad_at=3.0)
        self.black_level_score = float(np.round(min(dark19_score, dark20_score), 2))
        self.black_level_result = self.score_to_result(self.black_level_score,
                                                       self.TH[self.cct+'_'+self.light]["Dark"])

        self.saturation_score = float(100.0 if (L2 < 99.65) else 0.0)
        self.saturation_result = self.score_to_result(self.saturation_score,
                                                      self.TH[self.cct+'_'+self.light]["Saturation"])

        # Min Local Contrast
        self.min_local_contrast_score = float(100.0 if np.nanmin(LC_value) > 0 else 0.0)
        self.min_local_contrast_result = self.score_to_result(self.min_local_contrast_score,
                                                              self.TH[self.cct + '_' + self.light]["MinLocal"])


class VisualNoise(object):
    def __init__(self, image, rois, cct, light):
        self.image = image
        self.rois = rois
        self.cct = cct
        self.light = light

        self.vn_mean = None
        self.vn_max = None

        self.vn_mean_score = None
        self.vn_max_score = None

        self.vn_mean_result = None
        self.vn_max_result = None

        self.criteria = {
            'D65_1000Lx': {
                'vn_mean': 2,
                'vn_max': 4
            },
            'D65_100Lx': {
                'vn_mean': 2.5,
                'vn_max': 4.5
            },
            'TL84_1000Lx': {
                'vn_mean': 2,
                'vn_max': 4
            },
            'TL84_100Lx': {
                'vn_mean': 2.5,
                'vn_max': 4.5
            },
            'TL84_20Lx': {
                'vn_mean': 3,
                'vn_max': 4.95
            },
            'A_100Lx': {
                'vn_mean': 2.5,
                'vn_max': 4.5
            },
            'A_20Lx': {
                'vn_mean': 3,
                'vn_max': 4.95
            },
        }

        self.arr_ill = {
            'd50': np.array([0.9642, 1.0000, 0.8249]),
            'd65': np.array([0.95047, 1.00000, 1.08883]),
            'e': np.array([1.0000, 1.0000, 1.0000]),
            'a': np.array([1.0985, 1.0000, 0.3558]),
            'c': np.array([0.9807, 1.0000, 1.1822])
        }
        self.CycPerDeg = 16.5

        # Initialize constants
        self.mat_constants = type('', (), {})()
        self.mat_constants.a = 75
        self.mat_constants.b = 0.2
        self.mat_constants.c = 0.8
        self.mat_constants.K = 102.16

        self.mat_constants.a1_rg = 109.1413
        self.mat_constants.b1_rg = 4.0e-4
        self.mat_constants.c1_rg = 3.4244
        self.mat_constants.a2_rg = 93.5971
        self.mat_constants.b2_rg = 0.0037
        self.mat_constants.c2_rg = 2.1677

        self.mat_constants.a1_by = 7.0328
        self.mat_constants.b1_by = 0
        self.mat_constants.c1_by = 4.2582
        self.mat_constants.a2_by = 40.691
        self.mat_constants.b2_by = 0.1039
        self.mat_constants.c2_by = 1.6487

    @staticmethod
    def chromaAdapt(WP_S, WP_D, method):
        if method == 'BRADFORD':
            MA = np.array([
                [0.8951, -0.7502, 0.0389],
                [0.2664, 1.7135, -0.0685],
                [-0.1614, 0.0367, 1.0296]
            ])

            MA_inv = np.array([
                [0.9869929, 0.4323053, -0.0085287],
                [-0.1470543, 0.5183603, 0.0400428],
                [0.1599627, 0.0492912, 0.9684867]
            ])
        else:
            return np.eye(3)

        rgb_S = MA @ WP_S
        rgb_D = MA @ WP_D

        M_rgb = np.zeros((3, 3))
        M_rgb[0, 0] = rgb_D[0] / rgb_S[0]
        M_rgb[1, 1] = rgb_D[1] / rgb_S[1]
        M_rgb[2, 2] = rgb_D[2] / rgb_S[2]

        M = MA_inv @ M_rgb @ MA
        return M

    def frequency_matrix(self, w, h):
        h_L = -(h // 2)
        h_U = (h - 1) // 2
        w_L = -(w // 2)
        w_U = (w - 1) // 2

        iDeg = [2 * i / h * self.CycPerDeg for i in range(h_L, h_U + 1)]
        jDeg = [2 * j / h * self.CycPerDeg for j in range(w_L, w_U + 1)]

        I, J = np.meshgrid(iDeg, jDeg)
        F = np.sqrt(I ** 2 + J ** 2)
        return F

    def csf_scie(self, F):
        # For ISO 15739 old standard CSF curve

        # CSF_A
        tmp = F ** 0.9
        value = 45 + (tmp * 75)
        expo = np.exp(-0.2 * F)
        CSF_A = value * expo

        CSF_A = CSF_A * (1.0 / 45)
        CSF_A = CSF_A * 3 / np.max(CSF_A)
        CSF_A[F == 0] = 1

        # CSF_C1
        tmp = F ** self.mat_constants.c1_rg
        expo = np.exp(-self.mat_constants.b1_rg * tmp) * self.mat_constants.a1_rg
        tmp = F ** self.mat_constants.c2_rg
        CSF_C1 = np.exp(-self.mat_constants.b2_rg * tmp) * self.mat_constants.a2_rg
        CSF_C1 = CSF_C1 + expo
        CSF_C1 = CSF_C1 / np.max(CSF_C1)

        # CSF_C2
        tmp = F ** self.mat_constants.c1_by
        expo = np.exp(-self.mat_constants.b1_by * tmp) * self.mat_constants.a1_by
        tmp = F ** self.mat_constants.c2_by
        CSF_C2 = np.exp(-self.mat_constants.b2_by * tmp) * self.mat_constants.a2_by
        CSF_C2 = CSF_C2 + expo - 7.0328
        CSF_C2 = CSF_C2 / np.max(CSF_C2)

        return CSF_A, CSF_C1, CSF_C2

    @staticmethod
    def rgb_to_xyz_e(rgb):
        rgb = rgb.reshape(-1, 3)
        # Step 1: Convert RGB to XYZ (D65)
        rgb = np.array(rgb) / 255.0

        def gamma_correct(c):
            return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

        rgb_linear = gamma_correct(rgb)

        M_srgb_to_xyz = np.array([
            [0.4361, 0.3851, 0.1431],
            [0.2225, 0.7169, 0.0606],
            [0.0139, 0.0971, 0.7141]
        ])

        xyz_d65 = np.dot(rgb_linear, M_srgb_to_xyz.T)

        return xyz_d65.T

    @staticmethod
    def fourier(ACC, cols, rows):
        # Reshape ACC for FFT
        A = ACC[0].reshape(rows, cols)
        C1 = ACC[1].reshape(rows, cols)
        C2 = ACC[2].reshape(rows, cols)

        # Fourier Transform
        FA = fft2(A)
        FC1 = fft2(C1)
        FC2 = fft2(C2)

        # Shift DC to center
        FA = fftshift(FA)
        FC1 = fftshift(FC1)
        FC2 = fftshift(FC2)

        return FA, FC1, FC2

    @staticmethod
    def fourier_back(FA_f, FC1_f, FC2_f):
        # Shift back
        FA_shifted = ifftshift(FA_f)
        FC1_shifted = ifftshift(FC1_f)
        FC2_shifted = ifftshift(FC2_f)

        # Inverse FFT
        SA = np.real(ifft2(FA_shifted))
        SC1 = np.real(ifft2(FC1_shifted))
        SC2 = np.real(ifft2(FC2_shifted))

        # Reshape
        SA = SA.reshape(1, -1)
        SC1 = SC1.reshape(1, -1)
        SC2 = SC2.reshape(1, -1)

        # Combine
        SACC = np.vstack([SA, SC1, SC2])

        return SACC

    def calc_vn(self, patch):
        patch = patch.astype(np.float64)
        rows, cols = patch.shape[:2]

        WP_pcs = self.arr_ill['d50']
        M_Prof2E = self.chromaAdapt(WP_pcs, np.ones(3), 'BRADFORD')

        WP_d65 = self.arr_ill['d65']
        M_E2D65 = self.chromaAdapt(np.ones(3), WP_d65, 'BRADFORD')

        F = self.frequency_matrix(cols, rows)
        CSF_A, CSF_C1, CSF_C2 = self.csf_scie(F)

        # 1. rgb to linear rgb -> xyz
        XYZ_pcs = self.rgb_to_xyz_e(patch)

        # 2. xyz d65 -> xyz E
        XYZ_E = M_Prof2E @ XYZ_pcs

        # 3. XYZ_E to ACC
        xyz2acc = np.array([[0, 1, 0], [1, -1, 0], [0, 0.4, -0.4]])
        ACC = xyz2acc @ XYZ_E

        # 4. Apply CSF to ACC
        FA, FC1, FC2 = self.fourier(ACC, cols, rows)

        FA_f = FA * CSF_A
        FC1_f = FC1 * CSF_C1
        FC2_f = FC2 * CSF_C2

        SACC = self.fourier_back(FA_f, FC1_f, FC2_f)

        # 5. # ACC to XYZ_E
        acc2xyz = np.array([[1, 1, 0], [1, 0, 0], [1, 0, -2.5]])
        SXYZ_E = acc2xyz @ SACC

        SXYZ_pcs = (M_E2D65 @ SXYZ_E).T

        # 6. XYZ_E to LUV
        LUV = XYZ_to_Luv(SXYZ_pcs, illuminant=CCS_ILLUMINANTS['CIE 1931 2 Degree Standard Observer']['D65']).T
        stddev = np.std(LUV, axis=1)
        dL = stddev[0]
        dU = stddev[1]
        dV = stddev[2]

        # 7. get vn
        vn = dL + 0.852 * dU + 0.323 * dV

        return vn

    @staticmethod
    def vn_max_to_score(value):
        if value >= 9:
            score_max_vn = 0
        elif value <= 0.5:
            score_max_vn = 20
        else:
            score_max_vn = (-20/8.5) * value + (20/8.5*9)
        return int(score_max_vn)

    @staticmethod
    def vn_mean_to_score(value):
        if value >= 9:
            score_mean_vn = 0
        elif value <= 0.5:
            score_mean_vn = 80
        else:
            score_mean_vn = (-80/8.5) * value + (80/8.5*9)
        return int(score_mean_vn)

    def eva_visual_noise(self):
        image_rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        vns = []

        for idx, p in enumerate(self.rois, start=1):
            cx, cy, radius = self.rois[p]
            x = cx - radius
            y = cy - radius
            h = radius * 2
            w = radius * 2
            patch = image_rgb[y:y+h, x:x+w]
            vn = self.calc_vn(patch)
            vns.append(vn)

        self.vn_mean = np.mean(vns[2:18])
        self.vn_max = max(vns)

        self.vn_mean_score = self.vn_mean_to_score(self.vn_mean)
        self.vn_max_score = self.vn_max_to_score(self.vn_max)

        if self.vn_mean < self.criteria[self.cct + '_' + self.light]['vn_mean']:
            self.vn_mean_result = 'Pass'
        else:
            self.vn_mean_result = 'Fail'

        if self.vn_max < self.criteria[self.cct + '_' + self.light]['vn_max']:
            self.vn_max_result = 'Pass'
        else:
            self.vn_max_result = 'Fail'


def get_jpg(path):
    jpg_name = 'Snapshot_ipeout_pps_display_FULL_0'
    jpg_path = None
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith('.jpg') and jpg_name in file:
                full_path = os.path.join(root, file)
                jpg_path = full_path
                break
    return jpg_path


if __name__ == "__main__":
    # te42 = TE42(r'C:\Public\Auto_test\capturebin\tuning_task_20260304_165007\fine\1\fine_Plan_1_FineTune_BestVicinity_a78d22_cb6da0\IMG_20250821_005626.jpg', 'D65', '1000Lx')
    te42 = TE42(r'C:\Public\Auto_test\darklevel0324\default\IMG_20250801_064454.jpg', 'D65', '1000Lx')
    te42.gen_roi_file()
    # te42.file_roi = r'C:\Public\Auto_test\capturebin\tuning_task_20260304_165007\precapture\data\roi.json'
    te42.evaluate('Contrast')


