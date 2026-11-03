# -*- coding: utf-8 -*-
"""智回 · 电商自动回复工作台 —— 启动入口。

开发模式：
    python app.py            启动并自动打开浏览器
    python app.py --no-open  只启动服务
    python app.py --port 9000

单文件 exe（PyInstaller onefile + noconsole）：
    双击运行 → 弹出控制窗口 → 自动打开浏览器 → 关闭窗口即停止服务
"""
import os
import sys
import json
import socket
import threading
import time
import webbrowser
import urllib.request

FROZEN = bool(getattr(sys, "frozen", False))

if not FROZEN:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db          # noqa: E402
import server      # noqa: E402

APP_NAME = "智回"
APP_SUB = "电商自动回复工作台"
APP_VER = "1.0.0"

SHOUT = "http://127.0.0.1:{}"


def res_path(*parts):
    """打包后资源在 _MEIPASS 临时目录，开发时在脚本同级。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def free_port(start=8765, tries=60):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def probe(port):
    """检测该端口上是否已经是本程序在运行（用于重复双击时直接开浏览器）。"""
    try:
        with urllib.request.urlopen(SHOUT.format(port) + "/api/stats", timeout=0.6) as r:
            data = json.loads(r.read().decode("utf-8"))
        return "auto_replies" in data and "sessions_today" in data
    except Exception:
        return False


def open_later(url, delay=1.0):
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


# ---------------------------------------------------------------- 控制窗口

def _enable_dpi():
    """必须在创建 Tk 之前调用，否则 150% 缩放下文字会被位图拉伸变糊。"""
    if not sys.platform.startswith("win"):
        return 1.0
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, (dpi or 96) / 96.0)
    except Exception:
        return 1.0


def _msgbox(text, title="智回", error=False):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    except Exception:
        server.log(text)


def run_ui(port, url):
    try:
        import tkinter as tk
    except Exception:
        _msgbox("未找到 tkinter，已改为后台运行。\n请手动打开：%s" % url)
        _block_forever()
        return

    scale = _enable_dpi()
    px = lambda v: int(round(v * scale))

    C = {
        "bg": "#FFFFFF",
        "panel": "#F7F8FB",
        "line": "#ECEEF4",
        "text": "#111827",
        "sub": "#667085",
        "mute": "#98A2B3",
        "brand": "#4F46E5",
        "brand_dark": "#4338CA",
        "ok": "#12B76A",
    }
    FONT = "Microsoft YaHei UI"

    root = tk.Tk()
    root.title("%s · %s" % (APP_NAME, APP_SUB))
    root.configure(bg=C["bg"])
    root.resizable(False, False)
    try:
        root.tk.call("tk", "scaling", 96.0 * scale / 72.0)
    except Exception:
        pass

    ico = res_path("assets", "app.ico")
    if os.path.exists(ico):
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    W, H = px(478), px(352)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry("%dx%d+%d+%d" % (W, H, max(0, (sw - W) // 2), max(0, (sh - H) // 3)))

    body = tk.Frame(root, bg=C["bg"])
    body.pack(fill="both", expand=True)

    # ---- 品牌头
    head = tk.Frame(body, bg=C["bg"])
    head.pack(fill="x", padx=px(26), pady=(px(24), 0))

    badge = tk.Canvas(head, width=px(46), height=px(46), bg=C["bg"], highlightthickness=0)
    badge.pack(side="left")
    badge.create_oval(px(1), px(1), px(45), px(45), fill=C["brand"], outline="")
    badge.create_text(px(23), px(22), text="智", fill="#FFFFFF", font=(FONT, 15, "bold"))

    tbox = tk.Frame(head, bg=C["bg"])
    tbox.pack(side="left", padx=(px(13), 0))
    tk.Label(tbox, text="智回", bg=C["bg"], fg=C["text"],
             font=(FONT, 15, "bold")).pack(anchor="w")
    tk.Label(tbox, text="电商自动回复工作台 · v%s" % APP_VER, bg=C["bg"], fg=C["mute"],
             font=(FONT, 9)).pack(anchor="w", pady=(px(2), 0))

    tk.Frame(body, bg=C["line"], height=1).pack(fill="x", padx=px(26), pady=(px(18), 0))

    # ---- 运行状态卡
    card = tk.Frame(body, bg=C["panel"], highlightbackground=C["line"],
                    highlightthickness=1)
    card.pack(fill="x", padx=px(26), pady=(px(18), 0))

    row = tk.Frame(card, bg=C["panel"])
    row.pack(fill="x", padx=px(16), pady=(px(14), 0))
    dot = tk.Canvas(row, width=px(9), height=px(9), bg=C["panel"], highlightthickness=0)
    dot.pack(side="left", pady=(px(1), 0))
    dot.create_oval(0, 0, px(8), px(8), fill=C["ok"], outline="")
    tk.Label(row, text="服务运行中", bg=C["panel"], fg=C["text"],
             font=(FONT, 10, "bold")).pack(side="left", padx=(px(7), 0))

    addr = tk.Label(card, text=url, bg=C["panel"], fg=C["brand"],
                    font=("Consolas", 11), anchor="w", cursor="hand2")
    addr.pack(fill="x", padx=px(16), pady=(px(6), 0))
    addr.bind("<Button-1>", lambda e: webbrowser.open(url))

    stat = tk.Label(card, text="正在读取今日数据…", bg=C["panel"], fg=C["sub"],
                    font=(FONT, 9), anchor="w")
    stat.pack(fill="x", padx=px(16), pady=(px(7), px(14)))

    # ---- 按钮
    btns = tk.Frame(body, bg=C["bg"])
    btns.pack(fill="x", padx=px(26), pady=(px(18), 0))

    def flat(parent, text, bg, fg, hover, cmd, bold=True, pad=(22, 11)):
        b = tk.Label(parent, text=text, bg=bg, fg=fg, cursor="hand2",
                     font=(FONT, 10, "bold" if bold else "normal"),
                     padx=px(pad[0]), pady=px(pad[1]))
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=bg))
        b.bind("<Button-1>", lambda e: cmd())
        return b

    flat(btns, "打开工作台", C["brand"], "#FFFFFF", C["brand_dark"],
         lambda: webbrowser.open(url)).pack(side="left")

    copy_tip = tk.Label(body, text="", bg=C["bg"], fg=C["ok"], font=(FONT, 8))

    def copy_addr():
        try:
            root.clipboard_clear()
            root.clipboard_append(url)
            copy_tip.configure(text="地址已复制")
            root.after(1600, lambda: copy_tip.configure(text=""))
        except Exception:
            pass

    flat(btns, "复制地址", C["bg"], C["sub"], C["panel"], copy_addr,
         bold=False).pack(side="left", padx=(px(10), 0))

    def open_data():
        d = os.path.dirname(db.DB_PATH)
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)   # noqa: S606
        except Exception:
            _msgbox("数据目录：\n%s" % d)

    flat(btns, "数据目录", C["bg"], C["sub"], C["panel"], open_data,
         bold=False).pack(side="left", padx=(px(10), 0))

    # ---- 页脚
    foot = tk.Frame(body, bg=C["bg"])
    foot.pack(side="bottom", fill="x", padx=px(26), pady=(0, px(16)))
    copy_tip.pack(side="bottom", anchor="w", padx=px(26))
    tk.Frame(foot, bg=C["line"], height=1).pack(fill="x", pady=(0, px(12)))
    tk.Label(foot, text="关闭本窗口即停止服务，规则与日志已自动保存在 data 目录",
             bg=C["bg"], fg=C["mute"], font=(FONT, 8), anchor="w").pack(fill="x")

    # ---- 统计刷新
    alive = {"on": True}

    def refresh():
        if not alive["on"]:
            return

        def work():
            txt = None
            try:
                with urllib.request.urlopen(url + "/api/stats", timeout=2.0) as r:
                    d = json.loads(r.read().decode("utf-8"))
                txt = "今日接待 %d 位买家 · 自动回复 %d 条 · 待人工 %d 个会话" % (
                    d.get("sessions_today", 0), d.get("auto_replies", 0),
                    d.get("human_takeover", 0))
            except Exception:
                txt = "状态读取失败，正在重试…"
            try:
                root.after(0, lambda: stat.configure(text=txt) if alive["on"] else None)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()
        root.after(5000, refresh)

    root.after(300, refresh)

    def on_close():
        alive["on"] = False
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


def _block_forever():
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- 入口

def main():
    args = sys.argv[1:]
    no_open = "--no-open" in args
    no_ui = "--no-ui" in args
    port = None
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except Exception:
            port = None

    # 重复双击：已有实例在跑就直接把页面切到前面，不再起第二个进程
    if FROZEN and not port:
        for p in range(8765, 8771):
            if probe(p):
                webbrowser.open(SHOUT.format(p))
                return

    port = port or free_port()
    url = SHOUT.format(port)
    use_ui = FROZEN and not no_ui

    if not use_ui:
        if not no_open:
            open_later(url)
        try:
            server.serve("127.0.0.1", port)
        except OSError as exc:
            server.log("端口 %d 启动失败：%s" % (port, exc))
            _msgbox("端口 %d 被占用，请关闭占用程序后重试。\n\n%s" % (port, exc), error=True)
        return

    try:
        httpd = server.create_server("127.0.0.1", port)
    except OSError as exc:
        _msgbox("无法监听端口 %d：%s" % (port, exc), error=True)
        return

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if not no_open:
        open_later(url, 0.8)
    try:
        run_ui(port, url)
    finally:
        server.shutdown(httpd)


if __name__ == "__main__":
    try:
        db.init_db()
    except Exception as exc:
        _msgbox("数据库初始化失败：\n%s" % exc, error=True)
        raise SystemExit(1)
    main()
