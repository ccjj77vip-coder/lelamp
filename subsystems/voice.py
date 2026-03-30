# -*- coding: utf-8 -*-
"""
语音系统 — 火山引擎 (Volcengine) TTS/ASR (Bearer Token 认证)
- ASR: HTTP REST (一次性上传, 低延迟) + VAD 静音截断
- TTS: HTTP REST → mp3 → mpg123 流式播放
"""
import threading
import time
import os
import json
import subprocess
import math
import struct
import uuid
import base64
import hashlib
import hmac
import datetime
import requests

# VAD 参数
VAD_SILENCE_THRESHOLD = 200      # 降低门限，更灵敏
VAD_SILENCE_DURATION = 1.0
VAD_MIN_SPEECH_DURATION = 0.3

# ============ 火山引擎配置 (从环境变量读取) ============
VOLC_APP_ID = os.environ.get("VOLC_APP_ID", "")
VOLC_ACCESS_TOKEN = os.environ.get("VOLC_ACCESS_TOKEN", "")
VOLC_AK_ID = os.environ.get("VOLC_AK_ID", "")
VOLC_AK_SECRET = os.environ.get("VOLC_AK_SECRET", "")
VOLC_TTS_CLUSTER = "volcano_tts"
VOLC_ASR_CLUSTER = "volcengine_input_common"

# 端点
VOLC_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"
VOLC_ASR_URL = "https://openspeech.bytedance.com/api/v1/asr"


# ============ openspeech HMAC256 签名 ============
def _openspeech_auth_header(method, url, body_str):
    """生成 openspeech Bearer 或 HMAC256 认证头"""
    from urllib.parse import urlparse

    # 优先用 Bearer token（最简单最可靠）
    if VOLC_ACCESS_TOKEN:
        return {
            'Authorization': f'Bearer;{VOLC_ACCESS_TOKEN}',
            'Content-Type': 'application/json',
        }

    # 兜底: HMAC256 签名 (用 AK/SK)
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or '/'

    request_line = f'{method} {path} HTTP/1.1'
    headers_str = f'Host: {host}'
    string_to_sign = f'{request_line}\n{headers_str}\n{body_str}'

    mac_bytes = hmac.new(
        VOLC_AK_SECRET.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha256
    ).digest()
    mac_b64 = base64.urlsafe_b64encode(mac_bytes).decode('utf-8').rstrip('=')

    auth = f'HMAC256; access_token="{VOLC_AK_ID}"; mac="{mac_b64}"; h="Host"'
    return {
        'Authorization': auth,
        'Content-Type': 'application/json',
        'Host': host,
    }


class VoiceSystem:
    def __init__(self):
        self.running = False
        self.current_volume = 100

        # 从 calibration.json 读取硬件端口
        self.mic_hw, self.speaker_hw = self._load_audio_devices()

    def _load_audio_devices(self):
        """从 calibration.json 读取硬件端口，读不到则运行时自动检测"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        calib_path = os.path.join(base_dir, 'calibration.json')

        mic_hw = None
        speaker_hw = None

        if os.path.exists(calib_path):
            try:
                with open(calib_path, 'r') as f:
                    data = json.load(f)
                hw = data.get("HARDWARE", {})
                mic_hw = hw.get("mic")
                speaker_hw = hw.get("speaker")
            except:
                pass

        if not mic_hw or not speaker_hw:
            try:
                from subsystems.hardware_check import auto_configure_audio
                detected_mic, detected_spk = auto_configure_audio()
                mic_hw = mic_hw or detected_mic
                speaker_hw = speaker_hw or detected_spk
            except:
                mic_hw = mic_hw or "plughw:4,0"
                speaker_hw = speaker_hw or "plughw:2,0"

        print(f"  [Voice] mic={mic_hw}  speaker={speaker_hw}")
        return mic_hw, speaker_hw

    def _get_speaker_card(self):
        """从 speaker_hw 提取声卡编号，如 plughw:2,0 → 2"""
        try:
            return self.speaker_hw.split(':')[1].split(',')[0]
        except:
            return "0"

    def start(self):
        if self.running: return
        self.running = True
        # 启动时拉满所有声卡音量
        card = self._get_speaker_card()
        os.system(f"amixer -c {card} sset 'PCM' 100% >/dev/null 2>&1;"
                  f"amixer -c {card} sset 'Speaker' 100% >/dev/null 2>&1;"
                  f"amixer -c {card} sset 'Master' 100% >/dev/null 2>&1;"
                  f"amixer -c {card} sset 'Headphone' 100% >/dev/null 2>&1;"
                  "amixer sset 'PCM' 100% >/dev/null 2>&1;"
                  "amixer sset 'Speaker' 100% >/dev/null 2>&1;"
                  "amixer sset 'Master' 100% >/dev/null 2>&1;"
                  "amixer sset 'Headphone' 100% >/dev/null 2>&1")
        print(f"  [Voice] 扬声器音量已拉满 (card={card})")

    def stop(self):
        self.running = False
        self.stop_mic_monitor()

    # ============ 麦克风实时监听 ============
    def start_mic_monitor(self):
        """启动后台麦克风监听线程，持续采集音量"""
        if getattr(self, '_mic_monitor_running', False):
            return
        self._mic_monitor_running = True
        self._mic_level = 0
        self._mic_monitor_thread = threading.Thread(target=self._mic_monitor_loop, daemon=True)
        self._mic_monitor_thread.start()

    def stop_mic_monitor(self):
        """停止麦克风监听"""
        self._mic_monitor_running = False
        self._mic_level = 0

    def get_mic_level(self):
        """返回当前麦克风音量 (0~5000+)"""
        return getattr(self, '_mic_level', 0)

    def _mic_monitor_loop(self):
        """后台线程：持续读取麦克风并更新音量值"""
        cmd = ['arecord', '-D', self.mic_hw, '-f', 'S16_LE',
               '-r', '16000', '-c', '1', '-t', 'raw', '-q']
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"  [MicMonitor] arecord 启动失败: {e}")
            self._mic_monitor_running = False
            return

        try:
            while self._mic_monitor_running:
                data = process.stdout.read(3200)  # 100ms
                if not data:
                    break
                self._mic_level = self.calculate_volume(data)
        finally:
            process.terminate()
            process.wait()
            self._mic_level = 0
            self._mic_monitor_running = False

    def set_volume(self, volume: int):
        self.current_volume = max(0, min(100, int(volume)))
        card = self._get_speaker_card()
        os.system(f"amixer -c {card} sset 'PCM' {self.current_volume}% >/dev/null 2>&1;"
                  f"amixer -c {card} sset 'Speaker' {self.current_volume}% >/dev/null 2>&1;"
                  f"amixer -c {card} sset 'Master' {self.current_volume}% >/dev/null 2>&1;"
                  f"amixer -c {card} sset 'Headphone' {self.current_volume}% >/dev/null 2>&1")

    def calculate_volume(self, data):
        if not data: return 0
        count = len(data) // 2
        try:
            shorts = struct.unpack("<%dh" % count, data)
            return int(math.sqrt(sum(s * s for s in shorts) / count))
        except:
            return 0

    # ================================================================
    #  ASR: VAD 静音截断 + 火山引擎 HTTP 识别
    # ================================================================
    def listen(self, timeout=8) -> str:
        print("\n[听觉] 我在听，请说话...")

        # 先停掉麦克风监听，防止设备冲突
        self.stop_mic_monitor()
        time.sleep(0.2)

        # 启动录音
        cmd = ['arecord', '-D', self.mic_hw, '-f', 'S16_LE',
               '-r', '16000', '-c', '1', '-t', 'raw', '-q']
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"  [ASR] arecord 启动失败: {e}")
            return ""

        # 检查是否立即退出（设备打不开）
        time.sleep(0.1)
        if process.poll() is not None:
            stderr_out = process.stderr.read().decode('utf-8', errors='ignore')
            print(f"  [ASR] arecord 立即退出! stderr: {stderr_out}")
            return ""

        audio_buffer = bytearray()
        speaking_detected = False
        silence_start = None
        speech_start = None
        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                data = process.stdout.read(3200)  # 100ms of 16kHz 16bit mono
                if not data:
                    break

                audio_buffer.extend(data)

                # VAD 检测
                vol = self.calculate_volume(data)
                bars = int(vol / 200)
                print("\r  [mic] " + ">" * min(bars, 25) + " " * (25 - min(bars, 25)) + f" {vol:04d}", end="", flush=True)

                if vol > VAD_SILENCE_THRESHOLD:
                    if not speaking_detected:
                        speaking_detected = True
                        speech_start = time.time()
                    silence_start = None
                elif speaking_detected:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > VAD_SILENCE_DURATION:
                        if speech_start and (time.time() - speech_start > VAD_MIN_SPEECH_DURATION):
                            break
        finally:
            process.terminate()
            process.wait()
            print()

        print(f"  [ASR] 录音结束: {len(audio_buffer)} 字节, 检测到语音={speaking_detected}")

        if len(audio_buffer) < 16000:
            print("  [ASR] 音频太短，跳过识别")
            return ""

        # 发送到火山引擎 ASR
        text = self._asr_volcengine(bytes(audio_buffer))
        if text:
            print(f"  [你说]: {text}")
        return text

    def _asr_volcengine(self, audio_data: bytes) -> str:
        """火山引擎 ASR HTTP 识别"""
        # 依次尝试多个 cluster（不同控制台配置可能不同）
        clusters_to_try = [VOLC_ASR_CLUSTER, "volcengine_input_common", "volcano_asr", "volc_asr_common"]
        tried_clusters = set()

        for cluster in clusters_to_try:
            if cluster in tried_clusters:
                continue
            tried_clusters.add(cluster)
            try:
                audio_b64 = base64.b64encode(audio_data).decode('utf-8')
                payload = {
                    "app": {
                        "appid": VOLC_APP_ID,
                        "token": VOLC_ACCESS_TOKEN or "default",
                        "cluster": cluster
                    },
                    "user": {"uid": "lelamp_robot"},
                    "audio": {
                        "format": "pcm",
                        "rate": 16000,
                        "bits": 16,
                        "channel": 1,
                        "data": audio_b64
                    },
                    "request": {
                        "reqid": str(uuid.uuid4()),
                        "nbest": 1,
                        "sequence": -1
                    }
                }

                body_str = json.dumps(payload)
                headers = _openspeech_auth_header('POST', VOLC_ASR_URL, body_str)

                resp = requests.post(VOLC_ASR_URL, data=body_str.encode('utf-8'), headers=headers, timeout=10)
                print(f"  [ASR] cluster={cluster} HTTP {resp.status_code}")

                if resp.status_code == 500:
                    print(f"  [ASR] 服务端500, 原始响应: {resp.text[:200]}")
                    continue  # 尝试下一个 cluster

                if resp.status_code != 200:
                    print(f"  [ASR] HTTP {resp.status_code}: {resp.text[:200]}")
                    continue

                try:
                    result = resp.json()
                except:
                    print(f"  [ASR] 响应非JSON: {resp.text[:200]}")
                    continue

                if result.get("code") in (1000, 0):
                    if cluster != VOLC_ASR_CLUSTER:
                        print(f"  [ASR] ✓ 正确的cluster是: {cluster}")
                    # 解析结果：可能是字符串或列表
                    raw = result.get("result", "")
                    if isinstance(raw, list):
                        # [{"text": "...", "confidence": 0}, ...]
                        return raw[0].get("text", "") if raw else ""
                    return str(raw)
                else:
                    print(f"  [ASR] code={result.get('code')}, msg={result.get('message', '')}")
                    continue

            except Exception as e:
                print(f"  [ASR] cluster={cluster} 失败: {e}")
                continue

        # 所有 cluster 都失败，回退阿里云
        print("  [ASR] 所有火山引擎cluster均失败，回退阿里云...")
        return self._asr_alibaba_fallback(audio_data)

    def _asr_alibaba_fallback(self, audio_data: bytes) -> str:
        """阿里云 NLS REST 兜底 ASR"""
        try:
            import urllib.request
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.request import CommonRequest

            client = AcsClient(os.environ.get("ALI_AK_ID", ""), os.environ.get("ALI_AK_SECRET", ""), 'cn-shanghai')
            req = CommonRequest()
            req.set_method('POST')
            req.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
            req.set_version('2019-02-28')
            req.set_action_name('CreateToken')
            req.set_connect_timeout(2000)
            req.set_read_timeout(2000)
            response = client.do_action_with_exception(req)
            jss = json.loads(response)
            token = jss['Token']['Id']

            app_key = os.environ.get("ALI_NLS_APP_KEY", "")
            url = (f"https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
                   f"?appkey={app_key}&format=pcm&sample_rate=16000"
                   f"&enable_punctuation_prediction=true")
            http_req = urllib.request.Request(url, data=audio_data)
            http_req.add_header("X-NLS-Token", token)
            http_req.add_header("Content-Type", "application/octet-stream")

            with urllib.request.urlopen(http_req, timeout=8) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("status") == 20000000:
                    return result.get("result", "")
            return ""
        except Exception as e:
            print(f"  [ASR-fallback] 阿里云也失败了: {e}")
            return ""

    # ================================================================
    #  TTS: 火山引擎 HTTP → mp3 → mpg123 播放
    # ================================================================
    def speak(self, text: str):
        if not text: return
        safe_text = text.replace('"', '').replace("'", "").replace('\n', '，')

        # 获取当前角色的音色
        try:
            from subsystems.persona import get_persona_manager
            voice_id = get_persona_manager().current.get("voice_id", "BV001_streaming")
        except:
            voice_id = "BV001_streaming"

        try:
            audio_data = self._tts_volcengine(safe_text, voice_id)
            if audio_data:
                self._play_audio(audio_data)
                return
        except Exception as e:
            print(f"  [TTS] 火山引擎失败: {e}，回退阿里云...")

        # 兜底：阿里云 TTS
        self._tts_alibaba_fallback(safe_text)

    def _tts_volcengine(self, text: str, voice_id: str) -> bytes:
        """火山引擎 TTS HTTP 合成"""
        payload = {
            "app": {
                "appid": VOLC_APP_ID,
                "token": VOLC_ACCESS_TOKEN or "default",
                "cluster": VOLC_TTS_CLUSTER
            },
            "user": {"uid": "lelamp_robot"},
            "audio": {
                "voice_type": voice_id,
                "encoding": "mp3",
                "rate": 24000
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query"
            }
        }

        body_str = json.dumps(payload)
        headers = _openspeech_auth_header('POST', VOLC_TTS_URL, body_str)

        resp = requests.post(VOLC_TTS_URL, data=body_str.encode('utf-8'), headers=headers, timeout=15)
        print(f"  [TTS] HTTP {resp.status_code}")
        result = resp.json()

        if "data" in result:
            return base64.b64decode(result["data"])
        else:
            raise RuntimeError(f"TTS 无音频数据: code={result.get('code')}, msg={result.get('message', 'unknown')}")

    def _play_audio(self, audio_data: bytes):
        """通过 mpg123 播放 mp3 音频数据"""
        try:
            player = subprocess.Popen(
                ['mpg123', '-a', self.speaker_hw, '-q', '-'],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            player.stdin.write(audio_data)
            player.stdin.close()
            player.wait(timeout=30)
        except subprocess.TimeoutExpired:
            print("  [播放] mpg123 超时，强制终止")
            player.kill()
            player.wait()
        except Exception as e:
            print(f"  [播放] mpg123 播放失败: {e}")
            try:
                with open("/tmp/lelamp_reply.mp3", "wb") as f:
                    f.write(audio_data)
                subprocess.run(
                    ['mpg123', '-a', self.speaker_hw, '-q', '/tmp/lelamp_reply.mp3'],
                    timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def _tts_alibaba_fallback(self, text: str):
        """阿里云 NLS TTS 兜底"""
        try:
            import nls
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.request import CommonRequest

            client = AcsClient(os.environ.get("ALI_AK_ID", ""), os.environ.get("ALI_AK_SECRET", ""), 'cn-shanghai')
            req = CommonRequest()
            req.set_method('POST')
            req.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
            req.set_version('2019-02-28')
            req.set_action_name('CreateToken')
            req.set_connect_timeout(2000)
            req.set_read_timeout(2000)
            response = client.do_action_with_exception(req)
            jss = json.loads(response)
            token = jss['Token']['Id']

            app_key = os.environ.get("ALI_NLS_APP_KEY", "")
            audio_chunks = []
            done_event = threading.Event()

            def on_data(data, *args):
                audio_chunks.append(data)

            def on_close(*args):
                done_event.set()

            tts = nls.NlsSpeechSynthesizer(
                url="wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1",
                token=token,
                appkey=app_key,
                on_data=on_data,
                on_close=on_close,
            )
            tts.start(text, voice="xiaomei", aformat="mp3", volume=self.current_volume)
            done_event.wait(timeout=15)

            if audio_chunks:
                audio_data = b"".join(audio_chunks)
                self._play_audio(audio_data)

        except Exception as e:
            print(f"  [TTS-fallback] 阿里云也失败了: {e}")


_voice_instance = None
def get_voice_system():
    global _voice_instance
    if _voice_instance is None:
        _voice_instance = VoiceSystem()
    return _voice_instance
