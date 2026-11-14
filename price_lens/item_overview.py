"""Reusable item facts; no capture, pricing, database or network ownership."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QGridLayout,QHBoxLayout,QVBoxLayout,QWidget
from .motion import MotionLabel

ITEM_STATS={'reqLevel':'Level required','reqSTR':'STR required','reqDEX':'DEX required','reqINT':'INT required','reqLUK':'LUK required','reqPOP':'Fame required',
    'incPAD':'Weapon attack','incMAD':'Magic attack','incPDD':'Weapon defense','incMDD':'Magic defense','incACC':'Accuracy',
    'incEVA':'Avoidability','incSTR':'STR','incDEX':'DEX','incINT':'INT','incLUK':'LUK','incMHP':'HP','incMMP':'MP',
    'incSpeed':'Speed','incJump':'Jump','incCRT':'Critical rate','incCRD':'Critical damage','tuc':'Upgrade slots','slotMax':'Stack limit',
    'incWAT':'Weapon attack','incMAT':'Magic attack','incWDEF':'Weapon defense','incMDEF':'Magic defense'}


def formatted(value):
    if type(value) in (int,float):return f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value,float) else f'{value:,}'
    return str(value)


def item_overview(name,row):
    model=dict(description='',stats=[],requirements='',effects=[],scroll=[],npc='')
    if not row.get('scroll') and row.get('description'):
        from .domain import key
        if key(row['description'])!=key(name):model['description']=row['description']
    if row.get('cash'):return model
    values=[(caption,str(row['stats'][key])+'%' if key in ('incCRT','incCRD') else formatted(row['stats'][key]))
            for key,caption in ITEM_STATS.items() if key in (row.get('stats') or {}) and not key.startswith('req')]
    if row.get('gender'):values.insert(0,('Gender',row['gender'].capitalize()))
    speed=(row.get('stats') or {}).get('attackSpeed')
    if speed is not None:values.append(('Attack speed',{2:'Faster',3:'Faster',4:'Fast',5:'Fast',6:'Normal',7:'Slow',8:'Slow',9:'Slower'}.get(speed,str(speed))))
    model['stats']=values
    required=[(caption.removesuffix(' required'),row['stats'][key]) for key,caption in ITEM_STATS.items() if key.startswith('req') and key in (row.get('stats') or {})]
    if row.get('req_classes'):required.append(('Class',', '.join(row['req_classes'])))
    model['requirements']=' · '.join(f'{caption} {formatted(value)}' for caption,value in required)
    effects=row.get('spec') or {};values=[]
    for key,caption,unit in (('hp','HP restored',''),('mp','MP restored',''),('hpR','HP restored','%'),('mpR','MP restored','%'),
        ('pad','Weapon attack',''),('mad','Magic attack',''),('pdd','Weapon defense',''),('acc','Accuracy',''),('eva','Avoidability',''),('speed','Speed',''),('jump','Jump','')):
        if effects.get(key):values.append((caption,formatted(effects[key])+unit))
    if values and effects.get('time'):values.append(('Duration',formatted(effects['time']/60000)+' min'))
    model['effects']=values
    scroll=row.get('scroll') or {};values=[]
    if scroll:
        if 'success_rate' in scroll:values.append(('Success rate',formatted(scroll['success_rate'])+'%'))
        values.extend((ITEM_STATS[key],formatted(value)) for key,value in (scroll.get('stats') or {}).items() if key in ITEM_STATS)
        if scroll.get('slot'):values.append(('Applies to',scroll['slot']))
    model['scroll']=values
    if row.get('price') is not None and not (row.get('stats') or {}).get('notSale'):model['npc']=f"NPC sell-back · {formatted(row['price'])} mesos"
    return model


def label(value='',size=11,color='#b1bfd1',bold=False):
    widget=MotionLabel(value);widget.setWordWrap(True)
    widget.setStyleSheet(f'font-size:{size}px;color:{color};font-weight:{600 if bold else 400};background:transparent')
    return widget


class FactSection(QWidget):
    def __init__(self,title,*,paragraph=False):
        super().__init__();self.cells=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(9)
        heading=QHBoxLayout();heading.setSpacing(9);heading.addWidget(label(title,11,'#e2c69b',True))
        line=QFrame();line.setFixedHeight(1);line.setStyleSheet('background:#334154;border:0');heading.addWidget(line,1);layout.addLayout(heading)
        self.paragraph=label('',11,'#c0cbd9') if paragraph else None
        if self.paragraph:layout.addWidget(self.paragraph)
        else:
            self.grid=QGridLayout();self.grid.setContentsMargins(0,0,0,0);self.grid.setHorizontalSpacing(18);self.grid.setVerticalSpacing(6)
            self.grid.setColumnStretch(0,1);self.grid.setColumnStretch(1,1);layout.addLayout(self.grid)

    def set_values(self,values):
        if self.paragraph:self.paragraph.setText(values)
        else:
            while len(self.cells)<len(values):
                cell=QWidget();row=QHBoxLayout(cell);row.setContentsMargins(0,0,0,0);row.setSpacing(6)
                caption=label();number=label('',12,'#e6eaf1',True)
                number.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                row.addWidget(caption,1);row.addWidget(number)
                index=len(self.cells);self.grid.addWidget(cell,index//2,index%2);self.cells.append((cell,caption,number))
            for index,(cell,caption,number) in enumerate(self.cells):
                if index<len(values):caption.setText(str(values[index][0]));number.setText(str(values[index][1]))
                else:caption.clear();number.clear()
                cell.setVisible(index<len(values))
        self.setVisible(bool(values))


class ItemOverview(QWidget):
    ORDER=('stats','requirements','effects','scroll')
    TITLES=('Base stats','Requirements','Effect','Scroll effect')

    def __init__(self,model,parent=None):
        super().__init__(parent);self.sections={}
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(9)
        self.description=label('',11,'#bac5d5');layout.addWidget(self.description)
        self.npc=label('',11,'#9facc0');layout.addWidget(self.npc)
        self.set_model(model)

    def set_model(self,model):
        self.description.setText(model['description']);self.description.setVisible(bool(model['description']))
        for order,(key,title) in enumerate(zip(self.ORDER,self.TITLES)):
            values=model[key]
            if values and key not in self.sections:
                section=FactSection(title,paragraph=key=='requirements');self.sections[key]=section
                index=1+sum(other in self.sections for other in self.ORDER[:order])
                self.layout().insertWidget(index,section)
            if key in self.sections:self.sections[key].set_values(values)
        self.npc.setText(model['npc']);self.npc.setVisible(bool(model['npc']))
        populated=any(model.values())
        if self.parentWidget() is not None or not populated:self.setVisible(populated)
