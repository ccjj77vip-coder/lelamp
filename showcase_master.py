# -*- coding: utf-8 -*-
import threading
import sys
import os
import glob
import logging

# 🌟 核心引擎：内存级重写 time.sleep，瞬间打断原装长动作！
import time
_real_sleep = time.sleep
class SceneInterruptedException(Exception): pass
_global_master = None

def _smart_sleep(duration):
    start = time.time()
    while time.time() - start < duration:
        if _global_master and getattr(_global_master, 'cancel_flag', False):
            if threading.current_thread() == getattr(_global_master, 'current_thread', None):
                raise SceneInterruptedException()
        _real_sleep(min(0.05, duration - (time.time() - start)))
time.sleep = _smart_sleep

from flask import Flask, Response, render_template_string, send_file, request

from subsystems.motion import get_motion_system
from subsystems.led import get_led_engine
from subsystems.voice import get_voice_system
from subsystems.llm import get_llm_engine
from subsystems.camera import get_camera_system

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>诸葛亮 - 军机阁调度中心</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: monospace; text-align: center; margin: 0; padding: 20px; }
        h1 { color: #58a6ff; text-shadow: 0 0 10px rgba(88,166,255,0.5); }
        .container { display: flex; justify-content: center; gap: 40px; margin-top: 30px; flex-wrap: wrap; }
        .panel { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); width: 640px;}
        .panel h2 { margin-top: 0; color: #8b949e; font-size: 1.2em; }
        img { max-width: 100%; height: auto; border-radius: 5px; border: 1px solid #21262d; width: 100%; height: 360px; object-fit: cover; background: #000; }
        .slider-container { margin-top: 20px; display: flex; align-items: center; justify-content: center; gap: 15px; background: #0d1117; padding: 15px; border-radius: 8px; border: 1px solid #21262d; }
        input[type=range] { width: 70%; cursor: pointer; accent-color: #58a6ff; height: 8px; }
        #volText { width: 60px; font-weight: bold; color: #58a6ff; font-size: 1.2em; }
        .btn-group { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-top: 15px; }
        button { background-color: #238636; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 1.1em; font-family: monospace; transition: 0.2s; }
        button:hover { filter: brightness(1.2); }
        .stop-btn { background-color: #da3633; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🚀 诸葛亮 - 军机阁调度中心</h1>
    <div class="container">
        <div class="panel">
            <h2>🎬 剧本进程场控 (Scene Control)</h2>
            <div class="btn-group">
                <button onclick="updateScene('1')">🗣️ 1. 军机问答</button>
                <button onclick="updateScene('2')">💃 2. 阵法演练</button>
                <button onclick="updateScene('3')">👁️ 3. 天眼探察</button>
                <button class="stop-btn" onclick="updateScene('Q')">🛑 强行终止</button>
            </div>
        </div>
        <div class="panel">
            <h2>🔊 全局阵列音量控制 (Master Volume)</h2>
            <div class="slider-container">
                <span style="font-size: 1.5em;">🔈</span>
                <input type="range" id="volSlider" min="0" max="100" step="5" value="100" oninput="updateVol(this.value)">
                <span id="volText">100%</span>
            </div>
        </div>
    </div>
    <div class="container">
        <div class="panel">
            <h2>🔴 实时视觉雷达 (Live Feed)</h2>
            <img src="/video_feed" alt="Camera Feed">
        </div>
        <div class="panel">
            <h2>📸 最新多模态切片 (Latest Snapshot)</h2>
            <img id="latest-photo" src="/latest_photo" alt="Latest Photo" onerror="this.src=''">
        </div>
    </div>
    <script>
        setInterval(() => {
            const photoImg = document.getElementById('latest-photo');
            photoImg.src = '/latest_photo?t=' + new Date().getTime();
        }, 2000);

        let volTimeout;
        function updateVol(val) {
            document.getElementById('volText').innerText = val + '%';
            clearTimeout(volTimeout);
            volTimeout = setTimeout(() => { fetch('/set_volume?val=' + val).catch(e => console.error(e)); }, 80); 
        }
        function updateScene(val) {
            fetch('/trigger_scene?id=' + val).catch(e => console.error(e));
        }
    </script>
</body>
</html>
"""

def gen_frames():
    cam = get_camera_system()
    while True:
        frame_bytes = cam.get_frame_bytes()
        if frame_bytes: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else: time.sleep(0.1)
        time.sleep(0.05) 

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)
@app.route('/video_feed')
def video_feed(): return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
@app.route('/latest_photo')
def latest_photo():
    photo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
    try:
        latest_file = max(glob.glob(os.path.join(photo_dir, '*.jpg')), key=os.path.getctime)
        return send_file(latest_file, mimetype='image/jpeg')
    except: return "Not Found", 404

@app.route('/set_volume')
def set_volume_api():
    vol = request.args.get('val', default=100, type=int)
    get_voice_system().set_volume(vol)
    return "OK", 200

@app.route('/trigger_scene')
def trigger_scene_api():
    scene_id = request.args.get('id', default='Q', type=str)
    if _global_master: _global_master.trigger_scene(scene_id)
    return "OK", 200

def run_flask_server():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

class LebaoShowcase:
    def __init__(self):
        global _global_master
        _global_master = self
        self.motion = get_motion_system()
        self.led = get_led_engine()
        self.voice = get_voice_system()
        self.llm = get_llm_engine()
        self.camera = get_camera_system()
        self.voice.set_volume(100)
        from zhipuai import ZhipuAI
        self.vision_client = ZhipuAI(api_key=os.environ.get("ZHIPU_API_KEY", ""))
        self.cancel_flag = False
        self.current_thread = None

    def trigger_scene(self, cmd):
        print(f"\n[WEB COMMAND] 收到网页强切指令：[{cmd}]")
        self.stop_current_scene()
        
        # 🌟 核心防串台机制：等待 0.5 秒，让上一轮的语音识别彻底看到 cancel_flag 并销毁自己
        time.sleep(0.5) 
        self.cancel_flag = False 
        
        if cmd == '1': self.current_thread = threading.Thread(target=self._run_with_catch, args=(self.scene_1_interaction,))
        elif cmd == '2': self.current_thread = threading.Thread(target=self._run_with_catch, args=(self.scene_2_motion,))
        elif cmd == '3': self.current_thread = threading.Thread(target=self._run_with_catch, args=(self.scene_3_vision,))
        elif cmd == 'Q': return
        
        if cmd in ['1', '2', '3']:
            self.current_thread.daemon = True
            self.current_thread.start()

    def _run_with_catch(self, func):
        try: func()
        except SceneInterruptedException: print(f"🛑 [系统保护] {func.__name__} 进程已被安全切断释放！")

    def stop_current_scene(self):
        self.cancel_flag = True
        os.system("killall -9 mpg123 >/dev/null 2>&1")
        os.system("killall -9 arecord >/dev/null 2>&1")
        
    def scene_1_interaction(self):
        self.led.set_effect("solid_blue")
        goto_next_scene = False
        self.motion.move_to({1:2048, 2:2048, 3:2200, 4:2400, 5:1950}, duration=2.0)
        self.voice.speak("主公，亮已就位。今日有何军机要务，请尽情考较。")
        for turn in range(4):
            if self.cancel_flag: return
            self.motion.move_to({1:2048, 2:2048, 3:2200, 4:2400, 5:1950}, duration=2.0)
            self.led.set_effect("breathe_green")
            user_input = self.voice.listen()
            if self.cancel_flag: return
            self.motion.go_home(duration=2.0)
            if not user_input or len(user_input.strip()) == 0:
                self.voice.speak("风声喧嚣，亮未听清主公所言，可否再述一遍？")
                continue
            next_words = ["下一", "第二", "跳舞", "展示", "看点别的", "动作"]
            exit_words = ["结束", "退下", "再见", "休息", "闭嘴"]
            if any(w in user_input for w in next_words):
                self.led.set_effect("rainbow")
                self.voice.speak("好嘞，亮这就为主公展示一番机关奇门之术！")
                goto_next_scene = True
                break
            elif any(w in user_input for w in exit_words):
                self.led.set_effect("warm_lamp")
                self.voice.speak("机关闭锁，亮暂且歇息。")
                break
            self.led.set_effect("spin_orange")
            reply = self.llm.chat(user_input)
            if self.cancel_flag: return
            self.led.set_effect("solid_blue")
            self.voice.speak(reply)
            self.motion.nod()
        if not self.cancel_flag:
            if goto_next_scene: self.scene_2_motion()
            else: self.motion.go_home(duration=1.0)

    def scene_2_motion(self):
        self.led.set_effect("rainbow")
        self.voice.speak("请主公检阅这套天机连环阵法！")
        
        # 🌟 诸葛亮专属平缓阵法编排
        h = self.motion.home_offset
        part1 = [
            ({"dur": 1.2}, {1: h.get(1,2048)+200, 2: h.get(2,2048)-100, 3: h.get(3,2048)-100, 4: h.get(4,2048)+150, 5: h.get(5,2048)}), 
            ({"dur": 1.5}, {1: h.get(1,2048)-150, 2: h.get(2,2048), 3: h.get(3,2048)+100, 4: h.get(4,2048)-100, 5: h.get(5,2048)}),   
        ]
        part2 = [
            ({"dur": 1.0}, {1: h.get(1,2048)-200, 2: h.get(2,2048)-150, 3: h.get(3,2048)-150, 4: h.get(4,2048), 5: h.get(5,2048)+150}), 
            ({"dur": 1.0}, {1: h.get(1,2048)+200, 2: h.get(2,2048)-150, 3: h.get(3,2048)-150, 4: h.get(4,2048), 5: h.get(5,2048)-150}), 
        ]
        part3 = [
            ({"dur": 1.5}, {1: h.get(1,2048), 2: h.get(2,2048)+200, 3: h.get(3,2048)+150, 4: h.get(4,2048)-50, 5: h.get(5,2048)}), 
            ({"dur": 1.2}, h) 
        ]
        cyber_moves = part1 + part2 * 2 + part3
        
        for meta, target in cyber_moves:
            if self.cancel_flag: return
            self.motion.move_to(target, duration=meta["dur"])
            time.sleep(meta["dur"])
            
        if self.cancel_flag: return
        self.led.set_effect("warm_lamp")
        self.voice.speak("阵法演练完毕！主公可通过语音让我点头、摇头，以示军威！")
        
        goto_next_scene = False
        while True:
            if self.cancel_flag: return
            self.led.set_effect("breathe_green")
            cmd = self.voice.listen()
            if self.cancel_flag: return
            if not cmd: continue
            if any(w in cmd for w in ["不要", "下一", "够了", "照相", "拍照", "第三"]):
                self.voice.speak("遵命，这就进入奇门遁甲的视觉探察环节！")
                goto_next_scene = True
                break
            if any(w in cmd for w in ["结束", "停", "退下"]):
                self.voice.speak("机关闭锁，亮暂且歇息。")
                break
            action_done = False
            if ("点" in cmd and "头" in cmd) or "赞同" in cmd:
                self.led.set_effect("solid_blue"); self.motion.nod(); action_done = True
            elif ("摇" in cmd and "头" in cmd) or "否定" in cmd:
                self.led.set_effect("solid_blue"); self.motion.shake_head(); action_done = True
            elif "舞" in cmd or "跳" in cmd or "动" in cmd:
                self.led.set_effect("rainbow"); self.motion.dance_playful(); action_done = True
            if action_done:
                if self.cancel_flag: return
                self.voice.speak("遵令！主公还要继续检阅吗？")
        if not self.cancel_flag:
            if goto_next_scene: self.scene_3_vision()
            else: self.motion.go_home(duration=1.0)

    def scene_3_vision(self):
        os.system("killall -9 arecord >/dev/null 2>&1")
        self.motion.go_home(duration=0.6)
        self.voice.speak("诸位且慢，待亮以此天眼观天地之气象！")
        self.led.set_effect("blink_red")
        for _ in range(15):
            if self.cancel_flag: return
            time.sleep(0.1)
        self.led.set_effect("solid_white")
        self.camera.take_photo()
        time.sleep(0.5)
        if self.cancel_flag: return
        self.led.set_effect("spin_orange")
        self.voice.speak("八卦罗盘正在推演，请主公稍候...")
        try:
            photo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
            latest_file = max(glob.glob(os.path.join(photo_dir, '*.jpg')), key=os.path.getctime)
            import base64
            with open(latest_file, "rb") as f: img_b64 = base64.b64encode(f.read()).decode('utf-8')
            if self.cancel_flag: return
            vision_prompt = """请化身为三国时期的神机妙算的军师诸葛亮，仔细观察照片！用沉稳、睿智口吻，汇报人物表情、动作、衣着颜色，以及周围陈设。字数120字内。"""
            res = self.vision_client.chat.completions.create(
                model="glm-4v", 
                messages=[{"role":"user", "content":[{"type":"text", "text": vision_prompt},{"type":"image_url", "image_url":{"url":f"data:image/jpeg;base64,{img_b64}"}}]}],
                timeout=25.0 
            )
            if self.cancel_flag: return
            self.led.set_effect("breathe_green")
            self.voice.speak(res.choices[0].message.content)
        except Exception:
            if not self.cancel_flag: self.voice.speak("主公恕罪，方才灵气阻滞，未能看清，但想必皆是人中龙凤。")
        if not self.cancel_flag: self.motion.go_home(duration=1.0)

    def run(self):
        self.motion.start()
        self.led.start()
        self.voice.start()
        threading.Thread(target=run_flask_server, daemon=True).start()
        self.motion.go_home()
        self.led.set_effect("warm_lamp")
        print("\n" + "*"*45)
        print("  [诸葛亮专属] LELAMP 军机阁控制台已在线！")
        print("  [WEB] 请在网页端操控进程，按 Ctrl+C 退出此终端")
        print("*"*45)
        try:
            while True: time.sleep(10)
        except KeyboardInterrupt:
            self.stop_current_scene()
            self.motion.stop()
            self.led.stop()
            time.sleep(0.1)
            try:
                if hasattr(self.led, 'set_effect'): self.led.set_effect("off")
            except: pass
            self.voice.stop()
            os._exit(0)

if __name__ == "__main__":
    master = LebaoShowcase()
    master.run()
