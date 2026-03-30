# -*- coding: utf-8 -*-
import math
import json
import os
from zhipuai import ZhipuAI

class IntentEngine:
    def __init__(self):
        print("\n?? [云端向量皮层] 正在初始化智谱 Embedding 引擎...")
        self.client = ZhipuAI(api_key=os.environ.get("ZHIPU_API_KEY", ""))
        
        self.intent_anchors = {
            "SLEEP": ["退下", "休息", "闭嘴", "没你事了", "你可以睡觉了", "自己玩去吧", "别吵了", "跪安吧"],
            "DANCE": ["跳舞", "跳个舞", "来段才艺", "活动一下筋骨", "随音乐摇摆", "给我舞一个"],
            "CYBER_DANCE": ["机械舞", "赛博朋克", "炫酷模式", "系统过载"],
            "STAND": ["起立", "站起来", "把身子挺直", "别蹲着了", "站直"],
            "SQUAT": ["蹲下", "趴下", "低头隐蔽", "卧倒", "趴低一点"],
            "CUTE": ["卖萌", "装可爱", "撒个娇", "喵呜"],
            "NOD": ["点头", "同意", "点点头", "说得对", "我赞同你的看法"],
            "SHAKE": ["摇头", "不同意", "拒绝", "不对", "摇摇头", "我觉得不行"],
            "PHOTO": ["拍个照", "拍照", "给我拍张照", "合影", "记录一下", "照相", "帮我拍张照片"]
        }
        
        self.anchor_embeddings = {}
        for intent, phrases in self.intent_anchors.items():
            try:
                response = self.client.embeddings.create(model="embedding-2", input=phrases)
                self.anchor_embeddings[intent] = [item.embedding for item in response.data]
            except Exception: pass
            
        # 核心新增：启动时加载从网页端录制的自定义动作
        self.load_dynamic_poses()
        print("? 云端向量空间构建完成！")

    def load_dynamic_poses(self):
        """热加载网页端录制的新动作，实现Continual Learning (持续学习)"""
        print("\n?? [意图引擎] 正在扫描并加载你录制的新动作...")
        calib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'calibration.json')
        try:
            with open(calib_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                custom_poses = data.get("CUSTOM_POSES", {})
                for pose_name in custom_poses.keys():
                    if pose_name not in self.intent_anchors:
                        self.intent_anchors[pose_name] = [pose_name]
                        try:
                            response = self.client.embeddings.create(model="embedding-2", input=[pose_name])
                            self.anchor_embeddings[pose_name] = [response.data[0].embedding]
                            print(f"? 成功习得新动作并建立向量映射: <{pose_name}>")
                        except Exception: pass
        except Exception: pass

    def _cosine_similarity(self, v1, v2):
        dot_product = sum(a * b for a, b in zip(v1, v2))
        mag1 = math.sqrt(sum(a * a for a in v1))
        mag2 = math.sqrt(sum(b * b for b in v2))
        if mag1 == 0 or mag2 == 0: return 0.0
        return dot_product / (mag1 * mag2)

    def predict(self, text, threshold=0.55):
        for intent, phrases in self.intent_anchors.items():
            if any(phrase in text for phrase in phrases):
                print(f"\n?? [意图捕获] 关键词精准命中 <{intent}> (底层规则拦截)")
                return intent

        try:
            response = self.client.embeddings.create(model="embedding-2", input=[text])
            query_emb = response.data[0].embedding
            
            best_intent = None
            max_sim = 0.0
            
            for intent, embs in self.anchor_embeddings.items():
                for emb in embs:
                    sim = self._cosine_similarity(query_emb, emb)
                    if sim > max_sim:
                        max_sim = sim
                        best_intent = intent
                        
            if max_sim >= threshold:
                print(f"\n?? [意图捕获] 成功匹配动作 <{best_intent}> (空间置信度: {max_sim:.2f})")
                return best_intent
        except Exception: pass
        return None

_intent_instance = None
def get_intent_engine():
    global _intent_instance
    if _intent_instance is None:
        _intent_instance = IntentEngine()
    return _intent_instance