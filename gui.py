#!/usr/bin/env python3
import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from tkinter import filedialog, messagebox

import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from run import (
    artwork_id,
    collect_inputs,
    find_gallerydl,
    fmt_dur,
    fmt_size,
)

BROWSER = "helium"
BROWSE_TITLE = "Pilih folder penyimpanan"


def list_presets():
    files = sorted(glob.glob(os.path.join(BASE_DIR, "gallery-dl*.conf")))
    names = [os.path.basename(f) for f in files]
    if "gallery-dl.conf" in names:
        names.remove("gallery-dl.conf")
        names.insert(0, "gallery-dl.conf")
    return names


def patched_config_gui(src, download_dir):
    with open(src, encoding="utf-8") as f:
        cfg = json.load(f)
    for pp in cfg.get("postprocessors", []):
        if isinstance(pp, dict) and pp.get("name") == "ugoira":
            pp["keep-files"] = True
    dl = cfg.setdefault("downloader", {})
    dl.setdefault("progress", 0)
    out = cfg.setdefault("output", {})
    out.setdefault("progress", True)
    out.setdefault("shorten", True)
    cfg["base-directory"] = download_dir
    cfg["directory"] = []
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", delete=False, encoding="utf-8", dir=BASE_DIR
    )
    json.dump(cfg, tmp, indent=4)
    tmp.close()
    return tmp.name


def snapshot_sizes_gui(aid, download_dir):
    zpath = os.path.join(download_dir, f"{aid}.zip")
    mpath = os.path.join(download_dir, f"{aid}.mp4")
    zs = os.path.getsize(zpath) if os.path.isfile(zpath) else None
    ms = os.path.getsize(mpath) if os.path.isfile(mpath) else None
    return zpath, zs, mpath, ms


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Pixiv Ugoira Downloader")
        self.geometry("720x620")
        self.minsize(640, 560)

        self.presets = list_presets()
        self.download_dir = os.path.join(BASE_DIR, "downloads")
        self.log_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.proc = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(self, text="ID / URL Pixiv (bulk: pisah spasi, koma, ; atau baris baru)",
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.input_box = ctk.CTkTextbox(self, height=90)
        self.input_box.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.input_box.insert("1.0", "")

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        mid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(mid, text="Preset").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.preset_var = ctk.StringVar(value=self.presets[0] if self.presets else "")
        self.preset_menu = ctk.CTkOptionMenu(mid, variable=self.preset_var, values=self.presets if self.presets else ["-"])
        self.preset_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        ctk.CTkLabel(mid, text="Folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.folder_entry = ctk.CTkEntry(mid)
        self.folder_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        self.folder_entry.insert(0, self.download_dir)
        ctk.CTkButton(mid, text="Browse", width=90, command=self.browse_folder).grid(row=1, column=2, pady=(8, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.btn_download = ctk.CTkButton(btns, text="Download", command=self.start_download)
        self.btn_download.pack(side="left", padx=(0, 8))
        self.btn_stop = ctk.CTkButton(btns, text="Stop", fg_color="gray", state="disabled", command=self.stop_download)
        self.btn_stop.pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Clear Log", fg_color="transparent", border_width=1, command=self.clear_log).pack(side="left")

        ctk.CTkLabel(self, text="Detail (kecepatan, ukuran ZIP / MP4 + %)",
                     anchor="w").grid(row=4 - 1, column=0, sticky="w", padx=12, pady=(0, 4))
        self.log_box = ctk.CTkTextbox(self, state="disabled")
        self.log_grid_row = 5
        self.log_box.grid(row=self.log_grid_row, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.grid_rowconfigure(self.log_grid_row, weight=1)

        self.after(100, self.poll_log)
        self.log("Siap. Masukkan ID lalu tekan Download.\n")

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg if msg.endswith("\n") else msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def poll_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line == "__DONE__":
                    self.btn_download.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                else:
                    self.log(line)
        except queue.Empty:
            pass
        self.after(100, self.poll_log)

    def browse_folder(self):
        d = filedialog.askdirectory(title=BROWSE_TITLE, initialdir=self.folder_entry.get() or BASE_DIR)
        if d:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, d)

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def start_download(self):
        if self.worker and self.worker.is_alive():
            return
        raw = self.input_box.get("1.0", "end").strip()
        urls = collect_inputs([raw] if raw else [], "<none>")
        if not urls:
            messagebox.showwarning("Input kosong", "Masukkan minimal satu ID atau URL Pixiv.")
            return
        preset = self.preset_var.get()
        cfg_src = preset if os.path.isfile(preset) else os.path.join(BASE_DIR, preset)
        if not os.path.isfile(cfg_src):
            messagebox.showerror("Config hilang", f"Config tidak ditemukan: {preset}")
            return
        if not shutil.which("ffmpeg"):
            messagebox.showerror("ffmpeg hilang", "ffmpeg tidak ditemukan. Install via: winget install Gyan.FFmpeg")
            return
        download_dir = self.folder_entry.get().strip() or os.path.join(BASE_DIR, "downloads")
        try:
            os.makedirs(download_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Folder gagal", str(e))
            return
        self.download_dir = download_dir
        self.stop_event.clear()
        self.btn_download.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.worker = threading.Thread(target=self.run_worker, args=(urls, cfg_src, download_dir), daemon=True)
        self.worker.start()

    def stop_download(self):
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.log_queue.put("Dibatalkan oleh pengguna.\n")

    def run_worker(self, urls, cfg_src, download_dir):
        q = self.log_queue
        cfg_tmp = patched_config_gui(cfg_src, download_dir)
        base = find_gallerydl()
        try:
            q.put(f"Download {len(urls)} karya | config={os.path.basename(cfg_src)}\n")
            q.put("-" * 64 + "\n")
            total_zip = total_mp4 = 0
            n_ok = 0
            t_all = time.time()
            for i, url in enumerate(urls, 1):
                if self.stop_event.is_set():
                    q.put("Dibatalkan, sisa antrean dilewati.\n")
                    break
                aid = artwork_id(url)
                q.put(f"[{i}/{len(urls)}] {aid} ...\n")
                cmd = base + ["--config", cfg_tmp, "--cookies-from-browser", BROWSER, url]
                t0 = time.time()
                try:
                    self.proc = subprocess.Popen(
                        cmd, cwd=BASE_DIR, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, bufsize=1,
                    )
                except OSError as e:
                    q.put(f"  GAGAL start: {e}\n")
                    continue
                for line in self.proc.stdout:
                    q.put(f"  | {line.rstrip()}\n")
                rc = self.proc.wait()
                self.proc = None
                dt = time.time() - t0
                zpath, zs, mpath, ms = snapshot_sizes_gui(aid, download_dir)
                if self.stop_event.is_set():
                    q.put(f"  STOP | {fmt_dur(dt)}\n")
                    break
                if rc != 0:
                    q.put(f"  GAGAL (exit {rc}) | {fmt_dur(dt)}\n")
                    continue
                n_ok += 1
                zs = zs or 0
                ms = ms or 0
                total_zip += zs
                total_mp4 += ms
                ratio = (ms / zs * 100) if zs else 0
                speed = (zs / dt) if dt > 0 and zs else 0
                q.put(f"  ZIP mentah : {fmt_size(zs)}\n")
                q.put(f"  MP4 jadi   : {fmt_size(ms)} ({ratio:.0f}% dari ZIP)\n")
                q.put(f"  Waktu      : {fmt_dur(dt)} | ~{fmt_size(speed)}/s (rata-rata item ini)\n")
                if zs and os.path.isfile(zpath) and os.path.isfile(mpath):
                    try:
                        os.remove(zpath)
                        q.put("  (ZIP mentah dihapus kembali)\n")
                    except OSError:
                        pass
            q.put("-" * 64 + "\n")
            q.put(f"Selesai {n_ok}/{len(urls)} dalam {fmt_dur(time.time() - t_all)}\n")
            q.put(f"Total ZIP mentah: {fmt_size(total_zip)} | Total MP4: {fmt_size(total_mp4)}\n")
        finally:
            try:
                os.remove(cfg_tmp)
            except OSError:
                pass
            q.put("__DONE__")


if __name__ == "__main__":
    if not list_presets():
        messagebox.showerror("Preset kosong", "Tidak ada file gallery-dl*.conf di folder ini.")
        sys.exit(1)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.exit("tkinter tidak tersedia.")
    app = App()
    app.mainloop()
