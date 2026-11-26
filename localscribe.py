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
# hf-xet 分块下载在部分网络下会中途断掉、而且不续传，默认走普通 HTTP（设成 0 可恢复）
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import argparse
import faulthandler
import glob
import platform
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API.*")

__version__ = "0.1.1"

MODEL_SIZES = {
    "tiny": "约 75 MB",
    "small": "约 500 MB",
    "medium": "约 1.5 GB",
    "large-v3": "约 3.2 GB",
    "turbo": "约 1.6 GB",
}

MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

_DLL_HANDLES = []  # 保存句柄，防止 add_dll_directory 被回收


class ToolError(Exception):
    """可以直接给人看的错误。"""


def short(err, limit=160):
    """错误信息压成一行。"""
    return str(err).strip().replace("\r", " ").replace("\n", " ")[:limit]


def version_tuple(text, parts=2):
    """'4.9.1' → (4, 9)；解析不了返回 None。"""
    try:
        return tuple(int(x) for x in str(text).strip().split(".")[:parts])
    except Exception:
        return None


def msvc_runtime_version():
    """读取 System32\\msvcp140.dll 的文件版本，如 (14, 51, 36247)；读不到返回 None。

    ctranslate2 4.6+ / onnxruntime 1.22+ 用 VS2022 编译，需要 14.40+。
    旧运行库（如 14.28）上会直接闪退，而且没有 Python 报错。
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        path = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32", "msvcp140.dll",
        )
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf)
        ptr = ctypes.c_void_p()
        length = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buf, "\\", ctypes.byref(ptr), ctypes.byref(length)
        ):
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
                ("dwFileFlagsMask", wintypes.DWORD),
                ("dwFileFlags", wintypes.DWORD),
                ("dwFileOS", wintypes.DWORD),
                ("dwFileType", wintypes.DWORD),
                ("dwFileSubtype", wintypes.DWORD),
                ("dwFileDateMS", wintypes.DWORD),
                ("dwFileDateLS", wintypes.DWORD),
            ]

        info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        return (
            info.dwFileVersionMS >> 16,
            info.dwFileVersionMS & 0xFFFF,
            info.dwFileVersionLS >> 16,
        )
    except Exception:
        return None


def _site_packages_dirs():
    """venv 的 site-packages；用 --system-site-packages 时也查全局。"""
    roots = [Path(sys.prefix)]
    base = Path(getattr(sys, "base_prefix", sys.prefix))
    if base != roots[0]:
        roots.append(base)
    return [r / "Lib" / "site-packages" for r in roots]


def setup_cuda_dlls():
    """Windows：把 pip 安装的 CUDA 运行库目录挂到 DLL 搜索路径。"""
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return
    seen = set()
    for sp in _site_packages_dirs():
        nv = sp / "nvidia"
        for sub in ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin"):
            d = nv / sub
            if d.exists() and str(d) not in seen:
                seen.add(str(d))
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
        raise ToolError("文件可能不是视频/音频，或者已经损坏")
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
    if "0xc0000005" in low or "access violation" in low:
        hints.append("这是原生崩溃：先把 VC++ 运行库更新到最新，再试 --no-vad 或 --device cpu")
    hints.append("如果反复失败，把 --doctor 的输出和完整报错发给作者")
    return msg[:300] + "\n提示：" + "；".join(hints)


def collect_inputs(raw):
    """展开通配符、去掉重复的文件。"""
    out = []
    for item in raw:
        item = os.path.expanduser(item)
        if any(ch in item for ch in "*?["):
            matched = sorted(glob.glob(item))
            if not matched:
                print(f"[跳过] 没有匹配的文件：{item}")
            out.extend(matched)
        else:
            out.append(item)

    seen, uniq = set(), []
    for p in out:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def transcribe_audio(model, audio, language, use_vad):
    segs, info = model.transcribe(
        audio, language=language, vad_filter=use_vad, log_progress=True
    )
    return list(segs), info  # 列表化，强制跑完再返回


def transcribe_with_fallback(audio, state, load, language):
    """VAD 出错 → 关 VAD 重试；GPU 出错 → 换 CPU 重试。"""

    def attempt(use_vad):
        return transcribe_audio(state["model"], audio, language, use_vad)

    err = None
    try:
        return attempt(state["vad"])
    except Exception as e:
        err = e

    if state["vad"]:
        print(f"VAD 阶段出错，关掉 VAD 重试（后续文件也不再使用 VAD）：{short(err)}")
        state["vad"] = False
        try:
            return attempt(False)
        except Exception as e:
            err = e

    if state["device"] == "GPU":
        print(f"GPU 推理失败，改用 CPU 重试：{short(err)}")
        try:
            state["model"] = load("cpu")
        except Exception as e2:
            raise ToolError("CPU 模型加载失败：\n" + model_error_hint(e2))
        state["device"] = "CPU"
        try:
            return attempt(state["vad"])
        except Exception as e3:
            err = e3

    raise ToolError(
        f"转写失败：{short(err)}\n提示：可以试试 --model small 或 --no-vad，"
        "或检查文件是否正常"
    )


def transcribe_file(src, args, state, load, language):
    """转写一个文件并写出结果；失败时抛 ToolError。"""
    try:
        audio = load_audio(src)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"读取音视频失败：{short(e)}")

    print(f"音频时长：{len(audio) / 16000:.1f} 秒")
    t1 = time.time()

    segs, info = transcribe_with_fallback(audio, state, load, language)

    lang = info.language or (args.lang if args.lang != "auto" else "未知")
    print(f"识别语言：{lang}（置信度 {info.language_probability:.2f}）")
    print("-" * 50)

    lines, srt_lines = [], []
    for seg in segs:
        text = seg.text.strip()
        if not text:
            continue
        lines.append(text)
        print(f"[{fmt_ts(seg.start)}] {text}")
        if args.srt:
            srt_lines.append(
                f"{len(srt_lines) + 1}\n{fmt_ts(seg.start, ',')} --> "
                f"{fmt_ts(seg.end, ',')}\n{text}\n"
            )

    out = Path(args.output) if args.output else src.with_suffix(".txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("-" * 50)
    print(f"完成，用时 {time.time() - t1:.1f} 秒（设备：{state['device']}）")
    print(f"文本：{out}")

    if args.srt:
        srt_path = out.with_suffix(".srt")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        print(f"字幕：{srt_path}")


def probe(code, timeout=90):
    """在子进程里跑一段检测代码，原生崩溃也不会带走主进程。"""
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
        lines = [
            line for line in (r.stdout or "").splitlines()
            if "pkg_resources" not in line
        ]
        return r.returncode, "\n".join(lines).strip()
    except Exception as e:
        return -1, short(e)


def hf_cache_dir():
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def doctor():
    """打印环境自检信息，返回 0 表示没发现硬问题。"""
    setup_cuda_dlls()
    print(f"localscribe {__version__} 环境自检")
    print("=" * 52)
    fails = 0

    bits = "64 位" if sys.maxsize > 2 ** 32 else "32 位"
    print(f"[Python] {platform.python_version()}（{bits}）")
    print(f"[系统] {platform.platform()}")
    print(f"[解释器] {sys.executable}")

    ct2_ver = None
    rc, out = probe(
        "import ctranslate2; print(ctranslate2.__version__); "
        "print(ctranslate2.get_cuda_device_count())"
    )
    if rc == 0:
        rows = out.splitlines()
        ct2_ver = rows[0] if rows else None
        print(f"[OK] ctranslate2 {ct2_ver or '?'}")
        if len(rows) > 1:
            print(f"[OK] CUDA 设备数：{rows[1]}")
    else:
        print(f"[FAIL] ctranslate2 检查失败（退出码 {rc}）：{out[-200:]}")
        fails += 1

    ort_ver = None
    rc, out = probe("import onnxruntime; print(onnxruntime.__version__)")
    if rc == 0:
        ort_ver = out.splitlines()[-1] if out else None
        print(f"[OK] onnxruntime {ort_ver or '?'}")
    else:
        print(f"[FAIL] onnxruntime 导入失败（退出码 {rc}）：{out[-200:]}")
        print("       转写时可以加 --no-vad 绕过")
        fails += 1

    rc, out = probe(
        "from faster_whisper.vad import get_vad_model; "
        "print(type(get_vad_model()).__name__)"
    )
    if rc == 0:
        print(f"[OK] VAD 初始化正常（{out.splitlines()[-1] if out else 'OK'}）")
    else:
        print(f"[FAIL] VAD 初始化失败（退出码 {rc}）：{out[-200:]}")
        print("       转写时可以加 --no-vad 绕过")
        fails += 1

    try:
        import faster_whisper
        print(f"[OK] faster-whisper {faster_whisper.__version__}")
    except Exception as e:
        print(f"[FAIL] faster-whisper 导入失败：{short(e)}")
        fails += 1

    try:
        import imageio_ffmpeg
        print(f"[OK] ffmpeg：{imageio_ffmpeg.get_ffmpeg_exe()}")
    except Exception as e:
        print(f"[FAIL] ffmpeg 不可用：{short(e)}")
        fails += 1

    found = []
    for sp in _site_packages_dirs():
        nv = sp / "nvidia"
        for sub, pattern in (
            ("cublas/bin", "cublas64_*.dll"),
            ("cudnn/bin", "cudnn64_9.dll"),
            ("cuda_nvrtc/bin", "nvrtc64_*.dll"),
        ):
            d = nv / sub
            if d.exists() and list(d.glob(pattern)):
                found.append(str(d))
    if found:
        print("[OK] GPU 运行库：")
        for d in found:
            print(f"     {d}")
    else:
        print("[WARN] 没找到 pip 安装的 GPU 运行库；有 NVIDIA 显卡的话跑 setup.bat /gpu，或只用 CPU")

    cache = hf_cache_dir()
    print(f"[缓存] 模型目录：{cache}")
    cached = []
    for name, repo in MODEL_REPOS.items():
        d = cache / ("models--" + repo.replace("/", "--"))
        if d.exists():
            cached.append(f"{name}（{repo}）")
    if cached:
        print("     已下载：" + "、".join(cached))
    else:
        print("     还没有下载任何模型（首次转写会自动下载）")

    if sys.platform == "win32":
        ver = msvc_runtime_version()
        if not ver:
            print("[WARN] 读不到 msvcp140.dll 版本；如果转写闪退，先装最新 VC++ 运行库：")
            print("       https://aka.ms/vs/17/release/vc_redist.x64.exe")
        else:
            vtxt = f"{ver[0]}.{ver[1]}.{ver[2]}"
            if ver >= (14, 40):
                print(f"[OK] VC++ 运行库（msvcp140.dll）{vtxt}")
            else:
                ct2_mm = version_tuple(ct2_ver) if ct2_ver else None
                ort_mm = version_tuple(ort_ver) if ort_ver else None
                risky = bool(
                    (ct2_mm and ct2_mm >= (4, 6))
                    or (ort_mm and ort_mm >= (1, 22))
                )
                if risky:
                    print(f"[FAIL] VC++ 运行库（msvcp140.dll）{vtxt}，低于 14.40；")
                    print("       当前的 ctranslate2/onnxruntime 会闪退，先装最新运行库：")
                    print("       https://aka.ms/vs/17/release/vc_redist.x64.exe")
                    fails += 1
                else:
                    print(f"[WARN] VC++ 运行库（msvcp140.dll）{vtxt}，低于 14.40")
                    print("       当前锁定版本不受影响；以后升级 ctranslate2/onnxruntime 前，")
                    print("       先装最新运行库：https://aka.ms/vs/17/release/vc_redist.x64.exe")

    print("=" * 52)
    if fails:
        print(f"自检完成：{fails} 项需要处理，按上面的提示来。")
        return 1
    print("自检完成：没发现明显问题。")
    return 0


def main():
    faulthandler.enable()

    ap = argparse.ArgumentParser(
        description="本地视频/音频转文字（零 API 费用）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("inputs", nargs="*", metavar="输入文件",
                    help="一个或多个视频/音频文件；支持通配符，如 *.mp4")
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
    ap.add_argument("--no-vad", action="store_true",
                    help="关闭静音过滤（onnxruntime 出问题时用）")
    ap.add_argument("--doctor", action="store_true",
                    help="打印环境自检信息后退出（不需要输入文件）")
    ap.add_argument("-o", "--output", help="输出 txt 路径（默认与输入同目录同名）")
    ap.add_argument("--version", action="version", version=f"localscribe {__version__}")
    args = ap.parse_args()

    # 控制台编码兜底：生僻字显示为 ?，不崩溃
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if args.doctor:
        sys.exit(doctor())

    if not args.inputs:
        ap.error("请至少给一个视频/音频文件；只想检查环境请用 --doctor")

    inputs = collect_inputs(args.inputs)
    valid = []
    for item in inputs:
        p = Path(item)
        if not p.exists():
            print(f"[跳过] 文件不存在：{p}")
        elif not p.is_file():
            print(f"[跳过] 这不是一个文件：{p}")
        elif p.stat().st_size == 0:
            print(f"[跳过] 文件是空的（0 字节），没有可转写的内容：{p}")
        else:
            valid.append(p)

    if not valid:
        print("没有可处理的文件。")
        sys.exit(1)
    if len(valid) > 1 and args.output:
        ap.error("一次处理多个文件时不能指定 -o/--output")

    setup_cuda_dlls()
    from faster_whisper import WhisperModel

    # 旧 VC++ 运行库 + 新版 ctranslate2 = 一加载模型就闪退，先提醒（锁定版本不受影响）
    ver = msvc_runtime_version()
    if ver and ver < (14, 40):
        try:
            import ctranslate2
            cver = ctranslate2.__version__
        except Exception:
            cver = None
        if cver and version_tuple(cver) and version_tuple(cver) >= (4, 6):
            print(f"警告：VC++ 运行库 {ver[0]}.{ver[1]} 低于 14.40，"
                  f"当前 ctranslate2 {cver} 会闪退。")
            print("      先装最新运行库：https://aka.ms/vs/17/release/vc_redist.x64.exe")

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
            print(f"GPU 加载失败，改用 CPU 重试：{short(e)}")
            device = "CPU"
            try:
                model = load("cpu")
            except Exception as e2:
                sys.exit("模型加载失败：\n" + model_error_hint(e2))
        else:
            sys.exit("模型加载失败：\n" + model_error_hint(e))
    print(f"模型就绪，加载用时 {time.time() - t0:.1f} 秒")

    use_vad = not args.no_vad
    if use_vad:
        # 提前初始化 VAD：导入失败时关掉它，不拖累转写
        try:
            import onnxruntime  # noqa: F401
            from faster_whisper.vad import get_vad_model
            get_vad_model()
        except Exception as e:
            print(f"VAD 初始化失败，已自动关闭（不影响转写）：{short(e)}")
            print("提示：也可以手动加 --no-vad 跳过这一步。")
            use_vad = False

    state = {"model": model, "device": device, "vad": use_vad}
    language = None if args.lang == "auto" else args.lang

    total = len(valid)
    failures = 0
    for idx, src in enumerate(valid, 1):
        if total > 1:
            print()
            print(f"===== [{idx}/{total}] {src} =====")
        try:
            transcribe_file(src, args, state, load, language)
        except ToolError as e:
            print(f"[失败] {src}：{e}")
            failures += 1
        except Exception as e:
            print(f"[失败] {src}：{short(e)}")
            failures += 1

    if total > 1:
        print()
        print(f"全部完成：成功 {total - failures} 个，失败 {failures} 个")
    print("小提示：识别错字属正常现象，重要内容请校对；总结提示词见 summary_prompt.txt。")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()