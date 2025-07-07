import math
import time
from collections import deque

import psutil
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from py_utils.misc import percent_to_rgb
from py_utils.stats import (
    BaseMonitor,
    CpuCoresMonitor,
    MemoryMonitor,
    ProcessMonitor,
    find_process_by_id_or_name,
)


class QHorizontalLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)


class QVerticalLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Sunken)


class BaseMonitorSignals(QObject):
    """Signaux de base pour les moniteurs."""

    started = Signal()
    finished = Signal(bool, str)
    # signal `updated` à définir dans les sous-classes


class BaseMonitorThread(QThread):
    """Thread de base pour exécuter un moniteur de `py_utils.stats`."""

    def __init__(self, monitor: BaseMonitor, signals: QObject):
        super().__init__()
        self.monitor = monitor
        self.signals = signals

        self.monitor.add_handler_on("started", self.signals.started.emit)
        self.monitor.add_handler_on("updated", self.signals.updated.emit)
        self.monitor.add_handler_on("finished", self.signals.finished.emit)

    def run(self):
        """Démarre la boucle de surveillance du moniteur."""
        self.monitor.start()

    def stop(self):
        """Arrête la boucle de surveillance du moniteur."""
        self.monitor.stop()


class BaseMonitorViewModel(QObject):
    """ViewModel de base pour gérer un moniteur via un thread."""

    def __init__(self, interval: float, history_length: int = 0):
        super().__init__()
        self._interval = interval
        self._history_length = history_length
        self._thread: BaseMonitorThread | None = None

    def _create_thread(self) -> BaseMonitorThread:
        raise NotImplementedError("Cette méthode doit être implémentée dans une sous-classe.")

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

        self._thread = self._create_thread()
        self._thread.signals.started.connect(self.signals.started.emit)
        self._thread.signals.updated.connect(self.signals.updated.emit)
        self._thread.signals.finished.connect(self.signals.finished.emit)
        self._thread.start()

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread.wait()
            self._thread = None


#
# CPU Cores Monitor classes
#
class CpuCoresMonitorSignals(BaseMonitorSignals):
    updated = Signal(float, object)


class CpuCoresMonitorThread(BaseMonitorThread):
    def __init__(self, interval: float = 0.5, history_length: int = 0):
        monitor = CpuCoresMonitor(interval=interval, history_length=history_length)
        signals = CpuCoresMonitorSignals()
        super().__init__(monitor, signals)


class CpuCoresMonitorViewModel(BaseMonitorViewModel):

    def __init__(self, interval: float = 0.5, history_length: int = 0):
        super().__init__(interval, history_length)
        self.signals = CpuCoresMonitorSignals()

    def _create_thread(self) -> CpuCoresMonitorThread:
        return CpuCoresMonitorThread(interval=self._interval, history_length=self._history_length)


#
# Memory Monitor classes
#
class MemoryMonitorSignals(BaseMonitorSignals):
    updated = Signal(object, object)  # vmem, swap


class MemoryMonitorThread(BaseMonitorThread):
    """Thread pour surveiller l'utilisation de la RAM et du SWAP."""

    def __init__(self, interval: float = 1.0, history_length: int = 0):
        monitor = MemoryMonitor(interval=interval, history_length=history_length)
        signals = MemoryMonitorSignals()
        super().__init__(monitor, signals)


class MemoryMonitorViewModel(BaseMonitorViewModel):
    """ViewModel pour le moniteur de mémoire."""

    def __init__(self, interval: float = 1.0, history_length: int = 0):
        super().__init__(interval, history_length)
        self.signals = MemoryMonitorSignals()

    def _create_thread(self) -> MemoryMonitorThread:
        return MemoryMonitorThread(self._interval, self._history_length)


#
# Process Monitor classes
#
class ProcessMonitorSignals(BaseMonitorSignals):
    updated = Signal(float)  # percentage of cpu used by process


class ProcessMonitorThread(BaseMonitorThread):
    """Thread pour surveiller l'utilisation CPU par un processus."""

    def __init__(self, pid: int, interval: float = 0.2, history_length: int = 0):
        monitor = ProcessMonitor(pid, interval, history_length)
        signals = ProcessMonitorSignals()
        super().__init__(monitor, signals)


class ProcessMonitorViewModel(BaseMonitorViewModel):
    """ViewModel pour le moniteur de mémoire."""

    def __init__(
        self, process_identifier: str | int, interval: float = 0.2, history_length: int = 0
    ):
        super().__init__(interval, history_length)
        self.signals = ProcessMonitorSignals()

        # Déclaration des attributs de la classe
        self._process_identifier: str | int | None = None
        self._process: psutil.Process | None = None

        # Assignation de l'identifiant de process (et "attachement" du process)
        self.process_identifier = process_identifier

    def _create_thread(self) -> ProcessMonitorThread:
        if not self._process:
            self._attach_process()
        return ProcessMonitorThread(self._process.pid, self._interval, self._history_length)

    @property
    def process_identifier(self):
        return self._process_identifier

    @process_identifier.setter
    def process_identifier(self, value: str | int):
        if self._process_identifier == value:
            return
        self._process_identifier = value
        self._attach_process()

    def _attach_process(self):
        if self._thread:
            self._thread.stop()
            self._thread = None
        self._process = find_process_by_id_or_name(self._process_identifier)

    def get_name(self):
        return self._process.name() if self._process else None

    def get_pid(self):
        return self._process.pid if self._process else None


#
# Compact Views
#
class CompactCpuCoresMonitorView(QWidget):
    def __init__(
        self,
        vm: CpuCoresMonitorViewModel,
        orientation: Qt.Orientation = Qt.Horizontal,
        side_text: str = "right",
    ):
        super().__init__()
        self.vm = vm
        self._orientation = orientation
        self._side_text = side_text
        self.setup_ui()
        self.setup_signals()

    def setup_ui(self):
        layout = QHBoxLayout()
        self.setLayout(layout)

        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("CPU: --.-%")
        # self.label.setFixedWidth(75)

        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setOrientation(self._orientation)
        if self._orientation == Qt.Horizontal:
            self.meter.setMaximumHeight(12)
            if self._side_text == "right":
                self.meter.setInvertedAppearance(True)
        else:
            self.meter.setMaximumWidth(12)

        if self._side_text == "left":
            self.label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
            layout.addWidget(self.label)
            layout.addWidget(self.meter)
        else:
            self.label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
            layout.addWidget(self.meter)
            layout.addWidget(self.label)

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

    def __init__(self, vm: CpuCoresMonitorViewModel, display_percent: bool = False):
        super().__init__()
        self.vm = vm
        self.display_percent = display_percent
        self.current_value = 0.0
        self.vm.signals.updated.connect(self.on_updated)
        self.setToolTip("En attente de données...")
        # self.setMinimumHeight(10)
        self.setMinimumWidth(50)

    def _update_tooltip(self, cpu, cores):
        # Ne rafraîchir le tooltip que s'il est déjà visible
        if self.underMouse() and QToolTip.isVisible():
            color = percent_to_rgb(cpu, return_type="hexa")
            # Formatter le texte de l'infobulle avec les détails par cœur
            tooltip_text = f"<b>Utilisation CPU Globale: <span style='color: {color}'>{cpu:.1f}%</span></b><br><hr>"
            tooltip_text += "<br>".join(
                [
                    f"Cœur {i+1}: <span style='color: {percent_to_rgb(p, return_type='hexa')}'>{p:.1f}%</span>"
                    for i, p in enumerate(cores)
                ]
            )
            self.setToolTip(tooltip_text)
            # Si le curseur ne bouge pas, le texte du tooltip n'est pas rafraîchi par self.setToolTip
            QToolTip.showText(QCursor.pos(), self.toolTip(), self)

    def on_updated(self, cpu: float, cores: list[float]):
        self.current_value = cpu
        self._update_tooltip(cpu, cores)
        self.update()  # Demande un rafraîchissement du widget

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))

        # On s'assure que le thread et le moniteur existent et ont un historique
        if not (self.vm._thread and self.vm._thread.monitor and self.vm._thread.monitor.history):
            return

        history = self.vm._thread.monitor.get_cpu_history()
        monitor = self.vm._thread.monitor
        if not history or monitor.history_length <= 1:
            return

        # --- Configuration du dessin ---
        w = self.width()
        h = self.height()
        graph_h = h

        # --- Dessin des lignes de fond (grille) ---
        # Utilise une couleur claire du thème pour les lignes, pour qu'elles soient discrètes
        grid_color = self.palette().color(QPalette.ColorRole.Dark)
        # On la rend semi-transparente pour qu'elle soit encore plus discrète
        grid_color.setAlpha(100)  # Valeur entre 0 (transparent) et 255 (opaque)
        grid_pen = QPen(grid_color)
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        for percent in [50, 100]:
            # On s'assure que y est un entier pour un dessin net
            y = int(graph_h - (percent / 100.0 * graph_h))
            # La ligne à 100% est tout en haut (y=0), on peut la décaler de 1px pour la voir
            # et éviter qu'elle ne soit coupée par le bord du widget.
            if y == 0:
                y = 1
            painter.drawLine(0, y, w, y)

        # Ligne du graphique
        color = percent_to_rgb(self.current_value, return_type="tuple")
        pen = QPen(Qt.GlobalColor.black)
        pen.setColor(QColor.fromRgb(*color))
        pen.setWidth(2)
        painter.setPen(pen)

        points = []
        for i, value in enumerate(history):
            x = w * i / (monitor.history_length - 1)
            y = graph_h - (value / 100.0 * graph_h)
            points.append(QPointF(x, y))

        if points:
            painter.drawPolyline(points)

        if self.display_percent:
            # Texte de la valeur actuelle
            # On place le texte dans le coin supérieur droit de la zone du graphique
            painter.setPen(self.palette().color(self.foregroundRole()))
            text_rect = self.rect().adjusted(5, 5, -47, -5)
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignTop, "CPU :")

            painter.setPen(QColor.fromRgb(*color))
            text = f"{self.current_value:.1f}%"
            text_rect = self.rect().adjusted(5, 5, -5, -5)
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignTop, text)

        # --- Échelle de temps ---
        total_seconds = monitor.history_length * self.vm.interval
        font = painter.font()
        font.setPointSize(font.pointSize() - 2)  # Police plus petite
        painter.setFont(font)
        # On utilise la même couleur que la grille pour une apparence cohérente
        text_color = self.palette().color(QPalette.ColorRole.Dark)
        text_color.setAlpha(150)  # Un peu moins transparent que la grille pour la lisibilité
        painter.setPen(text_color)

        # Libellé de gauche
        left_label = f"-{int(total_seconds)}s"
        painter.drawText(
            self.rect().adjusted(5, h - 15, 0, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            left_label,
        )

        # Libellé du milieu
        mid_label = f"-{int(total_seconds / 2)}s"
        painter.drawText(
            self.rect().adjusted(0, h - 15, 0, 0),
            Qt.AlignCenter | Qt.AlignVCenter,
            mid_label,
        )

        # Libellé de droite
        right_label = "0s"
        painter.drawText(
            self.rect().adjusted(0, h - 15, -5, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            right_label,
        )


class CompactMemorySparklineView(QWidget):
    """Affiche un mini-graphique de l'utilisation de la RAM (ligne) et du SWAP (zone)."""

    def __init__(self, vm: MemoryMonitorViewModel, display_percent: bool = True):
        super().__init__()
        self.vm = vm
        self.display_percent = display_percent
        self.current_ram = 0.0
        self.current_swap = 0.0
        self.vm.signals.updated.connect(self.on_updated)
        self.setToolTip("En attente de données...")
        self.setMinimumHeight(40)  # On donne une taille minimale au widget

    def on_updated(self, vmem, swap):
        self.current_ram = vmem.percent
        self.current_swap = swap.percent
        self.update()  # Demande un rafraîchissement

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))

        if not (self.vm._thread and self.vm._thread.monitor and self.vm._thread.monitor.history):
            return

        monitor = self.vm._thread.monitor
        ram_history = monitor.get_ram_history()
        swap_history = monitor.get_swap_history()

        if not ram_history or monitor.history_length <= 1:
            return

        w = self.width()
        h = self.height()

        # --- 1. Dessin de la zone de SWAP (en arrière-plan) ---
        if any(p > 0 for p in swap_history):
            swap_color = QColor(255, 0, 0, 70)  # Rouge semi-transparent
            painter.setPen(Qt.NoPen)
            painter.setBrush(swap_color)

            points = [QPointF(0, h)]
            for i, value in enumerate(swap_history):
                x = w * i / (monitor.history_length - 1)
                y = h - (value / 100.0 * h)
                points.append(QPointF(x, y))
            points.append(QPointF(w, h))
            painter.drawPolygon(points)

        # --- 2. Dessin de la ligne de RAM (au premier plan) ---
        ram_color_tuple = percent_to_rgb(self.current_ram, return_type="tuple")
        pen = QPen(QColor.fromRgb(*ram_color_tuple))
        pen.setWidth(2)
        painter.setPen(pen)

        points = []
        for i, value in enumerate(ram_history):
            x = w * i / (monitor.history_length - 1)
            y = h - (value / 100.0 * h)
            points.append(QPointF(x, y))

        if points:
            painter.drawPolyline(points)

        # --- 3. Affichage des pourcentages ---
        if self.display_percent:
            # Texte RAM
            painter.setPen(QColor.fromRgb(*ram_color_tuple))
            ram_text = f"RAM: {self.current_ram:.1f}%"
            painter.drawText(
                self.rect().adjusted(5, 5, -5, -5), Qt.AlignLeft | Qt.AlignTop, ram_text
            )

            # Texte SWAP (uniquement si utilisé)
            if self.current_swap > 0:
                swap_text_color = QColor(255, 80, 80)  # Rouge plus visible pour le texte
                painter.setPen(swap_text_color)
                swap_text = f"SWAP: {self.current_swap:.1f}%"
                painter.drawText(
                    self.rect().adjusted(5, 5, -5, -5), Qt.AlignRight | Qt.AlignTop, swap_text
                )

        self._update_tooltip(ram_history, swap_history)

    def _update_tooltip(self, ram_history, swap_history):
        if self.underMouse() and QToolTip.isVisible():
            ram_color = percent_to_rgb(self.current_ram, return_type="hexa")
            swap_color = percent_to_rgb(self.current_swap, return_type="hexa")

            tooltip_text = (
                f"<b>RAM: <span style='color: {ram_color}'>{self.current_ram:.1f}%</span></b>"
            )
            if self.current_swap > 0:
                tooltip_text += f"<br><b>SWAP: <span style='color: {swap_color}'>{self.current_swap:.1f}%</span></b>"

            self.setToolTip(tooltip_text)
            QToolTip.showText(QCursor.pos(), self.toolTip(), self)

    def mouseMoveEvent(self, event):
        # Force la mise à jour du tooltip même si les données n'ont pas changé
        self.update()


class CompactCoresHeatmapView(QWidget):
    """Affiche une grille de carrés colorés (heatmap) pour l'utilisation de chaque cœur."""

    def __init__(self, vm: CpuCoresMonitorViewModel):
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


class CompactCoresHeatmap2View(QWidget):
    """Affiche une grille de carrés colorés (heatmap) pour l'utilisation de chaque cœur."""

    def __init__(self, vm: CpuCoresMonitorViewModel):
        super().__init__()
        self.vm = vm
        self.cpu_percent = 0
        self.num_cores = psutil.cpu_count()
        self.core_percents = [0.0] * self.num_cores
        self.setMinimumHeight(40)
        self.setMouseTracking(True)  # Pour les tooltips par cœur
        self.vm.signals.updated.connect(self.on_updated)

    def on_updated(self, _global: float, cores: list[float]):
        self.cpu_percent = _global
        self.core_percents = cores
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))

        # On s'assure que le thread et le moniteur existent et ont un historique
        if not (self.vm._thread and self.vm._thread.monitor and self.vm._thread.monitor.history):
            return

        history = self.vm._thread.monitor.get_cpu_history()
        monitor = self.vm._thread.monitor
        if not history or monitor.history_length <= 1:
            return

        # --- Configuration du dessin ---
        w = self.width()
        h = self.height()
        graph_h = h

        # --- Dessin des lignes de fond (grille) ---
        # Utilise une couleur claire du thème pour les lignes, pour qu'elles soient discrètes
        grid_color = self.palette().color(QPalette.ColorRole.Dark)
        # On la rend semi-transparente pour qu'elle soit encore plus discrète
        grid_color.setAlpha(100)  # Valeur entre 0 (transparent) et 255 (opaque)
        grid_pen = QPen(grid_color)
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        for percent in [50, 100]:
            # On s'assure que y est un entier pour un dessin net
            y = int(graph_h - (percent / 100.0 * graph_h))
            # La ligne à 100% est tout en haut (y=0), on peut la décaler de 1px pour la voir
            # et éviter qu'elle ne soit coupée par le bord du widget.
            if y == 0:
                y = 1
            painter.drawLine(0, y, w, y)

        # Ligne du graphique
        color = percent_to_rgb(self.cpu_percent, return_type="tuple")
        pen = QPen(Qt.GlobalColor.black)
        pen.setColor(QColor.fromRgb(*color))
        pen.setWidth(2)
        painter.setPen(pen)

        points = []
        for i, value in enumerate(history):
            x = w * i / (monitor.history_length - 1)
            y = graph_h - (value / 100.0 * graph_h)
            points.append(QPointF(x, y))

        if points:
            painter.drawPolyline(points)

        # --- Échelle de temps ---
        total_seconds = monitor.history_length * self.vm.interval
        font = painter.font()
        font.setPointSize(font.pointSize() - 2)  # Police plus petite
        painter.setFont(font)
        # On utilise la même couleur que la grille pour une apparence cohérente
        text_color = self.palette().color(QPalette.ColorRole.Dark)
        text_color.setAlpha(150)  # Un peu moins transparent que la grille pour la lisibilité
        painter.setPen(text_color)

        # Libellé de gauche
        left_label = f"-{int(total_seconds)}s"
        painter.drawText(
            self.rect().adjusted(5, h - 15, 0, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            left_label,
        )

        # Libellé du milieu
        mid_label = f"-{int(total_seconds / 2)}s"
        painter.drawText(
            self.rect().adjusted(0, h - 15, 0, 0),
            Qt.AlignCenter | Qt.AlignVCenter,
            mid_label,
        )

        # Libellé de droite
        right_label = "0s"
        painter.drawText(
            self.rect().adjusted(0, h - 15, -5, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            right_label,
        )

        # Texte de la valeur actuelle
        # On place le texte dans le coin supérieur droit de la zone du graphique
        painter.setPen(self.palette().color(self.foregroundRole()))
        text_rect = self.rect().adjusted(5, 5, -47, -5)
        painter.drawText(text_rect, Qt.AlignRight | Qt.AlignTop, "CPU :")

        painter.setPen(QColor.fromRgb(*color))
        text = f"{self.cpu_percent:.1f}%"
        text_rect = self.rect().adjusted(5, 5, -5, -5)
        painter.drawText(text_rect, Qt.AlignRight | Qt.AlignTop, text)

        padding = 2
        # Disposer les coeurs pairs sur la ligne 0, et les coeurs impairs sur la ligne 1.
        # Cela correspond souvent à la distinction coeurs physiques / coeurs logiques (Hyper-Threading).
        num_cols = (self.num_cores + 1) // 2
        num_rows = 1 if self.num_cores == 1 else 2

        widget_w = self.width() / 5
        widget_h = self.height() / 2.5

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

        cell_w = (self.width() / 5 - (num_cols + 1) * padding) / num_cols if num_cols > 0 else 0
        cell_h = (self.height() / 2.5 - (num_rows + 1) * padding) / num_rows if num_rows > 0 else 0

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

    def __init__(self, vm: CpuCoresMonitorViewModel):
        super().__init__()
        self.vm = vm
        self.core_percents: list[float] = []
        self.core_meters: list[QProgressBar] = []

        self.setup_ui()
        self.setup_signals()
        self.setMouseTracking(True)

    def setup_ui(self):
        # Le layout principal est un QHBoxLayout. On lui passe `self` pour l'assigner au widget.
        layout = QHBoxLayout(self)
        # On supprime les marges et on met un espacement minimal entre les éléments.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)  # Espace de 1px entre les barres

        num_cores = psutil.cpu_count()
        for i in range(num_cores):
            meter = QProgressBar()
            meter.setRange(0, 100)
            meter.setValue(0)
            meter.setTextVisible(False)
            meter.setOrientation(Qt.Vertical)
            meter.setMinimumWidth(3)  # Un peu plus large pour une meilleure visibilité
            self.core_meters.append(meter)
            layout.addWidget(meter)

    def setup_signals(self):
        self.vm.signals.updated.connect(self.on_updated)

    def on_updated(self, _global: float, cores: list[float]):
        self.core_percents = cores
        for i, percent in enumerate(cores):
            if i < len(self.core_meters):
                color = percent_to_rgb(percent, return_type="hexa")
                self.core_meters[i].setValue(int(percent))
                self.core_meters[i].setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; }}"
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


class SystemSummaryView(QWidget):
    """Un widget de synthèse affichant l'utilisation CPU, RAM et SWAP."""

    def __init__(self, cpu_vm: CpuCoresMonitorViewModel, mem_vm: MemoryMonitorViewModel):
        super().__init__()
        self.cpu_vm = cpu_vm
        self.mem_vm = mem_vm

        self.setup_ui()
        self.setup_signals()

    def _create_info_row(self, label_text: str) -> tuple[QLabel, QProgressBar, QLabel]:
        """Helper pour créer une ligne d'information (label, barre, valeur)."""
        label = QLabel(f"<b>{label_text} : </b>")
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setTextVisible(False)
        progress_bar.setMaximumHeight(6)
        value_label = QLabel("--/-- GB (---%)")

        # Réduire la taille de la police pour un affichage plus compact
        font = value_label.font()
        font.setPointSize(font.pointSize() - 1)
        label.setFont(font)
        value_label.setFont(font)

        return label, progress_bar, value_label

    def setup_ui(self):
        # Utiliser un QGridLayout pour un contrôle plus fin et un rendu plus compact
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)  # Marges minimales (gauche, haut, droite, bas)
        layout.setSpacing(1)  # Espacement minimal entre les widgets

        # Ligne CPU
        self.cpu_label, self.cpu_meter, self.cpu_value = self._create_info_row("CPU")
        self.cpu_value.setText("---.-%")  # Texte initial spécifique au CPU
        # Ligne RAM
        self.ram_label, self.ram_meter, self.ram_value = self._create_info_row("RAM")
        # Ligne SWAP
        self.swap_label, self.swap_meter, self.swap_value = self._create_info_row("SWAP")

        # Ajout des widgets à la grille
        layout.addWidget(self.cpu_label, 0, 0)
        layout.addWidget(self.cpu_meter, 0, 1)
        layout.addWidget(self.cpu_value, 0, 2)
        layout.addWidget(self.ram_label, 1, 0)
        layout.addWidget(self.ram_meter, 1, 1)
        layout.addWidget(self.ram_value, 1, 2)
        layout.addWidget(self.swap_label, 2, 0)
        layout.addWidget(self.swap_meter, 2, 1)
        layout.addWidget(self.swap_value, 2, 2)

        # Définir comment les colonnes s'étirent pour occuper l'espace
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 2)

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
