from datetime import datetime
import os
from zoneinfo import ZoneInfo
import re

from click import Path

DATETIME_HUMAN_FORMAT = os.getenv("DATETIME_HUMAN_FORMAT", "%Y-%m-%d %H:%M:%S")


def datetime_human(dt: datetime | str, fmt: str = DATETIME_HUMAN_FORMAT) -> str:
    """Convertit un datetime ou une chaîne en format lisible.

    Utilise dateutil si disponible, sinon version basique.
    """

    d = parse_datetime(dt) if isinstance(dt, str) else dt

    return d.strftime(fmt)


def parse_datetime(dt_str: str) -> datetime:
    """Analyse une chaîne de caractère pour renvoyer un objet datetime.

    Utilise dateutil si disponible, sinon version basique.
    """
    try:
        # Essayer d'abord dateutil si disponible
        from dateutil.parser import parse as parse_date

        d = parse_date(dt_str)
    except ImportError:
        # Fallback vers la version basique
        d = _parse_datetime_basic(dt_str)
    return d


def _parse_datetime_basic(dt_str: str) -> datetime:
    """Parser basique de datetime sans dépendance."""
    dt_str = dt_str.strip()

    # Essai avec fromisoformat
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
    except ValueError:
        pass

    dt_str = dt_str.replace("_", " ")
    # Formats courants
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Format de date non supporté: {dt_str}")


def duration_human(d: float | str | int, short: bool = True) -> str:
    """Convertit une durée en secondes en une chaîne de caractères lisible par l'homme.

    Si le paramètre short est True, les valeur d'heure et de minute ne seront pas incluses si elles sont nulles.
    Par exemple, 3661 secondes sera converti en "01h 01m 01s" ou "01m 01s" selon la valeur de short.
    """
    try:
        d_float = float(d)
    except ValueError:
        raise ValueError(
            f"Valeur de durée invalide: {d}. Doit être une valeur numérique ou une chaîne de caractère en réprésentant une."
        )

    total_milliseconds = int(d_float * 1000)
    ms = total_milliseconds % 1000
    total_seconds = total_milliseconds // 1000

    s = total_seconds % 60
    m = (total_seconds // 60) % 60
    h = total_seconds // 3600

    parts = []
    if h > 0 or not short:
        parts.append(f"{h:02d}h")
    if h > 0 or m > 0 or not short:
        parts.append(f"{m:02d}m")
    parts.append(f"{s:02d}s")

    dh = " ".join(parts)  # Utiliser join pour une construction plus propre

    if ms > 0 and not short:  # Vérifier si ms est > 0 avant d'ajouter
        dh += f"{ms:03d}ms"

    return dh.strip()


def tzlocutc(d: datetime) -> datetime:
    """Localise un datetime avec le timezone UTC s'il n'en a pas."""
    if d.tzinfo is None or d.tzinfo.utcoffset(d) is None:
        # Utiliser UTC comme timezone par défaut si aucune n'est présente
        d = d.replace(tzinfo=ZoneInfo("UTC"))
    return d


def get_date_from_filepath(filepath: Path | str) -> datetime:
    """
    Tente d'extraire une date d'un chemin de fichier, sinon utilise la date système.
    """
    filepath = Path(filepath)

    parts = filepath.resolve().as_posix().split("/")
    parts.reverse()

    # Les exemples qui suivent utilisent l'instant : 10:03:13 05/12/2021
    # et l'expression '(^)' représente un caractère non numérique
    for part in parts:
        # format : GMT20211205-100313(^)
        if r := re.search("GMT[0-9]{8}-[0-9]{6}([^0-9]|$)", part):
            r0 = r[0][3:] if len(r[0]) == 18 else r[0][3:-1]
            try:
                return tzlocutc(datetime.strptime(r0, "%Y%m%d-%H%M%S"))
            except ValueError:
                pass

        # format : 2021-12-05_10-03-13(^)
        if r := re.search(
            r"[1-2][0-9]{3}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}([^0-9]|$)", part
        ):
            r0 = r[0] if len(r[0]) == 19 else r[0][:-1]
            try:
                return tzlocutc(datetime.strptime(r0, "%Y-%m-%d_%H-%M-%S"))
            except ValueError:
                pass

        # format : 2021-12-05(^)
        if r := re.search(r"[1-2][0-9]{3}-[0-9]{2}-[0-9]{2}([^0-9]|$)", part):
            r0 = r[0] if len(r[0]) == 10 else r[0][:-1]
            try:
                return tzlocutc(datetime.strptime(r0, "%Y-%m-%d"))
            except ValueError:
                pass

        # format : 20211205(^)
        if r := re.search("[0-9]{6}([^0-9]|$)", part):
            try:  # les suites de 6 chiffres ne représentent pas toujours une date, donc on prend nos précautions
                r0 = r[0] if len(r[0]) == 6 else r[0][:-1]
                return tzlocutc(datetime.strptime(r0, "%y%m%d"))
            except ValueError:
                pass

    if filepath.exists():
        fstat = filepath.stat()
        # Retourne la date de création ou de dernière modification du fichier (avec la timezone du système)
        system_time = (
            datetime.fromtimestamp(fstat.st_ctime).astimezone()
            if fstat.st_ctime
            else datetime.fromtimestamp(fstat.st_mtime).astimezone()
        )
        return system_time

    return (
        datetime.today().astimezone()
    )  # Retourne la date actuelle avec la timezone du système si aucune date n'est trouvée


if __name__ == "__main__":
    paths = [
        "/tmp/GMT20211205-100313.mp4",
        "/tmp/2021-12-05_10-03-13.mp4",
        "/tmp/2021-12-05/recordings/2021-12-05_10-03-13.mp4",
        "/tmp/2021-12-04/recordings/2021-12-05_10-03-13.mp4",
        "/tmp/20211205.mp4",
        "/tmp/test.mp4",
    ]
    for path in paths:
        date = get_date_from_filepath(path)
        print(
            f"Path: {path} => Date: {date.strftime('%Y-%m-%d %H:%M:%S')} (UTC: {date.isoformat()})"
        )
