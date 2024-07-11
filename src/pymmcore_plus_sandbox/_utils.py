import tensorstore as ts
from pymmcore_plus import CMMCorePlus
from qtpy.QtGui import QFontMetrics, QGuiApplication
from qtpy.QtWidgets import QDialog, QDialogButtonBox, QGridLayout, QLabel, QTextEdit


class ErrorMessageBox(QDialog):
    """A helper widget for creating (and immediately displaying) popups"""

    def __init__(self, title: str, error_message: str, *args, **kwargs) -> None:
        QDialog.__init__(self, *args, **kwargs)
        self.setWindowTitle("Error")
        self._layout = QGridLayout()
        # Write the title to a Label
        self._layout.addWidget(QLabel(title, self), 0, 0, 1, self._layout.columnCount())

        # Write the error message to a TextEdit
        msg_edit = QTextEdit(self)
        msg_edit.setReadOnly(True)
        msg_edit.setText(error_message)
        self._layout.addWidget(msg_edit, 1, 0, 1, self._layout.columnCount())
        msg_edit.setLineWrapMode(QTextEdit.NoWrap)

        # Default size - size of the error message
        font = msg_edit.document().defaultFont()
        fontMetrics = QFontMetrics(font)
        textSize = fontMetrics.size(0, error_message)
        textWidth = textSize.width() + 100
        textHeight = textSize.height() + 100
        self.resize(textWidth, textHeight)
        # Maximum size - ~80% of the user's screen
        screen_size = QGuiApplication.primaryScreen().size()
        self.setMaximumSize(
            int(screen_size.width() * 0.8), int(screen_size.height() * 0.8)
        )

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        self._layout.addWidget(btn_box, 2, 0, 1, self._layout.columnCount())
        self.setLayout(self._layout)


def _data_type(mmc: CMMCorePlus):
    px_type = mmc.getBytesPerPixel()
    if px_type == 1:
        return ts.uint8
    elif px_type == 2:
        return ts.uint16
    elif px_type == 4:
        return ts.uint32
    else:
        raise Exception(f"Unsupported Pixel Type: {px_type}")
