# -*- coding: utf-8 -*-
import os
from zhipuai import ZhipuAI
from subsystems.persona import get_persona_manager

class LLMEngine:
    def __init__(self):
        self.api_key = os.environ.get("ZHIPU_API_KEY", "")
        self.client = ZhipuAI(api_key=self.api_key)
        self.is_sleeping = False

        # 从角色管理器获取当前角色
        self.persona = get_persona_manager()
        self._rebuild_history()

    def _rebuild_history(self):
        """根据当前角色重建对话历史"""
        self.chat_history = [{"role": "system", "content": self.persona.current["system_prompt"]}]

    def switch_persona(self, persona_id, custom_config=None):
        """切换角色并重置对话上下文"""
        result = self.persona.switch(persona_id, custom_config)
        if result:
            self.is_sleeping = False
            self._rebuild_history()
        return result

    def chat(self, user_text):
        print(f"[LLM] 正在向智谱云端发送思考请求: '{user_text}'")

        sleep_keywords = ["退下", "休息", "休眠", "睡觉", "闭嘴"]
        is_going_to_sleep = any(kw in user_text for kw in sleep_keywords)

        if self.is_sleeping and not is_going_to_sleep:
            print("[LLM-STATE] 检测到从休眠中唤醒，正在底层注入打招呼提示...")
            user_text = "【系统环境音：你刚从休眠中被唤醒，请先用一句符合你角色特点的问候语和我打个招呼，然后再顺畅地回答以下内容】\n" + user_text
            self.is_sleeping = False

        if is_going_to_sleep:
            print("[LLM-STATE] 接收到休眠指令，神经元进入逻辑休眠态...")
            self.is_sleeping = True

        self.chat_history.append({"role": "user", "content": user_text})

        search_keywords = ["查一下", "搜一下", "是什么", "新闻", "天气", "今天", "最新", "谁是", "解释", "为什么", "怎么做", "怎么样"]
        need_search = any(kw in user_text for kw in search_keywords)

        try:
            if need_search:
                print("[LLM] 开启联网搜索模式 (glm-4-flash-250414)...")
                response = self.client.chat.completions.create(
                    model="glm-4-flash-250414",
                    messages=self.chat_history,
                    tools=[{"type": "web_search", "web_search": {"enable": True}}],
                    timeout=15
                )
            else:
                print("[LLM] 日常深度逻辑模式 (glm-4-flash-250414)...")
                response = self.client.chat.completions.create(
                    model="glm-4-flash-250414",
                    messages=self.chat_history,
                    timeout=10
                )

            ai_reply = response.choices[0].message.content
            ai_reply = ai_reply.replace('*', '').replace('#', '')

            self.chat_history.append({"role": "assistant", "content": ai_reply})

            if len(self.chat_history) > 13:
                self.chat_history = [self.chat_history[0]] + self.chat_history[-12:]

            return ai_reply

        except Exception as e:
            print(f"[ERROR] 智谱 API 请求失败: {e}")
            return "抱歉，我的思考通道刚刚出了点问题，能再说一遍吗？"

_llm_instance = None
def get_llm_engine():
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMEngine()
    return _llm_instance
