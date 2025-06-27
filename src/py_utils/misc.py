import curses
import inspect
import os
from pathlib import Path


def demultiply_value(value: int | float) -> str:
    """Formate une valeur numérique en chaîne lisible (ex: 1024 -> 1K)."""
    value = float(value)
    i = 0
    dims = ["", "K", "M", "G", "T"]
    while value >= 1024 and i < len(dims) - 1:
        value /= 1024
        i += 1
    return f"{value:.2f}{dims[i]}".strip()  # Limiter à 2 décimales


def add_dir_to_path(dir: str | Path = "tmp"):
    """Ajoute un répertoire au PATH et le retourne.

    Si le chemin est relatif, il sera rendu absolu, relativement au script appelant cette fonction.
    """
    dir = Path(dir)
    if not dir.is_absolute():
        caller_file = inspect.stack()[1].filename
        caller_dir = Path(caller_file).parent
        dir = caller_dir / dir

    dir = dir.resolve()
    os.environ["PATH"] += os.pathsep + str(dir)
    return dir


def which_path(filename: Path | str) -> Path | None:
    """Comme pour la commande `which`, renvoie le chemin complet de filename s'il le trouve dans le PATH

    Vérifie si le fichier `filename` (qu'il soit exécutable ou pas)
    existe. S'il n'existe pas, il va chercher dans le PATH (environnement) et
    renvoie le premier chemin trouvé. Si le fichier n'existe pas dans le PATH,
    renvoie None.
    Args:
        filename (str): Nom du fichier ou dossier à chercher.
    Returns:
        Path | None: Chemin complet du fichier ou dossier s'il existe, sinon None.
    """
    # Vérifier d'abord si le fichier existe tel quel
    file_path = Path(filename)
    if file_path.exists():
        return file_path.resolve()

    # Si c'est un chemin absolu qui n'existe pas, retourner None
    if file_path.is_absolute():
        return None

    # Chercher dans le PATH
    for path in os.environ["PATH"].split(os.pathsep):
        potential_path = Path(path) / filename
        if potential_path.exists():
            return potential_path.resolve()

    return None


def percent_to_rgb(percent: float) -> tuple[int, int, int]:
    """
    Retourne un tuple de couleur RGB (0-255) basé sur un pourcentage (0-100).
    La couleur va du vert (faible pourcentage) au rouge (pourcentage élevé).
    """
    # S'assurer que le pourcentage est dans la plage [0, 100]
    percent = max(0, min(100, percent))

    percent_norm = percent / 100.0

    # Facteur d'intensité du rouge : permet d'ajuster à quelle vitesse le rouge s'intensifie.
    red_factor = 1.75
    percent_diff = 1.0 - percent_norm

    red = int(max(0, min(1, percent_norm * red_factor)) * 255)
    green = int(max(0, min(1, percent_diff * 2)) * 255)
    blue = 0

    return (red, green, blue)


def create_progress_bar(percent: float, width: int = 10) -> str:
    """
    Crée une chaîne de caractères représentant une barre de progression.

    Args:
        percent (float): Le pourcentage à représenter (0-100).
        width (int): La largeur totale de la barre en caractères.

    Returns:
        str: La chaîne de caractères de la barre de progression.
    """
    # Caractères Unicode pour une barre plus fine (8 niveaux de remplissage)
    bar_chars = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    num_chars = len(bar_chars) - 1  # Exclut le caractère vide

    total_ticks = width * num_chars  # Nombre total de "ticks" dans la barre
    filled_ticks = int(total_ticks * percent / 100)

    bar = ""
    for i in range(width):
        char_index = min(num_chars, (filled_ticks - i * num_chars))
        bar += bar_chars[char_index] if char_index >= 0 else bar_chars[0]

    return bar


class CursesContext:
    """
    Un gestionnaire de contexte pour initialiser et nettoyer l'environnement curses.
    Il encapsule également les opérations d'affichage.
    """

    def __init__(self):
        self._stdscr = None
        self._line_number = 0
        self._color_pairs = {}
        self._next_pair_id = 1

    def __enter__(self):
        self._stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()  # Réagit aux touches instantanément, sans attendre Entrée
        curses.curs_set(0)  # Cacher le curseur

        # Initialisation des couleurs
        if curses.has_colors():
            curses.start_color()
            # Utilise les couleurs par défaut du terminal pour le fond (-1)
            # Permet d'avoir un fond transparent
            curses.use_default_colors()

        self._stdscr.nodelay(True)  # Rendre getch() non bloquant
        self._stdscr.keypad(True)  # Permet de détecter les touches spéciales comme KEY_RESIZE
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restaure le terminal à son état normal."""
        curses.nocbreak()
        self._stdscr.keypad(False)
        curses.echo()
        curses.curs_set(1)  # Rétablir le curseur
        curses.endwin()

    def erase(self):
        """Efface l'écran et réinitialise le numéro de ligne."""
        self._stdscr.erase()
        self._line_number = 0

    def refresh(self):
        """Rafraîchit l'écran pour afficher les changements."""
        self._stdscr.refresh()

    def get_key(self):
        """Récupère une touche pressée (non bloquant)."""
        return self._stdscr.getch()

    def get_max_yx(self):
        """Retourne la hauteur et la largeur du terminal."""
        return self._stdscr.getmaxyx()

    def get_color_pair(self, fg: int, bg: int = -1) -> int:
        """
        Retourne l'ID d'une paire de couleurs. La crée si elle n'existe pas.
        Args:
            fg (int): ID de la couleur de premier plan (ex: curses.COLOR_RED).
            bg (int): ID de la couleur d'arrière-plan (-1 pour le fond par défaut).
        Returns:
            int: L'attribut de paire de couleurs à utiliser avec addstr.
        """
        if not curses.has_colors():
            return 0

        if (fg, bg) in self._color_pairs:
            return self._color_pairs[(fg, bg)]

        if self._next_pair_id < curses.COLOR_PAIRS:
            pair_id = self._next_pair_id
            curses.init_pair(pair_id, fg, bg)
            self._color_pairs[(fg, bg)] = curses.color_pair(pair_id)
            self._next_pair_id += 1
            return self._color_pairs[(fg, bg)]

        # Si plus de paires disponibles, retourne la première paire (souvent noir/blanc)
        return curses.color_pair(0)

    def addstr(self, y: int, x: int, text: str, attr: int = 0):
        """Wrapper sécurisé pour stdscr.addstr."""
        max_y, max_x = self.get_max_yx()
        if y < max_y and x < max_x:
            # Tronquer le texte s'il dépasse de l'écran
            remaining_width = max_x - x
            self._stdscr.addstr(y, x, text[:remaining_width], attr)

    def print_line(self, line: str, invert_colors: bool = False, color_pair: int = 0):
        """Écrit une ligne sur l'écran curses."""
        max_y, max_x = self.get_max_yx()

        # Ne pas écrire si nous dépassons la hauteur de l'écran
        if self._line_number >= max_y:
            return

        try:
            # Tronquer la ligne si elle est trop longue pour la largeur du terminal
            display_line = line[:max_x]
            if invert_colors:
                display_line += " " * (max_x - len(display_line))
                self.addstr(self._line_number, 0, display_line, curses.A_REVERSE)
            else:
                self.addstr(self._line_number, 0, display_line, color_pair)
        except curses.error:
            # Gérer les erreurs curses (ex: terminal trop petit après un redimensionnement)
            pass
        else:
            self._line_number += 1
