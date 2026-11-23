# -*- coding: utf-8 -*-
"""
localscribe —— 本地视频/音频转文字工具

零 API 费用 · 中文优先 · 自动 GPU/CPU · 内置国内模型镜像
"""
import os

# 国内模型下载镜像（必须在导入 huggingface_hub 之前设置）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# Windows 下没有开发者模式时会提示符号链接警告，对使用没影响，关掉噪音
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

__version__ = "0.1.0"

MODEL_SIZES = {
    "tiny": "约 75 MB",
    "small": "约 500 MB",
    "medium": "约 1.5 GB",
    "large-v3": "约 3.2 GB",
    "turbo": "约 1.6 GB",
}

_DLL_HANDLES = []  # 保存句柄，防止 add_dll_directory 被回收


def setup_cuda_dlls():
    """Windows：把 pip 安装的 CUDA 运行库目录挂到 DLL 搜索路径。"""
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return
    nv = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin"):
        d = nv / sub
        if d.exists():
            _DLL_HANDLES.append(os.add_dll_directory(str(d)))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]


def gpu_available():
    """检测是否有可用的 CUDA 设备（只检测驱动，运行库缺失会在加载时回退）。"""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def load_audio(path):
    """用 imageio-ffmpeg 自带的 ffmpeg 把视频/音频解码成 16k 单声道 float32。"""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-nostdin", "-threads", "0", "-i", str(path),
        "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", "16000", "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("文件可能不是视频/音频，或者已经损坏")
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


def fmt_ts(seconds, sep="."):
    """秒数 → HH:MM:SS.毫秒"""
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", sep)


def model_error_hint(err):
    """把模型加载/下载失败翻译成一句能照做的建议。"""
    msg = str(err)
    hints = []
    low = msg.lower()
    if "cuda" in low or "cudnn" in low:
        hints.append("显卡运行库缺失或版本不匹配，可以加 --device cpu 先用 CPU")
    if any(k in low for k in ("connect", "timeout", "http", "ssl", "resolve", "network")):
        hints.append("下载模型失败：检查网络后重试；模型走 hf-mirror.com 镜像")
    hints.append("如果反复失败，把完整报错截图发给作者")
    return msg[:300] + "\n提示：" + "；".join(hints)


def main():
    ap = argparse.ArgumentParser(
        description="本地视频/音频转文字（零 API 费用）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("input", help="视频或音频文件路径")
    ap.add_argument(
        "--model", default="auto",
        choices=["auto", "tiny", "small", "medium", "large-v3", "turbo"],
        help="模型档位；auto = 有显卡用 turbo，无显卡用 small",
    )
    ap.add_argument("--lang", default="zh", help="语言代码，如 zh / en；auto = 自动检测")
    ap.add_argument(
        "--device", default="auto", choices=["auto", "cpu"],
        help="auto = 优先 GPU，失败自动退回 CPU",
    )
    ap.add_argument("--srt", action="store_true", help="同时输出 .srt 字幕")
    ap.add_argument("-o", "--output", help="输出 txt 路径（默认与输入同目录同名）")
    ap.add_argument("--version", action="version", version=f"localscribe {__version__}")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"文件不存在：{src}")
    if not src.is_file():
        sys.exit(f"这不是一个文件：{src}")
    if src.stat().st_size == 0:
        sys.exit(f"文件是空的（0 字节），没有可转写的内容：{src}")

    # 控制台编码兜底：生僻字显示为 ?，不崩溃
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    setup_cuda_dlls()
    from faster_whisper import WhisperModel

    has_gpu = args.device != "cpu" and gpu_available()
    device_pref = "cuda" if has_gpu else "cpu"

    model_name = args.model
    if model_name == "auto":
        model_name = "turbo" if has_gpu else "small"

    def load(dev):
        compute = "float16" if dev == "cuda" else "int8"
        try:
            # 有缓存就直接用本地模型，避免每次联网检查（镜像限流时这一步会卡很久）
            return WhisperModel(
                model_name, device=dev, compute_type=compute, local_files_only=True
            )
        except Exception as e:
            name = type(e).__name__
            msg = str(e).lower()
            if "LocalEntryNotFoundError" in name or "incomplete" in msg:
                # 本地没缓存或缓存不完整，才联网下载
                return WhisperModel(model_name, device=dev, compute_type=compute)
            raise

    device = "GPU" if device_pref == "cuda" else "CPU"
    size_hint = MODEL_SIZES.get(model_name, "")
    print(f"模型：{model_name}（{device}{'，' + size_hint if size_hint else ''}）")
    print("首次使用会自动下载模型，有进度条，请耐心等待……")

    t0 = time.time()
    try:
        model = load(device_pref)
    except Exception as e:
        if device_pref == "cuda":
            print(f"GPU 加载失败，改用 CPU 重试：{str(e)[:120]}")
            device = "CPU"
            try:
                model = load("cpu")
            except Exception as e2:
                sys.exit("模型加载失败：\n" + model_error_hint(e2))
        else:
            sys.exit("模型加载失败：\n" + model_error_hint(e))
    print(f"模型就绪，加载用时 {time.time() - t0:.1f} 秒")

    t1 = time.time()
    try:
        audio = load_audio(src)
    except Exception as e:
        sys.exit(f"读取音视频失败：{e}")

    print(f"音频时长：{len(audio) / 16000:.1f} 秒")

    language = None if args.lang == "auto" else args.lang

    def run(m):
        segs, info = m.transcribe(
            audio, language=language, vad_filter=True, log_progress=True
        )
        return list(segs), info  # 列表化，强制跑完再返回

    try:
        segs, info = run(model)
    except Exception as e:
        if device == "GPU":
            print(f"GPU 推理失败，改用 CPU 重新转写：{str(e)[:120]}")
            try:
                model = load("cpu")
            except Exception as e2:
                sys.exit("CPU 模型加载失败：\n" + model_error_hint(e2))
            device = "CPU"
            try:
                segs, info = run(model)
            except Exception as e3:
                sys.exit(f"转写失败：{str(e3)[:300]}\n提示：可以试试 --model small，或检查文件是否正常")
        else:
            sys.exit(f"转写失败：{str(e)[:300]}\n提示：可以试试 --model small，或检查文件是否正常")

    lang = info.language or (args.lang if args.lang != "auto" else "未知")
    print(f"识别语言：{lang}（置信度 {info.language_probability:.2f}）")
    print("-" * 50)

    lines, srt_lines = [], []
    for i, seg in enumerate(segs, 1):
        text = seg.text.strip()
        if not text:
            continue
        lines.append(text)
        print(f"[{fmt_ts(seg.start)}] {text}")
        if args.srt:
            srt_lines.append(
                f"{i}\n{fmt_ts(seg.start, ',')} --> {fmt_ts(seg.end, ',')}\n{text}\n"
            )

    out = Path(args.output) if args.output else src.with_suffix(".txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("-" * 50)
    print(f"完成，用时 {time.time() - t1:.1f} 秒（设备：{device}）")
    print(f"文本：{out}")

    if args.srt:
        srt_path = out.with_suffix(".srt")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        print(f"字幕：{srt_path}")

    print("小提示：识别错字属正常现象，重要内容请校对；总结提示词见 summary_prompt.txt。")


if __name__ == "__main__":
    main()