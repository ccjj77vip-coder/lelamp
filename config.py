# -*- coding: utf-8 -*-
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def auto_detect_serial_port():
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            if any(k in p.description for k in ["USB", "CH340", "CP210", "Serial"]): return p.device
    except: pass
    return 'COM3' if sys.platform.startswith('win') else '/dev/ttyUSB0'

def auto_detect_camera():
    try:
        import cv2
        for i in range(2):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                cap.release()
                if ret: return i
    except: pass
    return 0

class HardwareConfig:
    SERVO_PORT = auto_detect_serial_port()
    CAMERA_ID = auto_detect_camera()
    SERVO_BAUDRATE = 1000000
    CV_FLIP = 1
    DNN_PROTO = os.path.join(BASE_DIR, "models/deploy.prototxt")
    DNN_MODEL = os.path.join(BASE_DIR, "models/res10_300x300_ssd_iter_140000.caffemodel")

class ServoConfig:
    ID_BASE_PAN = 1
    ID_NECK_TILT = 5
    ALL_IDS = [1, 2, 3, 4, 5] 
    
    LIMITS = {
        1: (0, 4095, 2048),
        2: (0, 4095, 2048),
        3: (0, 4095, 2048),
        4: (0, 4095, 2048),
        5: (0, 4095, 2048),
    }

class AlgorithmConfig:
    # 追踪方向配置（虽然目前关闭了，但保留正确值）
    PAN_DIRECTION = -1 
    TILT_DIRECTION = 1 
    
    # 追踪算法参数
    TRACKING_KP = 15.0
    TRACKING_KD = 20.0
    TRACKING_DEADZONE = 0.12
    INPUT_SMOOTH_FACTOR = 0.9
    LOST_BUFFER_FRAMES = 10
