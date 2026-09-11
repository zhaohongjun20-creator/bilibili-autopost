# bilibili-autopost

自动从免费素材库（Pexels）收集视频 → GLM 生成文案 → 自动投稿到哔哩哔哩。
每天一条，无人值守，Windows 计划任务驱动。

## 工作流程

```
搜索 Pexels（多关键词自动降级） → 筛选横屏/60-180s → 下载
→ GLM 生成标题/简介/标签（含素材来源声明） → ffmpeg 抽帧封面
→ B站投稿 → SQLite 记录去重
```

## 首次部署

```bash
cd bilibili-autopost
pip install -r requirements.txt
copy .env.example .env   # 然后编辑 .env 填入下方三组密钥
python main.py --dry-run # 试跑（不投稿），检查 downloads/ 里的产出
python main.py           # 真实投稿一条
install_task.bat         # 双击安装每日 10:00 计划任务
```

## 密钥获取（.env）

| 变量 | 获取方式 |
|------|---------|
| `PEXELS_API_KEY` | https://www.pexels.com/api/ 免费注册，即时发放 |
| `ZHIPU_API_KEY` | https://open.bigmodel.cn 控制台创建（glm-4-flash 免费） |
| `BILI_SESSDATA` / `BILI_JCT` / `BILI_UID` | 见下方「更新 B站 Cookie」 |

## 更新 B站 Cookie（约每月一次）

Cookie 过期时日志会出现 `B站登录态失效`，更新步骤：

1. Edge/Chrome 登录 bilibili.com
2. F12 → 应用 → 存储 → Cookie → `https://www.bilibili.com`
3. 复制 `SESSDATA`、`bili_jct`、`DedeUserID` 三个值，替换 `.env` 对应行
4. 重跑 `python main.py` 验证

## 配置说明（config.yaml）

- `keywords` — 素材主题关键词，可自由增删（建议用英文，Pexels 搜索以英文为主）
- `bilibili.tid` — 投稿分区（160=生活·日常），其他分区 id 见B站创作中心
- `copywriter.model` — `glm-4-flash`（免费）或 `glm-4.6`（更强，按量计费）

## 常见问题

- **所有关键词均无可用新素材** — 素材被发完了，往 `config.yaml` 加新关键词
- **412 / 登录态失效** — 更新 cookie（见上）
- **投稿失败** — 视频文件保留在 downloads/，查明原因后可重跑
- **频率建议** — 默认每天 1 条；新账号不建议超过 2 条/天

## 合规说明

仅使用 Pexels License（免费商用、无需授权）素材；简介自动注明素材来源与原作者。
请勿将本工具用于搬运受版权保护的内容。
