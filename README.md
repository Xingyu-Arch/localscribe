# localscribe · 本地视频转文字

**本地抄写员**：把视频/音频转成文字，全程在本机完成。零 API 费用、不注册、不上传。

> **第一次用、不想碰命令行？**
> 到 [Releases](https://github.com/Xingyu-Arch/localscribe/releases) 下载 `localscribe-v0.1.1.zip`（**不是** Source code），解压后先看 **README-FIRST.txt**，照着三步做就行。
> 只想检查环境：双击 `CHECK.bat`。

## 特性

- **完全本地**：识别在本机跑，音视频不上传（首次运行会从镜像站下载模型，之后可离线使用）
- **中文优先**：默认中文识别，自带标点
- **自动适配硬件**：有 NVIDIA 显卡自动用 GPU（turbo 模型），没有就用 CPU（small 模型）；GPU 出问题会自动退回 CPU
- **国内友好**：模型走 hf-mirror.com 镜像下载，不用翻墙；默认关闭 hf-xet，下载中断后不会从头再来
- **输出简单**：生成同名 `.txt`；加 `--srt` 顺便输出字幕
- **批量**：一次可以处理多个文件，支持 `*.mp4` 通配符
- **可选总结**：附 `summary_prompt.txt`，把转写文本贴到 Kimi / DeepSeek / 豆包等网页版就能总结，不用 API、不花钱；有 Claude Code 的话，直接把 `.txt` 交给它总结即可

## 安装

### Windows 一键（推荐）

1. 安装 **Python 3.12（64 位）**：<https://www.python.org/downloads/>
   安装时务必勾选 **Add python.exe to PATH**
   > 为什么要 3.12：本版锁定了 `ctranslate2 4.5.0`，它没有 Python 3.13/3.14 的 Windows 轮子，装不上。
   > 3.9~3.11 理论上也能用，但本版只在 3.12 上实测过。
2. 双击 `setup.bat`，按提示走
   - 检测到 NVIDIA 显卡会问要不要装 GPU 加速库（约 **1.3 GB**）
   - 不要交互：`setup.bat /auto`；要装 GPU 库：`setup.bat /gpu`；只要 CPU：`setup.bat /cpu`
   - `setup.bat` 的提示是英文——Windows 命令行对中文批处理兼容差，中文说明以本 README 为准。

体积参考：CPU 依赖约 **50~100 MB**；GPU 加速库另加约 **1.3 GB**。

### 手动安装

```bash
pip install -r requirements.txt

# 有 NVIDIA 显卡、想开 GPU 加速（Windows 推荐，约 1.3 GB）：
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## 用法

```bash
# 最简单：把视频/音频文件拖到 run.bat 上（可以一次拖多个）

# 或者在命令行运行
python localscribe.py 视频.mp4

# 多个文件 / 通配符
python localscribe.py a.mp4 b.mp3
python localscribe.py "*.mp4"        # 由程序展开通配符
run.bat "*.mp4" /q                   # /q = 结束不暂停，方便脚本调用

# 同时输出 .srt 字幕
python localscribe.py 视频.mp4 --srt

# 指定模型档位
python localscribe.py 视频.mp4 --model medium

# 英文视频 / 自动检测语言
python localscribe.py 视频.mp4 --lang en
python localscribe.py 视频.mp4 --lang auto

# 环境自检（装不上、闪退、想发 issue 时先跑这个）
python localscribe.py --doctor

# onnxruntime 出问题、VAD 一直崩时，先关掉静音过滤
python localscribe.py 视频.mp4 --no-vad
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

**双击后窗口一闪就没了？**
这是原生崩溃，没有 Python 报错。先跑 `--doctor` 看环境；再按顺序试：

1. 装最新的 VC++ 运行库：<https://aka.ms/vs/17/release/vc_redist.x64.exe>
2. 加 `--no-vad`（先绕开 onnxruntime 的静音过滤）
3. 加 `--device cpu`（先绕开显卡运行库）

还不行就把 `--doctor` 的输出和闪退前的画面发到 GitHub Issues。

**为什么锁着旧版本，不装最新的？**
根因已定位（2026-11-26）：`ctranslate2 4.6+` / `onnxruntime 1.22+` 用 VS2022 编译，需要 **VC++ 运行库 14.40+**；旧运行库（如 14.28）上会直接闪退，而且没有 Python 报错。`4.5.0 / 1.19.2` 是 VS2019 编译的，新旧运行库都能跑，所以作为默认组合，保证「装完就能用」。
想用最新版：先装 [VC++ 运行库 14.40+](https://aka.ms/vs/17/release/vc_redist.x64.exe)，再执行 `pip install "ctranslate2==4.9.1" "onnxruntime==1.32.0"`（测试者已验证这套组合）。`--doctor` 会显示当前 msvcp140.dll 版本。

**模型下载慢或失败？**
已内置 hf-mirror.com 镜像，并默认关闭 hf-xet（分块下载中途崩了会从头来，普通 HTTP 可以续传）。
仍然慢的话：换个网络或时段；模型缓存目录在 `%USERPROFILE%\.cache\huggingface\hub`，可以整个目录拷到别人机器上用。
也可以手动设置环境变量：

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

遇到问题请到 GitHub Issues 反馈，附上：

- `python localscribe.py --doctor` 的完整输出
- 系统版本、是否有显卡、报错截图

## 更新日志

### v0.1.1（2026-11-25）

- 根因定位（2026-11-26）：`ctranslate2 4.6+` / `onnxruntime 1.22+` 需要 VC++ 运行库 14.40+，旧运行库上会无报错闪退
- 默认锁定兼容组合（ctranslate2 4.5.0 / onnxruntime 1.19.2 / faster-whisper 1.2.1），新旧运行库都能「装完即用」
- 新增 VC++ 运行库检测：`--doctor` 显示 msvcp140.dll 版本；`setup.bat` 安装前检查；启动时仅在「新版依赖 + 旧运行库」时警告
- 新增 `--doctor` 环境自检（Python / ct2 / onnxruntime / VAD / CUDA / 模型缓存 / VC++ 运行库）
- 新增 `--no-vad`；VAD 初始化失败会自动关闭并提示
- 主流程加 `faulthandler`，原生崩溃会留下调用栈
- 默认关闭 hf-xet，模型下载更稳、可续传
- `run.bat` 支持多文件和通配符，新增 `/q`
- `setup.bat` 支持 `/auto` `/gpu` `/cpu`，不再强制交互；引导使用 Python 3.12
- 修正安装体积说明（GPU 库约 1.3 GB）

### v0.1.0（2026-11-24）

- 首个版本：本地转写、中文优先、GPU/CPU 自动切换、srt、国内镜像

## 未来计划（v0.2+）

- 整个文件夹（递归）批量处理
- 超长视频的分块处理
- 画面理解（场景抽帧 + OCR）
- 可选的自动总结（Claude Code CLI / OpenAI 兼容接口 / 本地 Ollama）

单文件版本是一切的起点：先把这一层做稳，再往上长。

## 许可

[MIT License](LICENSE)