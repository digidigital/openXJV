from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from openxjv.utils import open_url, is_in_bundle


class MaintenanceTokenDialog(QDialog):

    token_validated = Signal()

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Maintenance Token")
        self.setMinimumWidth(500)
        self._build_ui()
        self.adjustSize()
        self.setFixedSize(self.size())


    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel(
            '<center>'
            'Es wurde bisher kein gültiges Maintenance Token registriert.<br>'
            'Weitere Informationen: '
            '<a href="https://openxjv.de/maintenance_token.html">https://openxjv.de/maintenance_token.html</a>'
            '</center>'
        )
        self.info_label.setOpenExternalLinks(False)
        self.info_label.linkActivated.connect(open_url)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        layout.addSpacing(10)

        form = QFormLayout()
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("E-Mail-Adresse")
        existing_email = self.settings_manager.get_string('maintenance_email', '')
        if existing_email:
            self.email_edit.setText(existing_email)
        form.addRow("E-Mail:", self.email_edit)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        existing_token = self.settings_manager.get_string('maintenance_token', '')
        if existing_token:
            self.token_edit.setText(existing_token)
        form.addRow("Token:", self.token_edit)

        layout.addLayout(form)
        layout.addSpacing(10)

        self.check_button = QPushButton("Prüfen")
        self.check_button.clicked.connect(self._check_token)
        layout.addWidget(self.check_button)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        # Wenn bereits ein gültiges Token gespeichert ist, Erfolgsmeldung anzeigen
        if is_in_bundle() and existing_email and existing_token:
            from openxjv.utils.token_validator.validate_binary import check_token_via_binary
            if check_token_via_binary(existing_email, existing_token):
                self._show_success()

    def _check_token(self):
        email = self.email_edit.text().strip()
        token = self.token_edit.text().strip()

        if not email or not token:
            self.result_label.setStyleSheet("color: red;")
            self.result_label.setText("Bitte E-Mail und Token eingeben.")
            return

        if not is_in_bundle():
            return

        from openxjv.utils.token_validator.validate_binary import check_token_via_binary
        if check_token_via_binary(email, token):
            self.settings_manager.set_value('maintenance_email', email)
            self.settings_manager.set_value('maintenance_token', token)
            self._show_success()
            self.token_validated.emit()
        else:
            self.result_label.setStyleSheet("color: red;")
            self.result_label.setText("Das eingegebene Token ist ungültig.")

    def _show_success(self):
        self.info_label.setText(
            "<center>"
            "✅ Gültiges Maintenance Token hinterlegt.<br>"
            "Wir bedanken uns für die Unterstützung des Projekts."
            "</center>"
        )
        self.result_label.setStyleSheet("color: green;")
        self.result_label.setText("")
        self.email_edit.setEnabled(False)
        self.token_edit.setEnabled(False)
        self.check_button.setEnabled(False)
