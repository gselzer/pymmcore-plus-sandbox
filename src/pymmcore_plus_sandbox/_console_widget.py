from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget


class QtConsole(RichJupyterWidget):
    """A Qt widget for an IPython console, providing access to UI components.

    Heavily borrowed from napari's Qt console:
    https://github.com/napari/napari-console/blob/e2a8d7120a179c26295431a5c40820dcda6bb8f0/napari_console/qt_console.py#L1
    """

    def __init__(self, user_variables: dict | None = None):
        if user_variables is None:
            user_variables = {}
        super().__init__()
        self.setWindowTitle("PyMMCore Plus Sandbox Console")

        # this makes calling `setFocus()` on a QtConsole give keyboard focus to
        # the underlying `QTextEdit` widget
        self.setFocusProxy(self._control)

        # Create an in-process kernel
        self.kernel_manager = QtInProcessKernelManager()
        self.kernel_manager.start_kernel(show_banner=False)
        self.kernel_manager.kernel.gui = "qt"
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()
        self.shell = self.kernel_manager.kernel.shell
        self.push = self.shell.push

        # Add any user variables
        self.push(user_variables)

    def closeEvent(self, event):
        """Clean up the integrated console in napari."""

        if self.kernel_client is not None:
            self.kernel_client.stop_channels()
        if self.kernel_manager is not None and self.kernel_manager.has_kernel:
            self.kernel_manager.shutdown_kernel()

        # RichJupyterWidget doesn't clean these up
        self._completion_widget.deleteLater()
        self._call_tip_widget.deleteLater()
        self.deleteLater()
        event.accept()
