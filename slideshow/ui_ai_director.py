"""AI Director dialog: brief + library media → validated plan → project."""

import threading

import tkinter as tk
from tkinter import ttk, messagebox

from .ai_director import (apply_plan, build_messages, ensure_inventory,
                          parse_plan, prepare_vision_images, validate_plan,
                          vision_message_parts)
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import (ScrollFrame, aspect_label, flat_button,
                         primary_button)


class AIDirectorMixin:
    def _director_config(self):
        settings = self.settings
        base = (settings.get("ai_director_base_url") or
                self._ai_base_url()).strip().rstrip("/")
        key = (settings.get("ai_director_api_key") or
               settings.get("ai_api_key") or "").strip()
        model = (settings.get("ai_director_model") or
                 self._ai_model() or "").strip()
        return base, key, model

    def show_ai_director(self):
        existing = getattr(self, "_ai_director_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return existing
            except tk.TclError:
                pass
        if hasattr(self, "_ensure_library_ids"):
            self._ensure_library_ids()
        inventory = ensure_inventory(self)
        if not inventory:
            messagebox.showinfo(
                "AI Director",
                "Η βιβλιοθήκη είναι άδεια.\n\nΠρόσθεσε πρώτα φωτογραφίες ή βίντεο "
                "αριστερά και μετά ξαναπάτησε AI Director.")
            return
        dialog = tk.Toplevel(self.root)
        self._ai_director_dialog = dialog
        dialog.title("AI Director")
        dialog.geometry("900x820")
        dialog.minsize(720, 620)
        dialog.transient(self.root)
        dialog.grab_set()
        scroller = ScrollFrame(dialog, background=P["background"])
        scroller.pack(fill="both", expand=True)
        body = tk.Frame(scroller.body, bg=P["background"], padx=18, pady=14)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="AI Director", bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(body, text="Γράψε το θέμα. Ο Director θα διαλέξει media, σειρά, "
                           "captions, διάρκειες και template.",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 9),
                 wraplength=720, justify="left").pack(anchor="w", pady=(2, 10))
        tk.Label(body, text="Θέμα / οδηγίες", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        brief = tk.Text(body, height=5, wrap="word", undo=True,
                        font=("Segoe UI", 10), bg=P["field"], fg=P["text"],
                        insertbackground=P["text"])
        brief.pack(fill="x", pady=(3, 8))
        options = tk.Frame(body, bg=P["background"])
        options.pack(fill="x", pady=(0, 8))
        duration_var = tk.StringVar(value="30")
        tk.Label(options, text="Διάρκεια (δευτ.)", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Spinbox(options, from_=5, to=120, textvariable=duration_var,
                    width=8).grid(row=1, column=0, sticky="w", padx=(0, 18))
        aspect_var = tk.StringVar(value=aspect_label(self.settings.get("resolution")))
        tk.Label(options, text="Μορφή", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8)).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Combobox(options, textvariable=aspect_var, state="readonly", width=10,
                     values=("9:16", "4:5", "1:1", "16:9")).grid(
            row=1, column=1, sticky="w", padx=(0, 18))
        registry = self.template_registry()
        template_var = tk.StringVar(value="Auto (project default)")
        tk.Label(options, text="Template", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Combobox(options, textvariable=template_var, state="readonly", width=24,
                     values=("Auto (project default)", *registry)).grid(
            row=1, column=2, sticky="w")
        style_var = tk.StringVar(value=self.settings.get("ai_director_style", ""))
        tk.Label(body, text="Ύφος / κατεύθυνση", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Entry(body, textvariable=style_var).pack(fill="x", pady=(3, 8))
        vision_var = tk.BooleanVar(value=bool(self.settings.get("ai_director_vision")))
        ttk.Checkbutton(body, text="Ο Director να διαβάσει και τις εικόνες (vision)",
                        variable=vision_var).pack(anchor="w")
        tk.Label(body, text="Με το vision, μικρά αντίγραφα εικόνων στέλνονται στον "
                           "πάροχο AI. Χωρίς αυτό στέλνονται μόνο metadata/filenames.",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 7),
                 wraplength=720, justify="left").pack(anchor="w", pady=(0, 8))
        tk.Label(body, text="Τι δείχνει κάθε media (προαιρετικό, βοηθάει πολύ)",
                 bg=P["background"], fg=P["text"], font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(4, 2))
        tk.Label(body, text="Άφησέ το κενό για να χρησιμοποιηθούν filename/τύπος. "
                           "Για καλύτερο αποτέλεσμα γράψε π.χ. «εξωτερικό, θάλασσα, ηλιοβασίλεμα».",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 8),
                 wraplength=720, justify="left").pack(anchor="w", pady=(0, 4))
        notes = {}
        shown = 0
        for item in inventory:
            if shown >= 40:
                tk.Label(body, text=f"…και {len(inventory) - shown} ακόμη media",
                         bg=P["background"], fg=P["muted"], font=("Segoe UI", 8)).pack(
                    anchor="w", pady=(2, 0))
                break
            row = tk.Frame(body, bg=P["background"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=item["filename"][:42], width=42, anchor="w",
                     bg=P["background"], fg=P["muted"], font=("Segoe UI", 8)).pack(
                side="left")
            var = tk.StringVar(value=item.get("description", ""))
            notes[item["id"]] = var
            ttk.Entry(row, textvariable=var).pack(
                side="left", fill="x", expand=True, padx=(6, 0))
            shown += 1

        status = tk.StringVar(value="")
        tk.Label(body, textvariable=status, bg=P["background"], fg=P["accent"],
                 font=("Segoe UI", 9), wraplength=720, justify="left").pack(
            anchor="w", pady=(10, 2))
        buttons = tk.Frame(dialog, bg=P["panel"])
        buttons.pack(fill="x", padx=18, pady=(0, 12))
        generate_btn = primary_button(buttons, "Δημιουργία πλάνου",
                                      lambda: generate(), font=("Segoe UI", 10, "bold"),
                                      padx=16, pady=7)
        generate_btn.pack(side="left")
        flat_button(buttons, "Κλείσιμο", dialog.destroy, background=P["raised"],
                    foreground=P["text"], active_background=P["selected"]).pack(
            side="right")
        brief.focus_set()

        def set_busy(busy):
            generate_btn.configure(state="disabled" if busy else "normal")

        def generate():
            topic = brief.get("1.0", "end-1c").strip()
            if not topic:
                status.set("Γράψε πρώτα το θέμα ή τις οδηγίες.")
                return
            try:
                target = max(5.0, min(120.0, float(duration_var.get())))
            except (TypeError, ValueError):
                status.set("Γράψε έγκυρη διάρκεια.")
                return
            base, key, model = self._director_config()
            if not key and not base.startswith(("http://localhost", "http://127.")):
                status.set("Χρειάζεται API key για τον Director. Άνοιξε AI Settings → AI Director.")
                return
            for item in inventory:
                if item["id"] not in notes:
                    continue
                description = notes[item["id"]].get().strip()
                item["description"] = description
                for _kind, _path, library_edit in self.library_media:
                    if library_edit.get("library_id") == item["id"]:
                        if library_edit.get("ai_description") != description:
                            library_edit["ai_description"] = description
                            self.is_modified = True
                        break
            choice = template_var.get()
            template = None if choice.startswith("Auto") else choice
            config = {
                "brief": topic,
                "target_duration": target,
                "aspect": aspect_var.get(),
                "template": template,
                "style": style_var.get().strip(),
            }
            set_busy(True)
            status.set("Ο Director διαβάζει τη βιβλιοθήκη και ετοιμάζει πλάνο...")
            registry_snapshot = dict(registry)
            vision_model = (self.settings.get("ai_director_vision_model") or
                            model or "").strip()
            threading.Thread(target=worker,
                             args=(topic, inventory, config, vision_var.get(),
                                   base, key, model, vision_model,
                                   registry_snapshot),
                             daemon=True).start()

        def worker(topic, inventory, config, vision, base, key, model,
                   vision_model, registry):
            try:
                messages = build_messages(topic, inventory, config, vision=vision)
                selected = (prepare_vision_images(
                    self, inventory,
                    int(self.settings.get("ai_director_max_images", 8)))
                    if vision else [])
                if selected:
                    text = messages[1]["content"]
                    messages[1]["content"] = vision_message_parts(selected, text)
                payload = {"model": vision_model if selected else model,
                           "messages": messages, "stream": False}
                try:
                    data = self._ai_call("/chat/completions", payload, timeout=180,
                                         key=key, base_url=base)
                except Exception:
                    if not selected:
                        raise
                    messages = build_messages(topic, inventory, config, vision=False)
                    payload["model"] = model
                    payload["messages"] = messages
                    data = self._ai_call("/chat/completions", payload, timeout=180,
                                         key=key, base_url=base)
                    self._post_ui(status.set, "Το vision δεν υποστηρίχθηκε· "
                                               "χρησιμοποιήθηκαν metadata.")
                choices = data.get("choices") or []
                text = (choices[0].get("message", {}).get("content")
                        if choices else "") or ""
                plan = validate_plan(parse_plan(text), inventory,
                                     config["aspect"], registry)
                self._post_ui(show_plan, plan, inventory)
            except Exception as error:
                self._post_ui(show_error, str(error))

        def show_error(message):
            if not dialog.winfo_exists():
                return
            set_busy(False)
            status.set(message)
            messagebox.showerror("AI Director", message, parent=dialog)

        def show_plan(plan, inventory):
            if not dialog.winfo_exists():
                return
            set_busy(False)
            status.set("Το πλάνο είναι έτοιμο. Έλεγξέ το και πάτησε Εφαρμογή.")
            plan_dialog = tk.Toplevel(dialog)
            plan_dialog.title("AI Director — Πλάνο")
            plan_dialog.geometry("760x760")
            plan_dialog.transient(dialog)
            plan_dialog.grab_set()
            by_id = {item["id"]: item for item in inventory}
            frame = tk.Frame(plan_dialog, bg=P["background"], padx=16, pady=12)
            frame.pack(fill="both", expand=True)
            tk.Label(frame, text=plan["title"], bg=P["background"], fg=P["text"],
                     font=("Segoe UI", 15, "bold"), wraplength=700, justify="left").pack(
                anchor="w")
            total = sum(scene["duration"] * max(1, len(scene.get("source_ids", [])))
                        for scene in plan["scenes"])
            media_count = sum(max(1, len(scene.get("source_ids", [])))
                              for scene in plan["scenes"])
            tk.Label(frame, text=f"{plan['aspect']} · {total:.1f}s · "
                                f"{len(plan['scenes'])} σκηνές · {media_count} media" +
                                (f" · {plan['template']}" if plan["template"] else ""),
                     bg=P["background"], fg=P["accent"], font=("Segoe UI", 9)).pack(
                anchor="w", pady=(2, 8))
            list_scroller = ScrollFrame(frame, background=P["background"])
            list_scroller.pack(fill="both", expand=True)
            scene_frame = tk.Frame(list_scroller.body, bg=P["background"])
            scene_frame.pack(fill="both", expand=True)
            for index, scene in enumerate(plan["scenes"], 1):
                items = [by_id[source_id] for source_id in scene.get("source_ids", [])
                         if source_id in by_id]
                if len(items) > 1:
                    names = ", ".join(item["filename"] for item in items[:3])
                    if len(items) > 3:
                        names += f" +{len(items) - 3}"
                    title = f"Ομάδα ({len(items)}): {names}"
                else:
                    title = items[0]["filename"] if items else "media"
                row = tk.Frame(scene_frame, bg=P["raised"], padx=8, pady=6)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=f"{index:02d}  {title}",
                         bg=P["raised"], fg=P["text"], font=("Segoe UI", 9, "bold"),
                         anchor="w").pack(fill="x")
                tk.Label(row, text=f"{scene['duration']:.1f}s" +
                                   (f" · {scene['background_mode']}"
                                    if scene["background_mode"] else ""),
                         bg=P["raised"], fg=P["muted"], font=("Segoe UI", 8)).pack(
                    anchor="w")
                if scene["caption"]:
                    tk.Label(row, text=scene["caption"], bg=P["raised"], fg=P["muted"],
                             font=("Segoe UI", 9), wraplength=680, justify="left").pack(
                        anchor="w", pady=(2, 0))
            actions = tk.Frame(plan_dialog, bg=P["panel"])
            actions.pack(fill="x", padx=16, pady=(0, 12))

            def apply():
                if self.media_files and not messagebox.askyesno(
                        "AI Director", "Το project έχει ήδη σκηνές. Να αντικατασταθούν "
                                     "με το πλάνο του Director;", parent=plan_dialog):
                    return
                apply_plan(self, plan)
                plan_dialog.destroy()
                dialog.destroy()
                messagebox.showinfo("AI Director",
                                    "Το πλάνο εφαρμόστηκε. Μπορείς να το αλλάξεις "
                                    "χειροκίνητα ή να κάνεις Undo.", parent=self.root)

            def close_plan():
                plan_dialog.destroy()
                if dialog.winfo_exists():
                    dialog.grab_set()

            primary_button(actions, "Εφαρμογή στο project", apply,
                           font=("Segoe UI", 9, "bold")).pack(side="left")
            flat_button(actions, "Πίσω", close_plan,
                        background=P["raised"], foreground=P["text"],
                        active_background=P["selected"]).pack(side="right")
            flat_button(actions, "Άκυρο", close_plan,
                        background=P["raised"], foreground=P["muted"],
                        active_background=P["selected"]).pack(side="right", padx=(0, 6))
            plan_dialog.protocol("WM_DELETE_WINDOW", close_plan)

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        return dialog
