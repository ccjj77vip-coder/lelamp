# -*- coding: utf-8 -*-
import cv2
import time
import os
import threading

class CameraSystem:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.photo_dir = os.path.join(base_dir, "photos")
        if not os.path.exists(self.photo_dir):
            os.makedirs(self.photo_dir)
        
        self.cap = None
        self._lock = threading.Lock()  # 线程锁：防止网页流和拍照同时抢夺摄像头

    def _get_cap(self):
        if self.cap is None or not self.cap.isOpened():
            for cam_idx in [0, 1, 2]:
                self.cap = cv2.VideoCapture(cam_idx)
                if self.cap is not None and self.cap.isOpened():
                    # 硬件级 720p 分辨率
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    break
        return self.cap

    def take_photo(self):
        with self._lock:
            cap = self._get_cap()
            if cap is None or not cap.isOpened():
                return False, "无法连接摄像头硬件"

            # 清空陈旧缓冲帧，保证拍到的是说话瞬间的画面
            for _ in range(3):
                cap.read()

            ret, frame = cap.read()
            if ret:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.photo_dir, f"photo_{timestamp}.jpg")
                cv2.imwrite(filename, frame)
                return True, filename
            else:
                return False, "读取画面失败"

    def get_frame_bytes(self):
        # 专门给网页端推流用的高速接口
        with self._lock:
            cap = self._get_cap()
            if cap is None or not cap.isOpened():
                return None
            
            ret, frame = cap.read()
            if ret:
                # 网页预览降至 360p，极大减轻树莓派 CPU 推流压力
                frame = cv2.resize(frame, (640, 360))
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                return buffer.tobytes() if ret else None
            return None

_camera_instance = None
def get_camera_system():
    global _camera_instance
    if _camera_instance is None:
        _camera_instance = CameraSystem()
    return _camera_instance