# localscribe · 本地视频转文字

**本地抄写员**：把视频/音频转成文字，全程在本机完成。零 API 费用、不注册、不上传。

## 特性

- **完全本地**：识别在本机跑，音视频不上传（首次运行会从镜像站下载模型，之后可离线使用）
- **中文优先**：默认中文识别，自带标点
- **自动适配硬件**：有 NVIDIA 显卡自动用 GPU（turbo 模型），没有就用 CPU（small 模型）；GPU 出问题会自动退回 CPU
- **国内友好**：模型走 hf-mirror.com 镜像下载，不用翻墙
- **输出简单**：生成同名 `.txt`；加 `--srt` 顺便输出字幕
- **可选总结**：附 `summary_prompt.txt`，把转写文本贴到 Kimi / DeepSeek / 豆包等网页版就能总结，不用 API、不花钱；有 Claude Code 的话，直接把 `.txt` 交给它总结即可

## 安装

### Windows 一键（推荐）

1. 安装 Python 3.9 或更高版本：<https://www.python.org/downloads/>
   安装时务必勾选 **Add python.exe to PATH**
2. 双击 `setup.bat`，按提示走（检测到 NVIDIA 显卡会问要不要装 GPU 加速库）
   `setup.bat` 的提示是英文——Windows 命令行对中文批处理兼容差，中文说明以本 README 为准。

### 手动安装

```bash
pip install -r requirements.txt

# 有 NVIDIA 显卡、想开 GPU 加速（Windows 推荐）：
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## 用法

```bash
# 最简单：把视频/音频文件拖到 run.bat 上（一次一个）

# 或者在命令行运行
python localscribe.py 视频.mp4

# 同时输出 .srt 字幕
python localscribe.py 视频.mp4 --srt

# 指定模型档位
python localscribe.py 视频.mp4 --model medium

# 英文视频 / 自动检测语言
python localscribe.py 视频.mp4 --lang en
python localscribe.py 视频.mp4 --lang auto
```

## 模型档位

| 档位 | 大小 | 适合 |
|---|---|---|
| tiny | 约 75 MB | 只求快，精度一般 |
| small | 约 500 MB | **没显卡时的默认** |
| medium | 约 1.5 GB | 平衡，CPU 也能跑 |
| turbo | 约 1.6 GB | **有显卡时的默认**，快且较准 |
| large-v3 | 约 3.2 GB | 最准，也最慢 |

不指定 `--model` 时为 `auto`：有显卡用 turbo，没显卡用 small。模型第一次使用会自动下载，之后复用，不会重复下载。

## 常见问题

**第一次运行像卡住了？**
首次要下载模型（75 MB ~ 3.2 GB），有进度条，慢的时候请等一等；下载完成后不再需要网络。

**模型下载慢或失败？**
已内置 hf-mirror.com 镜像。仍然失败时检查网络后重试；也可以手动设置环境变量：

```bat
set HF_ENDPOINT=https://hf-mirror.com
```

**转完有错字？**
正常。模型对专业术语、同音字会出错（比如「实训」→「时讯」、「LoRa」→「LOL」）。重要内容建议人工校对，或换更大的模型。

**为什么这么慢？**
没有显卡时，CPU 转写 1 小时视频可能要 1~3 小时。装 NVIDIA 显卡 + 上面的两个 CUDA 运行库包会快很多。

**支持哪些格式？**
所有 ffmpeg 能读的格式：mp4 / mkv / avi / mov / mp3 / m4a / wav / flac 等。

**生僻字显示成问号？**
那是控制台编码限制，不影响写进 txt 文件的内容（文件是 UTF-8）。

## 隐私

- 转写完全在本机进行，音频和文字都不会上传。
- 首次运行会从 Hugging Face 或其镜像 hf-mirror.com 下载模型文件；之后可以离线使用。
- 镜像地址可以通过环境变量更改或关闭（`HF_ENDPOINT`）。
- 如果把转写文本贴进网页版 AI 做总结（见 `summary_prompt.txt`），文本会上传给对应的服务——涉密内容不要贴。

## 免责声明

- 转写结果不保证准确，正式场合请人工校对。
- 请只转写你拥有版权或已获得授权的内容。

## 反馈

遇到问题请到 GitHub Issues 反馈，附上：系统版本、是否有显卡、报错截图。

## 未来计划（v0.2+）

- 批量处理整个文件夹
- 超长视频的分块处理
- 画面理解（场景抽帧 + OCR）
- 可选的自动总结（Claude Code CLI / OpenAI 兼容接口 / 本地 Ollama）

单文件版本是一切的起点：先把这一层做稳，再往上长。

## 许可

[MIT License](LICENSE)