"""Compatibility commands for the embedded Slide Design inspector."""


class PresentationMixin:
    def open_presentation_editor(self, idx):
        if idx is None or not 0 <= idx < len(self.media_files):
            return
        self._commit_pending_caption_apply()
        if idx not in self._selected():
            self.select_scene(idx, sync_inspector=False)
        self._inline_design_scope = "Τρέχουσα σκηνή"
        self._set_inspector_view("design")
        return self.inspector_content

    def open_storyboard_editor(self):
        self._set_inspector_view("design")
        return self.inspector_content
