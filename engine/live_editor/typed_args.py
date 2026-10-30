"""Bounded Qt argument wire format; no borrowed Qt strings cross a GUI call."""
import math,struct
from .errors import require

def arguments(items,selection=0,selection_vtable=0,segment_id=''):
    require(len(items)<=8,'TOO_MANY_ARGUMENTS','At most 8 Qt arguments')
    require(len(segment_id.encode('ascii'))<40,'INVALID_SEGMENT_ID','Segment ID exceeds the wire limit')
    header=struct.pack('<IIQQ40s',1,len(items),selection,selection_vtable,segment_id.encode('ascii'))
    descriptors=[];payload=b''
    kinds={'bool':(1,'<?'),'int':(2,'<i'),'int64_t':(3,'<q'),'double':(4,'<d'),'float':(5,'<f'),'QString':(6,None),'QQuickItem*':(7,'<Q')}
    for item in items:
        name,value=item[:2];override=item[2] if len(item)==3 else ''
        require(name in kinds,'ARGUMENT_TYPE','Unsupported Qt argument')
        kind,format=kinds[name]
        if kind==6:
            require(isinstance(value,str) and '\0' not in value,'INVALID_TEXT','QString must be NUL-free text')
            data=value.encode('utf-8')+b'\0';require(len(data)<=4097,'TEXT_TOO_LONG','QString exceeds 4096 UTF8 bytes')
        else:
            require(kind not in (4,5) or math.isfinite(value),'NONFINITE_ARGUMENT','Numeric arguments must be finite')
            data=struct.pack(format,value)
        encoded=override.encode('ascii');require(len(encoded)<52,'TYPE_NAME_TOO_LONG','Qt enum type name too long')
        descriptors.append(struct.pack('<III52s',kind,len(data),576+len(payload),encoded));payload+=data
    result=header+b''.join(descriptors).ljust(512,b'\0')+payload
    require(len(result)<=8192,'PAYLOAD_TOO_LARGE','Qt arguments exceed wire limit')
    return result
