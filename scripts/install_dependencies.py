"""
智能依赖安装脚本

功能：
1. 自动检测本地 NVIDIA GPU 是否可用（通过 nvidia-smi）
2. 根据检测结果优先安装 GPU 版 PyTorch，否则回退 CPU 版
3. 安装 requirements.txt 中其他依赖

用法：
    python scripts/install_dependencies.py            # 自动检测
    python scripts/install_dependencies.py --cpu      # 强制 CPU 版
    python scripts/install_dependencies.py --gpu      # 强制 GPU 版 (默认 cu121)
    python scripts/install_dependencies.py --cuda 124 # 指定 CUDA 版本
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"

# PyTorch CUDA 索引地址映射
TORCH_CUDA_INDEX = {
    "118": "https://download.pytorch.org/whl/cu118",
    "121": "https://download.pytorch.org/whl/cu121",
    "124": "https://download.pytorch.org/whl/cu124",
    "126": "https://download.pytorch.org/whl/cu126",
}
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def detect_nvidia_gpu():
    """通过 nvidia-smi 检测本地是否有可用的 NVIDIA GPU。

    Returns:
        (has_gpu: bool, info: str)
    """
    if shutil.which("nvidia-smi") is None:
        return False, "未检测到 nvidia-smi 命令"
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip()
        return False, f"nvidia-smi 调用失败: {result.stderr.strip()}"
    except Exception as e:
        return False, f"nvidia-smi 异常: {e}"


def pip_install(args, extra_index_url=None, index_url=None):
    """调用 pip 安装。"""
    cmd = [sys.executable, "-m", "pip", "install"]
    if index_url:
        cmd += ["--index-url", index_url]
    if extra_index_url:
        cmd += ["--extra-index-url", extra_index_url]
    cmd += args
    print(f"\n>>> {' '.join(cmd)}\n", flush=True)
    return subprocess.call(cmd)


def install_pytorch_gpu(cuda_tag="121"):
    index = TORCH_CUDA_INDEX.get(cuda_tag)
    if not index:
        print(f"[!] 未知的 CUDA 版本 {cuda_tag}，支持: {', '.join(TORCH_CUDA_INDEX)}")
        return 1
    print(f"[*] 安装 GPU 版 PyTorch (CUDA {cuda_tag[:2]}.{cuda_tag[2:]})")
    return pip_install(
        ["torch", "torchvision", "torchaudio"],
        index_url=index,
    )


def install_pytorch_cpu():
    print("[*] 安装 CPU 版 PyTorch")
    return pip_install(
        ["torch", "torchvision", "torchaudio"],
        index_url=TORCH_CPU_INDEX,
    )


def install_requirements():
    if not REQUIREMENTS_FILE.exists():
        print(f"[!] 未找到 {REQUIREMENTS_FILE}")
        return 1
    print(f"[*] 安装其他依赖 ({REQUIREMENTS_FILE.name})")
    return pip_install(["-r", str(REQUIREMENTS_FILE)])


def main():
    parser = argparse.ArgumentParser(description="智能安装项目依赖（自动检测 GPU）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--gpu", action="store_true", help="强制安装 GPU 版 PyTorch")
    group.add_argument("--cpu", action="store_true", help="强制安装 CPU 版 PyTorch")
    parser.add_argument("--cuda", default="121", choices=list(TORCH_CUDA_INDEX),
                        help="GPU 版本对应的 CUDA 版本，默认 121")
    parser.add_argument("--skip-requirements", action="store_true",
                        help="跳过 requirements.txt 安装，仅处理 PyTorch")
    args = parser.parse_args()

    print("=" * 60)
    print("  INFO_EXTRACTION 智能依赖安装")
    print("=" * 60)

    # 1. 决定 PyTorch 版本
    if args.gpu:
        use_gpu = True
        gpu_info = "用户强制指定 GPU"
    elif args.cpu:
        use_gpu = False
        gpu_info = "用户强制指定 CPU"
    else:
        use_gpu, gpu_info = detect_nvidia_gpu()

    print(f"\n[设备检测] {'✅ 检测到 GPU' if use_gpu else '⚠️ 未检测到 GPU'}: {gpu_info}")

    # 2. 安装 PyTorch
    if use_gpu:
        code = install_pytorch_gpu(args.cuda)
        if code != 0:
            print("\n[!] GPU 版安装失败，回退尝试 CPU 版")
            code = install_pytorch_cpu()
    else:
        code = install_pytorch_cpu()

    if code != 0:
        print("\n[!] PyTorch 安装失败，请检查网络或手动安装")
        return code

    # 3. 安装其他依赖
    if not args.skip_requirements:
        code = install_requirements()
        if code != 0:
            print("\n[!] requirements.txt 安装失败")
            return code

    # 4. 验证
    print("\n" + "=" * 60)
    print("  安装完成，验证 PyTorch")
    print("=" * 60)
    try:
        import torch  # noqa: E402
        print(f"  PyTorch 版本: {torch.__version__}")
        print(f"  CUDA 可用:    {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  GPU 设备:     {torch.cuda.get_device_name(0)}")
            print(f"  显存大小:     {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    except Exception as e:
        print(f"  [!] 导入 torch 失败: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
