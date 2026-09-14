"""Copy deployable Miaoda source to the user's initialized app checkout."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / 'apps/miaoda'
    target = args.target.expanduser().resolve()
    if not (target / '.git').exists() or target == root or target.is_relative_to(source):
        parser.error('Target must be a separate initialized Miaoda Git checkout')
    roots = ['client', 'server', 'shared', 'scripts', 'docs', 'tests']
    files = [p for name in roots for p in (source / name).rglob('*') if p.is_file()]
    names = ['package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json',
             'tsconfig.node.json', 'tailwind.config.ts', 'postcss.config.js', 'nest-cli.json', '.env.example', '.gitignore']
    files += [source / name for name in names if (source / name).is_file()]
    for file in files:
        relative = file.relative_to(source)
        if any(part in ('node_modules', 'dist', '.local', '__pycache__') for part in relative.parts):
            raise RuntimeError('Refusing generated directory in deployment source')
        if file.name.startswith('.env') and file.name != '.env.example':
            raise RuntimeError('Refusing private environment file')
        destination = target / relative
        print(relative)
        if args.apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)
    print('Source copied.' if args.apply else 'Preview only; add --apply after inspecting the target checkout.')
    print('Review Git diff, configure this app\'s database and Key, then commit/push sprint/default and release.')


if __name__ == '__main__':
    main()
