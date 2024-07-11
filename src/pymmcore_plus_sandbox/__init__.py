from __future__ import annotations

import sys
from typing import TYPE_CHECKING, cast

import numpy as np
import tensorstore as ts
from ndv import DataWrapper, NDViewer
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
    QMenu,
    QSizePolicy,
    QToolBar,
    QWidget,
)
from superqt.utils import ensure_main_thread
from useq import MDAEvent, MDASequence

from pymmcore_plus_sandbox._mda_button_widget import MDAButton
from pymmcore_plus_sandbox._stage_widget import StageButton

if TYPE_CHECKING:
    from typing import Any, Hashable, Mapping


class SnapLiveToolBar(QToolBar):
    """Tab exposing widgets for data display."""

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

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
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
        self, parent: QWidget | None = None, mmc: CMMCorePlus | None = None
    ) -> None:
        super().__init__(parent=parent)
        self._layout = QHBoxLayout()

        centerWidget = GroupPresetTableWidget(parent=self)
        self._layout.addWidget(centerWidget)

        self.setLayout(self._layout)


class Viewfinder(NDViewer):
    """An NDViewer subclass designed for expedient Snap&Live views."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Viewfinder")
        self.live_view: bool = False
        self._mmc = mmc if mmc is not None else CMMCorePlus.instance()

        self._btns.insertWidget(0, SnapButton(mmcore=self._mmc))
        self._btns.insertWidget(1, LiveButton(mmcore=self._mmc))

        # Create initial buffer
        self.ts_array = None
        self.ts_shape = (0, 0)
        self.bytes_per_pixel = 0
        self.update_datastore()

    def update_datastore(self):
        if (
            self.ts_array is None
            or self.ts_shape[0] != self._mmc.getImageHeight()
            or self.ts_shape[1] != self._mmc.getImageWidth()
            or self.bytes_per_pixel != self._mmc.getBytesPerPixel()
        ):
            self.ts_shape = (self._mmc.getImageHeight(), self._mmc.getImageWidth())
            self.bytes_per_pixel = self._mmc.getBytesPerPixel()
            self.ts_array = ts.open(
                {"driver": "zarr", "kvstore": {"driver": "memory"}},
                create=True,
                shape=self.ts_shape,
                dtype=self._data_type(),
            ).result()
            super().set_data(self.ts_array)

    def set_data(
        self,
        data: DataWrapper[Any] | Any,
        *,
        initial_index: Mapping[Hashable, int | slice] | None = {},
    ) -> None:
        # def set_data(self, data, *, initial_index=None) -> None:
        if initial_index is None:
            initial_index = {}
        self.update_datastore()
        if self.ts_array:
            self.ts_array[:] = data
        self.set_current_index(initial_index)

    # -- HELPERS -- #

    def _data_type(self):
        px_type = self._mmc.getBytesPerPixel()
        if px_type == 1:
            return ts.uint8
        elif px_type == 2:
            return ts.uint16
        elif px_type == 4:
            return ts.uint32
        else:
            raise Exception(f"Unsupported Pixel Type: {px_type}")


class APP(QMainWindow):
    """Create a QToolBar for the Main Window."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self._mmc = CMMCorePlus.instance() if mmc is None else mmc
        self.setWindowTitle("PyMMCore Plus Sandbox")
        self.viewfinder: Viewfinder | None = None
        self.current_mda: NDViewer | None = None
        self.mdas: list[NDViewer] = []
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
        self._mmc.events.imageSnapped.connect(self._handle_snap)

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

    def _create_menus(self) -> None:
        if (bar := self.menuBar()) is None:
            return
        self.deviceMenu = cast(QMenu, bar.addMenu("Device"))

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

    @ensure_main_thread
    def _set_up_viewfinder(self) -> Viewfinder:
        # Instantiate if not yet created
        if self.viewfinder is None:
            self.viewfinder = Viewfinder(self._mmc)
        # Make viewfinder visible
        self.viewfinder.show()
        # Bring viewfinder to the top
        self.viewfinder.raise_()
        # Return viewfinder (for convenience)
        return self.viewfinder

    # -- SNAP VIEWER -- #

    def _handle_snap(self):
        if self._mmc.mda.is_running():
            # This signal is emitted during MDAs as well - we want to ignore those.
            return
        viewfinder = self._set_up_viewfinder().result()
        viewfinder.set_data(self._mmc.getImage().copy())
        # viewfinder.set_current_index({})

    # -- LIVE VIEWER -- #

    def _start_live_viewer(self):
        viewfinder = self._set_up_viewfinder().result()
        viewfinder.live_view = True

        # Start timer to update live viewer
        interval = int(self._mmc.getExposure())
        self._live_timer_id = self.startTimer(
            interval, QtCore.Qt.TimerType.PreciseTimer
        )

    def _stop_live_viewer(self):
        # Pause live viewer, but leave it open.
        if self.viewfinder.live_view:
            self.viewfinder.live_view = False
            self.killTimer(self._live_timer_id)
            self._live_timer_id = None

    @ensure_main_thread  # type: ignore [misc]
    def _update_viewer(self, data: np.ndarray | None = None) -> None:
        """Update viewer with the latest image from the circular buffer."""
        if data is None:
            if self._mmc.getRemainingImageCount() == 0:
                return
            try:
                if self.viewfinder:
                    self.viewfinder.set_data(self._mmc.getLastImage().copy())
            except (RuntimeError, IndexError):
                # circular buffer empty
                return

    # -- MDA VIEWER -- #

    def timerEvent(self, a0: QtCore.QTimerEvent | None) -> None:
        """Handles TimerEvents."""
        # Handle the timer event by updating the viewer (on gui thread)
        self._update_viewer()

    @ensure_main_thread  # type: ignore [misc]
    def _on_mda_frame(self, image: np.ndarray, event: MDAEvent) -> None:
        """Called on the `frameReady` event from the core."""
        self.mda_data.frameReady(image, event, {})
        current_mda = cast(NDViewer, self.current_mda)
        if not hasattr(current_mda, "_data_wrapper"):
            current_mda.set_data(self.mda_data.store)
        current_mda.set_current_index(event.index)

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
        self.current_mda = NDViewer()
        self.current_mda.show()

    def _on_mda_finished(self, sequence: MDASequence) -> None:
        # Retain references to old MDA viewer
        if self.current_mda is not None:
            self.mdas.append(self.current_mda)


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
