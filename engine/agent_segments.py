"""Readable segment identities; the shared entry never guesses from draft names."""
import json

def segment_table(doc):
    texts={m['id']:m for m in doc.get('materials',{}).get('texts',[])}
    tracks=[];segments=[]
    for t in doc['tracks']:
        tracks.append(dict(track_id=t['id'],type=t['type'],segment_count=len(t['segments'])))
        for s in t['segments']:
            row=dict(segment_id=s['id'],track_id=t['id'],type=t['type'],start_us=s['target_timerange'].get('start',0),duration_us=s['target_timerange']['duration'])
            if t['type']=='text':row['text']=json.loads(texts[s['material_id']]['content']).get('text','')
            segments.append(row)
    return dict(tracks=tracks,segments=segments)
