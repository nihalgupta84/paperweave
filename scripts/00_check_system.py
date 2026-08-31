#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys


def run(cmd):
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        ).stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-gpu", action="store_true")
    args = parser.parse_args()

    print("=" * 80)
    print("PaperWeave System Check")
    print("=" * 80)

    print("\n[Python]")
    print("python:", sys.executable)
    print("version:", sys.version.replace("\n", " "))

    print("\n[Commands]")
    for name in ["mineru", "rclone", "nvidia-smi"]:
        path = shutil.which(name)
        print(f"{name}: {path or 'NOT FOUND'}")

    print("\n[MinerU]")
    if shutil.which("mineru"):
        print(run(["mineru", "--version"]))
    else:
        print("MinerU not found in PATH.")

    print("\n[NVIDIA]")
    if shutil.which("nvidia-smi"):
        print(run(["nvidia-smi"]))
    else:
        print("nvidia-smi not found. CPU mode may still work, but GPU mode will not.")

    print("\n[PyTorch]")
    torch_ok = False
    cuda_ok = False
    try:
        import torch

        torch_ok = True
        print("torch:", torch.__version__)
        print("torch cuda:", torch.version.cuda)
        cuda_ok = torch.cuda.is_available()
        print("cuda available:", cuda_ok)
        if cuda_ok:
            print("gpu:", torch.cuda.get_device_name(0))
    except Exception as e:
        print("torch import failed:", repr(e))

    print("\n[PyMuPDF / pypdf]")
    try:
        import fitz
        print("pymupdf: OK")
    except Exception as e:
        print("pymupdf failed:", repr(e))

    try:
        import pypdf
        print("pypdf: OK")
    except Exception as e:
        print("pypdf failed:", repr(e))

    if args.require_gpu and not cuda_ok:
        print("\nERROR: --require-gpu was set but torch.cuda.is_available() is False.")
        sys.exit(2)

    print("\nCheck complete.")
    if torch_ok and cuda_ok:
        print("Recommended device: gpu")
    elif torch_ok:
        print("Recommended device: cpu")
    else:
        print("Torch is not usable. Fix environment before running MinerU.")


if __name__ == "__main__":
    main()
