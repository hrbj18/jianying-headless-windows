"""Strict SDR 33^3 Cube data, canonicalized without numerical resampling.

The native validator and loader disagree on some optional headers. Preserve
the original hash and emit the already-proven size+RGB-row representation.
FFmpeg's permissive parser alone is not a compatibility or completeness gate.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib,math,re

SIZE=33
SAMPLES=SIZE**3
MAX_BYTES=8*1024*1024
NUMBER=re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


def require(ok,message):
    if not ok:raise ValueError(message)


@dataclass(frozen=True)
class Cube:
    canonical:bytes
    source_sha256:str
    sha256:str
    title:str


def parse(data):
    require(isinstance(data,bytes) and 0<len(data)<=MAX_BYTES,'Cube file exceeds the reviewed size bound')
    text=data.decode('utf-8-sig');rows=[];size=None;domains={};title=''
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('TITLE'):
            require(not rows and not title,'Duplicate or late Cube TITLE')
            match=re.fullmatch(r'TITLE\s+"([^"\r\n]{1,128})"\s*(?:#.*)?',line)
            require(match is not None,'Invalid Cube TITLE');title=match.group(1);continue
        line=line.split('#',1)[0].strip()
        if not line:continue
        tokens=line.split();key=tokens[0]
        if key=='LUT_3D_SIZE':
            require(not rows and size is None and tokens==['LUT_3D_SIZE',str(SIZE)],
                    'Native custom Cube currently requires one LUT_3D_SIZE 33')
            size=SIZE;continue
        if key in ('DOMAIN_MIN','DOMAIN_MAX'):
            require(not rows and key not in domains and len(tokens)==4,'Invalid or late Cube domain')
            require(all(NUMBER.fullmatch(x) for x in tokens[1:]),'Invalid Cube domain numbers')
            values=[float(x) for x in tokens[1:]]
            require(values==([0.,0.,0.] if key=='DOMAIN_MIN' else [1.,1.,1.]),
                    'Nondefault Cube domains require independent native acceptance')
            domains[key]=values;continue
        require(size==SIZE and len(tokens)==3 and all(NUMBER.fullmatch(x) for x in tokens),
                'Invalid Cube row or unsupported directive at line '+str(number))
        values=[float(x) for x in tokens]
        require(all(math.isfinite(x) and 0<=x<=1 for x in values),'Cube output must be finite SDR values in 0..1')
        canonical=' '.join(tokens)
        require(len(canonical.encode('ascii'))<512,'Cube numeric row exceeds native line buffer')
        rows.append(canonical)
        require(len(rows)<=SAMPLES,'Cube contains extra RGB samples')
    require(size==SIZE and len(rows)==SAMPLES,'Cube must contain exactly 35937 RGB samples')
    canonical=('LUT_3D_SIZE 33\n'+'\n'.join(rows)+'\n').encode('ascii')
    return Cube(canonical,hashlib.sha256(data).hexdigest(),hashlib.sha256(canonical).hexdigest(),title)


def read(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.suffix.lower()=='.cube','Cube source must be a regular .cube file')
    require(path.stat().st_size<=MAX_BYTES,'Cube file exceeds reviewed size')
    return parse(path.read_bytes())
