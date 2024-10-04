from __future__ import annotations

import sys
import traceback as tb
from typing import TYPE_CHECKING, cast

import numpy as np
from ndv import NDViewer
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
from useq import GridRowsColumns, MDAEvent, MDASequence

from pymmcore_plus_sandbox._console_widget import QtConsole
from pymmcore_plus_sandbox._mda_button_widget import MDAButton
from pymmcore_plus_sandbox._settings import DefaultConfigFile, Settings
from pymmcore_plus_sandbox._stage_widget import StageButton
from pymmcore_plus_sandbox._utils import ErrorMessageBox, _data_type
from pymmcore_plus_sandbox._viewfinder import View, Viewfinder

if TYPE_CHECKING:
    from os import PathLike
    from typing import Literal, Mapping, TypeAlias

    import numpy as np
    import tensorstore as ts

    TsDriver: TypeAlias = Literal["zarr", "zarr3", "n5", "neuroglancer_precomputed"]
    EventKey: TypeAlias = frozenset[tuple[str, int]]


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
    """
    Tab exposing widgets for shutter control.

    Code adapted from:
    https://github.com/pymmcore-plus/pymmcore-widgets/blob/370dfcd5b73de95640fb0cc8aea79ec7f03adfd0/examples/shutters_widget.py#L1
    """

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self.mmc = mmc if mmc is not None else CMMCorePlus.instance()
        self.mmc.events.systemConfigurationLoaded.connect(self._refresh_toolbar)

        self.shutter_tab = QGroupBox()
        self.shutter_tab.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.snap_live_tab_layout = QGridLayout()

        self.btn_wdg = QWidget()
        self.btn_wdg.setMaximumHeight(65)
        self.btn_wdg_layout = QHBoxLayout()
        self.btn_wdg.setLayout(self.btn_wdg_layout)

        self.snap_live_tab_layout.addWidget(self.btn_wdg, 1, 0, 1, 2)
        self.shutter_tab.setLayout(self.snap_live_tab_layout)

        self.addWidget(self.shutter_tab)
        self._refresh_toolbar()

    def _refresh_toolbar(self) -> None:
        """Called to refresh the tab with current shutters."""
        # Remove old shutters
        for i in reversed(range(self.btn_wdg_layout.count())):
            self.btn_wdg_layout.itemAt(i).widget().deleteLater()

        # Add new shutters
        shutter_dev_list = list(self.mmc.getLoadedDevicesOfType(DeviceType.Shutter))
        if len(shutter_dev_list) == 0:
            self.hide()
        else:
            self.show()
            for idx, shutter_dev in enumerate(shutter_dev_list):
                # bool to display the autoshutter checkbox only with the last shutter
                autoshutter = bool(idx >= len(shutter_dev_list) - 1)
                shutter = ShuttersWidget(shutter_dev, autoshutter=autoshutter)
                shutter.button_text_open = shutter_dev
                shutter.button_text_closed = shutter_dev
                self.btn_wdg_layout.addWidget(shutter)


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


class APP(QMainWindow):
    """Create a QToolBar for the Main Window."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self._mmc = CMMCorePlus.instance() if mmc is None else mmc
        sys.excepthook = self._on_error

        self._settings = Settings(settings=[DefaultConfigFile(self._mmc)])

        self.setWindowTitle("PyMMCore Plus Sandbox")
        self.viewfinder = Viewfinder(self._mmc)
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

    def _on_error(self, type, value, traceback):
        msg = "".join(tb.format_exception(value))
        box = ErrorMessageBox(
            "Operation raised the following Exception. Please post this output "
            "and what you did to get it "
            "<a href=https://github.com/gselzer/pymmcore-plus-sandbox/issues/new>here</a>",
            msg,
        )
        box.setWindowTitle("ERROR")
        box.raise_()
        box.exec()

    def _create_menus(self) -> None:
        if (bar := self.menuBar()) is None:
            return
        self.fileMenu = cast(QMenu, bar.addMenu("File"))
        self.settingAction = QAction("Settings", self)
        self.settingAction.triggered.connect(self._settings.configure)

        self.quitAction = QAction("Quit", self)
        self.quitAction.triggered.connect(self.close)

        self.fileMenu.addAction(self.settingAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.quitAction)

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

        self.toolsMenu = cast(QMenu, bar.addMenu("Tools"))

        self.console: QtConsole | None = None
        self.consoleAction = QAction("Console", self)
        self.consoleAction.triggered.connect(self._launch_console)

        self.toolsMenu.addAction(self.consoleAction)

    def _launch_console(self):
        if self.console is None:
            # All values in the dictionary below can be accessed from the console using
            # the associated string key
            user_vars = {
                "mmc": self._mmc,
                "viewfinder": self.viewfinder,
                "mdas": self.mdas,
            }
            self.console = QtConsole(user_vars)
        self.console.show()
        self.console.raise_()

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
            try:
                self._mmc.loadSystemConfiguration(filename)
            except Exception as e:
                ErrorMessageBox(
                    "Could not load configuration due to the following error. "
                    "Please file an issue at "
                    "https://github.com/gselzer/pymmcore-plus-sandbox",
                    e.args[0],
                ).exec()

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

    def _set_up_viewfinder(self) -> Viewfinder:
        # Make viewfinder visible
        self.viewfinder.show()
        # Bring viewfinder to the top
        self.viewfinder.raise_()
        # Return viewfinder (for convenience)
        return self.viewfinder

    # -- SNAP VIEWER -- #

    @ensure_main_thread  # type: ignore [misc]
    def _handle_snap(self):
        if self._mmc.mda.is_running():
            # This signal is emitted during MDAs as well - we want to ignore those.
            return
        viewfinder = self._set_up_viewfinder()
        viewfinder.set_data(self._mmc.getImage())

    # -- LIVE VIEWER -- #

    @ensure_main_thread  # type: ignore [misc]
    def _start_live_viewer(self):
        viewfinder = self._set_up_viewfinder()
        viewfinder.live_view = True

        # Start timer to update live viewer
        interval = int(self._mmc.getExposure())
        self._live_timer_id = self.startTimer(
            interval, QtCore.Qt.TimerType.PreciseTimer
        )

    def _stop_live_viewer(self, cameraLabel: str) -> None:
        # Pause live viewer, but leave it open.
        if self.viewfinder.live_view:
            self.viewfinder.live_view = False
            self.killTimer(self._live_timer_id)
            self._live_timer_id = None

    def _update_viewer(self, data: np.ndarray | None = None) -> None:
        """Update viewer with the latest image from the circular buffer."""
        if data is None:
            if self._mmc.getRemainingImageCount() == 0:
                return
            try:
                if self.viewfinder:
                    self.viewfinder.set_data(self._mmc.getLastImage())
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
        idx = dict(event.index)
        if "g" in idx:
            idx.pop("g")
        current_mda.set_current_index(idx)

    @ensure_main_thread  # type: ignore [misc]
    def _on_mda_started(self, sequence: MDASequence) -> None:
        """Create temp folder and block gui when mda starts."""
        # TODO this field is likely limiting - consider throwing it in metadata?
        # TODO can we discern whether the sequence is being written to file?
        # If so, should we avoid viewing it?
        # TODO consider whether/how to expose other datastores
        self.mda_data = GridPlanTensorStoreHandler(
            sequence,
            driver="zarr",
            kvstore={"driver": "memory"},
            spec={"dtype": _data_type(self._mmc)},
        )
        self.current_mda = View()
        self.current_mda.show()
        self.mdas.append(self.current_mda)

    def _on_mda_finished(self, sequence: MDASequence) -> None:
        # Nothing to do...yet
        pass


class GridPlanTensorStoreHandler(TensorStoreHandler):
    def __init__(
        self,
        sequence: MDASequence,
        *,
        driver: TsDriver = "zarr",
        kvstore: str | dict | None = "memory://",
        path: str | PathLike | None = None,
        delete_existing: bool = False,
        spec: Mapping | None = None,
    ) -> None:
        super().__init__(
            driver=driver,
            kvstore=kvstore,
            path=path,
            delete_existing=delete_existing,
            spec=spec,
        )
        self._sequence = sequence
        self._evaluate_grid_plan()

    def get_shape_chunks_labels(
        self, frame_shape: tuple[int, ...], seq: MDASequence | None
    ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[str, ...]]:
        shape, chunks, labels = super().get_shape_chunks_labels(frame_shape, seq)

        if "g" in labels:
            g_idx = labels.index("g")
            x_idx = labels.index("x")
            y_idx = labels.index("y")
            # TODO: Consider overlap
            chunks = chunks[:g_idx] + chunks[g_idx + 1 :]

            shape = list(shape)
            shape[x_idx] = self._width
            shape[y_idx] = self._height
            shape.pop(g_idx)
            shape = tuple(shape)

            labels = labels[:g_idx] + labels[g_idx + 1 :]

        return shape, chunks, labels

    def _event_index_to_store_index(
        self, index: Mapping[str, int | slice]
    ) -> ts.DimExpression:
        if self._nd_storage:
            keys, values = [list(a) for a in zip(*index.items())]
            if "g" in keys:
                g_idx = keys.index("g")
                x = int(self._idx_to_pos[values[g_idx]].x - self._min[0])
                y = int(self._idx_to_pos[values[g_idx]].y - self._min[1])

                # TODO: Consider overlap
                keys = keys[:g_idx] + keys[g_idx + 1 :] + ["x", "y"]

                values = (
                    values[:g_idx]
                    + values[g_idx + 1 :]
                    + [slice(x, x + self._fov[0]), slice(y, y + self._fov[1])]
                )

            # NB: There's some issue values being a list - not sure why.
            return self._ts.d[*keys][*values]
        raise NotImplementedError()

    def _evaluate_grid_plan(self):
        gp = self._sequence.grid_plan
        if isinstance(gp, GridRowsColumns):
            w = (gp.fov_width * gp.rows) - (gp.overlap[0] * (gp.rows - 1))
            h = (gp.fov_width * gp.rows) - (gp.overlap[0] * (gp.rows - 1))
            self._width = int(w)
            self._height = int(h)
            self._fov = [int(gp.fov_width), int(gp.fov_height)]
            self._min = [0.0, 0.0]
            self._idx_to_pos = list(gp.iter_grid_positions())
            for pos in self._idx_to_pos:
                self._min[0] = min(self._min[0], pos.x)
                self._min[1] = min(self._min[1], pos.y)
            self._r = gp.rows
            self._c = gp.columns
        else:
            raise ValueError("Unrecognized GridPlan:")


def launch():
    """Launches the GUI and blocks."""

    qapp = QApplication(sys.argv)
    w = APP()
    w.show()

    qapp.exec()


if __name__ == "__main__":
    launch()
