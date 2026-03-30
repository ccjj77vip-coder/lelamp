# -*- coding: utf-8 -*-
import time
import math
from config import ServoConfig, AlgorithmConfig

class HeadTracker:
    def __init__(self, driver, vision):
        self.driver = driver
        self.vision = vision
        self.present_pan = 2048.0
        self.present_tilt = 2048.0
        self.goal_pan = 2048.0
        self.goal_tilt = 2048.0
        self.state = "IDLE"
        
        # ?? ������������Ĵ���������΢��(D)���Ƽ���
        self.last_dx = 0.0
        self.last_dy = 0.0
        
        self.serial_obj = None
        for name in ['serial', 'pSerial', '_serial', 'uart', 'ser']:
            if hasattr(self.driver, name): 
                self.serial_obj = getattr(self.driver, name)
                break

    def manual_sync_write(self, servo_data):
        if not self.serial_obj: return
        # �򻯰�ͬ��д���߼�
        packet = bytearray([0xFF, 0xFF, 0xFE, (6 + 1) * len(servo_data) + 4, 0x83, 0x2A, 6])
        payload_sum = 0
        for uid, pos in servo_data.items():
            pos = max(0, min(4095, int(pos)))
            packet.extend([uid, pos & 0xFF, (pos >> 8) & 0xFF, 0, 0, 0, 0])  # ���������λ��Ȼ�·���Ĭ�ϼ��ٶ�0������Ϊ׷���Ǹ�Ƶ΢������Ҫ������˲�������Ӱ�첻��
            payload_sum += (uid + (pos & 0xFF) + (pos >> 8))
        packet.append((~(0xFE + len(packet) - 3 + 0x83 + 0x2A + 6 + payload_sum)) & 0xFF)
        try: self.serial_obj.write(packet)
        except: pass

    def update(self):
        target = self.vision.get_target() # ���� vision �Ѹ��� dx, dy

        if target is not None:
            dx, dy = target
            
            # ?? 1. ������ˣ�ֻ��ƫ��������Ŷ�
            if abs(dx) < AlgorithmConfig.TRACKING_DEADZONE: dx = 0
            if abs(dy) < AlgorithmConfig.TRACKING_DEADZONE: dy = 0
            
            # ?? 2. PD������������΢�������������С�����ֹ����͵�ͷ��
            derivative_x = dx - self.last_dx
            derivative_y = dy - self.last_dy
            
            # ������ʷ���
            self.last_dx = dx
            self.last_dy = dy
            
            kp = AlgorithmConfig.TRACKING_KP
            kd = getattr(AlgorithmConfig, 'TRACKING_KD', 20.0)
            
            # �������벽����P��(�������) + D��(��������)
            step_pan = (dx * kp + derivative_x * kd) * AlgorithmConfig.PAN_DIRECTION
            step_tilt = (dy * kp + derivative_y * kd) * AlgorithmConfig.TILT_DIRECTION
            
            # ?? 3. ���������� (Clamping)��ÿ֡���ֻ�����ƶ� 5 ����λ
            max_v = 5.0 
            step_pan = max(-max_v, min(max_v, step_pan))
            step_tilt = max(-max_v, min(max_v, step_tilt))

            self.goal_pan -= step_pan
            self.goal_tilt -= step_tilt
            
            if self.state != "TRACKING":
                print(">> [Target Captured] 开始平滑锁定...")
                self.state = "TRACKING"
        else:
            self.state = "IDLE"
            # Ŀ�궪ʧʱ��������䣬��ֹ�´β�׽ʱ���ֵ���ͻ��
            self.last_dx = 0.0
            self.last_dy = 0.0

        # ?? 4. ��ǿ�����˲�������һ����Ӳ�Ķ���
        smooth = AlgorithmConfig.INPUT_SMOOTH_FACTOR
        self.present_pan = self.present_pan * smooth + self.goal_pan * (1 - smooth)
        self.present_tilt = self.present_tilt * smooth + self.goal_tilt * (1 - smooth)

        self.manual_sync_write({1: int(self.present_pan), 5: int(self.present_tilt)})