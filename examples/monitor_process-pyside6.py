import dis
import multiprocessing
import sys

import psutil
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from py_utils.misc import percent_to_rgb
from py_utils.stats import (
    CpuCoresMonitor,
    ProcessCpuMonitor,
    find_process_by_id_or_name,
)
from py_utils.widgets import (
    CompactCoresHeatmapView,
    CompactCoresMonitorView,
    CompactCpuCoresMonitorView,
    CompactCpuSparklineView,
    CpuCoresMonitorViewModel,
    MemoryMonitorViewModel,
    SystemSummaryView,
)


# Fonction worker qui sera exécutée dans un processus séparé pour consommer du CPU
def cpu_worker():
    """Une fonction simple qui tourne en boucle pour utiliser 100% d'un cœur CPU."""
    while True:
        pass


class ProcessCpuMonitorSignals(QObject):
    updated = Signal(float)
    started = Signal(int, str)
    finished = Signal(bool, str)


class ProcessCpuMonitorThread(QThread):
    def __init__(self, pid: int, interval: float):
        super().__init__()
        self.signals = ProcessCpuMonitorSignals()
        self.monitor = ProcessCpuMonitor(pid, interval)
        self.monitor.add_handler_on("started", self.signals.started.emit)
        self.monitor.add_handler_on("updated", self.signals.updated.emit)
        self.monitor.add_handler_on("finished", self.signals.finished.emit)

    def run(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()


class ProcessCpuMonitorViewModel(QObject):

    def __init__(self, process_identifier: str | int, interval: float = 0.5):
        super().__init__()
        self._process_identifier: str | int | None = None
        self._process: psutil.Process | None = None
        self._thread: ProcessCpuMonitorThread | None = None
        self._interval = interval

        self.signals = ProcessCpuMonitorSignals()
        self.process_identifier = process_identifier

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

    def start(self):
        if self._thread and self._thread.isRunning():
            return

        if not self._process:
            try:
                self._attach_process()
            except (ValueError, psutil.Error) as e:
                self.signals.finished.emit(False, f"Erreur: {e}")
                return

        self._thread = ProcessCpuMonitorThread(self._process.pid, self._interval)
        self._thread.signals.started.connect(self.signals.started.emit)
        self._thread.signals.updated.connect(self.signals.updated.emit)
        self._thread.signals.finished.connect(self.signals.finished.emit)
        self._thread.start()

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread.wait()
            self._thread = None

    def get_name(self):
        return self._process.name() if self._process else None

    def get_pid(self):
        return self._process.pid if self._process else None


class ProcessCpuMonitorView(QWidget):
    def __init__(self, vm: ProcessCpuMonitorViewModel):
        super().__init__()
        self.vm = vm

        self.setup_ui()
        self.setup_signals()

    def setup_ui(self):
        layout = QHBoxLayout()
        self.setLayout(layout)

        self.name = QLabel(self.vm.get_name())
        layout.addWidget(self.name)

        self.value = QLabel("0.0%")
        layout.addWidget(self.value)

        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setMaximumHeight(12)
        self.meter.setOrientation(Qt.Horizontal)
        layout.addWidget(self.meter)

    def setup_signals(self):
        self.vm.signals.updated.connect(self.on_updated)
        self.vm.signals.finished.connect(lambda ok, msg: self.name.setText(msg))

    def on_updated(self, value: float):
        self.value.setText(f"{value:.1f}%")
        self.value.setStyleSheet(f"color: {percent_to_rgb(value, return_type='hexa')}")
        self.meter.setValue(value)
        self.meter.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {percent_to_rgb(value, return_type='hexa')} }}"
        )


class CpuCoresMonitorView(QWidget):
    def __init__(self, vm: CpuCoresMonitorViewModel):
        super().__init__()
        self.vm = vm

        self.setup_ui()
        self.setup_signals()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.message = QLabel("Coin messages")
        layout.addWidget(self.message)

        self._setup_global_cpu()
        self._setup_cpu_cores()

    def _setup_global_cpu(self):
        layout = self.layout()

        cpu_global_block = QWidget()
        layout.addWidget(cpu_global_block)
        cpu_global = QHBoxLayout()
        cpu_global_block.setLayout(cpu_global)

        cpu_name = QLabel("CPU Global")
        cpu_global.addWidget(cpu_name)

        self.cpu_global_value = QLabel("0.0%")
        cpu_global.addWidget(self.cpu_global_value)

        self.cpu_global_meter = QProgressBar()
        self.cpu_global_meter.setRange(0, 100)
        self.cpu_global_meter.setOrientation(Qt.Horizontal)
        cpu_global.addWidget(self.cpu_global_meter)

    def _setup_cpu_cores(self):
        layout = self.layout()

        cpu_cores_block = QWidget()
        cpu_cores_block.setMaximumHeight(150)
        layout.addWidget(cpu_cores_block)

        cpu_cores = QHBoxLayout()
        cpu_cores_block.setLayout(cpu_cores)

        block_title = QLabel("CPU Cores")
        cpu_cores.addWidget(block_title)

        self.cpu_cores = []
        for i in range(psutil.cpu_count()):
            cpu_core = {}

            cpu_core_block = QVBoxLayout()
            cpu_cores.addLayout(cpu_core_block)

            meter = QProgressBar()
            meter.setRange(0, 100)
            meter.setOrientation(Qt.Vertical)
            cpu_core_block.addWidget(meter)
            cpu_core["meter"] = meter

            value = QLabel("0.0%")
            cpu_core_block.addWidget(value)
            cpu_core["value"] = value

            cpu_name = QLabel(f"Core {i+1}")
            cpu_core_block.addWidget(cpu_name)

            self.cpu_cores.append(cpu_core)

    def setup_signals(self):
        self.vm.signals.updated.connect(self.on_updated)
        self.vm.signals.finished.connect(lambda success, message: self.message.setText(message))

    def on_updated(self, value: float, percents: list[float]):
        self.cpu_global_value.setText(f"{value:.1f}%")
        self.cpu_global_meter.setValue(int(value))

        for i, core_percent in enumerate(percents):
            self.cpu_cores[i]["value"].setText(f"{core_percent:.1f}%")
            self.cpu_cores[i]["meter"].setValue(int(core_percent))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.container = QWidget()
        self.setCentralWidget(self.container)

        layout = QVBoxLayout()
        self.container.setLayout(layout)

        # Créer et démarrer le processus worker qui consomme du CPU
        self.worker_process = multiprocessing.Process(target=cpu_worker, daemon=True)
        self.worker_process.start()

        # --- Monitoring Système (CPU + Mémoire) ---
        # On crée UNE SEULE instance du ViewModel pour le CPU global.
        # On active l'historique pour le sparkline en passant history_length au ViewModel.
        history_length_for_sparkline = 300
        self.global_cpu_vm = CpuCoresMonitorViewModel(
            interval=0.2, history_length=history_length_for_sparkline
        )
        self.memory_vm = MemoryMonitorViewModel(interval=2.0)

        # On crée le widget de synthèse et on lui passe les VMs
        self.system_summary_view = SystemSummaryView(
            cpu_vm=self.global_cpu_vm, mem_vm=self.memory_vm
        )
        layout.addWidget(self.system_summary_view)

        # --- Monitoring CPU Global ---

        # Vue pour le CPU Global
        # self.cpu_global_view = CpuCoresMonitorView(vm=self.global_cpu_vm)
        # layout.addWidget(self.cpu_global_view)

        self.cpu_compact_view = CompactCpuCoresMonitorView(vm=self.global_cpu_vm)
        layout.addWidget(self.cpu_compact_view)

        self.cpu_compact_view_vert = CompactCpuCoresMonitorView(
            vm=self.global_cpu_vm, orientation=Qt.Vertical
        )
        layout.addWidget(self.cpu_compact_view_vert)

        self.cores_compact_view = CompactCoresMonitorView(vm=self.global_cpu_vm)
        # self.cores_compact_view.setMaximumWidth(200)
        layout.addWidget(self.cores_compact_view)

        self.cores_heatmap = CompactCoresHeatmapView(vm=self.global_cpu_vm)
        self.cores_heatmap.setFixedSize(100, 40)
        layout.addWidget(self.cores_heatmap)

        self.cpu_sparkline = CompactCpuSparklineView(vm=self.global_cpu_vm, display_percent=True)
        layout.addWidget(self.cpu_sparkline)

        spark_and_bar_block = QWidget()
        spark_and_bar_block.setMaximumHeight(100)
        layout.addWidget(spark_and_bar_block)
        spark_and_bar = QHBoxLayout()
        spark_and_bar_block.setLayout(spark_and_bar)

        spark_and_bar.addWidget(self.cpu_sparkline)
        spark_and_bar.addWidget(self.cpu_compact_view_vert)

        # --- Monitoring Processus Spécifique ---
        process_layout = QHBoxLayout()
        layout.addLayout(process_layout)

        process_vm = ProcessCpuMonitorViewModel(process_identifier=self.worker_process.pid)
        self.cpu_process_view = ProcessCpuMonitorView(vm=process_vm)
        process_layout.addWidget(self.cpu_process_view, 1)  # Donne plus de place à la vue

        # Ajout des boutons de contrôle
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.on_pause_process)
        process_layout.addWidget(self.pause_button)

        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self.on_resume_process)
        self.resume_button.setEnabled(False)  # Le processus démarre en cours d'exécution
        process_layout.addWidget(self.resume_button)

        # On démarre les moniteurs
        self.global_cpu_vm.start()
        self.memory_vm.start()
        process_vm.start()

        self.setWindowTitle("Exemple utilisation ProcCpuPercents")
        self.setGeometry(100, 100, 400, 600)

    def on_pause_process(self):
        """Met en pause le processus worker."""
        try:
            if self.worker_process and self.worker_process.is_alive():
                p = psutil.Process(self.worker_process.pid)
                p.suspend()
                self.pause_button.setEnabled(False)
                self.resume_button.setEnabled(True)
                print("Processus worker mis en pause.")
        except psutil.NoSuchProcess:
            print("Le processus worker n'existe plus.")

    def on_resume_process(self):
        """Reprend l'exécution du processus worker."""
        try:
            if self.worker_process and self.worker_process.is_alive():
                p = psutil.Process(self.worker_process.pid)
                p.resume()
                self.pause_button.setEnabled(True)
                self.resume_button.setEnabled(False)
                print("Processus worker relancé.")
        except psutil.NoSuchProcess:
            print("Le processus worker n'existe plus.")

    def closeEvent(self, event: QCloseEvent):
        """S'assure que tous les threads et processus sont bien arrêtés."""
        # Arrêter les moniteurs
        self.global_cpu_vm.stop()
        self.memory_vm.stop()
        if self.cpu_process_view:
            self.cpu_process_view.vm.stop()

        # Arrêter le processus worker
        if self.worker_process and self.worker_process.is_alive():
            self.worker_process.terminate()
            self.worker_process.join()

        event.accept()


def main():
    app = QApplication(sys.argv)

    # Appliquer un style global pour les tooltips.
    # C'est la méthode standard pour styliser les tooltips dans une application Qt.
    # Le sélecteur "QToolTip" cible spécifiquement ce widget.
    app.setStyleSheet(
        """
        QToolTip {
            color: #eff0f1;                     /* Couleur du texte (blanc cassé) */
            background-color: #2b2b2b;          /* Couleur de fond (gris foncé) */
            border: 1px solid #4f4f4f;          /* Bordure subtile */
            border-radius: 4px;                 /* Coins arrondis */
            padding: 5px;                       /* Marge intérieure */
            opacity: 230;                       /* Légère transparence (0-255) */
        }
    """
    )

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
