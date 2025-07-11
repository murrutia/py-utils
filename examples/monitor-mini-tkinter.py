import multiprocessing
import queue
import sys
import tkinter as tk
from tkinter import ttk

import psutil

from py_utils.misc import percent_to_rgb
from py_utils.widgets_tk import (
    CpuCoresMonitorViewModel,
    CpuHeatmapWidget,
    MemoryMonitorViewModel,
    MeterWidget,
    ProcessMonitorViewModel,
    SparklineCanvas,
)


# Fonction worker qui sera exécutée dans un processus séparé pour consommer du CPU
def cpu_worker():
    """Une fonction simple qui tourne en boucle pour utiliser 100% d'un cœur CPU."""
    while True:
        pass


class MonitorAppView(ttk.Frame):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.pack(fill=tk.BOTH, expand=True)

        # Créer et démarrer le processus worker qui consomme du CPU
        self.worker_process = multiprocessing.Process(target=cpu_worker, daemon=True)
        self.worker_process.start()

        # 1. Créer les ViewModels
        history_length = 100
        self.vms = {
            "cpu": CpuCoresMonitorViewModel(interval=0.5, history_length=history_length),
            "mem": MemoryMonitorViewModel(interval=1.0),
            "proc": ProcessMonitorViewModel(process_identifier=self.worker_process.pid),
        }

        # 2. Créer l'interface
        self.widgets = []
        self.setup_ui()

        # 3. Démarrer les moniteurs (qui remplissent la queue en arrière-plan)
        for vm in self.vms.values():
            vm.start()

        # 4. Démarrer le polling sur les ViewModels (qui notifient les widgets)
        for vm in self.vms.values():
            vm.start_polling(self)

    def setup_ui(self):
        """Crée et configure les widgets de l'interface."""
        # --- Section CPU Global ---
        # cpu_frame = ttk.LabelFrame(self, text="CPU Global", padding=10)
        cpu_frame = tk.Frame(self)
        cpu_frame.pack(fill=tk.X, padx=10, pady=5)
        self.cpu_sparkline = SparklineCanvas(cpu_frame, vm=self.vms["cpu"], height=50)
        self.cpu_sparkline.pack(fill=tk.X, expand=True, padx=5, pady=5)
        self.widgets.append(self.cpu_sparkline)

        # --- Section CPU Heatmap ---
        heatmap_frame = ttk.LabelFrame(self, text="CPU Cores", padding=10)
        heatmap_frame.pack(fill=tk.X, padx=10, pady=5)
        self.cpu_heatmap = CpuHeatmapWidget(heatmap_frame, vm=self.vms["cpu"])
        self.cpu_heatmap.pack(fill=tk.BOTH, expand=True)
        self.widgets.append(self.cpu_heatmap)
        # --- Section Mémoire ---
        mem_frame = ttk.LabelFrame(self, text="Mémoire (RAM)", padding=10)
        mem_frame.pack(fill=tk.X, padx=10, pady=5)
        mem_widget = MeterWidget(
            mem_frame,
            vm=self.vms["mem"],
            label_text="RAM",
            value_extractor=lambda data: data[0].percent,
            text_formatter=lambda data: f"{data[0].used / 1e9:.1f}/{data[0].total / 1e9:.1f} GB ({data[0].percent:.0f}%)",
        )
        mem_widget.pack(fill=tk.X, expand=True)
        self.widgets.append(mem_widget)

        # --- Section Processus ---
        proc_frame = ttk.LabelFrame(
            self, text=f"Processus Worker (PID: {self.worker_process.pid})", padding=10
        )
        proc_frame.pack(fill=tk.X, padx=10, pady=5)

        # Frame pour contenir le widget et les boutons de contrôle
        control_frame = ttk.Frame(proc_frame)
        control_frame.pack(fill=tk.X, expand=True)

        proc_meter = MeterWidget(
            control_frame,
            vm=self.vms["proc"],
            label_text="Process",
            value_extractor=lambda data: data[0],
            text_formatter=lambda data: f"{data[0]:.1f}%",
        )
        proc_meter.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.widgets.append(proc_meter)

        # Ajout des boutons de contrôle
        self.pause_button = ttk.Button(control_frame, text="Pause", command=self.on_pause_process)
        self.pause_button.pack(side=tk.LEFT, padx=(10, 2))

        self.resume_button = ttk.Button(
            control_frame, text="Reprendre", command=self.on_resume_process
        )
        self.resume_button.pack(side=tk.LEFT, padx=2)
        self.resume_button.config(state=tk.DISABLED)  # Désactivé au démarrage

    def on_closing(self):
        """Arrête les moniteurs et le processus worker."""
        print("Arrêt des moniteurs...")
        for vm in self.vms.values():
            vm.stop()

        if self.worker_process and self.worker_process.is_alive():
            print("Arrêt du processus worker...")
            self.worker_process.terminate()
            self.worker_process.join()

    def on_pause_process(self):
        """Met en pause le processus worker."""
        try:
            if self.worker_process and self.worker_process.is_alive():
                p = psutil.Process(self.worker_process.pid)
                p.suspend()
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.NORMAL)
                print("Processus worker mis en pause.")
        except psutil.NoSuchProcess:
            print("Le processus worker n'existe plus.")

    def on_resume_process(self):
        """Reprend l'exécution du processus worker."""
        try:
            if self.worker_process and self.worker_process.is_alive():
                p = psutil.Process(self.worker_process.pid)
                p.resume()
                self.pause_button.config(state=tk.NORMAL)
                self.resume_button.config(state=tk.DISABLED)
                print("Processus worker relancé.")
        except psutil.NoSuchProcess:
            print("Le processus worker n'existe plus.")


# --- Code pour lancer l'application ---
if __name__ == "__main__":
    # Nécessaire pour PyInstaller lors de l'utilisation de multiprocessing
    multiprocessing.freeze_support()

    root = tk.Tk()
    root.title("Exemple Moniteur Tkinter")
    root.geometry("600x500")

    app = MonitorAppView(master=root)

    def on_quit():
        """Fonction de nettoyage propre avant de quitter."""
        app.on_closing()
        root.destroy()

    # Gère la fermeture via le bouton de la fenêtre (tous OS)
    root.protocol("WM_DELETE_WINDOW", on_quit)

    # Gère la fermeture via le menu de l'application ou Cmd+Q (spécifique à macOS)
    if sys.platform == "darwin":
        # Cette commande intercepte l'action "Quit" du menu système de l'application.
        root.createcommand("tk::mac::Quit", on_quit)

    root.mainloop()
