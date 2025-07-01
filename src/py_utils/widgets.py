import math
import time
from collections import deque

import psutil
from PySide6.QtCore import QObject, QPointF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from py_utils.misc import percent_to_rgb
from py_utils.process import GlobalCpuMonitor, cpu_monitor


class GlobalCpuMonitorSignals(QObject):
    updated = Signal(float, object)
    started = Signal()
    finished = Signal(bool, str)


class GlobalCpuMonitorThread(QThread):
    def __init__(self, interval: float = 0.5):
        super().__init__()
        self.signals = GlobalCpuMonitorSignals()
        cpu_monitor.interval = interval
        self.monitor = cpu_monitor
        self.monitor.add_handler_on("started", self.signals.started.emit)
        self.monitor.add_handler_on("updated", self.signals.updated.emit)
        self.monitor.add_handler_on("finished", self.signals.finished.emit)

    def run(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()


class GlobalCpuMonitorViewModel(QObject):

    def __init__(self, interval: float = 0.5):
        super().__init__()
        self._interval = interval
        self._thread: GlobalCpuMonitorThread | None = None
        self.signals = GlobalCpuMonitorSignals()

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, value: float):
        if self._interval == value:
            return
        self._interval = value
        if self._thread:
            self._thread.monitor.interval = value

    def start(self):
        if self._thread and self._thread.isRunning():
            return

        self._thread = GlobalCpuMonitorThread(self._interval)
        self._thread.signals.updated.connect(self.signals.updated.emit)
        self._thread.signals.finished.connect(self.signals.finished.emit)
        self._thread.start()

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread.wait()
            self._thread = None


class CompactGlobalCpuMonitorView(QWidget):
    def __init__(self, vm: GlobalCpuMonitorViewModel):
        super().__init__()
        self.vm = vm

        self.setup_ui()
        self.setup_signals()

    def setup_ui(self):
        layout = QHBoxLayout()
        self.setLayout(layout)

        self.label = QLabel("CPU: --.-%")
        layout.addWidget(self.label)

        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setMaximumHeight(12)
        layout.addWidget(self.meter)

        self.setToolTip("En attente de données...")

    def setup_signals(self):
        self.vm.signals.updated.connect(self.on_updated)
        self.vm.signals.finished.connect(lambda ok, msg: self.label.setText(f"CPU: {msg}"))

    def on_updated(self, _global: float, cores: list[float]):
        color = percent_to_rgb(_global, return_type="hexa")
        self.label.setText(f"CPU: {_global:.1f}%")

        self.label.setStyleSheet(f"color: {color}")

        self.meter.setValue(int(_global))
        self.meter.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color} }}")

        # Ne rafraîchir le tooltip que s'il est déjà visible
        if self.underMouse() and QToolTip.isVisible():
            # Formatter le texte de l'infobulle avec les détails par cœur
            tooltip_text = f"<b>Utilisation CPU Globale: <span style='color: {color}'>{_global:.1f}%</span></b><br><hr>"
            tooltip_text += "<br>".join(
                [
                    f"Cœur {i+1}: <span style='color: {percent_to_rgb(p, return_type='hexa')}'>{p:.1f}%</span>"
                    for i, p in enumerate(cores)
                ]
            )
            self.setToolTip(tooltip_text)
            # Si le curseur ne bouge pas, le texte du tooltip n'est pas rafraîchi par self.setToolTip
            QToolTip.showText(QCursor.pos(), self.toolTip(), self)


class CompactCpuSparklineView(QWidget):
    """Affiche un mini-graphique (sparkline) de l'utilisation récente du CPU global."""

    def __init__(self, vm: GlobalCpuMonitorViewModel, history_length=500):
        super().__init__()
        self.vm = vm
        self.history = deque(
            [0.0] * history_length, maxlen=history_length
        )  # Garde les 500 dernières valeurs
        self.current_value = 0.0
        self.setMinimumSize(150, 40)
        self.setToolTip("Historique de l'utilisation CPU globale")
        self.vm.signals.updated.connect(self.on_updated)

    def on_updated(self, _global: float, _cores: list[float]):
        self.history.append(_global)
        self.current_value = _global
        self.update()  # Demande un rafraîchissement du widget

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))

        if not self.history:
            return

        # Ligne du graphique
        color = percent_to_rgb(self.current_value, return_type="tuple")
        pen = QPen(Qt.GlobalColor.black)
        pen.setColor(QColor.fromRgb(*color))
        pen.setWidth(2)
        painter.setPen(pen)

        w = self.width()
        h = self.height()
        points = []
        for i, value in enumerate(self.history):
            x = w * i / (len(self.history) - 1) if len(self.history) > 1 else w / 2
            y = h - (value / 100.0 * h)
            points.append(QPointF(x, y))

        if points:
            painter.drawPolyline(points)

        # Texte de la valeur actuelle
        painter.setPen(self.palette().color(self.foregroundRole()))
        text = f"{self.current_value:.1f}%"
        painter.drawText(self.rect().adjusted(5, 0, -5, -5), Qt.AlignRight | Qt.AlignBottom, text)


class CompactCoresHeatmapView(QWidget):
    """Affiche une grille de carrés colorés (heatmap) pour l'utilisation de chaque cœur."""

    def __init__(self, vm: GlobalCpuMonitorViewModel):
        super().__init__()
        self.vm = vm
        self.num_cores = psutil.cpu_count()
        self.core_percents = [0.0] * self.num_cores
        self.setMinimumHeight(40)
        self.setMouseTracking(True)  # Pour les tooltips par cœur
        self.vm.signals.updated.connect(self.on_updated)

    def on_updated(self, _global: float, cores: list[float]):
        self.core_percents = cores
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        padding = 2
        # Disposer les coeurs pairs sur la ligne 0, et les coeurs impairs sur la ligne 1.
        # Cela correspond souvent à la distinction coeurs physiques / coeurs logiques (Hyper-Threading).
        num_cols = (self.num_cores + 1) // 2
        num_rows = 1 if self.num_cores == 1 else 2

        widget_w = self.width()
        widget_h = self.height()

        cell_w = (widget_w - (num_cols + 1) * padding) / num_cols if num_cols > 0 else 0
        cell_h = (widget_h - (num_rows + 1) * padding) / num_rows if num_rows > 0 else 0

        for i, percent in enumerate(self.core_percents):
            # Calcul de la position en ligne/colonne
            row = i % 2  # 0 pour les coeurs pairs (0, 2, ...), 1 pour les impairs (1, 3, ...)
            col = i // 2  # La colonne est la même pour le coeur N et N+1

            x = padding + col * (cell_w + padding)
            y = padding + row * (cell_h + padding)

            color_tuple = percent_to_rgb(percent, return_type="tuple")
            color = QColor.fromRgb(*color_tuple)

            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(int(x), int(y), int(cell_w), int(cell_h))

        self._update_tooltip()

    def mouseMoveEvent(self, event):
        self._update_tooltip()

    def _update_tooltip(self):

        # Logique pour afficher le tooltip du bon cœur
        padding = 2
        num_cols = (self.num_cores + 1) // 2
        num_rows = 1 if self.num_cores == 1 else 2

        cell_w = (self.width() - (num_cols + 1) * padding) / num_cols if num_cols > 0 else 0
        cell_h = (self.height() - (num_rows + 1) * padding) / num_rows if num_rows > 0 else 0

        if cell_w <= 0 or cell_h <= 0:
            return

        pos = self.mapFromGlobal(QCursor.pos())
        col = int((pos.x() - padding) / (cell_w + padding)) if cell_w + padding > 0 else -1
        row = int((pos.y() - padding) / (cell_h + padding)) if cell_h + padding > 0 else -1

        core_index = col * 2 + row if row >= 0 and col >= 0 else -1
        if 0 <= core_index < self.num_cores:
            percent = self.core_percents[core_index]
            color = percent_to_rgb(percent, return_type="hexa")
            self.setToolTip(f"Cœur {core_index + 1}: <b style='color:{color}'>{percent:.1f}%</b>")
            # Si le curseur ne bouge pas, le texte du tooltip n'est pas rafraîchi par self.setToolTip
            QToolTip.showText(QCursor.pos(), self.toolTip(), self)
        else:
            self.setToolTip("")


class CompactCoresMonitorView(QWidget):
    """Un widget compact affichant l'utilisation de chaque cœur CPU avec des barres de progression."""

    def __init__(self, vm: GlobalCpuMonitorViewModel):
        super().__init__()
        self.vm = vm
        self.core_percents: list[float] = []
        self.core_meters: list[QProgressBar] = []

        self.setup_ui()
        self.setup_signals()
        self.setMouseTracking(True)

    def setup_ui(self):
        layout = QHBoxLayout()
        self.setLayout(layout)

        num_cores = psutil.cpu_count()
        for i in range(num_cores):
            core_layout = QVBoxLayout()
            core_layout.setSpacing(2)

            meter = QProgressBar()
            meter.setRange(0, 100)
            meter.setValue(0)
            meter.setTextVisible(False)
            meter.setOrientation(Qt.Vertical)
            # meter.setFixedSize(12, 40)
            self.core_meters.append(meter)
            core_layout.addWidget(meter, 0, Qt.AlignHCenter)

            layout.addLayout(core_layout)

    def setup_signals(self):
        self.vm.signals.updated.connect(self.on_updated)

    def on_updated(self, _global: float, cores: list[float]):
        self.core_percents = cores
        for i, percent in enumerate(cores):
            if i < len(self.core_meters):
                color = percent_to_rgb(percent, return_type="hexa")
                self.core_meters[i].setValue(int(percent))
                self.core_meters[i].setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; margin-top: 2px; }}"
                )
        self._update_tooltip()

    def mouseMoveEvent(self, event):
        self._update_tooltip()

    def _update_tooltip(self):
        pos = self.mapFromGlobal(QCursor.pos())
        found_core = False
        for i, meter in enumerate(self.core_meters):
            if meter.geometry().contains(pos):
                if i < len(self.core_percents):
                    percent = self.core_percents[i]
                    color = percent_to_rgb(percent, return_type="hexa")
                    tooltip_text = f"Cœur {i + 1}: <b style='color:{color}'>{percent:.1f}%</b>"
                    self.setToolTip(tooltip_text)
                    QToolTip.showText(QCursor.pos(), self.toolTip(), self)
                    found_core = True
                    break

        if not found_core:
            self.setToolTip("")


class MemoryMonitorSignals(QObject):
    """Signaux pour le moniteur de mémoire."""

    updated = Signal(object, object)  # virtual_memory, swap_memory


class MemoryMonitorThread(QThread):
    """Thread pour surveiller l'utilisation de la RAM et du SWAP."""

    def __init__(self, interval: float = 2.0):
        super().__init__()
        self.interval = interval
        self.signals = MemoryMonitorSignals()
        self._is_running = False

    def run(self):
        self._is_running = True
        while self._is_running:
            vmem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            self.signals.updated.emit(vmem, swap)
            time.sleep(self.interval)

    def stop(self):
        self._is_running = False


class MemoryMonitorViewModel(QObject):
    """ViewModel pour le moniteur de mémoire."""

    def __init__(self, interval: float = 2.0):
        super().__init__()
        self._interval = interval
        self._thread: MemoryMonitorThread | None = None
        self.signals = MemoryMonitorSignals()

    def start(self):
        if self._thread and self._thread.isRunning():
            return
        self._thread = MemoryMonitorThread(self._interval)
        self._thread.signals.updated.connect(self.signals.updated.emit)
        self._thread.start()

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread.wait()
            self._thread = None


class SystemSummaryView(QWidget):
    """Un widget de synthèse affichant l'utilisation CPU, RAM et SWAP."""

    def __init__(self, cpu_vm: GlobalCpuMonitorViewModel, mem_vm: MemoryMonitorViewModel):
        super().__init__()
        self.cpu_vm = cpu_vm
        self.mem_vm = mem_vm

        self.setup_ui()
        self.setup_signals()

    def _create_info_row(self, label_text: str) -> tuple[QLabel, QProgressBar, QLabel]:
        """Helper pour créer une ligne d'information (label, barre, valeur)."""
        label = QLabel(f"{label_text}:")
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setTextVisible(False)
        progress_bar.setMaximumHeight(12)
        value_label = QLabel("--/-- GB (---%)")
        return label, progress_bar, value_label

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Ligne CPU
        self.cpu_label, self.cpu_meter, self.cpu_value = self._create_info_row("CPU")
        # Ligne RAM
        self.ram_label, self.ram_meter, self.ram_value = self._create_info_row("RAM")
        # Ligne SWAP
        self.swap_label, self.swap_meter, self.swap_value = self._create_info_row("SWAP")

        for label, meter, value in [
            (self.cpu_label, self.cpu_meter, self.cpu_value),
            (self.ram_label, self.ram_meter, self.ram_value),
            (self.swap_label, self.swap_meter, self.swap_value),
        ]:
            row_layout = QHBoxLayout()
            row_layout.addWidget(label, 1)
            row_layout.addWidget(meter, 3)
            row_layout.addWidget(value, 2)
            layout.addLayout(row_layout)

    def setup_signals(self):
        self.cpu_vm.signals.updated.connect(self.on_cpu_updated)
        self.mem_vm.signals.updated.connect(self.on_mem_updated)

    def on_cpu_updated(self, _global: float, _cores: list[float]):
        color = percent_to_rgb(_global, return_type="hexa")
        self.cpu_meter.setValue(int(_global))
        self.cpu_meter.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
        self.cpu_value.setText(f"{_global:.1f}%")
        self.cpu_value.setStyleSheet(f"color: {color};")

    def on_mem_updated(self, vmem, swap):
        # Mise à jour de la RAM
        ram_color = percent_to_rgb(vmem.percent, return_type="hexa")
        self.ram_meter.setValue(int(vmem.percent))
        self.ram_meter.setStyleSheet(f"QProgressBar::chunk {{ background-color: {ram_color}; }}")
        used_gb = vmem.used / (1024**3)
        total_gb = vmem.total / (1024**3)
        self.ram_value.setText(f"{used_gb:.2f}/{total_gb:.1f} GB ({vmem.percent:.0f}%)")
        self.ram_value.setStyleSheet(f"color: {ram_color};")

        # Mise à jour du SWAP
        if swap.total > 0:
            swap_color = percent_to_rgb(swap.percent, return_type="hexa")
            self.swap_meter.setValue(int(swap.percent))
            self.swap_meter.setStyleSheet(
                f"QProgressBar::chunk {{ background-color: {swap_color}; }}"
            )
            used_gb = swap.used / (1024**3)
            total_gb = swap.total / (1024**3)
            self.swap_value.setText(f"{used_gb:.2f}/{total_gb:.1f} GB ({swap.percent:.0f}%)")
            self.swap_value.setStyleSheet(f"color: {swap_color};")
        else:
            self.swap_value.setText("N/A")
            self.swap_meter.setValue(0)
