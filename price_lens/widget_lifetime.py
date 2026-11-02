"""Keep Python wrappers alive through a complete deferred Qt widget teardown."""
from PySide6.QtCore import QObject,QTimer


def retire_widget(owner,widget):
    """Release wrappers after native child destruction, not inside its signal."""
    pending=getattr(owner,'_retiring_widgets',None)
    if pending is None:owner._retiring_widgets=pending={}
    key=id(widget)
    if key in pending:return
    # Include child widgets/animations as well as layouts. Not every native
    # child has a Python attribute on its parent to keep its wrapper alive.
    pending[key]=(widget,tuple(widget.findChildren(QObject)))
    widget.destroyed.connect(lambda:QTimer.singleShot(0,lambda:pending.pop(key,None)))
    widget.hide();widget.deleteLater()
