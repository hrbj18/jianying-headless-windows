// Separate typed edit transport. The preview transport remains read-only.
import net from 'node:net';
import readline from 'node:readline';
import {readFileSync} from 'node:fs';
const AUDIO=Object.values(JSON.parse(readFileSync(new URL('./windows-audio-resources.json',import.meta.url),'utf8')).resources);
const READS = new Set(['system.health','system.shutdown','player.create','player.load',
  'player.getState','player.destroy']);
const EDITS = new Set(['audio.denoiseOn','audio.denoiseOff','video.setBasicColor','audio.setVoiceEffect','audio.setVoiceEffectParams']);
const MAX = 16 * 1024 * 1024;

export function validate(input) {
  const r=input?.request, key=r?.domain+'.'+r?.operation;
  if (typeof input?.endpoint!=='string' || !input.endpoint.startsWith('\\\\.\\pipe\\jy-native-feature-') ||
      r?.protocolVersion!==1 || typeof r?.id!=='string' || !Number.isInteger(input.timeoutMs) ||
      input.timeoutMs<1 || input.timeoutMs>30000) throw Error('Invalid owned feature transport');
  if (r.domain==='edit') {
    const p=r.params;
    if (!EDITS.has(r.operation) || typeof input.boundSessionId!=='string' ||
        !input.boundSessionId || r.targetId!==input.boundSessionId) throw Error('Edit is outside the bound session');
    if (r.operation==='video.setBasicColor') {
      if (typeof p?.seg_id!=='string' || !p.material || typeof p.material!=='object' ||
          Object.keys(p).some(k=>!['seg_id','material','preset_resource_id','is_keyframe','keyframe_id','is_auto_fill_keyframe','is_unified_beauty_mode'].includes(k)) || p.is_keyframe!==false ||
          ![69,70,30,31].includes(p.material.type))
        throw Error('Unsupported typed local color edit');
      return;
    }
    if (r.operation==='audio.setVoiceEffect' || r.operation==='audio.setVoiceEffectParams') {
      if(typeof p?.segment_id!=='string' || typeof p.resource_id!=='string' || !p.resource_id ||
         Object.keys(p).some(k=>!['segment_id','name','resource_id','resource_path','category_id','category_name',
         'audio_adjust_params','production_path','audio_effect_type','vc_type','speaker_id','source_platform','third_resource_id',
         'is_vc_clone_tone','is_ugc','time_range','is_modify','effect_adjust_value','is_keyframe',
         'paramIndex','parameterIndex','portIndex','keyframe_id','is_auto_fill_keyframe','flags','is_clear_all_keyframes'].includes(k))) throw Error('Unsupported typed voice effect');
      if(r.operation==='audio.setVoiceEffect' && (typeof p.resource_path!=='string' || !p.resource_path))throw Error('Missing owned voice-effect path');
      const entry=AUDIO.find(e=>e.resource_id===p.resource_id);
      if(!entry)throw Error('Unknown native audio resource');
      if(('audio_effect_type' in p && p.audio_effect_type!==(entry.sub_type??1)) || ('vc_type' in p && p.vc_type!==0))
         throw Error('Unreviewed native audio enum');
      if(r.operation==='audio.setVoiceEffect' && p.audio_effect_type!==(entry.sub_type??1))
         throw Error('Native audio category must be explicit');
      const controlFor=v=>entry.controls.find(c=>c.parameterIndex===v.parameterIndex && c.portIndex===v.portIndex);
      // The SDK parser aborts the remaining fields on a string enum, while its
      // caller may still return a partial success. Keep unreviewed enum fields
      // out of this transport; the reviewed non-clone default is intentional.
      if(r.operation==='audio.setVoiceEffect' && (p.source_platform!==entry.source_platform ||
         !Array.isArray(p.audio_adjust_params) || p.audio_adjust_params.length!==entry.controls.length ||
         new Set(p.audio_adjust_params.map(v=>v.parameterIndex+':'+v.portIndex)).size!==entry.controls.length || p.audio_adjust_params.some(v=>
         Object.keys(v).sort().join(',')!==['value','default_value','parameterIndex','portIndex','name','min_value','max_value'].sort().join(',') ||
         !controlFor(v) || v.name!==controlFor(v).name || v.default_value!==controlFor(v).default_value ||
         v.min_value!==0 || v.max_value!==1 || !Number.isFinite(v.value) || v.value<0 || v.value>1)))
         throw Error('Unsupported native audio-effect controls');
      if(r.operation==='audio.setVoiceEffectParams' &&
         (!controlFor(p) || !Number.isFinite(p.effect_adjust_value) ||
          p.effect_adjust_value<0 || p.effect_adjust_value>1 || p.is_keyframe!==false))
         throw Error('Unsupported native audio-effect parameter edit');
      return;
    }
    if (
        !Array.isArray(p?.segmentIds) || p.segmentIds.length!==1 ||
        typeof p.segmentIds[0]!=='string') throw Error('Audio edit is outside the bound session');
    if (Object.keys(p).some(k=>!['segmentIds','path','denoiseMode','denoiseRate','samiName','samiVersion','samiType','isDenoise'].includes(k)))
      throw Error('Unknown denoise parameters');
    if ('isDenoise' in p && p.isDenoise!==(r.operation==='audio.denoiseOn')) throw Error('Denoise switch conflicts with operation');
    if (r.operation==='audio.denoiseOn' && (typeof p.path!=='string' || !p.path)) throw Error('Missing local model path');
  } else if (!READS.has(key)) throw Error('Unsupported native feature operation');
}

async function invoke(input) {
  validate(input);
  const {endpoint,request,timeoutMs}=input;
  const result=await new Promise((resolve,reject)=>{
    const socket=net.createConnection(endpoint);let data='',done=false;
    const finish=(error,value)=>{if(done)return;done=true;socket.destroy();error?reject(error):resolve(value);};
    socket.setEncoding('utf8');socket.setTimeout(timeoutMs,()=>finish(Error('Native feature request timed out')));
    socket.once('error',finish);socket.once('end',()=>{if(!done)finish(Error('Native feature pipe closed'));});
    socket.once('connect',()=>socket.write(JSON.stringify(request)+'\n'));
    socket.on('data',chunk=>{data+=chunk;if(data.length>MAX)return finish(Error('Native response too large'));
      const newline=data.indexOf('\n');if(newline<0)return;
      try{finish(null,JSON.parse(data.slice(0,newline)));}catch{finish(Error('Invalid native JSON'));}});
  });
  if(result?.id!==request.id || result.protocolVersion!==1)throw Error('Native feature response identity mismatch');
  return result;
}
if(import.meta.main)for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
  if(!line.trim())continue;let input;
  try{input=JSON.parse(line);console.log(JSON.stringify(await invoke(input)));}
  catch(error){console.log(JSON.stringify({id:input?.request?.id,protocolVersion:1,ok:false,transportError:String(error.message).slice(0,500)}));process.exitCode=1;}
}
