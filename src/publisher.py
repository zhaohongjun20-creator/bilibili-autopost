"""B站投稿：登录预检 + 视频上传。基于 bilibili-api-python。"""
import requests
from bilibili_api import Credential, video_uploader

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

def check_login(sessdata: str) -> dict:
    """预检 cookie；返回 {'ok': bool, 'uname': str}。失效时 ok=False。"""
    r = requests.get(
        "https://api.bilibili.com/x/web-interface/nav",
        cookies={"SESSDATA": sessdata},
        headers={"User-Agent": UA},  # 裸 python UA 会被 B 站 412 风控拦截
        timeout=20,
    )
    r.raise_for_status()
    data = r.json().get("data", {})
    return {"ok": bool(data.get("isLogin")), "uname": data.get("uname", "")}

async def publish(env: dict, video_path: str, cover_path: str,
                  title: str, desc: str, tags: list, tid: int = 160) -> str:
    """投稿，成功返回 bvid；失败抛异常。"""
    credential = Credential(
        sessdata=env["BILI_SESSDATA"],
        bili_jct=env["BILI_JCT"],
        dedeuserid=env.get("BILI_UID", ""),
    )
    page = video_uploader.VideoUploaderPage(path=video_path, title=title)
    meta = video_uploader.VideoMetaData(
        tid=tid, title=title, desc=desc, tags=tags, cover=cover_path,
    )
    uploader = video_uploader.VideoUploader([page], meta, credential)
    result = await uploader.start()
    return result["bvid"]
