# NVDIMM configuration dialog
#
# Copyright (C) 2018  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
from blivet.static_data import nvdimm
from pykickstart.constants import NVDIMM_MODE_SECTOR
from pyanaconda.core.i18n import _, CN_
from pyanaconda.modules.common.task import async_run_task
from pyanaconda.modules.common.constants.services import STORAGE
from pyanaconda.modules.common.constants.objects import NVDIMM
from pyanaconda.modules.common.errors.configuration import StorageConfigurationError
from pyanaconda.modules.storage.reset import StorageResetTask
from pyanaconda.ui.gui import GUIObject

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

__all__ = ["NVDIMMDialog"]

DEFAULT_SECTOR_SIZE = 512

PAGE_ACTION = 1
PAGE_RESULT_ERROR = 2
PAGE_RESULT_SUCCESS = 3


class NVDIMMDialog(GUIObject):
    """
       .. inheritance-diagram:: NVDIMMDialog
          :parts: 3
    """
    builderObjects = ["nvdimmDialog", "sectorSizeAdjustment"]
    mainWidgetName = "nvdimmDialog"
    uiFile = "spokes/advstorage/nvdimm.glade"

    def __init__(self, data, storage, namespaces):
        GUIObject.__init__(self, data)
        self._storage = storage
        self._namespaces = namespaces
        self._nvdimm_proxy = STORAGE.get_proxy(NVDIMM)

        self._startButton = self.builder.get_object("startButton")
        self._infoLabel = self.builder.get_object("infoLabel")
        self._devicesLabel = self.builder.get_object("devicesLabel")
        self._cancelButton = self.builder.get_object("cancelButton")
        self._okButton = self.builder.get_object("okButton")
        self._reconfigureSpinner = self.builder.get_object("reconfigureSpinner")
        self._repopulateSpinner = self.builder.get_object("repopulateSpinner")
        self._repopulateLabel = self.builder.get_object("repopulateLabel")
        self._sectorSizeLabel = self.builder.get_object("sectorSizeLabel")
        self._sectorSizeSpinButton = self.builder.get_object("sectorSizeSpinButton")
        self._conditionNotebook = self.builder.get_object("conditionNotebook")
        self._deviceErrorLabel = self.builder.get_object("deviceErrorLabel")

    def refresh(self):
        self._sectorSizeSpinButton.set_value(DEFAULT_SECTOR_SIZE)

        if self._namespaces:
            self._devicesLabel.set_text("%s" % ", ".join(self._namespaces))
        else:
            self._sectorSizeSpinButton.set_sensitive(False)
            self._okButton.set_sensitive(False)
            self._startButton.set_sensitive(False)
            self._sectorSizeLabel.set_sensitive(False)
            self._infoLabel.set_text(
                CN_("GUI|Advanced Storage|NVDIM", "No device to be reconfigured selected.")
            )

    def run(self):
        rc = self.window.run()
        self.window.destroy()
        return rc

    @property
    def sector_size(self):
        """Size of the sector."""
        return self._sectorSizeSpinButton.get_value_as_int()

    def on_start_clicked(self, *args):
        """Start to reconfigure the namespaces."""
        if not self._namespaces:
            return

        namespace = self._namespaces.pop(0)
        self.reconfigure_namespace(namespace)

    def reconfigure_namespace(self, namespace):
        """Start the reconfiguration task."""
        # Update the widgets.
        self._conditionNotebook.set_current_page(PAGE_ACTION)
        self._startButton.set_sensitive(False)
        self._cancelButton.set_sensitive(False)
        self._sectorSizeSpinButton.set_sensitive(False)
        self._okButton.set_sensitive(False)

        # Get the data.
        mode = NVDIMM_MODE_SECTOR
        sector_size = self.sector_size

        # Get the task.
        task_path = self._nvdimm_proxy.ReconfigureWithTask(namespace, mode, sector_size)
        task_proxy = STORAGE.get_proxy(task_path)

        # Start the reconfiguration.
        async_run_task(task_proxy, self.reconfigure_finished)

        self._reconfigureSpinner.start()

    def reconfigure_finished(self, task_proxy):
        """Callback for reconfigure_namespaces."""
        # Stop the spinner.
        self._reconfigureSpinner.stop()

        try:
            # Finish the task.
            task_proxy.Finish()
        except StorageConfigurationError as e:
            # Configuration has failed, show the error.
            self._deviceErrorLabel.set_text(str(e))
            self._conditionNotebook.set_current_page(PAGE_RESULT_ERROR)
            self._okButton.set_sensitive(True)
        else:
            # More namespaces to configure? Continue.
            if self._namespaces:
                namespace = self._namespaces.pop(0)
                self.reconfigure_namespace(namespace)
                return

            # Otherwise, repopulate the device tree.
            self.repopulate_storage()

    def repopulate_storage(self):
        """Repopulate the storage."""
        # Update the widgets.
        self._conditionNotebook.set_current_page(PAGE_RESULT_SUCCESS)

        # Update the namespaces info.
        nvdimm.update_namespaces_info()

        # Get the task.
        task = StorageResetTask(self._storage)
        task.stopped_signal.connect(lambda: self.repopulate_finished(task))

        # Start the task.
        task.start()

        self._repopulateSpinner.start()

    def repopulate_finished(self, task):
        """Callback for repopulate_storage.

        :param task: an instance of the task
        """
        # Stop the spinner.
        self._repopulateSpinner.stop()

        # Finish the task. The failures are fatal.
        task.finish()

        # Set up the UI.
        self._repopulateLabel.set_text(_("Rescanning disks finished."))
        self._okButton.set_sensitive(True)
