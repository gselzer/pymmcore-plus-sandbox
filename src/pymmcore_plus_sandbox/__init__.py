from enum import Enum
import sys
from typing import Any, Hashable, List

from pymmcore_plus import CMMCorePlus
import numpy as np
import tensorstore as ts

from fonticon_mdi6 import MDI6
from qtpy import QtCore
from qtpy.QtGui import QMouseEvent
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QWidget,
)
from ndv import NDViewer
from useq import MDAEvent, MDASequence
from superqt.fonticon import icon
from pymmcore_plus_sandbox._mda_button_widget import MDAButton
from pymmcore_widgets import LiveButton, SnapButton
from superqt.utils import ensure_main_thread
from pymmcore_plus.mda.handlers import TensorStoreHandler

class SnapLiveWidget(QToolBar):
    """Tabs shown in the main window."""

    def __init__(self) -> None:
        super().__init__()
        self._create_gui()

    def _create_gui(self) -> None:

        self.snap_live_tab = QGroupBox()
        self.snap_live_tab.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.snap_live_tab_layout = QGridLayout()
        self.snap_live_tab_layout.addWidget

        # snap/live in snap_live_tab
        self.btn_wdg = QWidget()
        self.btn_wdg.setMaximumHeight(65)
        self.btn_wdg_layout = QHBoxLayout()
        self.snap_Button = SnapButton()
        self.snap_Button.setMinimumSize(QtCore.QSize(200, 50))
        self.snap_Button.setMaximumSize(QtCore.QSize(200, 50))
        self.btn_wdg_layout.addWidget(self.snap_Button)
        self.live_Button = LiveButton()
        self.live_Button.setMinimumSize(QtCore.QSize(200, 50))
        self.live_Button.setMaximumSize(QtCore.QSize(200, 50))
        self.btn_wdg_layout.addWidget(self.live_Button)
        self.mda_Button = MDAButton()
        self.mda_Button.setMinimumSize(QtCore.QSize(200, 50))
        self.mda_Button.setMaximumSize(QtCore.QSize(200, 50))
        self.btn_wdg_layout.addWidget(self.mda_Button)

        self.btn_wdg.setLayout(self.btn_wdg_layout)

        self.snap_live_tab_layout.addWidget(self.btn_wdg, 1, 0, 1, 2)
        self.snap_live_tab.setLayout(self.snap_live_tab_layout)

        self.addWidget(self.snap_live_tab)

class APP (QMainWindow):
    """Create a QToolBar for the Main Window."""

    def __init__(self) -> None:
        super().__init__()
        self._mmc = CMMCorePlus.instance()
        self.windows = []
        self.live_viewer = None
        self._live_timer_id: int | None = None

        # Toolbar
        self._dock_widgets: dict[str, QDockWidget] = {}
        toolbar_items = [
            SnapLiveWidget(),
        ]
        for item in toolbar_items:
            if item:
                self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, item)
            else:
                self.addToolBarBreak(QtCore.Qt.ToolBarArea.TopToolBarArea)
        
        # TODO: In my testing, any combination of three new windows causes a segmentation fault :(
        
        # Snap signals
        self._mmc.events.imageSnapped.connect(self.new_snap_viewer)

        # Live signals
        self._mmc.events.continuousSequenceAcquisitionStarted.connect(self.start_live_viewer)
        self._mmc.events.sequenceAcquisitionStopped.connect(self.stop_live_viewer)

        # MDA signals
        self._mmc.mda.events.frameReady.connect(self._on_mda_frame)
        self._mmc.mda.events.sequenceStarted.connect(self._on_mda_started)
        self._mmc.mda.events.sequenceFinished.connect(self._on_mda_finished)
    
    def closeEvent(self, event):
        # HACK: Close all windows when the "main window" is closed.
        # Ideally, this functionality would be accomplished through setting parent-child relationships.
        # However parent-child relationships also enforce the child being drawn within the parent, which is undesirable.
        super().closeEvent(event)
        QApplication.quit()

    # -- SNAP VIEWER -- #
    
    def new_snap_viewer(self):
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

    def start_live_viewer(self):
        # Close old live viewer
        if (self.live_viewer):
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
        self._live_timer_id = self.startTimer(interval, QtCore.Qt.TimerType.PreciseTimer)
    
    def stop_live_viewer(self):
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
                # TODO Does it help us to do the write asyncronously, and just call setIndex later?
                self.ts_array[:] = self._mmc.getLastImage()
                # This call is important, telling the StackViewer to redraw the current data buffer.
                self.live_viewer.set_current_index({})
            except (RuntimeError, IndexError):
                # circular buffer empty
                return
    
    # -- MDA VIEWER -- #

    def timerEvent(self, a0: QtCore.QTimerEvent | None) -> None:
        # Handle the timer event by updating the viewer (on gui thread)
        self._update_viewer()
    

    def _on_mda_frame(self, image: np.ndarray, event: MDAEvent) -> None:
        """Called on the `frameReady` event from the core."""
        self.mda_data.frameReady(image, event, {})
        if not hasattr(self.mda_viewer, "_data_wrapper"):
            self.mda_viewer.set_data(self.mda_data.store)
   
    @ensure_main_thread  # type: ignore [misc]
    def _on_mda_started(self, sequence: MDASequence) -> None:
        """Create temp folder and block gui when mda starts."""
        # TODO this field is likely limiting - consider throwing it in metadata?
        # TODO can we discern whether the sequence is being written to file? If so, should we avoid viewing it?
        # TODO consider whether/how to expose other datastores 
        self.mda_data = TensorStoreHandler(
            driver="zarr",
            kvstore={"driver": "memory"},
            spec= {
                "dtype": "uint16" # TODO
            }
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
            return  ts.uint16
        elif px_type == "32bit":
            return ts.uint32
        else:
            raise Exception(f"Unsupported Pixel Type: {px_type}")


def launch():

    qapp = QApplication(sys.argv)
    w = APP()
    w.show()

    mmcore = CMMCorePlus.instance()
    mmcore.loadSystemConfiguration("./MMConfig_demo.cfg")

    qapp.exec()

if __name__ == "__main__":
    launch()