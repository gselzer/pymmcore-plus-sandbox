from fonticon_mdi6 import MDI6
from pymmcore_plus import CMMCorePlus, DeviceType
from pymmcore_widgets import StageWidget
from qtpy.QtCore import QSize
from qtpy.QtGui import QCloseEvent
from qtpy.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)
from superqt.fonticon import icon


class StageButton(QPushButton):
    """Create a mda widget QPushButton.

    TODO

    Parameters
    ----------
    parent : QWidget | None
        Optional parent widget.
    mmcore : CMMCorePlus | None
        Optional [`pymmcore_plus.CMMCorePlus`][] micromanager core.
        By default, None. If not specified, the widget will use the active
        (or create a new)
        [`CMMCorePlus.instance`][pymmcore_plus.core._mmcore_plus.CMMCorePlus.instance].

    Examples
    --------
    !!! example "Combining `SnapButton` with other widgets"

        see [ImagePreview](ImagePreview.md#example)
    """

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        mmcore: CMMCorePlus | None = None,
    ) -> None:
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self._mmc = mmcore or CMMCorePlus.instance()
        self._stages: StagesWidget | None = None

        self._mmc.events.systemConfigurationLoaded.connect(self._on_system_cfg_loaded)
        self._on_system_cfg_loaded()
        self.destroyed.connect(self._disconnect)

        self._create_button()

        self.setEnabled(False)
        if len(self._mmc.getLoadedDevices()) > 1:
            self.setEnabled(True)

    def _create_button(self) -> None:
        self.setText("Stage Control")
        self.setIcon(icon(MDI6.arrow_all, color=(0, 255, 0)))
        self.setIconSize(QSize(30, 30))
        self.clicked.connect(self.launch_stage_control)

    def launch_stage_control(self) -> None:
        if self._stages is None:
            self._stages = StagesWidget(parent=None, mmc=self._mmc)
        self._stages.show()
        self._stages.raise_()

    def _on_system_cfg_loaded(self) -> None:
        self.setEnabled(bool(self._mmc.getCameraDevice()))

    def _disconnect(self) -> None:
        self._mmc.events.systemConfigurationLoaded.disconnect(
            self._on_system_cfg_loaded
        )


class StagesWidget(QWidget):
    def __init__(
        self, parent: QWidget | None = None, mmc: CMMCorePlus | None = None
    ) -> None:
        super().__init__(parent=parent)
        self.mmc = mmc if mmc is not None else CMMCorePlus.instance()

        self.setLayout(QHBoxLayout())
        self.setWindowTitle("Stage Control")
        self.stage_dev_list = list(self.mmc.getLoadedDevicesOfType(DeviceType.XYStage))
        self.stage_dev_list.extend(
            iter(self.mmc.getLoadedDevicesOfType(DeviceType.Stage))
        )

        for stage_dev in self.stage_dev_list:
            if self.mmc.getDeviceType(stage_dev) is DeviceType.XYStage:
                bx = QGroupBox("XY Control")
                bx.setLayout(QHBoxLayout())
                bx.layout().addWidget(StageWidget(device=stage_dev))
                self.layout().addWidget(bx)
            if self.mmc.getDeviceType(stage_dev) is DeviceType.Stage:
                bx = QGroupBox("Z Control")
                bx.setLayout(QHBoxLayout())
                bx.layout().addWidget(StageWidget(device=stage_dev))
                self.layout().addWidget(bx)

    def has_stages(self) -> bool:
        return len(self.stage_dev_list) != 0

    def closeEvent(self, event: QCloseEvent | None):
        self.hide()
