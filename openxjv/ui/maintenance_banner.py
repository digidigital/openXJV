from PySide6.QtCore import Qt
from openxjv.utils import open_url
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)


class MaintenanceBanner(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("MaintenanceBanner")

        self.setStyleSheet("""
            #MaintenanceBanner {
                background-color: #fff8e1;
                border: 1px solid #ffe082;
                border-radius: 4px;
                padding: 8px;
            }

            #MaintenanceBanner QLabel {
                background-color: transparent;
                color: #1a1a1a;
            }

            #MaintenanceBanner QLabel a {
                color: #0a57b8;
            }

            #MaintenanceBanner QLabel a:hover {
                color: #084a9a;
            }

            #MaintenanceBanner QLabel a:visited {
                color: #0a57b8;
            }

            #MaintenanceBanner QPushButton {
                color: #1a1a1a;
                background: transparent;
                border: none;
            }

            #MaintenanceBanner QPushButton:hover {
                background-color: rgba(0,0,0,0.1);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        info_label = QLabel(
            'Sie nutzen eine uneingeschränkte und kostenlose Open\u2011Source\u2011Software, in deren Entwicklung und Pflege kontinuierlich Arbeitszeit und finanzielle Mittel fließen.<br>'
            'Damit dieses Projekt auch künftig zuverlässig funktioniert und frei verfügbar bleibt, laden wir <b>Berufsträger, Behörden und gewerbliche Nutzer</b> ein, ein <b>Open Source Maintenance Token</b> zu erwerben.<br><br>'
            'Ihr Beitrag hilft unmittelbar dabei, Weiterentwicklung und Wartung zu sichern – und zeigt Wertschätzung für die Arbeit, die hinter dieser Software steht.<br>Weitere Informationen finden Sie unter: '
            '<a href="https://openxjv.de/maintenance_token.html">https://openxjv.de/maintenance_token.html</a><br><br>'
            '<b>Token\u2011Inhaber sehen diesen Hinweis nicht.</b>'
        )
        info_label.setOpenExternalLinks(False)
        info_label.linkActivated.connect(open_url)
        info_label.setWordWrap(True)
        info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(info_label)

        close_button = QPushButton("\u2715")
        close_button.setFixedSize(24, 24)
        close_button.setFlat(True)
        close_button.setStyleSheet("QPushButton { font-size: 16px; border: none; }")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.hide)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignTop)
