import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

from py_utils.misc import percent_to_rgb
from py_utils.stats import CpuCoresMonitor


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Moniteur CPU - Tkinter")
        self.geometry("400x100")

        # La queue est le canal de communication entre le thread moniteur et le thread UI
        self.update_queue = queue.Queue()

        # --- Configuration de l'UI ---
        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.cpu_label = ttk.Label(
            self.main_frame, text="CPU Global: --.-%", font=("Helvetica", 14)
        )
        self.cpu_label.pack(pady=10)

        # --- Démarrage du moniteur ---
        self.monitor_thread = None
        self.start_monitor()

        # --- Démarrage de la boucle de traitement de la queue ---
        self.process_queue()

        # S'assurer que le thread s'arrête proprement à la fermeture
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_monitor(self):
        """Crée et démarre le moniteur CPU dans un thread séparé."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return

        # On utilise le moniteur existant de py_utils.stats
        self.cpu_monitor = CpuCoresMonitor(interval=0.5)

        # Le handler du moniteur met simplement les données dans la queue.
        # On préfixe avec un nom ("cpu_update") pour pouvoir gérer plusieurs sources plus tard.
        self.cpu_monitor.add_handler_on(
            "updated", lambda *args: self.update_queue.put(("cpu_update", args))
        )

        # On lance le moniteur dans un thread daemon pour qu'il ne bloque pas la sortie.
        self.monitor_thread = threading.Thread(target=self.cpu_monitor.start, daemon=True)
        self.monitor_thread.start()

    def process_queue(self):
        """
        Traite les messages de la queue. C'est le cœur de la mise à jour de l'UI.
        """
        try:
            # On essaie de récupérer un message sans bloquer
            message_type, data = self.update_queue.get_nowait()

            if message_type == "cpu_update":
                cpu_global, cpu_cores = data
                self.cpu_label.config(text=f"CPU Global: {cpu_global:.1f}%")

        except queue.Empty:
            # S'il n'y a rien dans la queue, ce n'est pas grave.
            pass
        finally:
            # On redemande à Tkinter d'appeler cette fonction dans 100ms
            self.after(100, self.process_queue)

    def on_closing(self):
        """Gère la fermeture de la fenêtre."""
        print("Arrêt du moniteur...")
        if self.cpu_monitor:
            self.cpu_monitor.stop()
        # Le thread est daemon, il s'arrêtera avec le programme principal.
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
