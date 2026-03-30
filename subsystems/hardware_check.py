import subprocess
import re

def get_audio_devices(command):
    """运行 arecord/aplay -l 并解析输出"""
    devices = []
    try:
        output = subprocess.check_output(command.split()).decode('utf-8')
        cards = output.split('\n')
        for line in cards:
            if "card" in line and "device" in line:
                # 完整保留原始行，便于查找 PnP 等关键字
                # 格式示例: card 3: Device [USB PnP Sound Device], device 0: ...
                card_match = re.search(r'card (\d+):', line)
                device_match = re.search(r'device (\d+):', line)
                
                if card_match and device_match:
                    card_id = card_match.group(1)
                    dev_id = device_match.group(1)
                    devices.append({'card': card_id, 'device': dev_id, 'raw': line})
    except Exception as e:
        print(f"❌ 硬件扫描失败: {e}")
    return devices

def auto_configure_audio():
    print("⚡ [自检] 正在扫描音频硬件...")
    
    # === 1. 寻找扬声器 (Playback) ===
    speakers = get_audio_devices("aplay -l")
    speaker_hw = "plughw:2,0" # 默认兜底耳机孔
    speaker_name = "默认设备"
    
    found_spk = False
    
    # 策略: 优先找耳机孔 (Headphones)
    for d in speakers:
        if "Headphones" in d['raw'] or "bcm2835" in d['raw']:
            speaker_hw = f"plughw:{d['card']},{d['device']}"
            speaker_name = "板载耳机孔 (Headphones)"
            found_spk = True
            break
            
    # 如果没找到耳机孔，试着找 USB 音箱
    if not found_spk:
        for d in speakers:
            if "USB" in d['raw'] and "Webcam" not in d['raw']:
                speaker_hw = f"plughw:{d['card']},{d['device']}"
                speaker_name = "USB 音箱"
                found_spk = True
                break
    
    # === 2. 寻找麦克风 (Capture) ===
    mics = get_audio_devices("arecord -l")
    mic_hw = "plughw:4,0" # 默认兜底
    mic_name = "默认设备"
    found_mic = False
    
    # 🟢 优先级 1: 必须是 "PnP" (你的 USB 麦克风特征)
    for d in mics:
        if "PnP" in d['raw']:
            mic_hw = f"plughw:{d['card']},{d['device']}"
            mic_name = "USB PnP 专用麦克风"
            found_mic = True
            break
            
    # 🟡 优先级 2: 包含 "USB" 但绝不是 "Webcam"
    if not found_mic:
        for d in mics:
            if "USB" in d['raw'] and "Webcam" not in d['raw'] and "Camera" not in d['raw']:
                mic_hw = f"plughw:{d['card']},{d['device']}"
                mic_name = "通用 USB 麦克风"
                found_mic = True
                break

    # 🔴 优先级 3: 实在没办法了才选 Webcam (最后选择)
    if not found_mic:
        for d in mics:
            if "Webcam" in d['raw']:
                mic_hw = f"plughw:{d['card']},{d['device']}"
                mic_name = "Webcam 麦克风 (不推荐)"
                found_mic = True
                break

    print(f"   ✅ 麦克风锁定: [{mic_hw}] {mic_name}")
    print(f"   ✅ 扬声器锁定: [{speaker_hw}] {speaker_name}")
    
    return mic_hw, speaker_hw

if __name__ == "__main__":
    auto_configure_audio()
