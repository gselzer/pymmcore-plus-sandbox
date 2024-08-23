from __future__ import annotations

from os import path
from typing import TYPE_CHECKING, Any, Hashable, Iterable, Mapping

import tensorstore as ts
import tifffile
from fonticon_mdi6 import MDI6
from ndv import DataWrapper, NDViewer
from pymmcore_plus import CMMCorePlus
from pymmcore_widgets import LiveButton, SnapButton
from qtpy.QtCore import QSize
from qtpy.QtGui import QCloseEvent
from qtpy.QtWidgets import QFileDialog, QPushButton, QSizePolicy, QWidget
from superqt import ensure_main_thread
from superqt.fonticon import icon

from pymmcore_plus_sandbox._utils import _data_type

if TYPE_CHECKING:
    from concurrent.futures import Future

    import numpy as np
    from ndv import Indices


class SaveButton(QPushButton):
    """Create a QPushButton to save Viewfinder data.

    TODO

    Parameters
    ----------
    viewfinder : Viewfinder | None
        The `Viewfinder` displaying the data to save.
    parent : QWidget | None
        Optional parent widget.

    """

    def __init__(
        self,
        viewer: "View",
        *,
        parent: QWidget | None = None,
        mmcore: CMMCorePlus | None = None,
    ) -> None:
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )
        self._viewer = viewer
        self._mmc = mmcore if mmcore is not None else CMMCorePlus.instance()

        self._create_button()

    def _create_button(self) -> None:
        self.setText("Save")
        self.setIcon(icon(MDI6.content_save, color=(0, 255, 0)))
        self.setIconSize(QSize(30, 30))

        self.clicked.connect(self._save_data)

    def _save_data(self) -> None:
        # Stop sequence acquisitions
        self._mmc.stopSequenceAcquisition()

        (file, _) = QFileDialog.getSaveFileName(
            self._viewer,
            "Save Image",
            "",  #
            "*.tif",  # Acceptible extensions
        )
        (p, extension) = path.splitext(file)
        if extension == ".tif":
            data = self._viewer.data_wrapper.isel({})
            # TODO: Save metadata?
            tifffile.imwrite(file, data=data)
        # TODO: Zarr seems like it would be easily supported through
        # self._view.data_wrapper.save_as_zarr, but it is not implemented
        # by TensorStoreWrapper


class ExportButton(QPushButton):
    """Create a QPushButton to create a View from the Viewfinder's current data.

    TODO

    Parameters
    ----------
    viewfinder : Viewfinder | None
        The `Viewfinder` displaying the data to save.
    parent : QWidget | None
        Optional parent widget.

    """

    def __init__(
        self,
        viewfinder: "Viewfinder",
        *,
        parent: QWidget | None = None,
        mmcore: CMMCorePlus | None = None,
    ) -> None:
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )
        self._view = viewfinder
        self._mmc = mmcore if mmcore is not None else CMMCorePlus.instance()

        self._create_button()

    def _create_button(self) -> None:
        # TODO: Better button text
        self.setText("Export")
        self.setIcon(icon(MDI6.export, color=(0, 255, 0)))
        self.setIconSize(QSize(30, 30))

        self.clicked.connect(self._export_data)

    def _export_data(self) -> None:
        future = self._view.data_wrapper.isel_async([{}])

        @ensure_main_thread  # type: ignore
        def cb(future: Future[Iterable[tuple[Indices, np.ndarray]]]) -> None:
            view = View(self._mmc)

            for idx, datum in future.result():
                view.set_data(datum, initial_index=idx)

            view.show()
            view.raise_()

            self._view._views.append(view)

        future.add_done_callback(cb)


class View(NDViewer):
    """An NDViewer subclass tailored to passive data viewing."""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self.setWindowTitle("View")
        self._mmc = mmc if mmc is not None else CMMCorePlus.instance()

        self.save_btn = SaveButton(mmcore=self._mmc, viewer=self)
        self._btns.insertWidget(0, self.save_btn)


class Viewfinder(View):
    """An NDViewer subclass tailored to active data viewing. By active viewing, we"""

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Viewfinder")
        self.live_view: bool = False
        self._views: list[View] = []
        self._mmc = mmc if mmc is not None else CMMCorePlus.instance()

        self._btns.insertWidget(0, SnapButton(mmcore=self._mmc))
        self._btns.insertWidget(1, LiveButton(mmcore=self._mmc))
        self._btns.insertWidget(2, ExportButton(mmcore=self._mmc, viewfinder=self))

        # Create initial buffer
        self.ts_array = None
        self.ts_shape = (0, 0)
        self.bytes_per_pixel = 0

    # # Begin TODO: Remove once https://github.com/pyapp-kit/ndv/issues/39 solved

    def _update_datastore(self) -> Any:
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
                dtype=_data_type(self._mmc),
            ).result()
            super().set_data(self.ts_array)
        return self.ts_array

    def set_data(
        self,
        data: DataWrapper[Any] | Any,
        *,
        initial_index: Mapping[Hashable, int | slice] | None = None,
    ) -> None:
        if initial_index is None:
            initial_index = {}
        array = self._update_datastore()
        array[:] = data
        self.set_current_index(initial_index)

    # # End TODO: Remove once https://github.com/pyapp-kit/ndv/issues/39 solved

    # -- HELPERS -- #

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self._mmc.stopSequenceAcquisition()
        super().closeEvent(event)
