import { ArrowUpRight, Check, CircleHelp } from 'lucide-react';

type Destination = 'overview'|'sources'|'audiences'|'drafts'|'reports'|'jobs'|'settings';
type Props = { onNavigate: (page: Destination) => void };

const sections: { page: Destination; title: string; purpose: string; action: string }[] = [
  { page: 'overview', title: '工作概览', purpose: '查看素材、分析、待审核稿件和最近任务，了解当前进度。', action: '每天打开工作台，先看看有哪些稿件等你审核、哪些任务需要处理。' },
  { page: 'sources', title: '用户需求', purpose: '保存学生原话、笔记和评论，整理目标人群、研究阶段和具体困难。', action: '导入真实问题，或搜索并选择笔记读取评论，再让AI分析。' },
  { page: 'audiences', title: '人群与提示词', purpose: '查看已沉淀的32类人群和96条内容提示词。', action: '找到对应专业与培养阶段，选择具体问题解答、判断与避坑、过程与案例。人群需求假设要用实际反馈验证。' },
  { page: 'drafts', title: '内容与审稿', purpose: '生成、修改和审核正文与图卡，批准具体版本的预约发布。', action: '打开候选稿，检查每张图和专业内容；修改后保存，再核对账号与时间。' },
  { page: 'reports', title: '分析与复盘', purpose: '查看采集样本中的人群与任务分布，生成有来源依据的AI复盘。', action: '选择时间范围，查看问题分布和下一轮建议。有素材后才能生成报告。' },
  { page: 'jobs', title: '任务与发布', purpose: '跟踪采集、分析、生成和发布任务，核对平台实际结果。', action: '任务提交后到这里看进度；发布显示已提交时，去平台后台核对，再保存核对结果。' },
  { page: 'settings', title: '连接与设置', purpose: '管理模型、小红书登录账号，以及每天生成候选稿的时间。', action: '首次先测试模型；需要小红书采集或发布时，扫码登录并核验账号。' },
];

export default function UsageGuide({ onNavigate }: Props) {
  const go = (page: Destination) => { onNavigate(page); window.scrollTo({ top: 0 }); };
  return <div className="usage-guide">
    <div className="page-head"><div><div className="eyebrow">GETTING STARTED / USER GUIDE</div><h1>使用说明</h1><p>从学生的一句话，走到一篇经过审核的文章。第一次使用，建议先走一遍手动导入流程。</p></div></div>

    <section className="panel guide-intro">
      <h2>先理解这条主线</h2>
      <p><strong>「用户需求」发现值得写的问题，「内容与审稿」把问题变成文章，「分析与复盘」帮助你决定下一步写什么。</strong></p>
      <ol className="guide-flow" aria-label="运营工作流程">
        {['收集学生原话', 'AI整理需求', '选人群与主题', '生成正文图卡', '人工审核预约', '核对结果与复盘'].map((text, i) => <li key={text}><span>{String(i + 1).padStart(2, '0')}</span>{text}</li>)}
      </ol>
    </section>

    <section className="panel">
      <div className="panel-head"><div><h2>第一次怎么用</h2><p>先用你已经听学生问过的三到五个问题，体验从需求到待审稿的过程。</p></div></div>
      <ol className="guide-instructions">
        <li><strong>确认模型可用。</strong>进入「连接与设置」，点击「测试连接」。模型分析和生成会调用已配置的外部服务。</li>
        <li><strong>导入原话。</strong>进入「用户需求」，点击「导入素材」，粘贴已去除身份和患者信息的问题，多条用空行分隔。</li>
        <li><strong>让AI整理。</strong>勾选素材，点击「分析选中素材」。进入「任务与发布」等待完成，再回「用户需求」查看分类、总结和判断依据。</li>
        <li><strong>根据问题生成文章。</strong>选中值得回应的素材，点击「据此生成内容」，手动确认目标人群、内容类型和主题，再点击「生成待审稿」。</li>
        <li><strong>检查生成结果。</strong>任务完成后，进入「内容与审稿」，打开稿件，检查正文和全部图卡。首次可以停在待审稿这一步。</li>
      </ol>
      <div className="actions"><button className="primary" onClick={() => go('sources')}>去导入第一条需求 <ArrowUpRight size={16}/></button><button className="secondary" onClick={() => go('settings')}>检查模型连接</button></div>
    </section>

    <section className="panel guide-needs">
      <div className="panel-head"><div><h2>「用户需求」到底用来干什么</h2><p>把它当作收集学生原话的运营笔记本，积累选题和服务改进的依据。</p></div></div>
      <div className="guide-example">
        <span className="code-label">教学示例 · 非真实客户记录</span>
        <blockquote>“我是临床专硕，病例已经收集了，但是有很多缺失值，不知道还能不能做。”</blockquote>
        <dl><div><dt>目标人群</dt><dd>临床专硕；依据是原话中的身份自述。</dd></div><div><dt>具体困难</dt><dd>已有资料，卡在数据整理和研究可行性判断。</dd></div><div><dt>可转化的选题</dt><dd>《病例资料缺失很多，开始分析前先检查这几件事》</dd></div><div><dt>后续怎么用</dt><dd>选择这条素材，生成面向临床专硕的“具体问题解答”，再人工审核。</dd></div></dl>
      </div>
      <div className="guide-two-columns">
        <div><h3>方式一：导入已有问题</h3><p>适合整理已有咨询、访谈笔记或公开讨论。点击「导入素材」，可粘贴文字或选择TXT、JSON、CSV文件。JSON对象使用text字段；CSV至少包含text列，可附title、url列。</p><p>系统会去重并保留原文。导入后需要发起分析，才能得到人群与问题标签。</p></div>
        <div><h3>方式二：从小红书寻找问题</h3><p>先在设置扫码登录并核验账号。在“从小红书发现问题”选择目标人群和内容类型，先使用提示词建议的搜索词。点击「AI 推荐近期话题」，AI会结合对应提示词生成搜索方向，再检索近一周的笔记。检索后由AI按标题初筛相关性，排除明显无关笔记，再展示相关样本讨论情况、来源和适合承接的文章主题，点击「搜这个问题」即可开始采集；也可填入搜索框自行修改。采集完成后，选择相关笔记，点击「读取正文与评论」，再分析读到的素材。</p><p>推荐中的“读评论时留意”是待观察的求助表达，并未替你识别评论。话题推荐不会自动导入素材；点击搜索、再读取正文与评论后才能分析。样本讨论情况不代表全站热榜或搜索量，超过24小时建议刷新。可从「人群与提示词」点击“查看相关话题与搜索词”带入人群，也能用推荐主题创建待审稿。搜索先收集笔记标题，正文与评论需进一步读取。目前每次搜索最多10篇，单篇最多加载30条一级评论，实际可能更少。</p></div>
      </div>
      <div className="notice"><CircleHelp size={17}/><span>AI的人群判断需要原文依据。“SPSS怎么用”只能说明工具问题，身份应保留未知。评论可作为需求线索；是否愿意购买服务，需要后续主动咨询来确认。</span></div>
    </section>

    <section className="panel">
      <div className="panel-head"><div><h2>每个板块怎么用</h2><p>点击“前往板块”，可以直接进入对应页面。</p></div></div>
      <div className="guide-sections">{sections.map(item => <article key={item.page} className="guide-section-row"><div><h3>{item.title}</h3><p>{item.purpose}</p><p className="guide-action"><Check size={14}/><span>{item.action}</span></p></div><button className="text-btn" aria-label={'前往'+item.title} onClick={() => go(item.page)}>前往板块 <ArrowUpRight size={15}/></button></article>)}</div>
    </section>

    <section className="panel">
      <div className="panel-head"><div><h2>从待审稿到定时发布</h2><p>每一次批准，都绑定具体稿件版本、账号和时间。</p></div></div>
      <ol className="guide-instructions">
        <li><strong>登录并核验账号。</strong>在「连接与设置」获取二维码，用小红书App扫码，完成后点击「核验账号」。账号核验超过12小时需要重新核验。</li>
        <li><strong>修改后先保存。</strong>在「内容与审稿」检查标题、正文、话题和每张图。图卡预览显示已保存版本；修改后点击「保存修改」，再检查预览。</li>
        <li><strong>确认发布方式。</strong>可以选择“立即发布”，或选择你希望的北京时间。核对账号、勾选审核确认后，点击批准按钮。时间不受工作台限制；适合平台预约的任务提前提交，其他任务由本地队列等到时间后提交。</li>
        <li><strong>核对平台后台。</strong>在「任务与发布」查看提交结果，再到小红书创作后台确认预约或公开发布状态，点击「核对结果」保存记录。</li>
      </ol>
      <p className="guide-note">“等待定时提交”的任务需要电脑和后台运行，可在执行前取消。电脑休眠或停止期间不会执行，恢复运行后已到时间的待提交任务会继续提交。修改待执行稿件会使原审批失效；取消本地任务不会取消平台已有预约。</p>
    </section>

    <section className="panel guide-faq">
      <div className="panel-head"><h2>常见问题</h2></div>
      <details><summary>还没有真实需求素材，可以先生成文章吗？</summary><p>可以。在「人群与提示词」找到目标人群，点击「创建内容」。没有选中素材时，文章基于人群需求假设生成，案例应标明为教学示例。发布前仍需核对专业内容。</p></details>
      <details><summary>点击分析、采集或生成后，在哪里看结果？</summary><p>先到「任务与发布」看状态。分析完成后回「用户需求」，生成完成后到「内容与审稿」，复盘完成后到「分析与复盘」。任务显示未完成时，查看说明并处理原因，再重新发起。</p></details>
      <details><summary>怎么切换小红书账号？</summary><p>进入「连接与设置」，点击「切换账号」。工作台退出当前登录后会显示新二维码。先在手机小红书App切换到目标账号，再扫码，最后点击「核验账号」确认名称与账号标识。此操作会让尚未提交的发布任务退回待审核，新账号发布前需重新核对并批准；已经提交或结果不明的记录仍保留，平台上的预约需在对应账号后台处理。</p><p>可以先点击“检查发布连接”，工作台会打开真实创作者后台确认是否可用；此检查不会上传或发布。若明确提示创作者后台未登录，请完成登录后再重试。</p></details>
      <details><summary>每天自动生成一篇，会直接发出去吗？</summary><p>每天生成的内容进入待审稿。在「连接与设置」开启“每日候选稿”、选择北京时间、人群和内容类型，再保存计划。每次发布仍需人工审核批准。</p></details>
      <details><summary>关掉页面或让电脑休眠，会有什么影响？</summary><p>只关闭页面，后台仍运行时可以继续执行。电脑休眠或停止工作台后，本地采集、生成和提交会暂停；错过的每日生成时间不会补跑。已成功进入平台预约队列的内容由平台按时间执行。</p></details>
      <details><summary>为什么“已提交”还要核对？结果不明怎么办？</summary><p>工具返回提交成功，只能说明一次提交操作完成，仍需确认平台是否接受预约或公开发布。结果不明时先查平台后台，系统不会自动重复发布；确认后在「任务与发布」保存实际状态。</p></details>
      <details><summary>“未提交 · 可重试”和“结果不明”有什么区别？</summary><p>明确的发布前校验失败会显示“未提交 · 可重试”，可查看原因并点击“重试发布”，选择现在补发或保留原时间。连接中断或发布过程超时无法判断是否成功，会显示“结果不明”；请先核对平台后台，避免重复发布。</p></details>
      <details><summary>分析报告能说明哪些人群更愿意付费吗？</summary><p>当前报告总结已导入或采集样本的分布和问题。曝光、阅读、有效咨询、成交数据尚未接入；提问频次也不等于付费意愿。报告中的建议应通过实际运营继续验证。</p></details>
      <details><summary>哪些资料适合导入？</summary><p>导入与你的运营问题有关、可用于分析的必要文本，移除身份和患者信息。需求与稿件保存在本机，AI处理时会发送必要文本至已配置的模型服务。真实案例发布前应取得授权并去标识化。</p></details>
    </section>
  </div>;
}
