# -*- coding: utf-8 -*-
import time
import threading
import math
import colorsys
import atexit

HAS_HARDWARE = False
try:
    import board
    import neopixel
    HAS_HARDWARE = True
except ImportError:
    print("  [LED] 缺少 neopixel 库。")

class LEDEngine:
    def __init__(self):
        global HAS_HARDWARE
        self.num_pixels = 24
        self.pin = board.D10 if HAS_HARDWARE else None
        self.pixels = None

        if HAS_HARDWARE:
            try:
                self.pixels = neopixel.NeoPixel(
                    self.pin, self.num_pixels, brightness=0.3, auto_write=False, pixel_order=neopixel.GRB
                )
                print(f"  [LED] NeoPixel 初始化成功 (pin=D10, {self.num_pixels}灯)")
            except Exception as e:
                print(f"  [LED] NeoPixel 初始化失败: {e}")
                HAS_HARDWARE = False

        self.current_effect = "warm_lamp"
        self.running = False
        self.render_thread = None
        atexit.register(self.stop)

    def start(self):
        self.running = True
        self.render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self.render_thread.start()

    def stop(self):
        self.running = False
        if self.render_thread:
            self.render_thread.join(timeout=0.5)
        if HAS_HARDWARE and self.pixels:
            self.pixels.fill((0, 0, 0))
            self.pixels.show()

    def set_effect(self, effect_name: str):
        if effect_name == "breathe_green":
            effect_name = "warm_lamp"
        if self.current_effect != effect_name:
            self.current_effect = effect_name

    def _render_loop(self):
        fps = 30
        dt = 1.0 / fps
        step = 0.0

        while self.running:
            loop_start = time.time()
            step += dt

            if not HAS_HARDWARE or not self.pixels:
                time.sleep(dt)
                continue

            try:
                effect = self.current_effect

                if effect == "warm_lamp":
                    # 暖光台灯：琥珀色微呼吸，像真实钨丝灯泡
                    breath = 0.85 + 0.15 * math.sin(step * 0.8)
                    r = int(255 * breath)
                    g = int(130 * breath)
                    b = int(8 * breath)
                    self.pixels.fill((r, g, b))

                elif effect == "warm_breathe":
                    # 暖光慢呼吸：待机时柔和感
                    breath = 0.5 + 0.5 * math.sin(step * 1.2)
                    r = int(255 * breath)
                    g = int(120 * breath)
                    b = int(5 * breath)
                    self.pixels.fill((r, g, b))

                elif effect == "listening":
                    # 聆听：暖橙渐变脉冲，从底部向顶部扩散
                    pulse = 0.5 + 0.5 * math.sin(step * 3.0)
                    for i in range(self.num_pixels):
                        ratio = i / self.num_pixels
                        wave = 0.5 + 0.5 * math.sin(step * 4.0 - ratio * math.pi * 2)
                        r = int(255 * wave * pulse)
                        g = int(160 * wave * pulse * 0.6)
                        b = int(20 * wave * pulse * 0.3)
                        self.pixels[i] = (r, g, b)

                elif effect == "thinking":
                    # 思考：琥珀流光环绕，像金色光芒在转圈思索
                    self.pixels.fill((15, 8, 0))
                    head = (step * 12) % self.num_pixels
                    for i in range(8):
                        idx = int(head - i) % self.num_pixels
                        t = 1.0 - (i / 8.0)
                        t2 = t * t
                        self.pixels[idx] = (int(255 * t2), int(140 * t2), int(10 * t2))

                elif effect == "speaking":
                    # 播报：暖黄色随节奏跳动，像烛火
                    for i in range(self.num_pixels):
                        flicker = 0.7 + 0.3 * math.sin(step * 6.0 + i * 0.8)
                        r = int(255 * flicker)
                        g = int(120 * flicker)
                        b = int(5 * flicker)
                        self.pixels[i] = (r, g, b)

                elif effect == "rainbow":
                    # 跳舞：全彩流光，但更温暖（饱和度0.85）
                    for i in range(self.num_pixels):
                        hue = (step * 0.5 + i / self.num_pixels) % 1.0
                        r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.85, 1.0)]
                        self.pixels[i] = (r, g, b)

                elif effect == "solid_white":
                    # 拍照闪光：暖白光（不发冷）
                    self.pixels.fill((255, 240, 220))

                elif effect == "photo_countdown":
                    # 拍照倒数：像快门一样环形收缩
                    active = int((step * 20) % self.num_pixels)
                    for i in range(self.num_pixels):
                        if i < active:
                            self.pixels[i] = (255, 240, 220)
                        else:
                            self.pixels[i] = (30, 15, 0)

                elif effect == "success":
                    # 成功：暖金色双闪
                    blink = math.sin(step * 8.0)
                    if blink > 0:
                        self.pixels.fill((255, 180, 30))
                    else:
                        self.pixels.fill((80, 40, 0))

                elif effect == "off":
                    self.pixels.fill((0, 0, 0))

                self.pixels.show()
            except Exception:
                pass

            elapsed = time.time() - loop_start
            if dt - elapsed > 0:
                time.sleep(dt - elapsed)

_led_instance = None
def get_led_engine():
    global _led_instance
    if _led_instance is None:
        _led_instance = LEDEngine()
    return _led_instance
