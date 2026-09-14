"""Public Bilibili anonymous cookies; no user login credentials."""
import hashlib,hmac,time
from pathlib import Path
from http.cookiejar import MozillaCookieJar,Cookie
from ..config import config_dir
UA = "Mozilla/5.0"
CACHE_DIR = config_dir() / "cache"

def _gen_bili_ticket(ts: int) -> str | None:
    """B站 web 风控票据. HMAC-SHA256(key='XgwSnGZ1p', msg='ts'+ts) → GenWebTicket."""
    try:
        import requests
        sign = hmac.new(b"XgwSnGZ1p", f"ts{ts}".encode(), hashlib.sha256).hexdigest()
        r = requests.post(
            "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket",
            params={"key_id": "ec02", "hexsign": sign, "context[ts]": str(ts), "csrf": ""},
            headers={"User-Agent": UA}, timeout=15)
        return (r.json().get("data") or {}).get("ticket")
    except Exception:
        return None

def bili_anon_cookiejar(force: bool = False) -> str:
    """生成/缓存 B站匿名 cookiejar (buvid3 + b_nut + bili_ticket). 返回文件路径.
    12 小时内复用缓存. 这些 cookie 无需登录, 仅用于过风控。"""
    import requests
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "bili_anon_cookies.txt"
    if path.exists() and not force and (time.time() - path.stat().st_mtime) < 12 * 3600:
        return str(path)

    s = requests.Session()
    s.trust_env = False   # 国内站强制直连, 忽略系统全局代理
    s.headers.update({"User-Agent": UA})
    try:
        s.get("https://www.bilibili.com/", timeout=15)          # → buvid3 + b_nut
        s.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=15)  # → 补 buvid
    except Exception as e:
        # 网络问题也写一个空 jar, 让 yt-dlp 自己再试
        pass

    jar = MozillaCookieJar(str(path))
    now = int(time.time())
    have = {c.name: c.value for c in s.cookies}
    # 确保关键 cookie 存在 (buvid3 兜底随机不可行, 用 SPI 已写入的)
    def add(name, value, exp):
        jar.set_cookie(Cookie(0, name, value, None, False, ".bilibili.com", True, True,
                              "/", False, False, exp, False, None, None, {}))
    for name, value in have.items():
        add(name, value, now + 365 * 24 * 3600)
    tk = _gen_bili_ticket(now)
    if tk:
        add("bili_ticket", tk, now + 3 * 24 * 3600)
    jar.save(ignore_discard=True, ignore_expires=True)
    return str(path)
