import os
import json
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import shlex

APP_TITLE = "Kuro Lite – Rename & Copy to Camera"
CAMERA_PATH = "/storage/emulated/0/DCIM/Camera"

ADB_FALLBACK = r"C:\Users\hanenashi\AppData\Local\Android\Sdk\platform-tools\adb.exe"

RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_SETTINGS_PATH = os.path.join(RESOURCE_DIR, "kuro_settings.json")
SETTINGS_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KuroCommander"
)
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

REQUIRED_ADB_DLLS = ["AdbWinApi.dll", "AdbWinUsbApi.dll"]


# ---------------- Settings ----------------

def load_settings():
    for path in (SETTINGS_PATH, SOURCE_SETTINGS_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def save_settings(data: dict):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


# ---------------- ADB helpers ----------------

def _try_run_adb(cmd: str) -> bool:
    try:
        result = subprocess.run(
            [cmd, "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_adb_dlls(adb_cmd: str) -> list[str]:
    if not adb_cmd or not os.path.isabs(adb_cmd):
        return []
    folder = os.path.dirname(adb_cmd)
    missing = []
    for dll in REQUIRED_ADB_DLLS:
        if not os.path.isfile(os.path.join(folder, dll)):
            missing.append(dll)
    return missing


def resolve_adb(settings: dict) -> str | None:
    user_adb = settings.get("adb_path", "")
    if isinstance(user_adb, str) and user_adb:
        if os.path.isfile(user_adb) and _try_run_adb(user_adb):
            return user_adb

    root_adb = os.path.join(RESOURCE_DIR, "adb.exe")
    if os.path.isfile(root_adb) and _try_run_adb(root_adb):
        return root_adb

    if _try_run_adb("adb"):
        return "adb"

    if os.path.isfile(ADB_FALLBACK) and _try_run_adb(ADB_FALLBACK):
        return ADB_FALLBACK

    return None


def adb_run(adb: str, args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    command = [adb] + args
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, -1, "", str(exc))


def adb_connected(adb: str) -> bool:
    r = adb_run(adb, ["devices"], timeout=10)
    if r.returncode != 0:
        return False
    return any("\tdevice" in line for line in r.stdout.splitlines())


def remote_file_exists(adb: str, path: str) -> bool | None:
    result = adb_run(adb, ["shell", f"test -e {shlex.quote(path)}"], timeout=10)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def media_scan_all(adb: str):
    """
    One-shot scan after all copies (faster than per-file scanning).
    Best-effort: Android versions differ in how well this works, but it's the
    least painful and usually sufficient.
    """
    adb_run(adb, [
        "shell", "content", "call",
        "--uri", "content://media",
        "--method", "scan_volume",
        "--arg", "external_primary"
    ])


# ---------------- UI app ----------------

class KuroLite(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("950x620")
        icon_path = os.path.join(RESOURCE_DIR, "kuro.ico")
        if os.path.isfile(icon_path):
            try:
                self.iconbitmap(icon_path)
            except tk.TclError:
                pass

        self.settings = load_settings()
        self.adb = resolve_adb(self.settings)
        self.adb_missing_dlls = check_adb_dlls(self.adb) if self.adb else []
        self._adb_is_connected = adb_connected(self.adb) if self.adb else False

        self.files: list[str] = []

        # worker plumbing
        self._uiq: "queue.Queue[tuple]" = queue.Queue()
        self._copy_thread: threading.Thread | None = None
        self._cancel_flag = threading.Event()
        self._busy = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._startup_warnings()
        self._update_status()

        self.after(80, self._drain_ui_queue)

    # ---------- UI ----------

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)

        self.btn_select = ttk.Button(top, text="Select files…", command=self.add_files)
        self.btn_select.pack(side="left")

        self.btn_clear = ttk.Button(top, text="Clear", command=self.clear_files)
        self.btn_clear.pack(side="left", padx=4)

        ttk.Label(top, text="Suffix:").pack(side="left", padx=(20, 4))
        self.suffix_var = tk.StringVar(value=self.settings.get("rename_suffix", "_ok"))
        self.ent_suffix = ttk.Entry(top, textvariable=self.suffix_var, width=14)
        self.ent_suffix.pack(side="left")

        self.btn_settings = ttk.Button(top, text="Settings", command=self.open_settings)
        self.btn_settings.pack(side="left", padx=(12, 0))

        self.btn_rename = ttk.Button(top, text="Rename", command=self.rename_files)
        self.btn_rename.pack(side="right")

        self.btn_copy = ttk.Button(top, text="Copy to Camera", command=self.copy_to_camera)
        self.btn_copy.pack(side="right", padx=6)

        self.btn_cancel = ttk.Button(top, text="Cancel copy", command=self.cancel_copy, state="disabled")
        self.btn_cancel.pack(side="right", padx=6)

        # -------- File list with scrollbars --------
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=8)

        self.listbox = tk.Listbox(mid, selectmode="extended", activestyle="none")
        self.listbox.grid(row=0, column=0, sticky="nsew")

        sb_y = ttk.Scrollbar(mid, orient="vertical", command=self.listbox.yview)
        sb_y.grid(row=0, column=1, sticky="ns")

        sb_x = ttk.Scrollbar(mid, orient="horizontal", command=self.listbox.xview)
        sb_x.grid(row=1, column=0, sticky="ew")

        self.listbox.config(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.listbox.bind("<Button-3>", self.popup_menu)

        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        # progress area
        pfrm = ttk.Frame(self)
        pfrm.pack(fill="x", padx=8, pady=(8, 2))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(pfrm, variable=self.progress_var, maximum=100.0)
        self.progress.pack(side="left", fill="x", expand=True)

        self.progress_label = ttk.Label(pfrm, text="Idle", width=30, anchor="w")
        self.progress_label.pack(side="left", padx=(8, 0))

        # -------- Log with scrollbar --------
        logfrm = ttk.Frame(self)
        logfrm.pack(fill="both", padx=8, pady=(6, 6))

        self.log = tk.Text(logfrm, height=9, bg="#111", fg="#0f0", insertbackground="#0f0", wrap="none")
        self.log.grid(row=0, column=0, sticky="nsew")

        log_sb_y = ttk.Scrollbar(logfrm, orient="vertical", command=self.log.yview)
        log_sb_y.grid(row=0, column=1, sticky="ns")

        log_sb_x = ttk.Scrollbar(logfrm, orient="horizontal", command=self.log.xview)
        log_sb_x.grid(row=1, column=0, sticky="ew")

        self.log.config(yscrollcommand=log_sb_y.set, xscrollcommand=log_sb_x.set, state="disabled")

        logfrm.rowconfigure(0, weight=1)
        logfrm.columnconfigure(0, weight=1)

        # status
        self.status = ttk.Label(self, anchor="w")
        self.status.pack(fill="x", padx=8, pady=(0, 6))

        # popup menu
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Rename", command=self.rename_files)
        self.menu.add_command(label="Copy to Camera", command=self.copy_to_camera)
        self.menu.add_separator()
        self.menu.add_command(label="Remove from list", command=self.remove_selected)
        self.menu.add_command(label="Clear list", command=self.clear_files)

    # ---------- UI safe helpers ----------

    def log_line(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _startup_warnings(self):
        if self.adb and self.adb_missing_dlls:
            msg = (
                "adb.exe found, but required DLL(s) are missing next to it:\n\n"
                + "\n".join(f"- {x}" for x in self.adb_missing_dlls)
                + "\n\nFix: copy these DLLs into the same folder as adb.exe."
            )
            messagebox.showwarning("ADB DLLs missing", msg)
            self.log_line("[WARN] ADB DLLs missing: " + ", ".join(self.adb_missing_dlls))

    def _adb_status_text(self) -> str:
        if not self.adb:
            return "ADB: not found"

        adb_label = "adb (PATH)" if not os.path.isabs(self.adb) else (os.path.basename(self.adb) + " (absolute)")

        if self.adb_missing_dlls:
            return f"ADB: DLL missing ({', '.join(self.adb_missing_dlls)}) | using: {adb_label}"

        if self._adb_is_connected:
            return f"ADB: device connected | using: {adb_label}"
        return f"ADB: no device | using: {adb_label}"

    def _update_status(self):
        self.status.config(text=f"{len(self.files)} files | {self._adb_status_text()}")

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_select.config(state=state)
        self.btn_clear.config(state=state)
        self.btn_settings.config(state=state)
        self.btn_rename.config(state=state)
        self.btn_copy.config(state=state)
        self.ent_suffix.config(state=state)
        self.btn_cancel.config(state=("normal" if busy else "disabled"))

        if not busy:
            self.progress_var.set(0.0)
            self.progress_label.config(text="Idle")

    def _persist_suffix(self):
        self.settings["rename_suffix"] = self.suffix_var.get()
        save_settings(self.settings)

    def _recheck_adb(self):
        self.adb = resolve_adb(self.settings)
        self.adb_missing_dlls = check_adb_dlls(self.adb) if self.adb else []
        self._adb_is_connected = adb_connected(self.adb) if self.adb else False
        self._update_status()

    def on_close(self):
        if self._busy:
            if not messagebox.askyesno("Copy in progress", "Cancel the copy and close Kuro Commander?"):
                return
            self._cancel_flag.set()
        self.destroy()

    # ---------- queue pump from worker ----------

    def _drain_ui_queue(self):
        try:
            while True:
                item = self._uiq.get_nowait()
                kind = item[0]

                if kind == "log":
                    self.log_line(item[1])

                elif kind == "progress":
                    self.progress_var.set(item[1])
                    self.progress_label.config(text=item[2])

                elif kind == "done":
                    ok, fail, cancelled = item[1], item[2], item[3]
                    if cancelled:
                        self.log_line(f"[DONE] copy cancelled: ok={ok} fail={fail}")
                    else:
                        self.log_line(f"[DONE] copy finished: ok={ok} fail={fail}")
                    self._set_busy(False)
                    self._update_status()

        except queue.Empty:
            pass

        self.after(80, self._drain_ui_queue)

    # ---------- actions ----------

    def add_files(self):
        paths = filedialog.askopenfilenames()
        added = 0
        for p in paths:
            if p and p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", p)
                added += 1
        if added:
            self.log_line(f"[OK] Added {added} file(s).")
        self._update_status()

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self._update_status()

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            self.files.pop(i)
            self.listbox.delete(i)
        self._update_status()

    def rename_files(self):
        if self._busy:
            return
        if not self.files:
            messagebox.showinfo("Rename", "No files selected.")
            return

        suffix = (self.suffix_var.get() or "").strip()
        if suffix == "":
            messagebox.showwarning("Rename", "Suffix is empty.")
            return

        preview = []
        already_suffixed = 0
        existing_targets = 0
        for p in self.files:
            base, ext = os.path.splitext(p)
            if base.endswith(suffix):
                already_suffixed += 1
                continue
            destination = base + suffix + ext
            if os.path.exists(destination):
                existing_targets += 1
                continue
            preview.append((p, destination))

        if not preview:
            messagebox.showinfo(
                "Rename",
                "Nothing to rename.\n\n"
                f"Already suffixed: {already_suffixed}\n"
                f"Destination exists: {existing_targets}",
            )
            return

        sample = "\n".join(
            f"{os.path.basename(a)} -> {os.path.basename(b)}"
            for a, b in preview[:12]
        )
        if len(preview) > 12:
            sample += "\n…and more."
        if already_suffixed or existing_targets:
            sample += (
                "\n\nWill skip:"
                f"\n- Already suffixed: {already_suffixed}"
                f"\n- Destination exists: {existing_targets}"
            )

        if not messagebox.askyesno("Confirm rename", sample):
            return

        renamed = 0
        skipped = already_suffixed + existing_targets
        failed = 0
        for src, dst in preview:
            try:
                if os.path.exists(dst):
                    self.log_line(f"[SKIP] exists: {dst}")
                    skipped += 1
                    continue
                os.rename(src, dst)
                renamed += 1
                self.log_line(f"[OK] {os.path.basename(src)} -> {os.path.basename(dst)}")
                self.files[self.files.index(src)] = dst
            except Exception as e:
                failed += 1
                self.log_line(f"[FAIL] {src}: {e}")

        self.listbox.delete(0, "end")
        for p in self.files:
            self.listbox.insert("end", p)

        self._persist_suffix()
        self._update_status()
        self.log_line(f"[DONE] rename: ok={renamed} skip={skipped} fail={failed}")

    def cancel_copy(self):
        if self._busy:
            self._cancel_flag.set()
            self.log_line("[*] Cancel requested (will stop after current file).")

    def copy_to_camera(self):
        if self._busy:
            return

        if not self.files:
            messagebox.showinfo("Copy to Camera", "No files selected.")
            return

        if not self.adb:
            messagebox.showerror("ADB", "ADB not found.\nPut adb.exe next to kuro.py or set it in Settings.")
            return

        if self.adb_missing_dlls:
            messagebox.showerror(
                "ADB",
                "ADB is present but missing required DLLs:\n\n"
                + "\n".join(f"- {x}" for x in self.adb_missing_dlls)
                + "\n\nCopy them next to adb.exe and restart."
            )
            return

        self._adb_is_connected = adb_connected(self.adb)
        if not self._adb_is_connected:
            self._update_status()
            messagebox.showerror("ADB", "No device connected.\nCheck USB debugging and run 'adb devices'.")
            return

        files = list(self.files)
        remote_conflicts = set()
        check_failed = False
        selected_names = {os.path.basename(path) for path in files}
        for name in selected_names:
            exists = remote_file_exists(self.adb, f"{CAMERA_PATH}/{name}")
            if exists is None:
                check_failed = True
                break
            if exists:
                remote_conflicts.add(name)

        if check_failed:
            messagebox.showerror(
                "Copy to Camera",
                "Could not check the Camera folder for existing files.\n"
                "No files were copied.",
            )
            return

        seen_names = set()
        duplicate_paths = set()
        for path in files:
            name = os.path.basename(path)
            if name in seen_names:
                duplicate_paths.add(path)
            seen_names.add(name)

        if remote_conflicts or duplicate_paths:
            conflict_names = sorted(remote_conflicts | {os.path.basename(p) for p in duplicate_paths})
            sample = "\n".join(conflict_names[:12])
            if len(conflict_names) > 12:
                sample += "\n…and more."
            overwrite = messagebox.askyesnocancel(
                "Copy conflicts",
                f"{len(conflict_names)} filename conflict(s) found:\n\n{sample}\n\n"
                "Yes: overwrite\nNo: skip conflicts\nCancel: stop",
            )
            if overwrite is None:
                return
            if not overwrite:
                filtered_files = []
                accepted_names = set()
                for path in files:
                    name = os.path.basename(path)
                    if name in remote_conflicts or name in accepted_names:
                        self.log_line(f"[SKIP] copy conflict: {name}")
                        continue
                    filtered_files.append(path)
                    accepted_names.add(name)
                files = filtered_files
                if not files:
                    messagebox.showinfo("Copy to Camera", "All selected files were skipped.")
                    return

        self._cancel_flag.clear()
        self._set_busy(True)
        self._uiq.put(("log", f"[*] Copy start: {len(files)} file(s) -> {CAMERA_PATH}"))
        self._uiq.put(("progress", 0.0, "Preparing…"))

        self._copy_thread = threading.Thread(target=self._copy_worker, args=(files,), daemon=True)
        self._copy_thread.start()

    def _copy_worker(self, files: list[str]):
        total = len(files)
        ok = 0
        fail = 0
        cancelled = False

        mkdir_result = adb_run(self.adb, ["shell", "mkdir", "-p", CAMERA_PATH], timeout=30)
        if mkdir_result.returncode != 0:
            self._uiq.put(("log", "[FAIL] Could not prepare the Camera folder: " + mkdir_result.stderr.strip()))
            self._uiq.put(("done", 0, total, False))
            return

        for idx, p in enumerate(files, 1):
            if self._cancel_flag.is_set():
                cancelled = True
                break

            name = os.path.basename(p)
            pct = (idx - 1) / max(total, 1) * 100.0
            self._uiq.put(("progress", pct, f"{idx}/{total} … {name}"))
            self._uiq.put(("log", f"[{idx}/{total}] push {name}"))

            r = adb_run(self.adb, ["push", p, f"{CAMERA_PATH}/{name}"])
            if r.returncode != 0:
                fail += 1
                self._uiq.put(("log", "[FAIL] adb push"))
                err = (r.stderr or "").strip()
                out = (r.stdout or "").strip()
                if err:
                    self._uiq.put(("log", "       " + err))
                elif out:
                    self._uiq.put(("log", "       " + out))
                continue

            ok += 1
            pct2 = idx / max(total, 1) * 100.0
            self._uiq.put(("progress", pct2, f"{idx}/{total} pushed"))

        # one-shot scan at end (unless cancelled or nothing copied)
        if not cancelled and ok > 0:
            self._uiq.put(("progress", min(99.0, (ok + fail) / max(total, 1) * 100.0), "Scanning media…"))
            self._uiq.put(("log", "[*] Media scan (one-shot) …"))
            media_scan_all(self.adb)
            self._uiq.put(("log", "[OK] Media scan requested."))

        self._uiq.put(("progress", 100.0 if not cancelled else (ok + fail) / max(total, 1) * 100.0,
                       "Cancelled" if cancelled else "Done"))
        self._uiq.put(("done", ok, fail, cancelled))

    # ---------- settings dialog ----------

    def open_settings(self):
        if self._busy:
            return

        dlg = tk.Toplevel(self)
        dlg.title("Settings")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="ADB binary (adb.exe):").grid(row=0, column=0, sticky="w")

        adb_var = tk.StringVar(value=self.settings.get("adb_path", ""))

        entry = ttk.Entry(frm, textvariable=adb_var, width=70)
        entry.grid(row=1, column=0, columnspan=3, sticky="we", pady=(4, 6))

        def browse():
            path = filedialog.askopenfilename(
                title="Select adb.exe",
                filetypes=[("adb.exe", "adb.exe"), ("Executable", "*.exe"), ("All files", "*.*")]
            )
            if path:
                adb_var.set(path)

        def use_bundled_adb():
            adb_var.set("")

        def test():
            candidate = adb_var.get().strip()
            test_adb = resolve_adb({}) if candidate == "" else candidate

            if not test_adb:
                messagebox.showerror("Test ADB", "ADB not found.")
                return

            if os.path.isabs(test_adb):
                missing = check_adb_dlls(test_adb)
                if missing:
                    messagebox.showerror(
                        "Test ADB",
                        "ADB DLL(s) missing next to selected adb.exe:\n\n"
                        + "\n".join(f"- {x}" for x in missing)
                    )
                    return

            if not _try_run_adb(test_adb):
                messagebox.showerror("Test ADB", f"Cannot run:\n{test_adb}")
                return

            r = adb_run(test_adb, ["devices"])
            body = r.stdout.strip() if r.stdout.strip() else "(no output)"
            messagebox.showinfo("adb devices", body)

        def save_and_close():
            p = adb_var.get().strip()
            if p == "":
                self.settings.pop("adb_path", None)
            else:
                self.settings["adb_path"] = p

            save_settings(self.settings)
            self._recheck_adb()
            dlg.destroy()

        ttk.Button(frm, text="Browse…", command=browse).grid(row=2, column=0, sticky="w")
        ttk.Button(frm, text="Use bundled/default ADB", command=use_bundled_adb).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Button(frm, text="Test", command=test).grid(row=2, column=2, sticky="e")

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(btns, text="Save", command=save_and_close).pack(side="right", padx=6)

        frm.columnconfigure(0, weight=1)

    # ---------- context menu ----------

    def popup_menu(self, e):
        if self.files and not self._busy:
            self.menu.tk_popup(e.x_root, e.y_root)


if __name__ == "__main__":
    KuroLite().mainloop()
