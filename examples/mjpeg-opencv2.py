import sys
import urllib.request

import cv2
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class VideoStreamThread(QThread):
    # Signal pour envoyer l'image décodée au thread principal
    change_pixmap_signal = Signal(QImage)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self._run_flag = True

    def run(self):
        # L'URL du flux MJPEG (remplacez par la vôtre)
        # Exemple d'URL de test si vous n'en avez pas :
        # "http://212.94.137.93/mjpg/video.mjpg" (peut ne pas être toujours disponible)
        # "http://192.168.1.100:8080/video" (si vous avez une caméra IP locale)

        stream = urllib.request.urlopen(self.url)
        bytes = b""
        while self._run_flag:
            bytes += stream.read(1024)  # Lire des petits morceaux du flux

            # Chercher le marqueur de fin d'une image JPEG (FF D9)
            a = bytes.find(b"\xff\xd8")  # Début d'image JPEG
            b = bytes.find(b"\xff\xd9")  # Fin d'image JPEG

            if a != -1 and b != -1:
                jpg_data = bytes[a : b + 2]  # Extraire les données JPEG
                bytes = bytes[b + 2 :]  # Conserver le reste du buffer

                # Décoder l'image JPEG avec OpenCV
                img_np = np.frombuffer(jpg_data, dtype=np.uint8)
                frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

                if frame is not None:
                    # Convertir l'image OpenCV (BGR) en RGB
                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Obtenir les dimensions de l'image
                    h, w, ch = rgb_image.shape

                    # Créer une QImage
                    bytes_per_line = ch * w
                    convert_to_qt_format = QImage(
                        rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888
                    )

                    # Émettre le signal avec l'image
                    self.change_pixmap_signal.emit(convert_to_qt_format)

    def stop(self):
        """Arrête le thread de lecture vidéo."""
        self._run_flag = False
        self.wait()  # Attend que le thread se termine correctement


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 MJPEG Stream Viewer")
        self.setGeometry(100, 100, 800, 600)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)  # Centrer l'image
        self.image_label.setFixedSize(640, 480)  # Taille fixe pour le label pour l'exemple

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.image_label)
        self.setLayout(main_layout)

        self.thread = None

        # --- REMPLACEZ CETTE URL PAR VOTRE ADRESSE DE FLUX MJPEG ---
        self.mjpeg_url = "http://172.26.82.36/axis-cgi/mjpg/video.cgi"  # Exemple : flux public, peut être instable
        # Vous pouvez utiliser un serveur MJPEG local pour les tests si vous en avez un.
        # Par exemple, si vous utilisez MotionEyeOS ou un projet similaire.
        # self.mjpeg_url = "http://192.168.1.100:8080/video"

        self.start_video_stream()

    def start_video_stream(self):
        self.thread = VideoStreamThread(self.mjpeg_url)
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.start()

    def update_image(self, qt_image):
        """Met à jour le QLabel avec la nouvelle image."""
        # Redimensionner l'image si nécessaire pour s'adapter au label (optionnel)
        # scaled_image = qt_image.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # self.image_label.setPixmap(QPixmap.fromImage(scaled_image))

        self.image_label.setPixmap(QPixmap.fromImage(qt_image))

    def closeEvent(self, event):
        """Gère la fermeture de l'application pour arrêter le thread."""
        if self.thread:
            self.thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
