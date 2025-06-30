import sys

import psutil
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from py_utils.process import (
    GlobalCpuMonitor,
    ProcessCpuMonitor,
    find_process_by_id_or_name,
)


class ProcessCpuMonitorSignals(QObject):
    updated = Signal(float)
    started = Signal(str)
    finished = Signal(bool, str)


class GlobalCpuMonitorSignals(QObject):
    updated = Signal(float, list[float])
    started = Signal(str)
    finished = Signal(bool, str)


class ProcessCpuMonitorThread(QThread):
    def __init__(self, pid: int, interval: float):
        super().__init__()
        self.signals = ProcessCpuMonitorSignals()
        self.monitor = ProcessCpuMonitor(pid, interval)
        self.monitor.add_handler_on("updated", self.signals.updated.emit)
        self.monitor.add_handler_on("started", self.signals.started.emit)
        self.monitor.add_handler_on("finished", self.signals.finished.emit)

    def run(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()


class GlobalCpuMonitorThread(QThread):
    def __init__(self, interval: float):
        super().__init__()
        self.signals = GlobalCpuMonitorSignals()
        self.monitor = GlobalCpuMonitor(interval)
        self.monitor.add_handler_on("updated", self.signals.updated.emit)
        self.monitor.add_handler_on("started", self.signals.started.emit)
        self.monitor.add_handler_on("finished", self.signals.finished.emit)

    def run(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()


class ProcessCpuMonitorViewModel(QObject):

    def __init__(self, process_identifier: str | int | None = None, interval: float = 0.5):
        super().__init__()
        self._process_identifier: str | int | None = None
        self._process: psutil.Process | None = None
        self._thread: ProcessCpuMonitorThread | None = None
        self._interval = interval

        self.signals = ProcessCpuMonitorSignals()

        # Possible initialisation du process et moniteur immédiate
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
        self._thread = ProcessCpuMonitorThread(self._process.pid, self._interval)
        self._thread.signals.updated.connect(self.signals.updated.emit)
        self._thread.signals.started.connect(self.signals.started.emit)
        self._thread.signals.finished.connect(self.signals.finished.emit)

    def start(self):
        if self._thread:
            self._thread.start()

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread = None


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
        self._thread.signals.started.connect(self.signals.started.emit)
        self._thread.signals.finished.connect(self.signals.finished.emit)

        self._thread.start()

    def stop(self):
        if self._thread:
            self._thread.stop()
            self._thread = None


class PCMView(QWidget):
    def __init__(self, vm: ProcessCpuMonitorViewModel):
        super().__init__()
        self.vm = vm

        self.setup_ui()
        self.setup_signals()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.finished_message = QLabel()
        self.finished_message.setVisible(False)
        layout.addWidget(self.finished_message)

    def setup_signals(self):
        self.vm.signals.updated.connect(self.on_updated)
        self.vm.signals.started.connect(self.on_started)
        self.vm.signals.finished.connect(self.on_finished)

    def on_finished(self, success: bool, message: str):
        self.finished_message.setVisible(True)
        self.finished_message.setText(message)
        if not success:
            self.finished_message.setStyleSheet("color: red")


def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Exemple utilisation ProcCpuPercents")
    window.setGeometry(100, 100, 800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
