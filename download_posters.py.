"""Download explicitly approved poster IDs, using the published catalog rows."""
import io
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PATTERN = re.compile(r'/images/posters/kp/([1-9][0-9]*)\.jpg')
HOSTS = {'kinopoiskapiunofficial.tech', 'st.kp.yandex.net', 'avatars.mds.yandex.net'}
LIMIT = 12 * 1024 * 1024


def poster_id(url):
    try:
        u = urlsplit(url)
        if u.scheme != 'https' or u.netloc != 'kinopoiskapiunofficial.tech':
            return None
        m = PATTERN.fullmatch(u.path)
        return m[1] if m and not u.query and not u.fragment else None
    except ValueError:
        return None


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        if u.scheme != 'https' or u.netloc not in HOSTS:
            raise ValueError('Unexpected redirect destination')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def prepare_posters(rows, root=ROOT):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 30_000_000
    approval = root / 'poster-approved-ids.txt'
    approved = set()
    if approval.exists():
        for line in approval.read_text(encoding='utf-8').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                if not re.fullmatch(r'[1-9][0-9]*', line):
                    raise ValueError('Invalid approved poster ID: ' + line)
                approved.add(line)
    cache = root / '.poster-cache'
    cache.mkdir(exist_ok=True)
    opener = urllib.request.build_opener(SafeRedirect())
    result = {}
    for category, row in rows:
        url = row.get('Постер', '')
        kp = poster_id(url)
        if not kp or kp not in approved:
            continue
        target = cache / (kp + '.webp')
        try:
            if target.exists():
                try:
                    with Image.open(target) as im:
                        if im.format != 'WEBP' or im.width > 500 or im.height > 750:
                            raise ValueError('Invalid cached image')
                        im.load()
                except Exception:
                    target.unlink()
            if not target.exists():
                req = urllib.request.Request(url, headers={'User-Agent': 'SCREENCAPS catalog builder'})
                with opener.open(req, timeout=15) as response:
                    if response.status != 200 or response.headers.get_content_type() not in {'image/jpeg', 'image/png', 'image/webp'}:
                        raise ValueError('Unexpected image response')
                    data = response.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise ValueError('Image too large')
                with Image.open(io.BytesIO(data)) as im:
                    im = ImageOps.exif_transpose(im).convert('RGB')
                    im.thumbnail((500, 750), Image.Resampling.LANCZOS)
                    tmp = target.with_suffix('.tmp')
                    im.save(tmp, 'WEBP', quality=78, method=4)
                    tmp.replace(target)
                print('Poster downloaded:', kp)
            result[row['ID']] = target
        except Exception as exc:
            print('Poster unavailable:', kp, type(exc).__name__)
    print('Approved posters available:', len(result), 'of', len(rows))
    return result
