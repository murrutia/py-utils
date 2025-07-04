import abc
import time
from collections import deque
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


class BaseMonitor(abc.ABC):
    """Classe de base abstraite pour les moniteurs de ressources.

    Gère le cycle de vie (start/stop), la boucle de surveillance et le système
    d'événements (handlers). Les classes filles doivent implémenter les méthodes
    _setup et _run_loop.
    """

    def __init__(self, interval: float = 1.0, history_length: int = 0):
        self.interval = interval
        self._handlers: dict[MonitorEvent, list[Callable]] = {event: [] for event in MonitorEvent}
        self._is_running = False
        self.history_length = history_length
        # Initialise un deque avec une taille max si history_length > 0, sinon None
        self.history = deque(maxlen=self.history_length) if self.history_length > 0 else None

    @abc.abstractmethod
    def _setup(self):
        """Méthode pour l'initialisation spécifique avant le début de la boucle."""
        pass

    @abc.abstractmethod
    def _run_loop(self):
        """Contient la logique principale de la boucle de surveillance."""
        pass

    def start(self):
        """Démarre la surveillance dans une boucle."""
        if self._is_running:
            print(f"{self.__class__.__name__} est déjà en cours d'exécution.")
            return

        self._is_running = True
        try:
            self._setup()
            self._run_loop()
            # La boucle s'est terminée normalement (via self.stop())
            self._apply_handlers_on(MonitorEvent.FINISHED, True, "Surveillance terminée.")
        except Exception as e:
            self._apply_handlers_on(MonitorEvent.FINISHED, False, f"Erreur inattendue: {e}")
        finally:
            self._is_running = False

    def stop(self):
        """Demande l'arrêt de la boucle de surveillance."""
        self._is_running = False

    def is_running(self) -> bool:
        """Retourne True si le moniteur est en cours d'exécution."""
        return self._is_running

    def add_handler_on(self, event_type: MonitorEvent | str, handler: Callable) -> None:
        """Ajoute un handler pour un type d'événement spécifique."""
        if isinstance(event_type, str):
            try:
                event_type = MonitorEvent[event_type.upper()]
            except KeyError:
                raise ValueError(f"Type d'événement non supporté: {event_type}")

        if event_type not in self._handlers:
            raise ValueError(f"Type d'événement non supporté: {event_type}")
        self._handlers[event_type].append(handler)

    def _apply_handlers_on(self, event_type: MonitorEvent, *args, **kwargs):
        """Exécute tous les handlers pour un type d'événement spécifique."""
        # Si l'historique est activé et que c'est un événement de mise à jour,
        # on stocke les données.
        if event_type == MonitorEvent.UPDATED and self.history is not None:
            self.history.append(args)
        for handler in self._handlers[event_type]:
            handler(*args, **kwargs)


class CpuCoresMonitor(BaseMonitor):
    """Observation de l'utilisation globale du CPU du système.

    Les handlers pour les différents événements doivent avoir les signatures suivantes :

    - MonitorEvent.STARTED: `Callable[[], None]`
    - MonitorEvent.UPDATED: `Callable[[float, list[float]], None]`
      Arguments:
        cpu_global (float) - Pourcentage d'utilisation CPU global du système.
        cpu_percents (list[float]) - Liste des pourcentages d'utilisation CPU par cœur.

    - MonitorEvent.FINISHED: `Callable[[bool, str], None]`
    """

    def __init__(
        self, interval: float = 0.3, smoothing_duration_s: float = 1.0, history_length: int = 0
    ):
        """
        Initialise le moniteur de CPU global.

        Args:
            interval (float): Intervalle de mise à jour en secondes.
            smoothing_duration_s (float): Durée en secondes pour la moyenne mobile.
                                          Mettre à 0 pour désactiver le lissage.
            history_length (int): Nombre de points de données à conserver dans l'historique. 0 pour désactiver.
        """
        super().__init__(interval, history_length)
        # Calcule le nombre d'échantillons nécessaires pour couvrir la durée de lissage
        self._smoothing_window = max(1, round(smoothing_duration_s / self.interval))
        self._global_history = deque(maxlen=self._smoothing_window)
        self._per_cpu_history: list[deque] = []

    def _setup(self):
        """Initialise les mesures psutil."""
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(percpu=True, interval=None)
        # Initialiser les tampons de l'historique avec des zéros
        self._global_history.extend([0.0] * self._smoothing_window)
        num_cores = psutil.cpu_count()
        self._per_cpu_history = [deque(maxlen=self._smoothing_window) for _ in range(num_cores)]
        for core_history in self._per_cpu_history:
            core_history.extend([0.0] * self._smoothing_window)

        self._apply_handlers_on(MonitorEvent.STARTED)

        # Pré-remplir l'historique principal avec des zéros pour que les vues (sparkline) aient une taille fixe dès le départ.
        if self.history is not None:
            padding_element = (0.0, [0.0] * num_cores)
            self.history.extend([padding_element] * self.history_length)

    def _run_loop(self):
        """Boucle de surveillance pour le CPU global."""
        while self._is_running:
            time.sleep(self.interval)
            if not self._is_running:
                break

            # Obtenir les valeurs brutes
            raw_global = psutil.cpu_percent(interval=None)
            raw_per_cpu = psutil.cpu_percent(percpu=True, interval=None)

            # Mettre à jour l'historique
            self._global_history.append(raw_global)
            for i, core_val in enumerate(raw_per_cpu):
                if i < len(self._per_cpu_history):
                    self._per_cpu_history[i].append(core_val)

            # Calculer les moyennes
            smoothed_global = sum(self._global_history) / len(self._global_history)
            smoothed_per_cpu = [
                sum(core_hist) / len(core_hist) for core_hist in self._per_cpu_history
            ]

            # Émettre les valeurs lissées
            self._apply_handlers_on(MonitorEvent.UPDATED, smoothed_global, smoothed_per_cpu)

    def get_cpu_history(self):
        return [a for a, b in self.history]

    def get_cores_history(self):
        return [b for a, b in self.history]


class MemoryMonitor(BaseMonitor):
    """Observation de l'utilisation de la mémoire (RAM et SWAP).

    Les handlers pour les différents événements doivent avoir les signatures suivantes :

    - MonitorEvent.STARTED: `Callable[[], None]`
    - MonitorEvent.UPDATED: `Callable[[psutil._common.snetio, psutil._common.sswap], None]`
      Arguments:
        vmem (psutil._common.snetio) - Informations sur la mémoire virtuelle.
        swap (psutil._common.sswap) - Informations sur la mémoire swap.

    - MonitorEvent.FINISHED: `Callable[[bool, str], None]`
    """

    def __init__(self, interval: float = 2.0, history_length: int = 0):
        """
        Initialise le moniteur de mémoire.
        """
        super().__init__(interval, history_length)

    def _setup(self):
        """Émet l'événement de démarrage."""
        self._apply_handlers_on(MonitorEvent.STARTED)

    def _run_loop(self):
        """Boucle de surveillance pour la mémoire."""
        while self._is_running:
            vmem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            self._apply_handlers_on(MonitorEvent.UPDATED, vmem, swap)
            time.sleep(self.interval)
            if not self._is_running:
                break


class ProcessCpuMonitor(BaseMonitor):
    """Observation de l'utilisation du CPU d'un processus spécifique.

    Les handlers pour les différents événements doivent avoir les signatures suivantes :
    - MonitorEvent.STARTED: `Callable[[int, str], None]` (pid, name)
    - MonitorEvent.UPDATED: `Callable[[float], None]` (proc_cpu_percent)
    - MonitorEvent.FINISHED: `Callable[[bool, str], None]`
    """

    def __init__(self, pid: int, interval: float = 0.3, history_length: int = 0):
        super().__init__(interval, history_length)
        self._pid = pid
        self._proc: psutil.Process | None = None
        self._n_cpu = psutil.cpu_count()

    def _setup(self):
        """Trouve le processus et émet l'événement STARTED."""
        self._proc = psutil.Process(self._pid)
        # Le premier appel retourne 0.0, on l'utilise pour initialiser.
        self._proc.cpu_percent(interval=None)
        self._apply_handlers_on(MonitorEvent.STARTED, self._proc.pid, self._proc.name())

    def _run_loop(self):
        """Boucle de surveillance pour le CPU du processus."""
        try:
            while self._is_running:
                # L'appel est bloquant pour la durée de l'intervalle
                proc_cpu_percent_raw = self._proc.cpu_percent(interval=self.interval)
                if not self._is_running:  # Vérifier après l'intervalle
                    break
                proc_cpu_percent = proc_cpu_percent_raw / self._n_cpu
                self._apply_handlers_on(MonitorEvent.UPDATED, proc_cpu_percent)
        except psutil.NoSuchProcess:
            # Le processus s'est terminé, c'est une fin normale.
            self._apply_handlers_on(MonitorEvent.FINISHED, True, "Le processus s'est terminé.")
            self._is_running = False  # Assure que la boucle externe s'arrête

    def get_pid(self) -> int:
        """Retourne le PID du processus surveillé."""
        return self._pid
