"""python -m build_patch  apply | restore | status | build"""
import argparse
import sys

from . import config, patcher

def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m build_patch',
                                 description='Make the Exanima Physique box affect gameplay (edit config.ini to change the numbers).')
    ap.add_argument('command', choices=['apply', 'restore', 'status', 'build'],
                    help='apply: patch Exanima.exe (re-run after editing config.ini) | restore: undo | status: show what is active | '
                         'build: write a patched COPY to --out and change nothing else')
    ap.add_argument('--config', help='path to a config.ini (default: the one next to this project)')
    ap.add_argument('--exe', help='path to Exanima.exe (default: auto-detect the Steam install)')
    ap.add_argument('--out', help='output file for the build command')
    a = ap.parse_args(argv)
    try:
        cfg = config.load(a.config)
        if a.command == 'apply': patcher.apply(cfg, a.exe)
        elif a.command == 'restore': patcher.restore(cfg, a.exe)
        elif a.command == 'status': patcher.status(cfg, a.exe)
        else:
            if not a.out: ap.error('build needs --out')
            patcher.build_copy(cfg, a.out, a.exe)
    except (config.ConfigError, patcher.PatchError) as e:
        print('\nERROR:', e)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
