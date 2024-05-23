import sys

import numpy as np
import tensorstore as ts
from ndv import NDViewer
from pymmcore import CMMCore
from pymmcore_plus import CMMCorePlus, DeviceType
from pymmcore_plus.mda.handlers import TensorStoreHandler
from pymmcore_widgets import (
    ConfigWizard,
    GroupPresetTableWidget,
    LiveButton,
    PixelConfigurationWidget,
    PropertyBrowser,
    ShuttersWidget,
    SnapButton,
)
from qtpy import QtCore
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QToolBar,
    QWidget,
)
from superqt.utils import ensure_main_thread
from useq import MDAEvent, MDASequence

from pymmcore_plus_sandbox._mda_button_widget import MDAButton
from pymmcore_plus_sandbox._stage_widget import StageButton


class SnapLiveToolBar(QToolBar):
    """Tab exposing widgets for data display."""

    def __init__(self, mmc: CMMCore | None = None) -> None:
        super().__init__()
        self._mmc = mmc if mmc is not None else CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self) -> None:
        self.snap_live_tab = QGroupBox()
        self.snap_live_tab.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.snap_live_tab_layout = QGridLayout()

        # snap/live in snap_live_tab
        self.btn_wdg = QWidget()
        self.btn_wdg.setMaximumHeight(65)
        self.btn_wdg_layout = QHBoxLayout()
        self.snap_Button = SnapButton()
        self.btn_wdg_layout.addWidget(self.snap_Button)
        self.live_Button = LiveButton()
        self.btn_wdg_layout.addWidget(self.live_Button)
        self.mda_Button = MDAButton()
        self.btn_wdg_layout.addWidget(self.mda_Button)

        self.btn_wdg.setLayout(self.btn_wdg_layout)

        self.snap_live_tab_layout.addWidget(self.btn_wdg, 1, 0, 1, 2)
        self.snap_live_tab.setLayout(self.snap_live_tab_layout)

        self.addWidget(self.snap_live_tab)


class StageControlToolBar(QToolBar):
    """Tab exposing widgets for stage control."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self._mmc = mmc if mmc is not None else CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self) -> None:
        self.snap_live_tab = QGroupBox()
        self.snap_live_tab.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.snap_live_tab_layout = QGridLayout()

        self.btn_wdg = QWidget()
        self.btn_wdg.setMaximumHeight(65)
        self.btn_wdg_layout = QHBoxLayout()
        self.stages_Button = StageButton()
        self.btn_wdg_layout.addWidget(self.stages_Button)

        self.btn_wdg.setLayout(self.btn_wdg_layout)

        self.snap_live_tab_layout.addWidget(self.btn_wdg, 1, 0, 1, 2)
        self.snap_live_tab.setLayout(self.snap_live_tab_layout)

        self.addWidget(self.snap_live_tab)


class ShuttersToolBar(QToolBar):
    """Tab exposing widgets for shutter control."""

    def __init__(self, mmc: CMMCore | None = None) -> None:
        super().__init__()
        self.mmc = mmc if mmc is not None else CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self) -> None:
        self.snap_live_tab = QGroupBox()
        self.snap_live_tab.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.snap_live_tab_layout = QGridLayout()

        self.btn_wdg = QWidget()
        self.btn_wdg.setMaximumHeight(65)
        self.btn_wdg_layout = QHBoxLayout()

        shutter_dev_list = list(self.mmc.getLoadedDevicesOfType(DeviceType.Shutter))
        for idx, shutter_dev in enumerate(shutter_dev_list):
            # bool to display the autoshutter checkbox only with the last shutter
            autoshutter = bool(idx >= len(shutter_dev_list) - 1)
            shutter = ShuttersWidget(shutter_dev, autoshutter=autoshutter)
            shutter.button_text_open = shutter_dev
            shutter.button_text_closed = shutter_dev
            self.btn_wdg_layout.addWidget(shutter)

        self.btn_wdg.setLayout(self.btn_wdg_layout)

        self.snap_live_tab_layout.addWidget(self.btn_wdg, 1, 0, 1, 2)
        self.snap_live_tab.setLayout(self.snap_live_tab_layout)

        self.addWidget(self.snap_live_tab)


class CentralWidget(QWidget):
    """Contains widgets shown in the center of the application."""

    def __init__(
        self, parent: QWidget | None = None, mmc: CMMCore | None = None
    ) -> None:
        super().__init__(parent=parent)
        self._layout = QHBoxLayout()

        centerWidget = GroupPresetTableWidget(parent=self)
        self._layout.addWidget(centerWidget)

        self.setLayout(self._layout)


class APP(QMainWindow):
    """Create a QToolBar for the Main Window."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self._mmc = CMMCorePlus.instance() if mmc is None else mmc
        self.setWindowTitle("PyMMCore Plus Sandbox")
        self.windows: list[NDViewer] = []
        self.live_viewer = None
        self._live_timer_id: int | None = None

        # Menus
        self._create_menus()

        # Toolbar
        self._dock_widgets: dict[str, QDockWidget] = {}
        toolbar_items = [
            SnapLiveToolBar(),
            StageControlToolBar(),
            ShuttersToolBar(),
        ]
        for item in toolbar_items:
            if item:
                self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, item)
            else:
                self.addToolBarBreak(QtCore.Qt.ToolBarArea.TopToolBarArea)

        # Snap signals
        self._mmc.events.imageSnapped.connect(self._new_snap_viewer)

        self.setCentralWidget(CentralWidget(self, self._mmc))

        # Live signals
        self._mmc.events.continuousSequenceAcquisitionStarted.connect(
            self._start_live_viewer
        )
        self._mmc.events.sequenceAcquisitionStopped.connect(self._stop_live_viewer)

        # MDA signals
        self._mmc.mda.events.frameReady.connect(self._on_mda_frame)
        self._mmc.mda.events.sequenceStarted.connect(self._on_mda_started)
        self._mmc.mda.events.sequenceFinished.connect(self._on_mda_finished)

    def _create_menus(self):
        self.deviceMenu = self.menuBar().addMenu("Device")

        self.property_browser: PropertyBrowser | None = None
        self.browseAction = QAction("Device Property Browser", self)
        self.browseAction.triggered.connect(self._show_property_browser)

        self.wizardAction = QAction("Hardware Configuration Wizard", self)
        self.wizardAction.triggered.connect(self._exec_property_wizard)

        self.loadAction = QAction("Load Hardware Configuration", self)
        self.loadAction.triggered.connect(self._load_hw_config)

        self.saveAction = QAction("Save Hardware Configuration", self)
        self.saveAction.triggered.connect(self._save_hw_config)

        # TODO - maybe we just wanted the widget?
        self.pixel_calibrator: PixelConfigurationWidget | None = None
        self.pixelAction = QAction("Pixel Size Calibration", self)
        self.pixelAction.triggered.connect(self._calibrate_pixel)

        self.deviceMenu.addAction(self.browseAction)
        self.deviceMenu.addSeparator()
        self.deviceMenu.addAction(self.wizardAction)
        self.deviceMenu.addAction(self.loadAction)
        self.deviceMenu.addAction(self.saveAction)
        self.deviceMenu.addSeparator()
        self.deviceMenu.addAction(self.pixelAction)

    def _show_property_browser(self) -> None:
        if self.property_browser is None:
            self.property_browser = PropertyBrowser(parent=None, mmcore=self._mmc)
            self.property_browser.setWindowTitle("Device Property Browser")
        self.property_browser.show()
        self.property_browser.raise_()

    def _exec_property_wizard(self) -> None:
        wizard = ConfigWizard(parent=None, core=self._mmc)
        wizard.exec()

    def _load_hw_config(self) -> None:
        """Open file dialog to select a config file."""
        # Shamelessly copied from https://github.com/pymmcore-plus/pymmcore-widgets/blob/1d19b1a10f963294b38cd3bcb969f25c49d0054e/src/pymmcore_widgets/_load_system_cfg_widget.py#L54
        (filename, _) = QFileDialog.getOpenFileName(
            self, "Select a Micro-Manager configuration file", "", "cfg(*.cfg)"
        )
        if filename:
            self._mmc.unloadAllDevices()
            self._mmc.loadSystemConfiguration(filename)

    def _save_hw_config(self) -> None:
        """Open file dialog to select a config file."""
        (filename, _) = QFileDialog.getSaveFileName(
            self, "Create a Micro-Manager configuration file", "", "cfg(*.cfg)"
        )
        if filename:
            self._mmc.saveSystemConfiguration(filename)

    def _calibrate_pixel(self) -> None:
        if self.pixel_calibrator is None:
            self.pixel_calibrator = PixelConfigurationWidget(
                parent=None, mmcore=self._mmc
            )
        self.pixel_calibrator.show()
        self.pixel_calibrator.raise_()

    def closeEvent(self, event):
        """Closes this widget, and all other windows spawned by the application."""
        super().closeEvent(event)
        QApplication.quit()

    # -- SNAP VIEWER -- #

    def _new_snap_viewer(self):
        if self._mmc.mda.is_running():
            # This signal is emitted during MDAs as well - we want to ignore those.
            return
        new_snap_viewer = NDViewer()
        data = self._mmc.getImage().copy()
        new_snap_viewer.set_data(data)
        new_snap_viewer.show()
        # Append viewer to avoid GC
        self.windows.append(new_snap_viewer)
        self.windows.append(data)

    # -- LIVE VIEWER -- #

    def _start_live_viewer(self):
        # Close old live viewer
        if self.live_viewer:
            self.live_viewer.close()
            self.live_viewer = None

        # Start new live viewer
        w = self._mmc.getProperty("Camera", "OnCameraCCDXSize")
        h = self._mmc.getProperty("Camera", "OnCameraCCDYSize")
        shape = (int(w), int(h))
        self.ts_array = ts.open(
            {"driver": "zarr", "kvstore": {"driver": "memory"}},
            create=True,
            shape=shape,
            dtype=self._data_type(),
        ).result()
        self.live_viewer = NDViewer(self.ts_array)
        self.live_viewer.show()

        # Start timer to update live viewer
        interval = int(self._mmc.getExposure())
        self._live_timer_id = self.startTimer(
            interval, QtCore.Qt.TimerType.PreciseTimer
        )

    def _stop_live_viewer(self):
        # Pause live viewer, but leave it open.
        if self.live_viewer:
            self.killTimer(self._live_timer_id)
            self._live_timer_id = None

    def _update_viewer(self, data: np.ndarray | None = None) -> None:
        """Update viewer with the latest image from the circular buffer."""
        if data is None:
            if self._mmc.getRemainingImageCount() == 0:
                return
            try:
                # TODO - is there any way to read the bytes directly into this buffer?
                # TODO Does it help us to do the write asyncronously, and just call
                # setIndex later?
                self.ts_array[:] = self._mmc.getLastImage()
                # This call is important, telling the StackViewer to redraw the current
                # data buffer.
                if self.live_viewer:
                    self.live_viewer.set_current_index({})
            except (RuntimeError, IndexError):
                # circular buffer empty
                return

    # -- MDA VIEWER -- #

    def timerEvent(self, a0: QtCore.QTimerEvent | None) -> None:
        """Handles TimerEvents."""
        # Handle the timer event by updating the viewer (on gui thread)
        self._update_viewer()

    def _on_mda_frame(self, image: np.ndarray, event: MDAEvent) -> None:
        """Called on the `frameReady` event from the core."""
        self.mda_data.frameReady(image, event, {})
        if not hasattr(self.mda_viewer, "_data_wrapper"):
            self.mda_viewer.set_data(self.mda_data.store)
        self.mda_viewer.set_current_index(event.index)

    @ensure_main_thread  # type: ignore [misc]
    def _on_mda_started(self, sequence: MDASequence) -> None:
        """Create temp folder and block gui when mda starts."""
        # TODO this field is likely limiting - consider throwing it in metadata?
        # TODO can we discern whether the sequence is being written to file?
        # If so, should we avoid viewing it?
        # TODO consider whether/how to expose other datastores
        self.mda_data = TensorStoreHandler(
            driver="zarr",
            kvstore={"driver": "memory"},
            spec={
                "dtype": "uint16"  # TODO
            },
        )
        self.mda_viewer = NDViewer()
        self.mda_viewer.show()

    def _on_mda_finished(self, sequence: MDASequence) -> None:
        # TODO consider necessary cleanup steps
        pass

    # -- HELPERS -- #

    def _data_type(self):
        px_type = self._mmc.getProperty("Camera", "PixelType")
        if px_type == "8bit":
            return ts.uint8
        elif px_type == "16bit":
            return ts.uint16
        elif px_type == "32bit":
            return ts.uint32
        else:
            raise Exception(f"Unsupported Pixel Type: {px_type}")


def launch():
    """Launches the GUI and blocks."""
    mmcore = CMMCorePlus.instance()
    mmcore.loadSystemConfiguration("./MMConfig_demo.cfg")

    qapp = QApplication(sys.argv)
    w = APP()
    w.show()

    qapp.exec()


if __name__ == "__main__":
    launch()
