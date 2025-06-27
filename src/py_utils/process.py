from enum import Enum, auto
from typing import Callable

import psutil


def find_process_by_id_or_name(identifier: str) -> psutil.Process:
    """
    Tente de trouver un processus par son PID ou son nom.

    Args:
        identifier (str): Le PID (sous forme de chaîne) ou le nom du processus.

    Returns:
        psutil.Process: un objet Process si un processus unique est trouvé.
    Raises:
        psutil.NoSuchProcess: Si aucun processus n'est trouvé avec le PID donné.
        psutil.AccessDenied: Si l'accès au processus est refusé (pour un PID donné).
        ValueError: Si plusieurs processus correspondent au nom fourni.
    """
    try:
        pid = int(identifier)
        try:
            proc = psutil.Process(pid)
            return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            # Laisse l'appelant gérer l'exception
            raise e
    except ValueError:  # L'identifiant n'est pas un PID, on suppose que c'est un nom
        # Supposons que c'est un nom de processus
        found_procs: list[dict] = []
        for proc in psutil.process_iter(["pid", "name"]):
            if proc.info["name"] == identifier:
                found_procs.append(proc.info)

        if not found_procs:
            raise ValueError(f"Aucun processus trouvé avec le nom '{identifier}'.")
        elif len(found_procs) > 1:
            error_msg = f"Plusieurs processus trouvés avec le nom '{identifier}':\n"
            for p_info in found_procs:
                error_msg += f"  - PID : {p_info['pid']}, Nom : {p_info['name']}\n"
            error_msg += "Veuillez spécifier un PID unique."
            raise ValueError(error_msg)
        else:
            return psutil.Process(found_procs[0]["pid"])


class MonitorEvent(Enum):
    """Définit les types d'événements pour le moniteur de processus."""

    STARTED = auto()
    UPDATED = auto()
    FINISHED = auto()


class ProcessCpuPercents:
    """Observation de l'utilisation du CPU d'un processus.

    Chaque update contient le pourcentage d'utilisation du CPU du processus (rapportée à la machine entière,
    contrairement à psutil.cpu_percent qui renvoie une valeur par rapport à un coeur), le pourcentage d'utilisation
    globale du système et la liste des pourcentages d'utilisation par coeur.

    Les handlers pour les différents événements doivent avoir les signatures suivantes :
    - MonitorEvent.STARTED (ou "started"): Callable[[str], None]
      Arguments: message (str) - Un message descriptif sur le démarrage de la surveillance.

    - MonitorEvent.UPDATED (ou "updated"): Callable[[float, float, list[float]], None]
      Arguments:
        proc_cpu_percent (float) - Pourcentage d'utilisation CPU du processus (normalisé par rapport à la capacité totale de la machine).
        cpu_global (float) - Pourcentage d'utilisation CPU global du système.
        cpu_percents (list[float]) - Liste des pourcentages d'utilisation CPU par cœur.

    - MonitorEvent.FINISHED (ou "finished"): Callable[[bool, str], None]
      Arguments:
        success (bool) - True si la surveillance s'est terminée avec succès ou si le processus s'est arrêté normalement, False si une erreur est survenue.
        message (str) - Un message descriptif sur la conclusion de la surveillance.
    """

    def __init__(self, pid: int, interval: float = 0.1):
        self._pid = pid
        self.interval = interval

        self._handlers: dict[MonitorEvent, list[Callable]] = {event: [] for event in MonitorEvent}

        self._proc = None
        self._is_running = False

    def start(self):

        if self._is_running:
            print("L'observation du processus est déjà en cours.")
            return

        try:

            self._proc = psutil.Process(self._pid)
            self._is_running = True

            n_cpu = psutil.cpu_count()

            self._apply_handlers_on(MonitorEvent.STARTED, "Démarrage de l'observation du processus")

            # Initialisation pour le premier affichage immédiat
            proc_cpu_percent = 0.0
            cpu_global = 0.0
            cpu_percents = [0.0] * n_cpu

            # Affiche les valeurs initiales (zéros)
            self._apply_handlers_on(
                MonitorEvent.UPDATED, proc_cpu_percent, cpu_global, cpu_percents
            )

            while True:
                # Vérifie l'état d'arrêt AVANT de commencer une nouvelle mesure
                if not self._is_running:
                    break

                # Mesure bloquante pour obtenir les nouvelles données
                proc_cpu_percent_raw = self._proc.cpu_percent(interval=self.interval)
                proc_cpu_percent = proc_cpu_percent_raw / n_cpu

                cpu_global = psutil.cpu_percent(interval=None)
                cpu_percents = psutil.cpu_percent(percpu=True, interval=None)

                # Affiche les données fraîches
                self._apply_handlers_on(
                    MonitorEvent.UPDATED, proc_cpu_percent, cpu_global, cpu_percents
                )

            self._apply_handlers_on(
                MonitorEvent.FINISHED, True, "Observation du processus terminée."
            )

        except psutil.NoSuchProcess:
            self._apply_handlers_on(
                MonitorEvent.FINISHED, True, "Processus arrivé en fin d'exécution."
            )
        except Exception as e:
            self._apply_handlers_on(
                MonitorEvent.FINISHED, False, f"Erreur lors de l'observation du processus : {e}"
            )
        finally:
            # Assure que le statut est bien "non-running" à la fin
            self._is_running = False

    def add_handler_on(self, event_type: MonitorEvent | str, handler: Callable) -> None:
        """
        Ajoute un handler pour un type d'événement spécifique.
        Le type d'événement peut être un membre de MonitorEvent ou une chaîne de caractères
        correspondant au nom du membre (ex: "STARTED", "UPDATED", "FINISHED").

        Args:
            event_type (MonitorEvent | str): Le type d'événement auquel attacher le handler.
            handler (Callable): La fonction (ou méthode) à appeler lorsque l'événement se produit.
                                Sa signature doit correspondre au type d'événement.

        Raises:
            ValueError: Si le type d'événement n'est pas supporté.
        """
        if isinstance(event_type, str):
            event_type = MonitorEvent[event_type.upper()]

        if event_type not in self._handlers:
            raise ValueError(f"Type d'événement non supporté: {event_type}")
        self._handlers[event_type].append(handler)

    def _apply_handlers_on(self, event_type: MonitorEvent, *args, **kwargs):
        """Exécute tous les handlers pour un type d'événement spécifique."""
        for handler in self._handlers[event_type]:
            handler(*args, **kwargs)

    def stop(self):
        self._is_running = False

    def is_running(self):
        return self._is_running

    def get_pid(self):
        return self._pid
