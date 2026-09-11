"""Pexels 视频搜索与筛选。"""
import os, random, requests

PEXELS_SEARCH = "https://api.pexels.com/videos/search"

def search(api_key: str, keyword: str, per_page: int = 15) -> dict:
    r = requests.get(
        PEXELS_SEARCH,
        headers={"Authorization": api_key},
        params={"query": keyword, "per_page": per_page, "orientation": "landscape"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def pick_video(api_result: dict, known_ids: set, min_dur: int, max_dur: int):
    """横屏 + 时长窗口 + 未发布过；符合者中随机取一个增加多样性。"""
    cands = [
        v for v in api_result.get("videos", [])
        if v["width"] > v["height"]
        and min_dur <= v["duration"] <= max_dur
        and v["id"] not in known_ids
    ]
    return random.choice(cands) if cands else None

def pick_video_file(video_files: list, max_height: int = 1080) -> str:
    """选 mp4 直链（排除 HLS），且高度 ≤ max_height 中画质最高的。"""
    mp4s = [f for f in video_files
            if f.get("file_type") == "video/mp4"
            and f.get("height", 0) <= max_height]
    if not mp4s:
        raise ValueError("no suitable mp4 file")
    best = max(mp4s, key=lambda f: (f["height"], f.get("width", 0)))
    return best["link"]

def download(link: str, dest: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with requests.get(link, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest
