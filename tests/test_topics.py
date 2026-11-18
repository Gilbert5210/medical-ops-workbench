from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend import ai, topics, worker, xhs
from backend.db import Audience, Job, Session, Source, now


def test_all_audiences_have_prompt_linked_search_entries(client):
    with Session() as s:
        audiences = list(s.scalars(select(Audience)))
        assert set(topics.SEEDS) == {a.id for a in audiences}
        for audience in audiences:
            for typ in 'ABC':
                data = topics.snapshot(s, audience, typ)
                rec = data['recommendation']
                assert rec['id'] == audience.id
                assert rec['prompt'] == audience.prompts[typ]
                assert rec['topic'] == audience.topics[typ]
                assert len(rec['items']) >= 3
                assert all(not i['evidence'] and i['discussion_count'] is None and not i['checked_at'] for i in rec['items'])
    assert client.get('/api/discovery/topics?audience_id=missing').status_code == 404
    assert client.get('/api/discovery/topics?content_type=Z').status_code == 422


@pytest.mark.parametrize(('value','expected'), [('1.2万',12000),('2,350',2350),('45+',45),('0',0),('',None),('--',None),(None,None),(True,None)])
def test_interaction_count_preserves_missing_data(value,expected):
    assert topics.counter(value) == expected


def test_duplicate_topic_requests_share_active_job_and_previous_result(client):
    body = {'audience_id':'M01','content_type':'B'}
    first = client.post('/api/discovery/topics',json=body)
    assert first.status_code == 200
    assert client.post('/api/discovery/topics',json=body).json()['id'] == first.json()['id']
    with Session.begin() as s:
        j = s.get(Job,first.json()['id']);j.state='completed'
        rec=topics.defaults(s.get(Audience,'M01'),'B')
        rec['generated_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        j.result=rec;j.created_at=rec['generated_at']
    second = client.post('/api/discovery/topics',json=body).json()
    data = client.get('/api/discovery/topics?audience_id=M01&content_type=B').json()
    assert data['stale'] and data['recommendation']['generated_at']==rec['generated_at']
    assert data['active_job']['id']==second['id']
    assert not client.get('/api/discovery/topics?audience_id=M07&content_type=B').json()['active_job']


@pytest.mark.asyncio
async def test_ai_topics_use_actual_search_evidence_not_model_claims(monkeypatch):
    calls=[]
    async def complete(prompt):
        if 'selections' in prompt:
            return {'selections':[
                {'keyword':'临床专硕 缺失数据','relevant_ids':['a'*24, 'b'*24, 'f'*24]},
                {'keyword':'临床专硕 研究设计','relevant_ids':['b'*24]},
            ]}, {}
        assert '临床专硕已有一批病例资料' in prompt
        assert '不能杜撰热度' in prompt
        return {'items':[
            {'keyword':'临床专硕 缺失数据','reason':'检索数据整理问题','angle':'先检查缺失原因','comment_keywords':['怎么办'],'heat':999999,'evidence':[{'title':'模型虚构'}]},
            {'keyword':'临床专硕 研究设计','reason':'检索设计问题','angle':'病例资料能研究什么'},
        ]}, {'total_tokens':100}
    async def request(method,path,body,**kwargs):
        calls.append(body)
        assert body['filters']['publish_time']=='一周内'
        if '缺失' in body['keyword']:
            return {'feeds':[{'id':'a'*24,'noteCard':{'displayTitle':'缺失数据怎么整理','interactInfo':{'commentCount':'12','likedCount':'1.2万'}}},
                             {'id':'c'*24,'noteCard':{'displayTitle':'MySQL消费数据项目','interactInfo':{'commentCount':'9999'}}},
                             {'id':'a'*24,'noteCard':{'displayTitle':'重复笔记'}}, {'id':'bad','noteCard':{'displayTitle':'无效条目'}}]}
        return {'feeds':[{'id':'b'*24,'noteCard':{'displayTitle':'研究设计疑问','interactInfo':{'likedCount':'8'}}}]}
    monkeypatch.setattr(ai,'complete',complete);monkeypatch.setattr(xhs,'request',request)
    result=await topics.recommend({'audience_id':'M01','content_type':'A'})
    assert len(calls)==2
    one,two=result['items']
    assert one['sample_count']==2 and one['related_count']==1 and one['discussion_count']==12
    assert one['evidence'][0]['likes']==12000 and one['evidence'][0]['collections'] is None
    assert two['discussion_count'] is None
    assert all('heat' not in x for x in result['items'])
    assert '模型虚构' not in str(result)
    assert 'MySQL' not in str(result) and one['relevance_method']=='AI标题初筛'
    with Session() as s:assert not list(s.scalars(select(Source)))


@pytest.mark.asyncio
async def test_ai_and_search_failure_keeps_usable_prompt_suggestions(monkeypatch):
    calls=[]
    async def unavailable(*args,**kwargs):raise ai.ModelError('模型连接失败')
    async def failed(*args,**kwargs):calls.append(1);raise xhs.ConnectorError('需要验证')
    monkeypatch.setattr(ai,'complete',unavailable);monkeypatch.setattr(xhs,'request',failed)
    result=await topics.recommend({'audience_id':'M07','content_type':'C'})
    assert calls==[1] and len(result['warnings'])==2
    assert len(result['items'])==4 and all(not i['evidence'] for i in result['items'])
    assert all(i['discussion_count'] is None for i in result['items'])
    assert result['items'][0]['status']=='未核实 · 检索未完成'
    assert '质性' in str(result)


@pytest.mark.asyncio
async def test_recommendation_worker_persists_results(client,monkeypatch):
    job=client.post('/api/discovery/topics',json={'audience_id':'B05','content_type':'C'}).json()
    async def recommend(payload):
        with Session() as s:result=topics.defaults(s.get(Audience,payload['audience_id']),payload['content_type'])
        return {**result,'generated_at':now()}
    monkeypatch.setitem(worker.HANDLERS,'recommend_topics',recommend)
    assert await worker.process_one()
    data=client.get('/api/discovery/topics?audience_id=B05&content_type=C').json()
    assert data['recommendation']['generated_at'] and not data['active_job']
    with Session() as s:assert s.get(Job,job['id']).state=='completed'


def test_relevance_fallback_rejects_obvious_off_topic_titles():
    samples=[{'id':'a','title':'MySQL病例数据可视化研究'},
             {'id':'b','title':'执医考试病例刷题秒杀'},
             {'id':'c','title':'临床缺失数据整理怎么做'}]
    assert topics.lexical_relevance(samples,'临床专硕 缺失数据')=={'c'}
