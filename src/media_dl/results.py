"""Publish completed files without overwriting existing downloads."""
from pathlib import Path
import shutil

def save_loose_files(files: list[Path], outdir: Path) -> list[str]:
    """Copy finished media beside each other; never replace an existing file."""
    outdir.mkdir(parents=True, exist_ok=True)
    saved = []
    for source in files:
        counter = 0
        while True:
            name = source.name if counter == 0 else f"{source.stem} ({counter}){source.suffix}"
            target = outdir / name
            try:
                destination = target.open("xb")
            except FileExistsError:
                counter += 1
                continue
            try:
                with destination, source.open("rb") as original:
                    shutil.copyfileobj(original, destination)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            saved.append(str(target))
            break
    return saved
