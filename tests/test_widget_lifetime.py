"""Native layout wrappers survive the complete deferred widget teardown."""
import gc
import unittest
import weakref

from PySide6.QtCore import QCoreApplication,QEvent,QVariantAnimation
from PySide6.QtWidgets import QApplication,QFrame,QVBoxLayout,QWidget
import shiboken6

from price_lens.widget_lifetime import retire_widget


class WidgetLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_retirement_keeps_layouts_until_after_native_children_are_destroyed(self):
        owner=QWidget();card=QFrame(owner);root=QVBoxLayout(card)
        columns=QWidget();root.addWidget(columns);nested=QVBoxLayout(columns)
        animation=QVariantAnimation(columns);animation_ref=weakref.ref(animation)
        retire_widget(owner,card);retire_widget(owner,card)
        entry=owner._retiring_widgets[id(card)]
        self.assertEqual(len(owner._retiring_widgets),1)
        self.assertEqual(set(entry[1]),{root,columns,nested,animation})
        del animation;gc.collect()
        self.assertIsNotNone(animation_ref())
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertFalse(shiboken6.isValid(card))
        self.assertFalse(shiboken6.isValid(nested))
        # destroyed is emitted before child teardown. The Python keep-alives
        # are released by the queued callback after native deletion finishes.
        self.assertEqual(len(owner._retiring_widgets),1)
        self.app.processEvents()
        self.assertEqual(owner._retiring_widgets,{})
        del entry;gc.collect()
        self.assertIsNone(animation_ref(),'The temporary animation wrapper must be released too')
        owner.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_many_retired_cards_are_released_without_an_unbounded_cache(self):
        owner=QWidget()
        for cycle in range(30):
            for _ in range(8):
                card=QFrame(owner);root=QVBoxLayout(card)
                child=QWidget();root.addWidget(child);QVBoxLayout(child)
                retire_widget(owner,card)
            gc.collect()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.app.processEvents()
            self.assertEqual(owner._retiring_widgets,{},cycle)
        owner.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
