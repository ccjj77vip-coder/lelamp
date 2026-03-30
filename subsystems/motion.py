# -*- coding: utf-8 -*-
import time
import json
import os
import math
import random
import threading
from drivers.sts3215 import get_servo_driver
from config import ServoConfig

class MotionSystem:
    def __init__(self):
        self.driver = get_servo_driver()
        self.home_offset = {id: 2048 for id in ServoConfig.ALL_IDS}
        self.custom_poses = {}
        self._last_calib_mtime = 0 
        self._load_calibration()
        
        self.current_positions = {id: float(self.home_offset.get(id, 2048)) for id in ServoConfig.ALL_IDS}
        self.start_positions = self.current_positions.copy()
        self.target_positions = self.current_positions.copy()
        self.dob_filtered_positions = self.current_positions.copy()
        
        self.motion_start_time = time.time()
        self.motion_duration = 1.0
        self.streaming = False
        self.stream_thread = None
        self.torque_enabled = True 

    def _load_calibration(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        calib_path = os.path.join(base_dir, '..', 'calibration.json')
        if not os.path.exists(calib_path):
            calib_path = os.path.join(base_dir, 'calibration.json')
        if os.path.exists(calib_path):
            mtime = os.path.getmtime(calib_path)
            if self._last_calib_mtime == mtime: return
            self._last_calib_mtime = mtime
            try:
                with open(calib_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "HOME_OFFSET" in data:
                        self.home_offset = {int(k): v for k, v in data["HOME_OFFSET"].items()}
                    if "CUSTOM_POSES" in data:
                        self.custom_poses = {
                            name: {int(k): v for k, v in pose.items()} 
                            for name, pose in data["CUSTOM_POSES"].items()
                        }
            except: pass

    def _kinematic_engine_worker(self):
        dt = 0.02
        duration_ms = int(dt * 1000)
        while self.streaming:
            loop_start = time.time()
            if not getattr(self, 'torque_enabled', True):
                time.sleep(dt)
                continue
                
            frame = {}
            elapsed = time.time() - self.motion_start_time
            tau = 1.0 if self.motion_duration <= 0 else elapsed / self.motion_duration
            if tau > 1.0: tau = 1.0
            
            s_curve_scale = 0.5 - 0.5 * math.cos(math.pi * tau)
            
            for sid in ServoConfig.ALL_IDS:
                start_p = self.start_positions.get(sid, 2048.0)
                target_p = self.target_positions.get(sid, 2048.0)
                ideal_pos = start_p + (target_p - start_p) * s_curve_scale
                alpha = 0.85 
                smoothed_pos = alpha * ideal_pos + (1 - alpha) * self.dob_filtered_positions[sid]
                
                self.dob_filtered_positions[sid] = smoothed_pos
                self.current_positions[sid] = smoothed_pos
                frame[sid] = int(smoothed_pos)
                
            self.driver.sync_write_target(frame, duration_ms=duration_ms, acc=0)
            sleep_time = dt - (time.time() - loop_start)
            if sleep_time > 0: time.sleep(sleep_time)

    def free_torque(self):
        self.torque_enabled = False
        time.sleep(0.05) 
        for sid in ServoConfig.ALL_IDS:
            self.driver._write_packet(sid, 0x03, [0x28, 0]) 

    def enable_torque(self):
        for sid in ServoConfig.ALL_IDS:
            real_pos = self.driver.read_pos(sid)
            if real_pos != -1:
                self.current_positions[sid] = float(real_pos)
                self.start_positions[sid] = float(real_pos)
                self.target_positions[sid] = float(real_pos)
                self.dob_filtered_positions[sid] = float(real_pos)
        self.torque_enabled = True

    def start(self):
        self.driver.open()
        for sid in ServoConfig.ALL_IDS:
            real_pos = self.driver.read_pos(sid)
            if real_pos != -1: 
                self.current_positions[sid] = float(real_pos)
                self.start_positions[sid] = float(real_pos)
                self.target_positions[sid] = float(real_pos)
                self.dob_filtered_positions[sid] = float(real_pos)
                
        self.streaming = True
        self.stream_thread = threading.Thread(target=self._kinematic_engine_worker, daemon=True)
        self.stream_thread.start()

    def stop(self):
        self.streaming = False
        if self.stream_thread: self.stream_thread.join()
        self.driver.close()

    def move_to(self, target_dict, duration=None):
        self.start_positions = self.dob_filtered_positions.copy()
        max_diff = 0
        for sid, pos in target_dict.items():
            self.target_positions[sid] = float(pos)
            diff = abs(self.target_positions[sid] - self.start_positions.get(sid, 2048.0))
            if diff > max_diff: max_diff = diff
            
        if duration is None:
            calc_dur = max_diff / 600.0
            self.motion_duration = max(1.0, calc_dur)
        else:
            self.motion_duration = duration
        self.motion_start_time = time.time()

    def go_home(self, duration=None):
        self._load_calibration()
        self.move_to(self.home_offset, duration)

    def goto_pose(self, pose_name: str, duration=None):
        self._load_calibration()
        if pose_name in self.custom_poses:
            self.move_to(self.custom_poses[pose_name], duration)

    def look_at(self, yaw_angle: float, pitch_angle: float, duration=None):
        self._load_calibration()
        steps_per_degree = 4096 / 360.0
        target = self.target_positions.copy()
        target[1] = self.home_offset.get(1, 2048) + int(yaw_angle * steps_per_degree)
        target[2] = self.home_offset.get(2, 2048) + int(pitch_angle * steps_per_degree)
        self.move_to(target, duration)

    def nod(self):
        self._load_calibration()
        h = self.home_offset
        import random
        repeats = random.randint(2, 3)
        for _ in range(repeats):
            dur1 = 0.5 + random.uniform(0.0, 0.15)
            dur2 = 0.5 + random.uniform(0.0, 0.15)
            self.move_to({5: h.get(5, 2048) + 250}, duration=dur1)
            time.sleep(dur1)
            self.move_to({5: h.get(5, 2048) - 150}, duration=dur2)
            time.sleep(dur2)
        self.move_to(h, duration=0.8)
        time.sleep(0.8)

    def shake_head(self):
        self._load_calibration()
        h = self.home_offset
        import random
        repeats = random.randint(2, 3)
        for _ in range(repeats):
            dur1 = 0.5 + random.uniform(0.0, 0.15)
            dur2 = 0.5 + random.uniform(0.0, 0.15)
            self.move_to({4: h.get(4, 2048) + 300}, duration=dur1)
            time.sleep(dur1)
            self.move_to({4: h.get(4, 2048) - 300}, duration=dur2)
            time.sleep(dur2)
        self.move_to(h, duration=0.8)
        time.sleep(0.8)

    # =============== 舞 蹈 库 ===============

    def dance(self):
        """经典舞蹈 (约4秒)"""
        self._load_calibration()
        h = self.home_offset
        moves = [
            {1: h.get(1,2048)+500, 2: h.get(2,2048)-200, 3: h.get(3,2048)-150, 4: h.get(4,2048)+300, 5: h.get(5,2048)+200},
            {1: h.get(1,2048)-500, 2: h.get(2,2048)+150, 3: h.get(3,2048)+150, 4: h.get(4,2048)-300, 5: h.get(5,2048)-200},
            {1: h.get(1,2048), 2: h.get(2,2048)-400, 3: h.get(3,2048)-300, 4: h.get(4,2048)+150, 5: h.get(5,2048)-150},
            h
        ]
        for target in moves:
            self.move_to(target, duration=1.0)
            time.sleep(1.0)

    def dance_cute(self):
        """新增 1：可爱歪头杀 (约4秒)"""
        self._load_calibration()
        h = self.home_offset
        moves = [
            # 偏头卖萌
            {1: h.get(1,2048), 2: h.get(2,2048), 3: h.get(3,2048)+200, 4: h.get(4,2048)+400, 5: h.get(5,2048)-200},
            {1: h.get(1,2048), 2: h.get(2,2048), 3: h.get(3,2048)+200, 4: h.get(4,2048)-400, 5: h.get(5,2048)-200},
            # 小鸡啄米
            {1: h.get(1,2048), 2: h.get(2,2048)-150, 3: h.get(3,2048)-150, 4: h.get(4,2048), 5: h.get(5,2048)+300},
            {1: h.get(1,2048), 2: h.get(2,2048)-150, 3: h.get(3,2048)-150, 4: h.get(4,2048), 5: h.get(5,2048)-100},
            h
        ]
        for target in moves:
            self.move_to(target, duration=0.8)
            time.sleep(0.8)

    def dance_playful(self):
        """新增 2：俏皮摇摆 (约6秒)"""
        self._load_calibration()
        h = self.home_offset
        moves = [
            {1: h.get(1,2048)+400, 2: h.get(2,2048)-300, 3: h.get(3,2048)-200, 4: h.get(4,2048)+200, 5: h.get(5,2048)+100},
            {1: h.get(1,2048)-400, 2: h.get(2,2048)-300, 3: h.get(3,2048)-200, 4: h.get(4,2048)-200, 5: h.get(5,2048)+100},
            {1: h.get(1,2048), 2: h.get(2,2048)+300, 3: h.get(3,2048)+300, 4: h.get(4,2048), 5: h.get(5,2048)-300},
            h
        ]
        for _ in range(2): 
            for target in moves[:-1]:
                self.move_to(target, duration=0.8)
                time.sleep(0.8)
        self.move_to(h, duration=0.8)
        time.sleep(0.8)

    def dance_long(self):
        """新增 3：20秒压轴长舞 (分4个节奏小节)"""
        self._load_calibration()
        h = self.home_offset
        
        # 动作编排序列表 (共18个关键帧)
        sequence = [
            # 小节 1：苏醒与环顾 (舒缓起手)
            {1: h.get(1,2048)+500, 2: h.get(2,2048), 3: h.get(3,2048)-200, 4: h.get(4,2048)+300, 5: h.get(5,2048)-100},
            {1: h.get(1,2048)-500, 2: h.get(2,2048), 3: h.get(3,2048)-200, 4: h.get(4,2048)-300, 5: h.get(5,2048)-100},
            {1: h.get(1,2048), 2: h.get(2,2048)+200, 3: h.get(3,2048)+200, 4: h.get(4,2048), 5: h.get(5,2048)-300},
            {1: h.get(1,2048), 2: h.get(2,2048)-200, 3: h.get(3,2048)-200, 4: h.get(4,2048), 5: h.get(5,2048)+200},
            # 小节 2：快节奏摇头晃脑 (进入高潮)
            {1: h.get(1,2048)+300, 2: h.get(2,2048)-100, 3: h.get(3,2048)-100, 4: h.get(4,2048), 5: h.get(5,2048)+300},
            {1: h.get(1,2048)-300, 2: h.get(2,2048)-100, 3: h.get(3,2048)-100, 4: h.get(4,2048), 5: h.get(5,2048)-200},
            {1: h.get(1,2048)+300, 2: h.get(2,2048)-100, 3: h.get(3,2048)-100, 4: h.get(4,2048), 5: h.get(5,2048)+300},
            {1: h.get(1,2048)-300, 2: h.get(2,2048)-100, 3: h.get(3,2048)-100, 4: h.get(4,2048), 5: h.get(5,2048)-200},
            # 小节 3：画大圈 (大动态展示力矩)
            {1: h.get(1,2048)+600, 2: h.get(2,2048)+200, 3: h.get(3,2048)+200, 4: h.get(4,2048)-200, 5: h.get(5,2048)},
            {1: h.get(1,2048), 2: h.get(2,2048)-400, 3: h.get(3,2048)-300, 4: h.get(4,2048), 5: h.get(5,2048)+400},
            {1: h.get(1,2048)-600, 2: h.get(2,2048)+200, 3: h.get(3,2048)+200, 4: h.get(4,2048)+200, 5: h.get(5,2048)},
            {1: h.get(1,2048), 2: h.get(2,2048)-400, 3: h.get(3,2048)-300, 4: h.get(4,2048), 5: h.get(5,2048)+400},
            # 小节 4：俏皮波浪形
            {1: h.get(1,2048), 2: h.get(2,2048)+100, 3: h.get(3,2048)-400, 4: h.get(4,2048), 5: h.get(5,2048)+200},
            {1: h.get(1,2048), 2: h.get(2,2048)-300, 3: h.get(3,2048)+300, 4: h.get(4,2048), 5: h.get(5,2048)-300},
            {1: h.get(1,2048), 2: h.get(2,2048)+100, 3: h.get(3,2048)-400, 4: h.get(4,2048), 5: h.get(5,2048)+200},
            {1: h.get(1,2048), 2: h.get(2,2048)-300, 3: h.get(3,2048)+300, 4: h.get(4,2048), 5: h.get(5,2048)-300},
            # 谢幕：深深鞠躬
            {1: h.get(1,2048), 2: h.get(2,2048)-500, 3: h.get(3,2048)-400, 4: h.get(4,2048), 5: h.get(5,2048)+300},
            h
        ]
        
        # 变速播放引擎：根据小节情感自动匹配执行时长
        for i in range(0, 4): self.move_to(sequence[i], duration=1.2); time.sleep(1.2)   # 舒缓 (4.8s)
        for i in range(4, 8): self.move_to(sequence[i], duration=0.6); time.sleep(0.6)   # 快速 (2.4s)
        for i in range(8, 12): self.move_to(sequence[i], duration=1.2); time.sleep(1.2)  # 饱满 (4.8s)
        for i in range(12, 16): self.move_to(sequence[i], duration=0.8); time.sleep(0.8) # 灵动 (3.2s)
        for i in range(16, 18): self.move_to(sequence[i], duration=2.0); time.sleep(2.0) # 隆重谢幕 (4.0s)

    # =============== 录舞与回放 ===============

    def record_dance_frame(self):
        """捕捉当前舵机位置作为一帧，返回帧数据"""
        frame = {}
        for sid in ServoConfig.ALL_IDS:
            pos = self.driver.read_pos(sid)
            if pos != -1:
                frame[str(sid)] = pos
        return frame

    def save_dance(self, name, frames, tempo=0.5):
        """保存录制的舞蹈到 calibration.json"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        calib_path = os.path.join(base_dir, '..', 'calibration.json')
        try:
            with open(calib_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            data = {}

        if "CUSTOM_DANCES" not in data:
            data["CUSTOM_DANCES"] = {}

        data["CUSTOM_DANCES"][name] = {
            "frames": frames,
            "tempo": tempo
        }

        with open(calib_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def play_dance(self, name):
        """回放 calibration.json 中保存的自定义舞蹈"""
        self._load_calibration()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        calib_path = os.path.join(base_dir, '..', 'calibration.json')
        try:
            with open(calib_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            dance_data = data.get("CUSTOM_DANCES", {}).get(name)
            if not dance_data:
                return False
        except:
            return False

        frames = dance_data["frames"]
        tempo = dance_data.get("tempo", 0.5)

        for frame in frames:
            target = {int(k): v for k, v in frame.items()}
            self.move_to(target, duration=tempo)
            time.sleep(tempo)

        self.go_home(duration=1.0)
        time.sleep(1.0)
        return True

    def list_dances(self):
        """列出所有已录制的自定义舞蹈"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        calib_path = os.path.join(base_dir, '..', 'calibration.json')
        try:
            with open(calib_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            dances = data.get("CUSTOM_DANCES", {})
            return {name: len(d["frames"]) for name, d in dances.items()}
        except:
            return {}

    def delete_dance(self, name):
        """删除一个自定义舞蹈"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        calib_path = os.path.join(base_dir, '..', 'calibration.json')
        try:
            with open(calib_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if name in data.get("CUSTOM_DANCES", {}):
                del data["CUSTOM_DANCES"][name]
                with open(calib_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                return True
        except:
            pass
        return False

    # =============== 随机编排引擎 ===============

    def dance_random(self):
        """随机组合动作原语，每次都不重复"""
        self._load_calibration()
        h = self.home_offset

        # 动作原语库：每个原语是 (目标位置偏移, 时长, 名称)
        primitives = [
            # 左摇
            lambda: ({1: h.get(1,2048)+500, 4: h.get(4,2048)+200}, 0.7),
            # 右摇
            lambda: ({1: h.get(1,2048)-500, 4: h.get(4,2048)-200}, 0.7),
            # 前倾点头
            lambda: ({2: h.get(2,2048)-300, 3: h.get(3,2048)-200, 5: h.get(5,2048)+250}, 0.6),
            # 后仰
            lambda: ({2: h.get(2,2048)+200, 3: h.get(3,2048)+200, 5: h.get(5,2048)-200}, 0.8),
            # 歪头左
            lambda: ({3: h.get(3,2048)+250, 4: h.get(4,2048)+400, 5: h.get(5,2048)-150}, 0.6),
            # 歪头右
            lambda: ({3: h.get(3,2048)+250, 4: h.get(4,2048)-400, 5: h.get(5,2048)-150}, 0.6),
            # 画圈左
            lambda: ({1: h.get(1,2048)+400, 2: h.get(2,2048)-300, 3: h.get(3,2048)-200}, 1.0),
            # 画圈右
            lambda: ({1: h.get(1,2048)-400, 2: h.get(2,2048)-300, 3: h.get(3,2048)-200}, 1.0),
            # 快速摇头
            lambda: ({4: h.get(4,2048)+350}, 0.3),
            # 快速摇头反向
            lambda: ({4: h.get(4,2048)-350}, 0.3),
            # 啄米
            lambda: ({5: h.get(5,2048)+300}, 0.4),
            # 抬头
            lambda: ({5: h.get(5,2048)-300}, 0.4),
            # 扭腰左
            lambda: ({1: h.get(1,2048)+300, 3: h.get(3,2048)-300}, 0.8),
            # 扭腰右
            lambda: ({1: h.get(1,2048)-300, 3: h.get(3,2048)-300}, 0.8),
            # 鞠躬
            lambda: ({2: h.get(2,2048)-500, 3: h.get(3,2048)-400, 5: h.get(5,2048)+300}, 1.2),
        ]

        # 随机选 6~10 个动作
        count = random.randint(6, 10)
        selected = random.choices(primitives, k=count)

        for prim_fn in selected:
            target, dur = prim_fn()
            # 随机微调时长 ±20%
            dur *= random.uniform(0.8, 1.2)
            self.move_to(target, duration=dur)
            time.sleep(dur)

        # 回家
        self.go_home(duration=1.0)
        time.sleep(1.0)

_motion_instance = None
def get_motion_system():
    global _motion_instance
    if _motion_instance is None: _motion_instance = MotionSystem()
    return _motion_instance