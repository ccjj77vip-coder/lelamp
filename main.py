# -*- coding: utf-8 -*-
import time
import random
import threading
import os
import glob
import base64
from zhipuai import ZhipuAI
from subsystems.motion import get_motion_system
from subsystems.led import get_led_engine
from subsystems.voice import get_voice_system
from subsystems.llm import get_llm_engine
from subsystems.intent_engine import get_intent_engine
from subsystems.camera import get_camera_system
from subsystems.persona import get_persona_manager
import web_dashboard

class LeLampBrain:
    def __init__(self):
        self.motion = get_motion_system()
        self.led = get_led_engine()
        self.voice = get_voice_system()
        self.llm = get_llm_engine()
        self.intent_engine = get_intent_engine()
        self.camera = get_camera_system()
        self.persona = get_persona_manager()
        self.running = False
        self.custom_thinking_pose = None

        # 语音交互状态 (由网页端触发)
        self._voice_trigger = threading.Event()
        self._voice_stop = threading.Event()   # 停止信号
        self._voice_busy = False
        self._chat_log = []       # [{role: "user"/"ai", text: "...", ts: 1234}]
        self._chat_lock = threading.Lock()
        self._status = "idle"     # idle / listening / thinking / speaking

        # 视觉大模型
        self.vision_client = ZhipuAI(api_key=os.environ.get("ZHIPU_API_KEY", ""))

    def start_all_subsystems(self):
        self.motion.start()
        self.led.start()
        self.voice.start()

    def _add_chat(self, role, text):
        with self._chat_lock:
            self._chat_log.append({"role": role, "text": text, "ts": time.time()})
            # 最多保留 50 条
            if len(self._chat_log) > 50:
                self._chat_log = self._chat_log[-50:]

    def get_chat_log(self):
        with self._chat_lock:
            return list(self._chat_log)

    def get_status(self):
        return self._status

    def trigger_voice(self):
        """网页端调用，开启持续语音交互"""
        if self._voice_busy:
            return False
        self._voice_stop.clear()
        self._voice_trigger.set()
        return True

    def stop_voice(self):
        """网页端调用，停止语音交互"""
        self._voice_stop.set()

    def _analyze_latest_photo(self):
        """后台静默提取最新照片并发送给视觉大模型"""
        try:
            photo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
            list_of_files = glob.glob(os.path.join(photo_dir, '*.jpg'))
            if not list_of_files:
                return "哎呀，照片好像没存下来，我什么都没看到。"

            latest_file = max(list_of_files, key=os.path.getctime)
            with open(latest_file, "rb") as f:
                base64_img = base64.b64encode(f.read()).decode('utf-8')

            response = self.vision_client.chat.completions.create(
                model="glm-4v-flash",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.persona.current.get("vision_prompt", "用简短幽默的口吻点评这张照片，40字以内。")},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]
                }]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[视觉报错] {e}")
            return "哎呀，我的视觉处理芯片走神了，没看清拍了什么。"

    def _safe_speak(self, text):
        """TTS 安全包装 — 失败不阻塞流程"""
        try:
            self.voice.speak(text)
        except Exception as e:
            print(f"[TTS失败] {e}")

    def _do_one_voice_round(self):
        """持续语音交互循环 — 直到网页端点击停止或用户说退下"""
        self._voice_busy = True
        empty_count = 0  # 连续没听到声音的次数
        try:
            # 唤醒反馈
            self._status = "speaking"
            self.led.set_effect("speaking")
            h = self.motion.home_offset
            self.motion.move_to({
                1: h.get(1, 2048),
                2: h.get(2, 2048),
                3: h.get(3, 2048) + 150,
                4: h.get(4, 2048) + 350,
                5: h.get(5, 2048) - 100
            }, duration=0.5)
            greeting = random.choice(["我在！", "怎么啦？", "有什么吩咐？"])
            self._add_chat("ai", greeting)
            self._safe_speak(greeting)

            # === 持续对话循环 ===
            while not self._voice_stop.is_set():
                # 听
                self._status = "listening"
                self.led.set_effect("listening")
                user_text = self.voice.listen()

                if self._voice_stop.is_set():
                    break

                if not user_text:
                    empty_count += 1
                    if empty_count >= 3:
                        self._add_chat("ai", "(连续没听到声音，对话结束)")
                        break
                    continue

                empty_count = 0
                self._add_chat("user", user_text)

                # 意图识别
                raw_action = self.intent_engine.predict(user_text)
                action = raw_action.strip("<>") if isinstance(raw_action, str) else raw_action

                # 休眠指令 → 退出循环
                if action == "SLEEP" or any(w in user_text for w in ["退下", "休息", "再见", "拜拜"]):
                    reply = random.choice(["好的，那我先休息啦~", "拜拜！需要我的时候再叫我哦~"])
                    self._add_chat("ai", reply)
                    self._status = "speaking"
                    self.led.set_effect("speaking")
                    self._safe_speak(reply)
                    break

                # 拍照指令
                if action == "PHOTO":
                    self._status = "speaking"
                    self.led.set_effect("speaking")
                    reply1 = "看镜头，准备拍照！"
                    self._add_chat("ai", reply1)
                    self._safe_speak(reply1)
                    self.motion.go_home(duration=0.5)
                    time.sleep(0.5)

                    self.led.set_effect("solid_white")
                    time.sleep(0.3)
                    self.camera.take_photo()
                    self.led.set_effect("success")
                    time.sleep(0.5)

                    reply2 = "咔嚓！让我仔细看看拍得怎么样。"
                    self._add_chat("ai", reply2)
                    self._safe_speak(reply2)

                    self._status = "thinking"
                    self.led.set_effect("thinking")
                    if self.custom_thinking_pose:
                        self.motion.move_to(self.custom_thinking_pose, duration=0.8)
                    else:
                        self.motion.goto_pose("THINKING", duration=0.8)

                    vlm_reply = self._analyze_latest_photo()
                    self._add_chat("ai", vlm_reply)

                    self._status = "speaking"
                    self.led.set_effect("speaking")
                    speak_thread = threading.Thread(target=self._safe_speak, args=(vlm_reply,))
                    speak_thread.start()
                    self.motion.nod()
                    speak_thread.join()
                    self.motion.go_home(duration=1.0)
                    continue

                # 有动作
                if action:
                    ai_reply = "好嘞！"
                else:
                    # LLM 思考
                    self._status = "thinking"
                    self.led.set_effect("thinking")
                    if self.custom_thinking_pose:
                        self.motion.move_to(self.custom_thinking_pose, duration=0.8)
                    else:
                        self.motion.goto_pose("THINKING", duration=0.8)
                    try:
                        ai_reply = self.llm.chat(user_text)
                    except Exception as e:
                        print(f"[LLM失败] {e}")
                        ai_reply = "抱歉，我的思考通道刚出了点问题。"

                self._add_chat("ai", ai_reply)

                # 说 + 动
                self._status = "speaking"
                self.led.set_effect("speaking")
                speak_thread = threading.Thread(target=self._safe_speak, args=(ai_reply,))
                speak_thread.start()

                if action:
                    if action == "NOD":
                        self.motion.nod()
                    elif action == "DANCE":
                        self.led.set_effect("rainbow")
                        self.motion.dance()
                    elif action == "SHAKE":
                        self.motion.shake_head()
                    else:
                        self.motion.goto_pose(action)
                        time.sleep(2.5)

                speak_thread.join()
                self.motion.go_home(duration=1.0)

        except Exception as e:
            print(f"[语音交互异常] {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._voice_busy = False
            self._voice_stop.clear()
            self._status = "idle"
            self.led.set_effect("warm_lamp")
            self.motion.go_home(duration=1.0)

    def run(self):
        self.running = True
        self.start_all_subsystems()

        # 启动网页服务 (后台线程)
        web_thread = threading.Thread(target=web_dashboard.run_server, args=(self,), daemon=True)
        web_thread.start()

        # 启动后立刻回到 HOME 并打招呼
        self.motion.go_home(duration=2.0)
        self.led.set_effect("warm_lamp")
        time.sleep(0.5)
        startup_greet = random.choice(["主人你好呀，我上线啦！", "嗨！我准备好啦！", "你好！今天也要元气满满哦！"])
        self._safe_speak(startup_greet)
        self.motion.nod()

        print("\n" + "="*50)
        print("  LeLamp 上线！")
        print("  网页控制台: http://树莓派IP:5000")
        print("  点击网页上的 [开始对话] 即可语音交互")
        print("="*50 + "\n")

        try:
            while self.running:
                # 等待网页端触发语音交互
                triggered = self._voice_trigger.wait(timeout=0.5)
                if triggered:
                    self._voice_trigger.clear()
                    self._do_one_voice_round()
        except KeyboardInterrupt:
            pass
        finally:
            self.motion.stop()


if __name__ == '__main__':
    import json

    # ============ 硬件自检 ============
    def hardware_selftest():
        results = {}

        # 1. 舵机串口
        try:
            from drivers.sts3215 import get_servo_driver
            from config import HardwareConfig, ServoConfig
            drv = get_servo_driver()
            drv.open()
            if drv.connected:
                results['servo_port'] = ('OK', HardwareConfig.SERVO_PORT)
                for sid in ServoConfig.ALL_IDS:
                    pos = drv.read_pos(sid)
                    if pos != -1:
                        results[f'servo_{sid}'] = ('OK', f'pos={pos}')
                    else:
                        results[f'servo_{sid}'] = ('FAIL', 'no response')
            else:
                results['servo_port'] = ('FAIL', HardwareConfig.SERVO_PORT)
        except Exception as e:
            results['servo_port'] = ('FAIL', str(e))

        # 2. 摄像头
        try:
            import cv2
            from config import HardwareConfig
            cap = cv2.VideoCapture(HardwareConfig.CAMERA_ID)
            if cap.isOpened():
                ret, _ = cap.read()
                cap.release()
                results['camera'] = ('OK', f'id={HardwareConfig.CAMERA_ID}') if ret else ('FAIL', 'cannot read frame')
            else:
                results['camera'] = ('FAIL', f'cannot open id={HardwareConfig.CAMERA_ID}')
        except Exception as e:
            results['camera'] = ('FAIL', str(e))

        # 3. LED (NeoPixel)
        try:
            import board
            import neopixel
            results['led'] = ('OK', 'neopixel on GPIO10')
        except ImportError:
            results['led'] = ('FAIL', 'neopixel/RPi.GPIO not found')
        except Exception as e:
            results['led'] = ('FAIL', str(e))

        # 4. 音频设备
        from subsystems.hardware_check import auto_configure_audio
        try:
            mic_hw, spk_hw = auto_configure_audio()
            results['mic'] = ('OK', mic_hw)
            results['speaker'] = ('OK', spk_hw)
        except Exception as e:
            results['mic'] = ('FAIL', str(e))
            results['speaker'] = ('FAIL', str(e))

        # 打印报告
        print("\n" + "="*50)
        print("  [硬件自检报告]")
        print("="*50)
        all_ok = True
        for name, (status, detail) in results.items():
            icon = "OK" if status == 'OK' else "FAIL"
            print(f"  [{icon:4s}] {name:12s} {detail}")
            if status != 'OK':
                all_ok = False
        print("="*50)
        if all_ok:
            print("  全部硬件就绪")
        else:
            print("  部分硬件异常，请检查接线")
        print("="*50 + "\n")

        # 将检测到的硬件端口写入 calibration.json
        calib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calibration.json')
        try:
            with open(calib_path, 'r') as f:
                calib_data = json.load(f)
        except:
            calib_data = {}

        hw_info = {}
        if 'mic' in results and results['mic'][0] == 'OK':
            hw_info['mic'] = results['mic'][1]
        if 'speaker' in results and results['speaker'][0] == 'OK':
            hw_info['speaker'] = results['speaker'][1]
        if hw_info:
            calib_data['HARDWARE'] = hw_info
            with open(calib_path, 'w') as f:
                json.dump(calib_data, f, indent=4)
            print(f"  [自检] 硬件端口已写入 calibration.json")

        return results

    hw = hardware_selftest()

    # ============ 首次部署检测 ============
    calib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calibration.json')
    needs_calibration = True
    if os.path.exists(calib_path):
        try:
            with open(calib_path, 'r') as f:
                data = json.load(f)
            if data.get("HOME_OFFSET") and len(data["HOME_OFFSET"]) >= 5:
                needs_calibration = False
        except:
            pass

    if needs_calibration:
        print("  [首次部署] 检测到未校准的新机器")
        print("  舵机已卸力，请通过网页完成校准")
        print("  网页地址: http://树莓派IP:5000")
        print("  校准步骤:")
        print("    1. 用手将台灯调整到理想的HOME位置")
        print("    2. 网页点击 [保存为HOME零点]")
        print("    3. 录入其他自定义动作 (可选)")
        print("    4. 校准完成后重启容器即可正常运行")
        print("="*50 + "\n")

        from subsystems.motion import get_motion_system
        from subsystems.led import get_led_engine
        from subsystems.camera import get_camera_system

        class CalibrationBrain:
            def __init__(self):
                self.motion = get_motion_system()
                self.led = get_led_engine()
                self.camera = get_camera_system()
                self.custom_thinking_pose = None
                self.motion.start()
                self.led.start()
                self.motion.free_torque()
                self.led.set_effect("warm_lamp")

        brain = CalibrationBrain()
        web_dashboard.run_server(brain)
    else:
        brain = LeLampBrain()
        brain.run()
