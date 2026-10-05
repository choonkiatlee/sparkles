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
    parser.add_argument('--diagnostic-indices',help='Explicit comma-separated source indices for comparable views')
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    if source == output or source in output.parents or output in source.parents:
        parser.error('Input and output must be disjoint directories')
    try:
        indices=[int(x) for x in args.diagnostic_indices.split(',')] if args.diagnostic_indices else None
        metadata = run(source, output, args.order_manifest,gain=args.gain,diagnostic_indices=indices)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    accepted=sum('registration' in r for r in metadata['frames'])
    print(f'{metadata["valid_count"]}/{metadata["frame_count"]} valid images; {accepted} accepted outlines; diagnostics: {metadata["diagnostics"]["status"]} -> {output}')
    if not accepted: print('QC required: no complete outline accepted; candidate masks/failures are recorded')

if __name__ == '__main__':
    main()
