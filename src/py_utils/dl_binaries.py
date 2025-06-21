import platform
import stat
import sys
import tarfile
import urllib.request as request
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from tqdm import tqdm


@dataclass
class BinaryInfo:
    """Structure pour stocker les informations sur un binaire."""

    names: list[str]
    os: str
    arch: str
    url: str


def get_architecture() -> str:
    """Retourne le type d'architecture de la machine, "x86_64" ou "arm64"."""
    arch = platform.machine().lower()
    if arch in ["x86", "x86_64", "amd64"]:
        return "x86_64"
    elif arch in ["arm64", "aarch64"]:
        return "arm64"
    return arch


def get_system() -> str:
    """Retourne le système d'exploitation."""
    return sys.platform


def dl_with_progress_bar(url: str, fpath: str) -> None:
    """
    Télécharge un fichier à partir d'une URL et l'enregistre localement.
    Utilise une barre de progression pour afficher l'état du téléchargement.

    :param url: URL du fichier à télécharger
    :param fpath: Chemin fichier local dans lequel enregistrer le téléchargement
    """

    class DownloadProgressBar(tqdm):
        def update_to(self, b=1, bsize=1, tsize=None):
            if tsize is not None:
                self.total = tsize
            self.update(b * bsize - self.n)

    with DownloadProgressBar(unit="B", unit_scale=True, miniters=1, desc=url.split("/")[-1]) as bar:
        try:
            request.urlretrieve(url, filename=fpath, reporthook=bar.update_to)
            return True
        except Exception as e:
            print(f"Erreur lors du téléchargement: {e}")
            return False


class BinaryDownloader:
    """Classe pour gérer le téléchargement et l'extraction des binaires."""

    def __init__(self, dl_dir: str | Path = "/tmp", dest_dir: str | Path = "bin"):
        """
        Initialise le téléchargeur de binaires.

        :param dl_dir: Dossier temporaire pour le téléchargement des fichiers
        :param dest_dir: Dossier de destination pour les fichiers extraits
        """
        self.dl_dir = Path(dl_dir)
        self.dest_dir = Path(dest_dir)

        # Créer les répertoires s'ils n'existent pas
        self.dl_dir.mkdir(parents=True, exist_ok=True)
        self.dest_dir.mkdir(parents=True, exist_ok=True)

    def download_and_extract(self, url: str, names: list[str] | None = None) -> list[Path]:
        """
        Télécharge une archive et extrait les fichiers listés dans 'names' vers le dossier de destination.

        :param url: URL de l'archive à télécharger
        :param names: Liste des noms de fichiers à extraire. Si None, tous les fichiers seront extraits.
        :return: Liste des chemins des fichiers extraits
        """
        print(f"Téléchargement de {url} dans {self.dl_dir}...")

        fname = url.split("/")[-1]
        fpath = self.dl_dir / fname

        if fpath.exists():
            print(f"{fname} a déjà été téléchargé.")
        else:
            success = dl_with_progress_bar(url, fpath)
            if not success:
                print(f"Échec du téléchargement de {fname}.")
                return []
            print(f"{fname} téléchargé.")

        files = []
        try:
            if fname.endswith(".zip"):
                files = self._extract_from_zip(fpath, names)
            elif fname.endswith(".tar.xz"):
                files = self._extract_from_tar(fpath, names, mode="r:xz")
            elif fname.endswith(".tar.gz"):
                files = self._extract_from_tar(fpath, names, mode="r:gz")
            else:
                print(f"Format d'archive non pris en charge: {fname}.")
                return []

            # Ajout des droits d'exécution pour l'utilisateur et le groupe sur Linux et macOS
            if sys.platform in ["linux", "darwin"]:
                for file in files:
                    file.chmod(file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

            return files
        except Exception as e:
            print(f"Erreur lors de l'extraction: {e}")
            return []

    def _extract_from_zip(self, fpath: Path, names: list[str] | None = None) -> list[Path]:
        """
        Extrait les fichiers d'une archive ZIP vers le dossier de destination.

        :param fpath: Chemin vers l'archive à extraire
        :param names: Liste des noms de fichiers à extraire. Si None, tous les fichiers seront extraits.
        :return: Liste des chemins des fichiers extraits
        """
        print(f"Extraction de {fpath} dans {self.dest_dir}...")
        files = []

        try:
            with ZipFile(fpath) as zip_ref:
                for member in zip_ref.infolist():
                    # On "aplatit" le nom du fichier pour éviter les sous-dossiers
                    member.filename = Path(member.filename).name

                    if not member.is_dir() and (not names or member.filename in names):
                        print(f"Extraction de {member.filename}...")
                        zip_ref.extract(member, self.dest_dir)
                        files.append(self.dest_dir / member.filename)

            return files
        except Exception as e:
            print(f"Erreur lors de l'extraction de l'archive ZIP: {e}")
            return []

    def _extract_from_tar(
        self, fpath: Path, names: list[str] | None = None, mode: str = "r:gz"
    ) -> list[Path]:
        """
        Extrait les fichiers d'une archive TAR vers le dossier de destination.

        :param fpath: Chemin vers l'archive à extraire
        :param names: Liste des noms de fichiers à extraire. Si None, tous les fichiers seront extraits.
        :param mode: Mode d'ouverture de l'archive (r:gz, r:xz, etc.)
        :return: Liste des chemins des fichiers extraits
        """
        print(f"Extraction de {fpath} dans {self.dest_dir}...")
        files = []

        try:
            with tarfile.open(fpath, mode) as tar_ref:
                for member in tar_ref.getmembers():
                    # On "aplatit" le nom du fichier pour éviter les sous-dossiers
                    member.name = Path(member.name).name

                    if member.isfile() and (not names or member.name in names):
                        print(f"Extraction de {member.name}...")
                        tar_ref.extract(member, self.dest_dir)
                        files.append(self.dest_dir / member.name)

            return files
        except Exception as e:
            print(f"Erreur lors de l'extraction de l'archive TAR: {e}")
            return []


# Liste de tous les binaires
ALL_BINARIES = [
    BinaryInfo(
        names=["ffmpeg", "ffprobe"],
        os="linux",
        arch="x86_64",
        url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
    ),
    BinaryInfo(
        names=["ffmpeg", "ffprobe"],
        os="linux",
        arch="arm64",
        url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
    ),
    BinaryInfo(
        names=["ffmpeg.exe", "ffprobe.exe"],
        os="win32",
        arch="x86_64",
        url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    ),
    BinaryInfo(
        names=["ffmpeg"],
        os="darwin",
        arch="x86_64",
        url="https://evermeet.cx/ffmpeg/ffmpeg-7.1.1.zip",
    ),
    BinaryInfo(
        names=["ffmpeg"],
        os="darwin",
        arch="arm64",
        url="https://www.osxexperts.net/ffmpeg711arm.zip",
    ),
    BinaryInfo(
        names=["ffprobe"],
        os="darwin",
        arch="x86_64",
        url="https://evermeet.cx/ffmpeg/ffprobe-7.1.1.zip",
    ),
    BinaryInfo(
        names=["ffprobe"],
        os="darwin",
        arch="arm64",
        url="https://www.osxexperts.net/ffprobe711arm.zip",
    ),
    BinaryInfo(
        names=["mediamtx", "mediamtx.yml"],
        os="darwin",
        arch="x86_64",
        url="https://github.com/bluenviron/mediamtx/releases/download/v1.12.2/mediamtx_v1.12.2_darwin_amd64.tar.gz",
    ),
    BinaryInfo(
        names=["mediamtx", "mediamtx.yml"],
        os="darwin",
        arch="arm64",
        url="https://github.com/bluenviron/mediamtx/releases/download/v1.12.2/mediamtx_v1.12.2_darwin_arm64.tar.gz",
    ),
    BinaryInfo(
        names=["mediamtx", "mediamtx.yml"],
        os="linux",
        arch="x86_64",
        url="https://github.com/bluenviron/mediamtx/releases/download/v1.12.2/mediamtx_v1.12.2_linux_amd64.tar.gz",
    ),
    BinaryInfo(
        names=["mediamtx", "mediamtx.yml"],
        os="linux",
        arch="arm64",
        url="https://github.com/bluenviron/mediamtx/releases/download/v1.12.2/mediamtx_v1.12.2_linux_arm64.tar.gz",
    ),
]


def download_binaries(
    binaries: list[BinaryInfo] = None,
    dl_dir: str | Path = "/tmp",
    dest_dir: str | Path = "bin",
    filter_names: list[str] | None = None,
) -> dict[str, list[Path]]:
    """
    Télécharge les binaires spécifiés dans la liste 'binaries' et les extrait dans le dossier de destination.

    :param binaries: Liste de BinaryInfo contenant les informations sur les binaires à télécharger.
    :param dl_dir: Dossier temporaire pour le téléchargement des fichiers.
    :param dest_dir: Dossier de destination pour les fichiers extraits.
    :param filter_names: Liste des noms de binaires à télécharger. Si None, tous les binaires seront téléchargés.
    :return: Dictionnaire des noms de binaires et leurs chemins extraits
    """
    current_os = get_system()
    current_arch = get_architecture()

    if binaries is None:
        binaries = ALL_BINARIES

    downloader = BinaryDownloader(dl_dir=dl_dir, dest_dir=dest_dir)
    extracted_files = {}

    for binary in binaries:
        # Vérifier si le binaire correspond à l'OS et l'architecture actuels
        if binary.os != current_os or binary.arch != current_arch:
            continue

        # Vérifier si le binaire est dans la liste de filtrage
        if filter_names and not any(name in binary.names for name in filter_names):
            continue

        print(
            f"\nTéléchargement de {', '.join(binary.names)} pour {current_os} {current_arch} depuis {binary.url}..."
        )

        files = downloader.download_and_extract(binary.url, binary.names)

        for file in files:
            name = file.name
            if name not in extracted_files:
                extracted_files[name] = []
            extracted_files[name].append(file)

    print("\nLe téléchargement et l'extraction des binaires sont terminés.")

    if not extracted_files:
        print(
            f"Attention: Aucun binaire correspondant à votre système ({current_os} {current_arch}) n'a été trouvé."
        )

    return extracted_files


if __name__ == "__main__":
    # Exemple d'utilisation
    bin_dir = Path(__file__).parent.resolve() / "bin"
    tmp_dir = Path("/tmp") / "binary_downloads"

    result = download_binaries(dl_dir=tmp_dir, dest_dir=bin_dir, filter_names=["ffmpeg", "ffprobe"])

    print("\nBinaires téléchargés et extraits:")
    for name, paths in result.items():
        print(f"- {name}: {[str(p) for p in paths]}")
