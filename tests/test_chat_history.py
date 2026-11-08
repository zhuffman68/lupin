"""Chat panel coverage, timestamp parsing and bounded OCR retries."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPoint,QRect,QRectF,Qt
from PySide6.QtGui import QColor,QFont,QImage,QPainter,QPolygon
from PySide6.QtWidgets import QApplication
from price_lens.chat_history import parse_prefix,history_regions,header_without_badges,body_bounds,prepare_line
from price_lens.chat_scan import ScanMemory,make_row
from price_lens.chat_worker import scan,source_role
from price_lens.chat_ocr import pixels


def panel_scene(*,rails=True,scale=1):
    image=QImage(round(1000*scale),round(600*scale),QImage.Format.Format_RGB888);image.fill(QColor('#203326'))
    painter=QPainter(image);painter.scale(scale,scale);painter.fillRect(102,347,596,120,QColor('#1c2734'))
    if rails:
        # Native frame rails retain one physical pixel at reduced UI scales.
        for x in (698,710):painter.fillRect(QRectF(x,350,max(1,1/scale),115),QColor('#dddddd'))
    for y in (350,456):
        painter.fillRect(697,y-3,15,15,QColor('#eeeeee'));painter.fillRect(700,y,9,9,QColor('#298fb8'))
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#ffffff'))
        painter.drawPolygon(QPolygon([QPoint(704,y+2),QPoint(702,y+5),QPoint(706,y+5)]))
    font=QFont('DejaVu Sans');font.setPixelSize(11);painter.setFont(font)
    for index,colour in enumerate(('#f591c0','#39d5d9','#1c2734','#e8c32c')):
        baseline=399+index*16
        painter.fillRect(104,baseline-12,592,15,QColor(colour))
        painter.setPen(QColor('#eeeeee' if index==2 else '#151515'))
        painter.drawText(108,baseline,f'[14:05] Player{index}: sample message')
    painter.end();return image,[round(v*scale) for v in (100,500,800,38)]


class ChatHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_timestamp_and_channel_metadata_are_neither_speaker_nor_message_numbers(self):
        for text in ('[14:05] Player: 25만 메소 팝니다','[14:05:32] Player [CH34]: 25만 메소 팝니다',
                     ' [00:09] [Player]: 25만 메소 팝니다','Player CH34: 25만 메소 팝니다'):
            with self.subTest(text=text):
                prefix=parse_prefix(text);self.assertIsNotNone(prefix)
                self.assertEqual(prefix.speaker,'Player');self.assertEqual(prefix.body,'25만 메소 팝니다')
                self.assertEqual(text[prefix.body_start:],prefix.body)
        for text in ('[14:05]','[14:05] 안녕하세요','[25:05] Player: 안녕하세요',
                     '[14:99] Player: 안녕하세요','판매: 안녕하세요'):
            self.assertIsNone(parse_prefix(text))
        self.assertEqual(parse_prefix('PlayerCH34: 안녕하세요').speaker,'PlayerCH34')

    def test_valid_timestamp_allows_an_extended_chat_panel_without_guessing_ordinary_prose(self):
        self.assertEqual(source_role([20,100,300,16],'[14:05] Player: 안녕하세요',False,(),(1000,600)),('chat',True))
        self.assertEqual(source_role([20,100,300,16],'Player: 안녕하세요',False,(),(1000,600)),('text',False))
        self.assertEqual(source_role([20,500,300,16],'[14:05] 안녕하세요',False,(),(1000,600)),('text',False))

    def test_native_scrollbar_and_gutter_yield_whole_white_and_coloured_chat_rows(self):
        image,hud=panel_scene();rows,panels=history_regions(image,hud)
        self.assertEqual(len(panels),1);self.assertEqual(len(rows),4)
        self.assertEqual([box[1] for box in rows],sorted((box[1] for box in rows),reverse=True))
        self.assertTrue(all(box[2]>150 and box[3]<=16 for box in rows))
        self.assertEqual(history_regions(image,None),([],[]))
        self.assertEqual(history_regions(image,hud,exclude=[[100,340,620,150]]),([],[]))

    def test_buttons_without_their_continuous_scrollbar_rails_do_not_supply_a_panel(self):
        image,hud=panel_scene(rails=False)
        self.assertEqual(history_regions(image,hud),([],[]))

    def test_scaled_chat_proposals_remain_inside_the_image(self):
        for scale in (.75,1.5):
            with self.subTest(scale=scale):
                image,hud=panel_scene(scale=scale);boxes,panels=history_regions(image,hud)
                self.assertEqual(len(boxes),4)
                self.assertTrue(all(image.rect().contains(QRect(*box)) for box in boxes))

    def test_translucent_scene_does_not_extend_white_chat_but_coloured_links_remain(self):
        image,hud=panel_scene();painter=QPainter(image)
        painter.fillRect(590,419,80,14,QColor('#176e28'))
        painter.fillRect(500,423,7,7,QColor('#50a0ff'))
        painter.end()
        rows,_=history_regions(image,hud);plain=rows[1]
        self.assertLess(plain[0]+plain[2],590)
        self.assertGreaterEqual(plain[0]+plain[2],507)

    def test_unfinished_history_reads_yield_to_other_rows_instead_of_starving_them(self):
        image=QImage(700,600,QImage.Format.Format_RGB888);image.fill(QColor('#223344'))
        boxes=[[10,500,400,16],[10,520,80,16],[10,540,160,16]];reads=[]
        for number,box in enumerate(boxes):image.setPixelColor(box[0],box[1],QColor(10+number,20,30))
        reader=SimpleNamespace(read=lambda crop:(reads.append(crop.pixelColor(0,0).red()) or 'uncertain',.5))
        memory=ScanMemory()
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),\
             patch('price_lens.chat_history.history_regions',return_value=(boxes,[])),\
             patch('price_lens.chat_ocr.text_regions',return_value=[]):
            for _ in range(3):scan(image,reader,SimpleNamespace(),lambda row:None,budget=0,memory=memory)
        self.assertEqual(reads,[11,12,10])
        self.assertFalse(memory.reads)  # Work deferred at the deadline is not a negative result.

    @staticmethod
    def moving_row(background,*,changed=False):
        image=QImage(400,16,QImage.Format.Format_RGB888);image.fill(QColor(background))
        painter=QPainter(image)
        painter.fillRect(12,3,8,10,QColor('#eeeeee'));painter.fillRect(40,3,8,10,QColor('#eeeeee'))
        if changed:painter.fillRect(100,4,2,9,QColor('#eeeeee'))
        painter.end();return image

    def test_history_cache_ignores_moving_background_but_keeps_changed_glyphs(self):
        before=self.moving_row('#223344');after=self.moving_row('#335c29');changed=self.moving_row('#335c29',changed=True)
        memory=ScanMemory();calls=[];reader=SimpleNamespace(read=lambda line:(calls.append(line.width()) or 'English',.99))
        self.assertNotEqual(memory.key(before,False),memory.key(after,False))
        self.assertEqual(memory.key(before,False,history=True),memory.key(after,False,history=True))
        self.assertNotEqual(memory.key(after,False,history=True),memory.key(changed,False,history=True))
        for image in (before,after,changed):
            self.assertEqual(memory.read(image,False,reader,lambda:False,time.perf_counter()+1,history=True),[])
        self.assertEqual(calls,[400,400])

    def test_unknown_empty_palette_is_not_canonicalized_to_a_reusable_blank(self):
        first=QImage(160,16,QImage.Format.Format_RGB888);first.fill(QColor('#223344'))
        second=first.copy();second.fill(QColor('#335c29'))
        self.assertEqual(prepare_line(first),first)
        self.assertNotEqual(ScanMemory.key(first,False,history=True),ScanMemory.key(second,False,history=True))

    def test_history_progress_survives_scenery_changes_between_submitted_frames(self):
        boxes=[[10,500,400,16],[10,520,80,16],[10,540,160,16]];reads=[];memory=ScanMemory()
        reader=SimpleNamespace(read=lambda line:(reads.append(line.width()) or 'uncertain',.5))
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),\
             patch('price_lens.chat_history.history_regions',return_value=(boxes,[])),\
             patch('price_lens.chat_ocr.text_regions',return_value=[]):
            for colour in ('#223344','#335c29','#243735'):
                image=QImage(700,600,QImage.Format.Format_RGB888);image.fill(QColor(colour));painter=QPainter(image)
                for x,y,w,h in boxes:painter.fillRect(x+10,y+3,8,10,QColor('#eeeeee'))
                painter.end();scan(image,reader,SimpleNamespace(),lambda row:None,budget=0,memory=memory)
        self.assertEqual(reads,[80,160,400])

    def test_channel_badge_cleanup_cannot_touch_message_pixels(self):
        image=QImage(340,16,QImage.Format.Format_RGB888);image.fill(QColor('#e88cbd'))
        painter=QPainter(image);painter.fillRect(100,3,34,10,QColor('#fff0d7'));painter.fillRect(105,5,5,5,QColor('#c43a37'))
        painter.fillRect(200,4,80,9,QColor('#123456'));painter.end()
        text='[14:05] Player [CH34]: 안녕하세요';separator=text.find(':',7)
        glyphs=[(i,i+1,i*6,(i+1)*6,.99) for i in range(7)]
        glyphs.append((separator,separator+1,170,182,.99))
        cleaned=header_without_badges(image,text,dict(glyphs=glyphs))
        self.assertIsNotNone(cleaned)
        self.assertTrue((pixels(cleaned)[:,190:]==pixels(image)[:,190:]).all())
        self.assertFalse((pixels(cleaned)[:,100:134]==pixels(image)[:,100:134]).all())
        self.assertIsNone(header_without_badges(image,text,{}))
        bad=[*glyphs[:-1],(separator,separator+1,70,80,.99)]
        self.assertIsNone(header_without_badges(image,text,dict(glyphs=bad)))
        text='Player C34-: 안녕하세요';separator=text.index(':');glyphs=[(separator,separator+1,170,182,.99)]
        self.assertIsNone(header_without_badges(image,text,dict(glyphs=glyphs)))
        self.assertIsNotNone(header_without_badges(image,text,dict(glyphs=glyphs),history=True))

    def test_body_retry_requires_a_confident_measured_speaker(self):
        prefix=parse_prefix('Player: 안녕하세요')
        glyphs=[(i,i+1,i*7,(i+1)*7,.99) for i in range(14)]
        self.assertEqual(body_bounds(prefix,dict(glyphs=glyphs)),54)
        glyphs[2]=(*glyphs[2][:-1],.89)
        self.assertIsNone(body_bounds(prefix,dict(glyphs=glyphs)))

    def test_skipped_contrast_at_deadline_does_not_poison_the_negative_cache(self):
        image=QImage(200,16,QImage.Format.Format_RGB888);image.fill(QColor('#c1699d'))
        class Reader:
            def __init__(self):self.calls=0
            def read(self,line):
                self.calls+=1
                return ('안녕하세요',.99) if self.calls==3 else ('안녕하세요',.7)
        reader=Reader();memory=ScanMemory();key=memory.key(image,False)
        self.assertIsNone(memory.read(image,False,reader,lambda:False,0))
        self.assertNotIn(key,memory.reads)
        result=memory.read(image,False,reader,lambda:False,time.perf_counter()+1)
        self.assertEqual(result[0]['text'],'안녕하세요');self.assertIn(key,memory.reads)

    def test_clear_message_can_be_read_without_lowering_its_confidence_for_the_header(self):
        image=QImage(400,16,QImage.Format.Format_RGB888);image.fill(QColor('#222222'))
        text='[14:05] Player: 안녕하세요'
        class Reader:
            def read(self,line):return (text,.82) if line.width()==400 else ('안녕하세요',.99)
            def detail(self,line):
                return dict(glyphs=[(i,i+1,i*7,(i+1)*7,.99) for i in range(len(text))]) if line.width()==400 else {}
        result=ScanMemory().read(image,False,Reader(),lambda:False,time.perf_counter()+1)
        self.assertEqual(result[0]['text'],text);self.assertGreater(result[0]['rect'][0],0)
        self.assertEqual(result[0]['confidence'],.99)

    @staticmethod
    def contrast_fixture():
        image=QImage(400,16,QImage.Format.Format_RGB888);image.fill(QColor('#223344'))
        painter=QPainter(image);painter.fillRect(20,3,50,10,QColor('#eeeeee'));painter.end()
        return image

    def test_broken_timestamp_is_never_sent_to_the_model_as_chat_prose(self):
        image=self.contrast_fixture()
        reader=SimpleNamespace(read=lambda line:('[14:05Player: 안녕하세요',.99))
        result=ScanMemory().read(image,False,reader,lambda:False,time.perf_counter()+1,history=True)
        self.assertEqual(result,[])

    def test_contrast_cannot_destroy_an_intact_history_header(self):
        image=self.contrast_fixture();good='[14:05] Player: 안녕하세요';bad='[14:05Player: 안녕하세요'
        reader=SimpleNamespace(read=lambda line:(good,.91) if line.format()==image.format() else (bad,.99))
        result=ScanMemory().read(image,False,reader,lambda:False,time.perf_counter()+1,history=True)
        self.assertEqual(result[0]['text'],good)

    def test_complete_contrast_header_can_recover_a_higher_scoring_broken_header(self):
        image=self.contrast_fixture();good='[14:05] Player: 안녕하세요';bad='[14:05Player: 안녕하세요'
        reader=SimpleNamespace(read=lambda line:(bad,.99) if line.format()==image.format() else (good,.95))
        result=ScanMemory().read(image,False,reader,lambda:False,time.perf_counter()+1,history=True)
        self.assertEqual(result[0]['text'],good)

    def test_history_body_and_sender_have_separate_pixel_anchors(self):
        image=self.contrast_fixture();text='[14:05] Player: 안녕하세요'
        class Reader:
            def read(self,line):return (text,.95) if line.width()==400 else ('안녕하세요',.99)
            def detail(self,line):
                return dict(glyphs=[(i,i+1,i*7,(i+1)*7,.99) for i in range(len(text))]) if line.width()==400 else {}
        result=ScanMemory().read(image,False,Reader(),lambda:False,time.perf_counter()+1,history=True)
        self.assertEqual(result[0]['confidence'],.99)
        self.assertGreater(result[0]['rect'][0],result[0]['speaker_rect'][0]+result[0]['speaker_rect'][2])
        frame=QImage(700,600,QImage.Format.Format_RGB888);frame.fill(QColor('#223344'));translated=[]
        translator=SimpleNamespace(translate=lambda value:(translated.append(value) or 'hello','Local'))
        row=make_row(frame,[10,500,400,16],False,result,translator,(),source_role,lambda:False)
        self.assertEqual(translated,['안녕하세요']);self.assertEqual(row['speaker'],'Player')
        self.assertEqual(row['source_role'],'chat')
        self.assertLess(row['speaker_box'][0]+row['speaker_box'][2],row['track_box'][0])

    def test_unprefixed_korean_history_continuations_can_still_translate(self):
        image=self.contrast_fixture();reader=SimpleNamespace(read=lambda line:('안녕하세요',.99))
        result=ScanMemory().read(image,False,reader,lambda:False,time.perf_counter()+1,history=True)
        self.assertEqual(result[0]['text'],'안녕하세요')

    def test_deferred_body_contrast_is_not_cached_as_an_empty_read(self):
        image=self.contrast_fixture();text='[14:05] Player: 안녕하세요';clock=[0.]
        class Reader:
            def read(self,line):
                if line.width()==400:return text,.85
                clock[0]=2.;return '안녕하세요',.8
            def detail(self,line):
                return dict(glyphs=[(i,i+1,i*7,(i+1)*7,.99) for i in range(len(text))])
        memory=ScanMemory()
        with patch('price_lens.chat_scan.time.perf_counter',side_effect=lambda:clock[0]):
            result=memory.read(image,False,Reader(),lambda:False,1,history=True)
        self.assertIsNone(result);self.assertFalse(memory.reads)

    def test_interruption_after_a_model_read_does_not_start_more_work_or_cache_it(self):
        image=self.contrast_fixture();interrupted=[False];calls=[]
        def read(line):
            calls.append(line.width());interrupted[0]=True
            return '[14:05] Player: 안녕하세요',.91
        memory=ScanMemory()
        result=memory.read(image,False,SimpleNamespace(read=read),lambda:interrupted[0],time.perf_counter()+1,history=True)
        self.assertEqual(result,[]);self.assertEqual(calls,[400]);self.assertFalse(memory.reads)

    def test_new_history_message_emits_before_full_scene_detection_and_keeps_only_body_numbers(self):
        image=QImage(1000,600,QImage.Format.Format_RGB888);image.fill(QColor('#222222'));outputs=[];sources=[]
        def translate(text):sources.append(text);return 'Selling for 250k mesos','Local'
        def detector(*args,**kwargs):
            self.assertEqual(len(outputs),1)
            return []
        reader=SimpleNamespace(read=lambda line:('[14:05] Player [CH34]: 25만 메소 팝니다',.99))
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),\
             patch('price_lens.chat_history.history_regions',return_value=([[20,500,350,16]],[[20,450,400,80]])),\
             patch('price_lens.chat_ocr.text_regions',side_effect=detector):
            scan(image,reader,SimpleNamespace(translate=translate),outputs.append)
        self.assertEqual(sources,['25만 메소 팝니다']);self.assertEqual(outputs[0]['speaker'],'Player')
        self.assertEqual(outputs[0]['source_role'],'chat')

    def test_hud_hint_is_clipped_and_translated_without_claiming_a_chat_context(self):
        from price_lens.chat import ChatTranslation
        from pathlib import Path
        class Pipe:
            def __init__(self):self.writes=[]
            def write(self,data):self.writes.append(data)
        chat=ChatTranslation(Path(__file__).resolve().parents[1]);pipe=Pipe()
        try:
            chat.ready=True;chat.process=pipe
            image=QImage(1000,700,QImage.Format.Format_RGB888);image.fill(QColor('#222222'))
            self.assertTrue(chat.request(image,QRect(100,50,800,600),hud=QRect(120,600,700,35)))
            header=json.loads(pipe.writes[-2]);self.assertEqual(header['hud'],[20,550,700,35])
            self.assertEqual(header['contexts'],[])
        finally:chat.process=None;chat.close()

    def test_timestamped_history_copy_and_bubble_share_one_translation_event(self):
        from pathlib import Path
        from price_lens.chat import ChatTranslation
        image=QImage(1000,600,QImage.Format.Format_RGB888);image.fill(QColor('#eeeeee'))
        painter=QPainter(image);painter.fillRect(30,35,4,12,QColor('#111111'));painter.fillRect(30,505,4,12,QColor('#111111'));painter.end()
        outputs=[];reader=SimpleNamespace(read=lambda line:('[14:05] Player [CH34]: 안녕하세요',.99))
        with patch('price_lens.chat_ocr.bubbles',return_value=[]),patch('price_lens.chat_ocr.text_regions',return_value=[[20,500,350,16]]):
            scan(image,reader,SimpleNamespace(translate=lambda text:('hello','Local')),outputs.append)
        chat=ChatTranslation(Path(__file__).resolve().parents[1])
        try:
            chat.frame=image;chat.region=image.rect();chat.identity=1
            bubble=dict(box=[20,30,200,30],speaker='Player',original='안녕하세요',text='hello',note='Local',source_role='bubble',role_verified=True)
            with patch('price_lens.chat.time.monotonic',return_value=10):chat.accept_row(bubble)
            chat.identity=2
            with patch('price_lens.chat.time.monotonic',return_value=10.1):chat.accept_row(outputs[0])
            self.assertEqual(len(chat.history),1);self.assertEqual(len(chat.cards),1)
            self.assertEqual({source['source_role'] for source in chat.cards[0]['sources']},{'bubble','chat'})
        finally:chat.close()
