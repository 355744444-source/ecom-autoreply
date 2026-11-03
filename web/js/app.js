/* ============================================================
   智回 · 电商自动回复工作台 — 前端逻辑
   ============================================================ */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const esc = (s) => String(s === null || s === undefined ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const icon = (n, cls = '') => `<svg class="ico ${cls}"><use href="#i-${n}"/></svg>`;

const TITLES = {
  dashboard: ['工作台', '今日自动回复概览与实时动态'],
  sessions: ['会话中心', '多平台买家对话，自动回复与人工接管同屏处理'],
  rules: ['自动回复规则', '关键词命中即自动回复，优先级从高到低依次匹配'],
  templates: ['话术库', '沉淀标准话术，支持变量一键插入'],
  tester: ['规则测试器', '输入买家原话，验证命中的规则与最终回复'],
  platforms: ['平台接入', '五个主流电商平台的授权与运行状态'],
  logs: ['运行日志', '每一条自动回复都可追溯'],
  settings: ['系统设置', '运行控制、发送策略与内容安全'],
};

const S = {
  view: 'dashboard',
  settings: {},
  platforms: [],
  rules: [],
  matchTypes: {},
  varHints: [],
  templates: [],
  tplCats: [],
  sessions: [],
  stats: { trend: [], top_rules: [] },
  recent: [],
  cursor: 0,
  active: null,
  messages: [],
  msgCount: -1,
  ruleKeyword: '',
  rulePlat: '',
  tplCat: '',
  tplKeyword: '',
  sessKeyword: '',
  sessFilter: 'all',
  logPage: 1,
  logSize: 20,
  logKeyword: '',
  logPlatform: '',
  logMode: '',
  dirty: false,
};

const AV_COLORS = ['#6366f1', '#0891b2', '#db2777', '#ea580c', '#059669', '#7c3aed', '#0284c7', '#b45309'];

function colorOf(str) {
  let h = 0;
  for (let i = 0; i < String(str).length; i++) h = (h * 31 + String(str).charCodeAt(i)) % 9973;
  return AV_COLORS[h % AV_COLORS.length];
}

function platOf(id) {
  return S.platforms.find(p => p.id === id) || { id, name: id, color: '#667085', short: '?' };
}

function todayStr() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 今天的显示 HH:MM，非今天显示 MM-DD */
function shortTime(ts) {
  if (!ts) return '';
  return ts.slice(0, 10) === todayStr() ? ts.slice(11, 16) : ts.slice(5, 10);
}

function platLogo(p, extra = '') {
  return `<div class="plat-logo ${extra}" style="background:${p.color}">${esc(p.short)}</div>`;
}

function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = icon(type === 'err' ? 'alert' : 'check') + `<span>${esc(msg)}</span>`;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(6px)'; }, 2600);
  setTimeout(() => el.remove(), 3000);
}

async function api(path, method = 'GET', body) {
  const opt = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const res = await fetch(path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) throw new Error(data.error || ('请求失败 ' + res.status));
  return data;
}

/* ============================ 启动 ============================ */
async function boot() {
  bindNav();
  bindGlobal();
  try {
    const b = await api('/api/bootstrap');
    S.settings = b.settings;
    S.platforms = b.platforms;
    S.rules = b.rules;
    S.stats = b.stats;
    await loadTemplates();
    await loadRecent();
    await loadSessions();
    fillLogPlatforms();
    renderAll();
    // 支持 ?view=xxx&sid=xxx 深链，便于刷新后停留在当前页面
    const qp = new URLSearchParams(location.search);
    const deep = qp.get('view');
    if (deep && TITLES[deep]) setView(deep);
    const sid = qp.get('sid');
    if (sid) openSession(sid);
    const q = qp.get('q');
    if (q) { setView('tester'); $('#testText').value = q; runTest(); }
    if (qp.get('new') === '1') { setView('rules'); openRuleDrawer(null); }
    startPolling();
  } catch (e) {
    toast('初始化失败：' + e.message, 'err');
    console.error(e);
  }
}

function renderAll() {
  renderSide();
  renderKpi();
  renderTrend();
  renderPlatList();
  renderRank();
  renderFeed();
  renderRuleTable();
  renderTemplates();
  renderSessList();
  renderPlatGrid();
  renderTestPlatforms();
  renderSettingsForm();
}

function fillLogPlatforms() {
  const sel = $('#logPlatform');
  if (!sel) return;
  sel.innerHTML = '<option value="">全部平台</option>' +
    S.platforms.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
}

/* ============================ 导航 ============================ */
function bindNav() {
  $$('.nav-item').forEach(el => {
    el.addEventListener('click', () => setView(el.dataset.view));
  });
  document.addEventListener('click', (e) => {
    const j = e.target.closest('[data-jump]');
    if (j) setView(j.dataset.jump);
  });
  $$('.view').forEach(v => { if (v.dataset.view === S.view) v.classList.add('is-active'); });
}

function setView(name) {
  if (!TITLES[name]) return;
  S.view = name;
  document.body.classList.toggle('view-chat', name === 'sessions');
  $$('.nav-item').forEach(el => el.classList.toggle('is-active', el.dataset.view === name));
  $$('.view').forEach(el => el.classList.toggle('is-active', el.dataset.view === name));
  $('#pageTitle').textContent = TITLES[name][0];
  $('#pageSub').textContent = TITLES[name][1];
  $('.content').scrollTop = 0;
  if (name === 'logs') loadLogs(1);
  if (name === 'templates') renderTemplates();
  if (name === 'platforms') renderPlatGrid();
  if (name === 'settings') renderSettingsForm();
  if (name === 'sessions') { renderSessList(); renderChatSide(); }
}

/* ============================ 全局开关 ============================ */
function bindGlobal() {
  $('#sideSwitch').addEventListener('click', toggleGlobal);
  $('#btnSimulate').addEventListener('click', simulate);
  $('#btnNewRuleTop').addEventListener('click', () => { setView('rules'); openRuleDrawer(null); });
  $('#btnNewRule').addEventListener('click', () => openRuleDrawer(null));
  $('#btnRuleTest').addEventListener('click', () => setView('tester'));
  $('#btnRunTest').addEventListener('click', runTest);
  $('#drawerClose').addEventListener('click', closeDrawer);
  $('#drawerCancel').addEventListener('click', closeDrawer);
  $('#drawerMask').addEventListener('click', closeDrawer);
  $('#drawerSave').addEventListener('click', saveRule);
  $('#modalMask').addEventListener('click', (e) => { if (e.target.id === 'modalMask') closeModal(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeDrawer(); closeModal(); }
  });

  $('#btnNewTpl').addEventListener('click', () => openTplModal(null));
  $('#tplSearch').addEventListener('input', (e) => { S.tplKeyword = e.target.value.trim(); renderTemplates(); });
  $('#ruleSearch').addEventListener('input', (e) => { S.ruleKeyword = e.target.value.trim(); renderRuleTable(); });
  $('#sessSearch').addEventListener('input', (e) => { S.sessKeyword = e.target.value.trim(); renderSessList(); });
  $('#btnExport').addEventListener('click', () => { window.location.href = '/api/logs/export.csv'; });
  $('#btnClearLogs').addEventListener('click', clearLogs);
  $('#btnWipe').addEventListener('click', clearLogs);
  $('#btnReset').addEventListener('click', resetSessions);
  $('#btnSaveSettings').addEventListener('click', saveSettings);
  $('#settings')?.addEventListener?.('input', markDirty);
  $$('#settings input, #settings textarea, #settings select').forEach(el => {
    el.addEventListener('input', markDirty);
    el.addEventListener('change', markDirty);
  });
  $('#logSearch').addEventListener('input', debounce((e) => { S.logKeyword = e.target.value.trim(); loadLogs(1); }, 350));
  $('#logPlatform').addEventListener('change', (e) => { S.logPlatform = e.target.value; loadLogs(1); });
  $('#logMode').addEventListener('change', (e) => { S.logMode = e.target.value; loadLogs(1); });

  $$('#sessFilter .chip').forEach(c => c.addEventListener('click', () => {
    S.sessFilter = c.dataset.f;
    $$('#sessFilter .chip').forEach(x => x.classList.toggle('is-on', x === c));
    renderSessList();
  }));
}

function markDirty() {
  S.dirty = true;
  const h = $('#saveHint');
  h.textContent = '有未保存的修改';
  h.classList.add('dirty');
}

async function toggleGlobal() {
  const next = !S.settings.global_enabled;
  try {
    const r = await api('/api/settings', 'POST', { global_enabled: next });
    S.settings = r.settings;
    renderSide();
    toast(next ? '自动回复已开启' : '自动回复已暂停');
  } catch (e) { toast(e.message, 'err'); }
}

async function simulate() {
  const btn = $('#btnSimulate');
  btn.disabled = true;
  try {
    const r = await api('/api/simulate', 'POST', {});
    if (!r.ok) { toast(r.reason || '模拟失败', 'err'); return; }
    if (r.replied) toast(`已命中「${r.rule}」，自动回复已发送`, 'ok');
    else toast(r.reason || '消息已收到，未触发自动回复');
    await refreshFeed();
    if (S.active && r.session_id === S.active.id) loadMessages(S.active.id, true);
  } catch (e) { toast(e.message, 'err'); }
  finally { btn.disabled = false; }
}

/* ============================ 轮询 ============================ */
let pollTimer = null;
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(refreshFeed, 3000);
}

async function refreshFeed() {
  try {
    const r = await api('/api/feed?since=' + S.cursor);
    S.cursor = r.cursor || S.cursor;
    if (r.logs && r.logs.length) {
      S.recent = r.logs.slice().reverse().concat(S.recent).slice(0, 30);
    }
    S.sessions = r.sessions || S.sessions;
    S.stats = r.stats || S.stats;
    renderSide();
    if (S.view === 'dashboard') { renderKpi(); renderTrend(); renderRank(); renderFeed(); renderPlatList(); }
    if (S.view === 'sessions') {
      renderSessList();
      if (S.active) loadMessages(S.active.id, true);
    }
    if (S.view === 'logs' && r.logs && r.logs.length) loadLogs(S.logPage, true);
  } catch (e) { /* 断线静默重试 */ }
}

/* ============================ 侧边栏 ============================ */
function renderSide() {
  const on = !!S.settings.global_enabled;
  $('#sideSwitch').classList.toggle('on', on);
  $('#sideDot').classList.toggle('off', !on);
  $('#sideShop').textContent = S.settings.shop_name || '未命名店铺';
  $('#sideState').textContent = on ? '运行中' : '已暂停';
  $('#sideState').classList.toggle('off', !on);
  const pill = $('#livePill');
  pill.classList.toggle('paused', !on);
  pill.innerHTML = `<i></i>${on ? '实时监听中' : '已暂停'}`;
  const unread = (S.sessions || []).reduce((a, s) => a + (s.unread || 0), 0);
  const n = $('#navUnread');
  n.textContent = unread > 99 ? '99+' : unread;
  n.dataset.zero = unread ? '0' : '1';
}

/* ============================ 工作台 ============================ */
function renderKpi() {
  const st = S.stats || {};
  const cards = [
    { label: '今日接待会话', value: st.sessions_today || 0, unit: '个', ic: 'chat', cls: '',
      foot: `买家消息 <b>${st.buyer_msgs || 0}</b> 条` },
    { label: '自动回复', value: st.auto_replies || 0, unit: '条', ic: 'zap', cls: 'green',
      foot: `命中率 <b>${st.hit_rate || 0}%</b>` },
    { label: '平均响应耗时', value: st.avg_latency || 0, unit: 'ms', ic: 'clock', cls: 'blue',
      foot: `生效规则 <b>${st.active_rules || 0}</b> 条` },
    { label: '待人工跟进', value: st.human_takeover || 0, unit: '个', ic: 'users', cls: 'amber',
      foot: `拦截 <b>${st.blocked || 0}</b> · 未命中 <b>${st.no_match || 0}</b>` },
  ];
  $('#kpiGrid').innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="kpi-top">
        <span class="kpi-label">${c.label}</span>
        <span class="kpi-icon ${c.cls}">${icon(c.ic)}</span>
      </div>
      <div class="kpi-value">${c.value}<small>${c.unit}</small></div>
      <div class="kpi-foot">${c.foot}</div>
    </div>`).join('');
}

function renderTrend() {
  const t = (S.stats && S.stats.trend) || [];
  if (!t.length) { $('#trendChart').innerHTML = '<div class="empty sm"><p>暂无数据</p></div>'; return; }
  const max = Math.max(1, ...t.map(d => Math.max(d.buyer || 0, d.auto || 0)));
  const H = 152, W = 700, slot = W / t.length, bw = 11, gap = 5;
  const bars = t.map((d, i) => {
    const cx = slot * i + slot / 2;
    const x1 = (cx - gap / 2 - bw).toFixed(1);
    const x2 = (cx + gap / 2).toFixed(1);
    let s = '';
    if ((d.buyer || 0) > 0) {
      const hb = Math.max(3, Math.round(d.buyer / max * (H - 16)));
      s += `<rect x="${x1}" y="${H - hb}" width="${bw}" height="${hb}" rx="3" fill="#dfe4f6"><title>买家消息 ${d.buyer} 条</title></rect>`;
    }
    if ((d.auto || 0) > 0) {
      const ha = Math.max(3, Math.round(d.auto / max * (H - 16)));
      s += `<rect x="${x2}" y="${H - ha}" width="${bw}" height="${ha}" rx="3" fill="url(#gradAuto)"><title>自动回复 ${d.auto} 条</title></rect>`;
    }
    return s;
  }).join('');
  const today = t[t.length - 1] || { buyer: 0, auto: 0 };
  const rate = today.buyer ? Math.round(today.auto / today.buyer * 100) : 0;
  $('#trendChart').innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="gradAuto" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#6d6cf5"/><stop offset="100%" stop-color="#4338ca"/>
        </linearGradient>
      </defs>
      <line x1="0" y1="${H - 1}" x2="${W}" y2="${H - 1}" stroke="#e7e9ef" stroke-width="1"/>
      ${bars}
    </svg>
    <div class="chart-axis">
      ${t.map((d, i) => `<span class="${i === t.length - 1 ? 'today' : ''}">${esc(d.day)}</span>`).join('')}
    </div>
    <div class="chart-foot">
      今日买家消息 <b>${today.buyer || 0}</b> 条 · 自动回复 <b>${today.auto || 0}</b> 条 · 命中率 <b>${rate}%</b>
    </div>`;
}

function renderPlatList() {
  const counts = {};
  (S.sessions || []).forEach(s => { counts[s.platform] = (counts[s.platform] || 0) + 1; });
  $('#platList').innerHTML = S.platforms.map(p => {
    const on = !!p.enabled;
    const today = (p.today_sessions !== undefined && p.today_sessions !== null) ? p.today_sessions : (counts[p.id] || 0);
    return `
      <div class="plat-row">
        ${platLogo(p)}
        <div>
          <div class="plat-name">${esc(p.name)}</div>
          <div class="plat-meta">${on ? (p.mode === 'demo' ? '演示模式' : '官方接口') : '未启用'}</div>
        </div>
        <div class="plat-right">
          <div class="plat-count">${today}</div>
          <div class="plat-state ${on ? '' : 'off'}">${on ? '在线' : '离线'}</div>
        </div>
      </div>`;
  }).join('');
}

function renderRank() {
  const list = (S.stats && S.stats.top_rules) || [];
  if (!list.length) {
    $('#rankList').innerHTML = '<div class="empty sm"><p>暂无命中记录</p></div>';
    return;
  }
  const max = Math.max(1, ...list.map(r => r.hits || 0));
  $('#rankList').innerHTML = list.map((r, i) => `
    <div class="rank-item">
      <span class="rank-no ${i < 3 ? 'top' : ''}">${String(i + 1).padStart(2, '0')}</span>
      <div class="rank-body">
        <div class="rank-name-row"><b>${esc(r.name)}</b><span>${r.hits} 次</span></div>
        <div class="rank-track"><div class="rank-fill" style="width:${Math.max(4, r.hits / max * 100)}%"></div></div>
      </div>
    </div>`).join('');
}

function renderFeed() {
  const list = (S.recent || []).slice(0, 8);
  if (!list.length) {
    $('#liveFeed').innerHTML = '<div class="empty sm"><p>还没有自动回复记录</p></div>';
    return;
  }
  $('#liveFeed').innerHTML = list.map(l => {
    const ok = l.mode === 'auto';
    return `
      <div class="feed-item">
        <div class="feed-dot ${ok ? 'ok' : 'warn'}">${icon(ok ? 'check' : 'alert')}</div>
        <div class="feed-body">
          <div class="feed-q"><span>${esc(l.buyer)}</span>${esc(l.question)}</div>
          <div class="feed-a">${ok ? esc(l.reply.split('\n')[0]) : esc(l.mode === 'blocked' ? '敏感词拦截，未发送' : '未命中规则')}</div>
        </div>
        <div class="feed-time">${esc(shortTime(l.ts))}</div>
      </div>`;
  }).join('');
}

/* ============================ 会话中心 ============================ */
async function loadSessions() {
  try {
    const r = await api('/api/sessions');
    S.sessions = r.items || [];
    renderSessList();
  } catch (e) { /* ignore */ }
}

function filteredSessions() {
  const kw = S.sessKeyword.toLowerCase();
  return (S.sessions || []).filter(s => {
    if (S.sessFilter === 'unread' && !s.unread) return false;
    if (S.sessFilter === 'human' && s.status !== 'human') return false;
    if (S.sessFilter === 'auto' && s.status === 'human') return false;
    if (kw && !((s.buyer || '').toLowerCase().includes(kw) || (s.product || '').toLowerCase().includes(kw))) return false;
    return true;
  });
}

function renderSessList() {
  const list = filteredSessions();
  if (!list.length) {
    $('#sessList').innerHTML = `<div class="empty sm">${icon('inbox')}<p>暂无会话</p></div>`;
    return;
  }
  $('#sessList').innerHTML = list.map(s => {
    const p = platOf(s.platform);
    const active = S.active && S.active.id === s.id;
    return `
      <div class="sess-item ${active ? 'is-on' : ''}" data-sid="${esc(s.id)}">
        <div class="avatar" style="background:${colorOf(s.buyer)}">
          ${esc((s.buyer || '?').slice(0, 1))}
          <span class="plat-badge" style="background:${p.color}">${esc(p.short)}</span>
        </div>
        <div class="sess-body">
          <div class="sess-top">
            <span class="sess-name">${esc(s.buyer)}</span>
            ${s.unread ? '<span class="unread-dot"></span>' : ''}
            <span class="sess-time">${esc((s.last_time || '').slice(11, 16))}</span>
          </div>
          <div class="sess-last">${esc(s.last_message || '（暂无消息）')}</div>
          <div class="sess-flags">
            <span class="tag ${s.status === 'human' ? 'human' : 'ok'}">${s.status === 'human' ? '人工跟进' : '自动接待'}</span>
            <span class="sess-plat">${esc(p.name)}</span>
          </div>
        </div>
      </div>`;
  }).join('');
  $$('#sessList .sess-item').forEach(el => {
    el.addEventListener('click', () => openSession(el.dataset.sid));
  });
}

async function openSession(id) {
  const s = (S.sessions || []).find(x => x.id === id);
  if (!s) return;
  S.active = s;
  S.msgCount = -1;
  renderSessList();
  await loadMessages(id, true);
  renderChatSide();
}

async function loadMessages(id, force) {
  try {
    const r = await api(`/api/sessions/${id}/messages`);
    const items = r.items || [];
    const first = S.msgCount === -1;
    const changed = items.length !== S.msgCount;
    S.messages = items;
    S.msgCount = items.length;
    if (!S.active || S.active.id !== id) return;

    if (first || !document.getElementById('msgs')) {
      renderChat();
      scrollChat();
    } else if (changed) {
      // 只替换消息区，保留正在输入的回复内容
      const box = document.getElementById('msgs');
      box.innerHTML = items.length
        ? items.map(m => bubble(m, S.active)).join('')
        : '<div class="empty sm"><p>还没有消息</p></div>';
      scrollChat();
    }
    const s = (S.sessions || []).find(x => x.id === id);
    if (s && s.unread) { s.unread = 0; renderSide(); }
  } catch (e) { /* ignore */ }
}

function renderChat() {
  const s = S.active;
  if (!s) return;
  const p = platOf(s.platform);
  const msgs = S.messages || [];
  const html = `
    <div class="chat-head">
      <div class="avatar" style="background:${colorOf(s.buyer)}">${esc((s.buyer || '?').slice(0, 1))}</div>
      <div class="chat-head-info">
        <div class="chat-head-name">${esc(s.buyer)}
          <span class="tag" style="background:${p.color}1a;color:${p.color};border:1px solid ${p.color}33">${esc(p.name)}</span>
          <span class="tag ${s.status === 'human' ? 'human' : 'ok'}">${s.status === 'human' ? '人工跟进中' : '自动接待中'}</span>
        </div>
        <div class="chat-head-sub">${esc(s.product || '—')} · 订单 ${esc(s.order_no || '—')}</div>
      </div>
      <div class="chat-head-actions">
        <button class="btn btn-ghost sm" id="btnTakeover">${icon('users', 'sm')}${s.status === 'human' ? '恢复自动' : '转人工'}</button>
      </div>
    </div>
    <div class="msgs" id="msgs">${msgs.length ? msgs.map(m => bubble(m, s)).join('') : '<div class="empty sm"><p>还没有消息</p></div>'}</div>
    <div class="composer">
      <div class="composer-tools" id="quickTools"></div>
      <div class="composer-box">
        <textarea id="replyText" placeholder="输入回复内容，Enter 发送 / Shift+Enter 换行"></textarea>
      </div>
      <div class="composer-foot">
        <span class="composer-hint">人工回复后该会话将静默自动回复，交由你继续跟进</span>
        <button class="btn btn-primary sm" id="btnSend">${icon('send', 'sm')}发送</button>
      </div>
    </div>`;
  $('#chatMain').innerHTML = html;

  $('#btnTakeover').addEventListener('click', async () => {
    const next = s.status === 'human' ? 'auto' : 'human';
    await api(`/api/sessions/${s.id}/status`, 'POST', { status: next });
    s.status = next;
    renderChat();
    renderSessList();
    toast(next === 'human' ? '已转人工，自动回复暂停' : '已恢复自动接待');
  });

  $('#btnSend').addEventListener('click', sendReply);
  $('#replyText').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply(); }
  });

  const quick = (S.templates || []).slice(0, 5);
  $('#quickTools').innerHTML = quick.map(t =>
    `<button class="chip" data-tpl="${esc(t.content)}">${esc(t.title)}</button>`).join('');
  $$('#quickTools .chip').forEach(b => b.addEventListener('click', () => {
    const ta = $('#replyText');
    ta.value = (ta.value ? ta.value + '\n' : '') + b.dataset.tpl;
    ta.focus();
  }));
}

function bubble(m, s) {
  const me = m.role === 'agent';
  const srcCls = m.source === 'manual' ? 'manual' : 'auto';
  const srcTxt = m.source === 'manual' ? '人工' : '自动';
  return `
    <div class="msg ${me ? 'me' : ''}">
      <div class="msg-av" style="background:${me ? '#4f46e5' : colorOf(s.buyer)}">${me ? '我' : esc((s.buyer || '?').slice(0, 1))}</div>
      <div class="msg-col">
        <div class="msg-bubble">${esc(m.content)}</div>
        <div class="msg-meta">
          <span>${esc((m.ts || '').slice(11, 16))}</span>
          ${me ? `<span class="msg-src ${srcCls}">${srcTxt}</span>` : ''}
        </div>
      </div>
    </div>`;
}

function scrollChat() {
  const el = $('#msgs');
  if (el) el.scrollTop = el.scrollHeight;
}

async function sendReply() {
  const ta = $('#replyText');
  const text = (ta.value || '').trim();
  if (!text) { toast('请输入回复内容'); return; }
  try {
    await api(`/api/sessions/${S.active.id}/send`, 'POST', { text });
    ta.value = '';
    if (S.active) S.active.status = 'human';
    await loadMessages(S.active.id, true);
    renderSessList();
    toast('已发送');
  } catch (e) { toast(e.message, 'err'); }
}

function renderChatSide() {
  const s = S.active;
  if (!s) {
    $('#chatSide').innerHTML = `
      <div class="side-placeholder">
        ${icon('users')}
        <p>选中会话后<br>这里会显示买家资料与快捷话术</p>
      </div>`;
    return;
  }
  const tpls = (S.templates || []).slice(0, 6);
  $('#chatSide').innerHTML = `
    <div class="side-block">
      <div class="side-title">买家信息</div>
      <div class="kv"><span>买家昵称</span><b>${esc(s.buyer)}</b></div>
      <div class="kv"><span>来源平台</span><b>${esc(platOf(s.platform).name)}</b></div>
      <div class="kv"><span>咨询商品</span><b>${esc(s.product || '—')}</b></div>
      <div class="kv"><span>订单号</span><b>${esc(s.order_no || '—')}</b></div>
      <div class="kv"><span>接待模式</span><b>${s.status === 'human' ? '人工' : '自动'}</b></div>
    </div>
    <div class="side-block">
      <div class="side-title">快捷话术</div>
      ${tpls.map((t, i) => `<button class="quick-tpl" data-qi="${i}"><b>${esc(t.title)}</b><span>${esc(t.content)}</span></button>`).join('')}
    </div>
    <div class="side-block">
      <div class="side-title">当前生效规则</div>
      ${(S.rules || []).filter(r => r.enabled && (!r.platforms.length || r.platforms.includes(s.platform))).slice(0, 4)
        .map(r => `<div class="kv"><span>${esc(r.name)}</span><b>P${r.priority}</b></div>`).join('') || '<div class="kv"><span>暂无</span></div>'}
    </div>`;
  $$('#chatSide .quick-tpl').forEach(b => b.addEventListener('click', () => {
    const t = tpls[+b.dataset.qi];
    const ta = $('#replyText');
    if (ta) { ta.value = (ta.value ? ta.value + '\n' : '') + t.content; ta.focus(); }
  }));
}

/* ============================ 规则管理 ============================ */
const MT_LABEL = { any: '包含任一', all: '包含全部', exact: '完全匹配', regex: '正则匹配', fallback: '兜底' };

function renderRuleTable() {
  // 平台筛选条
  const pf = $('#rulePlatFilter');
  if (pf) {
    pf.innerHTML = `<button class="chip ${S.rulePlat === '' ? 'is-on' : ''}" data-p="">全部平台</button>` +
      S.platforms.map(p => `<button class="chip ${S.rulePlat === p.id ? 'is-on' : ''}" data-p="${p.id}">${esc(p.name)}</button>`).join('');
    $$('#rulePlatFilter .chip').forEach(b => b.addEventListener('click', () => {
      S.rulePlat = b.dataset.p; renderRuleTable();
    }));
  }

  const kw = S.ruleKeyword.toLowerCase();
  const list = (S.rules || []).filter(r => {
    if (S.rulePlat && r.platforms.length && !r.platforms.includes(S.rulePlat)) return false;
    if (kw && !(r.name || '').toLowerCase().includes(kw) && !(r.keywords || []).join('').toLowerCase().includes(kw)) return false;
    return true;
  });

  if (!list.length) {
    $('#ruleBody').innerHTML = `<tr><td colspan="9"><div class="empty sm">${icon('inbox')}<p>没有匹配的规则，试试新建一条</p></div></td></tr>`;
    return;
  }

  $('#ruleBody').innerHTML = list.map(r => {
    const kws = r.keywords || [];
    const kwsHtml = r.match_type === 'fallback' || r.is_fallback
      ? '<span class="tag fallback">兜底回复</span>'
      : kws.slice(0, 3).map(k => `<span class="tag kw">${esc(k)}</span>`).join('') +
        (kws.length > 3 ? `<span class="tag mute">+${kws.length - 3}</span>` : '');
    const plats = !r.platforms.length
      ? '<span class="tag mute">全部</span>'
      : r.platforms.slice(0, 3).map(id => {
          const p = platOf(id);
          return `<span class="tag" style="background:${p.color}15;color:${p.color}">${esc(p.name)}</span>`;
        }).join('') + (r.platforms.length > 3 ? `<span class="tag mute">+${r.platforms.length - 3}</span>` : '');
    return `
      <tr data-id="${r.id}">
        <td><span class="cell-strong num">${r.priority}</span></td>
        <td>
          <div class="cell-strong">${esc(r.name)}</div>
          ${r.note ? `<div class="muted" style="font-size:11.5px">${esc(r.note)}</div>` : ''}
        </td>
        <td><span class="tag">${MT_LABEL[r.match_type] || r.match_type}</span></td>
        <td><div class="kw-cell">${kwsHtml}</div></td>
        <td><div class="kw-cell">${plats}</div></td>
        <td class="muted">${esc(r.work_hours || '全天')}</td>
        <td class="num">${r.hits || 0}</td>
        <td><label class="switch"><input type="checkbox" ${r.enabled ? 'checked' : ''} data-toggle="${r.id}"><span></span></label></td>
        <td>
          <div class="actions">
            <button class="icon-btn" data-edit="${r.id}" title="编辑">${icon('pencil', 'sm')}</button>
            <button class="icon-btn danger" data-del="${r.id}" title="删除">${icon('trash', 'sm')}</button>
          </div>
        </td>
      </tr>`;
  }).join('');

  $$('#ruleBody [data-toggle]').forEach(el => el.addEventListener('change', async () => {
    try {
      const r = await api(`/api/rules/${el.dataset.toggle}/toggle`, 'POST');
      const rule = S.rules.find(x => String(x.id) === el.dataset.toggle);
      if (rule) rule.enabled = r.enabled;
      toast(r.enabled ? '规则已启用' : '规则已停用');
    } catch (e) { toast(e.message, 'err'); el.checked = !el.checked; }
  }));
  $$('#ruleBody [data-edit]').forEach(el => el.addEventListener('click', () => {
    openRuleDrawer(S.rules.find(x => String(x.id) === el.dataset.edit));
  }));
  $$('#ruleBody [data-del]').forEach(el => el.addEventListener('click', () => {
    const rule = S.rules.find(x => String(x.id) === el.dataset.del);
    confirmModal('删除规则', `确定删除「${rule.name}」？删除后该规则立即失效。`, async () => {
      await api(`/api/rules/${rule.id}`, 'DELETE');
      S.rules = S.rules.filter(x => x.id !== rule.id);
      renderRuleTable(); renderRank();
      toast('已删除');
    }, '删除', true);
  }));
}

/* ---------- 规则抽屉 ---------- */
let editingRule = null;

function openRuleDrawer(rule) {
  editingRule = rule || null;
  $('#drawerTitle').textContent = rule ? '编辑规则' : '新建规则';
  $('#drawerSub').textContent = rule ? `优先级 P${rule.priority} · 累计命中 ${rule.hits} 次` : '关键词命中后自动回复买家';

  const mt = rule ? rule.match_type : 'any';
  const plats = rule ? (rule.platforms || []) : [];
  const kwText = rule ? (rule.keywords || []).join('\n') : '';
  const hints = ['{昵称}', '{店铺}', '{客服名}', '{商品名}', '{订单号}', '{物流状态}', '{平台}', '{时间}', '{日期}'];

  $('#drawerBody').innerHTML = `
    <label class="field">
      <span class="field-label">规则名称 <em>*</em></span>
      <input class="input" id="fName" value="${esc(rule ? rule.name : '')}" placeholder="例如：物流查询 / 尺码推荐">
    </label>

    <div class="field">
      <span class="field-label">匹配方式</span>
      <div class="segmented" id="fMatch">
        ${Object.keys(MT_LABEL).map(k => `<button data-v="${k}" class="${k === mt ? 'is-on' : ''}">${MT_LABEL[k]}</button>`).join('')}
      </div>
      <span class="field-hint" id="fMatchHint"></span>
    </div>

    <label class="field" id="fKwWrap">
      <span class="field-label">关键词 <em>*</em></span>
      <textarea class="textarea" id="fKw" rows="3" placeholder="每行一个，也可用逗号分隔">${esc(kwText)}</textarea>
      <span class="field-hint">买家消息包含关键词即命中；建议覆盖不同说法，如「快递 / 物流 / 到哪了」</span>
    </label>

    <div class="field-row">
      <label class="field">
        <span class="field-label">优先级</span>
        <input class="input" id="fPriority" type="number" min="1" max="999" value="${rule ? rule.priority : 50}">
      </label>
      <label class="field">
        <span class="field-label">生效时段</span>
        <input class="input" id="fHours" value="${esc(rule ? rule.work_hours : '')}" placeholder="08:00-23:00（空=全天）">
      </label>
    </div>

    <div class="field">
      <span class="field-label">适用平台</span>
      <div class="chip-row wrap" id="fPlats">
        ${S.platforms.map(p => `<button class="chip ${plats.includes(p.id) ? 'is-on' : ''}" data-p="${p.id}">${esc(p.name)}</button>`).join('')}
      </div>
      <span class="field-hint">不选择表示全部平台生效</span>
    </div>

    <label class="field">
      <span class="field-label">回复内容 <em>*</em></span>
      <textarea class="textarea" id="fReply" rows="4" placeholder="亲，您的包裹正在运输途中，预计 1-2 天送达～">${esc(rule ? rule.reply : '')}</textarea>
      <div class="var-pills" id="fVars">${hints.map(h => `<button class="var-pill" data-var="${h}">${h}</button>`).join('')}</div>
    </label>

    <div class="field">
      <span class="field-label">实时预览</span>
      <div class="preview-box" id="fPreview"></div>
    </div>

    <label class="field">
      <span class="field-label">备注（仅自己可见）</span>
      <input class="input" id="fNote" value="${esc(rule ? rule.note : '')}" placeholder="例如：涉及退款时需人工确认">
    </label>

    <div class="switch-line">
      <div><strong>启用此规则</strong><p>关闭后不参与匹配，可在列表中随时开启</p></div>
      <label class="switch"><input type="checkbox" id="fEnabled" ${!rule || rule.enabled ? 'checked' : ''}><span></span></label>
    </div>`;

  $('#drawerMask').classList.add('on');
  $('#drawer').classList.add('on');

  // 交互
  let curMt = mt;
  const syncMatch = () => {
    $$('#fMatch button').forEach(b => b.classList.toggle('is-on', b.dataset.v === curMt));
    const hint = $('#fMatchHint');
    const kwWrap = $('#fKwWrap');
    if (curMt === 'fallback') {
      hint.textContent = '兜底规则不需要关键词，未命中其他规则时触发，建议优先级设为 1。';
      kwWrap.style.display = 'none';
    } else if (curMt === 'regex') {
      hint.textContent = '关键词框填写一个正则表达式（Python 语法），如：发货|寄出|什么时候发';
      kwWrap.style.display = '';
    } else if (curMt === 'exact') {
      hint.textContent = '买家整句话与关键词完全一致才命中（去除首尾空格，不区分大小写）。';
      kwWrap.style.display = '';
    } else if (curMt === 'all') {
      hint.textContent = '必须同时包含全部关键词才命中，适合收敛范围。';
      kwWrap.style.display = '';
    } else {
      hint.textContent = '买家消息中包含任意一个关键词即命中，最常用。';
      kwWrap.style.display = '';
    }
  };
  $$('#fMatch button').forEach(b => b.addEventListener('click', () => { curMt = b.dataset.v; syncMatch(); }));
  syncMatch();

  $$('#fPlats .chip').forEach(b => b.addEventListener('click', () => b.classList.toggle('is-on')));

  const updatePreview = () => {
    const raw = $('#fReply').value;
    const ctx = {
      '{昵称}': '柠檬不酸', '{店铺}': S.settings.shop_name || '本店',
      '{客服名}': S.settings.agent_name || '客服', '{商品名}': '纯棉宽松短袖T恤',
      '{订单号}': 'TM20261017008812', '{物流状态}': '运输中',
      '{平台}': '天猫', '{时间}': '09:41', '{日期}': '2026-10-17',
    };
    let out = raw.replace(/\{[^{}]+\}/g, m => ctx[m] !== undefined ? ctx[m] : m);
    if (raw.trim() && S.settings.append_signature && S.settings.signature) {
      out += '\n' + S.settings.signature.replace(/\{[^{}]+\}/g, m => ctx[m] !== undefined ? ctx[m] : m);
    }
    $('#fPreview').textContent = raw.trim() ? out : '';
  };
  $('#fReply').addEventListener('input', updatePreview);
  updatePreview();

  $$('#fVars .var-pill').forEach(b => b.addEventListener('click', () => {
    const ta = $('#fReply');
    const pos = ta.selectionStart || ta.value.length;
    ta.value = ta.value.slice(0, pos) + b.dataset.var + ta.value.slice(pos);
    ta.focus();
    ta.setSelectionRange(pos + b.dataset.var.length, pos + b.dataset.var.length);
    updatePreview();
  }));
}

function closeDrawer() {
  $('#drawerMask').classList.remove('on');
  $('#drawer').classList.remove('on');
  editingRule = null;
}

async function saveRule() {
  const onBtn = $('#fMatch button.is-on');
  const mt = onBtn ? onBtn.dataset.v : 'any';
  const payload = {
    name: $('#fName').value.trim(),
    match_type: mt,
    keywords: $('#fKw').value.split(/[,，\n]/).map(s => s.trim()).filter(Boolean),
    priority: parseInt($('#fPriority').value, 10) || 50,
    work_hours: $('#fHours').value.trim(),
    platforms: $$('#fPlats .chip.is-on').map(b => b.dataset.p),
    reply: $('#fReply').value,
    note: $('#fNote').value.trim(),
    enabled: $('#fEnabled').checked ? 1 : 0,
  };
  try {
    const r = editingRule
      ? await api('/api/rules/' + editingRule.id, 'PUT', payload)
      : await api('/api/rules', 'POST', payload);
    S.rules = r.items;
    renderRuleTable(); renderRank();
    closeDrawer();
    toast(editingRule ? '规则已更新' : '规则已创建', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

/* ============================ 话术库 ============================ */
async function loadTemplates() {
  const r = await api('/api/templates');
  S.templates = r.items || [];
  S.tplCats = r.categories || [];
  renderTemplates();
}

function renderTemplates() {
  const cats = $('#tplCats');
  if (cats) {
    cats.innerHTML = `<button class="chip ${S.tplCat === '' ? 'is-on' : ''}" data-c="">全部</button>` +
      S.tplCats.map(c => `<button class="chip ${S.tplCat === c ? 'is-on' : ''}" data-c="${esc(c)}">${esc(c)}</button>`).join('');
    $$('#tplCats .chip').forEach(b => b.addEventListener('click', () => { S.tplCat = b.dataset.c; renderTemplates(); }));
  }
  const kw = S.tplKeyword.toLowerCase();
  const list = (S.templates || []).filter(t => {
    if (S.tplCat && t.category !== S.tplCat) return false;
    if (kw && !(t.title || '').toLowerCase().includes(kw) && !(t.content || '').toLowerCase().includes(kw)) return false;
    return true;
  });
  const grid = $('#tplGrid');
  if (!grid) return;
  if (!list.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1">${icon('inbox')}<p>还没有话术，点击右上角新建</p></div>`;
    return;
  }
  grid.innerHTML = list.map(t => `
    <div class="tpl-card">
      <div class="tpl-top">
        <span class="tpl-cat">${esc(t.category)}</span>
        <span class="tpl-title">${esc(t.title)}</span>
      </div>
      <div class="tpl-content">${esc(t.content)}</div>
      <div class="tpl-foot">
        <span class="tpl-uses">已使用 ${t.uses || 0} 次</span>
        <button class="icon-btn" data-copy="${t.id}" title="复制">${icon('copy', 'sm')}</button>
        <button class="icon-btn" data-tedit="${t.id}" title="编辑">${icon('pencil', 'sm')}</button>
        <button class="icon-btn danger" data-tdel="${t.id}" title="删除">${icon('trash', 'sm')}</button>
      </div>
    </div>`).join('');

  $$('#tplGrid [data-copy]').forEach(b => b.addEventListener('click', () => {
    const t = S.templates.find(x => String(x.id) === b.dataset.copy);
    navigator.clipboard?.writeText(t.content).then(() => toast('话术已复制'), () => toast('复制失败', 'err'));
  }));
  $$('#tplGrid [data-tedit]').forEach(b => b.addEventListener('click', () => {
    openTplModal(S.templates.find(x => String(x.id) === b.dataset.tedit));
  }));
  $$('#tplGrid [data-tdel]').forEach(b => b.addEventListener('click', () => {
    const t = S.templates.find(x => String(x.id) === b.dataset.tdel);
    confirmModal('删除话术', `确定删除「${t.title}」？`, async () => {
      await api('/api/templates/' + t.id, 'DELETE');
      await loadTemplates();
      toast('已删除');
    }, '删除', true);
  }));
}

function openTplModal(tpl) {
  const cats = ['售前', '物流', '售后', '财务', '通用'];
  openModal(`
    <h3>${tpl ? '编辑话术' : '新建话术'}</h3>
    <p class="sub">支持 {昵称} {店铺} {商品名} {订单号} 等变量</p>
    <label class="field"><span class="field-label">分类</span>
      <select class="select" id="tCat">${cats.map(c => `<option ${tpl && tpl.category === c ? 'selected' : ''}>${c}</option>`).join('')}</select>
    </label>
    <label class="field"><span class="field-label">标题 <em>*</em></span>
      <input class="input" id="tTitle" value="${esc(tpl ? tpl.title : '')}" placeholder="例如：发货时效说明">
    </label>
    <label class="field"><span class="field-label">内容 <em>*</em></span>
      <textarea class="textarea" id="tContent" rows="4" placeholder="我们承诺 48 小时内发货…">${esc(tpl ? tpl.content : '')}</textarea>
      <div class="var-pills">${['{昵称}', '{店铺}', '{商品名}', '{订单号}'].map(v => `<button class="var-pill" data-ins="${v}">${v}</button>`).join('')}</div>
    </label>
    <div class="modal-foot">
      <button class="btn btn-ghost" data-close>取消</button>
      <button class="btn btn-primary" id="tSave">保存</button>
    </div>
    <style>.modal .field:last-of-type{margin-bottom:0}</style>
  `);
  $$('#modal [data-ins]').forEach(b => b.addEventListener('click', () => {
    const ta = $('#tContent');
    ta.value += b.dataset.ins;
    ta.focus();
  }));
  $('#tSave').addEventListener('click', async () => {
    const payload = {
      category: $('#tCat').value,
      title: $('#tTitle').value.trim(),
      content: $('#tContent').value.trim(),
    };
    try {
      if (tpl) await api('/api/templates/' + tpl.id, 'PUT', payload);
      else await api('/api/templates', 'POST', payload);
      closeModal();
      await loadTemplates();
      toast('已保存', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  });
}

/* ============================ 测试器 ============================ */
const SAMPLES = ['我的快递到哪了，都三天了', '175 身高 70 公斤选什么码', '有优惠券吗', '能开专票吗', '我要退货', '转人工'];

function renderTestPlatforms() {
  const sel = $('#testPlatform');
  if (!sel) return;
  sel.innerHTML = S.platforms.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  $('#testSamples').innerHTML = SAMPLES.map(s => `<button class="chip" data-s="${esc(s)}">${esc(s)}</button>`).join('');
  $$('#testSamples .chip').forEach(b => b.addEventListener('click', () => {
    $('#testText').value = b.dataset.s;
    $('#testText').focus();
  }));
  renderPipeline(null);
}

function renderPipeline(res) {
  const wrap = $('#pipeline');
  if (!wrap) return;
  if (!res) { wrap.style.display = 'none'; wrap.innerHTML = ''; return; }
  wrap.style.display = 'flex';
  const steps = ['收到消息', '平台校验', '生效时段', '关键词匹配', '优先级排序', '变量渲染', '敏感词检查', '发送'];
  const onCount = res.blocked ? 7 : (res.matched ? 8 : 4);
  wrap.innerHTML = steps.map((s, i) =>
    `<span class="pipe-step ${i < onCount ? 'on' : ''}">${s}</span>` +
    (i < steps.length - 1 ? '<span class="pipe-arrow"></span>' : '')).join('');
}

async function runTest() {
  const text = $('#testText').value.trim();
  if (!text) { toast('请输入买家原话'); return; }
  const btn = $('#btnRunTest');
  btn.disabled = true;
  try {
    const res = await api('/api/test', 'POST', { text, platform: $('#testPlatform').value });
    const box = $('#testResult');
    if (!res.matched) {
      box.innerHTML = `
        <div class="result-card">
          <div class="result-head">
            <span class="result-rule">未命中任何规则</span>
            <span class="result-badge warn">无匹配</span>
          </div>
          <div class="result-meta"><span>${esc(res.reason || '')}</span></div>
          <div class="reply-preview" data-blocked="0">买家消息将进入人工待处理队列，不会自动回复。</div>
        </div>`;
      renderPipeline(res);
      return;
    }
    const highlighted = highlight(text, res.keywords || []);
    box.innerHTML = `
      <div class="result-card">
        <div class="result-head">
          <span class="result-rule">${esc(res.rule_name)}</span>
          <span class="result-badge ${res.blocked ? 'danger' : (res.is_fallback ? 'warn' : '')}">
            ${res.blocked ? '已拦截' : (res.is_fallback ? '兜底命中' : '命中')}
          </span>
          ${res.is_fallback ? '<span class="tag fallback">兜底规则</span>' : ''}
        </div>
        <div class="result-meta">
          <span>优先级 <b>P${res.priority}</b></span>
          <span>匹配方式 <b>${MT_LABEL[res.match_type] || res.match_type}</b></span>
          <span>命中词 <b>${res.keywords.length ? res.keywords.map(esc).join('、') : '—'}</b></span>
          <span>耗时 <b>${res.latency_ms}ms</b></span>
        </div>
        <div class="reply-label">买家原话</div>
        <div class="reply-preview" data-blocked="0">${highlighted}</div>
        <div class="reply-label" style="margin-top:12px">最终发送内容</div>
        <div class="reply-preview" data-blocked="${res.blocked ? 1 : 0}">${esc(res.reply)}</div>
        ${res.blocked ? `<div class="blocked-tip">${icon('alert', 'sm')}命中敏感词「${esc(res.blocked_word)}」，该回复已被拦截，不会发送给买家。</div>` : ''}
      </div>`;
    renderPipeline(res);
  } catch (e) { toast(e.message, 'err'); }
  finally { btn.disabled = false; }
}

function highlight(text, kws) {
  let out = esc(text);
  (kws || []).filter(Boolean).sort((a, b) => b.length - a.length).forEach(k => {
    const safe = esc(k).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out.replace(new RegExp(safe, 'gi'), m => `<span class="hl">${m}</span>`);
  });
  return out;
}

/* ============================ 平台接入 ============================ */
function renderPlatGrid() {
  const grid = $('#platGrid');
  if (!grid) return;
  grid.innerHTML = S.platforms.map(p => `
    <div class="plat-card" data-pid="${p.id}">
      <div class="plat-card-head">
        ${platLogo(p)}
        <div class="plat-card-title">
          <strong>${esc(p.name)}</strong>
          <span>${esc(p.api_name)}</span>
        </div>
        <span class="tag ${p.enabled ? 'ok' : 'mute'}">${p.enabled ? '已启用' : '未启用'}</span>
      </div>
      <div class="plat-api-note">${esc(p.api_note)}</div>
      <div class="field-row">
        <label class="field"><span class="field-label">接入方式</span>
          <select class="select" data-k="mode">
            <option value="demo" ${p.mode === 'demo' ? 'selected' : ''}>演示模式</option>
            <option value="api" ${p.mode === 'api' ? 'selected' : ''}>官方接口</option>
          </select>
        </label>
        <label class="field"><span class="field-label">店铺名称</span>
          <input class="input" data-k="shop" value="${esc(p.shop || '')}" placeholder="选填">
        </label>
      </div>
      <div class="field-row">
        <label class="field"><span class="field-label">App Key</span>
          <input class="input" data-k="app_key" value="${esc(p.app_key || '')}" placeholder="开放平台应用 Key">
        </label>
        <label class="field"><span class="field-label">App Secret</span>
          <input class="input" data-k="app_secret" type="password" value="${esc(p.app_secret || '')}" placeholder="应用密钥">
        </label>
      </div>
      <div class="plat-card-foot">
        <label class="switch"><input type="checkbox" data-k="enabled" ${p.enabled ? 'checked' : ''}><span></span></label>
        <span style="font-size:12px;color:var(--text-3)">启用该平台</span>
        <button class="btn btn-ghost sm" data-save="${p.id}">保存配置</button>
      </div>
    </div>`).join('');

  $$('#platGrid [data-save]').forEach(btn => btn.addEventListener('click', async () => {
    const card = btn.closest('.plat-card');
    const payload = {};
    $$('[data-k]', card).forEach(el => {
      if (el.type === 'checkbox') payload[el.dataset.k] = el.checked ? 1 : 0;
      else payload[el.dataset.k] = el.value;
    });
    if (payload.mode === 'api' && (!payload.app_key || !payload.app_secret)) {
      toast('切换到官方接口需要填写 App Key 与 Secret', 'err');
      return;
    }
    try {
      const r = await api('/api/platforms/' + btn.dataset.save, 'POST', payload);
      S.platforms = r.platforms;
      renderPlatGrid(); renderPlatList(); renderTestPlatforms();
      toast(payload.mode === 'api' ? '配置已保存，等待开放平台回调验证' : '配置已保存（演示模式）', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }));
}

/* ============================ 日志 ============================ */
async function loadLogs(page, silent) {
  S.logPage = page || 1;
  const qs = new URLSearchParams({
    page: S.logPage, size: S.logSize,
    platform: S.logPlatform, q: S.logKeyword, mode: S.logMode,
  });
  try {
    const r = await api('/api/logs?' + qs.toString());
    if (!silent) renderLogs(r);
    else renderLogs(r);
  } catch (e) { if (!silent) toast(e.message, 'err'); }
}

function renderLogs(r) {
  const items = r.items || [];
  const body = $('#logBody');
  if (!body) return;
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="7"><div class="empty sm">${icon('inbox')}<p>暂无日志</p></div></td></tr>`;
  } else {
    const modeMap = {
      auto: ['自动回复', 'ok'], no_match: ['未命中', 'warn'], blocked: ['敏感词拦截', 'danger'],
    };
    body.innerHTML = items.map(l => {
      const [txt, cls] = modeMap[l.mode] || [l.mode, 'mute'];
      return `
        <tr>
          <td class="muted num">${esc(l.ts)}</td>
          <td><span class="tag" style="background:${(l.platform_color || '#667085')}15;color:${l.platform_color || '#667085'}">${esc(l.platform_name || l.platform)}</span></td>
          <td>${esc(l.buyer)}</td>
          <td><div class="q-cell" title="${esc(l.question)}">${esc(l.question)}</div></td>
          <td class="muted">${esc(l.rule_name || '—')}</td>
          <td><span class="tag ${cls}">${esc(txt)}</span></td>
          <td class="num muted">${l.latency_ms}ms</td>
        </tr>`;
    }).join('');
  }
  const total = r.total || 0;
  const pages = Math.max(1, Math.ceil(total / S.logSize));
  $('#logPager').innerHTML = `
    <span>共 ${total} 条记录 · 第 ${S.logPage} / ${pages} 页</span>
    <div class="pager-btns">
      <button class="btn btn-ghost sm" ${S.logPage <= 1 ? 'disabled' : ''} data-pg="${S.logPage - 1}">上一页</button>
      <button class="btn btn-ghost sm" ${S.logPage >= pages ? 'disabled' : ''} data-pg="${S.logPage + 1}">下一页</button>
    </div>`;
  $$('#logPager [data-pg]').forEach(b => b.addEventListener('click', () => loadLogs(+b.dataset.pg)));
}

async function loadRecent() {
  try {
    const r = await api('/api/logs?page=1&size=12');
    S.recent = (r.items || []).slice();
    S.cursor = r.items && r.items.length ? Math.max(...r.items.map(x => x.id)) : 0;
  } catch (e) { /* ignore */ }
}

async function clearLogs() {
  confirmModal('清空运行日志', '所有自动回复记录将被删除，规则与会话不受影响。此操作不可撤销。', async () => {
    await api('/api/logs/clear', 'POST');
    S.recent = []; S.cursor = 0;
    renderFeed(); loadLogs(1);
    toast('日志已清空');
  }, '清空', true);
}

async function resetSessions() {
  confirmModal('重置演示数据', '将清空全部会话与消息，模拟器会重新生成新会话。确定继续？', async () => {
    await api('/api/sessions/reset', 'POST');
    S.active = null; S.messages = []; S.msgCount = -1;
    $('#chatMain').innerHTML = `<div class="chat-empty">${icon('chat')}<p>选择左侧会话开始接待</p></div>`;
    $('#chatSide').innerHTML = '';
    await loadSessions();
    toast('演示数据已重置');
  }, '重置', true);
}

/* ============================ 设置 ============================ */
function renderSettingsForm() {
  const s = S.settings || {};
  const [start, end] = (s.work_hours || '08:00-23:00').split('-');
  const set = (sel, val) => { const el = $(sel); if (el) el.value = val; };
  const chk = (sel, val) => { const el = $(sel); if (el) el.checked = !!val; };
  chk('#setGlobal', s.global_enabled);
  chk('#setFallback', s.fallback_enabled);
  chk('#setNight', s.night_reply);
  chk('#setSignatureOn', s.append_signature);
  set('#setHoursStart', start || '08:00');
  set('#setHoursEnd', end || '23:00');
  set('#setDelayMin', s.reply_delay_min ?? 1);
  set('#setDelayMax', s.reply_delay_max ?? 3);
  set('#setPerMinute', s.max_per_minute ?? 20);
  set('#setCooldown', s.same_session_cooldown ?? 60);
  set('#setTakeover', s.human_takeover_minutes ?? 5);
  set('#setSensitive', (s.sensitive_words || []).join(', '));
  set('#setSignature', s.signature || '');
  set('#setShop', s.shop_name || '');
  set('#setAgent', s.agent_name || '');
  S.dirty = false;
  const h = $('#saveHint');
  if (h) { h.textContent = '设置修改后点击保存生效'; h.classList.remove('dirty'); }
}

async function saveSettings() {
  const patch = {
    global_enabled: $('#setGlobal').checked,
    fallback_enabled: $('#setFallback').checked,
    night_reply: $('#setNight').checked,
    work_hours: `${$('#setHoursStart').value.trim() || '08:00'}-${$('#setHoursEnd').value.trim() || '23:00'}`,
    reply_delay_min: parseInt($('#setDelayMin').value, 10) || 0,
    reply_delay_max: parseInt($('#setDelayMax').value, 10) || 0,
    max_per_minute: parseInt($('#setPerMinute').value, 10) || 20,
    same_session_cooldown: parseInt($('#setCooldown').value, 10) || 0,
    human_takeover_minutes: parseInt($('#setTakeover').value, 10) || 5,
    sensitive_words: $('#setSensitive').value.split(/[,，\n]/).map(x => x.trim()).filter(Boolean),
    append_signature: $('#setSignatureOn').checked,
    signature: $('#setSignature').value,
    shop_name: $('#setShop').value.trim(),
    agent_name: $('#setAgent').value.trim(),
  };
  try {
    const r = await api('/api/settings', 'POST', patch);
    S.settings = r.settings;
    renderSide();
    S.dirty = false;
    const h = $('#saveHint');
    h.textContent = '已保存 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
    h.classList.remove('dirty');
    toast('设置已保存', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

/* ============================ 模态框 ============================ */
function openModal(html) {
  $('#modal').innerHTML = html;
  $('#modalMask').classList.add('on');
  $$('#modal [data-close]').forEach(b => b.addEventListener('click', closeModal));
}
function closeModal() { $('#modalMask').classList.remove('on'); }

function confirmModal(title, desc, onOk, okText = '确定', danger = false) {
  openModal(`
    <h3>${esc(title)}</h3>
    <p class="sub">${esc(desc)}</p>
    <div class="modal-foot">
      <button class="btn btn-ghost" data-close>取消</button>
      <button class="btn ${danger ? 'btn-primary' : 'btn-primary'}" id="mOk" style="${danger ? 'background:#c4321f;border-color:#a92a19' : ''}">${esc(okText)}</button>
    </div>`);
  $('#mOk').addEventListener('click', async () => {
    const btn = $('#mOk');
    btn.disabled = true;
    try { await onOk(); closeModal(); }
    catch (e) { toast(e.message, 'err'); btn.disabled = false; }
  });
}

/* ============================ 工具 ============================ */
function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

document.addEventListener('DOMContentLoaded', boot);
