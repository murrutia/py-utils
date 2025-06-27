#!/usr/bin/env python3

import argparse
import curses
import os
import signal
import sys
import threading
import time

import psutil

from py_utils.misc import CursesContext, create_progress_bar, percent_to_rgb
from py_utils.process import ProcessCpuPercents, find_process_by_id_or_name


class TopLikeDisplay:
    """Gère l'affichage pour la surveillance CPU de type 'top'."""

    def __init__(self, cc: CursesContext, pid: int, process_name: str):
        self.cc = cc
        self.pid = pid
        self.process_name = process_name
        self._init_color_pairs()

    def _init_color_pairs(self):
        """Initialise les paires de couleurs curses nécessaires."""
        self.pair_green = self.cc.get_color_pair(curses.COLOR_GREEN)
        self.pair_yellow = self.cc.get_color_pair(curses.COLOR_YELLOW)
        self.pair_red = self.cc.get_color_pair(curses.COLOR_RED)
        self.pair_cyan = self.cc.get_color_pair(curses.COLOR_CYAN)
        self.pair_white_bold = self.cc.get_color_pair(curses.COLOR_WHITE) | curses.A_BOLD

    def _percent_to_pair(self, percent: float) -> int:
        """Retourne une paire de couleur en fonction d'un pourcentage."""
        if percent > 80:
            return self.pair_red
        if percent > 50:
            return self.pair_yellow
        return self.pair_green

    def on_started(self, message: str):
        """Affiche le message de démarrage de la surveillance."""
        self.cc.erase()
        y = 0
        self.cc.addstr(y, 0, f"Surveillance du processus {self.process_name} (PID: {self.pid})...")
        y += 1
        self.cc.addstr(y, 0, message)
        y += 1
        self.cc.addstr(y, 0, "-" * 80)
        self.cc.refresh()

    def on_finished(self, success: bool, message: str):
        """Affiche le message de fin de surveillance."""
        self.cc.erase()
        y = 0
        self.cc.addstr(y, 0, "Surveillance terminée : ")
        if success:
            self.cc.addstr(y, 24, "SUCCÈS", self.pair_green)
            self.cc.addstr(y, 32, f" - {message}")
        else:
            self.cc.addstr(y, 24, "ÉCHEC", self.pair_red)
            self.cc.addstr(y, 31, f" - {message}")
        self.cc.refresh()

    def on_update(self, proc_cpu_percent: float, cpu_global: float, cpu_percents: list[float]):
        """Met à jour et affiche les informations CPU."""
        self.cc.erase()
        y = 0  # Toujours commencer à la ligne 0 après un erase()

        # --- Ligne de titre ---
        self.cc.addstr(y, 0, "Moniteur CPU - Processus : ")
        self.cc.addstr(y, 26, f"{self.process_name} (PID: {self.pid})", self.pair_cyan)
        y += 1
        self.cc.addstr(y, 0, f"Dernière mise à jour : {time.strftime('%Y-%m-%d %H:%M:%S')}")
        y += 1
        self.cc.addstr(y, 0, "-" * 80)
        y += 1

        # --- Affichage combiné des cœurs et de la barre verticale globale ---
        num_cores = len(cpu_percents)
        cores_per_line = 2  # Ajustez pour s'adapter à la largeur de votre terminal
        num_core_lines = (num_cores + cores_per_line - 1) // cores_per_line

        # --- Global CPU usage ---
        cpu_pair = self._percent_to_pair(cpu_global)
        cpu_bar_str = create_progress_bar(cpu_global, width=50)
        self.cc.addstr(y, 0, "Utilisation CPU globale : ")
        self.cc.addstr(y, 30, f"{cpu_global:.2f}%", cpu_pair)
        self.cc.addstr(y, 38, f" [{cpu_bar_str}]", cpu_pair)
        y += 1

        # --- Cores CPU usage ---
        self.cc.addstr(y, 0, "Utilisation par cœur :")
        y += 1  # Incrémenter y après avoir écrit la ligne

        # --- Boucle d'affichage des cœurs et de la barre verticale ---
        for i in range(num_core_lines):
            current_y = y + i

            x_offset = 0
            for j in range(cores_per_line):
                core_idx = i * cores_per_line + j
                if core_idx < num_cores:
                    core_percent = cpu_percents[core_idx]
                    bar_str = create_progress_bar(core_percent, width=10)
                    pair = self._percent_to_pair(core_percent)

                    self.cc.addstr(current_y, x_offset, f"  Cœur {core_idx+1:<2}: ")
                    self.cc.addstr(current_y, x_offset + 12, f"{core_percent:5.1f}%", pair)
                    self.cc.addstr(current_y, x_offset + 18, f" [{bar_str}]", pair)
                    x_offset += 35  # Espace pour la colonne suivante

        y += num_core_lines
        self.cc.addstr(y, 0, "-" * 80)
        y += 1

        # --- Barre horizontale pour le processus spécifique ---
        proc_pair = self._percent_to_pair(proc_cpu_percent)
        proc_bar_str = create_progress_bar(proc_cpu_percent, width=50)
        self.cc.addstr(y, 0, f"CPU Processus ({self.process_name}) : ")
        self.cc.addstr(y, 30, f"{proc_cpu_percent:.2f}%", proc_pair)  # Correction: Utiliser y ici
        self.cc.addstr(y, 38, f" [{proc_bar_str}]", proc_pair)
        y += 1

        self.cc.addstr(
            y,
            0,
            f"  (Ce pourcentage est normalisé par rapport à la capacité totale de tous les cœurs ({psutil.cpu_count()}))",
        )
        y += 1

        self.cc.addstr(y, 0, "-" * 80)
        y += 1
        self.cc.addstr(y, 0, "Appuyez sur Ctrl+C pour arrêter.")  # Correction: Utiliser y ici
        y += 1
        self.cc.refresh()


def main():
    parser = argparse.ArgumentParser(description="Surveille l'utilisation du CPU d'un processus.")
    parser.add_argument("id", type=str, help="PID ou nom du processus à surveiller")
    parser.add_argument(
        "-i", "--interval", type=float, default=1.0, help="Intervalle de mise à jour (en secondes)"
    )

    args = parser.parse_args()

    try:
        process_info = find_process_by_id_or_name(args.id)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError) as e:
        print(f"Erreur : {e}", file=sys.stderr)
        if isinstance(e, psutil.AccessDenied):
            print(
                "Astuce : Essayez d'exécuter le script en tant qu'administrateur/root.",
                file=sys.stderr,
            )
        sys.exit(1)

    with CursesContext() as cc:

        display = TopLikeDisplay(cc, process_info.pid, process_info.name())
        monitor = ProcessCpuPercents(process_info.pid, interval=args.interval)

        # Attache les callbacks de l'afficheur au moniteur
        monitor.add_handler_on("started", display.on_started)
        monitor.add_handler_on("finished", display.on_finished)
        monitor.add_handler_on("updated", display.on_update)

        monitor_thread = threading.Thread(target=monitor.start)

        # Gère le signal Ctrl+C pour un arrêt propre
        def signal_handler(sig, frame):
            # Ne pas printer ici pour éviter de corrompre l'affichage
            monitor.stop()

        signal.signal(signal.SIGINT, signal_handler)

        monitor_thread.start()
        # Le thread principal attend simplement que le thread de surveillance se termine.
        # Il se terminera soit parce que monitor.stop() a été appelé (via Ctrl+C),
        # soit parce que le processus surveillé a disparu, ce qui termine la boucle du moniteur.
        monitor_thread.join()


if __name__ == "__main__":
    main()
