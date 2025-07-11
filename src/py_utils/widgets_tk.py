import enum
import inspect
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

import psutil

from py_utils.misc import percent_to_rgb
from py_utils.stats import (
    BaseMonitor,
    CpuCoresMonitor,
    MemoryMonitor,
    ProcessMonitor,
    find_process_by_id_or_name,
)


class BaseTkViewModel:
    """Classe de base pour les ViewModels Tkinter qui utilisent un moniteur."""

    def __init__(self):
        self._monitor: BaseMonitor | None = None
        self._thread: threading.Thread | None = None
        self._update_queue = queue.Queue()
        self._handlers = {"updated": [], "finished": []}

    def start(self):
        """Démarre le moniteur dans un thread dédié."""
        if not self._monitor:
            raise NotImplementedError(
                "Le `_monitor` doit être défini dans la sous-classe avant d'appeler start()."
            )

        if self._thread and self._thread.is_alive():
            return

        self._monitor.add_handler_on(
            "updated", lambda *args: self._update_queue.put(("updated", args))
        )
        self._monitor.add_handler_on(
            "finished", lambda *args: self._update_queue.put(("finished", args))
        )

        self._thread = threading.Thread(target=self._monitor.start, daemon=True)
        self._thread.start()

    def stop(self):
        """Arrête le moniteur."""
        if self._monitor and self._thread and self._thread.is_alive():
            self._monitor.stop()

    def add_handler(self, event_name: str, handler: callable):
        """Ajoute un handler pour un événement."""
        if event_name in self._handlers:
            self._handlers[event_name].append(handler)

    def start_polling(self, root_widget: tk.Widget):
        """Démarre la boucle de vérification de la queue et de notification des handlers."""

        def poll():
            try:
                event_name, data = self._update_queue.get_nowait()
                if event_name in self._handlers:
                    for handler in self._handlers[event_name]:
                        handler(*data)
            except queue.Empty:
                pass
            finally:
                root_widget.after(100, poll)

        poll()


class CpuCoresMonitorViewModel(BaseTkViewModel):
    """
    ViewModel pour le CpuCoresMonitor, adapté pour une utilisation avec Tkinter.

    Il gère le cycle de vie du moniteur dans un thread séparé et communique
    les mises à jour à l'interface utilisateur via une `queue.Queue`.
    """

    def __init__(self, interval=0.5, history_length=0):
        super().__init__()
        self._monitor = CpuCoresMonitor(interval=interval, history_length=history_length)

    def get_cpu_history(self):
        """Retourne l'historique de l'utilisation CPU Globale."""
        if self._monitor and self._monitor.history:
            return [cpu for cpu, cores in self._monitor.history]
        return []


class MemoryMonitorViewModel(BaseTkViewModel):
    """
    ViewModel pour le MemoryMonitor, adapté pour une utilisation avec Tkinter.
    """

    def __init__(self, interval=2.0, history_length=0):
        super().__init__()
        self._monitor = MemoryMonitor(interval=interval, history_length=history_length)


class ProcessMonitorViewModel(BaseTkViewModel):
    """
    ViewModel pour le ProcessMonitor, adapté pour une utilisation avec Tkinter.
    """

    def __init__(
        self, process_identifier: str | int, interval: float = 0.2, history_length: int = 0
    ):
        super().__init__()
        self._process_identifier = process_identifier
        self._interval = interval
        self._history_length = history_length

        self._process: psutil.Process | None = None

        self._attach_process()

    def _attach_process(self):
        """Trouve le processus basé sur l'identifiant et informe l'UI via la queue."""
        if self._thread and self._thread.is_alive():
            self.stop()
        try:
            self._process = find_process_by_id_or_name(self._process_identifier)
        except (ValueError, psutil.NoSuchProcess) as e:
            self._update_queue.put(("finished", (False, str(e))))
            self._process = None

    def start(self):
        """Démarre le moniteur si le processus a été trouvé."""
        if not self._process:
            return

        if self._thread and self._thread.is_alive():
            return

        self._monitor = ProcessMonitor(self._process.pid, self._interval, self._history_length)
        super().start()  # Appelle la logique de base pour démarrer le thread


class CustomProgressBar(tk.Canvas):
    def __init__(
        self, parent, length=200, width=10, bg="#555", fg="red", orientation=tk.HORIZONTAL
    ):
        if orientation == tk.HORIZONTAL:
            canvas_width = length
            canvas_height = width
        else:  # VERTICAL
            canvas_width = width
            canvas_height = length

        super().__init__(
            parent, width=canvas_width, height=canvas_height, bg=bg, highlightthickness=0
        )
        self.fg = fg
        self.value = 0
        self.orientation = orientation
        self.rect = self.create_rectangle(0, 0, canvas_width, canvas_height, fill=fg, outline="")
        self.set_value(0)  # Positionne le rectangle initialement
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        self.set_value(self.value)

    def set_value(self, value):
        self.value = max(0, min(100, value))
        w = self.winfo_width()
        h = self.winfo_height()
        if self.orientation == tk.HORIZONTAL:
            pixel_width = (w * self.value) / 100
            self.coords(self.rect, 0, 0, pixel_width, h)
        else:  # VERTICAL
            pixel_height = (h * self.value) / 100
            self.coords(self.rect, 0, h, w, h - pixel_height)

    def set_color(self, color):
        self.itemconfig(self.rect, fill=color)


class Tooltip:
    """
    Crée une infobulle (tooltip) pour un widget donné.
    """

    def __init__(self, widget, text_generator: callable):
        self.widget = widget
        self.text_generator = text_generator
        self.tip_window = None
        self.tip_label = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        # Affiche l'infobulle après un court délai (ex: 500ms)
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self):
        if self.tip_window:
            return

        text = self.text_generator()
        if not text:
            return

        # Positionne l'infobulle près du widget
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 1

        self.tip_window = tw = tk.Toplevel(self.widget)
        # Supprime les décorations de la fenêtre (bordure, barre de titre)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        self.tip_label = ttk.Label(
            tw,
            text=text,
            justify=tk.LEFT,
            background="#ffffe0",  # Jaune classique pour les infobulles
            relief=tk.SOLID,
            borderwidth=1,
            padding=(4, 2),
        )
        self.tip_label.pack()

    def update_text(self):
        if self.tip_window and self.tip_label:
            text = self.text_generator()
            if text:
                self.tip_label.config(text=text)
            else:
                self.hidetip()

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


class MeterWidget(ttk.Frame):
    """Un widget composite affichant un label, une barre de progression et une valeur."""

    def __init__(
        self,
        master,
        vm,
        label_text: str,
        value_extractor: Callable,
        text_formatter: Callable,
        tooltip_formatter: Callable | None = None,
        orientation=tk.HORIZONTAL,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.vm = vm
        self.value_extractor = value_extractor
        self.text_formatter = text_formatter
        self.tooltip_formatter = tooltip_formatter
        self.orientation = orientation
        self.last_data = None

        # --- Widgets internes ---
        self.value_label = ttk.Label(self, text="--.-%", font=("Helvetica", 10))

        if self.orientation == tk.HORIZONTAL:
            self.value_label.config(width=15)
            self.value_label.pack(side=tk.LEFT, padx=5)
            self.meter = CustomProgressBar(self, orientation=self.orientation)
            self.meter.pack(side=tk.LEFT, fill=tk.X, expand=True)
        else:  # VERTICAL
            self.meter = CustomProgressBar(self, orientation=self.orientation)
            self.meter.pack(side=tk.TOP, fill=tk.Y, expand=True, pady=(0, 5))
            self.value_label.pack(side=tk.TOP)

        # S'abonner aux événements du ViewModel
        self.vm.add_handler("updated", self.on_updated)
        self.vm.add_handler("finished", self.on_finished)

        if self.tooltip_formatter:

            def get_tooltip_text():
                if self.last_data:
                    return self.tooltip_formatter(self.last_data)
                return ""

            # Attacher le tooltip à la barre de progression elle-même
            self.tooltip = Tooltip(self.meter, text_generator=get_tooltip_text)
            # Et aussi au label, pour une meilleure expérience utilisateur
            self.tooltip_label = Tooltip(self.value_label, text_generator=get_tooltip_text)

    def on_updated(self, *data):
        """Callback pour l'événement 'updated'."""
        # data est un tuple, on le passe directement aux extracteurs
        self.last_data = data
        percent = self.value_extractor(data) or 0
        text = self.text_formatter(data)
        self.value_label.config(text=text)
        self.meter.set_value(percent)
        self._update_color(percent)

        if self.tooltip_formatter:
            self.tooltip.update_text()
            self.tooltip_label.update_text()

    def on_finished(self, ok: bool, msg: str):
        """Callback pour l'événement 'finished'."""
        self.value_label.config(text=msg)

    def _update_color(self, percent):
        color = percent_to_rgb(percent, return_type="hexa")
        self.value_label.config(foreground=color)
        self.meter.set_color(color)


class SparklineCanvas(tk.Canvas):
    def __init__(self, master=None, vm=None, **kwargs):
        kwargs.setdefault("bg", "#2e2e2e")
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)

        self.vm = vm
        self.history_data = []
        self.current_value = 0.0
        self.line_color = "#00ff00"

        # Redessiner si la taille du widget change
        self.bind("<Configure>", self._on_resize)

        # S'abonner aux événements du ViewModel
        self.vm.add_handler("updated", self.on_updated)
        self.vm.add_handler("finished", self.on_finished)

    def on_updated(self, current_value, cores):
        """Callback pour l'événement 'updated'."""
        self.current_value = current_value
        self.history_data = self.vm.get_cpu_history()
        self.line_color = percent_to_rgb(self.current_value, return_type="hexa")
        self._draw()

    def on_finished(self, ok: bool, msg: str):
        """Callback pour l'événement 'finished'."""
        # On pourrait afficher un message sur le canvas ici
        pass

    def _on_resize(self, event=None):
        self._draw()

    def _draw(self, event=None):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()

        if (
            not self.history_data
            or len(self.history_data) <= 1
            or width <= 1
            or height <= 1
            or not self.vm
        ):
            return

        # Lignes de fond
        for percent in [50, 100]:
            y = int(height - (percent / 100.0 * height))
            self.create_line(0, y, width, y, fill="gray", width=1)

        # Ligne des valeurs au cours du temps
        points = []
        num_points = len(self.history_data)
        # L'historique peut être plus long que la capacité du deque au début (rempli de 0)
        # On s'assure de ne pas diviser par zéro si l'historique est de taille 1.
        x_factor = num_points - 1 if num_points > 1 else 1
        for i, value in enumerate(self.history_data):
            x = width * i / x_factor
            y = height - (value / 100.0 * height)
            points.append((x, y))
        self.create_line(points, fill=self.line_color, width=2)

        # Affichage textuel de la valeur courante
        text = f"{self.current_value:.1f}%"
        self.create_text(
            width - 45,
            5,
            text="CPU : ",
            anchor="ne",
            fill="lightgray",
            font=("Helvetica", 9, "bold"),
        )
        self.create_text(
            width - 5,
            5,
            text=text,
            anchor="ne",
            fill=self.line_color,
            font=("Helvetica", 9, "bold"),
        )

        # --- Échelle de temps ---
        # On s'assure que le ViewModel et son moniteur interne sont accessibles
        if not (self.vm and hasattr(self.vm, "_monitor") and self.vm._monitor):
            return

        monitor = self.vm._monitor
        if not monitor.history_length or monitor.history_length <= 1:
            return

        total_seconds = monitor.history_length * monitor.interval
        time_font = ("Helvetica", 8)
        time_color = "#9e9e9e"  # Gris, pour être discret

        # Libellé de gauche (début de l'historique)
        left_label = f"-{int(total_seconds)}s"
        self.create_text(
            5, height - 2, text=left_label, anchor="sw", fill=time_color, font=time_font
        )

        # Libellé du milieu
        mid_label = f"-{int(total_seconds / 2)}s"
        self.create_text(
            width / 2, height - 2, text=mid_label, anchor="s", fill=time_color, font=time_font
        )

        # Libellé de droite (maintenant)
        right_label = "0s"
        self.create_text(
            width - 5, height - 2, text=right_label, anchor="se", fill=time_color, font=time_font
        )


class CpuHeatmapWidget(ttk.Frame):
    """Affiche une heatmap de l'utilisation des cœurs CPU avec des MeterWidget verticaux."""

    def __init__(self, master, vm: CpuCoresMonitorViewModel, **kwargs):
        super().__init__(master, **kwargs)
        self.vm = vm
        self.num_cores = psutil.cpu_count()
        self.core_widgets = []
        self.setup_ui()

    def setup_ui(self):
        """Crée les MeterWidgets verticaux pour chaque cœur."""
        for i in range(self.num_cores):

            core_widget = MeterWidget(
                self,
                vm=self.vm,
                label_text=f"C{i + 1}",  # Nom court pour le label
                value_extractor=lambda data, core_index=i: (
                    data[1][core_index] if core_index < len(data[1]) else 0
                ),
                text_formatter=lambda _: "",
                tooltip_formatter=lambda data, core_index=i: (
                    f"Cœur {core_index + 1}: {data[1][core_index]:.1f}%"
                    if core_index < len(data[1])
                    else ""
                ),
                orientation=tk.VERTICAL,
                width=20,  # Largeur fixe pour chaque barre
            )
            core_widget.pack(side=tk.LEFT, fill=tk.Y, expand=True, padx=2)
            self.core_widgets.append(core_widget)
