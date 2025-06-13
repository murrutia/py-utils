import inspect
import os
from click import Path


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
