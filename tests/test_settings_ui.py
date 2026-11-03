"""Preferences operate on the same live state as their main-page controls."""
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

import test_ui_context as fixtures


class SettingsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ContextUiTests.setUpClass()
        cls.app = fixtures.ContextUiTests.app

    def setUp(self):
        self.fixture = fixtures.ContextUiTests()
        self.fixture.setUp()
        self.w = self.fixture.window
        self.dialog = self.w.settings_dialog

    def tearDown(self):
        self.fixture.tearDown()
        self.fixture.doCleanups()

    def test_opening_preferences_is_modeless_and_starts_no_reading_or_jobs(self):
        w = self.w
        initial = w.service.catalog_starts
        with patch.object(w.chat, 'enable') as enable, patch.object(w.reference, 'start') as database, \
                patch.object(w.updates, 'check') as check:
            w.open_settings()
            self.app.processEvents()
            self.assertTrue(self.dialog.isVisible())
            self.assertFalse(self.dialog.isModal())
            self.assertEqual(self.dialog.windowModality(), Qt.WindowModality.NonModal)
            self.assertEqual(w.reader.starts, 0)
            self.assertFalse(w.exp_panel.requested)
            self.assertEqual(w.service.catalog_starts, initial)
            enable.assert_not_called()
            database.assert_not_called()
            check.assert_not_called()
            self.dialog.done_button.click()
            self.assertFalse(self.dialog.isVisible())
            self.assertFalse(w.closing)

    def test_translation_controls_sync_both_ways_without_restarting_the_worker(self):
        w, d = self.w, self.dialog
        with patch.object(w.chat, 'enable') as enable, patch.object(w.chat, 'start_scan') as scan:
            d.chat_check.setChecked(True)
            self.assertTrue(w.chat_check.isChecked())
            self.assertTrue(w.translation_panel.translate_button.isEnabled())
            enable.assert_called_once_with(True)
            w.chat_check.setChecked(False)
            self.assertFalse(d.chat_check.isChecked())
            self.assertFalse(w.translation_panel.translate_button.isEnabled())
            self.assertEqual(enable.call_count, 2)
            scan.assert_not_called()
        with patch.object(w.chat, 'configure', wraps=w.chat.configure) as configure:
            d.scan.setValue(7.5)
            self.assertEqual(w.translation_panel.scan.value(), 7.5)
            self.assertEqual(w.settings.values['chat-scan-seconds'], 7.5)
            self.assertEqual(configure.call_count, 1)
            w.translation_panel.linger.setValue(2.5)
            self.assertEqual(d.linger.value(), 2.5)
            self.assertEqual(w.settings.values['chat-linger-seconds'], 2.5)
            self.assertEqual(configure.call_count, 2)

    def test_overlay_preferences_stay_independent_and_keep_hover_choice(self):
        w = self.w
        w.labels_check.setChecked(False)
        self.assertFalse(w.hover_check.isEnabled())
        self.assertTrue(w.hover_check.isChecked())
        w.labels_check.setChecked(True)
        self.assertTrue(w.hover_check.isEnabled())
        w.exp_panel.overlay_check.setChecked(False)
        self.assertFalse(w.exp_overlay_check.isChecked())
        self.assertTrue(w.meso_overlay_check.isChecked())
        w.meso_overlay_check.setChecked(False)
        self.assertFalse(w.exp_panel.meso_overlay_check.isChecked())
        self.assertFalse(w.exp_panel.requested)

    def test_market_interval_and_update_interval_apply_to_separate_timers(self):
        w = self.w
        with patch.object(w.updates, 'configure') as configure:
            w.update_panel.interval.setValue(120)
            w.ttl_combo.setCurrentIndex(w.ttl_combo.findData(1800))
            self.assertEqual(w.service.interval, 1800)
            self.assertEqual(w.settings.values['update-interval-minutes'], 120)
            w.update_panel.periodic.setChecked(False)
            self.assertFalse(w.update_panel.interval.isEnabled())
            self.assertEqual(w.settings.values['update-interval-minutes'], 0)
            self.assertEqual(w.service.interval, 1800)
            self.assertEqual(configure.call_count, 2)

    def test_compact_pages_fit_without_scroll_and_short_windows_keep_controls_accessible(self):
        w, d = self.w, self.dialog
        w.set_reduce_motion(True)
        w.show()
        d.show()
        for width in (460, 520):
            d.resize(width, 660)
            for index, (name, (scroll, _)) in enumerate(d.pages.items()):
                d.tabs.setCurrentIndex(index)
                self.app.processEvents()
                self.assertEqual(scroll.verticalScrollBar().maximum(), 0, (width, name))
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0, (width, name))
                bar = d.tabs.tabBar()
                self.assertLessEqual(abs(bar.geometry().center().x()-d.tabs.rect().center().x()), 2)
        d.resize(460, 430)
        d.tabs.setCurrentIndex(0)
        self.app.processEvents()
        scroll = d.pages['General'][0]
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        scroll.ensureWidgetVisible(w.crop_button)
        self.assertTrue(scroll.viewport().rect().contains(w.crop_button.mapTo(scroll.viewport(), w.crop_button.rect().center())))
        self.assertTrue(d.done_button.isVisible())

    def test_advanced_reading_actions_require_capture_and_leave_settings_before_opening(self):
        w, d = self.w, self.dialog
        w.mode = 'idle'
        image = w.reader.image
        w.reader.image = QImage()
        w.open_settings()
        self.assertFalse(w.crop_button.isEnabled())
        w.mode = 'screenshot'
        w.reader.image = image
        w.update_capture_controls()
        self.assertTrue(w.crop_button.isEnabled())
        with patch.object(w, 'crop') as crop:
            w.crop_button.click()
            crop.assert_called_once_with()
            self.assertFalse(d.isVisible())

    def test_translation_links_open_the_right_main_page_without_enabling_reading(self):
        d, w = self.dialog, self.w
        d.show()
        writer = next(b for b in d.findChildren(QPushButton) if b.text() == 'Open Korean writer')
        writer.click()
        self.assertFalse(d.isVisible())
        self.assertEqual(w.tabs.currentIndex(), w.translation_tab_index)
        self.assertEqual(w.translation_panel.modes.currentIndex(), 1)
        self.assertFalse(w.chat_enabled)
        self.assertEqual(w.reader.starts, 0)

    def test_shortcut_summary_follows_an_edited_chord(self):
        self.w.hotkeys.changed.emit('Meta+F6')
        self.assertIn('F6', self.dialog.shortcut_summary.text())
        self.assertNotIn('F9', self.dialog.shortcut_summary.text())

    def test_update_offer_and_cancel_actions_fit_at_minimum_width(self):
        from types import SimpleNamespace
        w, d = self.w, self.dialog
        w.set_reduce_motion(True)
        w.updates.target = SimpleNamespace(installable=True, name='linux-arch-x64')
        w.updates.offer = {'manifest': {'version': '1.0.4'}, 'package': {'bytes': 12345678}, 'release': {}}
        w.updates.state = 'checking'
        w.update_panel.refresh()
        d.resize(460, 660)
        d.show()
        d.tabs.setCurrentIndex(4)
        self.app.processEvents()
        self.assertTrue(w.update_panel.install.isVisible())
        self.assertTrue(w.update_panel.cancel.isVisible())
        self.assertFalse(w.update_panel.install.isEnabled())
        self.assertFalse(w.update_panel.check.isEnabled())
        self.assertGreater(w.update_panel.install.width(), 300)
        scroll = d.pages['Updates'][0]
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)

    def test_sliding_preferences_respect_reduce_motion(self):
        w, d = self.w, self.dialog
        w.show()
        d.show()
        self.app.processEvents()
        w.set_reduce_motion(False)
        d.tabs.setCurrentIndex(1)
        self.assertTrue(d.tabs.sliding)
        QTest.qWait(300)
        self.assertFalse(d.tabs.sliding)
        w.motion_check.setChecked(True)
        d.tabs.setCurrentIndex(2)
        self.assertFalse(d.tabs.sliding)
