#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio
import os
import sys
import json
import requests
import threading

class MessageBox(Gtk.Box):
    def __init__(self, text, is_user=True, parent_window=None, is_code=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.parent_window = parent_window
        self.is_user = is_user
        self.is_code = is_code
        
        # Message container
        msg_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(msg_container)
        
        # Content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        msg_container.append(content_box)
        
        # Text label
        self.label = Gtk.Label(label=text)
        self.label.set_wrap(not is_code)
        self.label.set_max_width_chars(80 if is_code else 60)
        self.label.set_xalign(0)
        self.label.set_yalign(0)
        self.label.set_selectable(True)
        
        if is_code:
            self.label.set_markup("<tt>" + GLib.markup_escape_text(text) + "</tt>")
        
        # Apply style classes
        if is_code:
            self.label.add_css_class('code-block')
        else:
            self.label.add_css_class('user-message' if is_user else 'assistant-message')
        
        content_box.append(self.label)
        
        # Button container
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        button_box.set_halign(Gtk.Align.END if is_user else Gtk.Align.START)
        content_box.append(button_box)
        
        # Add buttons based on message type
        if is_code:
            # Copy button for code
            copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
            copy_btn.connect('clicked', self.on_copy_clicked)
            button_box.append(copy_btn)
            
            # Run button for commands
            if not text.strip().startswith(('import ', 'def ', 'class ')):
                run_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
                run_btn.connect('clicked', self.on_run_clicked)
                button_box.append(run_btn)
        
        elif is_user:
            # Edit button for user messages
            edit_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
            edit_btn.connect('clicked', self.on_edit_clicked)
            button_box.append(edit_btn)
        
        else:
            # Read button for assistant messages
            read_btn = Gtk.Button.new_from_icon_name("audio-speakers-symbolic")
            read_btn.connect('clicked', self.on_read_clicked)
            button_box.append(read_btn)
            
            # Copy button for assistant messages
            copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
            copy_btn.connect('clicked', self.on_copy_clicked)
            button_box.append(copy_btn)
        
        # Delete button for non-code messages
        if not is_code:
            delete_btn = Gtk.Button.new_from_icon_name("edit-delete-symbolic")
            delete_btn.connect('clicked', self.on_delete_clicked)
            button_box.append(delete_btn)
        
        # Update button styling
        for button in button_box:
            button.add_css_class('message-button')
            button.set_has_frame(False)  # Remove button borders
    
    def on_edit_clicked(self, button):
        text = self.label.get_text()
        self.parent_window.entry.set_text(text)
        self.parent_window.entry.grab_focus()
    
    def on_read_clicked(self, button):
        text = self.label.get_text()
        threading.Thread(target=lambda: os.system(f'espeak "{text}"')).start()
    
    def on_copy_clicked(self, button):
        text = self.label.get_text()
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_text(text)
    
    def on_delete_clicked(self, button):
        parent = self.get_parent()
        if parent:
            parent.remove(self)
            if isinstance(self.parent_window, MainWindow):
                self.parent_window.save_history()
    
    def on_run_clicked(self, button):
        command = self.label.get_text().strip()
        try:
            threading.Thread(target=lambda: os.system(command)).start()
        except Exception as e:
            dialog = Adw.MessageDialog.new(
                self.parent_window,
                "Error running command",
                str(e)
            )
            dialog.add_response("ok", "OK")
            dialog.present()

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        
        # Start with opacity 0
        self.set_opacity(0.0)
        
        self.setup_window()
    
    def setup_position(self):
        """Position window at the bottom center of the screen"""
        display = self.get_display()
        monitor = display.get_primary_monitor()
        if monitor:
            geometry = monitor.get_geometry()
            window_width, window_height = self.get_default_size()
            x = geometry.x + (geometry.width - window_width) // 2
            y = geometry.y + geometry.height - window_height
            self.set_default_size(window_width, window_height)
            # Don't show the window yet
            self.present()
            GLib.idle_add(self.move_and_show_window, x, y)

    def move_and_show_window(self, x, y):
        """Move the window and then make it visible"""
        window_id = self.get_surface().get_xid()
        # Move the window while it's still invisible
        os.system(f"wmctrl -ir {window_id} -e 0,{x},{y},-1,-1")
        # Add a small delay before showing the window
        GLib.timeout_add(50, self.fade_in_window)
        return False

    def fade_in_window(self):
        """Fade in the window smoothly"""
        current_opacity = self.get_opacity()
        if current_opacity < 1.0:
            self.set_opacity(min(current_opacity + 0.2, 1.0))
            GLib.timeout_add(10, self.fade_in_window)
        return False
    
    def setup_window(self):
        self.set_title("MAGI Assistant")
        self.set_default_size(800, 600)
        
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        
        # Chat history area
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        
        self.messages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.set_child(self.messages_box)
        
        # Input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.entry = Gtk.Entry()
        self.entry.set_hexpand(True)
        
        self.send_button = Gtk.Button(label="Send")
        self.send_button.add_css_class('suggested-action')
        
        input_box.append(self.entry)
        input_box.append(self.send_button)
        
        # Pack everything
        main_box.append(scroll)
        main_box.append(input_box)
        
        self.set_content(main_box)
        
        # Focus handling
        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect('leave', self.on_focus_lost)
        self.add_controller(focus_controller)

        # Position window
        GLib.timeout_add(50, self.setup_position)  # Short delay to ensure window is ready

        # Connect signals
        self.entry.connect('activate', self.on_send)
        self.send_button.connect('clicked', self.on_send)
        
        # Load history
        self.load_history()
        
        # Setup keyboard shortcuts
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(key_controller)

    def on_focus_lost(self, controller):
        """Close window when focus is lost"""
        self.close()
        
        # Connect signals
        self.entry.connect('activate', self.on_send)
        self.send_button.connect('clicked', self.on_send)
        
        # Load history
        self.load_history()
        
        # Setup keyboard shortcuts
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(key_controller)
    
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
    
    def scroll_to_bottom(self):
        def _scroll():
            parent = self.messages_box.get_parent()
            if isinstance(parent, Gtk.ScrolledWindow):
                adj = parent.get_vadjustment()
                adj.set_value(adj.get_upper() - adj.get_page_size())
        GLib.idle_add(_scroll)
    
    def add_message(self, text, is_user=True):
        msg_box = MessageBox(text, is_user, self)
        self.messages_box.append(msg_box)
        self.scroll_to_bottom()
        if is_user:
            self.save_history()
    
    def on_send(self, widget):
        text = self.entry.get_text().strip()
        if text:
            self.add_message(text, True)
            self.entry.set_text("")
            threading.Thread(target=self.send_to_ollama, args=(text,)).start()
    
    def send_to_ollama(self, prompt):
        try:
            # Create initial message box for live output
            live_box = MessageBox("...", False, self)
            self.messages_box.append(live_box)
            self.scroll_to_bottom()
            
            full_response = ""
            
            response = requests.post('http://localhost:11434/api/generate',
                                   json={'model': 'mistral',
                                        'prompt': prompt},
                                   stream=True)
            
            if response.ok:
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            if 'response' in chunk:
                                text = chunk['response']
                                full_response += text
                                
                                def update():
                                    live_box.label.set_text(full_response)
                                    self.scroll_to_bottom()
                                GLib.idle_add(update)
                                        
                        except json.JSONDecodeError:
                            continue
                
                # Split response into parts
                def split_and_create_boxes():
                    self.messages_box.remove(live_box)
                    
                    is_code = False
                    parts = full_response.split('```')
                    
                    for part in parts:
                        if part.strip():
                            msg_box = MessageBox(part.strip(), False, self, is_code)
                            self.messages_box.append(msg_box)
                            is_code = not is_code
                    
                    self.scroll_to_bottom()
                    self.save_history()
                
                GLib.idle_add(split_and_create_boxes)
            
            else:
                GLib.idle_add(lambda: self.add_message(f"Error: HTTP {response.status_code}", False))
                
        except Exception as e:
            GLib.idle_add(lambda: self.add_message(f"Error: {str(e)}", False))
    
    def load_history(self):
        try:
            with open('/tmp/MAGI/chat_history.json', 'r') as f:
                history = json.load(f)
                for msg in history:
                    msg_box = MessageBox(
                        msg['text'],
                        msg['is_user'],
                        self,
                        msg.get('is_code', False)
                    )
                    self.messages_box.append(msg_box)
                self.scroll_to_bottom()
        except FileNotFoundError:
            pass
    
    def save_history(self):
        history = []
        for child in self.messages_box:
            if isinstance(child, MessageBox):
                history.append({
                    'text': child.label.get_text(),
                    'is_user': child.is_user,
                    'is_code': child.is_code
                })
        
        os.makedirs('/tmp/MAGI', exist_ok=True)
        with open('/tmp/MAGI/chat_history.json', 'w') as f:
            json.dump(history, f)

class MAGIApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.test.app')
    
    def do_activate(self):
        win = MainWindow(self)
        win.present()

def main():
    app = MAGIApplication()
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
