"""Read a public Threads post and preserve its text and media locally."""

from __future__ import annotations

import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests


ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
MEDIA_DOMAINS = ("fbcdn.net", "cdninstagram.com", "giphy.com", "tenor.com")


def shortcode_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "threads.com", "www.threads.com", "threads.net", "www.threads.net"
    } or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("请粘贴 threads.com 或 threads.net 的 HTTPS 帖子链接")
    match = re.fullmatch(r"/(?:@[^/]+/post|t)/([A-Za-z0-9_-]{5,30})/?", parsed.path)
    if not match:
        raise ValueError("请复制 Threads 单条帖子的链接（包含 /post/ 或 /t/）")
    return match.group(1)


def post_id_from_shortcode(code: str) -> str:
    value = 0
    for character in code:
        value = value * 64 + ALPHABET.index(character)
    return str(value)


def find_post(payload: Any, code: str) -> dict[str, Any]:
    """Responses may contain ancestors and replies; only accept the linked post."""
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if value.get("code") == code and "media_type" in value:
                info = value.get("text_post_app_info") or {}
                if info.get("is_post_unavailable") or value.get("is_post_unavailable"):
                    raise RuntimeError("这条 Threads 帖子不可访问，可能已删除或限制访问")
                return value
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    raise RuntimeError("未找到链接对应的 Threads 帖子；未将其他帖子或回复当作结果")


def best_version(versions: list[dict[str, Any]], quality: str = "best") -> dict[str, Any]:
    candidates = [item for item in versions if isinstance(item.get("url"), str)]
    if not candidates:
        raise RuntimeError("帖子包含媒体，但没有返回可下载地址")
    if quality != "best":
        capped = [item for item in candidates if 0 < min(
            item.get("width") or 0, item.get("height") or 0
        ) <= int(quality)]
        if capped:
            candidates = capped
    return max(candidates, key=lambda item: (item.get("width") or 0) * (item.get("height") or 0))


@dataclass(frozen=True)
class MediaAsset:
    kind: str
    url: str


def media_assets(post: dict[str, Any], quality: str) -> list[MediaAsset]:
    giphy = post.get("giphy_media_info")
    if giphy:
        versions = giphy.get("images") or {}
        rendition = versions.get("original") or versions.get("fixed_height") or {}
        url = rendition.get("url") or rendition.get("webp") or rendition.get("mp4")
        if not url:
            raise RuntimeError("检测到 GIF 动图，但平台没有返回动画文件地址")
        return [MediaAsset("animation", url)]
    items = post.get("carousel_media") or [post]
    assets: list[MediaAsset] = []
    for item in items:
        videos = item.get("video_versions") or []
        images = (item.get("image_versions2") or {}).get("candidates") or []
        if videos:
            assets.append(MediaAsset("video", best_version(videos, quality)["url"]))
        elif item.get("media_type") == 2:
            raise RuntimeError("视频没有返回可下载地址，未将封面图片当作视频")
        elif images and (item.get("media_type") != 19):
            assets.append(MediaAsset("image", best_version(images)["url"]))
        elif item.get("media_type") in (1, 2, 8) or len(items) > 1:
            raise RuntimeError("帖子中的部分媒体缺少下载地址，未交付不完整结果")
    return assets


def post_text(post: dict[str, Any]) -> str:
    caption = post.get("caption") or ""
    text = caption.get("text", "") if isinstance(caption, dict) else str(caption)
    return text


def metadata(post: dict[str, Any]) -> dict[str, Any]:
    username = (post.get("user") or {}).get("username") or "Threads"
    return {
        "title": post_text(post).strip()[:1000] or f"{username} 的 Threads 帖子",
        "uploader": username,
    }


class ThreadsClient:
    def __init__(self, env: dict[str, str], heartbeat: Callable[[], None] = lambda: None) -> None:
        self.key = env.get("TIKHUB_API_KEY", "").strip()
        self.base = env.get("TIKHUB_BASE", "https://api.tikhub.dev").rstrip("/")
        if not self.key:
            raise RuntimeError("Threads 下载需要配置 TIKHUB_API_KEY；无需 Threads 登录 Cookie")
        if not self.base.startswith("https://"):
            raise ValueError("TIKHUB_BASE 必须是 HTTPS 地址")
        self.proxy = env.get("MEDIA_DL_PROXY") or env.get("HTTPS_PROXY")
        self.heartbeat = heartbeat
        self.ffmpeg = env.get("FFMPEG_BINARY") or shutil.which("ffmpeg")
        if not self.ffmpeg:
            try:
                import imageio_ffmpeg

                self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                pass

    def fetch_post(self, url: str) -> dict[str, Any]:
        code = shortcode_from_url(url)
        # Keep the worker online while the provider is resolving the public post.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._fetch, post_id_from_shortcode(code))
            while True:
                try:
                    payload = future.result(timeout=15)
                    break
                except TimeoutError:
                    self.heartbeat()
        return find_post(payload, code)

    def _fetch(self, post_id: str) -> dict[str, Any]:
        # API credentials are never put on the separate CDN download session.
        with requests.Session() as session:
            session.trust_env = False
            try:
                response = session.get(
                    f"{self.base}/api/v1/threads/web/fetch_post_detail",
                    params={"post_id": post_id},
                    headers={"Authorization": f"Bearer {self.key}", "Accept-Encoding": "identity"},
                    timeout=(15, 90),
                )
                if response.status_code in (401, 403):
                    raise RuntimeError("TikHub Key 无效或未开放 Threads 接口权限，请检查配置")
                if response.status_code == 402:
                    raise RuntimeError("TikHub 余额不足，请充值后重试")
                if response.status_code == 429:
                    raise RuntimeError("Threads 解析接口暂时限流，请稍后重试")
                if response.status_code != 200:
                    raise RuntimeError(f"Threads 解析接口返回 HTTP {response.status_code}，请稍后重试")
                payload = response.json()
            except requests.RequestException as error:
                raise RuntimeError("无法连接 Threads 解析接口，请检查网络后重试") from error
            except ValueError as error:
                raise RuntimeError("Threads 解析接口未返回有效数据，请稍后重试") from error
        if not isinstance(payload, dict) or payload.get("code") != 200:
            raise RuntimeError("Threads 解析接口未成功返回帖子，请稍后重试")
        return payload.get("data") or {}

    @staticmethod
    def validate_media_url(url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443)
                or not any(host == domain or host.endswith("." + domain) for domain in MEDIA_DOMAINS)):
            raise RuntimeError("平台返回了未支持的媒体地址，已停止下载")

    def download_asset(self, asset: MediaAsset, stem: Path) -> Path:
        with requests.Session() as session:
            session.trust_env = False
            if self.proxy:
                session.proxies.update({"http": self.proxy, "https": self.proxy})
            url = asset.url
            for _ in range(5):
                self.validate_media_url(url)
                try:
                    response = session.get(url, stream=True, allow_redirects=False, timeout=(15, 30))
                except requests.RequestException as error:
                    raise RuntimeError("Threads 媒体下载连接失败，请检查网络或 MEDIA_DL_PROXY") from error
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("Location", ""))
                    response.close()
                    continue
                break
            else:
                raise RuntimeError("Threads 媒体下载重定向次数过多")
            with response:
                if response.status_code != 200:
                    raise RuntimeError(f"Threads 媒体下载返回 HTTP {response.status_code}，请重新排队获取新地址")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                extensions = {
                    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                    "image/gif": ".gif", "video/mp4": ".mp4", "video/quicktime": ".mov",
                }
                extension = extensions.get(content_type)
                if not extension:
                    raise RuntimeError("下载地址未返回支持的图片或视频文件，未保存网页作为媒体")
                target = stem.with_suffix(extension)
                total = 0
                with target.open("xb") as output:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            output.write(chunk)
                            total += len(chunk)
                        self.heartbeat()
                expected = response.headers.get("Content-Length")
                if total == 0 or (expected and not response.headers.get("Content-Encoding") and total != int(expected)):
                    raise RuntimeError("Threads 媒体文件未完整下载，请重新排队")
                return target

    def download(self, post: dict[str, Any], source_url: str, outdir: Path,
                 quality: str, audio_only: bool = False) -> list[Path]:
        outdir.mkdir(parents=True, exist_ok=True)
        code = shortcode_from_url(source_url)
        username = re.sub(r"[^A-Za-z0-9._-]", "-", (post.get("user") or {}).get("username") or "post")[:60]
        prefix = f"Threads-{username}-{code}"
        assets = media_assets(post, quality)
        if audio_only:
            assets = [asset for asset in assets if asset.kind == "video"]
            if not assets:
                raise RuntimeError("这条 Threads 帖子没有视频音轨；请选择下载内容保存文字、图片或动图")
            if not self.ffmpeg:
                raise RuntimeError("提取音频需要安装 FFmpeg，或设置 FFMPEG_BINARY")
        if not assets and not post_text(post).strip():
            raise RuntimeError("这条 Threads 帖子没有可保存的正文或媒体")
        files: list[Path] = []
        for index, asset in enumerate(assets, 1):
            stem = outdir / (prefix if len(assets) == 1 else f"{prefix}-{index:02d}")
            file = self.download_asset(asset, stem)
            if audio_only:
                audio = stem.with_suffix(".mp3")
                result = subprocess.run(
                    [str(self.ffmpeg), "-nostdin", "-n", "-i", str(file), "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(audio)],
                    capture_output=True, timeout=900,
                )
                if result.returncode != 0 or not audio.exists():
                    raise RuntimeError("该视频无法提取音频，可能没有音轨")
                file = audio
            files.append(file)
        if not audio_only:
            text_file = outdir / f"{prefix}.txt"
            text_file.write_text(
                f"{post_text(post)}\n\n作者：@{username}\n原帖：{source_url}\n",
                encoding="utf-8",
            )
            files.append(text_file)
        return files
