import sys
from io import BytesIO

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class MjpegViewer(QWidget):
    def __init__(self, stream_url):
        super().__init__()

        self.stream_url = stream_url
        self.session = requests.Session()
        self.stream = None

        self.init_ui()
        self.init_timer()

    def init_ui(self):
        self.setWindowTitle("MJPEG Stream Viewer")
        self.resize(800, 600)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        self.setLayout(layout)

    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(100)  # Mise à jour toutes les 100ms

    def update_frame(self):
        try:
            if self.stream is None:
                self.stream = self.session.get(self.stream_url, stream=True)

            # Lecture du prochain frame MJPEG
            bytes_data = bytes()
            for chunk in self.stream.iter_content(chunk_size=1024):
                bytes_data += chunk
                if b"\xff\xd8" in bytes_data and b"\xff\xd9" in bytes_data:
                    start = bytes_data.find(b"\xff\xd8")
                    end = bytes_data.find(b"\xff\xd9") + 2
                    jpeg_data = bytes_data[start:end]
                    bytes_data = bytes_data[end:]

                    # Affichage de l'image
                    pixmap = QPixmap()
                    pixmap.loadFromData(jpeg_data)
                    self.image_label.setPixmap(
                        pixmap.scaled(
                            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                    break

        except Exception as e:
            print(f"Erreur: {e}")
            self.stream = None

    def closeEvent(self, event):
        if self.stream:
            self.stream.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Remplacez cette URL par votre flux MJPEG
    stream_url = "http://172.26.82.36/axis-cgi/mjpg/video.cgi"
    viewer = MjpegViewer(stream_url)
    viewer.show()

    sys.exit(app.exec())
