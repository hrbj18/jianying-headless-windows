"""Task preflight exercises the actual compiler, without cloud submission."""
import hashlib, importlib.util, json, sys, tempfile
from pathlib import Path

def doctor():
    import windows_runtime
    from local_config import workspace_root, config_path
    from windows_native_toolchain import compile_helper
    runtime=windows_runtime.validate_runtime()
    dependencies={name:importlib.util.find_spec(name) is not None for name in ('fontTools','PIL','numpy','dotenv','requests')}
    missing=[name for name,available in dependencies.items() if not available]
    if missing:raise ValueError('Missing project Python dependencies: '+', '.join(missing)+'; install requirements-production.txt with the project .venv Python')
    base=workspace_root();base.mkdir(parents=True,exist_ok=True)
    if not str(base).isascii():raise ValueError('workspace_root must be ASCII')
    with tempfile.TemporaryDirectory(prefix='compiler-preflight-',dir=base) as task:
        root=Path(task);source=root/'probe.cpp'
        source.write_text('#include <windows.h>\nint main(){return GetCurrentProcessId()==0;}\n',encoding='utf-8')
        result,compiler=compile_helper(source,root/'probe.exe',root)
        if result.returncode:raise ValueError('Compiler preflight failed: '+result.stderr.decode('utf-8',errors='replace')[:1200])
    bridge=Path(__file__).resolve().parents[1]/'bridge/live-editor'
    manifest=json.loads((bridge/'manifest.json').read_text(encoding='utf-8'))
    if not all(hashlib.sha256((bridge/name).read_bytes()).hexdigest()==sha for name,sha in manifest['files'].items()):
        raise ValueError('Live bridge package checksum mismatch')
    try:
        from cloud_asr import configuration
        asr=configuration();cloud={'provider':'bailian','credential_available':True,'model':asr['model'],'network_called':False}
    except (ValueError,ImportError) as error:
        cloud={'provider':'bailian','credential_available':False,'reason':str(error),'network_called':False}
    return dict(status='ready',runtime=runtime,project_root=str(Path(__file__).resolve().parents[1]),
                python=sys.executable,config=str(config_path()),dependencies=dependencies,
                compiler={k:v for k,v in compiler.items() if k not in ('command','compiler_cwd')},
                live_bridge_verified=True,asr=cloud)
