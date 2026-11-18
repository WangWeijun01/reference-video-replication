"""Synthesize rewritten script lines and lay them out back to back.

Input JSON: {"voice": "...", "rate": "+10%", "gap": 0.12, "lead": 0.2, "tail": 0.6, "lines": ["...", ...]}
Optional "engine": "volc" uses Volcengine seed-tts-2.0 instead of edge-tts, reading VOLC_APP_ID and
VOLC_TOKEN from the environment (never put them in the JSON); "rate" is then speech_rate -50..100 and
"tone" is an optional delivery note sent as context_texts.
Output dir (must not exist): per-line mp3, voice.wav (48 kHz stereo) and timeline.json with each
line's start/end seconds. edge-tts output is machine voiceover for a review cut only.
"""
import argparse, asyncio, base64, json, os, subprocess, urllib.request, uuid
from pathlib import Path


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out)


async def synth_edge(text, voice, rate, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(path))


def synth_volc(text, cfg, path):
    params = {'text': text, 'speaker': cfg['voice'],
              'audio_params': {'format': 'mp3', 'sample_rate': 24000, 'speech_rate': int(cfg.get('rate', 0))}}
    if cfg.get('tone'):
        params['additions'] = json.dumps({'context_texts': [cfg['tone']]}, ensure_ascii=False)
    req = urllib.request.Request('https://openspeech.bytedance.com/api/v3/tts/unidirectional',
                                 json.dumps({'user': {'uid': 'video-replication'}, 'req_params': params}).encode(),
                                 {'X-Api-App-Id': os.environ['VOLC_APP_ID'], 'X-Api-Access-Key': os.environ['VOLC_TOKEN'],
                                  'X-Api-Resource-Id': 'seed-tts-2.0', 'X-Api-Request-Id': str(uuid.uuid4()),
                                  'Content-Type': 'application/json'}, method='POST')
    audio = b''
    with urllib.request.urlopen(req, timeout=60) as r:
        for row in r:
            if row.strip():
                j = json.loads(row)
                if j.get('code') not in (0, 20000000, None):
                    raise RuntimeError(f'Volcengine TTS: {j.get("code")} {j.get("message")}')
                if j.get('data'):
                    audio += base64.b64decode(j['data'])
    if not audio:
        raise RuntimeError('Volcengine TTS returned no audio')
    path.write_bytes(audio)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('script', type=Path)
    ap.add_argument('out', type=Path)
    a = ap.parse_args()
    cfg = json.loads(a.script.read_text(encoding='utf8'))
    a.out.mkdir(parents=True)
    volc = cfg.get('engine') == 'volc'
    t = cfg.get('lead', 0.2); rows = []; inputs = []; filters = []
    for i, line in enumerate(cfg['lines']):
        mp3 = a.out / f'line{i + 1:02d}.mp3'
        if volc:
            synth_volc(line, cfg, mp3)
        else:
            asyncio.run(synth_edge(line, cfg['voice'], cfg.get('rate', '+0%'), mp3))
        # Engines pad a little silence; trim it so the timeline matches audible speech.
        wav = a.out / f'line{i + 1:02d}.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(mp3), '-af',
                        'silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse',
                        '-ar', '48000', '-ac', '2', str(wav)], check=True)
        d = duration(wav)
        rows.append(dict(index=i + 1, text=line, start=round(t, 3), end=round(t + d, 3)))
        inputs += ['-i', str(wav)]
        filters.append(f'[{i}]adelay={int(t * 1000)}|{int(t * 1000)}[a{i}]')
        t += d + cfg.get('gap', 0.12)
    total = t - cfg.get('gap', 0.12) + cfg.get('tail', 0.6)
    mix = ';'.join(filters) + ';' + ''.join(f'[a{i}]' for i in range(len(rows))) + \
          f'amix=inputs={len(rows)}:normalize=0,apad,atrim=0:{total:.3f}[out]'
    subprocess.run(['ffmpeg', '-v', 'error', *inputs, '-filter_complex', mix, '-map', '[out]', '-ar', '48000',
                    '-ac', '2', str(a.out / 'voice.wav')], check=True)
    json.dump(dict(voice=cfg['voice'], rate=cfg.get('rate'), engine='volc-seed-tts-2.0' if volc else 'edge-tts',
                   tone=cfg.get('tone'), total=round(total, 3),
                   # Volcengine use is governed by the account's own service terms, not settled here.
                   licensed_for_publish=None if volc else False, lines=rows),
              open(a.out / 'timeline.json', 'w', encoding='utf8'), ensure_ascii=False, indent=2)
    print(f'{len(rows)} lines, total {total:.2f}s')


if __name__ == '__main__':
    main()
