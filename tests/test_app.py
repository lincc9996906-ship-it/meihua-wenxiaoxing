from datetime import datetime
from pathlib import Path
import sys
import json
import re
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import (build_chart, make_datetime, validate_question, blocked_topic,
                  validate_reading, ask_model, ModelConfig, messages_for,
                  InputError, ReadingError, DISCLAIMER, GLYPHS, reading_payload, HEADINGS,
                  reading_for_display, reading_sections)
from meihua_yi import engine
from streamlit.testing.v1 import AppTest
from settings import load_model_config, SettingsError
import requests


def chart():
    return build_chart(2026,10,6,17,"两个学习方向，我该关注哪些因素？","有些犹豫，但没有紧急事项。")


def good_reading():
    return """## 1. 读卦复核
本卦：天火同人；互卦：天风姤；变卦：天雷无妄。第三爻动，体乾金、用离火。

## 2. 总断
偏向先找到共同目标，再比较投入条件。【依据：天火同人】

## 3. 体用生克
可以关注外部压力与学习资源的平衡。【依据：用克体】

## 4. 卦名与卦象
本卦：天火同人，可以考虑如何找到共同目标。【依据：本卦天火同人】

## 5. 动爻爻辞
爻辞此项缺失，以下为基于现有信息的推断；关注调整学习方法的环节。【依据：第三爻动】

## 6. 互卦看过程
互卦：天风姤，可观察沟通方式，不代表已经掌握他人想法。【依据：互卦天风姤】

## 7. 变卦看结果
变卦：天雷无妄，偏向按实际条件调整学习安排。【依据：变卦天雷无妄】

## 8. 结合用户问题
比较两个方向的课程、投入与反馈节奏。【依据：体用关系与用户提问】

## 9. 应期
可把三周作为观察窗口，选择周而非天是配合学习反馈节奏，属于象征性取数，不保证在该时点发生变化。【依据：第三爻动】

## 10. 建议
列出各方向需要的时间和资源，再核对自己的条件。【依据：用克体与用户提问】

## 11. 局限声明
当前没有爻辞、卦辞与详细现实背景，象征性比较不等于事实保证。
"""


class CoreTests(unittest.TestCase):
    def test_exact_datetime_contract(self):
        with patch.object(engine,'qigua_time',wraps=engine.qigua_time) as fn:
            c = chart()
        fn.assert_called_once_with(datetime(2026,10,6,17,0,0))
        self.assertEqual(c['lines'],[1,0,1,1,1,1])
        self.assertEqual(c['moving'],[2])
        self.assertIn('天火同人',c['hexagram_text'])
        self.assertEqual(GLYPHS['地天泰'],'䷊')

    def test_lunar_new_year(self):
        c = build_chart(2026,2,17,0,'学习计划如何安排？')
        # 午年7 + 正月1 + 初一1 = 9; 子时1 -> lower 10 mod8 = 兑.
        self.assertEqual(c['lines'],[1,1,0,1,1,1])
        self.assertEqual(c['moving'],[3])

    def test_hour_boundaries_display(self):
        for hour, expected in ((3,'寅时'),(13,'未时'),(14,'未时'),(15,'申时'),(16,'申时'),(17,'酉时'),(23,'子时'),(0,'子时')):
            with self.subTest(hour=hour):
                self.assertEqual(build_chart(2026,10,6,hour,'学习安排如何？')['shichen'],expected)

    def test_invalid_and_out_of_range_dates(self):
        for values in ((2026,2,30,17),(2026,13,1,1),(2026,10,6,24),
                       (1900,1,1,0),(2100,1,1,0),(2026,10,1.2,17)):
            with self.subTest(values=values),self.assertRaises(InputError):
                make_datetime(*values)

    def test_no_lunar_no_chart(self):
        with patch.object(engine,'HAS_LUNAR',False),patch.object(engine,'qigua_time') as fn:
            with self.assertRaises(InputError): chart()
            fn.assert_not_called()

    def test_blocked_before_chart(self):
        for text in ('我还能活多久','癌症治疗会怎样','官司能否胜诉','生 死判断','手术结果如何'):
            with self.subTest(text=text),patch.object(engine,'qigua_time') as fn:
                with self.assertRaises(InputError): build_chart(2026,10,6,17,text)
                fn.assert_not_called()
        self.assertIsNone(blocked_topic('换一份工作需要考虑什么？'))
        with self.assertRaises(InputError): validate_question('工作如何？','背景是法院案件')

    def test_prompt_context(self):
        messages = messages_for(chart())
        self.assertEqual(messages[0]['role'],'system')
        self.assertIn('2026-10-06 17:00',messages[1]['content'])
        self.assertIn('天火同人',messages[1]['content'])
        self.assertIn('两个学习方向',messages[1]['content'])
        self.assertNotIn('大凶',messages[1]['content'])
        facts = json.loads(messages[1]['content'])['gua_data']
        self.assertEqual(facts['ben_gua']['name'],'天火同人')
        self.assertEqual(facts['hu_gua']['name'],'天风姤')
        self.assertEqual(facts['bian_gua']['name'],'天雷无妄')
        self.assertEqual(facts['ti_gua'],'乾')
        self.assertEqual(facts['yong_gua'],'离')
        self.assertEqual(facts['dong_yao'],3)

    def test_company_example_json_and_changed_relation(self):
        c=build_chart(2026,10,7,3,'我最后会去哪家公司','目前求职中','甲公司：咨询；乙公司：数据服务，其他信息未知。')
        payload=reading_payload(c)
        gua=payload['gua_data']
        self.assertEqual([gua[key]['name'] for key in ('ben_gua','hu_gua','bian_gua')],['泽风大过','乾为天','泽水困'])
        self.assertEqual((gua['dong_yao'],gua['ti_gua'],gua['yong_gua']),(3,'兑','巽'))
        self.assertEqual((gua['ti_yong_relation'],gua['bian_relation']),('体克用','体生用'))
        self.assertEqual((gua['bian_yong_gua'],gua['bian_yong_wuxing']),('坎','水'))
        self.assertEqual(payload['time'],'2026-10-07 03:00')
        self.assertEqual(payload['time_range'],'03:00–03:59')
        self.assertEqual(payload['time_precision'],'hour')
        self.assertIn('甲公司',payload['companies'])
        self.assertIsNone(gua['yao_ci'])
        self.assertIsNone(gua['gua_ci'])
        self.assertEqual(gua['ben_gua']['symbol'],'䷛')
        # Upper-trigram moving line: the unchanged body stays 兑（金）, while
        # the changing 乾（金） becomes 巽（木）; check that the side is not swapped.
        upper=reading_payload(build_chart(2026,2,17,0,'学习计划如何安排？'))['gua_data']
        self.assertEqual((upper['ti_gua'],upper['bian_yong_gua']),('兑','巽'))
        self.assertEqual((upper['ti_yong_relation'],upper['bian_relation']),('体用比和','体克用'))

    def test_flow_order_evidence_and_missing_quotes(self):
        for text in (good_reading().replace('## 2. 总断','## 2. 应期'),
                     good_reading().replace('【依据：用克体】',''),
                     good_reading().replace('爻辞此项缺失，以下为基于现有信息的推断','九三爻辞已经提供'),
                     good_reading()+'【依据：九三爻辞“栋桡，凶”】'):
            with self.subTest(text=text),self.assertRaises(ReadingError):
                validate_reading(text,chart())
        # The previous 1500-character ceiling must not cut off the full flow.
        longer=good_reading().replace('列出各方向需要的时间和资源','详细核对现实条件。'*110)
        self.assertGreater(len(longer),1500)
        self.assertTrue(validate_reading(longer,chart()).endswith(DISCLAIMER))

    def test_company_three_distinct_conclusions(self):
        c=build_chart(2026,10,6,17,'我最后会去哪家公司')
        with self.assertRaises(ReadingError):
            validate_reading(good_reading(),c)
        text=good_reading().replace('比较两个方向的课程、投入与反馈节奏。','最可能去：有共同目标的团队；最适合：需结合岗位资源；最需要谨慎：职责不清的团队。')
        self.assertTrue(validate_reading(text,c).endswith(DISCLAIMER))

    def test_display_groups_keep_original_body_and_hide_internal_sections(self):
        raw=validate_reading(good_reading(),chart())
        sections=reading_sections(raw)
        displayed=reading_for_display(raw)
        self.assertEqual([line for line in displayed.splitlines() if line.startswith('## ')],
                         ['## 总断','## 卦象大意','## 分析','## 应期','## 建议'])
        self.assertNotIn('【依据',displayed)
        self.assertNotIn(sections['读卦复核'],displayed)
        self.assertNotIn(sections['局限声明'],displayed)
        self.assertNotIn(DISCLAIMER,displayed)
        # Every retained paragraph must be preserved verbatim except its
        # citation annotation. The five merged blocks keep their original order.
        bodies=[]
        for name in HEADINGS[1:-1]:
            clean=re.sub(r'【依据[：:][^】]+】','',sections[name]).strip()
            self.assertIn(clean,displayed)
            bodies.append(clean)
        offsets=[displayed.index(body) for body in bodies]
        self.assertEqual(offsets,sorted(offsets))
        self.assertEqual(len(reading_sections(raw)),11)
        self.assertIn('【依据：',raw)

    def test_display_removes_standalone_multiline_and_bold_evidence(self):
        raw=good_reading().replace('【依据：用克体】','**【依据：\n用克体\n】**\n\n[依据: 体乾金]')
        visible=reading_for_display(raw)
        self.assertNotIn('依据',visible)
        self.assertNotIn('****',visible)
        self.assertIn('可以关注外部压力与学习资源的平衡。',visible)

    def test_model_response_guards(self):
        c = chart()
        self.assertTrue(validate_reading(good_reading(),c).endswith(DISCLAIMER))
        for text in (good_reading().replace('## 9. 应期','## 9. 缺少标题'),good_reading()+'风天小畜',
                     good_reading()+'甲'*12000,good_reading()+'<script>bad</script>',
                     '没有结构的文字'):
            with self.subTest(text=text[-20:]),self.assertRaises(ReadingError):
                validate_reading(text,c)

    def test_trigram_meanings_do_not_look_like_other_hexagrams(self):
        text = good_reading() + '\n\n体卦取象：乾为天，属金；用卦取象：离为火。互卦上乾下巽，巽为风；变卦下震，震为雷。'
        self.assertTrue(validate_reading(text,chart()).endswith(DISCLAIMER))

    def test_wrong_labeled_hexagram_is_still_rejected(self):
        for text in (good_reading().replace('本卦：天火同人','本卦：乾为天'),
                     good_reading().replace('本卦：天火同人','**本卦：天风姤**'),
                     good_reading().replace('互卦：天风姤','互卦（天雷无妄）'),
                     good_reading()+'\n本卦为“乾为天”'):
            with self.subTest(text=text), self.assertRaises(ReadingError):
                validate_reading(text,chart())

    def test_name_error_explains_the_conflict(self):
        with self.assertRaises(ReadingError) as caught:
            validate_reading(good_reading()+'\n风天小畜提示调整。',chart())
        self.assertIn('风天小畜',str(caught.exception))
        self.assertIn('天火同人',str(caught.exception))

    def test_model_network_errors_sanitized(self):
        for error in (requests.exceptions.Timeout('secret'),requests.exceptions.ConnectionError('secret')):
            with self.subTest(error=type(error).__name__),patch('core.requests.post',side_effect=error):
                with self.assertRaises(ReadingError) as caught:
                    ask_model(chart(),ModelConfig('test-key','test-model'))
                self.assertNotIn('secret',str(caught.exception))

    def test_api_payload_and_response(self):
        response = Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':good_reading()}}]}
        with patch('core.requests.post',return_value=response) as post:
            result = ask_model(chart(),ModelConfig('test-key','test-model'))
        self.assertTrue(result.endswith(DISCLAIMER))
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.kwargs['json']['model'],'test-model')
        self.assertEqual(post.call_args.kwargs['json']['temperature'],0.6)
        self.assertEqual(post.call_args.kwargs['json']['top_p'],0.9)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'],4000)
        self.assertNotIn('response_format',post.call_args.kwargs['json'])

    def test_service_errors_and_truncation(self):
        for code in (302,401,403,429,500):
            response=Mock(status_code=code)
            with self.subTest(code=code),patch('core.requests.post',return_value=response):
                with self.assertRaises(ReadingError): ask_model(chart(),ModelConfig('test-key','test-model'))
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'length','message':{'content':good_reading()}}]}
        with patch('core.requests.post',return_value=response),self.assertRaises(ReadingError):
            ask_model(chart(),ModelConfig('test-key','test-model'))


class ConfigurationTests(unittest.TestCase):
    def test_file_load_and_secret_not_in_repr(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'secrets.toml'
            path.write_text('[deepseek]\napi_key="test-local-key"\n',encoding='utf-8-sig')
            config=load_model_config(path,environ={})
            self.assertEqual(config.api_key,'test-local-key')
            self.assertEqual(config.model,'deepseek-chat')
            self.assertNotIn('test-local-key',repr(config))

    def test_missing_key_and_environment_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'missing.toml'
            self.assertIsNone(load_model_config(path,environ={}))
            self.assertEqual(load_model_config(path,environ={'DEEPSEEK_API_KEY':'test-env-key'}).api_key,'test-env-key')

    def test_invalid_file_does_not_echo_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'secrets.toml'
            for source in ('[deepseek]\napi_key="test-secret', '[deepseek]\napi_key=123',
                           '[deepseek]\napi_key="test-secret"\nmodel=""'):
                path.write_text(source,encoding='utf-8')
                with self.subTest(source=source),self.assertRaises(SettingsError) as error:
                    load_model_config(path,environ={})
                self.assertNotIn('test-secret',str(error.exception))

    def test_saved_file_is_loaded_on_next_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'secrets.toml'
            path.write_text('[deepseek]\napi_key=""',encoding='utf-8')
            self.assertIsNone(load_model_config(path,environ={}))
            path.write_text('[deepseek]\napi_key="test-new-key"',encoding='utf-8')
            self.assertEqual(load_model_config(path,environ={}).api_key,'test-new-key')


class PageTests(unittest.TestCase):
    def setUp(self):
        config_patch=patch('settings.load_model_config',return_value=None)
        self.config_mock=config_patch.start()
        self.addCleanup(config_patch.stop)

    def new_app(self):
        return AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()

    def submit(self,app,question='两个学习方向怎么考虑？',day=6,month=10):
        for widget,value in zip(app.number_input,(2026,month,day)):
            widget.set_value(value)
        app.selectbox(key='hour_select').set_value(17)
        app.text_input[0].set_value(question)
        app.button[0].click()
        return app.run()

    def test_initial_and_chart(self):
        app=self.new_app()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.number_input),3)
        self.assertEqual(len(app.text_input),1)
        self.assertEqual(len(app.selectbox),1)
        self.assertFalse(any(e.label=='解读设置' for e in app.expander))
        self.assertFalse(any(e.label=='候选公司（选填）' for e in app.text_area))
        self.assertEqual(app.selectbox(key='hour_select').options[3],'03:00–03:59')
        self.assertEqual(app.selectbox(key='hour_select').options[15],'15:00–15:59')
        self.submit(app)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['chart']['datetime'],datetime(2026,10,6,17))
        self.assertTrue(any('天火同人' in m.value for m in app.markdown))
        self.assertNotIn('reading',app.session_state)
        self.assertFalse(any(e.label=='查看结构化卦象' for e in app.expander))
        self.assertFalse(app.json)

    def test_invalid_date_clears_previous_chart(self):
        app=self.new_app()
        self.submit(app)
        self.submit(app,day=30,month=2)
        self.assertFalse(app.exception)
        self.assertTrue(app.warning)
        self.assertNotIn('chart',app.session_state)

    def test_blocked_topic_has_no_chart(self):
        app=self.new_app()
        self.submit(app,question='我会被判刑吗')
        self.assertFalse(app.exception)
        self.assertTrue(app.warning)
        self.assertNotIn('chart',app.session_state)

    def test_reading_retry_keeps_submitted_time(self):
        app=self.new_app()
        self.config_mock.return_value=ModelConfig('test-key')
        with patch('core.ask_model',return_value=good_reading()) as request:
            self.submit(app)
        self.assertFalse(app.exception)
        self.assertEqual(request.call_count,1)
        self.assertIn('reading',app.session_state)
        app.selectbox(key='hour_select').set_value(18)
        app.button(key='generate_reading').click()
        with patch('core.ask_model',side_effect=ReadingError('解读等待超时，排盘已保留。')) as retry:
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(retry.call_args.args[0]['datetime'],datetime(2026,10,6,17))
        self.assertEqual(app.session_state['chart']['datetime'],datetime(2026,10,6,17))
        self.assertIn('reading_error',app.session_state)
        self.assertNotIn('reading',app.session_state)

    def test_model_text_validation_in_page(self):
        for text, accepted in ((good_reading()+'\n体卦取象：乾为天；用卦取象：离为火。',True),
                               (good_reading().replace('本卦：天火同人','本卦：天风姤'),False)):
            with self.subTest(accepted=accepted):
                app=self.new_app()
                self.config_mock.return_value=ModelConfig('test-key')
                response=Mock(status_code=200)
                response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':text}}]}
                with patch('core.requests.post',return_value=response):
                    self.submit(app)
                self.assertFalse(app.exception)
                self.assertIn('chart',app.session_state)
                self.assertEqual('reading' in app.session_state,accepted)
                if accepted:
                    self.assertEqual(app.session_state['reading'],validate_reading(text,chart()))
                    visible=next(m.value for m in app.markdown if m.value.startswith('## 总断'))
                    self.assertNotIn('【依据',visible)
                    self.assertNotIn('读卦复核',visible)
                    self.assertNotIn('局限声明',visible)
                    self.assertIn('## 卦象大意',visible)
                if not accepted:
                    self.assertIn('本卦写成了',app.session_state['reading_error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
