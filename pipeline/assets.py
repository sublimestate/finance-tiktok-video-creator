"""Fetch stock footage/images from Pexels/Pixabay and news images via DuckDuckGo."""

import json
import re
import time
import subprocess
import requests
from pathlib import Path
from typing import Optional, List


def search_pexels_video(api_key: str, query: str) -> Optional[str]:
    """Search Pexels for a vertical video and return the download URL."""
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params={"query": query, "orientation": "portrait", "per_page": 5},
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        return None

    # Pick the first video, find the best quality file
    video = videos[0]
    files = video.get("video_files", [])
    # Prefer HD portrait
    best = None
    for f in files:
        if f.get("height", 0) >= 1080:
            best = f
            break
    if not best and files:
        best = files[0]
    return best["link"] if best else None


def search_pexels_image(api_key: str, query: str) -> Optional[str]:
    """Search Pexels for a portrait image and return the download URL."""
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={"query": query, "orientation": "portrait", "per_page": 5},
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    if not photos:
        return None
    return photos[0]["src"]["large2x"]


def search_pixabay_video(api_key: str, query: str) -> Optional[str]:
    """Fallback: search Pixabay for a video."""
    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": api_key, "q": query, "per_page": 5},
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return None
    videos = hits[0].get("videos", {})
    large = videos.get("large", videos.get("medium", {}))
    return large.get("url")


def search_pixabay_image(api_key: str, query: str) -> Optional[str]:
    """Fallback: search Pixabay for an image."""
    resp = requests.get(
        "https://pixabay.com/api/",
        params={"key": api_key, "q": query, "per_page": 5, "orientation": "vertical"},
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return None
    return hits[0].get("largeImageURL")


def search_serpapi_images(api_key: str, query: str, num: int = 5) -> List[str]:
    """Search Google Images via SerpAPI. Returns list of image URLs."""
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={
            "api_key": api_key,
            "q": query,
            "tbm": "isch",
            "num": num,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    data = resp.json()
    urls = []
    for item in data.get("images_results", [])[:num]:
        url = item.get("original", "")
        if url and url.startswith("http"):
            urls.append(url)
    return urls


def search_google_images(api_key: str, cx: str, query: str, num: int = 5) -> List[str]:
    """Search Google Custom Search for images. Returns list of image URLs."""
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": api_key,
            "cx": cx,
            "q": query,
            "searchType": "image",
            "num": num,
            "imgSize": "large",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    data = resp.json()
    urls = []
    for item in data.get("items", []):
        link = item.get("link", "")
        if link:
            urls.append(link)
    return urls


def search_news_image(
    query: str,
    google_api_key: str = "",
    google_cx: str = "",
    serpapi_key: str = "",
) -> Optional[str]:
    """Search for a news/event image. Tries SerpAPI → Google CSE → DuckDuckGo."""
    # Try SerpAPI first (best results)
    if serpapi_key:
        urls = search_serpapi_images(serpapi_key, query)
        if urls:
            return urls[0]

    # Try Google Custom Search
    if google_api_key and google_cx:
        urls = search_google_images(google_api_key, google_cx, query)
        if urls:
            return urls[0]

    # Fallback: DuckDuckGo (no API key needed)
    try:
        token_resp = requests.get(
            "https://duckduckgo.com/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=10,
        )
        vqd_match = re.search(r"vqd=['\"]([^'\"]+)['\"]", token_resp.text)
        if not vqd_match:
            vqd_match = re.search(r"vqd=(\d+-\d+)", token_resp.text)
        if not vqd_match:
            return None
        vqd = vqd_match.group(1)

        resp = requests.get(
            "https://duckduckgo.com/i.js",
            params={
                "l": "us-en", "o": "json", "q": query,
                "vqd": vqd, "f": ",,,,,", "p": "1",
            },
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        for result in data.get("results", [])[:5]:
            img_url = result.get("image", "")
            if img_url and img_url.startswith("http"):
                return img_url
    except Exception:
        pass
    return None


def download_file(url: str, output_path: str) -> None:
    """Download a file from URL. Raises on HTML responses or failures."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "html" in content_type.lower():
        raise ValueError(f"Got HTML instead of image from {url}")
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    # Verify it's not HTML
    with open(output_path, "rb") as f:
        header = f.read(20)
    if b"<!DOCTYPE" in header or b"<html" in header:
        Path(output_path).unlink()
        raise ValueError(f"Downloaded HTML instead of image from {url}")


def trim_video(input_path: str, output_path: str, max_duration: float) -> None:
    """Trim a video to max_duration seconds."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-t", str(max_duration),
         "-c", "copy", output_path],
        capture_output=True,
    )


def fetch_asset(
    scene_index: int,
    visual_type: str,
    query: str,
    pexels_key: str,
    pixabay_key: Optional[str],
    tmp_dir: str,
    max_video_length: float = 15.0,
    google_api_key: str = "",
    google_cx: str = "",
    serpapi_key: str = "",
) -> Optional[str]:
    """Fetch a stock asset for a scene. Returns the local file path or None."""
    tmp = Path(tmp_dir) / "assets"
    tmp.mkdir(parents=True, exist_ok=True)

    if visual_type == "stock_video":
        url = search_pexels_video(pexels_key, query)
        if not url and pixabay_key:
            url = search_pixabay_video(pixabay_key, query)
        if not url:
            return None
        ext = "mp4"
        raw_path = str(tmp / f"scene_{scene_index:03d}_raw.{ext}")
        final_path = str(tmp / f"scene_{scene_index:03d}.{ext}")
        download_file(url, raw_path)
        trim_video(raw_path, final_path, max_video_length)
        return final_path

    elif visual_type == "stock_image":
        url = search_pexels_image(pexels_key, query)
        if not url and pixabay_key:
            url = search_pixabay_image(pixabay_key, query)
        if not url:
            return None
        ext = "jpg"
        final_path = str(tmp / f"scene_{scene_index:03d}.{ext}")
        download_file(url, final_path)
        return final_path

    elif visual_type == "news_image":
        ext = "jpg"
        final_path = str(tmp / f"scene_{scene_index:03d}.{ext}")

        # Try SerpAPI results (multiple URLs)
        if serpapi_key:
            urls = search_serpapi_images(serpapi_key, query, num=5)
            for url in urls:
                try:
                    download_file(url, final_path)
                    return final_path
                except Exception:
                    continue

        # Try single news_image search (Google CSE / DuckDuckGo)
        url = search_news_image(query, google_api_key=google_api_key, google_cx=google_cx)
        if url:
            try:
                download_file(url, final_path)
                return final_path
            except Exception:
                pass

        # Fallback to Pexels
        url = search_pexels_image(pexels_key, query)
        if url:
            try:
                download_file(url, final_path)
                return final_path
            except Exception:
                pass

        return None

    # solid_color needs no asset
    return None
