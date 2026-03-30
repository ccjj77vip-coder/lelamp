# -*- coding: utf-8 -*-
import serial
import time
import threading

class STS3215Driver:
    def __init__(self, port: str, baudrate: int = 1000000, timeout: float = 0.05):
        self.port_name = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self._lock = threading.Lock()
        self.connected = False

    def open(self):
        if self.connected: return
        try:
            self.serial = serial.Serial(self.port_name, self.baudrate, timeout=self.timeout)
            self.connected = True
        except Exception as e:
            self.connected = False
            print(f"?? 串口打开失败: {e}")

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connected = False

    def _calc_checksum(self, data_list):
        return (~sum(data_list)) & 0xFF

    def _write_packet(self, servo_id, instruction, params):
        if not self.connected: return
        length = len(params) + 2
        packet = [0xFF, 0xFF, servo_id, length, instruction] + params
        packet.append(self._calc_checksum(packet[2:]))
        with self._lock:
            try: self.serial.write(bytes(packet))
            except: pass

    # =========================================================
    # ?? 已修复：兼容 motion.py 传来的 acc_dict (加速度字典)
    # =========================================================
    def sync_write_target(self, target_data: dict, duration_ms: int = 0, acc = 0):
        if not self.connected: return
        duration_ms = max(0, min(32767, int(duration_ms)))
        
        # 判断传入的 acc 是字典还是单个整数
        is_acc_dict = isinstance(acc, dict)
        default_acc = 0 if is_acc_dict else max(0, min(254, int(acc)))
        
        addr = 0x29 
        len_per_servo = 7  
        params = [addr, len_per_servo]

        for sid, pos in target_data.items():
            pos = max(0, min(4096, int(pos)))
            p_L, p_H = pos & 0xFF, (pos >> 8) & 0xFF
            t_L, t_H = duration_ms & 0xFF, (duration_ms >> 8) & 0xFF
            
            # 如果是字典，获取对应 ID 的加速度，否则使用默认值
            if is_acc_dict:
                servo_acc = max(0, min(254, int(acc.get(sid, 0))))
            else:
                servo_acc = default_acc
                
            params.extend([sid, servo_acc, p_L, p_H, t_L, t_H, 0, 0])

        length = len(params) + 2
        packet = [0xFF, 0xFF, 0xFE, length, 0x83] + params
        packet.append(self._calc_checksum(packet[2:]))

        with self._lock:
            try: self.serial.write(bytes(packet))
            except: pass

    def sync_write_pos(self, servo_data_dict: dict, speed: int = 0, acc: int = 0):
        self.sync_write_target(servo_data_dict, speed, acc)

    def write_pos(self, servo_id: int, position: int, speed: int = 0, acc: int = 0):
        position = max(0, min(4096, position))
        speed = max(0, min(3400, speed))
        pos_L, pos_H = position & 0xFF, (position >> 8) & 0xFF
        spd_L, spd_H = speed & 0xFF, (speed >> 8) & 0xFF
        self._write_packet(servo_id, 0x03, [0x2A, pos_L, pos_H, spd_L, spd_H, acc])

    def read_pos(self, servo_id: int) -> int:
        for _ in range(2):
            with self._lock:
                try:
                    self.serial.reset_input_buffer()
                    params = [0x38, 0x02]
                    length = len(params) + 2
                    packet = [0xFF, 0xFF, servo_id, length, 0x02] + params
                    packet.append(self._calc_checksum(packet[2:]))
                    self.serial.write(bytes(packet))
                    time.sleep(0.002)
                    data = self.serial.read(8)
                    if len(data) == 8 and data[0]==0xFF and data[1]==0xFF:
                        return data[5] + (data[6] << 8)
                except: pass
            time.sleep(0.01)
        return -1

_driver_instance = None
def get_servo_driver():
    global _driver_instance
    if _driver_instance is None:
        import sys, os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import HardwareConfig
        _driver_instance = STS3215Driver(HardwareConfig.SERVO_PORT, HardwareConfig.SERVO_BAUDRATE)
    return _driver_instance