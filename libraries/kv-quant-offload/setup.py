# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
from pathlib import Path

import torch
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CppExtension

CSRC_DIR = Path("kvweave/csrc")
BINDINGS_DIR = Path("kvweave/bindings")
REPO_ROOT = Path(__file__).resolve().parent

AVX512_FLAGS = [
    "-mavx512bw",
    "-mavx512fp16",
    "-mavx512f",
    "-mavx512dq",
    "-mavx512bf16",
]

AVX2_FLAGS = [
    "-mavx2",
    "-mfma",
    "-mf16c",
]

# Set KVWEAVE_ISA=avx512 only on hosts that support AVX-512 FP16/BF16.
# AVX2 is the safe default for client CPUs; using AVX-512 on unsupported
# machines can make Python terminate with "Illegal instruction".
isa = os.environ.get("KVWEAVE_ISA", "avx2").lower()
if isa == "avx2":
    AVX_FLAGS = AVX2_FLAGS
elif isa == "avx512":
    AVX_FLAGS = AVX512_FLAGS
else:
    raise ValueError("KVWEAVE_ISA must be 'avx2' or 'avx512'")

# Set KVWEAVE_XPU=1 to additionally build the kvweave_quant_xpu extension
# (SYCL/DPC++ quantize/dequantize kernels for Intel GPUs). Default is CPU-only.
xpu_enabled = os.environ.get("KVWEAVE_XPU", "0") == "1"

# Set KVWEAVE_COMPILER=icpx to force the Intel oneAPI compiler for the Python
# extension. This keeps the pybind module/API unchanged while matching the
# native icpx benchmark compiler more closely. KVWEAVE_XPU=1 requires icpx
# regardless of KVWEAVE_COMPILER, since the XPU extension needs -fsycl.
compiler = os.environ.get("KVWEAVE_COMPILER", "").lower()
if compiler not in ("", "default", "icpx"):
    raise ValueError("KVWEAVE_COMPILER must be 'default' or 'icpx'")

if compiler == "icpx" or xpu_enabled:
    os.environ.setdefault("CC", "icx")
    os.environ.setdefault("CXX", "icpx")
    if shutil.which(os.environ["CXX"]) is None:
        raise RuntimeError(
            (
                "KVWEAVE_COMPILER=icpx requested"
                if compiler == "icpx"
                else "KVWEAVE_XPU=1 requested"
            )
            + ", but icpx is not in PATH. Source /opt/intel/oneapi/setvars.sh "
            "or use a container image with oneAPI compiler paths preconfigured."
        )
    compiler = "icpx"
else:
    compiler = Path(os.environ.get("CXX", "default")).name or "default"

# Set KVWEAVE_MULTITHREAD=0 to disable OpenMP multithreading
use_mt = os.environ.get("KVWEAVE_MULTITHREAD", "1") != "0"
MT_COMPILE_FLAGS = ["-fopenmp", "-DUSE_MULTITHREADING"] if use_mt else []
MT_LINK_FLAGS = ["-fopenmp"] if use_mt else []

BUILD_DEFINES = [
    f'-DKVWEAVE_BUILD_COMPILER="{compiler}"',
    f'-DKVWEAVE_BUILD_ISA="{isa}"',
    f'-DKVWEAVE_BUILD_MULTITHREAD={1 if use_mt else 0}',
]

quant_extension = CppExtension(
    name="kvweave.kvweave_quant",
    sources=[
        str(BINDINGS_DIR / "kvweave_quant_wrapper.cpp"),
        str(CSRC_DIR / "quant.cpp"),
    ],
    include_dirs=[str(REPO_ROOT / CSRC_DIR)],
    extra_compile_args=[
        "-O3",
        "-std=c++17",
        *AVX_FLAGS,
        *MT_COMPILE_FLAGS,
        *BUILD_DEFINES,
    ],
    extra_link_args=[*MT_LINK_FLAGS],
)

ext_modules = [quant_extension]

if xpu_enabled:
    xpu_extension = CppExtension(
        name="kvweave.kvweave_quant_xpu",
        sources=[
            str(BINDINGS_DIR / "kvweave_quant_xpu_wrapper.cpp"),
            str(CSRC_DIR / "quant_sycl.cpp"),
        ],
        include_dirs=[str(REPO_ROOT / CSRC_DIR)],
        extra_compile_args=[
            "-std=c++17",
            "-fsycl",
            "-O3",
            "-fp-model=precise",
            "-DKVWEAVE_XPU=1",
        ],
        extra_link_args=["-fsycl"],
    )
    ext_modules.append(xpu_extension)

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": BuildExtension},
)


# pip uninstall -y kvweave-quant || true && rm -rf build kvweave_quant.egg-info && python setup.py install