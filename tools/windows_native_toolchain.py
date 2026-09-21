"""为固定 Windows 剪映 ABI 构建一次性原生导出子进程。"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


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
        fallback = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'LLVM/bin/clang-cl.exe'
        clang = str(fallback) if fallback.is_file() else None
    require(clang, '未找到 clang-cl；请安装 LLVM for Windows')
    return vcvars, Path(clang)


def compile_helper(source, output, temp, timeout=180):
    """用 vcvars64 + clang-cl /MD 编译，返回可写入证据文件的身份信息。"""
    source, output, temp = map(Path, (source, output, temp))
    require(source.is_file() and output.is_absolute() and temp.is_dir(), '无效的 Windows 导出构建路径')
    vcvars, clang = _toolchain()
    args = [str(clang), '/nologo', '/std:c++17', '/EHsc', '/MD', '/O2',
            '/D_CRT_SECURE_NO_WARNINGS', '/utf-8', str(source), '/Fe:' + str(output)]
    compile_line = subprocess.list2cmdline(args)
    script = temp / 'build-native-export.cmd'
    script.write_text('@echo off\r\ncall "' + str(vcvars) + '" >nul\r\n'
                      'if errorlevel 1 exit /b %errorlevel%\r\n' + compile_line + '\r\n',
                      encoding='utf-8', newline='')
    env = dict(os.environ, TMP=str(temp), TEMP=str(temp))
    result = subprocess.run(['cmd.exe', '/d', '/c', str(script)], capture_output=True,
                            timeout=timeout, env=env)
    identity = subprocess.run([str(clang), '--version'], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=30, env=env)
    compiler = identity.stdout.splitlines()[0] if identity.returncode == 0 and identity.stdout else 'unknown'
    return result, {'compiler': compiler, 'clang_cl': str(clang), 'vcvars64': str(vcvars),
                    'command': args}
