"""Download optional open-source fonts for *local* packaging of Yomu Note.

Run once on your development computer with internet. This script retrieves font
software and the matching SIL Open Font License notices from Google's official
font repository. Yomu itself never contacts a font server; standalone builds
copy the locally downloaded files via PyInstaller's --add-data option.

Files are downloaded with a byte cap and validated as sfnt fonts before use.
If a download fails, existing files are left untouched; Yomu uses system fonts.
"""
from pathlib import Path
from urllib.request import Request, urlopen
import os
import tempfile

BASE = 'https://raw.githubusercontent.com/google/fonts/main/ofl/'
ASSETS = Path(__file__).resolve().parent / 'assets' / 'fonts'
FONT_FILES = (
    ('mochiypopone', 'MochiyPopOne-Regular.ttf', 'MochiyPopOne-Regular.ttf'),
    ('nunito', 'Nunito%5Bwght%5D.ttf', 'Nunito-wght.ttf'),
    ('nunito', 'Nunito-Italic%5Bwght%5D.ttf', 'Nunito-Italic-wght.ttf'),
    # Default application UI: the two variable-weight Montserrat fonts.
    # Font files and their OFL notices are fetched only when building.
    ('montserrat', 'Montserrat%5Bwght%5D.ttf', 'Montserrat-wght.ttf'),
    ('montserrat', 'Montserrat-Italic%5Bwght%5D.ttf', 'Montserrat-Italic-wght.ttf'),
)
LIMIT = 11 * 1024 * 1024


def download_file(url: str, destination: Path, *, expect_font: bool) -> None:
    """Fetch into a temporary file and replace the destination only on success."""
    if destination.exists() and destination.stat().st_size > 100:
        print('Already present:', destination.relative_to(ASSETS))
        return
    request = Request(url, headers={'User-Agent': 'YomuNoteFontSetup/0.3.4a'})
    with urlopen(request, timeout=30) as response:
        data = response.read(LIMIT + 1)
    if not data or len(data) > LIMIT:
        raise ValueError(f'Unexpected file size for {url}')
    if expect_font and data[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
        raise ValueError(f'Expected a valid sfnt font from {url}')
    if not expect_font and b'OPEN FONT LICENSE' not in data.upper():
        raise ValueError(f'Expected an Open Font License notice from {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=destination.parent, prefix='.font-')
    try:
        with os.fdopen(handle, 'wb') as output:
            output.write(data)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    print('Ready:', destination.relative_to(ASSETS))


def main() -> None:
    for family, remote_file, local_file in FONT_FILES:
        dest_dir = ASSETS / family
        # Keep an OFL notice adjacent to every distributable family.
        download_file(BASE + family + '/OFL.txt', dest_dir / 'OFL.txt', expect_font=False)
        download_file(BASE + family + '/' + remote_file, dest_dir / local_file,
                      expect_font=True)
    print('Fonts ready. Run your platform build script to embed them.')


if __name__ == '__main__':
    main()
