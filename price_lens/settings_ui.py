"""Compact, immediately applied preferences using Lupin's normal page controls."""
import shutil
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from . import __version__
from .motion import AnimatedTabs, StableScrollArea
from .shortcut_defaults import label as shortcut_label
from .update_ui import UpdatePanel


MUTED = 'color:#a6b1bf;font-size:11px;'


def text(value, style='', *, wrap=False):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if style:
        widget.setStyleSheet(style)
    return widget


def button(title, callback, *, quiet=False):
    widget = QPushButton(title)
    widget.setAutoDefault(False)
    if quiet:
        widget.setObjectName('ghost')
    widget.clicked.connect(callback)
    return widget


def check(title, value, callback, parent):
    widget = QCheckBox(title, parent)
    widget.setChecked(value)
    widget.toggled.connect(callback)
    return widget


def field(layout, title, control):
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(text(title), 1)
    row.addWidget(control)
    layout.addLayout(row)


class SettingsDialog(QDialog):
    """One reusable, modeless dialog. Opening it never starts a reader or job."""

    def __init__(self, window):
        super().__init__(window)
        self.host = window
        self.setWindowTitle('Lupin settings')
        self.setObjectName('settingsDialog')
        self.setMinimumSize(460, 430)
        available = window.screen().availableGeometry()
        self.resize(min(520, available.width()-32), min(660, available.height()-64))
        self.setStyleSheet('''
            QTabWidget::pane { border:0; padding-top:0; }
            QTabWidget::tab-bar { alignment:center; }
            QTabBar::tab { padding:8px 9px; margin-right:2px; }
            QCheckBox { background:transparent; }
            QDoubleSpinBox, QSpinBox {
                background:#252d3b;color:#e7edf5;border:1px solid #45536a;
                border-radius:6px;padding:5px 7px;
            }
            QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus { border-color:#d9ad66; }
            QDoubleSpinBox:disabled, QSpinBox:disabled { color:#68788e;border-color:#354052; }
            QDoubleSpinBox::up-button, QSpinBox::up-button {
                subcontrol-origin:border;subcontrol-position:top right;
                width:18px;height:15px;border:0;border-top-right-radius:6px;background:#303d51;
            }
            QDoubleSpinBox::down-button, QSpinBox::down-button {
                subcontrol-origin:border;subcontrol-position:bottom right;
                width:18px;height:15px;border:0;border-bottom-right-radius:6px;background:#303d51;
            }
            QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
            QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover { background:#45536a; }
            QDoubleSpinBox::up-arrow, QSpinBox::up-arrow { image:url("ARROW_UP");width:8px;height:5px; }
            QDoubleSpinBox::down-arrow, QSpinBox::down-arrow { image:url("ARROW_DOWN");width:8px;height:5px; }
            QComboBox::drop-down { border:0;width:25px; }
            QComboBox::down-arrow { image:url("ARROW_DOWN");width:10px;height:6px; }
        '''.replace('ARROW_UP', (Path(__file__).parent/'resources/chevron-up.svg').as_posix())
           .replace('ARROW_DOWN', (Path(__file__).parent/'resources/chevron-down.svg').as_posix()))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(text('Settings', 'font-size:23px;font-weight:700;'))
        header.addStretch()
        header.addWidget(text('Lupin '+__version__, MUTED))
        outer.addLayout(header)
        self.tabs = AnimatedTabs(self)
        outer.addWidget(self.tabs, 1)
        self.pages = {}
        for name in ('General', 'Prices', 'Tracking', 'Translation', 'Updates'):
            scroll = StableScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            contents = QWidget()
            layout = QVBoxLayout(contents)
            layout.setContentsMargins(0, 10, 0, 0)
            layout.setSpacing(12)
            scroll.setWidget(contents)
            self.tabs.addTab(scroll, name)
            self.pages[name] = (scroll, layout)
        self.general()
        self.prices()
        self.tracking()
        self.translation()
        self.updates()
        for _, layout in self.pages.values():
            layout.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(button('About Lupin', lambda:self.open_tool(window.about), quiet=True))
        footer.addStretch()
        footer.addWidget(text('Changes apply immediately', MUTED))
        self.done_button = button('Done', self.accept)
        self.done_button.setObjectName('primary')
        footer.addWidget(self.done_button)
        outer.addLayout(footer)
        for manager in (window.hotkeys, window.exp_hotkeys, window.chat_hotkeys, window.write_hotkeys):
            manager.changed.connect(self.sync_shortcuts)

    def card(self, page, title, help_text=''):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(text(title, 'font-size:14px;font-weight:650;color:#e8dfcf;'))
        if help_text:
            layout.addWidget(text(help_text, MUTED, wrap=True))
        self.pages[page][1].addWidget(frame)
        return layout

    def general(self):
        w = self.host
        layout = self.card('General', 'Appearance')
        w.motion_check = check('Reduce motion', w.reduce_motion, w.set_reduce_motion, self)
        w.tray_check = check('Minimize to the system tray', w.minimize_to_tray, w.set_minimize_to_tray, self)
        layout.addWidget(w.motion_check)
        layout.addWidget(w.tray_check)

        layout = self.card('General', 'Shortcuts')
        row = QHBoxLayout()
        self.shortcut_summary = text('', MUTED, wrap=True)
        row.addWidget(self.shortcut_summary, 1)
        w.hotkey_button = button('Edit shortcuts…', self.edit_shortcuts)
        row.addWidget(w.hotkey_button)
        layout.addLayout(row)
        self.sync_shortcuts()

        layout = self.card('General', 'Screen reading')
        w.auto_area_check = check('Find the Classic World area automatically', w.auto_game_area, w.set_auto_area, self)
        w.auto_area_check.setToolTip('A manually selected reading area takes priority until reset.')
        layout.addWidget(w.auto_area_check)
        layout.addWidget(text('Use a smaller reading area or check the connection if capture needs attention.', MUTED, wrap=True))
        row = QHBoxLayout()
        w.crop_button = button('Limit reading area…', lambda:self.open_tool(w.crop))
        w.diagnostics_button = button('Connection details…', lambda:self.open_tool(w.troubleshoot))
        row.addWidget(w.crop_button)
        row.addWidget(w.diagnostics_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button('Open screenshot…', lambda:self.open_tool(w.open_screenshot), quiet=True))
        if shutil.which('spectacle'):
            w.kde_button = button('Use KDE capture', lambda:self.open_tool(w.start_kde), quiet=True)
            row.addWidget(w.kde_button)
        row.addStretch()
        layout.addLayout(row)

    def prices(self):
        w = self.host
        layout = self.card('Prices', 'Price overlays')
        w.labels_check = check('Show market prices beside items', w.labels_enabled, w.set_labels, self)
        layout.addWidget(w.labels_check)
        w.hover_check = check('Show inventory and equipment prices', w.hover_enabled, w.set_hover, self)
        w.hover_check.setEnabled(w.labels_enabled)
        layout.addWidget(w.hover_check)
        layout.addWidget(text('Hover cards work outside a shop’s item list, including while a shop is open. Shop items keep their listing labels.', MUTED, wrap=True))

        layout = self.card('Prices', 'Market refresh', 'Prices refresh on launch and at this interval. All price views share the same saved market data.')
        w.ttl_combo = QComboBox()
        for minutes in (5, 15, 30, 60):
            w.ttl_combo.addItem(f'{minutes} minutes'+(' · recommended' if minutes == 15 else ''), minutes*60)
        w.ttl_combo.setCurrentIndex(w.ttl_combo.findData(w.ttl))
        w.ttl_combo.currentIndexChanged.connect(lambda index:w.set_ttl(w.ttl_combo.itemData(index)))
        field(layout, 'Refresh every', w.ttl_combo)
        layout.addWidget(text('If a refresh fails, saved prices remain available. Deal colors return when fresh data arrives.', MUTED, wrap=True))

    def tracking(self):
        w = self.host
        layout = self.card('Tracking', 'Game overlays', 'Separate cards sit at the bottom left of Classic World. They appear only while tracking is running or paused.')
        w.exp_overlay_check = check('Show EXP overlay', w.exp_overlay, w.set_exp_overlay, self)
        w.meso_overlay_check = check('Show meso overlay', w.meso_overlay, w.set_meso_overlay, self)
        layout.addWidget(w.exp_overlay_check)
        layout.addWidget(w.meso_overlay_check)
        layout = self.card('Tracking', 'EXP figures')
        w.exp_display_combo = QComboBox()
        for value, title in (('percent', 'Percentage'), ('raw', 'Raw EXP'), ('both', 'Percentage + raw EXP')):
            w.exp_display_combo.addItem(title, value)
        w.exp_display_combo.setCurrentIndex(w.exp_display_combo.findData(w.exp_display))
        w.exp_display_combo.currentIndexChanged.connect(lambda *_:w.set_exp_display(w.exp_display_combo.currentData()))
        field(layout, 'Display as', w.exp_display_combo)
        layout.addWidget(text('Start or pause a session on the EXP/Meso Tracking page.', MUTED, wrap=True))

    def translation(self):
        w = self.host
        layout = self.card('Translation', 'Read Korean')
        self.chat_check = check('Enable Korean translation', w.chat_enabled, w.set_chat_enabled, self)
        layout.addWidget(self.chat_check)
        layout.addWidget(text('Each scan keeps checking the game window for new text. Translations appear as soon as they are ready.', MUTED, wrap=True))
        self.scan = QDoubleSpinBox()
        self.linger = QDoubleSpinBox()
        for spin, maximum, minimum, value in ((self.scan, 10, 1, w.chat.scan_seconds), (self.linger, 5, 0, w.chat.linger_seconds)):
            spin.setRange(minimum, maximum)
            spin.setSingleStep(.5)
            spin.setDecimals(1)
            spin.setSuffix(' s')
            spin.setFixedWidth(100)
            spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            spin.setValue(value)
            spin.valueChanged.connect(lambda *_:w.set_chat_timing(self.scan.value(), self.linger.value()))
        field(layout, 'Keep checking for', self.scan)
        field(layout, 'Keep after disappearance', self.linger)
        layout = self.card('Translation', 'Write Korean', 'Translate a draft and copy it to the clipboard. The writer works independently of incoming translation.')
        layout.addWidget(button('Open Korean writer', lambda:self.open_translation(1)))
        layout.addWidget(button('Open translation results', lambda:self.open_translation(0), quiet=True))

    def updates(self):
        w = self.host
        layout = self.card('Updates', 'Application')
        w.update_panel = UpdatePanel(w.updates, self, settings=True)
        w.update_panel.title.hide()
        layout.addWidget(w.update_panel)
        layout = self.card('Updates', 'Local database', 'Checks for changes and downloads only updated files. Saved entries stay available offline.')
        w.database_update_status = text('', MUTED, wrap=True)
        layout.addWidget(w.database_update_status)
        w.database_update_button = button('Check for database updates', lambda:w.reference.start())
        layout.addWidget(w.database_update_button)

    def sync_shortcuts(self):
        w = self.host
        values = (('Prices', w.hotkey_description or w.hotkey_sequence),
                  ('Tracking', w.exp_hotkey_description or w.exp_sequence),
                  ('Read', w.chat_hotkey_description or w.chat_sequence),
                  ('Write', w.write_hotkey_description or w.write_sequence))
        value = '\n'.join(f'{title}  {shortcut_label(chord)}' for title, chord in values)
        if not w.hotkey_enabled:
            value = 'Global shortcuts are off\n'+value
        if value != self.shortcut_summary.text():
            self.shortcut_summary.setText(value)

    def sync_translation(self):
        for widget, value, setter in ((self.chat_check, self.host.chat_enabled, 'setChecked'),
                                      (self.scan, self.host.chat.scan_seconds, 'setValue'),
                                      (self.linger, self.host.chat.linger_seconds, 'setValue')):
            with QSignalBlocker(widget):
                getattr(widget, setter)(value)

    def edit_shortcuts(self):
        self.host.configure_shortcuts()
        self.sync_shortcuts()

    def open_translation(self, mode):
        self.hide()
        self.host.tabs.setCurrentIndex(self.host.translation_tab_index)
        self.host.translation_panel.modes.setCurrentIndex(mode)

    def open_tool(self, callback):
        self.hide()
        callback()

    def showEvent(self, event):
        self.sync_shortcuts()
        self.sync_translation()
        super().showEvent(event)
