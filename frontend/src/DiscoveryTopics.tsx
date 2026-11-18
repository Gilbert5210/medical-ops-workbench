import { useEffect, useState } from 'react';
import { ArrowUpRight, ChevronRight, LoaderCircle, Search, Sparkles } from 'lucide-react';
type Row = Record<string, any>;
type Props = {audiences:Row[];audience:string;contentType:string;onAudience:(id:string)=>void;onType:(id:string)=>void;api:(path:string,method?:string,body?:any)=>Promise<any>;onSearch:(keyword:string)=>void;onFill:(keyword:string)=>void;onDraft:(audience:string,type:string,topic:string)=>void;onPrompts:(id:string)=>void;busy:boolean};
const types={A:'具体问题解答',B:'判断与避坑',C:'过程与案例'};
const time=(v:string)=>new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Shanghai',hour12:false}).format(new Date(v));
const count=(n:number|null)=>n===null||n===undefined?'未提供':n.toLocaleString('zh-CN');
export default function DiscoveryTopics(p:Props){
 const [data,setData]=useState<Row|null>(null),[error,setError]=useState(''),[submitting,setSubmitting]=useState(false),[revision,setRevision]=useState(0);
 const query='/discovery/topics?audience_id='+encodeURIComponent(p.audience)+'&content_type='+p.contentType;
 useEffect(()=>{let cancelled=false,inFlight=false;setData(null);setError('');async function load(){if(inFlight)return;inFlight=true;try{const d=await p.api(query);if(!cancelled){setData(d);setError('');}}catch(e:any){if(!cancelled)setError(e.message);}finally{inFlight=false;}}load();const timer=setInterval(load,5000);return()=>{cancelled=true;clearInterval(timer);};},[query,revision]);
 async function refresh(){setSubmitting(true);setError('');try{await p.api('/discovery/topics','POST',{audience_id:p.audience,content_type:p.contentType});setRevision(v=>v+1);}catch(e:any){setError(e.message);}finally{setSubmitting(false);}}
 const rec=data?.recommendation,working=submitting||!!data?.active_job;
 return <div className="discovery-topics">
 <div className="discovery-intro"><div><span className="code-label">从人群出发 / 找到值得回答的问题</span><h3>不知道搜什么？先选你想了解的人群。</h3><p>关联现有32类人群与96条提示词，先给搜索起点，再用近期笔记验证。</p></div><button className="text-btn" onClick={()=>p.onPrompts(p.audience)}>查看对应提示词 <ChevronRight size={15}/></button></div>
 <div className="discovery-controls"><label>想了解的人群<select aria-label="推荐目标人群" value={p.audience} disabled={submitting} onChange={e=>p.onAudience(e.target.value)}>{p.audiences.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>想做的内容<select aria-label="推荐内容类型" value={p.contentType} disabled={submitting} onChange={e=>p.onType(e.target.value)}>{Object.entries(types).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><button className="primary" disabled={working} onClick={refresh}>{working?<LoaderCircle size={16} className="spin"/>:<Sparkles size={16}/>} {working?'正在整理推荐…':'AI 推荐近期话题'}</button></div>
 {working&&<p className="discovery-progress" role="status">{data?.active_job?.state==='pending'?'任务已排队，其他任务结束后开始。':'AI 正在结合提示词生成搜索词、检索近一周的笔记，并筛选相关标题。'}完成后这里会自动更新，你也可以先使用下面的建议。</p>}
 {(error||data?.last_error)&&<p className="discovery-error" role="alert">{error||data?.last_error}</p>}
 {rec&&<><div className="discovery-context"><span>需求方向</span><p>{rec.need}</p><small>承接主题：{rec.topic}</small></div>
 <div className="discovery-result-head"><strong>{rec.generated_at?'近期话题与搜索建议':'先试试这些搜索词'}</strong><span>{rec.generated_at?'更新于 '+time(rec.generated_at)+' · 北京时间':'来自人群提示词 · 尚未检索热度'}{data?.stale?' · 已超过24小时，建议刷新':''}</span></div>
 <div className="topic-grid">{rec.items.map((item:Row,i:number)=><article className="topic-card" key={item.keyword}><div className="topic-meta"><span className="code-label">{String(i+1).padStart(2,'0')} / {item.origin==='ai'?'AI 推荐':'提示词建议'}</span><span className={'badge '+(item.sample_count?'completed':'')}>{item.status}</span></div><h3>{item.keyword}</h3><p className="topic-reason">{item.reason}</p>
 {item.checked_at&&<div className="topic-measured"><span>本次检索 {item.sample_count} 篇 · 初筛相关 {item.related_count??0} 篇</span><span>相关样本最高评论 {count(item.discussion_count)}</span></div>}
 <p className="topic-angle"><strong>可以写：</strong>{item.angle}</p>
 {item.comment_keywords?.length>0&&<div className="topic-words"><span>读评论时留意</span>{item.comment_keywords.map((w:string,i:number)=><span className="tag" key={i}>{w}</span>)}</div>}
 {item.evidence?.length>0&&<details className="topic-evidence"><summary>查看检索依据 · {item.evidence.length} 篇示例</summary>{item.evidence.map((n:Row)=><div className="topic-source" key={n.id}><a href={n.url} target="_blank" rel="noreferrer">{n.title}<ArrowUpRight size={13}/></a><small>评论 {count(n.comments)} · 点赞 {count(n.likes)} · 收藏 {count(n.collections)}</small></div>)}<small>检索于 {time(item.checked_at)} · 按近一周筛选返回 · {item.relevance_method}</small></details>}
 <div className="topic-actions"><button className="small-btn" disabled={p.busy} onClick={()=>p.onSearch(item.keyword)}><Search size={14}/>搜这个问题</button><button className="text-btn" onClick={()=>p.onFill(item.keyword)}>填入搜索框</button><button className="text-btn" onClick={()=>p.onDraft(p.audience,p.contentType,item.angle)}>用此选题创作</button></div></article>)}</div>
 {rec.warnings.map((w:string)=><p className="discovery-error" key={w}>{w}</p>)}<p className="discovery-scope">{rec.scope}</p></>}
 {!rec&&!error&&<p className="hint" role="status">正在读取该人群的推荐…</p>}
 </div>;
}
