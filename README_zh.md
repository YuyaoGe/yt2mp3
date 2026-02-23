# yt2mp3

[English](README.md)

YouTube 视频批量下载转 MP3 命令行工具，支持完整元数据嵌入。

## 功能

- 批量下载 YouTube 视频并转为 MP3（或 m4a/opus/flac/wav）
- 多线程并发下载（默认 3 线程）
- 自动嵌入元数据：标题、作者、专辑、年份、封面图、同步歌词（LRC 格式）
- 直接从浏览器读取 cookies（Safari、Chrome、Firefox 等），无需手动导出
- 提取 YouTube 频道的全部视频链接
- 可配置音质、命名模板、代理、限速等参数
- 下载记录：自动跳过已下载的文件

## 依赖

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/)
- [deno](https://deno.land/)（yt-dlp 需要它来解决 YouTube JS 反爬）
- 在浏览器中保持 YouTube 登录状态（或准备 Netscape 格式 cookies 文件）

## 安装

```bash
# 克隆项目
git clone https://github.com/YuyaoGe/yt2mp3.git
cd yt2mp3

# 创建虚拟环境并安装依赖
python3.12 -m venv venv
source venv/bin/activate
pip install yt-dlp mutagen

# 安装系统依赖 (macOS)
brew install ffmpeg deno
```

## 使用方法

### 1. 下载 YouTube 视频为 MP3

准备一个 `input.txt`，每行一个 YouTube URL（`#` 开头为注释）：

```
# 我的播放列表
https://www.youtube.com/watch?v=xxxxx
https://www.youtube.com/watch?v=yyyyy
```

运行 shell 脚本（默认从 Safari 读取 cookies）：

```bash
bash run_download.sh
```

或直接调用 Python 脚本：

```bash
# 使用浏览器 cookies（推荐）
python3 yt2mp3.py input.txt -b safari

# 使用 cookies 文件
python3 yt2mp3.py input.txt -c cookies.txt
```

#### 完整参数

```
usage: yt2mp3.py [-h] [-c COOKIES] [-b BROWSER] [-o OUTPUT] [-q QUALITY]
                 [-f FORMAT] [-t THREADS] [--naming NAMING] [--no-metadata]
                 [--no-thumbnail] [--no-lyrics] [--subs-lang SUBS_LANG]
                 [--no-archive] [--proxy PROXY] [--limit-rate BYTES]
                 urls

  urls                  包含 YouTube URL 的文本文件（每行一个）
  -c, --cookies         Netscape 格式 cookies 文件（默认: cookies.txt）
  -b, --browser         从浏览器读取 cookies: safari, chrome, firefox,
                        edge, brave, opera, chromium。指定后忽略 --cookies
  -o, --output          输出目录（默认: output）
  -q, --quality         音频比特率 kbps: 64/96/128/192/256/320（默认: 128）
  -f, --format          音频格式: mp3/m4a/opus/flac/wav（默认: mp3）
  -t, --threads         并发下载线程数（默认: 3）
  --naming              文件命名模板（默认: "%(title)s"）
                        可用变量: %(title)s, %(channel)s, %(id)s, %(upload_date)s
  --no-metadata         不嵌入元数据（标题、作者、专辑、年份）
  --no-thumbnail        不嵌入封面图
  --no-lyrics           不下载和嵌入歌词/字幕
  --subs-lang           字幕语言偏好，逗号分隔（默认: "zh-Hans,zh,en"）
  --no-archive          禁用下载记录（重新下载全部）
  --proxy               代理地址（例: socks5://127.0.0.1:1080）
  --limit-rate          下载限速 bytes/s
```

### 2. 提取频道全部视频链接

```bash
# 修改 run_get_urls.sh 中的 CHANNEL_URL 后运行
bash run_get_urls.sh

# 或直接调用
python3 get_channel_urls.py https://www.youtube.com/@ChannelName -b safari -o urls.txt
```

## Shell 脚本配置

`run_download.sh` 和 `run_get_urls.sh` 顶部均有配置区域，直接编辑变量即可：

```bash
# run_download.sh
COOKIES_FROM_BROWSER="safari"    # 从浏览器读取 cookies（留空则使用 cookies 文件）
COOKIES_FILE="cookies.txt"      # 备用 cookies 文件
OUTPUT_DIR="output"
QUALITY="128"
FORMAT="mp3"
NAMING="%(title)s"
EMBED_METADATA="yes"
EMBED_THUMBNAIL="yes"
EMBED_LYRICS="yes"
SUBS_LANG="zh-Hans,zh,en"
USE_ARCHIVE="yes"
THREADS="3"
PROXY=""
LIMIT_RATE=""
```

## 工作原理

1. **下载**：yt-dlp 从 YouTube 下载最佳音频流
2. **转码**：FFmpeg 提取/转换音频到目标格式和比特率
3. **元数据**：FFmpegMetadata 写入基本标签；`MetadataFallbackPP` 补全缺失项（标题、作者、频道名作为专辑、年份）
4. **封面图**：yt-dlp 的 EmbedThumbnail 嵌入缩略图；`ThumbnailFallbackPP` 在失败时通过直接下载 URL 重试
5. **歌词**：下载 YouTube 字幕，解析为同步 LRC 格式，嵌入为 ID3 USLT 标签
6. **下载记录**：每次下载完成后记录到 `.archive.txt`（线程安全），下次运行时自动跳过

## 注意事项

- macOS 首次运行从浏览器读取 cookies 时可能弹出钥匙串访问授权提示，允许即可
- 使用 `--no-archive` 可以强制重新下载所有文件
- cookies 文件包含隐私信息，请勿提交到版本控制
- 下载记录按输出目录存储（输出目录内的 `.archive.txt`）

## License

MIT
