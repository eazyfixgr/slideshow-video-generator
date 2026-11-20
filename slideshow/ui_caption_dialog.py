"""Caption entry points routed to the embedded inspector."""

from .ui_caption_media import MediaCaptionMixin


class CaptionsMixin(MediaCaptionMixin):
    def open_video_text(self):
        return self.open_text_captions_manager("by_type", "video")

    def open_photo_captions(self):
        return self.open_text_captions_manager("by_type", "image")

    def open_text_window(self):
        return self.open_text_captions_manager()

    def open_text_captions_manager(self, initial_strategy=None, initial_media=None):
        self._commit_pending_caption_apply()
        if initial_media:
            self._inline_caption_scope = ("Βίντεο" if initial_media == "video"
                                          else "Φωτογραφίες")
        elif initial_strategy == "all":
            self._inline_caption_scope = "Όλο το project"
        self._set_inspector_view("captions")
        return self.inspector_content

    def _sync_captions_inspector(self):
        self._render_inspector()
