# =====================================================================
#  Pannello Wi-Fi in stile Omarchy (shell/plugins/panels/network).
#  Lo apre il click sinistro sul widget Wi-Fi di YASB.
#
#  Uso:
#      pythonw wifi-panel.pyw                  apre/chiude il pannello
#      python  wifi-panel.pyw --screenshot X   lo disegna in X.png ed esce
#
#  Resta in memoria dopo la prima apertura: i click successivi mandano
#  "toggle" sulla pipe e il pannello compare subito.
#  Dipendenze: pip install --user PyQt6 psutil qrcode winrt-runtime
#              winrt-Windows.Devices.Radios winrt-Windows.Foundation
#              winrt-Windows.Foundation.Collections
# =====================================================================

import sys
import ctypes

PIPE_NAME = "windowsarchy-wifi-panel"

# --- client veloce: se il pannello e' gia' in memoria basta avvisarlo ---
# Niente import di Qt qui: un click deve costare pochi millisecondi.
if "--screenshot" not in sys.argv:
    try:
        with open(r"\\.\pipe\%s" % PIPE_NAME, "wb", buffering=0) as pipe:
            # Il processo lanciato dal click ha il diritto di portare una
            # finestra in primo piano: lo cede al pannello gia' aperto.
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
            pipe.write(b"toggle\n")
        sys.exit(0)
    except OSError:
        pass

import os
import re
import json
import time
import socket
import struct
import asyncio
import logging
import threading
import winreg
import collections
from ctypes import wintypes as wt
from xml.sax.saxutils import escape

import psutil
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRectF, QPoint, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QCursor, QPixmap, QImage, QGuiApplication
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton,
    QLineEdit, QScrollArea, QFrame, QGraphicsOpacityEffect, QSizePolicy,
)

logging.basicConfig(
    filename=os.path.join(os.environ.get("TEMP", "."), "wifi-panel.log"),
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
)

FONT = "JetBrainsMono NFP"
WIDTH = 400

# Glifi della barra di Omarchy (Model.js: wifiIconFor / connectionIcon)
WIFI_ICONS = ["\U000F092F", "\U000F091F", "\U000F0922", "\U000F0925", "\U000F0928"]
WIFI_OFF = "\U000F092E"
ICON_QR = "\U000F0432"
ICON_SPEED = "\U000F04C5"
ICON_LOCK = "\U000F033E"
ICON_FORGET = "\U000F0159"

PHRASES = ["Wiring bits", "Handling packets", "Sorting frames", "Hauling bytes",
           "Routing crumbs", "Counting collisions", "Bending light"]

DNS_PRESETS = {"Cloudflare": ["1.1.1.1", "1.0.0.1"], "Google": ["8.8.8.8", "8.8.4.4"]}


def wifi_icon(strength):
    return WIFI_ICONS[max(0, min(4, -(-int(strength) // 20) - 1))]


# =====================================================================
#  API Wi-Fi native di Windows (wlanapi.dll)
# =====================================================================

class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]

    def __str__(self):
        d4 = bytes(self.Data4)
        return "{%08X-%04X-%04X-%s-%s}" % (self.Data1, self.Data2, self.Data3, d4[:2].hex().upper(), d4[2:].hex().upper())


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("guid", GUID), ("desc", ctypes.c_wchar * 256), ("state", ctypes.c_uint)]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("n", wt.DWORD), ("idx", wt.DWORD), ("items", WLAN_INTERFACE_INFO * 1)]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ulong), ("ssid", ctypes.c_char * 32)]


class WLAN_AVAILABLE_NETWORK(ctypes.Structure):
    _fields_ = [("profile", ctypes.c_wchar * 256), ("ssid", DOT11_SSID), ("bsstype", ctypes.c_uint),
                ("nbss", ctypes.c_ulong), ("connectable", wt.BOOL), ("reason", wt.DWORD),
                ("nphy", ctypes.c_ulong), ("phy", ctypes.c_uint * 8), ("morephy", wt.BOOL),
                ("quality", ctypes.c_ulong), ("secure", wt.BOOL), ("auth", ctypes.c_uint),
                ("cipher", ctypes.c_uint), ("flags", wt.DWORD), ("reserved", wt.DWORD)]


class WLAN_AVAILABLE_NETWORK_LIST(ctypes.Structure):
    _fields_ = [("n", wt.DWORD), ("idx", wt.DWORD), ("items", WLAN_AVAILABLE_NETWORK * 1)]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("ssid", DOT11_SSID), ("bsstype", ctypes.c_uint), ("bssid", ctypes.c_ubyte * 6),
                ("phy", ctypes.c_uint), ("phyidx", ctypes.c_ulong), ("quality", ctypes.c_ulong),
                ("rx", ctypes.c_ulong), ("tx", ctypes.c_ulong)]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("secure", wt.BOOL), ("onex", wt.BOOL), ("auth", ctypes.c_uint), ("cipher", ctypes.c_uint)]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("state", ctypes.c_uint), ("mode", ctypes.c_uint), ("profile", ctypes.c_wchar * 256),
                ("assoc", WLAN_ASSOCIATION_ATTRIBUTES), ("sec", WLAN_SECURITY_ATTRIBUTES)]


class WLAN_RATE_SET(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ulong), ("rates", ctypes.c_ushort * 126)]


class WLAN_BSS_ENTRY(ctypes.Structure):
    _fields_ = [("ssid", DOT11_SSID), ("phyid", ctypes.c_ulong), ("bssid", ctypes.c_ubyte * 6),
                ("bsstype", ctypes.c_uint), ("bssphy", ctypes.c_uint), ("rssi", ctypes.c_long),
                ("quality", ctypes.c_ulong), ("inreg", ctypes.c_ubyte), ("beacon", ctypes.c_ushort),
                ("ts", ctypes.c_ulonglong), ("hts", ctypes.c_ulonglong), ("cap", ctypes.c_ushort),
                ("freq", ctypes.c_ulong), ("rateset", WLAN_RATE_SET), ("ieoff", ctypes.c_ulong),
                ("iesize", ctypes.c_ulong)]


class WLAN_BSS_LIST(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("n", wt.DWORD), ("items", WLAN_BSS_ENTRY * 1)]


class NDIS_OBJECT_HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ubyte), ("revision", ctypes.c_ubyte), ("size", ctypes.c_ushort)]


def bssid_list_type(count):
    class DOT11_BSSID_LIST(ctypes.Structure):
        _fields_ = [("header", NDIS_OBJECT_HEADER), ("n", ctypes.c_ulong), ("total", ctypes.c_ulong),
                    ("bssids", (ctypes.c_ubyte * 6) * count)]
    return DOT11_BSSID_LIST


class WLAN_CONNECTION_PARAMETERS(ctypes.Structure):
    _fields_ = [("mode", ctypes.c_uint), ("profile", ctypes.c_wchar_p), ("ssid", ctypes.POINTER(DOT11_SSID)),
                ("bssids", ctypes.c_void_p), ("bsstype", ctypes.c_uint), ("flags", wt.DWORD)]


# dot11DefaultAuthAlgorithm -> come scriverlo nel profilo XML
AUTH_OPEN, AUTH_WPA_PSK, AUTH_RSNA_PSK, AUTH_WPA3_SAE, AUTH_OWE = 1, 4, 7, 9, 10
AUTH_ENTERPRISE = {3, 6, 8, 11}


def band_of(freq_khz):
    if freq_khz < 3_000_000:
        return "2.4"
    return "5" if freq_khz < 5_925_000 else "6"


class Wlan:
    def __init__(self):
        self.dll = ctypes.WinDLL("wlanapi")
        self.handle = wt.HANDLE()
        ver = wt.DWORD()
        if self.dll.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(self.handle)):
            raise OSError("WlanOpenHandle fallita")
        self.guid = None
        self.alias = ""
        self.refresh_interface()

    def _items(self, ptr, typ):
        return ctypes.cast(ctypes.byref(ptr.contents.items), ctypes.POINTER(typ * ptr.contents.n)).contents

    def refresh_interface(self):
        lst = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
        if self.dll.WlanEnumInterfaces(self.handle, None, ctypes.byref(lst)) or lst.contents.n == 0:
            self.guid = None
            return
        info = self._items(lst, WLAN_INTERFACE_INFO)[0]
        self.guid = GUID.from_buffer_copy(info.guid)
        self.dll.WlanFreeMemory(lst)
        try:
            key = r"SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}\%s\Connection"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key % self.guid) as k:
                self.alias = winreg.QueryValueEx(k, "Name")[0]
        except OSError:
            self.alias = ""

    def current(self):
        """Rete a cui e' associata la scheda, o None."""
        if not self.guid:
            return None
        size, data, vt = wt.DWORD(), ctypes.c_void_p(), ctypes.c_uint()
        if self.dll.WlanQueryInterface(self.handle, ctypes.byref(self.guid), 7, None,
                                       ctypes.byref(size), ctypes.byref(data), ctypes.byref(vt)):
            return None
        c = ctypes.cast(data, ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES)).contents
        res = None
        if c.state == 1:  # wlan_interface_state_connected
            a = c.assoc
            res = {"ssid": a.ssid.ssid[:a.ssid.len].decode("utf-8", "replace"), "profile": c.profile,
                   "quality": a.quality, "rx": a.rx // 1000, "bssid": bytes(a.bssid)}
        self.dll.WlanFreeMemory(data)
        return res

    def scan(self):
        if self.guid:
            self.dll.WlanScan(self.handle, ctypes.byref(self.guid), None, None, None)

    def bss(self):
        """Tutti gli access point visti: [(ssid, bssid, banda, qualita')]."""
        if not self.guid:
            return []
        lst = ctypes.POINTER(WLAN_BSS_LIST)()
        if self.dll.WlanGetNetworkBssList(self.handle, ctypes.byref(self.guid), None, 3, False, None, ctypes.byref(lst)):
            return []
        out = [(b.ssid.ssid[:b.ssid.len].decode("utf-8", "replace"), bytes(b.bssid), band_of(b.freq), b.quality)
               for b in self._items(lst, WLAN_BSS_ENTRY)]
        self.dll.WlanFreeMemory(lst)
        return out

    def networks(self):
        """Reti visibili, una per SSID, con il profilo salvato se c'e'."""
        if not self.guid:
            return []
        lst = ctypes.POINTER(WLAN_AVAILABLE_NETWORK_LIST)()
        if self.dll.WlanGetAvailableNetworkList(self.handle, ctypes.byref(self.guid), 0, None, ctypes.byref(lst)):
            return []
        nets = {}
        for n in self._items(lst, WLAN_AVAILABLE_NETWORK):
            ssid = n.ssid.ssid[:n.ssid.len].decode("utf-8", "replace")
            if not ssid:
                continue
            item = nets.setdefault(ssid, {"ssid": ssid, "profile": "", "signal": 0, "secure": bool(n.secure),
                                          "auth": n.auth, "connected": False})
            item["signal"] = max(item["signal"], n.quality)
            if n.profile:
                item["profile"] = n.profile
            if n.flags & 1:
                item["connected"] = True
        self.dll.WlanFreeMemory(lst)
        return list(nets.values())

    def _ssid(self, ssid):
        raw = ssid.encode("utf-8")[:32]
        s = DOT11_SSID()
        s.len = len(raw)
        s.ssid = raw
        return s

    def connect(self, profile, ssid, bssids=None):
        p = WLAN_CONNECTION_PARAMETERS()
        p.mode = 0  # wlan_connection_mode_profile
        p.profile = profile
        s = self._ssid(ssid)
        p.ssid = ctypes.pointer(s)
        p.bsstype = 1  # infrastructure
        lst = None
        if bssids:
            T = bssid_list_type(len(bssids))
            lst = T()
            lst.header = NDIS_OBJECT_HEADER(0x80, 1, ctypes.sizeof(T))
            lst.n = lst.total = len(bssids)
            for i, b in enumerate(bssids):
                lst.bssids[i] = (ctypes.c_ubyte * 6)(*b)
            p.bssids = ctypes.cast(ctypes.pointer(lst), ctypes.c_void_p)
        return self.dll.WlanConnect(self.handle, ctypes.byref(self.guid), ctypes.byref(p), None)

    def disconnect(self):
        return self.dll.WlanDisconnect(self.handle, ctypes.byref(self.guid), None)

    def set_profile(self, ssid, auth, password):
        if auth == AUTH_OPEN:
            security = "<authEncryption><authentication>open</authentication><encryption>none</encryption>" \
                       "<useOneX>false</useOneX></authEncryption>"
        elif auth == AUTH_OWE:
            security = "<authEncryption><authentication>OWE</authentication><encryption>AES</encryption>" \
                       "<useOneX>false</useOneX></authEncryption>"
        else:
            method = {AUTH_WPA_PSK: "WPAPSK", AUTH_WPA3_SAE: "WPA3SAE"}.get(auth, "WPA2PSK")
            cipher = "TKIP" if auth == AUTH_WPA_PSK else "AES"
            security = ("<authEncryption><authentication>%s</authentication><encryption>%s</encryption>"
                        "<useOneX>false</useOneX></authEncryption><sharedKey><keyType>passPhrase</keyType>"
                        "<protected>false</protected><keyMaterial>%s</keyMaterial></sharedKey>"
                        % (method, cipher, escape(password)))
        xml = ('<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
               "<name>%s</name><SSIDConfig><SSID><name>%s</name></SSID></SSIDConfig>"
               "<connectionType>ESS</connectionType><connectionMode>auto</connectionMode>"
               "<MSM><security>%s</security></MSM></WLANProfile>" % (escape(ssid), escape(ssid), security))
        reason = wt.DWORD()
        return self.dll.WlanSetProfile(self.handle, ctypes.byref(self.guid), 0, xml, None, True, None, ctypes.byref(reason))

    def delete_profile(self, profile):
        return self.dll.WlanDeleteProfile(self.handle, ctypes.byref(self.guid), profile, None)

    def password(self, profile):
        xml, flags, access = ctypes.c_wchar_p(), wt.DWORD(4), wt.DWORD()  # 4 = chiave in chiaro
        if self.dll.WlanGetProfile(self.handle, ctypes.byref(self.guid), profile, None,
                                   ctypes.byref(xml), ctypes.byref(flags), ctypes.byref(access)):
            return None
        m = re.search(r"<protected>false</protected>\s*<keyMaterial>([^<]*)</keyMaterial>", xml.value or "")
        return m.group(1) if m else ""


# =====================================================================
#  Statistiche: ping, traffico, IP, gateway, DNS, radio
# =====================================================================

class Pinger(threading.Thread):
    """Un ping al secondo verso 1.1.1.1 (IcmpSendEcho, niente console)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.results = collections.deque(maxlen=20)
        self.active = threading.Event()
        self.icmp = ctypes.WinDLL("iphlpapi")
        self.icmp.IcmpCreateFile.restype = wt.HANDLE
        self.icmp.IcmpSendEcho.argtypes = [wt.HANDLE, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ushort,
                                          ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, wt.DWORD]

    def run(self):
        handle = self.icmp.IcmpCreateFile()
        dest = struct.unpack("<I", socket.inet_aton("1.1.1.1"))[0]
        payload = ctypes.create_string_buffer(b"windowsarchy" * 2)
        reply = ctypes.create_string_buffer(256)
        while True:
            self.active.wait()
            start = time.monotonic()
            ok = self.icmp.IcmpSendEcho(handle, dest, payload, len(payload) - 1, None, reply, len(reply), 1000)
            status, rtt = struct.unpack_from("<II", reply, 4)
            self.results.append(rtt if ok and status == 0 else None)
            time.sleep(max(0.0, 1.0 - (time.monotonic() - start)))

    def latest(self):
        ok = [r for r in self.results if r is not None]
        if not self.results:
            return None, None
        last = next((r for r in reversed(self.results) if r is not None), None)
        return last, round(100 * (len(self.results) - len(ok)) / len(self.results))


def tcpip_info(guid):
    out = {"gateway": "", "dns_static": [], "dns": []}
    try:
        key = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\%s" % guid
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
            def val(name):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except OSError:
                    return ""
            gw = val("DefaultGateway") or val("DhcpDefaultGateway")
            gw = [g for g in (gw if isinstance(gw, list) else [gw]) if g]
            out["gateway"] = gw[0] if gw else ""
            out["dns_static"] = re.split(r"[ ,]+", val("NameServer").strip()) if val("NameServer").strip() else []
            out["dns"] = out["dns_static"] or re.split(r"[ ,]+", val("DhcpNameServer").strip())
    except OSError:
        pass
    return out


def human_rate(bps):
    if bps < 1024:
        return "%d B/s" % bps
    if bps < 1024 ** 2:
        return "%.1f KB/s" % (bps / 1024)
    return "%.1f MB/s" % (bps / 1024 ** 2)


def human_bytes(n):
    for unit, size in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= size:
            return "%.1f %s" % (n / size, unit)
    return "%d B" % n


def radio_state(turn_on=None):
    """Legge (o imposta) la radio Wi-Fi via WinRT. None se non c'e'."""
    from winrt.windows.devices.radios import Radio, RadioKind, RadioState

    async def run():
        await Radio.request_access_async()
        for r in await Radio.get_radios_async():
            if r.kind == RadioKind.WI_FI:
                if turn_on is not None:
                    await r.set_state_async(RadioState.ON if turn_on else RadioState.OFF)
                    return turn_on
                return r.state == RadioState.ON
        return None
    try:
        return asyncio.run(run())
    except Exception:
        logging.exception("radio")
        return None


def run_elevated_powershell(command):
    # Cambiare i DNS richiede l'amministratore: Windows mostra l'UAC.
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe",
                                        '-NoProfile -WindowStyle Hidden -Command "%s"' % command, None, 0)


# =====================================================================
#  Tema: colori dal tema Windowsarchy attivo
# =====================================================================

def load_theme():
    base = os.path.join(os.path.expanduser("~"), ".config", "windowsarchy")
    palette = {"bg": "#1F1F28", "surface": "#363646", "text": "#DCD7BA", "subtext": "#C8C093", "accent": "#DCD7BA"}
    radius = 6
    try:
        with open(os.path.join(base, "current-theme"), encoding="utf-8") as f:
            name = f.read().strip()
        with open(os.path.join(base, "themes", name, "theme.json"), encoding="utf-8") as f:
            palette.update(json.load(f).get("palette", {}))
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(os.path.expanduser("~"), ".config", "yasb", "styles.css"), encoding="utf-8") as f:
            m = re.search(r"--border-radius:\s*(\d+)", f.read())
            if m:
                radius = int(m.group(1))
    except OSError:
        pass
    fg = QColor(palette["text"])
    return {
        "bg": QColor(palette["bg"]), "fg": fg, "accent": QColor(palette["accent"]),
        "dim": fg.darker(140), "faint": fg.darker(150), "urgent": QColor("#E46876"), "radius": radius,
    }


def rgba(c, alpha):
    return "rgba(%d,%d,%d,%.2f)" % (c.red(), c.green(), c.blue(), alpha)


# =====================================================================
#  Elementi grafici
# =====================================================================

def make_font(size, bold=False, spacing=0.0):
    f = QFont(FONT)
    f.setPixelSize(size)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


class Label(QLabel):
    def __init__(self, text="", size=12, color=None, bold=False, spacing=0.0, align=None):
        super().__init__(text)
        self.setFont(make_font(size, bold, spacing))
        if color is not None:
            self.set_color(color)
        if align is not None:
            self.setAlignment(align)

    def set_color(self, color):
        self.setStyleSheet("color: %s; background: transparent;" % color.name())


class SectionHeader(Label):
    def __init__(self, text, theme):
        super().__init__(text.upper(), 10, theme["dim"], bold=True, spacing=1.2)


class Separator(QFrame):
    def __init__(self, theme):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet("background: %s;" % rgba(theme["fg"], 0.14))


class Switch(QWidget):
    """Interruttore squadrato come quello dei pannelli di Omarchy."""

    def __init__(self, theme, w, h, on_toggle):
        super().__init__()
        self.theme, self.on, self.on_toggle = theme, False, on_toggle
        self.setFixedSize(w, h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_on(self, on):
        self.on = bool(on)
        self.update()

    def mousePressEvent(self, e):
        self.on_toggle(not self.on)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg, r = self.theme["fg"], min(self.theme["radius"], self.height() / 2)
        p.setPen(QPen(fg if self.on else self.theme["faint"], 1))
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), r, r)
        pad = 3
        k = self.height() - 2 * pad
        x = self.width() - pad - k if self.on else pad
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fg if self.on else self.theme["faint"])
        p.drawRoundedRect(QRectF(x, pad, k, k), max(0, r - pad), max(0, r - pad))


class IconButton(QPushButton):
    def __init__(self, glyph, theme, tooltip, on_click):
        super().__init__(glyph)
        self.setFont(make_font(16))
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(28, 28)
        self.setStyleSheet(
            "QPushButton { color: %s; background: transparent; border: none; border-radius: %dpx; }"
            "QPushButton:hover { background: %s; }" % (theme["fg"].name(), theme["radius"], rgba(theme["fg"], 0.12)))
        self.clicked.connect(on_click)


class Pill(QPushButton):
    def __init__(self, text, theme, on_click):
        super().__init__(text)
        self.theme = theme
        self.setFont(make_font(12))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.clicked.connect(on_click)
        self.set_selected(False)

    def set_selected(self, selected):
        t = self.theme
        self.setStyleSheet(
            "QPushButton { color: %s; background: %s; border: 1px solid %s; border-radius: %dpx; padding: 0 8px; }"
            "QPushButton:hover { background: %s; }" % (
                t["fg"].name(), rgba(t["fg"], 0.16) if selected else "transparent",
                t["fg"].name() if selected else rgba(t["fg"], 0.35), t["radius"], rgba(t["fg"], 0.12)))


class NetworkRow(QWidget):
    def __init__(self, panel, net):
        super().__init__()
        self.panel, self.theme = panel, panel.theme
        self.net, self.status, self.failed, self.hover = net, "", False, False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(10)
        outer.addLayout(row)

        self.icon = Label("", 14)
        self.icon.setFixedWidth(18)
        row.addWidget(self.icon)
        info = QVBoxLayout()
        info.setSpacing(1)
        self.name = Label("", 12, self.theme["fg"])
        self.sub = Label("", 10)
        info.addWidget(self.name)
        info.addWidget(self.sub)
        row.addLayout(info, 1)
        self.right = Label("", 13, align=Qt.AlignmentFlag.AlignCenter)
        self.right.setFixedWidth(22)
        row.addWidget(self.right)

        # Riga della password, solo per le reti protette mai usate
        self.pw_box = QWidget()
        pw = QHBoxLayout(self.pw_box)
        pw.setContentsMargins(28, 0, 0, 0)
        pw.setSpacing(6)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setPlaceholderText("Passphrase")
        self.pw.setFont(make_font(12))
        self.pw.setFixedHeight(28)
        self.pw.setStyleSheet(
            "QLineEdit { color: %s; background: transparent; border: 1px solid %s; border-radius: %dpx; padding: 0 6px; }"
            % (self.theme["fg"].name(), rgba(self.theme["fg"], 0.35), self.theme["radius"]))
        self.pw.returnPressed.connect(self.submit_password)
        go = IconButton("\U000F0054", self.theme, "Connect", self.submit_password)
        pw.addWidget(self.pw, 1)
        pw.addWidget(go)
        outer.addWidget(self.pw_box)
        self.pw_box.hide()
        self.update_net(net)

    def update_net(self, net):
        self.net = net
        connected = net["connected"]
        color = self.theme["urgent"] if self.failed else (self.theme["fg"] if connected or self.status else self.theme["faint"])
        self.icon.setText(wifi_icon(net["signal"]))
        self.icon.set_color(color)
        self.name.setText(net["ssid"])
        text = self.status or ("Connected" if connected else "")
        self.sub.setText(text)
        self.sub.set_color(color)
        self.sub.setVisible(bool(text))
        forget = self.hover and bool(net["profile"])
        self.right.setText(ICON_FORGET if forget else (ICON_LOCK if net["secure"] else ""))
        self.right.set_color(self.theme["urgent"] if forget else self.theme["dim"])
        self.right.setToolTip("Forget network" if forget else "")
        self.update()

    def set_status(self, text, failed=False):
        self.status, self.failed = text, failed
        self.update_net(self.net)

    def enterEvent(self, e):
        self.hover = True
        self.panel.select_row(self)
        self.update_net(self.net)

    def leaveEvent(self, e):
        self.hover = False
        self.update_net(self.net)

    def paintEvent(self, e):
        if self.panel.selected is self:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.theme["fg"].red(), self.theme["fg"].green(), self.theme["fg"].blue(), 30))
            r = self.theme["radius"]
            p.drawRoundedRect(QRectF(self.rect()), r, r)

    def mousePressEvent(self, e):
        if self.hover and self.net["profile"] and self.right.geometry().adjusted(-6, -6, 6, 6).contains(e.position().toPoint()):
            self.panel.forget(self)
        else:
            self.panel.activate_row(self)

    def submit_password(self):
        if self.pw.text():
            self.panel.connect_new(self, self.pw.text())


# =====================================================================
#  Il pannello
# =====================================================================

class Panel(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self.wlan = Wlan()
        self.pinger = Pinger()
        self.pinger.start()
        self.rows, self.selected, self.pending = {}, None, None
        self.band_auto, self.band_pin = True, None
        self.last_io, self.rates = None, (0, 0)
        self.hidden_by_click = (0.0, QPoint())
        self.radio_on = True
        self.phrase_index = 1
        self.theme = None
        self.build()

        self.fast = QTimer(self, interval=1000, timeout=self.refresh_stats)
        self.slow = QTimer(self, interval=5000, timeout=self.refresh_networks)
        self.scanner = QTimer(self, interval=15000, timeout=self.start_scan)
        self.watch = QTimer(self, interval=40, timeout=self.watch_outside_click)
        self.phrase_timer = QTimer(self, interval=2800, timeout=self.next_phrase)

    # ---------- costruzione ----------
    def build(self):
        self.theme = t = load_theme()
        if self.layout():
            QWidget().setLayout(self.layout())  # butta via il layout vecchio (cambio tema)
        self.rows, self.selected = {}, None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(12)

        # Intestazione: icona, SSID + frase, azioni
        hero = QHBoxLayout()
        hero.setSpacing(14)
        self.hero_icon = Label(WIFI_ICONS[4], 24, t["fg"])
        hero.addWidget(self.hero_icon)
        labels = QVBoxLayout()
        labels.setSpacing(2)
        self.hero_ssid = Label("", 14, t["fg"], bold=True)
        self.hero_meta = Label("", 10, t["dim"], bold=True, spacing=1.2)
        self.meta_fx = QGraphicsOpacityEffect(self.hero_meta)
        self.hero_meta.setGraphicsEffect(self.meta_fx)
        labels.addWidget(self.hero_ssid)
        labels.addWidget(self.hero_meta)
        hero.addLayout(labels, 1)
        hero.addWidget(IconButton(ICON_QR, t, "Show QR code", self.show_qr))
        hero.addWidget(IconButton(ICON_SPEED, t, "Run a speed test", lambda: os.startfile("https://www.speedtest.net/")))
        hero.addSpacing(6)
        self.radio_switch = Switch(t, 34, 20, self.toggle_radio)
        hero.addWidget(self.radio_switch)
        root.addLayout(hero)

        # Statistiche, due colonne di coppie etichetta/valore
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.stats = {}
        names = [("Ping", "Packet Loss"), ("Receiving", "Sending"), ("Downloaded", "Uploaded"), ("IP Address", "Gateway")]
        for r, pair in enumerate(names):
            for c, name in enumerate(pair):
                grid.addWidget(Label(name, 12, t["dim"]), r, c * 2)
                value = Label("--", 12, t["fg"], align=Qt.AlignmentFlag.AlignRight)
                grid.addWidget(value, r, c * 2 + 1)
                if c == 0:
                    value.setContentsMargins(0, 0, 12, 0)
                self.stats[name] = value
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnMinimumWidth(1, 96)
        root.addLayout(grid)
        root.addWidget(Separator(t))

        # Banda
        band = QHBoxLayout()
        self.band_label = SectionHeader("Wi-Fi band", t)
        band.addWidget(self.band_label, 1)
        band.addWidget(SectionHeader("Automatic", t))
        band.addSpacing(6)
        self.band_switch = Switch(t, 22, 12, self.toggle_band_auto)
        band.addWidget(self.band_switch)
        root.addLayout(band)
        self.band_pills_box = QWidget()
        self.band_pills = QHBoxLayout(self.band_pills_box)
        self.band_pills.setContentsMargins(0, 0, 0, 0)
        self.band_pills.setSpacing(8)
        root.addWidget(self.band_pills_box)
        self.band_pills_box.hide()
        root.addWidget(Separator(t))

        # DNS
        root.addWidget(SectionHeader("DNS provider", t))
        dns = QHBoxLayout()
        dns.setSpacing(8)
        self.dns_pills = {}
        for name in ("DHCP", "Cloudflare", "Google", "Custom"):
            pill = Pill(name, t, lambda _=False, n=name: self.set_dns(n))
            dns.addWidget(pill)
            self.dns_pills[name] = pill
        root.addLayout(dns)
        self.dns_custom = QLineEdit()
        self.dns_custom.setPlaceholderText("1.1.1.1, 9.9.9.9  (Enter to apply)")
        self.dns_custom.setFont(make_font(12))
        self.dns_custom.setFixedHeight(28)
        self.dns_custom.setStyleSheet(
            "QLineEdit { color: %s; background: transparent; border: 1px solid %s; border-radius: %dpx; padding: 0 6px; }"
            % (t["fg"].name(), rgba(t["fg"], 0.35), t["radius"]))
        self.dns_custom.returnPressed.connect(self.apply_custom_dns)
        self.dns_custom.hide()
        root.addWidget(self.dns_custom)
        root.addWidget(Separator(t))

        # Reti
        self.scan_header = SectionHeader("Scanning Wi-Fi…", t)
        self.scan_header.hide()
        root.addWidget(self.scan_header)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.list_widget)
        self.scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: %s; min-height: 20px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }" % rgba(t["fg"], 0.3))
        root.addWidget(self.scroll)
        self.wifi_off_label = Label("Wi-Fi is off", 12, t["dim"])
        self.wifi_off_label.hide()
        root.addWidget(self.wifi_off_label)

        # Vista del QR (sostituisce il contenuto finche' non si clicca)
        self.qr_view = QWidget(self)
        self.qr_view.hide()

    # ---------- disegno della cornice ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self.theme["bg"])
        bg.setAlphaF(0.96)
        p.setBrush(bg)
        p.setPen(QPen(self.theme["accent"], 1))
        r = self.theme["radius"]
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), r, r)

    # ---------- apertura / chiusura ----------
    def toggle(self):
        if self.isVisible():
            self.hide_panel()
            return
        when, where = self.hidden_by_click
        # Il click sul widget ha gia' chiuso il pannello (click fuori): non riaprirlo
        if time.monotonic() - when < 1.5 and (QCursor.pos() - where).manhattanLength() < 40:
            return
        self.show_panel()

    def show_panel(self, at=None):
        theme = load_theme()
        if theme != self.theme:
            self.build()
        self.radio_on = radio_state() is not False
        self.radio_switch.set_on(self.radio_on)
        self.last_io = None
        self.pinger.active.set()
        self.refresh_networks()
        self.refresh_stats()
        self.start_scan()
        for timer in (self.fast, self.slow, self.scanner, self.phrase_timer):
            timer.start()
        self.adjustSize()
        self.move(at if at is not None else self.anchor_position())
        self.show()
        self.raise_()
        self.activateWindow()
        ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        self.was_pressed = self.mouse_pressed()
        self.watch.start()

    def hide_panel(self):
        for timer in (self.fast, self.slow, self.scanner, self.watch, self.phrase_timer):
            timer.stop()
        self.pinger.active.clear()
        self.qr_view.hide()
        self.hide()

    def anchor_position(self):
        """Sotto il punto cliccato, appena sotto la barra di YASB."""
        user32 = ctypes.windll.user32
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio()
        geo = screen.geometry()
        hwnd = user32.GetAncestor(user32.WindowFromPoint(pt), 2)
        rect = wt.RECT()
        bottom = geo.top() + 40
        if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.bottom - rect.top < 120:
            bottom = int(rect.bottom / dpr)
        cur = QCursor.pos()
        x = max(geo.left() + 8, min(cur.x() - self.width() // 2, geo.right() - self.width() - 8))
        return QPoint(x, bottom + 6)

    def mouse_pressed(self):
        return any(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000 for vk in (1, 2, 4))

    def watch_outside_click(self):
        # Conta solo un click nuovo: il tasto puo' essere ancora giu' dal
        # click sul widget che ha aperto il pannello
        pressed, was = self.mouse_pressed(), self.was_pressed
        self.was_pressed = pressed
        if pressed and not was and not self.geometry().contains(QCursor.pos()):
            self.hidden_by_click = (time.monotonic(), QCursor.pos())
            self.hide_panel()

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key.Key_Escape:
            if self.qr_view.isVisible():
                self.qr_view.hide()
            else:
                self.hide_panel()
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_J, Qt.Key.Key_K):
            rows = self.ordered_rows()
            if rows:
                i = rows.index(self.selected) if self.selected in rows else -1
                step = 1 if key in (Qt.Key.Key_Down, Qt.Key.Key_J) else -1
                self.select_row(rows[max(0, min(len(rows) - 1, i + step))])
                self.scroll.ensureWidgetVisible(self.selected)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.selected:
            self.activate_row(self.selected)

    # ---------- aggiornamenti ----------
    def next_phrase(self):
        if not self.hero_meta.text() or self.hero_meta.text() == "NOT CONNECTED":
            return
        self.phrase_index = (self.phrase_index + 1) % len(PHRASES)
        out = QPropertyAnimation(self.meta_fx, b"opacity", self, duration=180, startValue=1.0, endValue=0.0)

        def swap():
            self.hero_meta.setText(PHRASES[self.phrase_index].upper())
            QPropertyAnimation(self.meta_fx, b"opacity", self, duration=260, startValue=0.0, endValue=1.0).start(
                QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        out.finished.connect(swap)
        out.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def start_scan(self):
        self.wlan.scan()
        self.scan_header.setVisible(self.radio_on)
        QTimer.singleShot(4000, self.after_scan)

    def after_scan(self):
        self.scan_header.hide()
        self.refresh_networks()

    def refresh_stats(self):
        cur = self.wlan.current() if self.radio_on else None
        t = self.theme
        if cur:
            self.hero_icon.setText(wifi_icon(cur["quality"]))
            self.hero_ssid.setText(cur["ssid"])
            if not self.hero_meta.text() or self.hero_meta.text() == "NOT CONNECTED":
                self.hero_meta.setText(PHRASES[self.phrase_index].upper())
        else:
            self.hero_icon.setText(WIFI_OFF if not self.radio_on else WIFI_ICONS[0])
            self.hero_ssid.setText("Disconnected")
            self.hero_meta.setText("NOT CONNECTED")
        self.hero_icon.set_color(t["fg"] if cur else t["dim"])

        ping, loss = self.pinger.latest()
        self.stats["Ping"].setText("%d ms" % ping if ping is not None else "--")
        self.stats["Packet Loss"].setText("%d%%" % loss if loss is not None else "--")

        io = psutil.net_io_counters(pernic=True).get(self.wlan.alias)
        now = time.monotonic()
        if io:
            if self.last_io:
                dt = max(0.1, now - self.last_io[0])
                self.rates = ((io.bytes_recv - self.last_io[1].bytes_recv) / dt,
                              (io.bytes_sent - self.last_io[1].bytes_sent) / dt)
                self.stats["Receiving"].setText(human_rate(self.rates[0]))
                self.stats["Sending"].setText(human_rate(self.rates[1]))
            self.last_io = (now, io)
            self.stats["Downloaded"].setText(human_bytes(io.bytes_recv))
            self.stats["Uploaded"].setText(human_bytes(io.bytes_sent))
        ip = ""
        for a in psutil.net_if_addrs().get(self.wlan.alias, []):
            if a.family == socket.AF_INET:
                ip = a.address
        tcp = tcpip_info(self.wlan.guid) if self.wlan.guid else {"gateway": "", "dns_static": []}
        self.stats["IP Address"].setText(ip if cur and ip else "--")
        self.stats["Gateway"].setText(tcp["gateway"] if cur and tcp["gateway"] else "--")
        self.update_dns(tcp["dns_static"])
        self.update_band(cur)

    def update_dns(self, static):
        current = "DHCP"
        if static:
            current = next((n for n, ips in DNS_PRESETS.items() if static[:len(ips)] == ips), "Custom")
        for name, pill in self.dns_pills.items():
            pill.set_selected(name == current)

    def update_band(self, cur):
        aps = [b for b in self.wlan.bss() if cur and b[0] == cur["ssid"]]
        now = next((b[2] for b in aps if b[1] == cur["bssid"]), None) if cur else None
        self.band_label.setText(("WI-FI BAND: %sGHZ" % now) if now else "WI-FI BAND")
        self.band_switch.set_on(self.band_auto)
        bands = sorted({b[2] for b in aps}, key=float)
        shown = [self.band_pills.itemAt(i).widget().text() for i in range(self.band_pills.count())]
        wanted = ["%s GHz" % b for b in bands]
        if shown != wanted:
            while self.band_pills.count():
                self.band_pills.takeAt(0).widget().deleteLater()
            for b in bands:
                self.band_pills.addWidget(Pill("%s GHz" % b, self.theme, lambda _=False, x=b: self.pin_band(x)))
        for i in range(self.band_pills.count()):
            pill = self.band_pills.itemAt(i).widget()
            pill.set_selected(pill.text() == "%s GHz" % (self.band_pin or now))
        visible = not self.band_auto and bool(bands)
        if visible == self.band_pills_box.isHidden():
            self.band_pills_box.setVisible(visible)
            self.adjustSize()

    def refresh_networks(self):
        nets = self.wlan.networks() if self.radio_on else []
        self.scroll.setVisible(self.radio_on)
        self.wifi_off_label.setVisible(not self.radio_on)
        known = sorted([n for n in nets if n["profile"]], key=lambda n: (not n["connected"], -n["signal"]))
        other = sorted([n for n in nets if not n["profile"]], key=lambda n: -n["signal"])
        layout_key = [("K", n["ssid"]) for n in known] + [("O", n["ssid"]) for n in other]
        if getattr(self, "_layout_key", None) == layout_key or any(r.pw_box.isVisible() for r in self.rows.values()):
            for n in nets:
                if n["ssid"] in self.rows:
                    self.rows[n["ssid"]].update_net(n)
            self.fit_list()
            return
        self._layout_key = layout_key
        selected_ssid = self.selected.net["ssid"] if self.selected else None
        old = self.rows
        while self.list_layout.count():
            w = self.list_layout.takeAt(0).widget()
            if w is not None and w not in old.values():
                w.deleteLater()
        self.rows = {}
        for title, group in (("Known networks", known), ("Other networks", other)):
            if not group:
                continue
            self.list_layout.addWidget(SectionHeader(title, self.theme))
            for n in group:
                row = old.pop(n["ssid"], None) or NetworkRow(self, n)
                row.update_net(n)
                self.rows[n["ssid"]] = row
                self.list_layout.addWidget(row)
        for row in old.values():
            row.deleteLater()
        self.list_layout.addStretch(1)
        rows = self.ordered_rows()
        self.selected = self.rows.get(selected_ssid) or (rows[0] if rows else None)
        self.fit_list()

    def fit_list(self):
        # La lista cresce con le reti fino a 260px, poi scorre
        self.list_layout.activate()
        height = min(self.list_layout.sizeHint().height(), 260)
        if self.scroll.height() != height:
            self.scroll.setFixedHeight(height)
            self.adjustSize()

    def ordered_rows(self):
        return [self.list_layout.itemAt(i).widget() for i in range(self.list_layout.count())
                if isinstance(self.list_layout.itemAt(i).widget(), NetworkRow)]

    def select_row(self, row):
        old, self.selected = self.selected, row
        for r in (old, row):
            if r is not None:
                r.update()

    # ---------- azioni ----------
    def activate_row(self, row):
        net = row.net
        if net["connected"]:
            row.set_status("Disconnecting…")
            self.wlan.disconnect()
            QTimer.singleShot(1500, lambda: (row.set_status(""), self.refresh_networks()))
        elif net["profile"]:
            row.set_status("Connecting…")
            self.wlan.connect(net["profile"], net["ssid"])
            self.wait_connection(row, created=False)
        elif net["auth"] in AUTH_ENTERPRISE:
            os.startfile("ms-availablenetworks:")  # 802.1X: meglio il pannello di Windows
        elif net["secure"] and net["auth"] != AUTH_OWE:
            for r in self.rows.values():
                if r is not row:
                    r.pw_box.hide()
            row.pw_box.setVisible(not row.pw_box.isVisible())
            self.fit_list()
            if row.pw_box.isVisible():
                row.pw.setFocus()
        else:
            self.connect_new(row, "")

    def connect_new(self, row, password):
        net = row.net
        if self.wlan.set_profile(net["ssid"], net["auth"], password):
            row.set_status("Failed", failed=True)
            return
        row.pw_box.hide()
        row.pw.clear()
        row.set_status("Connecting…")
        self.wlan.connect(net["ssid"], net["ssid"])
        self.wait_connection(row, created=True)

    def wait_connection(self, row, created, started=None):
        started = started or time.monotonic()
        cur = self.wlan.current()
        if cur and cur["ssid"] == row.net["ssid"]:
            row.set_status("")
            self.refresh_networks()
            return
        if time.monotonic() - started > 20:
            if created:
                self.wlan.delete_profile(row.net["ssid"])
            row.set_status("Wrong password" if created and row.net["secure"] else "Connection failed", failed=True)
            QTimer.singleShot(4000, lambda: row.set_status(""))
            return
        QTimer.singleShot(500, lambda: self.wait_connection(row, created, started))

    def forget(self, row):
        row.set_status("Forgetting…")
        self.wlan.delete_profile(row.net["profile"])
        QTimer.singleShot(800, lambda: (row.set_status(""), self.refresh_networks()))

    def toggle_radio(self, on):
        result = radio_state(on)
        if result is None:
            return
        self.radio_on = result
        self.radio_switch.set_on(result)
        QTimer.singleShot(1500, lambda: (self.refresh_networks(), self.refresh_stats(), self.adjustSize()))

    def toggle_band_auto(self, on):
        self.band_auto = on
        if on and self.band_pin:
            # Torna libero: riconnette senza vincoli sugli access point
            self.band_pin = None
            cur = self.wlan.current()
            if cur:
                self.wlan.connect(cur["profile"], cur["ssid"])
        self.update_band(self.wlan.current())

    def pin_band(self, band):
        cur = self.wlan.current()
        if not cur:
            return
        bssids = [b[1] for b in sorted(self.wlan.bss(), key=lambda b: -b[3]) if b[0] == cur["ssid"] and b[2] == band]
        if bssids:
            self.band_pin = band
            self.wlan.connect(cur["profile"], cur["ssid"], bssids)
            QTimer.singleShot(3000, self.refresh_stats)
        self.update_band(cur)

    def set_dns(self, name):
        alias = self.wlan.alias.replace("'", "''")
        if name == "Custom":
            self.dns_custom.setVisible(not self.dns_custom.isVisible())
            self.adjustSize()
            if self.dns_custom.isVisible():
                self.dns_custom.setFocus()
            return
        self.dns_custom.hide()
        if name == "DHCP":
            run_elevated_powershell("Set-DnsClientServerAddress -InterfaceAlias '%s' -ResetServerAddresses" % alias)
        else:
            run_elevated_powershell("Set-DnsClientServerAddress -InterfaceAlias '%s' -ServerAddresses %s"
                                    % (alias, ",".join(DNS_PRESETS[name])))
        self.adjustSize()

    def apply_custom_dns(self):
        ips = [ip for ip in re.split(r"[ ,;]+", self.dns_custom.text().strip()) if re.fullmatch(r"[0-9a-fA-F:.]+", ip)]
        if ips:
            run_elevated_powershell("Set-DnsClientServerAddress -InterfaceAlias '%s' -ServerAddresses %s"
                                    % (self.wlan.alias.replace("'", "''"), ",".join(ips)))
            self.dns_custom.hide()
            self.adjustSize()

    def show_qr(self):
        import qrcode
        cur = self.wlan.current()
        if not cur:
            return
        password = self.wlan.password(cur["profile"]) or ""

        def esc(s):
            return re.sub(r'([\\;,:"])', r"\\\1", s)
        kind = "WPA" if password else "nopass"
        qr = qrcode.QRCode(border=2, box_size=1)
        qr.add_data("WIFI:T:%s;S:%s;P:%s;;" % (kind, esc(cur["ssid"]), esc(password)))
        qr.make(fit=True)
        matrix = qr.get_matrix()
        size = len(matrix)
        img = QImage(size, size, QImage.Format.Format_RGB32)
        fg, bg = self.theme["fg"], self.theme["bg"]
        for y, line in enumerate(matrix):
            for x, dark in enumerate(line):
                img.setPixelColor(x, y, bg if dark else fg)
        side = WIDTH - 120
        pix = QPixmap.fromImage(img).scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)

        view = self.qr_view
        if view.layout():
            QWidget().setLayout(view.layout())
        lay = QVBoxLayout(view)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addStretch(1)
        image = QLabel()
        image.setPixmap(pix)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(image)
        lay.addWidget(Label(cur["ssid"], 14, self.theme["fg"], bold=True, align=Qt.AlignmentFlag.AlignCenter))
        lay.addWidget(Label("SCAN TO JOIN · CLICK TO GO BACK", 10, self.theme["dim"], bold=True, spacing=1.2,
                            align=Qt.AlignmentFlag.AlignCenter))
        lay.addStretch(1)
        view.setStyleSheet("background: transparent;")
        view.mousePressEvent = lambda e: view.hide()
        view.setGeometry(self.rect())
        view.setAutoFillBackground(False)
        view.paintEvent = lambda e: self._paint_qr_bg(view)
        view.show()
        view.raise_()

    def _paint_qr_bg(self, view):
        p = QPainter(view)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self.theme["bg"])
        p.setPen(QPen(self.theme["accent"], 1))
        r = self.theme["radius"]
        p.drawRoundedRect(QRectF(view.rect()).adjusted(0.5, 0.5, -0.5, -0.5), r, r)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    panel = Panel()

    if "--screenshot" in sys.argv:
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        panel.show_panel(QPoint(100, 100))

        def grab():
            panel.grab().save(out)
            app.quit()
        QTimer.singleShot(6000, grab)
        return app.exec()

    server = QLocalServer()
    QLocalServer.removeServer(PIPE_NAME)
    if not server.listen(PIPE_NAME):
        logging.error("pipe occupata: %s", server.errorString())
        return 1

    def on_client():
        sock = server.nextPendingConnection()
        if sock is None:
            return

        def read():
            if b"toggle" in bytes(sock.readAll()):
                panel.toggle()
            sock.disconnectFromServer()
        sock.readyRead.connect(read)
        if sock.bytesAvailable():
            read()
    server.newConnection.connect(on_client)
    panel.show_panel()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("wifi-panel")
        raise
