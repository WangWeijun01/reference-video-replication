"""Refit an existing fullscreen-mix plan to a new voiceover timeline.

Captions map one-to-one onto timeline lines, except --silent-lines (1-based), which are spoken over
on-screen text and only anchor the timing. Each caption runs from 0.1s before its line to the next
caption; segment cuts are interpolated inside the caption they fell in. Footage never reads past its
old source range, so a new voice cannot pull in a neighbouring shot: a shorter slot trims the tail at
normal speed, a longer one slows down. Prints each footage segment's slowdown; anything over the limit
needs a fresh look at the source.
"""
import argparse, json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan', type=Path)
    ap.add_argument('timeline', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--audio', required=True)
    ap.add_argument('--version', required=True, help='work/output directory name, e.g. v5')
    ap.add_argument('--limit', type=float, default=1.25)
    ap.add_argument('--silent-lines', default='', help='1-based lines with no caption, e.g. 1,9')
    a = ap.parse_args()
    plan = json.loads(a.plan.read_text(encoding='utf8'))
    lines = json.loads(a.timeline.read_text(encoding='utf8'))
    fps = plan['fps']; rows = lines['lines']
    silent = {int(x) for x in a.silent_lines.split(',') if x}
    if len(rows) - len(silent) != len(plan['captions']):
        raise ValueError(f'{len(rows)} lines, {len(silent)} silent, {len(plan["captions"])} captions')
    # A silent line starts where the previous caption ended, or at frame 0.
    caps = []; pending = iter(plan['captions']); previous_end = 0
    for n in range(1, len(rows) + 1):
        if n in silent:
            caps.append(dict(start_frame=previous_end, silent=True))
        else:
            caps.append(next(pending)); previous_end = caps[-1]['end_frame']
    total = round(lines['total'] * fps)
    new_starts = [0] + [round((r['start'] - .1) * fps) for r in rows[1:]]
    old_starts = [c['start_frame'] for c in caps]
    old_ends = old_starts[1:] + [plan['total_frames']]
    new_ends = new_starts[1:] + [total]

    def remap(f):
        if f >= plan['total_frames']:
            return total
        i = max(k for k, s in enumerate(old_starts) if s <= f)
        return new_starts[i] + round((f - old_starts[i]) * (new_ends[i] - new_starts[i]) / (old_ends[i] - old_starts[i]))

    for s in plan['segments']:
        duration = (s['end_frame'] - s['start_frame']) / fps
        s['start_frame'], s['end_frame'] = remap(s['start_frame']), remap(s['end_frame'])
        if s['mode'] == 'footage':
            target = (s['end_frame'] - s['start_frame']) / fps
            s['source_span'] = round(min(s.get('source_span', duration), target), 3)
            ratio = target / s['source_span']
            print(f"{s['id']} {ratio:.2f}x duration{'  OVER LIMIT' if ratio > a.limit else ''}")
    for c, start, end in zip(caps, new_starts, new_ends):
        c['start_frame'], c['end_frame'] = start, end
    plan['captions'] = [c for c in caps if not c.get('silent')]
    plan['total_frames'] = total
    plan['audio'] = a.audio
    work, output = Path(plan['work']), Path(plan['output'])
    root = work.parent.parent
    plan['work'] = (root / a.version / 'work').as_posix()
    plan['output'] = (root / a.version / output.name.replace(work.parent.name, a.version)).as_posix()
    a.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf8')
    print(f'{total} frames, {total / fps:.2f}s')


if __name__ == '__main__':
    main()
