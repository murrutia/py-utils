import sys

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class MjpegViewer(QWidget):
    def __init__(self, stream_url):
        super().__init__()

        self.stream_url = stream_url
        self.cap = cv2.VideoCapture(stream_url)

        if not self.cap.isOpened():
            print("Erreur: Impossible d'ouvrir le flux")
            sys.exit(1)

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
        self.timer.start(30)  # ~30 FPS

    def update_frame(self):
        ret, frame = self.cap.read()

        if ret:
            # Convertir l'image OpenCV (BGR) en QImage (RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_BGR888)

            # Afficher l'image dans le QLabel
            self.image_label.setPixmap(
                QPixmap.fromImage(qt_image).scaled(
                    self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )

    def closeEvent(self, event):
        self.cap.release()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Remplacez cette URL par votre flux MJPEG
    stream_url = "http://172.26.82.36/axis-cgi/mjpg/video.cgi"
    viewer = MjpegViewer(stream_url)
    viewer.show()

    sys.exit(app.exec())
