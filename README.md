# yt2mp3

YouTube 视频批量下载并转换为 MP3 的命令行工具，支持元数据嵌入（标题、作者、封面）。

## 功能

- 批量下载 YouTube 视频并转为 MP3（或 m4a/opus/flac/wav）
- 自动嵌入元数据（标题、作者、专辑、封面图）
- 提取 YouTube 频道的全部视频链接
- 为已有 MP3 文件补充元数据
- 支持自定义音质、命名模板、代理等参数
- 断点续传：跳过已下载的文件

## 依赖

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/)
- [deno](https://deno.land/)（yt-dlp JS challenge 求解需要）
- YouTube cookies（Netscape 格式，可用 [Cookie-Editor](https://cookie-editor.com/) 浏览器扩展导出）

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

将 cookies 导出为 Netscape 格式，保存为 `cookies.txt`，然后运行：

```bash
bash run_download.sh
```

或直接调用 Python 脚本：

```bash
python3 yt2mp3.py input.txt -c cookies.txt -o output -q 128
```

完整参数列表：

```
python3 yt2mp3.py --help

  -c, --cookies       cookies 文件 (默认: cookies.txt)
  -o, --output        输出目录 (默认: output)
  -q, --quality       音频比特率 kbps (64/96/128/192/256/320, 默认: 128)
  -f, --format        音频格式 (mp3/m4a/opus/flac/wav, 默认: mp3)
  --naming            文件命名模板 (默认: "%(title)s")
  --no-metadata       不嵌入元数据
  --no-thumbnail      不嵌入封面图
  --no-archive        禁用下载记录（重新下载全部）
  --proxy             代理地址 (例: socks5://127.0.0.1:1080)
  --limit-rate        下载限速 bytes/s
```

### 2. 提取频道全部视频链接

```bash
# 修改 run_get_urls.sh 中的 CHANNEL_URL 后运行
bash run_get_urls.sh

# 或直接调用
python3 get_channel_urls.py https://www.youtube.com/@ChannelName -o urls.txt
```

## Shell 脚本配置

`run_download.sh` 和 `run_get_urls.sh` 顶部均有可修改参数区域，直接编辑即可：

```bash
# run_download.sh 可配置参数
INPUT_FILE="input.txt"
COOKIES_FILE="cookies.txt"
OUTPUT_DIR="output"
QUALITY="128"
FORMAT="mp3"
NAMING="%(title)s"
EMBED_METADATA="yes"
EMBED_THUMBNAIL="yes"
USE_ARCHIVE="yes"
PROXY=""
LIMIT_RATE=""
```

## 注意事项

- YouTube 会在自动化访问期间轮换 cookies，长时间运行可能需要重新导出 cookies
- 使用 `--no-archive` 可以强制重新下载所有文件
- cookies 文件包含隐私信息，请勿提交到版本控制

## License

MIT
