#!/usr/bin/env python3

import atexit  # Running scripts before exiting
import curses  # Graphical interface library
import sys  # Exiting the script if requirements are not satisfied
import time  # Sleeping

import psutil  # Process management library

from py_utils.misc import CursesContext

# Global constants
header_message = "PyTop Simplifié - Vue d'ensemble du CPU"


def display_cpu_info(cc: CursesContext, cpu_percent_overall: float, cpu_per_core: list[float]):
    """Affiche les informations CPU formatées."""
    cc.erase()

    # Fonction interne pour créer les barres de progression
    def count_pipelines(perc: float) -> str:
        # S'assurer que le pourcentage est entre 0 et 100
        perc = max(0, min(100, perc))
        # Échelle sur 40 caractères
        dashes = "|" * int((float(perc) / 100) * 40)
        empty_dashes = " " * (40 - len(dashes))
        return dashes + empty_dashes

    cc.print_line(header_message, invert_colors=True)
    cc.print_line("")

    # Gets CPU usage
    cc.print_line(
        " CPU (Global) [%s] %5.1f%%" % (count_pipelines(cpu_percent_overall), cpu_percent_overall)
    )

    # Affichage de l'utilisation CPU par cœur
    for i, core_percent in enumerate(cpu_per_core):
        cc.print_line(f"   Cœur {i+1:<2}    [{count_pipelines(core_percent)}] {core_percent:5.1f}%")
    cc.print_line("")  # Ligne vide pour l'espacement
    cc.print_line("")  # Ligne vide pour l'espacement
    cc.print_line("Appuyez sur 'q' pour quitter.")
    cc.refresh()


# Main function
def main():

    interval = 1.0  # Intervalle de mise à jour par défaut (en secondes)

    try:
        with CursesContext() as cc:
            # Premier appel à psutil.cpu_percent() pour initialiser les compteurs
            # Les valeurs retournées par psutil.cpu_percent(interval=None) sont
            # les pourcentages depuis le dernier appel. Le premier appel retourne 0.0.
            psutil.cpu_percent(interval=None, percpu=True)  # Pour les cœurs individuels
            psutil.cpu_percent(interval=None, percpu=False)  # Pour le CPU global

            while True:
                # Récupérer les pourcentages CPU (non bloquant)
                cpu_percent_overall = psutil.cpu_percent(interval=None, percpu=False)
                cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)

                display_cpu_info(cc, cpu_percent_overall, cpu_per_core)  # Affiche les informations

                # Gérer les entrées utilisateur (non bloquant)
                key = cc.get_key()
                if key == ord("q"):  # 'q' pour quitter
                    break
                elif key == curses.KEY_RESIZE:  # Gérer le redimensionnement du terminal
                    cc.erase()  # Effacer et redessiner tout
                    cc.refresh()

                time.sleep(interval)  # Pause avant la prochaine mise à jour
    except KeyboardInterrupt:
        # Géré par curses.endwin() dans __exit__ du contexte
        pass
    except Exception as e:
        print(f"Une erreur s'est produite : {e}", file=sys.stderr)


# Calls main function
if __name__ == "__main__":
    main()
