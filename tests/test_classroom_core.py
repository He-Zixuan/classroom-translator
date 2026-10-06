from types import SimpleNamespace
from classroom_core import SentenceBuffer, Store, translation_prompt

def token(text, start=0, end=1):
    return SimpleNamespace(text=text, start=start, end=end)

def test_complete_sentence_and_trailing_clause():
    emitted=[]
    b=SentenceBuffer(lambda *args: emitted.append(args))
    b.insert([token(' Today'), token(' we discuss costs.')])
    b.insert([token(' An incomplete clause', 1, 2)])
    assert emitted[0][0]=='Today we discuss costs.'
    assert b.text.strip()=='An incomplete clause'
    b.flush()
    b.flush()
    assert len(emitted)==2

def test_decimal_and_abbreviation_are_preserved():
    emitted=[]
    b=SentenceBuffer(lambda *args: emitted.append(args))
    b.insert([token(' Dr.'), token(' Smith reports 3.5 percent.')])
    assert [s[0] for s in emitted]==['Dr. Smith reports 3.5 percent.']

def test_pause_and_long_segment_keep_all_words():
    emitted=[]
    b=SentenceBuffer(lambda *args: emitted.append(args), max_words=3)
    b.insert([token(' one two',0,1),token(' three four',3,4),token(' five six',4,5)])
    b.flush()
    assert ' '.join(x[0] for x in emitted)=='one two three four five six'

def test_queue_restart_stable_pairing_and_failed_retry(tmp_path):
    path=tmp_path/'history.db'
    s=Store(path)
    sid=s.session('example',{'terms':'cost 翻译成 成本'})
    first=s.add(sid,'First sentence.',0,1)
    second=s.add(sid,'Second sentence.',1,2)
    s.update(first['id'],'translating')
    s.db.close()
    s=Store(path)
    assert s.next()['id']==first['id']
    s.update(first['id'],'done','第一句。')
    assert s.next()['id']==second['id']
    s.update(second['id'],'error',error='timeout')
    assert s.next() is None
    s.update(second['id'],'waiting')
    assert s.next()['english']=='Second sentence.'
    assert s.rows(sid)[0]['chinese']=='第一句。'
    assert 'First sentence.' in s.context(second)
    s.db.close()

def test_translation_prompt_uses_context_and_terms():
    p=translation_prompt('Demand did not double.','Previous sentence.','demand 翻译成 需求','Economics')
    assert '不需要翻译上文' in p
    assert '需求' in p
    assert p.endswith('Demand did not double.')


def test_rename_persists_without_changing_subtitles_or_translation_context(tmp_path):
    path = tmp_path / 'history.db'
    store = Store(path)
    settings = {'course': 'Economics', 'terms': 'cost 翻译成 成本'}
    sid = store.session('2026-10-06 09:00:00', settings)
    segment = store.add(sid, 'A real lesson sentence.', 0, 2)
    store.update(segment['id'], 'done', '真实课堂的一句话。')
    before = store.rows(sid)
    assert store.rename_session(sid, '  经济学第一课  ')['title'] == '经济学第一课'
    assert store.rename_session('missing-session', 'Missing') is None
    store.db.close()
    reopened = Store(path)
    assert reopened.sessions()[0]['title'] == '经济学第一课'
    assert reopened.rows(sid) == before
    assert reopened.settings(sid) == settings
    reopened.db.close()


def test_first_segment_course_is_reference_only():
    p=translation_prompt('Demand did not double.', course='Economics')
    assert '课程背景（仅供参考，不要输出）' in p
    assert '不需要翻译上文' in p
    assert p.endswith('Demand did not double.')

def test_isolated_punctuation_does_not_create_translation_job():
    emitted=[]
    b=SentenceBuffer(lambda *args: emitted.append(args))
    b.insert([token('.')])
    b.flush()
    assert not emitted

def test_short_fragment_waits_for_full_meaning():
    emitted=[]
    b=SentenceBuffer(lambda *args: emitted.append(args))
    b.insert([token(' Before making a.')])
    assert not emitted
    b.insert([token(' Decision.',1,2)])
    assert emitted[0][0]=='Before making a. Decision.'

def test_classroom_buffer_groups_streaming_fragments_before_chinese():
    emitted=[]
    b=SentenceBuffer(lambda *args:emitted.append(args),min_words=18,pause_seconds=3)
    b.insert([token(' - This semester. - This semester will be looking.',0,4)])
    b.insert([token(' - At. - Uh.',4.5,5)])
    assert not emitted
    b.insert([token(' Reading and English listening mainly.',5.5,9)])
    assert len(emitted)==1
    assert 'This semester' in emitted[0][0] and 'English listening' in emitted[0][0]

def test_streaming_period_after_is_waits_for_sentence_continuation():
    emitted=[]
    b=SentenceBuffer(lambda *args:emitted.append(args),min_words=18,pause_seconds=3)
    b.insert([token("Today is going to be a very easy day. I'm just going to talk about what the plan is.",0,10)])
    assert not emitted
    b.insert([token(' For us this semester.',10.2,12)])
    assert len(emitted)==1
    assert 'For us this semester.' in emitted[0][0]

def test_glossary_only_contains_terms_actually_present_in_current_english():
    p=translation_prompt('English reading and listening.',terms='IELTS 翻译成 雅思\nscanning 翻译成 寻读\nreading 翻译成 阅读')
    assert '雅思' not in p and '寻读' not in p
    assert 'reading 翻译成 阅读' in p
