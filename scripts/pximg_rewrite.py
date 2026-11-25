"""Rewrite i.pximg.net -> reverse-proxy sendiri (mis. Cloudflare Workers).

Didaftarkan sebagai post-processor "python" dengan event "init", sehingga
fungsi install() jalan SEKALI sebelum download apa pun dan memonkey-patch
DownloadJob.handle_url: setiap URL i.pximg.net ditulis ulang ke domain
worker, URL asli disimpan sebagai fallback (dipakai otomatis jika gagal).

Worker harus reverse-proxy transparan: teruskan path + query apa adanya,
mis. https://pximg.example.com/img-original/img/....jpg -> i.pximg.net/...,
dan sertakan header Referer https://www.pixiv.net/ (wajib oleh Pixiv).

Aktifkan lewat gallery-dl.conf:
  ganti PROXY_HOST di bawah ATAU set env PXIMG_PROXY_HOST,
  lalu tambah post-processor pertama:
    {"name": "python@init", "function": "scripts/pximg_rewrite.py:install"}
"""

import os

ORIGIN_HOST = "i.pximg.net"
PROXY_HOST = "px.arisa43fps.pp.ua"

_patched = False


def _rewrite(url):
    if isinstance(url, str) and ORIGIN_HOST in url \
            and not url.startswith("text:"):
        return url.replace(ORIGIN_HOST, PROXY_HOST, 1)
    return url


def install(_kwdict=None):
    global _patched
    if _patched or PROXY_HOST in ("", "pximg.example.com", ORIGIN_HOST):
        return
    from gallery_dl.job import DownloadJob

    if getattr(DownloadJob.handle_url, "_pximg_rewritten", False):
        _patched = True
        return

    orig_handle_url = DownloadJob.handle_url

    def handle_url(self, url, kwdict):
        new_url = _rewrite(url)
        if new_url != url:
            fb = kwdict.get("_fallback")
            if isinstance(fb, (list, tuple)):
                fb = list(fb)
            elif isinstance(fb, str):
                fb = [fb]
            elif fb is None:
                fb = []
            else:
                try:
                    fb = list(fb)
                except TypeError:
                    fb = []
            # fallback utama = URL asli (dipakai otomatis jika proxy gagal),
            # diikuti fallback lain yang juga di-rewrite
            seen = {new_url}
            new_fb = []
            for u in [url, *fb]:
                if u not in seen:
                    seen.add(u)
                    new_fb.append(u if u == url else _rewrite(u))
            kwdict["_fallback"] = new_fb
            url = new_url
        return orig_handle_url(self, url, kwdict)

    handle_url._pximg_rewritten = True
    DownloadJob.handle_url = handle_url
    _patched = True
