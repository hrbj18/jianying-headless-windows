"""为固定 Windows 剪映 ABI 构建一次性原生导出子进程。"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import hashlib
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def _vswhere():
    explicit = os.environ.get('VSWHERE')
    candidates = [Path(explicit)] if explicit else []
    candidates.append(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) /
                      'Microsoft Visual Studio/Installer/vswhere.exe')
    return next((path for path in candidates if path.is_file()), None)


def _toolchain():
    require(os.name == 'nt', 'Windows 原生导出工具链只能在 Windows 上使用')
    finder = _vswhere()
    require(finder, '未找到 Visual Studio Installer 的 vswhere.exe')
    result = subprocess.run([
        str(finder), '-latest', '-products', '*',
        '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
        '-property', 'installationPath'
    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    install = Path(result.stdout.strip())
    vcvars = install / 'VC/Auxiliary/Build/vcvars64.bat'
    require(result.returncode == 0 and vcvars.is_file(), '未找到 Visual Studio x64 C++ 工具链')
    clang = shutil.which('clang-cl')
    if not clang:
        candidates = [install / 'VC/Tools/Llvm/x64/bin/clang-cl.exe',
                      install / 'VC/Tools/Llvm/bin/clang-cl.exe',
                      Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'LLVM/bin/clang-cl.exe']
        clang = next((str(path) for path in candidates if path.is_file()), None)
    require(clang, '未找到 clang-cl；请安装 LLVM for Windows')
    return vcvars, Path(clang)


def compiler_environment(vcvars, clang):
    """Discover installed headers/libraries directly; never execute vcvars/reg."""
    install = Path(vcvars).parents[3]
    versions = install / 'VC/Tools/MSVC'
    require(versions.is_dir(), 'MSVC headers/libraries are missing')
    order = lambda p: tuple(int(x) for x in p.name.split('.') if x.isdigit())
    choices = sorted((p for p in versions.iterdir() if (p/'include').is_dir() and
                      (p/'lib/x64').is_dir()), key=order, reverse=True)
    require(choices, 'No complete MSVC x64 headers/libraries found')
    msvc = choices[0]
    kits = Path(os.environ.get('WindowsSdkDir', str(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Windows Kits/10')))
    include_root = kits/'Include'
    require(include_root.is_dir(), 'Windows SDK Include directory is missing')
    sdks = sorted((p for p in include_root.iterdir() if (p/'um/windows.h').is_file() and
                   (p/'ucrt').is_dir() and (kits/'Lib'/p.name/'um/x64').is_dir() and
                   (kits/'Lib'/p.name/'ucrt/x64').is_dir()),key=order,reverse=True)
    require(sdks, 'No complete Windows SDK x64 headers/libraries found')
    sdk = sdks[0]
    includes = [msvc/'include']+[sdk/name for name in ('ucrt','um','shared','winrt') if (sdk/name).is_dir()]
    libraries = [msvc/'lib/x64',kits/'Lib'/sdk.name/'ucrt/x64',kits/'Lib'/sdk.name/'um/x64']
    env = dict(os.environ)
    env.update(INCLUDE=';'.join(map(str,includes)),LIB=';'.join(map(str,libraries)))
    env['LIBPATH'] = env['LIB']
    env['PATH'] = os.pathsep.join([str(msvc/'bin/Hostx64/x64'),str(Path(clang).parent),env.get('PATH','')])
    return env, {'environment_route':'installed-msvc-sdk-direct', 'msvc':str(msvc), 'windows_sdk':str(sdk),
                 'vcvars_executed':False, 'registry_command_executed':False}


def compile_helper(source, output, temp, timeout=180):
    """Use clang-cl with explicit installed SDK paths, without shell initialization."""
    source, output, temp = map(Path, (source, output, temp))
    require(source.is_file() and output.is_absolute() and not output.exists() and
            output.parent.is_dir() and temp.is_dir(), '无效的 Windows 导出构建路径')
    vcvars, clang = _toolchain()
    compiler_env, environment_identity = compiler_environment(vcvars, clang)
    # cmd.exe and the MSVC linker do not consistently preserve non-ASCII argv.
    # Keep compiler inputs/outputs relative to an ASCII scratch directory; Python
    # copies exact bytes across the Unicode checkout/job paths afterwards.
    bases = [temp.resolve(), Path(tempfile.gettempdir()).resolve()]
    base = next((path for path in bases if str(path).isascii() and path.is_dir()), None)
    require(base is not None, 'Windows 编译需要可用的纯 ASCII 临时目录')
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    with tempfile.TemporaryDirectory(prefix='jy-export-', dir=base) as scratch:
        directory = Path(scratch)
        staged_source = directory / 'native_export.cpp'
        staged_source.write_bytes(source_bytes)
        args = [str(clang), '/nologo', '/std:c++17', '/EHsc', '/MD', '/O2',
                '/D_CRT_SECURE_NO_WARNINGS', '/utf-8', staged_source.name,
                '/Fo:native-export-helper.obj', '/Fe:native-export-helper.exe']
        env = dict(compiler_env, TMP=str(directory), TEMP=str(directory))
        result = subprocess.run(args, cwd=directory,
                                capture_output=True, timeout=timeout, env=env)
        identity = subprocess.run([str(clang), '--version'], cwd=directory, capture_output=True,
                                  text=True, encoding='utf-8', errors='replace', timeout=30, env=env)
        require(hashlib.sha256(source.read_bytes()).hexdigest() == source_hash and
                hashlib.sha256(staged_source.read_bytes()).hexdigest() == source_hash,
                '原生导出源码在编译期间发生变化')
        if result.returncode == 0:
            executable = directory / 'native-export-helper.exe'
            require(executable.is_file(), '编译器未生成原生导出助手')
            with executable.open('rb') as src, output.open('xb') as dst:
                shutil.copyfileobj(src, dst)
        compiler = identity.stdout.splitlines()[0] if identity.returncode == 0 and identity.stdout else 'unknown'
        return result, {'compiler': compiler, 'clang_cl': str(clang), 'vcvars64': str(vcvars), **environment_identity,
                        'command': args, 'source_sha256': source_hash,
                        'source_staging': 'byte-identical ASCII compiler workspace',
                        'compiler_cwd': str(directory)}
