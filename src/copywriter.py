"""GLM 文案生成：标题/简介/标签，失败退回模板。"""
import json, re, requests

ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

PROMPT = """你是B站视频运营。根据以下素材信息生成中文投稿文案，只输出 JSON，不要输出任何其他内容。
素材主题关键词：{keyword}
原作者：{author}
时长：{duration}秒
原始链接：{orig_title}

输出格式：
{{"title": "80字内吸引人的中文标题", "desc": "100字内中文简介，结尾必须自然带上一句：素材来源：Pexels（免费商用授权），原作者：{author}", "tags": ["标签1","标签2","标签3","标签4","标签5"]}}"""

def _parse_llm_json(raw: str):
    """容错解析：裸 JSON / markdown 围栏 / 前后杂质。"""
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    candidates = [m.group(1)] if m else []
    brace = re.search(r"\{.*\}", raw, re.S)
    if brace:
        candidates.append(brace.group(0))
    for c in candidates:
        try:
            obj = json.loads(c)
            if all(k in obj for k in ("title", "desc", "tags")):
                return obj
        except (json.JSONDecodeError, TypeError):
            continue
    return None

def fallback_copywriting(meta: dict) -> dict:
    kw = meta["keyword"].title()
    return {
        "title": f"{kw}｜高清治愈风景，放松一下",
        "desc": (f"一段{meta['duration']}秒的{meta['keyword']}素材。\n"
                 f"素材来源：Pexels（免费商用授权），原作者：{meta['author']}"),
        "tags": ["风景", "治愈", "素材", "自然", "放松"],
    }

def generate(api_key: str, meta: dict, model: str = "glm-4-flash",
             temperature: float = 0.8) -> dict:
    prompt = PROMPT.format(
        keyword=meta["keyword"], author=meta["author"],
        duration=meta["duration"], orig_title=meta.get("orig_title", ""),
    )
    for _ in range(2):
        try:
            r = requests.post(
                ZHIPU_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "temperature": temperature,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            parsed = _parse_llm_json(content)
            if parsed:
                return parsed
        except (requests.RequestException, KeyError, IndexError):
            continue
    return fallback_copywriting(meta)
