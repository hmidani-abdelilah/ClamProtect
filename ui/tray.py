from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPainter, QPixmap, QColor, QPen
from PyQt6.QtCore import Qt, QPointF, pyqtSignal


def _create_shield_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor("#27ae60"))
    painter.setPen(QPen(QColor("#1e8449"), 2))
    points = [
        (32, 8), (56, 16), (52, 40),
        (32, 56), (12, 40), (8, 16),
    ]
    polygon = [QPointF(*p) for p in points]
    from PyQt6.QtGui import QPolygonF
    painter.drawPolygon(QPolygonF(polygon))

    painter.setPen(QPen(QColor("white"), 3))
    painter.drawLine(22, 32, 28, 40)
    painter.drawLine(28, 40, 42, 24)
    painter.end()

    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    update_requested = pyqtSignal()
    cancel_scan_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(_create_shield_icon())
        self.setToolTip("ClamProtect — Antivirus Scanner")

        menu = QMenu()

        self.show_action = QAction("Show Window", self)
        menu.addAction(self.show_action)

        self.scan_action = QAction("Quick Scan", self)
        menu.addAction(self.scan_action)

        self.cancel_scan_action = QAction("Cancel Scan", self)
        self.cancel_scan_action.setEnabled(False)
        self.cancel_scan_action.triggered.connect(self.cancel_scan_requested.emit)
        menu.addAction(self.cancel_scan_action)

        self.update_action = QAction("Update Definitions", self)
        self.update_action.triggered.connect(self.update_requested.emit)
        menu.addAction(self.update_action)

        menu.addSeparator()

        self.quit_action = QAction("Quit", self)
        menu.addAction(self.quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def set_scanning(self, scanning):
        self.cancel_scan_action.setEnabled(scanning)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_action.trigger()

    def notify(self, title, message, icon=QSystemTrayIcon.MessageIcon.Information, duration=5000):
        if self.supportsMessages():
            self.showMessage(title, message, icon, duration)
