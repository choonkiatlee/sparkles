"""Command-line entry point; successive stages extend the same manifest."""
import argparse
import json
from pathlib import Path
from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description='Preprocess extracted diamond 360 frames')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--order-manifest', type=Path)
    parser.add_argument('--gain',type=float,default=1.0,help='Optional fixed sequence-wide luminance gain (0.9..1.1)')
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    if source == output or source in output.parents or output in source.parents:
        parser.error('Input and output must be disjoint directories')
    try:
        metadata = run(source, output, args.order_manifest,gain=args.gain)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sequence.json').write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n')
    print(f'{metadata["valid_count"]}/{metadata["frame_count"]} valid frames -> {output}')

if __name__ == '__main__':
    main()
