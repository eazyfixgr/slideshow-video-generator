"""Resizable workspace columns, remembered independently for each profile."""

import math


class WorkspaceLayoutMixin:
    def _setup_workspace_layout(self):
        self._workspace_dragging = False
        self._workspace_restore_job = None
        self._workspace_restoring = False
        self.workspace.bind("<Configure>", self._queue_workspace_restore, add="+")
        self.workspace.bind("<Map>", self._queue_workspace_restore, add="+")
        self.workspace.bind("<ButtonPress-1>", self._workspace_press, add="+")
        self.workspace.bind("<ButtonRelease-1>", self._workspace_release, add="+")
        self.workspace.bind("<Motion>", self._workspace_cursor, add="+")
        self.workspace.bind("<Leave>", lambda _e: self.workspace.configure(cursor=""), add="+")
        self._load_profile_workspace_layout()

    def _load_profile_workspace_layout(self):
        value = self.settings.get("workspace_layout")
        self._workspace_ratios = None
        if isinstance(value, (list, tuple)) and len(value) == 3:
            try:
                values = [float(part) for part in value]
                total = sum(values)
                if (math.isfinite(total) and
                        all(math.isfinite(part) and part > 0 for part in values)):
                    self._workspace_ratios = [part / total for part in values]
            except (TypeError, ValueError, OverflowError):
                pass
        self._workspace_layout_profile = self.active_profile_id
        self._workspace_dragging = False
        self._queue_workspace_restore()

    def _queue_workspace_restore(self, _event=None):
        if self._workspace_dragging or self._workspace_restoring:
            return
        if self._workspace_restore_job is not None:
            self.root.after_cancel(self._workspace_restore_job)
        self._workspace_restore_job = self.root.after_idle(self._restore_workspace_layout)

    def _restore_workspace_layout(self):
        self._workspace_restore_job = None
        if self._workspace_dragging:
            return
        workspace = self.workspace
        sash = int(workspace.cget("sashwidth"))
        available = workspace.winfo_width() - 2 * sash
        panes = [workspace.nametowidget(name) for name in workspace.panes()]
        minimum = [int(workspace.panecget(pane, "minsize")) for pane in panes]
        if available < sum(minimum):
            return
        ratios = self._workspace_ratios
        left = max(minimum[0], round(available * ratios[0]) if ratios else 250)
        right = max(minimum[2], round(available * ratios[2]) if ratios else 360)
        side_space = available - minimum[1]
        if left + right > side_space:
            extra = left + right - minimum[0] - minimum[2]
            factor = (side_space - minimum[0] - minimum[2]) / max(1, extra)
            left = minimum[0] + round((left - minimum[0]) * factor)
            right = side_space - left
        center = available - left - right
        self._workspace_restoring = True
        try:
            for pane, width in zip(panes, (left, center, right)):
                workspace.paneconfigure(pane, width=width)
        finally:
            self._workspace_restoring = False

    def _workspace_cursor(self, event):
        hit = self.workspace.identify(event.x, event.y)
        self.workspace.configure(cursor="sb_h_double_arrow" if hit else "")

    def _workspace_press(self, event):
        self._workspace_dragging = bool(self.workspace.identify(event.x, event.y))
        if self._workspace_dragging and self._workspace_restore_job is not None:
            self.root.after_cancel(self._workspace_restore_job)
            self._workspace_restore_job = None

    def _workspace_release(self, _event):
        if self._workspace_dragging:
            self._workspace_dragging = False
            profile = self.active_profile_id
            self.root.after_idle(lambda: self._remember_workspace_layout()
                                 if self.active_profile_id == profile else None)

    def _remember_workspace_layout(self):
        if (not hasattr(self, "workspace") or not self.workspace.winfo_ismapped() or
                self._workspace_layout_profile != self.active_profile_id):
            return
        widths = [self.workspace.nametowidget(name).winfo_width()
                  for name in self.workspace.panes()]
        if min(widths) <= 1:
            return
        total = sum(widths)
        self._workspace_ratios = [width / total for width in widths]
        self.settings["workspace_layout"] = self._workspace_ratios[:]
        self.save_settings()
