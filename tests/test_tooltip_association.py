"""Small pixel proofs for a description's inventory source, without capture."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QImage

from price_lens.tooltip_association import TooltipAssociation,association_state
from price_lens.tooltip_geometry import TooltipReference


class TooltipAssociationTests(unittest.TestCase):
    def setUp(self):
        self.image=QImage(800,600,QImage.Format.Format_RGBA8888)
        self.image.fill(QColor('#24384b'))
        self.found={'area':dict(x=58,y=111,width=180,height=12)}
        self.value={'state':'inventory-primary','token':'source:tab:slot',
                    'source':dict(x=300,y=150,width=230,height=300),
                    'slot':dict(x=324,y=174,width=36,height=36),
                    'panel':dict(x=50,y=100,width=240,height=330),
                    'guards':[dict(x=300,y=150,width=230,height=20),
                              dict(x=50,y=100,width=240,height=2)]}

    def proof(self):
        return TooltipAssociation.read(self.value,self.found,self.image)

    def test_only_explicit_primary_metadata_extends_the_normal_path(self):
        self.assertEqual(association_state(None),'normal')
        self.assertEqual(association_state({'state':'normal'}),'normal')
        for value in ({},{'state':'rejected'},{'state':'future'},[],False):
            self.assertEqual(association_state(value),'rejected')
        self.assertIsNotNone(self.proof())
        self.assertTrue(self.proof().matches(self.image,(340,190)))

    def test_small_pointer_move_to_another_cell_invalidates_the_binding(self):
        proof=self.proof()
        self.assertTrue(proof.matches(self.image,(350,200)))
        self.assertFalse(proof.matches(self.image,(376,190)))
        for point in (None,(340,),('340',190),(True,190)):
            self.assertFalse(proof.contains_pointer(point))

    def test_forwarded_immutable_proof_is_reused_but_latest_pixels_are_revalidated(self):
        proof=self.proof()
        result={'tooltipAssociation':self.value,'tooltip':{'found':self.found},'_tooltip_context':proof}
        with patch.object(TooltipAssociation,'read',side_effect=AssertionError('Do not build the same proof twice')):
            received=TooltipAssociation.from_result(result,self.image,pointer=(340,190))
        self.assertIs(received,proof)
        changed=self.image.copy();changed.setPixelColor(310,155,QColor('red'))
        self.assertFalse(received.matches(changed,(340,190)))
        self.assertIsNone(TooltipAssociation.from_result({**result,'_tooltip_context':None},self.image))

    def test_name_header_and_panel_guards_expire_independently(self):
        proof=self.proof()
        for point in ((60,112),(310,155),(51,100),(326,176)):
            with self.subTest(point=point):
                changed=self.image.copy();changed.setPixelColor(*point,QColor('red'))
                self.assertFalse(proof.matches(changed,(340,190)))
        changed=self.image.copy();changed.setPixelColor(740,500,QColor('red'))
        self.assertTrue(proof.matches(changed,(340,190)))

    def test_incomplete_out_of_bounds_or_unbounded_proofs_fail_closed(self):
        mutations=[('token',''),('token','x'*513),('guards',[]),('guards',[{}]*13),
                   ('guards',[dict(x=0,y=0,width=800,height=600)]),
                   ('source',dict(x=300,y=150,width=20,height=20)),
                   ('slot',dict(x=324,y=174,width=True,height=36)),
                   ('panel',dict(x=50,y=100,width=40,height=40)),
                   ('guards',[dict(x=-1,y=0,width=10,height=10)]),
                   ('guards',[dict(x=0,y=0,width=0,height=10)])]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                metadata=deepcopy(self.value);metadata[key]=value
                self.assertIsNone(TooltipAssociation.read(metadata,self.found,self.image))
        self.assertIsNone(TooltipAssociation.read(self.value,None,self.image))
        self.assertIsNone(TooltipAssociation.read(self.value,self.found,QImage()))

    def test_scaled_translated_pixels_and_tokens_remain_in_one_coordinate_space(self):
        image=QImage(1700,1300,QImage.Format.Format_RGBA8888);image.fill(QColor('navy'))
        def transform(rect):
            return dict(x=rect['x']*2+30,y=rect['y']*2+40,
                        width=rect['width']*2,height=rect['height']*2)
        value={**self.value,'token':'origin30,40:scale2',
               **{key:transform(self.value[key]) for key in ('source','slot','panel')},
               'guards':[transform(rect) for rect in self.value['guards']]}
        proof=TooltipAssociation.read(value,{'area':transform(self.found['area'])},image)
        self.assertIsNotNone(proof)
        self.assertEqual(proof.token,'origin30,40:scale2')
        self.assertEqual(proof.slot,QRect(678,388,72,72))
        self.assertTrue(proof.matches(image,(710,420)))
        self.assertFalse(proof.matches(image,(340,190)))

    def v2(self):
        found={'name':'Primary Hat','area':dict(x=58,y=231,width=180,height=12)}
        value={**deepcopy(self.value),'version':2,'layout':'primary-left','sourceKind':'inventory',
               'panel':dict(x=50,y=220,width=240,height=330),
               'comparison':dict(x=292,y=220,width=240,height=300),
               'pointer':dict(x=340,y=190),'cursor':dict(x=334,y=184,width=32,height=36),
               'guards':[dict(x=300,y=150,width=230,height=20),dict(x=50,y=220,width=240,height=2)]}
        return value,found

    def test_v2_keeps_primary_and_comparison_rectangles_separate(self):
        value,found=self.v2();proof=TooltipAssociation.read(value,found,self.image)
        self.assertEqual(proof.panel,QRect(50,220,240,330))
        self.assertEqual(proof.comparison,QRect(292,220,240,300))
        self.assertEqual(proof.source_kind,'inventory');self.assertEqual(proof.layout,'primary-left')
        self.assertTrue(proof.matches(self.image,(340,190)))
        found={'area':dict(x=302,y=231,width=180,height=12)}
        self.assertIsNone(TooltipAssociation.read(value,found,self.image))

    def test_cursor_motion_in_one_slot_preserves_visible_source_evidence(self):
        value,found=self.v2();image=self.image.copy()
        # A small captured hand moves on top of a stable item. The masks cover
        # the old/new cursor only; the rest of the source cell stays visible.
        for y in range(190,202):
            for x in range(340,348):image.setPixelColor(x,y,QColor('white'))
        proof=TooltipAssociation.read(value,found,image)
        moved=self.image.copy()
        for y in range(192,204):
            for x in range(343,351):moved.setPixelColor(x,y,QColor('white'))
        self.assertTrue(proof.matches(moved,(343,192)))
        changed=moved.copy();changed.setPixelColor(326,176,QColor('red'))
        self.assertFalse(proof.matches(changed,(343,192)))
        changed=moved.copy();changed.setPixelColor(60,232,QColor('red'))
        self.assertFalse(proof.matches(changed,(343,192)))
        self.assertFalse(proof.matches(moved,(376,192)))

    def test_narrow_exposed_cell_strip_is_exact_and_not_a_cursor_animation_switch(self):
        value,found=self.v2();value['slot']=dict(x=324,y=174,width=32,height=32)
        value['pointer']=dict(x=327,y=180)
        value['cursor']=dict(x=321,y=173,width=32,height=37)
        image=self.image.copy();proof=TooltipAssociation.read(value,found,image,pointer=(327,180))
        latest=image.copy();latest.setPixelColor(330,185,QColor('white'))
        self.assertTrue(proof.matches(latest,(327,180)))
        # Three full columns remain exposed. Every one of those pixels, the
        # source header and the real name remain independently mandatory.
        for point in ((354,185),(310,155),(60,232)):
            changed=latest.copy();changed.setPixelColor(*point,QColor('red'))
            self.assertFalse(proof.matches(changed,(327,180)),point)

    def test_wholly_hidden_cell_is_consistently_unknown_even_on_an_identical_frame(self):
        value,found=self.v2();value['slot']=dict(x=324,y=174,width=32,height=32)
        value['pointer']=dict(x=330,y=181)
        value['cursor']=dict(x=324,y=174,width=32,height=37)
        proof=TooltipAssociation.read(value,found,self.image,pointer=(330,181))
        self.assertFalse(proof.matches(self.image,(330,181)))
        changed=self.image.copy();changed.setPixelColor(335,185,QColor('white'))
        self.assertFalse(proof.matches(changed,(330,181)))

    def test_stationary_animated_hand_top_outline_is_not_an_item_change(self):
        from price_lens.shop_source import cursor_rectangle
        value,found=self.v2();point=(340,190)
        cursor=cursor_rectangle(point)
        value['cursor']=dict(zip(('x','y','width','height'),cursor.getRect()))
        image=self.image.copy();proof=TooltipAssociation.read(value,found,image)
        changed=image.copy();changed.setPixelColor(341,183,QColor('black'))
        self.assertTrue(proof.matches(changed,point))
        # The first pixel outside the measured outline remains exact; a real
        # changed item or title cannot be held by an enlarged tolerance.
        changed.setPixelColor(341,182,QColor('red'))
        self.assertFalse(proof.matches(changed,point))
        changed=image.copy();changed.setPixelColor(60,232,QColor('white'))
        self.assertFalse(proof.matches(changed,point))

    def test_changed_source_invalidates_a_bridge_while_comparison_is_unchanged(self):
        value,found=self.v2();proof=TooltipAssociation.read(value,found,self.image)
        reference=TooltipReference()
        self.assertIs(reference.observe(found,self.image,(340,190),now=1,context=proof),found)
        self.assertEqual(reference.panel,proof.panel)
        changed=self.image.copy();changed.setPixelColor(326,176,QColor('red'))
        self.assertIsNone(reference.observe(None,changed,(340,190),now=1.2,context=proof))
        reference.observe(found,self.image,(340,190),now=2,context=proof)
        self.assertIsNone(reference.observe(None,self.image,(340,190),now=2.2))

    def test_blended_title_fringe_still_requires_the_same_inventory_cell_and_header(self):
        from PySide6.QtGui import QPainter
        value,found=self.v2();image=self.image.copy()
        p=QPainter(image);p.fillRect(62,234,30,4,QColor('white'))
        p.fillRect(62,238,30,1,QColor('#adb2cb'));p.end()
        proof=TooltipAssociation.read(value,found,image)
        latest=image.copy();p=QPainter(latest);p.fillRect(62,238,30,1,QColor('#bbc0d4'));p.end()
        self.assertFalse(proof.title.matches(latest,panel=proof.panel))
        self.assertTrue(proof.matches(latest,(340,190)))
        for point in ((326,176),(310,155),(63,235)):
            changed=latest.copy();changed.setPixelColor(*point,QColor('red'))
            self.assertFalse(proof.matches(changed,(340,190)),point)

    def test_v2_rejects_missing_or_unbounded_cursor_and_pair_proofs(self):
        value,found=self.v2()
        for key,bad in (('comparison',None),('comparison',value['panel']),('layout','nearest'),
                        ('sourceKind','unknown'),('version',True),('pointer',None),
                        ('pointer',dict(x=700,y=500)),('cursor',None),
                        ('cursor',dict(x=300,y=150,width=230,height=300))):
            with self.subTest(key=key,bad=bad):
                metadata={**value,key:bad}
                self.assertIsNone(TooltipAssociation.read(metadata,found,self.image))

    def v3(self):
        from PySide6.QtGui import QPainter
        image=QImage(900,700,QImage.Format.Format_RGBA8888);image.fill(QColor('#4a5430'))
        p=QPainter(image);p.fillRect(600,80,207,285,QColor('#e9eaeb'))
        for left,height in ((320,300),(559,270)):
            p.fillRect(left,170,236,height,QColor(65,55,90))
            for x in (left,left+233):
                p.fillRect(x,170,3,height,QColor(40,40,65));p.fillRect(x+1,170,1,height,QColor(170,170,200))
            p.fillRect(left,170,236,3,QColor(40,40,65));p.fillRect(left,171,236,1,QColor(170,170,200))
        for x in (337,343,350,360,370):p.fillRect(x,183,2,8,QColor('white'))
        p.end()
        value=dict(state='inventory-primary',version=3,token='current:slot',sourceKind='inventory',layout='primary-left',
            source=dict(x=600,y=80,width=207,height=285),slot=dict(x=607,y=127,width=32,height=32),
            panel=dict(x=320,y=170,width=236,height=300),comparison=dict(x=559,y=170,width=236,height=270),
            pointer=dict(x=627,y=140),cursor=dict(x=621,y=134,width=32,height=36),frameCaps=[True,True],
            guards=[dict(x=600,y=80,width=207,height=45)])
        found=dict(name='Example Hat',area=dict(x=329,y=179,width=180,height=14))
        return image,value,found

    def test_v3_translucent_frame_colours_can_change_while_title_and_slot_remain_exact(self):
        from PySide6.QtGui import QPainter
        image,value,found=self.v3();proof=TooltipAssociation.read(value,found,image,pointer=(627,140))
        self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,(627,140)))
        changed=QImage(image);p=QPainter(changed)
        for left,height in ((320,300),(559,270)):
            p.fillRect(left+3,173,230,height-3,QColor(80,70,105))
            for x in (left,left+233):
                p.fillRect(x,170,3,height,QColor(50,45,70));p.fillRect(x+1,170,1,height,QColor(155,160,190))
            p.fillRect(left,170,236,3,QColor(50,45,70));p.fillRect(left,171,236,1,QColor(155,160,190))
        for x in (337,343,350,360,370):p.fillRect(x,183,2,8,QColor('white'))
        p.end();self.assertTrue(proof.matches(changed,(627,140)))
        for point in ((337,184),(603,84),(610,129)):
            bad=QImage(changed);bad.setPixelColor(*point,QColor('red'))
            self.assertFalse(proof.matches(bad,(627,140)))
        p=QPainter(changed);p.fillRect(320,170,3,300,QColor('white'));p.end()
        self.assertFalse(proof.matches(changed,(627,140)))

    def test_v3_requires_explicit_caps_source_header_and_consistent_layout(self):
        image,value,found=self.v3()
        for key,bad in (('frameCaps',[]),('frameCaps',[False,False]),('frameCaps',[1,True]),
                        ('layout','nearest'),('guards',[dict(x=600,y=80,width=2,height=2)]),
                        ('comparison',None),('version',4)):
            with self.subTest(key=key,bad=bad):
                self.assertIsNone(TooltipAssociation.read({**value,key:bad},found,image,pointer=(627,140)))

    def test_owned_labels_are_unknown_rim_pixels_and_never_hide_changed_item_evidence(self):
        from PySide6.QtGui import QPainter
        image,value,found=self.v3();hidden=[QRect(310,y,30,35) for y in (210,255,300,345,390)]
        painter=QPainter(image)
        for rect in hidden:painter.fillRect(rect,QColor('#171c26'))
        painter.end()
        self.assertIsNone(TooltipAssociation.read(value,found,image,pointer=(627,140)))
        proof=TooltipAssociation.read(value,found,image,pointer=(627,140),exclude=hidden)
        self.assertIsNotNone(proof);self.assertTrue(proof.matches(image,(627,140),exclude=hidden))
        self.assertFalse(proof.matches(image,(627,140)))
        for point in ((337,184),(603,84),(610,129)):
            bad=image.copy();bad.setPixelColor(*point,QColor('red'))
            self.assertFalse(proof.matches(bad,(627,140),exclude=hidden))
        # Neither a wholly hidden border nor a removed exposed corner supplies
        # independent frame evidence, even with the source/name unchanged.
        self.assertIsNone(TooltipAssociation.read(value,found,image,pointer=(627,140),
            exclude=[QRect(310,160,30,320)]))
        missing=image.copy();painter=QPainter(missing);painter.fillRect(320,170,236,3,QColor('#464169'));painter.end()
        self.assertFalse(proof.matches(missing,(627,140),exclude=hidden))

    def test_changed_frame_extent_cannot_keep_an_out_of_bounds_panel(self):
        value,found=self.v2();proof=TooltipAssociation.read(value,found,self.image)
        # Source/header/name guards all fit, but the native primary's bottom no
        # longer does. The original bounds cannot survive a smaller game frame.
        self.assertFalse(proof.matches(self.image.copy(0,0,800,500),(340,190)))

    def test_only_rounded_header_corners_may_change_while_interior_and_slot_stay_exact(self):
        proof=self.proof()
        changed=self.image.copy();changed.setPixelColor(529,150,QColor('#354b73'))
        changed.setPixelColor(529,151,QColor('#354b73'))
        self.assertTrue(proof.matches(changed,(340,190)))
        for point in ((310,155),(326,176),(529,155)):
            with self.subTest(point=point):
                invalid=changed.copy();invalid.setPixelColor(*point,QColor('red'))
                self.assertFalse(proof.matches(invalid,(340,190)))

    def test_primary_title_keeps_its_ink_and_source_authority_when_background_changes(self):
        value,found=self.v2();image=self.image.copy()
        for x in (60,74,88,104,121):
            for y in range(233,239):image.setPixelColor(x,y,QColor('white'))
        proof=TooltipAssociation.read(value,found,image)
        self.assertIsNotNone(proof);self.assertTrue(proof.title.semantic)
        changed=image.copy()
        for y in range(231,243):
            for x in range(200,230):changed.setPixelColor(x,y,QColor('#354b73'))
        self.assertTrue(proof.matches(changed,(340,190)))
        changed.setPixelColor(60,233,QColor('#24384b'))
        self.assertFalse(proof.matches(changed,(340,190)))

    def test_cursor_masks_cannot_replace_all_visible_cell_evidence(self):
        value,found=self.v2();value['cursor']=dict(x=322,y=172,width=40,height=40)
        proof=TooltipAssociation.read(value,found,self.image)
        changed=self.image.copy();changed.setPixelColor(340,190,QColor('white'))
        self.assertFalse(proof.matches(changed,(341,190)))


if __name__=='__main__':unittest.main()
