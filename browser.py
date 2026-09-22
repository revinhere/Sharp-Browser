import os
import sys
import json
import time
import base64
from datetime import datetime

# Force Qt WebEngine Chromium flags for 240Hz capped refresh rate, smooth scrolling, hardware acceleration, and flicker-free video rendering
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--enable-gpu-rasterization "
    "--ignore-gpu-blocklist "
    "--max-fps=240 "
    "--enable-smooth-scrolling "
    "--enable-accelerated-video-decode "
    "--autoplay-policy=no-user-gesture-required "
    "--enable-features=UseSkiaRenderer,CanvasOopRasterization,PlatformHEVCDecoderSupport "
)

from PyQt6.QtCore import (
    QUrl, QSettings, Qt, QPoint, QTimer, QSize, QCoreApplication,
    QFileInfo
)
from PyQt6.QtGui import (
    QGuiApplication, QIcon, QKeySequence, QShortcut, QCloseEvent,
    QPixmap, QPainter, QColor
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QLineEdit, QTabBar,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QWidget, QToolButton,
    QPushButton, QLabel, QMessageBox, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu, QProgressBar, QInputDialog,
    QSizePolicy, QFrame, QCheckBox, QComboBox, QRadioButton, QListWidget,
    QListWidgetItem, QFileIconProvider
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineSettings, QWebEngineDownloadRequest,
    QWebEnginePage
)

APP_VERSION = "Build 1902.2"


def crash_proof_excepthook(exctype, value, tb):
    """Prevents PyQt6 from triggering native fatal crashes on unhandled Python exceptions."""
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = crash_proof_excepthook

DATA_DIR = os.path.join(os.path.expanduser("~"), ".sharpbrowser_data")
os.makedirs(DATA_DIR, exist_ok=True)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
DOWNLOADS_FILE = os.path.join(DATA_DIR, "downloads.json")
BOOKMARKS_FILE = os.path.join(DATA_DIR, "bookmarks.json")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")
STORAGE_DIR = os.path.join(DATA_DIR, "web_profile")

# Global state collections
download_data = []
history_data = []
bookmarks_data = []
active_download_requests = {}
active_download_info = {}
windows = []


def load_json(filepath):
    """Safely loads JSON data from a given path."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_json(filepath, data):
    """Safely writes JSON data to a target path."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")


# Load stored state at module load
history_data = load_json(HISTORY_FILE)
download_data = load_json(DOWNLOADS_FILE)
bookmarks_data = load_json(BOOKMARKS_FILE)


def get_os_accent_color():
    """Returns the primary system accent hex code."""
    return "#2563eb"


def get_app_icon_path():
    """Finds the app icon next to the script or inside a PyInstaller bundle."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    for fname in ["icon.ico", "icon.png", "favicon.ico"]:
        icon_path = os.path.join(base_dir, fname)
        if os.path.exists(icon_path):
            return icon_path

    return ""


def get_icon_base64():
    """Converts local icon to Base64 data URI for inline HTML usage."""
    icon_path = get_app_icon_path()
    if icon_path and os.path.exists(icon_path):
        try:
            with open(icon_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                ext = os.path.splitext(icon_path)[1].lower().replace(".", "")
                mime = "image/png" if ext == "png" else "image/x-icon"
                return f"data:{mime};base64,{encoded}"
        except Exception:
            return ""
    return ""


def get_relative_time_str(time_str):
    """Formats raw timestamp strings into user-friendly relative descriptions."""
    if not time_str:
        return "Recently"
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = now - dt
        if diff.days > 0:
            return f"{diff.days}d ago"
        seconds = diff.seconds
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        else:
            return f"{seconds // 3600}h ago"
    except Exception:
        return time_str


def format_bytes(bytes_num):
    """Formats byte count to human-readable string (KB, MB, GB)."""
    if not bytes_num or bytes_num <= 0:
        return "0 B"
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    double_bytes = float(bytes_num)
    while double_bytes >= 1024 and i < len(sizes) - 1:
        double_bytes /= 1024.0
        i += 1
    return f"{double_bytes:.1f} {sizes[i]}"


def get_os_formatted_datetime():
    """Returns standard current date and time string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_domain(url_str):
    """Extracts hostname domain string from URL."""
    try:
        if not url_str.startswith('http://') and not url_str.startswith('https://'):
            url_str = 'https://' + url_str
        u = QUrl(url_str)
        return u.host() or url_str
    except Exception:
        return url_str


def get_search_url(query, engine="Google"):
    """Constructs search engine URL for input search terms."""
    encoded = QUrl.toPercentEncoding(query).data().decode('utf-8')
    engines = {
        "Google": f"https://www.google.com/search?q={encoded}",
        "Bing": f"https://www.bing.com/search?q={encoded}",
        "DuckDuckGo": f"https://duckduckgo.com/?q={encoded}",
        "Brave": f"https://search.brave.com/search?q={encoded}",
        "Yahoo": f"https://search.yahoo.com/search?p={encoded}"
    }
    return engines.get(engine, f"https://www.google.com/search?q={encoded}")


SMOOTH_SCROLL_JS = """
(function() {
    if (!document.getElementById('sharp-smooth-scroll')) {
        const style = document.createElement('style');
        style.id = 'sharp-smooth-scroll';
        style.textContent = 'html { scroll-behavior: smooth !important; }';
        (document.head || document.documentElement).appendChild(style);
    }
})();
"""

HOME_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sharp Browser</title>
    <style>
        :root {
            --bg-color: __BG__;
            --text-color: __TEXT__;
            --card-bg: __CARD_BG__;
            --card-hover: __CARD_HOVER__;
            --accent-color: __ACCENT__;
            --input-bg: __INPUT_BG__;
            --input-border: __INPUT_BORDER__;
            --shadow-color: __SHADOW__;
            --modal-bg: __MODAL_BG__;
        }
        html { scroll-behavior: smooth; }
        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            box-sizing: border-box;
            transition: background-color 0.15s ease, color 0.15s ease;
        }
        .container {
            width: 100%;
            max-width: 720px;
            padding: 20px;
            text-align: center;
            box-sizing: border-box;
        }
        .logo-header {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 18px;
            margin-bottom: 28px;
        }
        .app-logo-img {
            width: 72px;
            height: 72px;
            object-fit: contain;
        }
        .logo-title {
            font-family: "Arial Rounded MT Bold", "Arial Rounded MT", -apple-system, sans-serif;
            font-size: 3.2rem;
            font-weight: bold;
            color: var(--text-color);
            user-select: none;
            letter-spacing: -0.5px;
        }
        .search-box-wrapper {
            position: relative;
            width: 100%;
            margin-bottom: 36px;
        }
        .search-input {
            width: 100%;
            height: 54px;
            padding: 0 60px 0 20px;
            font-size: 1.05rem;
            border-radius: 28px;
            border: 2px solid var(--input-border);
            background-color: var(--input-bg);
            color: var(--text-color);
            box-shadow: 0 4px 16px var(--shadow-color);
            outline: none;
            box-sizing: border-box;
            transition: all 0.2s ease;
        }
        .search-input:focus {
            border-color: var(--accent-color);
            box-shadow: 0 6px 20px var(--shadow-color), 0 0 0 3px rgba(37, 99, 235, 0.15);
        }
        .search-arrow-btn {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            width: 38px;
            height: 38px;
            border-radius: 50%;
            background: transparent;
            border: none;
            color: var(--accent-color);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background-color 0.2s ease, transform 0.2s ease;
        }
        .search-arrow-btn:hover {
            background-color: var(--card-hover);
            transform: translateY(-50%) scale(1.08);
        }
        .shortcuts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(105px, 1fr));
            gap: 16px;
            margin-top: 10px;
        }
        .shortcut-card {
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 16px 10px;
            border-radius: 14px;
            background-color: var(--card-bg);
            color: var(--text-color);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: transform 0.2s ease, background-color 0.2s ease;
            box-shadow: 0 2px 8px var(--shadow-color);
            user-select: none;
        }
        .shortcut-card:hover {
            transform: translateY(-3px);
            background-color: var(--card-hover);
        }
        .shortcut-icon-img {
            width: 32px;
            height: 32px;
            margin-bottom: 8px;
            border-radius: 8px;
            object-fit: contain;
        }
        .add-card-icon {
            font-size: 1.6rem;
            line-height: 32px;
            margin-bottom: 8px;
            color: var(--accent-color);
            font-weight: bold;
        }
        .context-menu {
            position: absolute;
            display: none;
            background-color: var(--modal-bg);
            border: 1px solid var(--input-border);
            border-radius: 8px;
            box-shadow: 0 4px 16px var(--shadow-color);
            z-index: 100;
            overflow: hidden;
        }
        .context-menu-item {
            padding: 10px 16px;
            font-size: 0.9rem;
            text-align: left;
            cursor: pointer;
            color: var(--text-color);
        }
        .context-menu-item:hover {
            background-color: var(--card-hover);
        }
        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal {
            background-color: var(--modal-bg);
            padding: 24px;
            border-radius: 16px;
            width: 90%;
            max-width: 400px;
            box-shadow: 0 10px 30px var(--shadow-color);
            text-align: left;
        }
        .modal h3 { margin-top: 0; margin-bottom: 16px; }
        .modal input {
            width: 100%;
            padding: 10px 14px;
            margin-bottom: 12px;
            border-radius: 8px;
            border: 1px solid var(--input-border);
            background-color: var(--input-bg);
            color: var(--text-color);
            box-sizing: border-box;
            outline: none;
        }
        .modal-buttons {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 8px;
        }
        .modal-btn {
            padding: 8px 16px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-weight: 600;
        }
        .modal-btn-primary { background-color: var(--accent-color); color: white; }
        .modal-btn-cancel { background-color: var(--card-bg); color: var(--text-color); }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-header">
            __LOGO_HTML__
            <div class="logo-title">SharpBrowser</div>
        </div>
        <div class="search-box-wrapper">
            <input type="text" id="search-input" class="search-input" placeholder="Type keywords or URL then press Enter" autofocus />
            <button id="search-btn" class="search-arrow-btn" title="Search or Navigate">
                <svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                    <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
            </button>
        </div>
        <div class="shortcuts-grid" id="shortcuts-grid"></div>
    </div>

    <div id="context-menu" class="context-menu">
        <div class="context-menu-item" id="ctx-rename">Rename</div>
        <div class="context-menu-item" id="ctx-remove" style="color: #ef4444;">Remove</div>
    </div>

    <div id="modal-overlay" class="modal-overlay">
        <div class="modal">
            <h3 id="modal-title">Add Shortcut</h3>
            <input type="text" id="shortcut-name" placeholder="Title (e.g. Google)" />
            <input type="text" id="shortcut-url" placeholder="URL (e.g. https://google.com)" />
            <div class="modal-buttons">
                <button class="modal-btn modal-btn-cancel" id="btn-cancel">Cancel</button>
                <button class="modal-btn modal-btn-primary" id="btn-save">Save</button>
            </div>
        </div>
    </div>

    <script>
        const defaultShortcuts = [
            { title: 'Google', url: 'https://www.google.com' },
            { title: 'YouTube', url: 'https://www.youtube.com' },
            { title: 'GitHub', url: 'https://github.com' },
            { title: 'Wikipedia', url: 'https://www.wikipedia.org' },
            { title: 'Reddit', url: 'https://www.reddit.com' }
        ];

        function getShortcuts() {
            try {
                const stored = localStorage.getItem('sharp_shortcuts');
                return stored ? JSON.parse(stored) : defaultShortcuts;
            } catch (e) {
                return defaultShortcuts;
            }
        }

        function saveShortcuts(list) {
            localStorage.setItem('sharp_shortcuts', JSON.stringify(list));
            renderShortcuts();
        }

        function getDomain(urlStr) {
            try {
                if (!urlStr.startsWith('http://') && !urlStr.startsWith('https://')) {
                    urlStr = 'https://' + urlStr;
                }
                const u = new URL(urlStr);
                return u.hostname;
            } catch (e) {
                return urlStr;
            }
        }

        let targetIndex = -1;

        function renderShortcuts() {
            const grid = document.getElementById('shortcuts-grid');
            grid.innerHTML = '';
            const shortcuts = getShortcuts();

            shortcuts.forEach((sc, idx) => {
                const card = document.createElement('a');
                card.className = 'shortcut-card';
                card.href = sc.url;

                const domain = getDomain(sc.url);
                const faviconUrl = 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=64';

                card.innerHTML = `
                    <img class="shortcut-icon-img" src="${faviconUrl}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🌐</text></svg>'" />
                    <div>${sc.title}</div>
                `;

                card.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    targetIndex = idx;
                    showContextMenu(e.clientX, e.clientY);
                });

                grid.appendChild(card);
            });

            const addCard = document.createElement('div');
            addCard.className = 'shortcut-card';
            addCard.innerHTML = `
                <div class="add-card-icon">+</div>
                <div>Add site</div>
            `;
            addCard.addEventListener('click', () => {
                targetIndex = -1;
                openModal('Add Shortcut', '', '');
            });
            grid.appendChild(addCard);
        }

        const ctxMenu = document.getElementById('context-menu');
        function showContextMenu(x, y) {
            ctxMenu.style.left = x + 'px';
            ctxMenu.style.top = y + 'px';
            ctxMenu.style.display = 'block';
        }

        function hideContextMenu() {
            ctxMenu.style.display = 'none';
        }

        document.addEventListener('click', hideContextMenu);

        document.getElementById('ctx-rename').addEventListener('click', () => {
            if (targetIndex >= 0) {
                const shortcuts = getShortcuts();
                const item = shortcuts[targetIndex];
                openModal('Edit Shortcut', item.title, item.url);
            }
        });

        document.getElementById('ctx-remove').addEventListener('click', () => {
            if (targetIndex >= 0) {
                const shortcuts = getShortcuts();
                shortcuts.splice(targetIndex, 1);
                saveShortcuts(shortcuts);
            }
        });

        const overlay = document.getElementById('modal-overlay');
        const inputName = document.getElementById('shortcut-name');
        const inputUrl = document.getElementById('shortcut-url');

        function openModal(title, name, url) {
            document.getElementById('modal-title').innerText = title;
            inputName.value = name;
            inputUrl.value = url;
            overlay.style.display = 'flex';
            inputName.focus();
        }

        function closeModal() {
            overlay.style.display = 'none';
        }

        document.getElementById('btn-cancel').addEventListener('click', closeModal);
        document.getElementById('btn-save').addEventListener('click', () => {
            const name = inputName.value.trim();
            let url = inputUrl.value.trim();
            if (!name || !url) return;

            if (!url.startsWith('http://') && !url.startsWith('https://') && !url.startsWith('file://')) {
                url = 'https://' + url;
            }

            const shortcuts = getShortcuts();
            if (targetIndex >= 0) {
                shortcuts[targetIndex] = { title: name, url: url };
            } else {
                shortcuts.push({ title: name, url: url });
            }
            saveShortcuts(shortcuts);
            closeModal();
        });

        function doSearch() {
            const input = document.getElementById('search-input');
            const val = input.value.trim();
            if (!val) return;

            if (val.startsWith('http://') || val.startsWith('https://') || val.startsWith('sharp://') || val.startsWith('file://')) {
                window.location.href = val;
            } else if (val.includes('.') || val.includes('/')) {
                window.location.href = 'https://' + val;
            } else {
                window.location.href = 'https://www.google.com/search?q=' + encodeURIComponent(val);
            }
        }

        document.getElementById('search-btn').addEventListener('click', doSearch);
        document.getElementById('search-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') doSearch();
        });

        renderShortcuts();
    </script>
</body>
</html>
"""


def get_home_html(is_dark=False):
    """Generates sharp://home HTML layout dynamically."""
    logo_base64 = get_icon_base64()
    if logo_base64:
        logo_html = f'<img src="{logo_base64}" class="app-logo-img" alt="Logo" />'
    else:
        logo_html = ''

    replacements = {
        "__BG__": "#121214" if is_dark else "#ffffff",
        "__TEXT__": "#f3f4f6" if is_dark else "#111827",
        "__CARD_BG__": "#1f1f23" if is_dark else "#f3f4f6",
        "__CARD_HOVER__": "#2d2d32" if is_dark else "#e5e7eb",
        "__ACCENT__": "#3b82f6" if is_dark else "#2563eb",
        "__INPUT_BG__": "#18181b" if is_dark else "#ffffff",
        "__INPUT_BORDER__": "#3f3f46" if is_dark else "#d1d5db",
        "__SHADOW__": "rgba(0, 0, 0, 0.4)" if is_dark else "rgba(0, 0, 0, 0.08)",
        "__MODAL_BG__": "#1f1f23" if is_dark else "#ffffff",
        "__LOGO_HTML__": logo_html,
    }
    html = HOME_HTML_TEMPLATE
    for key, val in replacements.items():
        html = html.replace(key, val)
    return html


class SwitchToggle(QCheckBox):
    """Pill-shaped toggle switch styled with OS accent color and responsive hit test."""

    def __init__(self, parent=None, is_dark=False):
        super().__init__(parent)
        self.is_dark = is_dark
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 24)

    def mouseReleaseEvent(self, event):
        """Ensures single click anywhere in the switch bounds toggles state reliably."""
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.setChecked(not self.isChecked())
            self.clicked.emit(self.isChecked())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent_color = QColor(get_os_accent_color())
        bg_off = QColor("#3f3f46" if self.is_dark else "#cbd5e1")

        painter.setBrush(accent_color if self.isChecked() else bg_off)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 46, 24, 12, 12)

        handle_x = 24 if self.isChecked() else 2
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(handle_x, 2, 20, 20)


class DownloadsPopupWindow(QFrame):
    """Recent download history dropdown panel."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.main_window = main_window
        self.setFixedSize(360, 320)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title = QLabel("Recent download history")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("border: none; font-size: 14px; font-weight: bold; background: transparent;")
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)

        self.items_widget = QWidget()
        self.items_layout = QVBoxLayout(self.items_widget)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(8)

        layout.addWidget(self.items_widget, stretch=1)

        footer_layout = QHBoxLayout()
        full_hist_btn = QPushButton("Full download history  ↗")
        full_hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        full_hist_btn.setStyleSheet(
            "text-align: left; border: none; font-weight: 600; font-size: 14px; background: transparent;")
        full_hist_btn.clicked.connect(self.open_full_history)
        footer_layout.addWidget(full_hist_btn)
        footer_layout.addStretch()
        layout.addLayout(footer_layout)

        self.apply_theme()
        self.refresh_items()

    def apply_theme(self):
        is_dark = self.main_window.dark_mode
        bg = "#1f1f23" if is_dark else "#ffffff"
        text = "#f3f4f6" if is_dark else "#111827"
        border = "#3f3f46" if is_dark else "#d1d5db"
        self.setStyleSheet(f"""
            DownloadsPopupWindow {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QLabel {{ color: {text}; }}
            QPushButton, QToolButton {{ color: {text}; }}
        """)

    def refresh_items(self):
        while self.items_layout.count():
            child = self.items_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        recent = list(reversed(download_data))[:3]
        if not recent:
            empty_lbl = QLabel("No recent downloads")
            empty_lbl.setStyleSheet("color: #a1a1aa; font-size: 13px;")
            self.items_layout.addWidget(empty_lbl)
            return

        icon_provider = QFileIconProvider()

        for item in recent:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(12)

            filePath = item.get('path', '')
            icon_lbl = QLabel()
            if filePath and os.path.exists(filePath):
                fileIcon = icon_provider.icon(QFileInfo(filePath))
                icon_lbl.setPixmap(fileIcon.pixmap(28, 28))
            else:
                default_icon = icon_provider.icon(QFileIconProvider.IconType.File)
                icon_lbl.setPixmap(default_icon.pixmap(28, 28))
            row_layout.addWidget(icon_lbl)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            name_lbl = QLabel(item.get('name', 'Unknown'))
            name_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")

            status_text = get_download_status(item)
            time_str = get_relative_time_str(item.get('time', ''))

            if "100%" in status_text or status_text == "Completed":
                file_size = format_bytes(os.path.getsize(filePath)) if filePath and os.path.exists(filePath) else ""
                sub_text = f"{file_size} • {time_str}" if file_size else time_str
            else:
                sub_text = f"{status_text} • {time_str}"

            sub_lbl = QLabel(sub_text)
            sub_lbl.setStyleSheet("font-size: 11px; color: #a1a1aa;")

            info_layout.addWidget(name_lbl)
            info_layout.addWidget(sub_lbl)
            row_layout.addLayout(info_layout, stretch=1)

            self.items_layout.addWidget(row_widget)

    def open_full_history(self):
        self.close()
        self.main_window.open_downloads_tab()


def global_download_handler(download: QWebEngineDownloadRequest):
    """Handles file download requests safely with normalized path formatting."""
    try:
        settings = QSettings("SharpBrowser", "BrowserSettings")
        ask_save = settings.value("ask_download_location", True, type=bool)
        default_dir = settings.value("download_dir", os.path.expanduser("~/Downloads")).replace("\\", "/")

        default_filename = download.downloadFileName()
        default_path = os.path.join(default_dir, default_filename).replace("\\", "/")

        if ask_save:
            path, _ = QFileDialog.getSaveFileName(None, "Save File As", default_path)
            if not path:
                download.cancel()
                return
            path = path.replace("\\", "/")
        else:
            path = default_path
            os.makedirs(os.path.dirname(path), exist_ok=True)

        folder, name = os.path.split(path)
        folder = folder.replace("\\", "/")
        download.setDownloadDirectory(folder)
        download.setDownloadFileName(name)

        dl_id = str(id(download))
        active_download_requests[dl_id] = download
        now_str = get_os_formatted_datetime()

        entry = {
            'id': dl_id,
            'time': now_str,
            'name': name,
            'status': 'Downloading',
            'path': path,
            'folder': folder
        }
        download_data.append(entry)
        save_json(DOWNLOADS_FILE, download_data)

        start_time = time.time()

        show_popup = settings.value("show_download_popup", True, type=bool)
        if show_popup:
            for win in windows:
                win.show_downloads_popup()

        def on_received_bytes_changed():
            nonlocal start_time
            curr_time = time.time()
            elapsed = curr_time - start_time
            received = download.receivedBytes()
            total = download.totalBytes()

            speed_bps = (received / elapsed) if elapsed > 0 else 0
            if speed_bps >= 1024 * 1024:
                speed_str = f"{speed_bps / (1024 * 1024):.1f} MB/s"
            elif speed_bps >= 1024:
                speed_str = f"{speed_bps / 1024:.0f} KB/s"
            else:
                speed_str = f"{speed_bps:.0f} B/s"

            active_download_info[dl_id] = {
                'state': download.state(),
                'received_bytes': received,
                'total_bytes': total,
                'speed_bps': speed_bps,
                'speed_str': speed_str
            }

        def on_state_changed(state):
            state_name = getattr(state, 'name', str(state))
            if state_name == 'DownloadCompleted' or state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                entry['status'] = 'Completed'
                if show_popup:
                    for win in windows:
                        win.show_downloads_popup()
            elif state_name in ('DownloadCancelled', 'DownloadInterrupted') or state in (
                    QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
                    QWebEngineDownloadRequest.DownloadState.DownloadInterrupted):
                entry['status'] = 'Canceled'

            active_download_info[dl_id] = {
                'state': state,
                'received_bytes': download.receivedBytes(),
                'total_bytes': download.totalBytes(),
                'speed_bps': 0,
                'speed_str': '0 KB/s'
            }
            save_json(DOWNLOADS_FILE, download_data)

        download.receivedBytesChanged.connect(on_received_bytes_changed)
        download.stateChanged.connect(on_state_changed)

        download.accept()
    except Exception as e:
        print(f"Download handler exception: {e}")


def get_download_status(item):
    """Determines detailed status string and progress metrics for a download item."""
    path = item.get('path', '').replace("\\", "/")
    status = item.get('status', 'Completed')
    dl_id = item.get('id')

    if dl_id in active_download_info:
        info = active_download_info[dl_id]
        state = info.get('state')
        state_name = getattr(state, 'name', str(state))

        if state_name == 'DownloadInProgress' or state == QWebEngineDownloadRequest.DownloadState.DownloadInProgress:
            total = info.get('total_bytes', 0)
            received = info.get('received_bytes', 0)
            speed_str = info.get('speed_str', '0 KB/s')
            speed_bps = info.get('speed_bps', 0)

            pct = int((received / total) * 100) if total > 0 else 0
            rec_str = format_bytes(received)
            tot_str = format_bytes(total) if total > 0 else "Unknown"

            if total > 0 and speed_bps > 0:
                rem_bytes = max(0, total - received)
                rem_sec = int(rem_bytes / speed_bps)
                if rem_sec >= 60:
                    eta_str = f"{rem_sec // 60}m {rem_sec % 60}s left"
                else:
                    eta_str = f"{rem_sec} sec left"
            else:
                eta_str = "-- sec left"

            return f"{pct}% — {speed_str}: {rec_str}/{tot_str} — {eta_str}"
        elif state_name == 'DownloadCompleted' or state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            status = "Completed"
        elif state_name in ('DownloadCancelled', 'DownloadInterrupted') or state in (
                QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
                QWebEngineDownloadRequest.DownloadState.DownloadInterrupted):
            status = "Canceled"

    if status == "Canceled":
        return "Canceled"

    if status == "Completed" and path and not os.path.exists(path):
        return "Deleted"

    return status


class CustomWebPage(QWebEnginePage):
    """Custom Web Page handling popups, fullscreen state, and browser dark/light mode synchronization."""

    def __init__(self, profile, parent=None, main_window=None, is_dark=False):
        super().__init__(profile, parent)
        self.main_window = main_window
        self.fullScreenRequested.connect(self.handle_fullscreen)
        self.renderProcessTerminated.connect(self.handle_render_terminated)
        self.sync_color_scheme(is_dark)

    def sync_color_scheme(self, is_dark):
        """Directly informs web rendering engine of explicit dark/light mode preference before loading."""
        if hasattr(self, 'setColorScheme') and hasattr(QWebEnginePage, 'ColorScheme'):
            try:
                self.setColorScheme(QWebEnginePage.ColorScheme.Dark if is_dark else QWebEnginePage.ColorScheme.Light)
            except Exception:
                pass

    def handle_render_terminated(self, status, exit_code):
        try:
            QTimer.singleShot(100, lambda: self.triggerAction(QWebEnginePage.WebAction.Reload))
        except Exception:
            pass

    def createWindow(self, _type):
        try:
            if self.main_window:
                if _type in (QWebEnginePage.WebWindowType.WebBrowserWindow, QWebEnginePage.WebWindowType.WebDialog):
                    new_win = self.main_window.open_new_window_with_url()
                    return new_win.current_browser().page()
                else:
                    new_browser = self.main_window.add_new_tab()
                    return new_browser.page()
        except Exception as e:
            print(f"Error creating window: {e}")
        return super().createWindow(_type)

    def handle_fullscreen(self, request):
        request.accept()
        if self.main_window:
            if request.toggleOn():
                self.main_window.enter_fullscreen()
            else:
                self.main_window.exit_fullscreen()


class CustomWebView(QWebEngineView):
    """Custom Web View with sharp://home handling, smooth scrolling injection, and context menu."""

    def __init__(self, main_window, is_dark=False, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.is_dark = is_dark
        self.setPage(CustomWebPage(persistent_profile, self, main_window, is_dark))
        self.loadFinished.connect(self.on_load_finished)

    def on_load_finished(self, ok):
        if ok:
            self.page().runJavaScript(SMOOTH_SCROLL_JS)

    def setUrl(self, url: QUrl):
        url_str = url.toString()
        if url_str == "sharp://home":
            self.setHtml(get_home_html(self.main_window.dark_mode), QUrl("sharp://home"))
        else:
            super().setUrl(url)

    def contextMenuEvent(self, event):
        try:
            menu = self.createStandardContextMenu()
            if menu is None:
                menu = QMenu(self)

            data = self.page().contextMenuData()
            if data and data.isValid():
                if data.linkUrl() and data.linkUrl().isValid():
                    url = data.linkUrl()
                    menu.addSeparator()

                    open_tab = menu.addAction("Open link in new tab")
                    open_tab.triggered.connect(lambda checked=False, u=url: self.main_window.add_new_tab(u))

                    open_win = menu.addAction("Open link in new window")
                    open_win.triggered.connect(
                        lambda checked=False, u=url: self.main_window.open_new_window_with_url(u))

                    copy_link = menu.addAction("Copy link address")
                    copy_link.triggered.connect(
                        lambda checked=False, u=url: QGuiApplication.clipboard().setText(u.toString()))

            pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            menu.exec(pos)
            event.accept()
        except Exception as e:
            print(f"Context menu exception: {e}")
            super().contextMenuEvent(event)


class CustomTabBar(QTabBar):
    """Custom tab bar enforcing uniform sizing, dynamic shrinking, and scroll buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setExpanding(False)

    def tabSizeHint(self, index):
        count = self.count()
        if count == 0:
            return super().tabSizeHint(index)

        std_size = super().tabSizeHint(index)
        max_tab_width = 180
        min_tab_width = 36

        parent = self.parentWidget()
        avail_width = parent.width() - 55 if parent else self.width()

        if avail_width < min_tab_width:
            avail_width = 800

        equal_width = avail_width // count
        target_width = max(min_tab_width, min(max_tab_width, equal_width))

        return QSize(target_width, std_size.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateGeometry()


class SettingsTab(QWidget):
    """Native Sharp Browser Settings page."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)

        # Navigation Sidebar
        left_box = QVBoxLayout()
        header_title = QLabel("Settings ⚙️")
        header_title.setStyleSheet("font-size: 26px; font-weight: 800; margin-bottom: 12px;")
        left_box.addWidget(header_title)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(220)
        self.nav_list.setStyleSheet("""
            QListWidget { border: none; background: transparent; font-size: 15px; font-weight: 600; }
            QListWidget::item { padding: 10px 14px; border-radius: 8px; margin-bottom: 4px; }
            QListWidget::item:selected { background-color: rgba(37, 99, 235, 0.2); color: #2563eb; }
        """)

        nav_items = [
            ("ℹ️  About SharpBrowser", 0),
            ("🎨  Personalization", 1),
            ("🔍  Search Engine", 2),
            ("📥  Downloads", 3),
            ("🔧  System", 4)
        ]

        for text, idx in nav_items:
            item = QListWidgetItem(text)
            self.nav_list.addItem(item)

        left_box.addWidget(self.nav_list)
        left_box.addStretch()
        main_layout.addLayout(left_box)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("color: #3f3f46;")
        main_layout.addWidget(divider)

        # Stacked Panels
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, stretch=1)

        self.init_about_page()
        self.init_personalization_page()
        self.init_search_engine_page()
        self.init_downloads_page()
        self.init_system_page()

        self.nav_list.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        self.nav_list.setCurrentRow(0)

    def init_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_path = get_app_icon_path()
        if icon_path and os.path.exists(icon_path):
            logo_lbl = QLabel()
            logo_lbl.setPixmap(QPixmap(icon_path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
            header_layout.addWidget(logo_lbl)

        title = QLabel(f"SharpBrowser (Version: {APP_VERSION})")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        github_btn = QPushButton("Check Github")
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.setStyleSheet("""
            background-color: transparent; color: #00a8ff; font-weight: 600;
            padding: 10px 22px; border-radius: 20px; border: 2px solid #00a8ff;
        """)
        github_btn.clicked.connect(
            lambda: self.main_window.add_new_tab(QUrl("https://github.com/revinhere/Sharp-Browser/releases")))
        btn_layout.addWidget(github_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()
        self.content_stack.addWidget(page)

    def init_personalization_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(20)

        # Dark Mode Toggle
        theme_row = QHBoxLayout()
        theme_lbl = QLabel("Dark Mode Theme")
        theme_lbl.setStyleSheet("font-size: 16px; font-weight: 600;")
        theme_row.addWidget(theme_lbl)
        theme_row.addStretch()

        theme_switch = SwitchToggle(is_dark=self.main_window.dark_mode)
        theme_switch.setChecked(self.main_window.dark_mode)
        theme_switch.clicked.connect(self.main_window.toggle_dark_mode)
        theme_row.addWidget(theme_switch)
        layout.addLayout(theme_row)

        # Show Home Button
        home_row = QHBoxLayout()
        home_lbl = QLabel("Show Home Button")
        home_lbl.setStyleSheet("font-size: 16px; font-weight: 600;")
        home_row.addWidget(home_lbl)
        home_row.addStretch()

        show_home = self.main_window.settings.value("show_home_button", True, type=bool)
        home_switch = SwitchToggle(is_dark=self.main_window.dark_mode)
        home_switch.setChecked(show_home)

        def toggle_home_btn(checked):
            self.main_window.settings.setValue("show_home_button", checked)
            for win in windows:
                win.home_btn.setVisible(checked)

        home_switch.clicked.connect(toggle_home_btn)
        home_row.addWidget(home_switch)
        layout.addLayout(home_row)

        # Home Target Radio Selection
        home_target_lbl = QLabel("Home Button Opens:")
        home_target_lbl.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        layout.addWidget(home_target_lbl)

        home_type = self.main_window.settings.value("home_page_type", "new_tab")

        r1 = QRadioButton("New Tab Page (sharp://home)")
        r2 = QRadioButton("Custom Website URL")
        r1.setChecked(home_type == "new_tab")
        r2.setChecked(home_type == "custom")

        custom_url_input = QLineEdit()
        custom_url_input.setPlaceholderText("https://example.com")
        custom_url_input.setText(
            self.main_window.settings.value("custom_home_url", "https://google.com").replace("\\", "/"))
        custom_url_input.setEnabled(home_type == "custom")

        def on_home_type_changed():
            if r1.isChecked():
                self.main_window.settings.setValue("home_page_type", "new_tab")
                custom_url_input.setEnabled(False)
            else:
                self.main_window.settings.setValue("home_page_type", "custom")
                custom_url_input.setEnabled(True)

        r1.toggled.connect(on_home_type_changed)
        r2.toggled.connect(on_home_type_changed)
        custom_url_input.textChanged.connect(
            lambda t: self.main_window.settings.setValue("custom_home_url", t.strip().replace("\\", "/")))

        layout.addWidget(r1)
        layout.addWidget(r2)
        layout.addWidget(custom_url_input)

        layout.addStretch()
        self.content_stack.addWidget(page)

    def init_search_engine_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        se_lbl = QLabel("Default Search Engine")
        se_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(se_lbl)

        combo = QComboBox()
        combo.addItems(["Google", "Bing", "DuckDuckGo", "Brave", "Yahoo"])
        curr_se = self.main_window.settings.value("search_engine", "Google")
        combo.setCurrentText(curr_se)
        combo.currentTextChanged.connect(lambda val: self.main_window.settings.setValue("search_engine", val))

        layout.addWidget(combo)
        layout.addStretch()
        self.content_stack.addWidget(page)

    def init_downloads_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(20)

        loc_title = QLabel("Download Location")
        loc_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(loc_title)

        loc_row = QHBoxLayout()
        curr_dir = self.main_window.settings.value("download_dir", os.path.expanduser("~/Downloads")).replace("\\", "/")
        path_lbl = QLineEdit(curr_dir)
        path_lbl.setReadOnly(True)
        loc_row.addWidget(path_lbl)

        change_btn = QPushButton("Change")
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def choose_dir():
            folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", path_lbl.text())
            if folder:
                folder_clean = folder.replace("\\", "/")
                path_lbl.setText(folder_clean)
                self.main_window.settings.setValue("download_dir", folder_clean)

        change_btn.clicked.connect(choose_dir)
        loc_row.addWidget(change_btn)
        layout.addLayout(loc_row)

        ask_row = QHBoxLayout()
        ask_lbl = QLabel("Ask where to save a file before downloading")
        ask_lbl.setStyleSheet("font-size: 14px; font-weight: 500;")
        ask_row.addWidget(ask_lbl)
        ask_row.addStretch()

        ask_switch = SwitchToggle(is_dark=self.main_window.dark_mode)
        ask_switch.setChecked(self.main_window.settings.value("ask_download_location", True, type=bool))
        ask_switch.clicked.connect(lambda c: self.main_window.settings.setValue("ask_download_location", c))
        ask_row.addWidget(ask_switch)
        layout.addLayout(ask_row)

        pop_row = QHBoxLayout()
        pop_lbl = QLabel("Show downloads dropdown window when downloading")
        pop_lbl.setStyleSheet("font-size: 14px; font-weight: 500;")
        pop_row.addWidget(pop_lbl)
        pop_row.addStretch()

        pop_switch = SwitchToggle(is_dark=self.main_window.dark_mode)
        pop_switch.setChecked(self.main_window.settings.value("show_download_popup", True, type=bool))
        pop_switch.clicked.connect(lambda c: self.main_window.settings.setValue("show_download_popup", c))
        pop_row.addWidget(pop_switch)
        layout.addLayout(pop_row)

        layout.addStretch()
        self.content_stack.addWidget(page)

    def init_system_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(20)

        # On Startup Section
        startup_title = QLabel("On startup")
        startup_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(startup_title)

        startup_row = QHBoxLayout()
        startup_lbl = QLabel("When SharpBrowser starts:")
        startup_lbl.setStyleSheet("font-size: 14px; font-weight: 500;")
        startup_row.addWidget(startup_lbl)

        startup_combo = QComboBox()
        startup_combo.addItems(["Open a new tab", "Continue where I left off"])
        curr_startup = self.main_window.settings.value("startup_behavior", "Open a new tab")
        startup_combo.setCurrentText(curr_startup)

        def on_startup_changed(val):
            self.main_window.settings.setValue("startup_behavior", val)
            if val == "Continue where I left off":
                self.main_window.save_session_tabs()

        startup_combo.currentTextChanged.connect(on_startup_changed)
        startup_row.addWidget(startup_combo)
        layout.addLayout(startup_row)

        close_row = QHBoxLayout()
        close_lbl = QLabel("Confirmation dialogue before closing a window")
        close_lbl.setStyleSheet("font-size: 14px; font-weight: 500;")
        close_row.addWidget(close_lbl)
        close_row.addStretch()

        close_switch = SwitchToggle(is_dark=self.main_window.dark_mode)
        close_switch.setChecked(self.main_window.settings.value("confirm_on_close", True, type=bool))
        close_switch.clicked.connect(lambda c: self.main_window.settings.setValue("confirm_on_close", c))
        close_row.addWidget(close_switch)
        layout.addLayout(close_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #3f3f46;")
        layout.addWidget(divider)

        sys_row = QHBoxLayout()
        sys_lbl = QLabel("Use graphics acceleration when available")
        sys_lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        sys_row.addWidget(sys_lbl)
        sys_row.addStretch()

        sys_switch = SwitchToggle(is_dark=self.main_window.dark_mode)
        sys_switch.setChecked(self.main_window.settings.value("use_hardware_accel", True, type=bool))
        sys_switch.clicked.connect(lambda c: self.main_window.settings.setValue("use_hardware_accel", c))
        sys_row.addWidget(sys_switch)
        layout.addLayout(sys_row)

        layout.addStretch()
        self.content_stack.addWidget(page)


class HistoryTab(QWidget):
    """Modern GUI Tab for viewing and managing browsing history with website icons."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title = QLabel("Browsing History 🕒")
        title.setStyleSheet("font-size: 24px; font-weight: 800;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        clear_btn = QPushButton("Clear History")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("padding: 8px 16px; font-weight: 600; border-radius: 8px;")
        clear_btn.clicked.connect(self.clear_history)
        header_layout.addWidget(clear_btn)

        clear_data_btn = QPushButton("Clear Browsing Data")
        clear_data_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_data_btn.setStyleSheet("padding: 8px 16px; font-weight: 600; border-radius: 8px;")
        clear_data_btn.clicked.connect(self.clear_browsing_data)
        header_layout.addWidget(clear_data_btn)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date & Time", "Title", "URL", "Action"])
        self.table.setColumnWidth(0, 180)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        self.table.cellClicked.connect(self.handle_cell_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.handle_context_menu)

        layout.addLayout(header_layout)
        layout.addWidget(self.table)
        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(0)
        icon_provider = QFileIconProvider()

        for row, item in enumerate(reversed(history_data)):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.get('time', '')))

            # Title column with domain favicon/logo icon
            url_str = item.get('url', '')
            title_text = item.get('title', '') or url_str
            title_item = QTableWidgetItem(title_text)

            if url_str.startswith("file://") or os.path.exists(url_str):
                title_item.setIcon(icon_provider.icon(QFileIconProvider.IconType.File))
            else:
                default_icon = icon_provider.icon(QFileIconProvider.IconType.Network)
                title_item.setIcon(default_icon)

            self.table.setItem(row, 1, title_item)

            url_item = QTableWidgetItem(url_str)
            self.table.setItem(row, 2, url_item)

            del_btn = QPushButton("Remove")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                "background-color: #ef4444; color: white; border: none; border-radius: 6px; padding: 4px 10px;")
            idx = len(history_data) - 1 - row
            del_btn.clicked.connect(lambda _, i=idx: self.delete_item(i))
            self.table.setCellWidget(row, 3, del_btn)

    def handle_cell_click(self, row, column):
        if column != 3:
            url_item = self.table.item(row, 2)
            if url_item:
                curr = self.main_window.current_browser()
                if isinstance(curr, QWebEngineView):
                    curr.setUrl(QUrl(url_item.text()))
                else:
                    self.main_window.add_new_tab(QUrl(url_item.text()))

    def handle_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if item:
            row = item.row()
            url_item = self.table.item(row, 2)
            if url_item:
                menu = QMenu(self)
                open_win_action = menu.addAction("Open in new window")
                action = menu.exec(self.table.viewport().mapToGlobal(pos))
                if action == open_win_action:
                    self.main_window.open_new_window_with_url(QUrl(url_item.text()))

    def delete_item(self, index):
        if 0 <= index < len(history_data):
            history_data.pop(index)
            save_json(HISTORY_FILE, history_data)
            self.refresh_table()

    def clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History", "Are you sure you want to clear all browsing history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            history_data.clear()
            save_json(HISTORY_FILE, history_data)
            self.refresh_table()

    def clear_browsing_data(self):
        reply = QMessageBox.question(
            self, "Clear Browsing Data",
            "Are you sure you want to clear cookies, cache, and all browsing data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            global persistent_profile
            if persistent_profile:
                persistent_profile.clearHttpCache()
                persistent_profile.cookieStore().deleteAllCookies()
                persistent_profile.clearAllVisitedLinks()
            history_data.clear()
            save_json(HISTORY_FILE, history_data)
            self.refresh_table()
            QMessageBox.information(self, "Success", "Browsing data successfully cleared!")


class DownloadsTab(QWidget):
    """Modern GUI Tab for managing downloads with progress and system file icons."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.refresh_table)
        self.timer.start()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title = QLabel("Downloads 📥")
        title.setStyleSheet("font-size: 24px; font-weight: 800;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date & Time", "File Name", "Status", "Path", "Action", "Open Folder"])
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 340)
        self.table.setColumnWidth(4, 160)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        layout.addLayout(header_layout)
        layout.addWidget(self.table)
        self.refresh_table()

    def cancel_download(self, dl_id):
        if dl_id in active_download_requests:
            try:
                active_download_requests[dl_id].cancel()
            except Exception:
                pass

    def refresh_table(self):
        scrollbar = self.table.verticalScrollBar()
        scroll_pos = scrollbar.value()

        icon_provider = QFileIconProvider()
        self.table.setRowCount(0)

        for row, item in enumerate(reversed(download_data)):
            self.table.insertRow(row)
            status_text = get_download_status(item)
            dl_id = item.get('id')
            file_path = item.get('path', '').replace("\\", "/")

            self.table.setItem(row, 0, QTableWidgetItem(item.get('time', '')))

            file_item = QTableWidgetItem(item.get('name', ''))
            if file_path and os.path.exists(file_path):
                file_item.setIcon(icon_provider.icon(QFileInfo(file_path)))
            else:
                file_item.setIcon(icon_provider.icon(QFileIconProvider.IconType.File))
            self.table.setItem(row, 1, file_item)

            status_item = QTableWidgetItem(status_text)
            if "100%" in status_text or status_text == "Completed":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif status_text in ("Canceled", "Deleted"):
                status_item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 2, status_item)

            self.table.setItem(row, 3, QTableWidgetItem(file_path))

            is_downloading = "%" in status_text and status_text != "100%" and status_text != "Completed"

            action_layout = QHBoxLayout()
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)

            if is_downloading:
                open_btn = QPushButton("Open File")
                open_btn.setEnabled(False)
                open_btn.setStyleSheet("border-radius: 6px; padding: 4px 8px;")
                action_layout.addWidget(open_btn)

                cancel_btn = QPushButton("Cancel")
                cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                cancel_btn.setStyleSheet(
                    "background-color: #ef4444; color: white; border: none; border-radius: 6px; padding: 4px 8px;")
                cancel_btn.clicked.connect(lambda _, d=dl_id: self.cancel_download(d))
                action_layout.addWidget(cancel_btn)
            else:
                open_btn = QPushButton("Open File")
                file_exists = os.path.exists(file_path)
                is_completed = status_text == "Completed" or "100%" in status_text
                is_canceled_or_deleted = status_text in ("Canceled", "Deleted")

                open_btn.setEnabled(file_exists and is_completed and not is_canceled_or_deleted)
                if file_exists and is_completed and not is_canceled_or_deleted:
                    open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    open_btn.clicked.connect(
                        lambda _, p=file_path: os.startfile(p) if hasattr(os, 'startfile') else None)
                open_btn.setStyleSheet("border-radius: 6px; padding: 4px 8px;")
                action_layout.addWidget(open_btn)

            action_widget = QWidget()
            action_widget.setLayout(action_layout)
            self.table.setCellWidget(row, 4, action_widget)

            open_folder_btn = QPushButton("Open Folder")
            folder_path = item.get('folder', '').replace("\\", "/")
            folder_exists = os.path.exists(folder_path)
            is_canceled_or_deleted = status_text in ("Canceled", "Deleted")
            open_folder_btn.setEnabled(folder_exists and not is_canceled_or_deleted)
            if folder_exists and not is_canceled_or_deleted:
                open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                open_folder_btn.clicked.connect(
                    lambda _, f=folder_path: os.startfile(f) if hasattr(os, 'startfile') else None)
            open_folder_btn.setStyleSheet("border-radius: 6px; padding: 4px 8px;")
            self.table.setCellWidget(row, 5, open_folder_btn)

        scrollbar.setValue(scroll_pos)


class Browser(QMainWindow):
    def __init__(self, initial_url=None):
        super().__init__()
        self.setWindowTitle("Sharp Browser 🌐")
        self.resize(1200, 800)

        icon_path = get_app_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings("SharpBrowser", "BrowserSettings")
        self.dark_mode = self.settings.value("dark_mode", False, type=bool)

        self.was_maximized_before_fullscreen = False
        self.saved_geometry_before_fullscreen = None

        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        if self.settings.contains("windowState"):
            self.restoreState(self.settings.value("windowState"))
        if self.settings.value("isMaximized", False, type=bool):
            self.showMaximized()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ROW 1: Tab Header Row
        tab_header_widget = QWidget()
        tab_header_layout = QHBoxLayout(tab_header_widget)
        tab_header_layout.setContentsMargins(4, 4, 4, 0)
        tab_header_layout.setSpacing(2)

        self.tab_bar = CustomTabBar()
        self.tab_bar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.tab_bar.currentChanged.connect(self.on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self.close_tab)
        self.tab_bar.tabMoved.connect(self.on_tab_moved)
        tab_header_layout.addWidget(self.tab_bar)

        self.new_tab_btn = QToolButton()
        self.new_tab_btn.setText("+")
        self.new_tab_btn.setToolTip("Open new tab")
        self.new_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_tab_btn.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.new_tab_btn.clicked.connect(lambda: self.add_new_tab())
        tab_header_layout.addWidget(self.new_tab_btn)

        tab_header_layout.addStretch()
        main_layout.addWidget(tab_header_widget)

        # ROW 2: Navigation Toolbar
        self.nav_toolbar = QToolBar()
        self.nav_toolbar.setMovable(False)
        main_layout.addWidget(self.nav_toolbar)

        # Controls
        self.back_btn = QToolButton()
        self.back_btn.setText("🡰")
        self.back_btn.setToolTip("Back")
        self.back_btn.clicked.connect(self.go_back)
        self.nav_toolbar.addWidget(self.back_btn)

        self.forward_btn = QToolButton()
        self.forward_btn.setText("🡲")
        self.forward_btn.setToolTip("Forward")
        self.forward_btn.clicked.connect(self.go_forward)
        self.nav_toolbar.addWidget(self.forward_btn)

        self.reload_btn = QToolButton()
        self.reload_btn.setText("↻")
        self.reload_btn.setToolTip("Reload")
        self.reload_btn.clicked.connect(self.reload_page)
        self.nav_toolbar.addWidget(self.reload_btn)

        self.home_btn = QToolButton()
        self.home_btn.setText("🏠")
        self.home_btn.setToolTip("Home")
        self.home_btn.setVisible(self.settings.value("show_home_button", True, type=bool))
        self.home_btn.clicked.connect(self.go_home)
        self.nav_toolbar.addWidget(self.home_btn)

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Search or enter address")
        self.url_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.nav_toolbar.addWidget(self.url_bar)

        self.bookmark_btn = QToolButton()
        self.bookmark_btn.setText("★")
        self.bookmark_btn.setToolTip("Bookmark this page")
        self.bookmark_btn.clicked.connect(self.add_bookmark)
        self.nav_toolbar.addWidget(self.bookmark_btn)

        self.downloads_btn = QToolButton()
        self.downloads_btn.setText("⭳")
        self.downloads_btn.setToolTip("Downloads")
        self.downloads_btn.clicked.connect(self.show_downloads_popup)
        self.nav_toolbar.addWidget(self.downloads_btn)

        self.history_btn = QToolButton()
        self.history_btn.setText("🕒")
        self.history_btn.setToolTip("History")
        self.history_btn.clicked.connect(self.open_history_tab)
        self.nav_toolbar.addWidget(self.history_btn)

        self.new_win_btn = QToolButton()
        self.new_win_btn.setText("❐")
        self.new_win_btn.setToolTip("New Window")
        self.new_win_btn.clicked.connect(lambda: self.open_new_window_with_url())
        self.nav_toolbar.addWidget(self.new_win_btn)

        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙️")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.open_settings_tab)
        self.nav_toolbar.addWidget(self.settings_btn)

        # ROW 3: Bookmarks Bar
        self.bm_bar = QToolBar()
        self.bm_bar.setMovable(False)
        main_layout.addWidget(self.bm_bar)
        self.refresh_bookmarks_bar()

        # ROW 4: Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(2)
        main_layout.addWidget(self.progress_bar)

        # ROW 5: Container
        self.container = QStackedWidget()
        main_layout.addWidget(self.container, stretch=1)

        self.escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.escape_shortcut.activated.connect(self.exit_fullscreen)

        self.apply_theme()

        startup_behavior = self.settings.value("startup_behavior", "Open a new tab")
        session_urls = load_json(SESSION_FILE) if startup_behavior == "Continue where I left off" else []

        if initial_url:
            self.add_new_tab(initial_url)
        elif session_urls:
            for url_str in session_urls:
                self.add_new_tab(QUrl(url_str))
        else:
            self.add_new_tab()

    def closeEvent(self, event: QCloseEvent):
        """Saves window geometry, session state, and handles close confirmation."""
        confirm_close = self.settings.value("confirm_on_close", True, type=bool)
        if confirm_close and self.container.count() > 1:
            reply = QMessageBox.question(
                self,
                "Close Window",
                f"Are you sure you want to close this window and all {self.container.count()} tabs?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.save_session_tabs()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("isMaximized", self.isMaximized())
        super().closeEvent(event)

    def save_session_tabs(self):
        """Persists open tab URLs for session restoration."""
        urls = []
        for i in range(self.container.count()):
            widget = self.container.widget(i)
            if isinstance(widget, CustomWebView):
                urls.append(widget.url().toString())
        save_json(SESSION_FILE, urls)

    def enter_fullscreen(self):
        """Remembers pre-fullscreen geometry and window maximized state."""
        self.was_maximized_before_fullscreen = self.isMaximized()
        self.saved_geometry_before_fullscreen = self.saveGeometry()
        self.nav_toolbar.hide()
        self.bm_bar.hide()
        self.tab_bar.parentWidget().hide()
        self.showFullScreen()

    def exit_fullscreen(self):
        """Restores exact previous window state (Maximized or Restored geometry)."""
        self.nav_toolbar.show()
        self.bm_bar.show()
        self.tab_bar.parentWidget().show()
        if self.was_maximized_before_fullscreen:
            self.showMaximized()
        else:
            self.showNormal()
            if self.saved_geometry_before_fullscreen:
                self.restoreGeometry(self.saved_geometry_before_fullscreen)

    def add_new_tab(self, url=None):
        """Creates a new browser tab with optional custom URL support."""
        browser = CustomWebView(self, is_dark=self.dark_mode)
        browser.page().loadProgress.connect(self.on_load_progress)
        browser.titleChanged.connect(lambda title, b=browser: self.on_browser_title_changed(b, title))
        browser.urlChanged.connect(lambda u, b=browser: self.on_browser_url_changed(b, u))
        browser.iconChanged.connect(lambda icon, b=browser: self.on_icon_changed(icon, b))

        idx = self.container.addWidget(browser)
        tab_idx = self.tab_bar.addTab("New Tab")
        self.tab_bar.setCurrentIndex(tab_idx)

        if url is None:
            home_type = self.settings.value("home_page_type", "new_tab")
            if home_type == "custom":
                custom_url = self.settings.value("custom_home_url", "https://google.com").replace("\\", "/")
                if not custom_url.startswith(('http://', 'https://', 'sharp://', 'file://')):
                    custom_url = 'https://' + custom_url
                target_url = QUrl(custom_url)
            else:
                target_url = QUrl("sharp://home")
        else:
            target_url = url if isinstance(url, QUrl) else QUrl(str(url).replace("\\", "/"))

        browser.setUrl(target_url)
        self.save_session_tabs()
        return browser

    def close_tab(self, index):
        if self.container.count() <= 1:
            self.close()
            return

        widget = self.container.widget(index)
        self.container.removeWidget(widget)
        self.tab_bar.removeTab(index)
        widget.deleteLater()
        self.save_session_tabs()

    def on_tab_changed(self, index):
        if index >= 0:
            widget = self.container.widget(index)
            self.container.setCurrentIndex(index)
            if isinstance(widget, QWebEngineView):
                widget.update()
                widget.setFocus()
                url_str = widget.url().toString()
                title_str = widget.title() or "Sharp Browser"
                self.url_bar.setText(url_str)
                self.setWindowTitle(f"{title_str} - Sharp Browser")
            elif isinstance(widget, HistoryTab):
                self.url_bar.setText("sharp://history")
                self.setWindowTitle("History - Sharp Browser")
            elif isinstance(widget, DownloadsTab):
                self.url_bar.setText("sharp://downloads")
                self.setWindowTitle("Downloads - Sharp Browser")
            elif isinstance(widget, SettingsTab):
                self.url_bar.setText("sharp://settings")
                self.setWindowTitle("Settings - Sharp Browser")

    def on_tab_moved(self, from_idx, to_idx):
        widget = self.container.widget(from_idx)
        if widget:
            self.container.removeWidget(widget)
            self.container.insertWidget(to_idx, widget)
            self.tab_bar.setCurrentIndex(to_idx)

    def current_browser(self):
        return self.container.currentWidget()

    def go_back(self):
        curr = self.current_browser()
        if isinstance(curr, QWebEngineView):
            curr.back()

    def go_forward(self):
        curr = self.current_browser()
        if isinstance(curr, QWebEngineView):
            curr.forward()

    def reload_page(self):
        curr = self.current_browser()
        if isinstance(curr, QWebEngineView):
            curr.reload()

    def go_home(self):
        home_type = self.settings.value("home_page_type", "new_tab")
        if home_type == "custom":
            target_url = self.settings.value("custom_home_url", "https://google.com").replace("\\", "/")
            if not target_url.startswith(("http://", "https://")):
                target_url = "https://" + target_url
            url_obj = QUrl(target_url)
        else:
            url_obj = QUrl("sharp://home")

        curr = self.current_browser()
        if isinstance(curr, QWebEngineView):
            curr.setUrl(url_obj)
        else:
            self.add_new_tab(url_obj)

    def navigate_to_url(self):
        """Parses address bar input including path extensions like linktr.ee/username."""
        text = self.url_bar.text().strip()
        curr = self.current_browser()
        if not isinstance(curr, QWebEngineView) or not text:
            return

        if text == "sharp://home":
            curr.setUrl(QUrl("sharp://home"))
            return
        elif text == "sharp://history":
            self.open_history_tab()
            return
        elif text == "sharp://downloads":
            self.open_downloads_tab()
            return
        elif text == "sharp://settings":
            self.open_settings_tab()
            return

        # Check local files
        if os.path.exists(text):
            curr.setUrl(QUrl.fromLocalFile(os.path.abspath(text)))
            return

        # Check standard explicit schemes
        if text.startswith(('http://', 'https://', 'sharp://', 'file://')):
            curr.setUrl(QUrl(text))
            return

        # If user entered spaces, perform search engine lookup
        if " " in text:
            engine = self.settings.value("search_engine", "Google")
            curr.setUrl(QUrl(get_search_url(text, engine)))
            return

        # Handle domains and path subroutes (e.g. linktr.ee/username)
        if "." in text or "/" in text or "\\" in text:
            clean_url = "https://" + text.replace("\\", "/")
            curr.setUrl(QUrl(clean_url))
            return

        # Fallback to search engine query
        engine = self.settings.value("search_engine", "Google")
        curr.setUrl(QUrl(get_search_url(text, engine)))

    def on_load_progress(self, progress):
        self.progress_bar.setValue(progress)
        if progress >= 100:
            QTimer.singleShot(300, lambda: self.progress_bar.setValue(0))

    def on_browser_title_changed(self, view, title):
        """Updates tab title dynamically when webpage title changes."""
        for i in range(self.container.count()):
            if self.container.widget(i) == view:
                display_title = title if title else "New Tab"
                if len(display_title) > 22:
                    display_title = display_title[:20] + "..."
                self.tab_bar.setTabText(i, display_title)

                if self.container.currentIndex() == i:
                    self.setWindowTitle(f"{title or 'Sharp Browser'} - Sharp Browser")

                url_str = view.url().toString()
                if url_str and url_str != "sharp://home" and title:
                    now_str = get_os_formatted_datetime()
                    if not history_data or history_data[-1].get('url') != url_str:
                        history_data.append({'time': now_str, 'title': title or url_str, 'url': url_str})
                        save_json(HISTORY_FILE, history_data)
                break

    def on_browser_url_changed(self, view, url):
        curr = self.current_browser()
        if curr == view:
            url_str = url.toString()
            if not url_str.startswith("sharp://"):
                self.url_bar.setText(url_str)
        self.save_session_tabs()

    def on_icon_changed(self, icon, view):
        for i in range(self.container.count()):
            if self.container.widget(i) == view:
                self.tab_bar.setTabIcon(i, icon)
                break

    def add_bookmark(self):
        curr = self.current_browser()
        if isinstance(curr, QWebEngineView):
            curr_url = self.url_bar.text()
            title = curr.page().title() or curr_url
            if curr_url and not any(b.get('url') == curr_url for b in bookmarks_data):
                bookmarks_data.append({'title': title, 'url': curr_url})
                save_json(BOOKMARKS_FILE, bookmarks_data)
                self.refresh_bookmarks_bar()

    def refresh_bookmarks_bar(self):
        self.bm_bar.clear()
        for bm in bookmarks_data:
            btn = QToolButton()
            title = bm.get('title', bm.get('url'))
            short_title = title[:20] + "..." if len(title) > 20 else title
            btn.setText(short_title)
            btn.setToolTip(bm.get('url'))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

            url = bm.get('url')
            btn.clicked.connect(lambda _, u=url: self.open_bookmark_url(u))
            btn.customContextMenuRequested.connect(
                lambda pos, b_item=bm, button=btn: self.show_bookmark_context_menu(pos, button, b_item))
            self.bm_bar.addWidget(btn)

    def open_bookmark_url(self, url):
        curr = self.current_browser()
        if isinstance(curr, QWebEngineView):
            curr.setUrl(QUrl(url))
        else:
            self.add_new_tab(QUrl(url))

    def show_bookmark_context_menu(self, pos: QPoint, button: QToolButton, bm_item: dict):
        menu = QMenu(self)

        open_tab = menu.addAction("Open in new tab")
        open_win = menu.addAction("Open in new window")
        copy_link = menu.addAction("Copy link")
        rename_act = menu.addAction("Rename")
        remove_act = menu.addAction("Remove")

        action = menu.exec(button.mapToGlobal(pos))
        url = bm_item.get('url', '')

        if action == open_tab:
            self.add_new_tab(QUrl(url))
        elif action == open_win:
            self.open_new_window_with_url(QUrl(url))
        elif action == copy_link:
            QGuiApplication.clipboard().setText(url)
        elif action == rename_act:
            new_title, ok = QInputDialog.getText(self, "Rename Bookmark", "Enter new bookmark name:",
                                                 QLineEdit.EchoMode.Normal, bm_item.get('title', ''))
            if ok and new_title.strip():
                bm_item['title'] = new_title.strip()
                save_json(BOOKMARKS_FILE, bookmarks_data)
                self.refresh_bookmarks_bar()
        elif action == remove_act:
            if bm_item in bookmarks_data:
                bookmarks_data.remove(bm_item)
                save_json(BOOKMARKS_FILE, bookmarks_data)
                self.refresh_bookmarks_bar()

    def show_downloads_popup(self):
        popup = DownloadsPopupWindow(self)
        btn_pos = self.downloads_btn.mapToGlobal(QPoint(0, self.downloads_btn.height()))
        popup.move(btn_pos.x() - 300 + self.downloads_btn.width(), btn_pos.y() + 4)
        popup.show()

    def open_history_tab(self):
        for i in range(self.container.count()):
            if isinstance(self.container.widget(i), HistoryTab):
                self.tab_bar.setCurrentIndex(i)
                return
        hist_tab = HistoryTab(self)
        idx = self.container.addWidget(hist_tab)
        tab_idx = self.tab_bar.addTab("🕒 History")
        self.tab_bar.setCurrentIndex(tab_idx)

    def open_downloads_tab(self):
        for i in range(self.container.count()):
            if isinstance(self.container.widget(i), DownloadsTab):
                self.tab_bar.setCurrentIndex(i)
                return
        dl_tab = DownloadsTab(self)
        idx = self.container.addWidget(dl_tab)
        tab_idx = self.tab_bar.addTab("📥 Downloads")
        self.tab_bar.setCurrentIndex(tab_idx)

    def open_settings_tab(self):
        for i in range(self.container.count()):
            if isinstance(self.container.widget(i), SettingsTab):
                self.tab_bar.setCurrentIndex(i)
                return
        st_tab = SettingsTab(self)
        idx = self.container.addWidget(st_tab)
        tab_idx = self.tab_bar.addTab("⚙️ Settings")
        self.tab_bar.setCurrentIndex(tab_idx)

    def apply_theme(self):
        accent_color = get_os_accent_color()

        if self.dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget { background-color: #121214; color: #f3f4f6; }
                QLineEdit { background-color: #18181b; color: #f3f4f6; border: 1px solid #3f3f46; border-radius: 6px; padding: 6px; }
                QToolBar { background-color: #18181b; border-bottom: 1px solid #27272a; spacing: 6px; padding: 4px; }
                QTabBar { qproperty-drawBase: 0; background-color: #121214; }
                QTabBar::tab { background: #1f1f23; color: #a1a1aa; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
                QTabBar::tab:selected { background: #121214; color: #f3f4f6; font-weight: bold; border: 1px solid #3f3f46; border-bottom: none; }
                QTableWidget { background-color: #18181b; color: #f3f4f6; gridline-color: #27272a; alternate-background-color: #1f1f23; }
                QHeaderView::section { background-color: #27272a; color: #f3f4f6; font-weight: bold; border: 1px solid #3f3f46; padding: 6px; }
                QPushButton, QToolButton { background-color: #27272a; color: #f3f4f6; border: 1px solid #3f3f46; border-radius: 6px; padding: 5px 10px; }
                QPushButton:hover, QToolButton:hover { background-color: #3f3f46; }
                QMenu { background-color: #1f1f23; color: #f3f4f6; border: 1px solid #3f3f46; }
                QMenu::item:selected { background-color: #27272a; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget { background-color: #ffffff; color: #111827; }
                QLineEdit { background-color: #ffffff; color: #111827; border: 1px solid #d1d5db; border-radius: 6px; padding: 6px; }
                QToolBar { background-color: #f8fafc; border-bottom: 1px solid #e2e8f0; spacing: 6px; padding: 4px; }
                QTabBar { qproperty-drawBase: 0; background-color: #f1f5f9; }
                QTabBar::tab { background: #e2e8f0; color: #475569; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
                QTabBar::tab:selected { background: #ffffff; color: #111827; font-weight: bold; border: 1px solid #cbd5e1; border-bottom: none; }
                QTableWidget { background-color: #ffffff; color: #111827; gridline-color: #e2e8f0; alternate-background-color: #f8fafc; }
                QHeaderView::section { background-color: #f1f5f9; color: #111827; font-weight: bold; border: 1px solid #cbd5e1; padding: 6px; }
                QPushButton, QToolButton { background-color: #f1f5f9; color: #111827; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 10px; }
                QPushButton:hover, QToolButton:hover { background-color: #e2e8f0; }
                QMenu { background-color: #ffffff; color: #111827; border: 1px solid #cbd5e1; }
                QMenu::item:selected { background-color: #f1f5f9; }
            """)

        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: transparent;
                height: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {accent_color};
            }}
        """)

        for i in range(self.container.count()):
            widget = self.container.widget(i)
            if isinstance(widget, CustomWebView):
                if hasattr(widget.page(), 'sync_color_scheme'):
                    widget.page().sync_color_scheme(self.dark_mode)
                if widget.url().toString() == "sharp://home":
                    widget.setHtml(get_home_html(self.dark_mode), QUrl("sharp://home"))

    def toggle_dark_mode(self):
        """Toggles dark mode instantly without refreshing webpages."""
        self.dark_mode = not self.dark_mode
        self.settings.setValue("dark_mode", self.dark_mode)

        for win in list(windows):
            win.dark_mode = self.dark_mode
            win.apply_theme()

    def open_new_window_with_url(self, url=None):
        start_url = url if url else None
        new_win = Browser(initial_url=start_url)
        windows.append(new_win)
        new_win.show()
        return new_win


if __name__ == "__main__":
    if hasattr(Qt.ApplicationAttribute, 'AA_ShareOpenGLContexts'):
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)

    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    persistent_profile = QWebEngineProfile("SharpBrowserPersistentProfile", app)
    persistent_profile.setPersistentStoragePath(STORAGE_DIR)
    persistent_profile.setCachePath(STORAGE_DIR)

    CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    persistent_profile.setHttpUserAgent(CHROME_UA)

    settings = persistent_profile.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LinksIncludedInFocusChain, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)

    persistent_profile.downloadRequested.connect(global_download_handler)

    main_window = Browser()
    windows.append(main_window)
    main_window.show()
    sys.exit(app.exec())