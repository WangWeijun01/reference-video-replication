"""Write untouched local ASR results; this is not a human-verified transcript."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', default='base')
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error('Input video does not exist')
    if args.output.exists():
        parser.error('Output exists; choose a new path to preserve evidence')
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device='cpu', compute_type='int8')
    segments, info = model.transcribe(str(args.video), language='zh', beam_size=5, vad_filter=True)
    rows = [dict(start=s.start, end=s.end, text=s.text) for s in segments]
    sha = hashlib.sha256()
    with args.video.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            sha.update(chunk)
    result = dict(source=str(args.video.resolve()), sha256=sha.hexdigest(), model=args.model,
                  engine='faster-whisper', device='cpu', compute_type='int8', language=info.language,
                  human_listening_verified=False, segments=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
    print(f'Wrote {len(rows)} machine-transcribed segments to {args.output}')


if __name__ == '__main__':
    main()
