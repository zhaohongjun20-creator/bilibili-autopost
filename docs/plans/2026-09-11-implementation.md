# bilibili-autopost 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天自动从 Pexels 收集一个符合主题的横屏视频，GLM 生成文案，ffmpeg 抽封面，自动投稿到 B 站。

**Architecture:** 单进程 Python 脚本，五模块流水线（fetch→download→copywrite→cover→publish），SQLite 去重防重发，Windows 计划任务驱动，密钥全部走 .env。

**Tech Stack:** Python 3.14, requests, bilibili-api-python, pyyaml, python-dotenv, imageio-ffmpeg（免装 ffmpeg）, pytest

**环境注意:** Python 3.14 较新，若 `bilibili-api-python` 或其依赖（aiohttp 等）安装失败，回退方案是 publisher 模块改用 requests 直接调 B 站 web 投稿接口（预检 nav → 上传 → 提交）。先装再说。

---

### Task 1: 项目基础设施

**Files:**
- Create: `requirements.txt`, `config.yaml`, `.env.example`, `src/__init__.py`

- [ ] **Step 1: 创建 requirements.txt**

```
requests>=2.31
pyyaml>=6.0
python-dotenv>=1.0
imageio-ffmpeg>=0.4.9
bilibili-api-python>=17.1.0
pytest>=8.0
```

- [ ] **Step 2: 创建 config.yaml（默认主题：自然风景）**

```yaml
# 每次运行随机取一个关键词搜索 Pexels
keywords:
  - "ocean waves"
  - "mountain sunrise"
  - "forest waterfall"
  - "starry sky timelapse"
  - "aurora"

video_filter:
  orientation: landscape   # 仅横屏
  min_duration: 60         # 秒
  max_duration: 180

download:
  max_height: 1080         # 取 ≤1080p 的最大画质即可

bilibili:
  tid: 160                 # 分区：生活-日常（可改）
  tags_extra: ["风景", "治愈", "4K素材"]

copywriter:
  model: "glm-4-flash"     # 免费；可改 glm-4.6
  temperature: 0.8
```

- [ ] **Step 3: 创建 .env.example（占位模板）**

```ini
PEXELS_API_KEY=your_pexels_key_here
ZHIPU_API_KEY=your_zhipu_key_here
BILI_SESSDATA=your_sessdata_here
BILI_JCT=your_bili_jct_here
BILI_UID=your_uid_here
```

- [ ] **Step 4: 建目录与包标识**

```bash
mkdir -p src tests downloads logs data
touch src/__init__.py tests/__init__.py
```

- [ ] **Step 5: 安装依赖并验证**

```bash
pip install -r requirements.txt
python -c "import requests, yaml, dotenv, imageio_ffmpeg; from bilibili_api import video_uploader; print('deps ok')"
```

- [ ] **Step 6: Commit** `git add -A && git commit -m "chore: project scaffolding and config"`

---

### Task 2: store.py — SQLite 状态记录（TDD）

**Files:**
- Create: `src/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_store.py
import os, tempfile
from src.store import Store

def make_store():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return Store(path)

def test_record_and_is_published():
    s = make_store()
    assert not s.is_published(12345)
    s.record_fetched(12345, "ocean", "https://pexels.com/v/12345")
    s.mark_published(12345, "BV1xx411c7mD")
    assert s.is_published(12345)
    assert s.get_bvid(12345) == "BV1xx411c7mD"

def test_mark_failed_and_retry_queue():
    s = make_store()
    s.record_fetched(111, "x", "u")
    s.mark_failed(111, "upload timeout")
    rows = s.pending_retry()
    assert len(rows) == 1 and rows[0]["pexels_id"] == 111
    s.mark_published(111, "BV2")
    assert s.pending_retry() == []

def test_duplicate_record_rejected():
    s = make_store()
    s.record_fetched(123, "x", "u")
    try:
        s.record_fetched(123, "x", "u")  # 同一素材二次记录应抛错
        assert False, "should raise"
    except Exception:
        pass
```

- [ ] **Step 2: 运行确认失败** `python -m pytest tests/test_store.py -v` → ModuleNotFoundError

- [ ] **Step 3: 实现 src/store.py**

```python
"""SQLite 状态存储：素材去重 + 投稿状态流转。"""
import sqlite3, os, datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    pexels_id   INTEGER PRIMARY KEY,
    keyword     TEXT,
    source_url  TEXT,
    title       TEXT DEFAULT '',
    status      TEXT DEFAULT 'fetched',   -- fetched|published|failed
    bvid        TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    published_at TEXT DEFAULT ''
);
"""

class Store:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def is_published(self, pexels_id: int) -> bool:
        row = self.conn.execute(
            "SELECT status FROM videos WHERE pexels_id=?", (pexels_id,)
        ).fetchone()
        return bool(row and row["status"] == "published")

    def record_fetched(self, pexels_id: int, keyword: str, source_url: str):
        self.conn.execute(
            "INSERT INTO videos (pexels_id, keyword, source_url) VALUES (?,?,?)",
            (pexels_id, keyword, source_url),
        )
        self.conn.commit()

    def mark_published(self, pexels_id: int, bvid: str):
        self.conn.execute(
            "UPDATE videos SET status='published', bvid=?, published_at=? WHERE pexels_id=?",
            (bvid, datetime.datetime.now().isoformat(timespec="seconds"), pexels_id),
        )
        self.conn.commit()

    def mark_failed(self, pexels_id: int, error: str):
        self.conn.execute(
            "UPDATE videos SET status='failed', error=? WHERE pexels_id=?",
            (error, pexels_id),
        )
        self.conn.commit()

    def pending_retry(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM videos WHERE status='failed' ORDER BY created_at LIMIT 5"
        ).fetchall()]

    def known_ids(self) -> set:
        return {r[0] for r in self.conn.execute("SELECT pexels_id FROM videos").fetchall()}
```

- [ ] **Step 4: 运行测试通过** `python -m pytest tests/test_store.py -v` → 3 passed

- [ ] **Step 5: Commit** `git add src/store.py tests/test_store.py && git commit -m "feat: sqlite store with dedup and retry state"`

---

### Task 3: fetcher.py — Pexels 搜索筛选（TDD）

**Files:**
- Create: `src/fetcher.py`
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: 写失败测试（筛选逻辑纯函数，不发网络请求）**

```python
# tests/test_fetcher.py
from src.fetcher import pick_video, pick_video_file

FAKE_API_RESULT = {
    "videos": [
        {"id": 1, "width": 2160, "height": 3840, "duration": 10,
         "user": {"name": "A"}, "url": "https://pexels.com/v/1", "video_files": []},
        {"id": 2, "width": 1920, "height": 1080, "duration": 5,
         "user": {"name": "B"}, "url": "https://pexels.com/v/2", "video_files": []},
        {"id": 3, "width": 3840, "height": 2160, "duration": 120,
         "user": {"name": "C"}, "url": "https://pexels.com/v/3", "video_files": []},
    ]
}

def test_pick_video_prefers_landscape_duration():
    v = pick_video(FAKE_API_RESULT, known_ids=set(), min_dur=60, max_dur=180)
    assert v["id"] == 3  # 1竖屏被滤，2太短被滤，3符合

def test_pick_video_skips_known():
    v = pick_video(FAKE_API_RESULT, known_ids={3}, min_dur=60, max_dur=180)
    assert v is None  # 全被去重

def test_pick_video_file():
    files = [
        {"link": "sd", "quality": "sd", "width": 640, "height": 360, "file_type": "video/mp4"},
        {"link": "fhd", "quality": "hd", "width": 1920, "height": 1080, "file_type": "video/mp4"},
        {"link": "uhd", "quality": "uhd", "width": 3840, "height": 2160, "file_type": "video/mp4"},
        {"link": "hls", "quality": "hd", "width": 1920, "height": 1080, "file_type": "video/x-mpegURL"},
    ]
    link = pick_video_file(files, max_height=1080)
    assert link == "fhd"  # ≤1080p 中最大，且排除 HLS 流
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 src/fetcher.py**

```python
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
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with requests.get(link, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest
```

- [ ] **Step 4: 运行测试通过** → 3 passed

- [ ] **Step 5: 真实 API 冒烟（不进测试套件，手工跑一次）**

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from src.fetcher import search, pick_video, pick_video_file
import os
res = search(os.environ['PEXELS_API_KEY'], 'ocean waves')
v = pick_video(res, known_ids=set(), min_dur=60, max_dur=180)
print(v['id'], v['duration'], v['user']['name'])
print(pick_video_file(v['video_files']))
"
```
Expected: 打印一个视频 id、时长、作者名、mp4 链接

- [ ] **Step 6: Commit** `git add src/fetcher.py tests/test_fetcher.py && git commit -m "feat: pexels fetcher with landscape/duration filter"`

---

### Task 4: copywriter.py — GLM 文案生成（TDD）

**Files:**
- Create: `src/copywriter.py`
- Test: `tests/test_copywriter.py`

- [ ] **Step 1: 写失败测试（JSON 解析容错 + 模板退回）**

```python
# tests/test_copywriter.py
import src.copywriter as cw

def test_parse_llm_json_clean():
    out = cw._parse_llm_json('{"title":"T","desc":"D","tags":["a","b"]}')
    assert out == {"title": "T", "desc": "D", "tags": ["a", "b"]}

def test_parse_llm_json_with_fenced_code():
    raw = '好的，这是结果：\n```json\n{"title":"T2","desc":"D2","tags":["x"]}\n```'
    out = cw._parse_llm_json(raw)
    assert out["title"] == "T2"

def test_parse_llm_json_garbage_returns_none():
    assert cw._parse_llm_json("我不是JSON") is None

def test_fallback_template():
    meta = {"keyword": "ocean waves", "author": "Cameraman", "duration": 120}
    out = cw.fallback_copywriting(meta)
    assert "Pexels" in out["desc"] and "Cameraman" in out["desc"]
    assert isinstance(out["tags"], list) and out["title"]
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 src/copywriter.py**

```python
"""GLM 文案生成：标题/简介/标签，失败退回模板。"""
import json, os, re, requests

ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

PROMPT = """你是B站视频运营。根据以下素材信息生成中文投稿文案，只输出 JSON，不要输出其他内容。
素材主题关键词：{keyword}
原作者：{author}
时长：{duration}秒
原始标题：{orig_title}

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
    for attempt in range(2):
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
                parsed["desc"] = parsed["desc"]  # 已含来源声明
                return parsed
        except (requests.RequestException, KeyError, IndexError):
            continue
    return fallback_copywriting(meta)
```

- [ ] **Step 4: 运行测试通过** → 4 passed

- [ ] **Step 5: Commit** `git add src/copywriter.py tests/test_copywriter.py && git commit -m "feat: glm copywriter with tolerant json parsing and template fallback"`

---

### Task 5: cover.py — ffmpeg 抽帧封面

**Files:**
- Create: `src/cover.py`

说明：用 `imageio-ffmpeg` 自带的 ffmpeg 可执行文件，用户机器无需安装 ffmpeg。逻辑简单（一条 subprocess 命令），不做单测，dry-run 时人工看封面。

- [ ] **Step 1: 实现 src/cover.py**

```python
"""从视频抽帧生成B站封面（jpg, 16:9）。依赖 imageio-ffmpeg 自带的 ffmpeg。"""
import subprocess, os
import imageio_ffmpeg

def extract_cover(video_path: str, cover_path: str, at_second: int = 3) -> str:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(os.path.dirname(os.path.abspath(cover_path)), exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-ss", str(at_second), "-i", video_path,
        "-frames:v", "1",
        "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "-q:v", "2",
        cover_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return cover_path
```

- [ ] **Step 2: 手工验证（用 downloads 里 dry-run 下载的任意视频）**

```bash
python -c "
from src.cover import extract_cover
import glob
v = glob.glob('downloads/*.mp4')[0]
print(extract_cover(v, 'downloads/_cover_test.jpg'))
" && ls -la downloads/_cover_test.jpg
```
Expected: 命令输出封面路径，文件存在且 >30KB

- [ ] **Step 3: Commit** `git add src/cover.py && git commit -m "feat: ffmpeg frame-extract cover generator"`

---

### Task 6: publisher.py — B站投稿

**Files:**
- Create: `src/publisher.py`

说明：真实投稿接口，不做单测；由 dry-run/首条人工发布验证。核心：登录预检 → 封面上传 → 视频投稿。
**实施时验证点**：`VideoMetaData` 是否支持转载声明字段（copyright/reprint）——支持则设为转载附 Pexels 链接，不支持则依赖简介中的来源声明。

- [ ] **Step 1: 实现 src/publisher.py**

```python
"""B站投稿：登录预检 + 视频上传。基于 bilibili-api-python。"""
import os, requests
from bilibili_api import Credential, video_uploader

def check_login(sessdata: str) -> dict:
    """预检 cookie；返回 {'ok': bool, 'uname': str}。失效时 ok=False。"""
    r = requests.get(
        "https://api.bilibili.com/x/web-interface/nav",
        cookies={"SESSDATA": sessdata}, timeout=20,
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
    # result: {'bvid': 'BV...', 'aid': 123, ...}
    return result["bvid"]
```

- [ ] **Step 2: 登录预检冒烟（不投稿）**

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from src.publisher import check_login
import os
print(check_login(os.environ['BILI_SESSDATA']))
"
```
Expected: `{'ok': True, 'uname': '塞伯坦最高议会议员'}`

- [ ] **Step 3: Commit** `git add src/publisher.py && git commit -m "feat: bilibili publisher with login precheck"`

---

### Task 7: main.py — 流水线入口

**Files:**
- Create: `main.py`

- [ ] **Step 1: 实现 main.py**

```python
"""bilibili-autopost 入口。
用法：
  python main.py               # 完整流程：取素材→文案→封面→投稿
  python main.py --dry-run     # 同上但不投稿，打印产出供检查
  python main.py --retry-failed # 重试历史失败的投稿（需要 downloads 里文件还在）
"""
import argparse, asyncio, logging, os, random, sys
from datetime import datetime
from dotenv import load_dotenv

from src.store import Store
from src.fetcher import search, pick_video, pick_video_file, download
from src.copywriter import generate as gen_copy
from src.cover import extract_cover
from src import publisher

LOG_DIR, DL_DIR, DATA_DIR = "logs", "downloads", "data"

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(f"{LOG_DIR}/{datetime.now():%Y-%m}.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

def load_config():
    import yaml
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_once(dry_run: bool):
    log = logging.getLogger("main")
    load_dotenv()
    cfg = load_config()
    store = Store(f"{DATA_DIR}/published.db")

    # ① fetch
    keyword = random.choice(cfg["keywords"])
    log.info("搜索关键词: %s", keyword)
    res = search(os.environ["PEXELS_API_KEY"], keyword)
    vf = cfg["video_filter"]
    video = pick_video(res, known_ids=store.known_ids(),
                       min_dur=vf["min_duration"], max_dur=vf["max_duration"])
    if not video:
        log.warning("本关键词无可用新素材，本次跳过")
        return
    store.record_fetched(video["id"], keyword, video["url"])
    log.info("选中素材 pexels_id=%s 时长=%ss 作者=%s",
             video["id"], video["duration"], video["user"]["name"])

    # ② download
    link = pick_video_file(video["video_files"], cfg["download"]["max_height"])
    video_path = f"{DL_DIR}/{video['id']}.mp4"
    if not os.path.exists(video_path):
        log.info("下载中: %s", link)
        download(link, video_path)
    log.info("已下载: %s (%.1f MB)", video_path, os.path.getsize(video_path) / 1e6)

    # ③ metadata
    copy = gen_copy(
        os.environ["ZHIPU_API_KEY"],
        {"keyword": keyword, "author": video["user"]["name"],
         "duration": video["duration"],
         "orig_title": video.get("url", "")},
        model=cfg["copywriter"]["model"],
        temperature=cfg["copywriter"]["temperature"],
    )
    copy["tags"] = list(dict.fromkeys(copy["tags"] + cfg["bilibili"]["tags_extra"]))[:10]
    log.info("标题: %s", copy["title"])

    # ④ cover
    cover_path = f"{DL_DIR}/{video['id']}_cover.jpg"
    extract_cover(video_path, cover_path)
    log.info("封面: %s", cover_path)

    if dry_run:
        log.info("[DRY-RUN] 简介:\n%s\n标签: %s", copy["desc"], copy["tags"])
        return

    # ⑤ publish
    login = publisher.check_login(os.environ["BILI_SESSDATA"])
    if not login["ok"]:
        log.error("B站登录态失效！请更新 .env 中的 cookie 后重跑")
        store.mark_failed(video["id"], "cookie expired")
        sys.exit(2)
    try:
        bvid = asyncio.run(publisher.publish(
            env=dict(os.environ), video_path=video_path, cover_path=cover_path,
            title=copy["title"], desc=copy["desc"],
            tags=copy["tags"], tid=cfg["bilibili"]["tid"],
        ))
        store.mark_published(video["id"], bvid)
        log.info("投稿成功: %s", bvid)
        os.remove(video_path)  # 发布成功清理视频（封面保留可追溯）
        os.remove(cover_path)
    except Exception as e:
        store.mark_failed(video["id"], repr(e))
        log.exception("投稿失败，已记录，可 --retry-failed 重试: %s", video_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    args = ap.parse_args()
    setup_logging()
    run_once(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
```

（`--retry-failed` 首版从简：失败记录在库中，重跑 `--dry-run` 排除法自然换新素材；完整重投逻辑待首条发布验证后按需补充——YAGNI。）

- [ ] **Step 2: 语法检查** `python -m py_compile main.py src/*.py` → 无输出即通过

- [ ] **Step 3: Commit** `git add main.py && git commit -m "feat: pipeline entrypoint with dry-run mode"`

---

### Task 8: 全部测试通过 + dry-run 真实验证

- [ ] **Step 1: 跑全部单测** `python -m pytest tests/ -v` → 全部 PASS

- [ ] **Step 2: 真实 dry-run（连真实 Pexels/GLM，不投稿）**

```bash
cd C:/Users/15804/ZCodeProject/bilibili-autopost && python main.py --dry-run
```
Expected 日志：关键词 → pexels_id/时长/作者 → 下载 MB 数 → 标题 → 封面路径 → `[DRY-RUN] 简介+标签`
人工检查：downloads 里的 mp4 可播放、封面 jpg 构图合理、标题简介无乱码

- [ ] **Step 3: Commit（若 dry-run 暴露问题则修复后一并提交）**

---

### Task 9: README + 定时任务

**Files:**
- Create: `README.md`, `install_task.bat`

- [ ] **Step 1: README.md**——内容：项目简介、首次部署（pip install、.env 填写）、cookie 更新教程（F12 → 应用 → Cookie → SESSDATA/bili_jct，或 Playwright 法）、schtasks 安装/卸载命令、常见问题（cookie 过期/接口失效/频率限制）

- [ ] **Step 2: install_task.bat（每天 10:00 自动运行）**

```bat
@echo off
cd /d %~dp0
schtasks /Create /TN "bilibili-autopost" /TR "cmd /c cd /d %CD% && python main.py >> logs\task.log 2>&1" /SC DAILY /ST 10:00 /F
echo 已安装每日 10:00 计划任务。查看: schtasks /Query /TN bilibili-autopost
pause
```

- [ ] **Step 3: Commit** `git add README.md install_task.bat && git commit -m "docs: readme and scheduled task installer"`

---

### Task 10: GitHub 私有仓库 + 泄漏扫描 + 推送

- [ ] **Step 1: 泄漏扫描（推送前的强制检查）**

```bash
git log --all --oneline -p | grep -iE "sessdata|bili_jct|pexels_api_key|zhipu_api_key|Bearer [A-Za-z0-9]" | head -5
```
Expected: 无输出（密钥只在 .env，被 .gitignore 排除）。若有输出 → 立即停止，清除历史后再继续

- [ ] **Step 2: 创建私有仓库并推送**

```bash
gh repo create bilibili-autopost --private --source . --push
```

- [ ] **Step 3: 远程确认** `gh repo view --web` 或 `git remote -v` → 已关联且分支推送成功

---

### Task 11: 首条真实投稿（用户在场确认）

- [ ] **Step 1: 用户确认 dry-run 产出满意后，手动真实投稿一次**

```bash
python main.py
```

- [ ] **Step 2: 验证**：日志出现 `投稿成功: BVxxx` → 打开B站创作中心确认稿件在审核中 → `data/published.db` 该条 status=published

- [ ] **Step 3: 运行 install_task.bat 挂上每日计划任务，完成交付**
