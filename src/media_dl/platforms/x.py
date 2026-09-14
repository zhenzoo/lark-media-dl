"""Resolve public X video posts with FxTwitter."""
import re
UA = "Mozilla/5.0"

def twitter_via_fxtwitter(url: str, proxy: str | None):
    """用 fxtwitter API 解出推文视频。返回 {m3u8, direct_url, title, author, duration, id, meta} 或 None。
    优先返回 m3u8(HLS 分片, 配 -N 多路并行最快); 无则回退最高清 mp4 直链。"""
    import requests
    m = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)/status/(\d+)", url)
    if m:
        user, sid = m.group(1), m.group(2)
    else:
        m2 = re.search(r"status/(\d+)", url)
        sid, user = (m2.group(1) if m2 else None), "i"
    if not sid:
        return None
    api = f"https://api.fxtwitter.com/{user}/status/{sid}"
    # fxtwitter API 国内通常直连可达; 直连失败再走代理 (视频 CDN video.twimg.com 才是必须走代理的)
    j = None
    for use_proxy in (False, True):
        try:
            s = requests.Session(); s.trust_env = False
            proxies = ({"http": proxy, "https": proxy} if (use_proxy and proxy) else None)
            r = s.get(api, timeout=30, proxies=proxies, headers={"User-Agent": UA})
            j = r.json()
            if j:
                break
        except Exception:
            continue
    tw = (j or {}).get("tweet") or {}
    videos = ((tw.get("media") or {}).get("videos") or [])
    if not videos:
        return None
    v = videos[0]
    m3u8 = None
    for fmt in (v.get("formats") or []):
        if fmt.get("container") == "m3u8" and fmt.get("url"):
            m3u8 = fmt["url"]; break
    if not m3u8:
        for var in (v.get("variants") or []):
            if "m3u8" in (var.get("content_type", "") + var.get("url", "")):
                m3u8 = var.get("url"); break
    return {
        "m3u8": m3u8,
        "direct_url": v.get("url"),   # 最高清渐进式 mp4 (无 m3u8 时兜底)
        "title": (tw.get("text") or f"tweet-{sid}").strip().split("\n")[0][:80],
        "author": (tw.get("author") or {}).get("screen_name"),
        "duration": v.get("duration"),
        "width": v.get("width"), "height": v.get("height"),
        "id": sid,
    }
