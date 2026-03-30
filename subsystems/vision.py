# -*- coding: utf-8 -*-
import cv2
import numpy as np
import threading
import time
from config import HardwareConfig

class VisionSystem:
    def __init__(self):
        self.cap = cv2.VideoCapture(HardwareConfig.CAMERA_ID)
        # 锁定分辨率以保证处理帧率
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        self.net = cv2.dnn.readNetFromCaffe(HardwareConfig.DNN_PROTO, HardwareConfig.DNN_MODEL)
        self.running = False
        self.current_frame = None
        self.target_dx = None
        self.target_dy = None
        self.has_target = False
        self.lock = threading.Lock()

    def start(self):
        self.running = True
        threading.Thread(target=self._update, daemon=True).start()

    def stop(self):
        self.running = False
        if self.cap: self.cap.release()

    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # 根据配置决定是否翻转画面（镜像）
            if getattr(HardwareConfig, 'CV_FLIP', 0) == 1:
                frame = cv2.flip(frame, 1)

            h, w = frame.shape[:2]
            
            # DNN 预处理
            blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
            self.net.setInput(blob)
            detections = self.net.forward()

            found = False
            max_area = 0
            best_box = None

            # 遍历寻找画面中最大的人脸
            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                # 🔴 核心阈值：置信度大于 50% 才认为是人脸
                if confidence > 0.5: 
                    box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                    (startX, startY, endX, endY) = box.astype("int")
                    
                    # 边界安全钳制
                    startX, startY = max(0, startX), max(0, startY)
                    endX, endY = min(w, endX), min(h, endY)
                    
                    area = (endX - startX) * (endY - startY)
                    if area > max_area:
                        max_area = area
                        best_box = (startX, startY, endX, endY, confidence)

            if best_box:
                startX, startY, endX, endY, conf = best_box
                cX = (startX + endX) // 2
                cY = (startY + endY) // 2
                
                # 计算归一化偏移量 (-1.0 到 1.0)
                self.target_dx = (cX - w/2) / (w/2)
                self.target_dy = (cY - h/2) / (h/2)
                self.has_target = True
                found = True

                # 🟢 HUD 绘制：画出绿色锁定框和准星
                cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)
                cv2.circle(frame, (cX, cY), 4, (0, 0, 255), -1)
                cv2.putText(frame, f"TARGET LOCKED: {conf*100:.1f}%", (startX, startY-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
            if not found:
                self.has_target = False
                self.target_dx = None
                self.target_dy = None
                cv2.putText(frame, "SCANNING...", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

            # 编码为 JPEG 供 Web 端拉取
            with self.lock:
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret: self.current_frame = buffer.tobytes()
            
            time.sleep(0.02) # 维持 50FPS 的处理节奏

    def get_target(self):
        return (self.target_dx, self.target_dy) if self.has_target else None

    def get_video_frame(self):
        with self.lock: return self.current_frame

_vision_inst = None
def get_vision_system():
    global _vision_inst
    if _vision_inst is None: _vision_inst = VisionSystem()
    return _vision_inst
