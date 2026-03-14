import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/* ─────────────────────────────────────────
   SHARED UI ATOMS
───────────────────────────────────────── */
function Badge({ status }) {
  const MAP = {
    approved:      { bg:'#ecfdf5', c:'#059669', b:'#a7f3d0', l:'Approved' },
    blocked:       { bg:'#fef2f2', c:'#dc2626', b:'#fecaca', l:'Blocked' },
    pending:       { bg:'#fffbeb', c:'#d97706', b:'#fde68a', l:'Pending' },
    pending_human: { bg:'#f5f3ff', c:'#7c3aed', b:'#ddd6fe', l:'Review' },
    killed:        { bg:'#fef2f2', c:'#dc2626', b:'#fecaca', l:'Killed' },
    failed:        { bg:'#f9fafb', c:'#6b7280', b:'#e5e7eb', l:'Failed' },
  };
  const s = MAP[status] || { bg:'#f9fafb', c:'#6b7280', b:'#e5e7eb', l: status?.toUpperCase()||'—' };
  return <span className="badge" style={{ background:s.bg, color:s.c, borderColor:s.b }}>{s.l}</span>;
}

function RiskPill({ score }) {
  if (score == null) return <span style={{ color:'#a3c4b0', fontSize:11 }}>—</span>;
  const p = (score * 100).toFixed(0);
  const s = score < 0.3 ? { bg:'#ecfdf5', c:'#059669', b:'#a7f3d0' }
    : score < 0.7        ? { bg:'#fffbeb', c:'#d97706', b:'#fde68a' }
    :                      { bg:'#fef2f2', c:'#dc2626', b:'#fecaca' };
  return <span className="badge" style={{ background:s.bg, color:s.c, borderColor:s.b }}>{p}%</span>;
}

function Dot({ color='#059669', pulse }) {
  return <span style={{ width:8, height:8, borderRadius:'50%', background:color, display:'inline-block', flexShrink:0 }}
               className={pulse ? `pulse-${pulse}` : ''} />;
}

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'#fff', border:'1px solid #e4f0e9', borderRadius:10, padding:'8px 14px', boxShadow:'0 4px 16px rgba(0,0,0,.08)' }}>
      <p style={{ color:'#8fb8a0', fontSize:10, marginBottom:3 }}>Transaction #{label}</p>
      <p style={{ color:'#059669', fontSize:14, fontWeight:700 }}>{payload[0].value}%</p>
    </div>
  );
};

/* ─────────────────────────────────────────
   SIDEBAR
───────────────────────────────────────── */
const NAV = [
  { id:'home',         icon:'⌂',  label:'Home' },
  { id:'dashboard',    icon:'⊞',  label:'Dashboard' },
  { id:'transactions', icon:'⟳',  label:'Transactions' },
  { id:'threats',      icon:'⚡',  label:'AI Threats' },
  { id:'intelligence', icon:'◈',  label:'Intelligence' },
  { id:'ledger',       icon:'🔗', label:'Ledger' },
  { id:'kill',         icon:'⚠',  label:'Kill Switch', danger:true },
];

/* ─────────────────────────────────────────
   HOME PAGE
───────────────────────────────────────── */
function HomeFeatureCard({ icon, title, desc, accent='#059669' }) {
  return (
    <div style={{ background:'#fff', border:'1px solid #e4f0e9', borderRadius:16, padding:'22px 22px 20px', boxShadow:'0 2px 10px rgba(0,0,0,.04)', transition:'all .2s', cursor:'default' }}
         onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-3px)';e.currentTarget.style.boxShadow='0 8px 28px rgba(0,0,0,.08)'}}
         onMouseLeave={e=>{e.currentTarget.style.transform='';e.currentTarget.style.boxShadow='0 2px 10px rgba(0,0,0,.04)'}}>
      <div style={{ width:44, height:44, borderRadius:13, background:`${accent}14`, border:`1px solid ${accent}30`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:20, marginBottom:14 }}>{icon}</div>
      <p style={{ fontSize:14, fontWeight:700, color:'#0f1f16', marginBottom:6 }}>{title}</p>
      <p style={{ fontSize:12, color:'#6b9e80', lineHeight:1.55 }}>{desc}</p>
    </div>
  );
}

function HomePage({ wallet, transactions, setTab }) {
  const approved = transactions.filter(t=>t.status==='approved').length;
  const blocked  = transactions.filter(t=>t.status==='blocked'||t.status==='killed').length;
  const total    = transactions.length;
  const pctSafe  = total ? ((approved/total)*100).toFixed(0) : '100';

  const features = [
    { icon:'🛡️', title:'Intelligent Interception',   desc:'Every payment passes through 3 parallel checks — merchant trust, ML behavior analysis, and policy rules — before a single rupee moves.',           accent:'#059669' },
    { icon:'🤖', title:'AI Threat Hunter',            desc:'Gemini-powered log analyst hunts for attack patterns, amount probing, and merchant hopping across your full transaction history.',             accent:'#7c3aed' },
    { icon:'⚡', title:'Instant Kill Switch',          desc:'One tap freezes the agent wallet globally. Redis pub/sub propagates the signal to every agent instance in milliseconds.',                     accent:'#dc2626' },
    { icon:'👤', title:'Human-in-the-Loop',           desc:'Medium-risk payments pause and fire a Telegram approval request. 5-minute timeout auto-kills if no response — safe by default.',            accent:'#d97706' },
    { icon:'🔗', title:'Tamper-Proof Ledger',         desc:'Every event is chained with SHA-256 across two independent databases. Tampering with any entry breaks the chain — detectable instantly.',     accent:'#2563eb' },
    { icon:'🧠', title:'Adaptive Spend Intelligence', desc:'An always-on background scanner surfaces unused subscriptions, price hikes, and monthly budget forecasts from your agent spending history.',  accent:'#059669' },
  ];

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:28 }}>

      {/* Hero */}
      <div style={{ background:'linear-gradient(135deg,#052e16 0%,#064e3b 50%,#065f46 100%)', borderRadius:22, padding:'44px 48px', position:'relative', overflow:'hidden' }}>
        {/* BG orb */}
        <div style={{ position:'absolute', top:-60, right:-60, width:280, height:280, borderRadius:'50%', background:'rgba(52,211,153,.1)', pointerEvents:'none' }}/>
        <div style={{ position:'absolute', bottom:-40, left:160, width:200, height:200, borderRadius:'50%', background:'rgba(16,185,129,.07)', pointerEvents:'none' }}/>

        <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:20 }}>
          <img src="/logo.png" alt="LatentPay" style={{ width:54, height:54, borderRadius:14, objectFit:'contain', background:'rgba(255,255,255,.08)', padding:6 }}/>
          <div>
            <h1 style={{ fontSize:32, fontWeight:900, color:'#fff', letterSpacing:'-1px', lineHeight:1 }}>LatentPay</h1>
            <p style={{ fontSize:12, color:'rgba(52,211,153,.8)', fontWeight:600, letterSpacing:'.1em', textTransform:'uppercase', marginTop:4 }}>Cognitive Payment Intelligence</p>
          </div>
        </div>

        <p style={{ fontSize:16, color:'rgba(255,255,255,.7)', lineHeight:1.65, maxWidth:620, marginBottom:28 }}>
          A secure, AI-native payment layer for autonomous agents. Every payment intercepted, analysed, and
          approved in milliseconds — your real bank account stays completely invisible to the agent.
        </p>

        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
          <button onClick={()=>setTab('dashboard')} style={{ background:'linear-gradient(135deg,#059669,#34d399)', border:'none', color:'#fff', fontWeight:700, fontSize:13, padding:'11px 22px', borderRadius:12, cursor:'pointer', boxShadow:'0 4px 14px rgba(5,150,105,.4)', fontFamily:"'Inter',sans-serif" }}>
            Open Dashboard →
          </button>
          <button onClick={()=>setTab('threats')} style={{ background:'rgba(255,255,255,.08)', border:'1px solid rgba(255,255,255,.15)', color:'rgba(255,255,255,.8)', fontWeight:600, fontSize:13, padding:'11px 22px', borderRadius:12, cursor:'pointer', fontFamily:"'Inter',sans-serif" }}>
            View Threats
          </button>
        </div>
      </div>

      {/* Live stats strip */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14 }}>
        {[
          { label:'Transactions Analysed', val: total,          icon:'📊', bg:'#ecfdf5', ic:'#059669' },
          { label:'Approved Payments',      val: approved,       icon:'✓',  bg:'#ecfdf5', ic:'#059669' },
          { label:'Threats Blocked',         val: blocked,        icon:'🛡', bg:'#fef2f2', ic:'#dc2626' },
          { label:'Safety Rate',             val: `${pctSafe}%`, icon:'◉',  bg:'#fffbeb', ic:'#d97706' },
        ].map(s => (
          <div key={s.label} style={{ background:'#fff', border:'1px solid #e4f0e9', borderRadius:16, padding:'18px 20px', boxShadow:'0 2px 8px rgba(0,0,0,.04)' }}>
            <div style={{ width:36, height:36, borderRadius:10, background:s.bg, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, color:s.ic, marginBottom:10 }}>{s.icon}</div>
            <p style={{ fontSize:11, color:'#8fb8a0', fontWeight:500, marginBottom:4 }}>{s.label}</p>
            <p style={{ fontSize:24, fontWeight:800, letterSpacing:'-1px', color:'#0f1f16', lineHeight:1 }}>{s.val}</p>
          </div>
        ))}
      </div>

      {/* Features grid */}
      <div>
        <p style={{ fontSize:11, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.08em', fontWeight:700, marginBottom:14 }}>Core Capabilities</p>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:14 }}>
          {features.map(f => <HomeFeatureCard key={f.title} {...f}/>)}
        </div>
      </div>

      {/* Architecture */}
      <div style={{ background:'#fff', border:'1px solid #e4f0e9', borderRadius:18, padding:'24px 26px', boxShadow:'0 2px 10px rgba(0,0,0,.04)' }}>
        <p style={{ fontSize:11, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.08em', fontWeight:700, marginBottom:18 }}>How It Works</p>
        <div style={{ display:'flex', alignItems:'center', gap:0, overflowX:'auto', paddingBottom:4 }}>
          {[
            { icon:'🤖', label:'AI Agent',       sub:'OpenClaw / PicoClaw', color:'#7c3aed', bg:'#f5f3ff' },
            { icon:'→',  label:'',               sub:'',                   color:'#c4ddd0', bg:'transparent', arrow:true },
            { icon:'⚡',  label:'LatentPay',      sub:'Interceptor + Risk',  color:'#059669', bg:'#ecfdf5' },
            { icon:'→',  label:'',               sub:'',                   color:'#c4ddd0', bg:'transparent', arrow:true },
            { icon:'👤', label:'Human Review',   sub:'Telegram HITL',       color:'#d97706', bg:'#fffbeb' },
            { icon:'→',  label:'',               sub:'',                   color:'#c4ddd0', bg:'transparent', arrow:true },
            { icon:'💳', label:'Pine Labs',       sub:'UAT / Production',    color:'#2563eb', bg:'#eff6ff' },
          ].map((s,i) => s.arrow ? (
            <div key={i} style={{ fontSize:22, color:'#c4ddd0', padding:'0 10px', flexShrink:0 }}>→</div>
          ) : (
            <div key={i} style={{ background:s.bg, border:`1px solid ${s.color}22`, borderRadius:14, padding:'16px 18px', flexShrink:0, minWidth:130, textAlign:'center' }}>
              <div style={{ fontSize:24, marginBottom:8 }}>{s.icon}</div>
              <p style={{ fontSize:13, fontWeight:700, color:s.color }}>{s.label}</p>
              <p style={{ fontSize:10, color:'#8fb8a0', marginTop:3 }}>{s.sub}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Built for Pine Labs */}
      <div style={{ background:'linear-gradient(135deg,#fffbeb,#fef9c3)', border:'1px solid #fde68a', borderRadius:16, padding:'18px 22px', display:'flex', alignItems:'center', gap:16 }}>
        <div style={{ fontSize:28, flexShrink:0 }}>🏆</div>
        <div>
          <p style={{ fontSize:13, fontWeight:700, color:'#713f12' }}>Pine Labs AI Hackathon 2026</p>
          <p style={{ fontSize:12, color:'#92400e', lineHeight:1.5 }}>Theme: Agentic / Autonomous Commerce & Intelligent Payments · March 14, 2026</p>
        </div>
      </div>

    </div>
  );
}

function Sidebar({ activeTab, setActiveTab, pendingCount }) {
  return (
    <nav className="sidebar">
      {/* Logo */}
      <div className="s-logo">
        <img src="/logo.png" alt="LatentPay" style={{ width:40, height:40, borderRadius:10, objectFit:'contain', background:'transparent', flexShrink:0 }} />
        <div>
          <div className="s-logo-name">LatentPay</div>
          <div className="s-logo-sub">Payment Intelligence</div>
        </div>
      </div>

      {/* Nav */}
      <div className="s-section">
        <div className="s-label">Navigation</div>
        {NAV.filter(n => !n.danger).map(n => (
          <div key={n.id} className={`s-item ${activeTab === n.id ? 'active' : ''}`}
               onClick={() => setActiveTab(n.id)}>
            <span className="s-icon">{n.icon}</span>
            {n.label}
            {n.id === 'threats' && pendingCount > 0 && <span className="s-badge">{pendingCount}</span>}
          </div>
        ))}
      </div>

      <div className="s-divider" />

      <div className="s-section" style={{ paddingTop:6 }}>
        <div className="s-label">Control</div>
        <div
          className={`s-item ${activeTab === 'kill' ? 'active' : ''}`}
          onClick={() => setActiveTab('kill')}
          style={activeTab !== 'kill' ? { color:'rgba(252,165,165,.6)' } : { background:'rgba(220,38,38,.12)', color:'#f87171' }}
        >
          <span className="s-icon">⚠</span>
          Kill Switch
        </div>
      </div>

      {/* Bottom */}
      <div className="s-bottom">
        <div style={{ padding:'10px 12px', borderRadius:10, background:'rgba(52,211,153,.06)', border:'1px solid rgba(52,211,153,.1)', display:'flex', alignItems:'center', gap:8 }}>
          <Dot color="#10b981" pulse="g" />
          <div>
            <p style={{ fontSize:11, color:'rgba(255,255,255,.6)', fontWeight:500 }}>System Online</p>
            <p style={{ fontSize:9, color:'rgba(255,255,255,.3)' }}>Auto-refresh every 5s</p>
          </div>
        </div>
      </div>
    </nav>
  );
}

/* ─────────────────────────────────────────
   PAGE HEADER
───────────────────────────────────────── */
function PageHeader({ title, subtitle, right }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-sub">{subtitle}</p>}
      </div>
      {right && <div style={{ display:'flex', alignItems:'center', gap:8 }}>{right}</div>}
    </div>
  );
}

/* ─────────────────────────────────────────
   STATUS STRIP (top of every page)
───────────────────────────────────────── */
function StatusStrip({ wallet, txns, lastRefresh, loading, error }) {
  const approved = txns.filter(t => t.status==='approved').length;
  const blocked  = txns.filter(t => t.status==='blocked'||t.status==='killed').length;
  const avgRisk  = txns.length
    ? (txns.slice(0,10).reduce((s,t) => s+(t.risk_score||0),0)/Math.min(txns.length,10)*100).toFixed(0)
    : '—';

  const tiles = [
    { label:'Balance',  val: wallet ? `₹${(wallet.balance||0).toLocaleString('en-IN')}` : '—', icon:'💰', bg:'#ecfdf5', ic:'#059669' },
    { label:'Approved', val: approved, icon:'✓', bg:'#ecfdf5', ic:'#059669' },
    { label:'Blocked',  val: blocked,  icon:'✕', bg: blocked>0?'#fef2f2':'#ecfdf5', ic: blocked>0?'#dc2626':'#059669' },
    { label:'Avg Risk', val: avgRisk==='—'?'—':`${avgRisk}%`, icon:'◉', bg:'#fffbeb', ic:'#d97706' },
  ];

  return (
    <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14, marginBottom:6 }}>
      {tiles.map(t => (
        <div key={t.label} className="stat-tile">
          <div className="st-icon" style={{ background:t.bg }}><span style={{ color:t.ic }}>{t.icon}</span></div>
          <div>
            <div className="st-label">{t.label}</div>
            <div className="st-val">{t.val}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─────────────────────────────────────────
   WALLET CARD
───────────────────────────────────────── */
function WalletCard({ wallet, onFreeze, onUnfreeze, onTopup }) {
  const [amt, setAmt] = useState('');
  const pct = wallet?.weekly_limit > 0 ? Math.min(((wallet.current_weekly_spend||0)/wallet.weekly_limit)*100,100) : 0;
  const isHot = pct>80, isMed = pct>50;

  return (
    <div className="card p20" style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 }}>
        <div>
          <p style={{ fontSize:11, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.07em', fontWeight:600 }}>Agent Wallet</p>
          <p style={{ fontSize:16, fontWeight:700, color:'#0f1f16', marginTop:3 }}>Pine Labs</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          {wallet && (
            <div style={{
              display:'flex', alignItems:'center', gap:6,
              background: wallet.is_frozen?'#fef2f2':'#ecfdf5',
              border:`1px solid ${wallet.is_frozen?'#fecaca':'#a7f3d0'}`,
              padding:'5px 11px', borderRadius:99,
            }}>
              <Dot color={wallet.is_frozen?'#dc2626':'#059669'} pulse={wallet.is_frozen?'r':'g'} />
              <span style={{ fontSize:11, fontWeight:600, color:wallet.is_frozen?'#dc2626':'#059669' }}>
                {wallet.is_frozen ? 'Frozen' : 'Active'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Balance */}
      <p style={{ fontSize:11, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.07em', fontWeight:600, marginBottom:6 }}>Available Balance</p>
      <p style={{ fontSize:36, fontWeight:900, letterSpacing:'-1.5px', lineHeight:1, color:'#0f1f16', marginBottom:20 }}>
        <span style={{ fontSize:18, fontWeight:500, color:'#8fb8a0', marginRight:3 }}>₹</span>
        {wallet ? (wallet.balance||0).toLocaleString('en-IN',{minimumFractionDigits:2}) : '—'}
      </p>

      {wallet && <>
        {/* Mini stats */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
          {[['Per Tx Limit', wallet.spend_limit], ['Weekly Left', wallet.weekly_remaining]].map(([l,v]) => (
            <div key={l} className="mini-card">
              <p style={{ fontSize:10, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.06em', fontWeight:600 }}>{l}</p>
              <p style={{ fontSize:17, fontWeight:700, color:'#0f1f16', fontFamily:"'JetBrains Mono',monospace", marginTop:4 }}>₹{(v||0).toLocaleString()}</p>
            </div>
          ))}
        </div>

        {/* Progress */}
        <div style={{ marginBottom:18 }}>
          <div style={{ display:'flex', justifyContent:'space-between', fontSize:11, marginBottom:7 }}>
            <span style={{ color:'#8fb8a0', fontWeight:500, textTransform:'uppercase', letterSpacing:'.05em' }}>Weekly Budget</span>
            <span style={{ fontWeight:700, color: isHot?'#dc2626': '#059669' }}>{pct.toFixed(0)}%</span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width:`${pct}%`, background: isHot?'linear-gradient(90deg,#f97316,#ef4444)':isMed?'linear-gradient(90deg,#fbbf24,#f97316)':'linear-gradient(90deg,#34d399,#059669)' }} />
          </div>
        </div>

        <div className="sep" />

        {/* Actions */}
        <div style={{ display:'flex', gap:8 }}>
          <div style={{ flex:1, position:'relative' }}>
            <span style={{ position:'absolute', left:11, top:'50%', transform:'translateY(-50%)', color:'#8fb8a0', fontSize:13 }}>₹</span>
            <input type="number" placeholder="Amount" value={amt} onChange={e=>setAmt(e.target.value)} className="g-input" style={{ paddingLeft:26 }} />
          </div>
          <button className="btn btn-primary" onClick={()=>{onTopup(amt);setAmt('')}}>Add Funds</button>
          {wallet.is_frozen
            ? <button className="btn btn-primary" style={{ background:'linear-gradient(135deg,#1d4ed8,#2563eb)',boxShadow:'0 3px 10px rgba(37,99,235,.25)' }} onClick={onUnfreeze}>Unfreeze</button>
            : <button className="btn btn-danger" onClick={onFreeze}>Freeze</button>
          }
        </div>

        {wallet.frozen_reason && (
          <div style={{ marginTop:12, background:'#fef2f2', border:'1px solid #fecaca', borderRadius:10, padding:'10px 14px', display:'flex', gap:8 }}>
            <span style={{ fontSize:14 }}>❄️</span>
            <p style={{ fontSize:12, color:'#b91c1c', lineHeight:1.4 }}>{wallet.frozen_reason}</p>
          </div>
        )}

        <p style={{ fontSize:10, color:'#c4ddd0', fontFamily:'monospace', marginTop:12 }}>ID: {wallet.id}</p>
      </>}
    </div>
  );
}

/* ─────────────────────────────────────────
   RISK CARD
───────────────────────────────────────── */
function RiskCard({ transactions }) {
  if (!transactions?.length) return (
    <div className="card p20" style={{ display:'flex', alignItems:'center', justifyContent:'center', opacity:.4, minHeight:200 }}>
      <p style={{ color:'#8fb8a0' }}>No transaction data</p>
    </div>
  );

  const latest = transactions[0];
  const scores = [
    { name:'Merchant Trust',    val:latest.merchant_score||0, color:'#059669' },
    { name:'Behavior Analysis', val:latest.behavior_score||0, color:'#2563eb' },
    { name:'Policy Rules',      val:latest.policy_score||0,  color:'#d97706' },
  ];
  const chartData = transactions.slice(0,20).reverse().map((tx,i) => ({ name:`${i+1}`, risk:+((tx.risk_score||0)*100).toFixed(0) }));
  const avgRisk = transactions.slice(0,10).reduce((s,t)=>s+(t.risk_score||0),0)/Math.min(transactions.length,10);
  const avPct   = (avgRisk*100).toFixed(0);
  const r=44, circ=2*Math.PI*r;
  const arc = circ*(avgRisk||0);

  return (
    <div className="card p20" style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:18 }}>
        <div>
          <p style={{ fontSize:15, fontWeight:700, color:'#0f1f16' }}>Risk Analysis</p>
          <p style={{ fontSize:11, color:'#8fb8a0', marginTop:2 }}>Latest: {latest.merchant||'—'}</p>
        </div>
        <RiskPill score={avgRisk} />
      </div>

      {/* Donut + bars */}
      <div style={{ display:'flex', gap:18, alignItems:'center', marginBottom:18 }}>
        <div className="ring-wrap">
          <svg width="100" height="100" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r={r} fill="none" stroke="#f0faf5" strokeWidth="10"/>
            <circle cx="50" cy="50" r={r} fill="none"
              stroke={avgRisk>.7?'#dc2626':avgRisk>.4?'#d97706':'#059669'}
              strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${arc} ${circ-arc}`}
              style={{ transition:'stroke-dasharray .7s ease' }}
            />
          </svg>
          <div className="ring-center">
            <span style={{ fontSize:20, fontWeight:800, color:'#0f1f16', lineHeight:1 }}>{avPct}%</span>
            <span style={{ fontSize:9, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.07em', fontWeight:600, marginTop:2 }}>Avg Risk</span>
          </div>
        </div>
        <div style={{ flex:1, display:'flex', flexDirection:'column', gap:12 }}>
          {scores.map(s => (
            <div key={s.name}>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, marginBottom:5 }}>
                <span style={{ color:'#4a7a5e', fontWeight:500 }}>{s.name}</span>
                <span style={{ color:s.color, fontWeight:700, fontFamily:'monospace', fontSize:11 }}>{(s.val*100).toFixed(0)}%</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width:`${Math.min(s.val*100,100)}%`, background:s.color }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="sep" />

      <p style={{ fontSize:10, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.07em', fontWeight:600, marginBottom:10 }}>Risk Trend · Last 20 Transactions</p>
      {chartData.length > 1 && (
        <ResponsiveContainer width="100%" height={96}>
          <AreaChart data={chartData} margin={{ top:0, right:4, left:-22, bottom:0 }}>
            <defs>
              <linearGradient id="rg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#059669" stopOpacity={0.18}/>
                <stop offset="100%" stopColor="#059669" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <XAxis dataKey="name" tick={{ fontSize:9, fill:'#c4ddd0' }} axisLine={false} tickLine={false}/>
            <YAxis domain={[0,100]} tick={{ fontSize:9, fill:'#c4ddd0' }} axisLine={false} tickLine={false}/>
            <Tooltip content={<ChartTip/>}/>
            <Area type="monotone" dataKey="risk" stroke="#059669" strokeWidth={2} fill="url(#rg)" dot={false} activeDot={{ r:4, fill:'#059669', strokeWidth:0 }}/>
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────
   TRANSACTION FEED
───────────────────────────────────────── */
function TxFeed({ transactions, compact }) {
  const shown = compact ? transactions.slice(0,6) : transactions;
  return (
    <div className="card p20" style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <div>
          <p style={{ fontSize:15, fontWeight:700, color:'#0f1f16' }}>Live Transactions</p>
          <p style={{ fontSize:11, color:'#8fb8a0', marginTop:2 }}>Real-time payment feed</p>
        </div>
        <span style={{ fontSize:11, color:'#059669', background:'#ecfdf5', border:'1px solid #a7f3d0', padding:'4px 10px', borderRadius:8, fontWeight:600 }}>
          {transactions?.length||0} total
        </span>
      </div>

      {!shown?.length ? (
        <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:10, opacity:.4, padding:'32px 0' }}>
          <div style={{ fontSize:28 }}>📡</div>
          <p style={{ fontSize:12, color:'#4a7a5e' }}>Listening for payments…</p>
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:4, overflowY:'auto', maxHeight: compact?320:520 }}>
          {shown.map((tx,i) => (
            <div key={tx.id||i} className="tx-row">
              <div className="av">{tx.merchant?.[0]?.toUpperCase()||'?'}</div>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:2 }}>
                  <span style={{ fontSize:13, fontWeight:600, color:'#0f1f16' }}>{tx.merchant||'Unknown'}</span>
                  <Badge status={tx.status}/>
                </div>
                <p style={{ fontSize:11, color:'#8fb8a0', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{tx.description||'API Payment'}</p>
                <p style={{ fontSize:9, color:'#c4ddd0', fontFamily:'monospace', marginTop:2 }}>
                  {tx.id?.substring(0,8)} · {tx.created_at ? new Date(tx.created_at).toLocaleTimeString() : ''}
                </p>
              </div>
              <div style={{ textAlign:'right', display:'flex', flexDirection:'column', alignItems:'flex-end', gap:4 }}>
                <p style={{ fontSize:13, fontWeight:700, color:'#0f1f16', fontFamily:"'JetBrains Mono',monospace" }}>₹{(tx.amount||0).toLocaleString()}</p>
                <RiskPill score={tx.risk_score}/>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────
   KILL SWITCH
───────────────────────────────────────── */
function KillSwitch({ status, onTrigger }) {
  const [conf, setConf] = useState(false);
  return (
    <div className="card p20" style={{ border:'1px solid rgba(220,38,38,.1)' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <p style={{ fontSize:15, fontWeight:700, color:'#b91c1c', display:'flex', alignItems:'center', gap:6 }}>
          <span>⚡</span> Kill Switch
        </p>
        {status?.trigger_count > 0 && (
          <span style={{ fontSize:10, background:'#fef2f2', color:'#dc2626', border:'1px solid #fecaca', padding:'2px 9px', borderRadius:99, fontWeight:700, letterSpacing:'.04em', textTransform:'uppercase' }}>
            {status.trigger_count}× triggered
          </span>
        )}
      </div>

      {status?.last_trigger && (
        <div style={{ background:'#fef2f2', border:'1px solid #fecaca', borderRadius:12, padding:'13px 15px', marginBottom:16 }}>
          <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:11 }}>
            <Dot color="#dc2626" pulse="r"/>
            <p style={{ fontSize:11, color:'#dc2626', fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em' }}>Last Activation</p>
          </div>
          {[['Time', new Date(status.last_trigger).toLocaleString()], ['Cause', status.last_reason], ['Count', `${status.trigger_count} times`]].map(([k,v]) => (
            <div key={k} style={{ display:'flex', justifyContent:'space-between', fontSize:12, marginBottom:6 }}>
              <span style={{ color:'#8fb8a0', fontWeight:500 }}>{k}</span>
              <span style={{ color:'#b91c1c', fontWeight:600, maxWidth:190, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', textAlign:'right' }}>{v}</span>
            </div>
          ))}
        </div>
      )}

      {!conf ? (
        <button className="kill-btn" onClick={()=>setConf(true)}>⚠ Emergency Kill</button>
      ) : (
        <div style={{ background:'#fef2f2', border:'1px solid rgba(220,38,38,.25)', borderRadius:12, padding:16 }}>
          <p style={{ fontSize:12, color:'#d97706', textAlign:'center', fontWeight:700, textTransform:'uppercase', letterSpacing:'.07em', marginBottom:14 }}>This will freeze all payments. Confirm?</p>
          <div style={{ display:'flex', gap:8 }}>
            <button className="btn btn-danger" style={{ flex:1, borderRadius:9 }} onClick={()=>{onTrigger();setConf(false)}}>EXECUTE</button>
            <button className="btn btn-outline" style={{ flex:1, borderRadius:9 }} onClick={()=>setConf(false)}>Abort</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────
   AI THREAT
───────────────────────────────────────── */
function ThreatCard({ analysis, onRun }) {
  const lvl = analysis?.threat_level?.toUpperCase();
  const cfgMap = {
    CRITICAL: { bg:'#fef2f2', c:'#dc2626', b:'#fecaca', dp:'r' },
    HIGH:     { bg:'#fff7ed', c:'#ea580c', b:'#fed7aa', dp:'a' },
    MEDIUM:   { bg:'#fffbeb', c:'#d97706', b:'#fde68a', dp:'' },
    LOW:      { bg:'#ecfdf5', c:'#059669', b:'#a7f3d0', dp:'g' },
  };
  const cfg = (lvl && cfgMap[lvl]) || cfgMap.LOW;

  return (
    <div className="card p20" style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:18 }}>
        <div>
          <p style={{ fontSize:15, fontWeight:700, color:'#0f1f16' }}>AI Threat Hunter</p>
          <p style={{ fontSize:11, color:'#8fb8a0', marginTop:2 }}>Gemini-powered security scan</p>
        </div>
        <button className="btn btn-primary" style={{ padding:'8px 14px', fontSize:11, borderRadius:9 }} onClick={onRun}>+ Run Scan</button>
      </div>

      {!analysis ? (
        <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:12, opacity:.45, padding:'28px 0' }}>
          <div style={{ width:56, height:56, borderRadius:18, background:'#f0faf5', border:'1px solid #e4f0e9', display:'flex', alignItems:'center', justifyContent:'center', fontSize:26 }}>🔍</div>
          <p style={{ fontSize:12, color:'#4a7a5e', textAlign:'center' }}>No scan data.<br/>Click Run Scan to analyse threats.</p>
        </div>
      ) : (
        <div className="anim-fade" style={{ flex:1, display:'flex', flexDirection:'column', gap:14 }}>
          {/* Level banner */}
          <div style={{ display:'flex', alignItems:'center', gap:10, background:cfg.bg, border:`1px solid ${cfg.b}`, borderRadius:12, padding:'13px 16px' }}>
            <Dot color={cfg.c} pulse={cfg.dp}/>
            <div style={{ flex:1 }}>
              <p style={{ fontSize:10, color:cfg.c, opacity:.6, textTransform:'uppercase', letterSpacing:'.07em', fontWeight:600 }}>Threat Level</p>
              <p style={{ fontSize:18, fontWeight:800, color:cfg.c }}>{lvl}</p>
            </div>
            {analysis.timestamp && <p style={{ fontSize:10, color:cfg.c, opacity:.45, fontFamily:'monospace' }}>{new Date(analysis.timestamp).toLocaleTimeString()}</p>}
          </div>

          {analysis.findings?.length > 0 && (
            <div>
              <p style={{ fontSize:10, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.07em', fontWeight:700, marginBottom:8 }}>Findings</p>
              <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                {analysis.findings.map((f,i) => (
                  <div key={i} style={{ display:'flex', gap:9, background:'#f8fdfb', border:'1px solid #e4f0e9', borderRadius:10, padding:'10px 13px' }}>
                    <span style={{ color:'#059669', flexShrink:0, marginTop:1 }}>•</span>
                    <p style={{ fontSize:12, color:'#0f1f16', lineHeight:1.5 }}>{f}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {analysis.remediations?.length > 0 && (
            <div>
              <p style={{ fontSize:10, color:'#8fb8a0', textTransform:'uppercase', letterSpacing:'.07em', fontWeight:700, marginBottom:8 }}>Recommended Actions</p>
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {analysis.remediations.map((r,i) => (
                  <button key={i} className="btn btn-ghost" style={{ fontSize:10, padding:'5px 10px', borderRadius:8 }}>{r}</button>
                ))}
              </div>
            </div>
          )}
          <p style={{ marginTop:'auto', fontSize:10, color:'#c4ddd0', fontFamily:'monospace' }}>Model: {analysis.backend||'gemini'}</p>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────
   SPEND INTELLIGENCE
───────────────────────────────────────── */
function IntelCard({ intelligence }) {
  if (!intelligence?.insights) return (
    <div className="card p20" style={{ display:'flex', alignItems:'center', justifyContent:'center', opacity:.4 }}>
      <p style={{ color:'#8fb8a0' }}>No insights yet</p>
    </div>
  );
  const ICONS = { recurring_payment:'🔄', price_increase:'📈', budget_forecast:'📊', category_breakdown:'🏷️', high_velocity:'⚡', unused_subscription:'💤' };
  return (
    <div className="card p20">
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <div>
          <p style={{ fontSize:15, fontWeight:700, color:'#0f1f16' }}>Spend Intelligence</p>
          <p style={{ fontSize:11, color:'#8fb8a0', marginTop:2 }}>AI-powered spending insights</p>
        </div>
        {intelligence.actionable_count > 0 && (
          <span style={{ fontSize:11, color:'#d97706', background:'#fffbeb', border:'1px solid #fde68a', padding:'4px 10px', borderRadius:8, fontWeight:700 }}>
            {intelligence.actionable_count} actionable
          </span>
        )}
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:8, overflowY:'auto' }}>
        {intelligence.insights.map((ins,i) => (
          <div key={i} className="insight-row" style={ ins.severity==='warning'
            ? { background:'#fffbeb', borderColor:'#fde68a' }
            : { background:'#f0fdf4', borderColor:'#e4f0e9' }}>
            <span style={{ fontSize:17, flexShrink:0 }}>{ICONS[ins.type]||'💡'}</span>
            <div style={{ flex:1 }}>
              <p style={{ fontSize:12, color:'#0f1f16', lineHeight:1.48 }}>{ins.message}</p>
              {ins.action && (
                <button className="btn btn-ghost" style={{ fontSize:10, padding:'3px 9px', borderRadius:7, marginTop:6 }}>
                  {ins.action.replace(/_/g,' ')} →
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   LEDGER
───────────────────────────────────────── */
function LedgerCard({ logs, verifResult, onVerify }) {
  const [exp, setExp] = useState(null);
  const evtStyle = t => {
    if (t?.includes('BLOCK')||t?.includes('DEATH')||t?.includes('KILL')) return { bg:'#fef2f2', c:'#dc2626', b:'#fecaca' };
    if (t?.includes('APPROVE')) return { bg:'#ecfdf5', c:'#059669', b:'#a7f3d0' };
    if (t?.includes('FREEZE'))  return { bg:'#fffbeb', c:'#d97706', b:'#fde68a' };
    return { bg:'#eff6ff', c:'#2563eb', b:'#bfdbfe' };
  };

  return (
    <div className="card p20" style={{ display:'flex', flexDirection:'column' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <div>
          <p style={{ fontSize:15, fontWeight:700, color:'#0f1f16' }}>Immutable Ledger</p>
          <p style={{ fontSize:11, color:'#8fb8a0', marginTop:2 }}>Tamper-proof audit chain</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          {verifResult && (
            <span className="badge" style={ verifResult.tampered
              ? { background:'#fef2f2', color:'#dc2626', borderColor:'#fecaca' }
              : { background:'#ecfdf5', color:'#059669', borderColor:'#a7f3d0' }}>
              {verifResult.tampered ? '⚠ Tampered' : '✓ Verified'}
            </span>
          )}
          <button className="btn btn-outline" style={{ padding:'6px 14px', fontSize:11 }} onClick={onVerify}>Verify Chain</button>
        </div>
      </div>

      {verifResult?.tampered && (
        <div style={{ background:'#fef2f2', border:'1px solid #fecaca', borderRadius:12, padding:'14px 16px', marginBottom:14 }}>
          <p style={{ fontSize:12, color:'#dc2626', fontWeight:700, marginBottom:10 }}>⚠ CRITICAL: Log tampering detected!</p>
          {[['Primary Store', verifResult.primary_intact, verifResult.primary_break_at],
            ['Immutable Store', verifResult.immutable_intact, verifResult.immutable_break_at],
            ['Synchronization', verifResult.stores_in_sync, null]].map(([l,ok,at]) => (
            <div key={l} style={{ display:'flex', justifyContent:'space-between', fontSize:12, marginBottom:5, fontFamily:'monospace' }}>
              <span style={{ color:'#8fb8a0' }}>{l}</span>
              <span style={{ color:ok?'#059669':'#dc2626', fontWeight:700 }}>
                {l==='Synchronization' ? (ok?'IN SYNC':'OUT OF SYNC') : ok?'OK':`BROKEN @ index ${at}`}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display:'flex', flexDirection:'column', gap:5, overflowY:'auto', maxHeight:420 }}>
        {!logs?.length ? (
          <div style={{ textAlign:'center', padding:'24px 0', opacity:.4 }}>
            <div style={{ fontSize:24, marginBottom:8 }}>📋</div>
            <p style={{ fontSize:12, color:'#4a7a5e' }}>Ledger is empty</p>
          </div>
        ) : logs.map((entry,i) => {
          const s = evtStyle(entry.event_type);
          return (
            <div key={entry.hash||i} className={`audit-row ${exp===i?'open':''}`} onClick={()=>setExp(exp===i?null:i)}>
              <span style={{ color:'#c4ddd0', fontSize:14 }}>⛓</span>
              <div style={{ flex:1, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span className="badge" style={{ background:s.bg, color:s.c, borderColor:s.b, fontSize:10 }}>{entry.event_type||'EVENT'}</span>
                <span style={{ fontSize:10, color:'#c4ddd0', fontFamily:'monospace' }}>
                  {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : ''}
                </span>
              </div>
              {exp===i && (
                <div className="anim-up" style={{ width:'100%', marginTop:10, background:'#f8fdfb', borderRadius:10, padding:12, border:'1px solid #e4f0e9' }}>
                  <p style={{ fontSize:10, fontFamily:'monospace', color:'#8fb8a0', wordBreak:'break-all', marginBottom:4 }}>
                    Hash: <span style={{ color:'#059669' }}>{entry.hash}</span>
                  </p>
                  <p style={{ fontSize:10, fontFamily:'monospace', color:'#c4ddd0', wordBreak:'break-all', marginBottom:8 }}>
                    Prev: {entry.previous_hash}
                  </p>
                  <pre style={{ fontSize:10, color:'#0f1f16', fontFamily:"'JetBrains Mono',monospace", whiteSpace:'pre-wrap', wordBreak:'break-all', lineHeight:1.55, background:'#f0faf5', borderRadius:8, padding:'10px 12px', border:'1px solid #e4f0e9' }}>
                    {JSON.stringify(entry.payload,null,2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   PENDING APPROVALS BANNER
───────────────────────────────────────── */
function PendingBanner({ pending, onApprove, onKill }) {
  if (!pending||!Object.keys(pending).length) return null;
  const entries = Object.entries(pending);
  return (
    <div className="card p20" style={{ border:'1px solid #fde68a', background:'rgba(255,255,255,.95)' }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:18 }}>
        <div style={{ width:36, height:36, borderRadius:10, background:'#fffbeb', border:'1px solid #fde68a', display:'flex', alignItems:'center', justifyContent:'center', fontSize:17 }}>⏳</div>
        <div style={{ flex:1 }}>
          <p style={{ fontSize:14, fontWeight:700, color:'#0f1f16' }}>Manual Intervention Required</p>
          <p style={{ fontSize:11, color:'#8fb8a0', marginTop:1 }}>These transactions need human approval before processing</p>
        </div>
        <span style={{ background:'#f59e0b', color:'#fff', fontSize:11, fontWeight:800, padding:'4px 12px', borderRadius:99, boxShadow:'0 2px 8px rgba(245,158,11,.35)' }}>
          {entries.length} PENDING
        </span>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))', gap:12 }}>
        {entries.map(([id,approval]) => (
          <div key={id} style={{ background:'#fffbeb', border:'1px solid #fde68a', borderRadius:14, padding:16 }}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:12 }}>
              <div>
                <p style={{ fontSize:14, fontWeight:700, color:'#0f1f16' }}>{approval.context?.merchant||'Unknown'}</p>
                <p style={{ fontSize:10, color:'#8fb8a0', fontFamily:'monospace', marginTop:2 }}>ID: {id.substring(0,12)}</p>
              </div>
              <div style={{ textAlign:'right' }}>
                <p style={{ fontSize:20, fontWeight:800, color:'#0f1f16', fontFamily:"'JetBrains Mono',monospace" }}>₹{(approval.context?.amount||0).toLocaleString()}</p>
                <p style={{ fontSize:10, color:'#8fb8a0' }}>{approval.created_at ? new Date(approval.created_at).toLocaleTimeString() : ''}</p>
              </div>
            </div>
            <div style={{ background:'rgba(255,255,255,.7)', borderRadius:10, padding:'10px 12px', border:'1px solid rgba(253,230,138,.5)', marginBottom:12 }}>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, marginBottom:6 }}>
                <span style={{ color:'#8fb8a0' }}>Risk Score</span>
                <RiskPill score={approval.context?.risk_score}/>
              </div>
              {approval.context?.reasons?.slice(0,2).map((r,i) => (
                <p key={i} style={{ fontSize:11, color:'#4a7a5e', display:'flex', gap:6, marginTop:4 }}>
                  <span style={{ color:'#d97706', flexShrink:0 }}>⚠</span>
                  <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r}</span>
                </p>
              ))}
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <button className="btn btn-primary" style={{ flex:1, borderRadius:9, fontSize:12, justifyContent:'center' }} onClick={()=>onApprove(id)}>✓ Approve</button>
              <button className="btn btn-danger"  style={{ flex:1, borderRadius:9, fontSize:12, justifyContent:'center' }} onClick={()=>onKill(id)}>✕ Block</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────
   PAGE VIEWS
───────────────────────────────────────── */
function DashboardView({ wallet, txns, aiAna, intel, ds, logs, verif, pending, onActions }) {
  return (
    <>
      <StatusStrip wallet={wallet} txns={txns} lastRefresh={onActions.lastRefresh} loading={onActions.loading} error={onActions.error}/>
      {Object.keys(pending).length > 0 && <PendingBanner pending={pending} onApprove={onActions.approve} onKill={onActions.block}/>}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1.3fr 1fr', gap:18, alignItems:'stretch' }}>
        <WalletCard wallet={wallet} onFreeze={onActions.freeze} onUnfreeze={onActions.unfreeze} onTopup={onActions.topup}/>
        <RiskCard transactions={txns}/>
        <ThreatCard analysis={aiAna} onRun={onActions.runAI}/>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1.4fr 1fr 1fr', gap:18 }}>
        <TxFeed transactions={txns} compact/>
        <IntelCard intelligence={intel}/>
        <KillSwitch status={ds} onTrigger={onActions.kill}/>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────
   MAIN APP
───────────────────────────────────────── */
export default function App() {
  const [tab, setTab]         = useState('home');
  const [wallet, setWallet]   = useState(null);
  const [walletId, setWId]    = useState(null);
  const [txns, setTxns]       = useState([]);
  const [logs, setLogs]       = useState([]);
  const [intel, setIntel]     = useState(null);
  const [aiAna, setAiAna]     = useState(null);
  const [ds, setDs]           = useState(null);
  const [pending, setPending] = useState({});
  const [verif, setVerif]     = useState(null);
  const [err, setErr]         = useState(null);
  const [refresh, setRefresh] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async()=>{
    try {
      let wId = walletId;
      if (!wId) { try { const s=await axios.post(`${API}/demo/seed`); wId=s.data.wallet_id; setWId(wId); } catch {} }
      const [wR,txR,auR,dsR,pR]=await Promise.all([
        wId?axios.get(`${API}/wallets/${wId}`).catch(()=>null):null,
        axios.get(`${API}/transactions?limit=50`).catch(()=>null),
        axios.get(`${API}/audit/logs?limit=50`).catch(()=>null),
        axios.get(`${API}/death-switch/status`).catch(()=>null),
        axios.get(`${API}/hitl/pending`).catch(()=>null),
      ]);
      if(wR?.data){setWallet(wR.data);if(!walletId)setWId(wR.data.id)}
      if(txR?.data) setTxns(txR.data.transactions||[]);
      if(auR?.data) setLogs(auR.data.entries||[]);
      if(dsR?.data) setDs(dsR.data);
      if(pR?.data)  setPending(pR.data.pending||{});
      if(wId){const iR=await axios.get(`${API}/intelligence/${wId}`).catch(()=>null);if(iR?.data)setIntel(iR.data)}
      setErr(null); setRefresh(new Date());
    } catch { setErr('Cannot reach backend'); }
    finally { setLoading(false); }
  },[walletId]);

  useEffect(()=>{fetchAll();const iv=setInterval(fetchAll,5000);return()=>clearInterval(iv)},[fetchAll]);

  const actions = {
    topup:    async a  => { if(!walletId||!a||+a<=0)return; await axios.post(`${API}/wallet/topup/${walletId}`,{amount:+a}); fetchAll(); },
    freeze:   async()  => { if(!walletId)return; await axios.post(`${API}/wallet/freeze/${walletId}`); fetchAll(); },
    unfreeze: async()  => { if(!walletId)return; await axios.post(`${API}/wallet/unfreeze/${walletId}`); fetchAll(); },
    kill:     async()  => { if(!walletId)return; await axios.post(`${API}/death-switch/trigger/${walletId}?reason=manual_dashboard_trigger`); fetchAll(); },
    verify:   async()  => { const r=await axios.get(`${API}/audit/verify`); setVerif(r.data); },
    runAI:    async()  => { const r=await axios.post(`${API}/intelligence/ai/run`); setAiAna(r.data); },
    approve:  async id => { await axios.post(`${API}/hitl/approve`,{approval_id:id,action:'approved'}); fetchAll(); },
    block:    async id => { await axios.post(`${API}/hitl/approve`,{approval_id:id,action:'killed'}); fetchAll(); },
    loading, error:err, lastRefresh:refresh,
  };

  const pendingCount = Object.keys(pending).length;

  /* Page titles per tab */
  const TITLES = {
    home:         ['Home',          'Welcome to LatentPay'],
    dashboard:    ['Dashboard',     'Welcome back \u2014 AI payment overview'],
    transactions: ['Transactions',  'Real-time feed of all payment events'],
    threats:      ['AI Threats',    'Gemini-powered threat detection and analysis'],
    intelligence: ['Intelligence',  'AI-generated spend insights and forecasts'],
    ledger:       ['Audit Ledger',  'Immutable, tamper-proof blockchain log'],
    kill:         ['Kill Switch',   'Emergency payment shutdown controls'],
  };
  const [title, subtitle] = TITLES[tab];

  return (
    <div className="layout">
      <Sidebar activeTab={tab} setActiveTab={setTab} pendingCount={pendingCount}/>

      <main className="main">
        {/* Connection indicator */}
        <div style={{ position:'fixed', top:16, right:28, zIndex:40, display:'flex', alignItems:'center', gap:6,
          background:'rgba(255,255,255,.85)', backdropFilter:'blur(12px)', border:'1px solid #e4f0e9',
          borderRadius:99, padding:'6px 14px', boxShadow:'0 2px 10px rgba(0,0,0,.05)' }}>
          {loading ? (
            <>
              <div style={{ width:8, height:8, borderRadius:'50%', border:'2px solid #059669', borderTopColor:'transparent', animation:'spin .8s linear infinite' }}/>
              <span style={{ fontSize:11, color:'#4a7a5e', fontWeight:500 }}>Syncing…</span>
            </>
          ) : err ? (
            <><Dot color="#dc2626" pulse="r"/><span style={{ fontSize:11, color:'#b91c1c', fontWeight:500 }}>Offline</span></>
          ) : (
            <><Dot color="#059669" pulse="g"/><span style={{ fontSize:11, color:'#059669', fontWeight:600 }}>{refresh?.toLocaleTimeString()||'Live'}</span></>
          )}
        </div>

        {/* Page header */}
        <div style={{ paddingTop:4 }}>
          <h1 style={{ fontSize:22, fontWeight:800, color:'#0f1f16', letterSpacing:'-.5px' }}>{title}</h1>
          <p style={{ fontSize:12, color:'#8fb8a0', marginTop:3 }}>{subtitle}</p>
        </div>

        {/* Tab views */}
        <div className="anim-up" key={tab}>
          {tab === 'dashboard' && (
            <DashboardView wallet={wallet} txns={txns} aiAna={aiAna} intel={intel} ds={ds} logs={logs} verif={verif} pending={pending} onActions={actions}/>
          )}

          {tab === 'transactions' && (
            <>
              <StatusStrip wallet={wallet} txns={txns} lastRefresh={refresh} loading={loading} error={err}/>
              <TxFeed transactions={txns}/>
            </>
          )}

          {tab === 'home' && (
            <HomePage wallet={wallet} transactions={txns} setTab={setTab}/>
          )}

          {tab === 'threats' && (
            <>
              {pendingCount > 0 && <PendingBanner pending={pending} onApprove={actions.approve} onKill={actions.block}/>}
              <ThreatCard analysis={aiAna} onRun={actions.runAI}/>
            </>
          )}

          {tab === 'intelligence' && (
            <>
              <StatusStrip wallet={wallet} txns={txns} lastRefresh={refresh} loading={loading} error={err}/>
              <IntelCard intelligence={intel}/>
            </>
          )}

          {tab === 'ledger' && (
            <LedgerCard logs={logs} verifResult={verif} onVerify={actions.verify}/>
          )}

          {tab === 'kill' && (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:18, maxWidth:860 }}>
              <WalletCard wallet={wallet} onFreeze={actions.freeze} onUnfreeze={actions.unfreeze} onTopup={actions.topup}/>
              <KillSwitch status={ds} onTrigger={actions.kill}/>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ marginTop:'auto', paddingTop:20, borderTop:'1px solid #e4f0e9', display:'flex', justifyContent:'space-between' }}>
          <p style={{ fontSize:11, color:'#c4ddd0' }}>LatentPay v2.0 · Pine Labs AI Hackathon 2026</p>
          <p style={{ fontSize:11, color:'#c4ddd0' }}>🔒 Tamper-proof audit · Auto-refresh 5s</p>
        </div>
      </main>
    </div>
  );
}
