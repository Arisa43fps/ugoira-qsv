#!/usr/bin/env python3
"""Pengganti run.bat/run.ps1: download ugoira Pixiv -> MP4 dengan ringkasan rapi.

Contoh:
    python run.py 151723034 151673020
    python run.py --config gallery-dl-444.conf --browser helium
    python run.py --keep-zip --verbose <URL>
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")


def fmt_size(n):
    if n is None:
        return "-"
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def fmt_dur(s):
    s = max(0.0, s)
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(s, 60)
    return f"{int(m)}m{sec:04.1f}s"


def normalize_token(tok):
    t = tok.strip().strip("\"'")
    if re.fullmatch(r"\d{5,}", t):
        return f"https://www.pixiv.net/artworks/{t}"
    return t


def collect_inputs(args, urls_file):
    tokens = []
    for raw in args:
        tokens.extend(re.split(r"[\s,;]+", raw))
    if not tokens and os.path.isfile(urls_file):
        with open(urls_file, encoding="utf-8", errors="ignore") as f:
            tokens.extend(re.split(r"[\s,;]+", f.read()))
    out, seen = [], set()
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        u = normalize_token(t)
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def find_gallerydl():
    if shutil.which("gallery-dl"):
        return ["gallery-dl"]
    return [sys.executable, "-m", "gallery_dl"]


def artwork_id(url):
    m = re.search(r"/artworks/(\d+)", url)
    return m.group(1) if m else url


def snapshot_sizes(aid):
    """Kembalikan (zip_path, zip_size, mp4_path, mp4_size) untuk satu artwork id."""
    zpath = os.path.join(DOWNLOAD_DIR, f"{aid}.zip")
    mpath = os.path.join(DOWNLOAD_DIR, f"{aid}.mp4")
    zs = os.path.getsize(zpath) if os.path.isfile(zpath) else None
    ms = os.path.getsize(mpath) if os.path.isfile(mpath) else None
    return zpath, zs, mpath, ms


def patched_config(src, show_ffmpeg):
    with open(src, encoding="utf-8") as f:
        cfg = json.load(f)
    for pp in cfg.get("postprocessors", []):
        if isinstance(pp, dict) and pp.get("name") == "ugoira":
            pp["keep-files"] = True  # simpan ZIP sementara agar ukurannya bisa dilaporkan
            if show_ffmpeg:
                pp["ffmpeg-output"] = "info"
    dl = cfg.setdefault("downloader", {})
    dl.setdefault("progress", 0)  # tampilkan progress bar + kecepatan sejak awal
    out = cfg.setdefault("output", {})
    out.setdefault("progress", True)
    out.setdefault("shorten", True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", delete=False, encoding="utf-8", dir=BASE_DIR
    )
    json.dump(cfg, tmp, indent=4)
    tmp.close()
    return tmp.name


def main():
    ap = argparse.ArgumentParser(description="Download ugoira Pixiv dengan ringkasan rapi.")
    ap.add_argument("inputs", nargs="*", help="ID / URL Pixiv (boleh bulk, koma/spasi).")
    ap.add_argument("--config", default="gallery-dl.conf")
    ap.add_argument("--browser", default="helium")
    ap.add_argument("--urls-file", default=os.path.join(BASE_DIR, "urls.txt"))
    ap.add_argument("--keep-zip", action="store_true", help="Simpan ZIP mentah, jangan hapus.")
    ap.add_argument("--verbose", "-v", action="store_true", help="Teruskan -v ke gallery-dl.")
    ap.add_argument("--ffmpeg-log", action="store_true", help="Tampilkan log ffmpeg (ffmpeg-output=info).")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        print("[error] ffmpeg tidak ditemukan. Install via: winget install Gyan.FFmpeg")
        return 1

    urls = collect_inputs(a.inputs, a.urls_file)
    if not urls:
        line = input("Masuk ID atau URL Pixiv (pisah spasi untuk bulk): ").strip()
        urls = collect_inputs([line], a.urls_file)
    if not urls:
        print("[error] Tidak ada input. Contoh: python run.py 151723034 151673020")
        return 1

    cfg_src = a.config if os.path.isfile(a.config) else os.path.join(BASE_DIR, a.config)
    if not os.path.isfile(cfg_src):
        print(f"[error] Config tidak ditemukan: {a.config}")
        return 1
    cfg_tmp = patched_config(cfg_src, a.ffmpeg_log)

    base = find_gallerydl()
    try:
        print(f"Download {len(urls)} karya | config={os.path.basename(cfg_src)} browser={a.browser}")
        print("-" * 64)
        total_zip = total_mp4 = 0
        n_ok = 0
        t_all = time.time()
        for i, url in enumerate(urls, 1):
            aid = artwork_id(url)
            print(f"[{i}/{len(urls)}] {aid} ...")
            cmd = base + ["--config", cfg_tmp, "--cookies-from-browser", a.browser]
            if a.verbose:
                cmd.append("--verbose")
            cmd.append(url)
            t0 = time.time()
            rc = subprocess.run(cmd, cwd=BASE_DIR).returncode
            dt = time.time() - t0
            zpath, zs, mpath, ms = snapshot_sizes(aid)
            if rc != 0:
                print(f"  GAGAL (exit {rc}) | {fmt_dur(dt)}")
                continue
            n_ok += 1
            zs = zs or 0
            ms = ms or 0
            total_zip += zs
            total_mp4 += ms
            ratio = (ms / zs * 100) if zs else 0
            speed = (zs / dt) if dt > 0 and zs else 0
            print(f"  ZIP mentah : {fmt_size(zs)}")
            print(f"  MP4 jadi   : {fmt_size(ms)} ({ratio:.0f}% dari ZIP)")
            print(f"  Waktu      : {fmt_dur(dt)} | ~{fmt_size(speed)}/s (rata-rata item ini)")
            if not a.keep_zip and zs and os.path.isfile(zpath) and os.path.isfile(mpath):
                os.remove(zpath)
                print("  (ZIP mentah dihapus kembali)")
        print("-" * 64)
        print(f"Selesai {n_ok}/{len(urls)} dalam {fmt_dur(time.time() - t_all)}")
        print(f"Total ZIP mentah: {fmt_size(total_zip)} | Total MP4: {fmt_size(total_mp4)}")
        return 0 if n_ok == len(urls) else 2
    finally:
        try:
            os.remove(cfg_tmp)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
