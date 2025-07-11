import multiprocessing
import sys

import psutil
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from py_utils.misc import percent_to_rgb
from py_utils.widgets import (
    CompactCoresMonitorView,
    CompactCpuSparklineView,
    CpuCoresMonitorViewModel,
    MemoryMonitorViewModel,
    ProcessMonitorViewModel,
    SystemSummaryView,
)


# Fonction worker qui sera exécutée dans un processus séparé pour consommer du CPU
def cpu_worker():
    """Une fonction simple qui tourne en boucle pour utiliser 100% d'un cœur CPU."""
    while True:
        pass


class ProcessMonitorView(QWidget):
    def __init__(self, vm: ProcessMonitorViewModel):
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
        # self.vm.signals.started.connect(self.on_started)
        self.vm.signals.updated.connect(self.on_updated)
        self.vm.signals.finished.connect(lambda ok, msg: self.name.setText(msg))

    def on_updated(self, value: float):
        self.value.setText(f"{value:.1f}%")
        self.value.setStyleSheet(f"color: {percent_to_rgb(value, return_type='hexa')}")
        self.meter.setValue(value)
        self.meter.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {percent_to_rgb(value, return_type='hexa')} }}"
        )


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
        self.memory_vm = MemoryMonitorViewModel(
            interval=0.5, history_length=history_length_for_sparkline
        )

        # On crée le widget de synthèse et on lui passe les VMs
        self.system_summary_view = SystemSummaryView(
            cpu_vm=self.global_cpu_vm, mem_vm=self.memory_vm
        )
        self.cpu_sparkline = CompactCpuSparklineView(vm=self.global_cpu_vm, display_percent=True)
        self.cores_compact_view = CompactCoresMonitorView(vm=self.global_cpu_vm)

        spark_and_bar_block = QWidget()
        spark_and_bar_block.setMaximumHeight(100)
        layout.addWidget(spark_and_bar_block)
        spark_and_bar = QHBoxLayout()
        spark_and_bar_block.setLayout(spark_and_bar)

        spark_and_bar.addWidget(self.cores_compact_view, 1)
        spark_and_bar.addWidget(self.cpu_sparkline, 2)
        spark_and_bar.addWidget(self.system_summary_view, 1)

        # # --- Monitoring Processus Spécifique ---
        process_layout = QHBoxLayout()
        layout.addLayout(process_layout)

        self.process_vm = ProcessMonitorViewModel(process_identifier=self.worker_process.pid)
        self.cpu_process_view = ProcessMonitorView(vm=self.process_vm)
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
        self.process_vm.start()

        self.setWindowTitle("Exemple utilisation ProcCpuPercents")
        self.setGeometry(100, 100, 800, 600)

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
        self.process_vm.stop()

        # Arrêter le processus worker
        if self.worker_process and self.worker_process.is_alive():
            self.worker_process.terminate()
            self.worker_process.join()

        event.accept()


def main():
    # Nécessaire pour PyInstaller lors de l'utilisation de multiprocessing
    multiprocessing.freeze_support()

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
