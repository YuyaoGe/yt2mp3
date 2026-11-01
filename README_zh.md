# yt2mp3

[English](README.md)

一键下载整个 YouTube 频道，转为 MP3 —— 封面、元数据、同步歌词，全部自动嵌入。

## 为什么选择 yt2mp3？

- **一条命令，整个频道** —— 提取任意 YouTuber 的全部视频链接，批量转为 MP3
- **开箱即听** —— 每个 MP3 自带标题、作者、专辑、年份、封面图和逐句同步歌词（LRC），导入任何音乐播放器即可使用
- **没有字幕也能有歌词** —— 视频本身没有字幕轨时，用 Whisper 在本地把语音转成文字，再作为同步歌词嵌入
- **无需手动导出 cookies** —— 直接从浏览器（Safari/Chrome/Firefox）读取登录状态，不需要安装任何浏览器扩展
- **快速且可断点续传** —— 多线程并发下载（默认 3 线程）；内置下载记录，重复运行自动跳过已下载的文件
- **多重回退保障** —— yt-dlp 内置的元数据或封面嵌入失败时，自定义回退处理器会自动重试
- **压缩后再上传** —— 可重新编码到更低比特率，同时完整保留全部 ID3 标签，歌词和封面都不丢
- **不只是转格式，还会清理** —— 删掉 Whisper 编出来的填充行，裁掉静音或音乐片尾，找出各集重复出现的片头片尾曲，试听后再决定删不删

## 完整流水线

```
链接 ─> 下载 ─> 转写 ─> 清理 ─> 裁片尾 ─> 检查 ─> (删除) ─> 压缩 ─> 导出
       yt2mp3.py transcribe.py strip_ads trim_tail find_repeats.py compress.py export_transcripts.py
```

`run_pipeline.sh` 把这些串起来。在脚本顶部改好配置，把链接放进 `input.txt`，然后：

```bash
bash run_pipeline.sh                 # 下载 -> 转写 -> 清理 -> 裁片尾 -> 检查
open review_output/index.html        # 试听找到的重复片段和静音
bash run_pipeline.sh apply R01,S03   # 删掉不要的编号
bash run_pipeline.sh finish          # 压缩；设了 EXPORT_DIR 还会导出文字稿
```

每一步也能单独跑：`bash run_pipeline.sh transcribe`、`... trim` 等。已下载的视频、已转写的文件会自动跳过；所有会改动文件的步骤都先把原文件备份到 `_untrimmed_backup/`。

| 步骤 | 做什么 |
|---|---|
| 下载 | 每个视频一个 MP3，带标题、作者、专辑、年份、封面，字幕作为同步歌词 |
| 转写 | 对还没有歌词的文件用 Whisper 转写（Apple Silicon，MLX） |
| 清理 | 删掉 Whisper 在音乐或静音处编出来的行（字幕组署名、一个词刷屏）和口播广告 |
| 裁片尾 | 裁掉结尾静音和最后一句话之后的片尾音乐；无损，标签和歌词保留 |
| 检查 | 给每集算声学指纹，找出各集重复出现的音频（片头片尾曲、插入的推广）以及开头、结尾和中途的静音，生成一个可以逐段试听的网页 |
| 删除 | 把你选中的编号从所有出现过的集里剪掉，位置不限，歌词时间轴同步前移 |
| 压缩 | 生成 64 kbps 单声道副本，保留全部标签 |
| 导出 | 可选：每集一份 Markdown 文字稿加一个目录，段首带 `[mm:ss]` |

下面的分步说明是同一套工具一个一个地用。

## 快速开始

### 第一步：提取频道的全部视频链接

编辑 `run_get_urls.sh`，将 `CHANNEL_URL` 改为目标频道地址：

```bash
CHANNEL_URL="https://www.youtube.com/@YourFavoriteChannel"
```

运行：

```bash
bash run_get_urls.sh
```

这会生成一个 `channel_urls.txt` 文件，包含该频道的全部视频链接。

### 第二步：批量下载为 MP3

将链接文件复制或重命名为 `input.txt`（或在脚本中修改 `INPUT_FILE`）：

```bash
cp channel_urls.txt input.txt
bash run_download.sh
```

完成。所有视频被下载为 MP3 文件，存放在 `output/` 目录中，自动附带元数据、封面和歌词。

### 第三步（可选）：用 Whisper 补齐缺失的歌词

很多视频压根没有字幕轨，也就无从嵌入。这时可以在本地把语音转成文字：

```bash
bash run_transcribe.sh
```

脚本会扫描 `output/`，跳过已有歌词的文件，其余交给 Whisper 用 GPU 转写，并把结果作为逐句同步的 LRC 嵌入。过长的句子会按标点切分，保证每行短到边听边看得过来。

### 第四步（可选）：压缩体积

人声讲解用不上 128 kbps 立体声。重新编码成 64 kbps 单声道，体积大约减半：

```bash
python3 compress.py output/
```

结果输出到 `output_small/`，原文件不动。转码后会用 mutagen 把标签整块搬过去 —— 单靠 ffmpeg 会静默丢掉歌词帧 —— 并在报告成功前逐个校验。

## 附：整理手头已有的音频

转写和打标签这两步并不关心音频从哪来。如果你手上有一整个文件夹的课程或讲座音频，
`organize.py` 可以把它整理成在播放器里一眼看得懂的资料库：

```bash
python3 organize.py "~/Downloads/某某课程" -o "podcast/某某课程" \
    -a "某某课程" --artist "作者" --dry-run
```

它会从文件名里解析出集数和标题，按所在目录和日期排出收听顺序，并写入干净的
标题/作者/专辑/音轨号。二手转卖的课程音频常常被塞进店家的广告——藏在作者、专辑
和封面图里——而标签块是整个重建的，广告随之消失。建议先加 `--dry-run` 确认命名，
再去掉这个参数正式复制。原文件全程只读，不会改动。

`make_cover.py` 用来生成一张文字封面，供本来就没有配图的音频使用。给它标题、
作者和三个颜色即可，英文小字和细线的颜色由这三色混合得出，因此一整套专辑可以
共用同一版式而彼此又能分辨：

```bash
python3 make_cover.py "某某课程/第二季" -s "作者" \
    --caption "a course in something" -o cover.jpg \
    -c "#f4efe2" --ink "#23201c" --accent "#a63f2c"
```

在标签里塞广告的转卖者，往往也会在每集的头尾念一段口播，转写后就混进了歌词。
`strip_ads.py` 负责把这些行删掉：

```bash
python3 strip_ads.py "podcast/某某课程" --dry-run
```

它匹配电话号码和几句固定话术，并会顺带删掉广告常常溢出到的那半句短行。建议先用
`--dry-run` 看一遍报告，确认无误再正式写入。它默认还会删掉 Whisper 编出来的填充行
（加 `--keep-hallucinations` 可关闭）。

## 更多工具

**裁掉静音或音乐片尾** —— `trim_tail.py` 在以下两个位置中取较早的一个剪断：
(a) 一直持续到结尾的静音开始处；(b) 最后一句真正的话之后、后面只剩音乐的地方。
无损剪切（`-c copy`），标签和封面保留，剪点之后的歌词行一并删除：

```bash
python3 trim_tail.py output/ --dry-run
python3 trim_tail.py output/ --also output_small --backup _untrimmed_backup
```

**找出并删除重复音频** —— `find_repeats.py` 给每个文件算声学指纹，两两做互相关，
所以片头曲、片尾曲、插在中间的推广片段，即便每次混音略有不同也能找出来。它同时列出
开头、结尾的静音和较长的中途静音。在你挑选之前不会改动任何文件：

```bash
python3 find_repeats.py output/ review/              # 生成 review/index.html，可逐段试听
python3 find_repeats.py output/ review/ --apply R01,S02 --backup _untrimmed_backup
```

**从画面硬字幕提取歌词** —— 视频没有声音、字幕却印在画面上时，`burnin_subs.py`
用 macOS 自带的 Vision 文字识别（通过 `ocr_frames.swift`，无需额外安装）读出字幕，
作为同步歌词嵌入：

```bash
python3 burnin_subs.py video.mp4 "output/那一集.mp3" --dry-run
```

**导出文字稿** —— `export_transcripts.py` 把一个目录里嵌入的歌词导出成每集一份的
Markdown（合并成段落，段首带 `[mm:ss]`），外加一个 `index.md`，方便阅读或交给其他工具：

```bash
python3 export_transcripts.py output/ transcripts/ --course "我的资料"
```

## 依赖

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/)
- [deno](https://deno.land/)（yt-dlp 需要它来解决 YouTube JS 反爬验证）
- 在浏览器中保持 YouTube 登录状态
- 转写这一步需要 Apple Silicon 芯片的 Mac（`mlx-whisper` 跑在 Metal 上）

## 安装

```bash
git clone https://github.com/YuyaoGe/yt2mp3.git
cd yt2mp3

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# macOS
brew install ffmpeg deno
```

首次转写会自动下载 Whisper 权重（默认 `turbo` 模型约 1.6 GB），缓存在 `~/.cache/huggingface`。

## 项目结构

```
yt2mp3/
├── run_pipeline.sh       # 整条流水线（编辑配置后运行）
├── run_get_urls.sh       # 第一步：提取频道视频链接（编辑配置后运行）
├── get_channel_urls.py   # 链接提取逻辑
├── run_download.sh       # 第二步：批量下载为 MP3（编辑配置后运行）
├── yt2mp3.py             # 下载与转码逻辑
├── run_transcribe.sh     # 第三步：转写补齐歌词（编辑配置后运行）
├── transcribe.py         # Whisper 转写 -> LRC -> 写入 ID3
├── strip_ads.py          # 删掉歌词里的 Whisper 填充行和口播广告
├── trim_tail.py          # 裁掉静音或音乐片尾
├── find_repeats.py       # 找出重复的片头片尾曲和静音，试听后删除
├── compress.py           # 第四步：压缩体积，保留全部标签
├── export_transcripts.py # 歌词 -> Markdown 文字稿 + 目录
├── burnin_subs.py        # 从画面硬字幕识别歌词（OCR）
├── ocr_frames.swift      # burnin_subs.py 用的 macOS Vision 识别脚本
├── organize.py           # 附加：把一堆音频整理成播客资料库
├── make_cover.py         # 附加：给没有配图的音频生成文字封面
├── local/                # 你自己的配置（*.conf），不进 git
├── input.txt             # 你的链接列表（每行一个，# 为注释）
├── output/               # 下载的 MP3 文件存放在这里
└── output_small/         # 压缩后的副本存放在这里
```

**典型工作流：** `run_get_urls.sh` -> `input.txt` -> `run_pipeline.sh` -> 试听 -> `run_pipeline.sh apply ...` -> `run_pipeline.sh finish`

你只需要编辑 shell 脚本并运行它们，`.py` 文件在后台处理一切。

## 配置说明

每个 shell 脚本顶部都有清晰标注的配置区域。不想把自己的设置提交进 git，就写到 `local/<脚本名>.conf` 里（例如 `local/run_pipeline.conf` 里写 `COOKIES_FROM_BROWSER="edge"`）；脚本会在默认值之后读取它，`local/` 已被 git 忽略。

### run_get_urls.sh

```bash
CHANNEL_URL="https://www.youtube.com/@ChannelName"   # 目标频道地址
OUTPUT_FILE="channel_urls.txt"                        # 输出文件名
COOKIES_FROM_BROWSER="safari"    # 从哪个浏览器读取 cookies（留空则使用 cookies 文件）
COOKIES_FILE="cookies.txt"      # 备用：Netscape 格式 cookies 文件
MAX_COUNT="0"                   # 最多提取视频数（0 = 全部）
PROXY=""                        # 代理地址（例: socks5://127.0.0.1:1080）
```

### run_download.sh

```bash
INPUT_FILE="input.txt"          # 链接列表文件
COOKIES_FROM_BROWSER="safari"   # 从哪个浏览器读取 cookies
COOKIES_FILE="cookies.txt"     # 备用 cookies 文件
OUTPUT_DIR="output"            # 输出目录
QUALITY="128"                  # 比特率: 64/96/128/192/256/320 kbps
FORMAT="mp3"                   # 格式: mp3/m4a/opus/flac/wav
NAMING="%(title)s"             # 文件命名模板
EMBED_METADATA="yes"           # 嵌入标题、作者、专辑、年份
EMBED_THUMBNAIL="yes"          # 嵌入封面图
EMBED_LYRICS="yes"             # 嵌入同步歌词
SUBS_LANG="zh-Hans,zh,en"     # 字幕语言偏好
USE_ARCHIVE="yes"              # 跳过已下载的文件
THREADS="3"                    # 并发下载线程数
PROXY=""                       # 代理地址
LIMIT_RATE=""                  # 下载限速（bytes/s）
SLEEP=""                       # 每集下载前随机等待 SLEEP~2×SLEEP 秒
```

### run_transcribe.sh

```bash
TARGET_DIR="output"             # 要处理的目录（也可写单个文件路径）
MODEL="turbo"                   # 模型: turbo / large / medium / small
LANGUAGE="zh"                   # 语言代码，留空则自动识别
ZH_VARIANT="simp"               # 中文字形: auto（不转换）/ trad（繁体）/ simp（简体）
PROMPT=""                       # 引导词，填入专有名词可减少同音字错误
SAVE_LRC="no"                   # 是否额外导出 .lrc 文件
FORCE="no"                      # 是否重新转写已有歌词的文件
THREADS="3"                     # 并发进程数
```

两点值得留意：

- 引导词既影响用词也影响字形。用繁体写的引导词会让模型倾向输出繁体，所以请和 `ZH_VARIANT` 保持一致。
- 已经嵌好的歌词想在简繁之间切换，不必重跑模型：`python3 transcribe.py output/ --zh-variant simp --convert-only`。

## 进阶：直接使用命令行

你也可以直接调用 Python 脚本来获得更精细的控制：

```bash
# 提取链接
python3 get_channel_urls.py https://www.youtube.com/@ChannelName -b safari -o urls.txt -n 50

# 下载
python3 yt2mp3.py urls.txt -b safari -q 320 -t 5 -o music/
python3 yt2mp3.py urls.txt -b chrome -f m4a --no-lyrics
python3 yt2mp3.py urls.txt -c cookies.txt --proxy socks5://127.0.0.1:1080

# 转写歌词
python3 transcribe.py output/ -l zh -t 3
python3 transcribe.py output/ -m large --save-lrc
python3 transcribe.py output/ --zh-variant simp --convert-only

# 压缩
python3 compress.py output/ -b 64
python3 compress.py output/ -b 96 --stereo -o output_hq/

# 清理、裁片尾、检查
python3 strip_ads.py output/ --dry-run
python3 trim_tail.py output/ --dry-run
python3 find_repeats.py output/ review/ && python3 find_repeats.py output/ review/ --apply R01
```

每个脚本都有 `--help` 可以查看全部选项。

## 嵌入的元数据

每个下载的 MP3 包含以下信息：

| 标签 | 数据来源 | 示例 |
|------|---------|------|
| 标题 | 视频标题 | `我的歌曲` |
| 作者 | 频道名称 | `频道名` |
| 专辑 | 频道名称 | `频道名` |
| 年份 | 上传日期 | `2024` |
| 封面 | 视频缩略图 | （嵌入图片） |
| 歌词 | YouTube 字幕，或 Whisper 转写 | 逐句同步 LRC 格式 |

歌词以 LRC 文本写在 ID3 的 `USLT` 帧里，所以单个 `.mp3` 就装齐了全部信息，拷贝或上传时不需要额外照看伴生文件。

## 注意事项

- macOS 首次从浏览器读取 cookies 时可能弹出钥匙串访问授权提示，允许即可
- Safari 的 cookie 库受 macOS 隐私保护，沙盒终端可能读不到。这种情况改为导出 `cookies.txt`，并把 `COOKIES_FROM_BROWSER` 留空
- 同一账号并发请求过多时，YouTube 会轮换会话 cookie。导出的 `cookies.txt` 是固定的一份，下几十个视频就会失效（报 "Sign in to confirm you're not a bot"）；直接从浏览器读取（`-b edge`、`-b chrome` 等）则一直有效，因为浏览器会持续刷新会话
- 有些视频没有单独的音轨，下载器会改选格式 18（单个 360p 文件，自带 AAC 音频），而不是几百个 HLS 分片
- 如果运行环境不允许一次删除大量文件，给 `yt2mp3.py` 加 `--keep-intermediate`，残留的视频和缩略图之后自己清理
- 设置 `USE_ARCHIVE="no"` 或使用 `--no-archive` 可强制重新下载所有文件
- 下载记录文件（`.archive.txt`）存放在输出目录内
- cookies 文件包含隐私信息，请勿提交到版本控制

## License

MIT
