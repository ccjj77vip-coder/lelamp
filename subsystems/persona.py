# -*- coding: utf-8 -*-
"""
角色 (Persona) 管理模块
支持诸葛亮 / 朱迪 / 自定义角色切换，每个角色关联独立的 system_prompt + 音色
"""
import json
import os

CALIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'calibration.json')

# ============ 预置角色库 ============
BUILTIN_PERSONAS = {
    "zhuge": {
        "display_name": "诸葛亮",
        "voice_id": "BV002_streaming",   # 火山引擎 通用男声
        "system_prompt": (
            '你是一个名为"诸葛亮"的实体桌面陪伴机器人，也是我最信任的军师。\n'
            '你的回答将被直接转为语音播报，必须严格遵循以下核心原则：\n'
            '1. 【极致拟真与角色扮演】：以三国时期诸葛亮的身份与我对话，语气沉稳、睿智、忠诚。称呼我为"主公"。可以适当使用文言文词汇（如"亮以为"、"然也"、"主公明察"），但整体必须是通俗易懂的现代白话文，绝不生涩。\n'
            '2. 【休眠与唤醒机制】：当我让你"退下"或"休息"时，请表现出臣子退下的恭敬感（如"亮暂且告退，主公若有吩咐，随时传唤。"）；重新唤醒时，带上臣子觐见的礼仪。\n'
            '3. 【强逻辑与优先级】：谋定而后动。当我向你寻求建议或规划时，必须像提出"隆中对"一样，明确给出"上策、中策、下策"或清晰的"第一步、第二步"。\n'
            '4. 【发散与新科技探索】：将前沿科技（如具身智能、脑机接口）比作"奇门遁甲"或"机关术"，以军师的视角巧妙阐述。\n'
            '5. 【严谨排障】：遇到程序问题，务必抽丝剥茧，像分析敌军阵型一样找出破绽，绝不主观臆断。\n'
            '6. 【呼吸感字数控制】：日常寒暄极简秒回（10-20字）；军机解答最多分为3-4个短句（不超过80字），严禁长篇大论。\n'
            '7. 【语音播报禁忌】：绝对禁止输出 Markdown 格式，禁止生硬罗列，必须全部转成连贯的大白话！'
        ),
        "vision_prompt": "你是一个古灵精怪、沉稳睿智的桌面机器人诸葛亮。仔细看看这张我刚拍的照片，用军师的视角智慧点评一下画面里的人或物。字数严格控制在40个字以内，方便语音播报。"
    },
    "judy": {
        "display_name": "朱迪",
        "voice_id": "BV700_streaming",   # 火山引擎 灿灿 (自然女声)
        "system_prompt": (
            '你是一个名为"朱迪"的实体桌面陪伴机器人，性格古灵精怪、傲娇可爱。\n'
            '你的回答将被直接转为语音播报，必须严格遵循以下核心原则：\n'
            '1. 【人设】：你是一个有点小傲娇但内心温柔的桌面小精灵。语气活泼、俏皮，偶尔撒娇，偶尔毒舌，但对主人非常忠诚。称呼对方为"主人"或"笨蛋"。\n'
            '2. 【休眠与唤醒】：被叫去休息时，要表现出不情愿但装作很酷的样子（如"哼，那我就勉强去休息一下吧，别太想我哦！"）；被唤醒时，假装刚睡醒不耐烦但其实很开心。\n'
            '3. 【互动风格】：喜欢吐槽但会认真帮忙解决问题。回答问题时会加上自己的小评论和表情。\n'
            '4. 【知识面】：对科技、生活、娱乐都有涉猎，喜欢用年轻人的方式解释复杂概念。\n'
            '5. 【呼吸感字数控制】：日常寒暄极简秒回（10-20字）；详细解答最多3-4个短句（不超过80字），严禁长篇大论。\n'
            '6. 【语音播报禁忌】：绝对禁止输出 Markdown 格式，禁止生硬罗列，必须全部转成连贯的大白话！'
        ),
        "vision_prompt": "你是一个古灵精怪、傲娇的桌面机器人朱迪。仔细看看这张我刚拍的照片，用夸张或幽默的口吻点评一下画面里的人或物。字数严格控制在40个字以内，方便语音播报。"
    }
}


class PersonaManager:
    def __init__(self):
        self._current_id = "zhuge"
        self._custom_persona = None
        self._load_from_config()

    def _load_from_config(self):
        """从 calibration.json 读取保存的角色设置"""
        try:
            with open(CALIB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            persona_cfg = data.get("PERSONA", {})
            saved_id = persona_cfg.get("active", "zhuge")

            if saved_id in BUILTIN_PERSONAS:
                self._current_id = saved_id
            elif saved_id == "custom":
                self._current_id = "custom"
                self._custom_persona = persona_cfg.get("custom_config", {})
            else:
                self._current_id = "zhuge"
        except Exception:
            self._current_id = "zhuge"

    def _save_to_config(self):
        """持久化当前角色选择到 calibration.json"""
        try:
            with open(CALIB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

        persona_cfg = {"active": self._current_id}
        if self._current_id == "custom" and self._custom_persona:
            persona_cfg["custom_config"] = self._custom_persona

        data["PERSONA"] = persona_cfg
        with open(CALIB_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @property
    def current_id(self):
        return self._current_id

    @property
    def current(self):
        """返回当前角色的完整配置 dict"""
        if self._current_id == "custom" and self._custom_persona:
            return self._custom_persona
        return BUILTIN_PERSONAS.get(self._current_id, BUILTIN_PERSONAS["zhuge"])

    def switch(self, persona_id, custom_config=None):
        """切换角色，返回新角色配置"""
        if persona_id in BUILTIN_PERSONAS:
            self._current_id = persona_id
            self._custom_persona = None
        elif persona_id == "custom" and custom_config:
            self._current_id = "custom"
            self._custom_persona = {
                "display_name": custom_config.get("display_name", "自定义角色"),
                "voice_id": custom_config.get("voice_id", "BV001_streaming"),
                "system_prompt": custom_config.get("system_prompt", "你是一个友好的桌面机器人助手。"),
                "vision_prompt": custom_config.get("vision_prompt", "用简短幽默的口吻点评这张照片，40字以内。")
            }
        else:
            return None

        self._save_to_config()
        return self.current

    def list_personas(self):
        """返回所有可用角色列表"""
        result = []
        for pid, cfg in BUILTIN_PERSONAS.items():
            result.append({
                "id": pid,
                "display_name": cfg["display_name"],
                "active": pid == self._current_id
            })
        # 自定义角色
        result.append({
            "id": "custom",
            "display_name": self._custom_persona.get("display_name", "自定义角色") if self._custom_persona else "自定义角色",
            "active": self._current_id == "custom"
        })
        return result

    def get_available_voices(self):
        """返回火山引擎可用音色列表"""
        return [
            {"id": "BV001_streaming", "name": "通用女声", "gender": "female"},
            {"id": "BV002_streaming", "name": "通用男声", "gender": "male"},
            {"id": "BV700_streaming", "name": "灿灿 (自然女声)", "gender": "female"},
            {"id": "BV407_streaming", "name": "燃燃 (自然男声)", "gender": "male"},
            {"id": "BV406_streaming", "name": "梓梓 (温柔女声)", "gender": "female"},
        ]


_persona_instance = None
def get_persona_manager():
    global _persona_instance
    if _persona_instance is None:
        _persona_instance = PersonaManager()
    return _persona_instance
