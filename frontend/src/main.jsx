import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api, money } from './api'
import './styles.css'

const nav = [
  ['dashboard','داشبورد','⌂'], ['customers','مشتریان','◉'], ['import','آپلود فایل','⇧'],
  ['promises','وعده‌ها','▣'], ['telegram','تلگرام','➤']
]

function Card({label, value, hint, tone=''}) { return <div className={`kpi ${tone}`}><div><span>{label}</span><b>{value}</b><small>{hint}</small></div><i>•</i></div> }
function Status({value}) {
  const map={active:['فعال','blue'],settled:['تسویه شده','green'],promised:['وعده داده','yellow'],overdue:['عقب‌افتاده','red'],awaiting_date:['منتظر تاریخ','gray'],paid:['پرداخت شد','green'],cancelled:['لغو شده','gray']}
  const x=map[value]||[value,'gray']; return <span className={`badge ${x[1]}`}>{x[0]}</span>
}
function Notice({type='ok', children}) { return children ? <div className={`notice ${type}`}>{children}</div> : null }

function App(){
  const [page,setPage]=useState('dashboard'), [stats,setStats]=useState({}), [customers,setCustomers]=useState([]), [promises,setPromises]=useState([])
  const [loading,setLoading]=useState(false), [notice,setNotice]=useState(''), [search,setSearch]=useState(''), [preview,setPreview]=useState(null), [telegram,setTelegram]=useState({})
  const refresh=async()=>{
    const [s,c,p,t]=await Promise.all([api.get('/dashboard'),api.get('/customers'),api.get('/promises'),api.get('/telegram/status')])
    setStats(s.data); setCustomers(c.data); setPromises(p.data); setTelegram(t.data)
  }
  useEffect(()=>{refresh().catch(e=>setNotice(e.message))},[])
  const filtered=useMemo(()=>customers.filter(c=>c.name.includes(search)),[customers,search])
  const send=async(id)=>{ setLoading(true); try{await api.post(`/customers/${id}/send`);setNotice('پیام پیگیری ارسال شد.');await refresh()}catch(e){setNotice(e.response?.data?.detail||e.message)}finally{setLoading(false)} }
  const sendAll=async()=>{if(!confirm('برای تمام بدهکارانی که گروه متصل دارند پیام ارسال شود؟'))return;setLoading(true);try{const {data}=await api.post('/followups/start');setNotice(`${data.sent} پیام ارسال شد؛ ${data.skipped} مورد رد شد.`);await refresh()}catch(e){setNotice(e.response?.data?.detail||e.message)}finally{setLoading(false)}}
  const patchCustomer=async(id,body)=>{await api.patch(`/customers/${id}`,body);await refresh()}
  const doPreview=async(e)=>{const file=e.target.files?.[0];if(!file)return;const fd=new FormData();fd.append('file',file);setLoading(true);try{const {data}=await api.post('/import/preview',fd);setPreview(data);setPage('import')}catch(err){setNotice(err.response?.data?.detail||err.message)}finally{setLoading(false)}}
  const commit=async()=>{setLoading(true);try{const {data}=await api.post('/import/commit',preview);setNotice(`${data.inserted} مشتری جدید و ${data.updated} مشتری بروزرسانی شد.`);setPreview(null);await refresh();setPage('customers')}catch(e){setNotice(e.response?.data?.detail||e.message)}finally{setLoading(false)}}
  return <div className="app">
    <aside><div className="brand"><div className="logo">₮</div><div><b>پیگیری مطالبات</b><small>Debt Collector</small></div></div>
      <nav>{nav.map(([id,label,icon])=><button key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><span>{icon}</span>{label}</button>)}</nav>
      <div className="side-foot"><span className={`dot ${telegram.running?'on':''}`}></span>{telegram.running?`@${telegram.username}`:'ربات غیرفعال'}</div>
    </aside>
    <main>
      <header><div><h1>{nav.find(x=>x[0]===page)?.[1]}</h1><p>مدیریت ساده، سریع و دقیق وصول مطالبات</p></div><div className="header-actions"><label className="btn primary">＋ آپلود فایل<input hidden type="file" accept=".xlsx,.pdf" onChange={doPreview}/></label><button className="btn" disabled={loading} onClick={sendAll}>▷ شروع پیگیری</button></div></header>
      <Notice type={notice.includes('ارسال')||notice.includes('بروزرسانی')?'ok':'warn'}>{notice}</Notice>
      {page==='dashboard'&&<Dashboard stats={stats} customers={customers} send={send} loading={loading}/>} 
      {page==='customers'&&<Customers rows={filtered} search={search} setSearch={setSearch} patch={patchCustomer} send={send}/>} 
      {page==='import'&&<ImportPanel preview={preview} setPreview={setPreview} onFile={doPreview} commit={commit} loading={loading}/>} 
      {page==='promises'&&<Promises rows={promises} refresh={refresh}/>} 
      {page==='telegram'&&<Telegram status={telegram} customers={customers}/>} 
    </main>
  </div>
}

function Dashboard({stats,customers,send,loading}){return <>
  <section className="kpis">
    <Card label="کل بدهکاران" value={stats.debtors??0} hint={`${money(stats.total_debt)} تومان`} />
    <Card label="گروه‌های متصل" value={stats.connected??0} hint="آماده ارسال" tone="purple"/>
    <Card label="بدون پاسخ" value={stats.no_reply??0} hint="نیاز به پیگیری" tone="yellow"/>
    <Card label="وعده‌های باز" value={stats.promised??0} hint="در انتظار واریز" tone="blue"/>
    <Card label="عقب‌افتاده" value={stats.overdue??0} hint="نیاز به اقدام" tone="red"/>
  </section>
  <section className="panel"><div className="panel-head"><div><h2>بدهکاران اصلی</h2><p>مرتب‌شده بر اساس مبلغ مانده حساب</p></div></div><CustomerTable rows={customers.slice(0,8)} send={send} loading={loading}/></section>
</>}

function CustomerTable({rows,send,loading,patch}){return <div className="table-wrap"><table><thead><tr><th>مشتری</th><th>مبلغ بدهی</th><th>گروه تلگرام</th><th>وضعیت</th><th>آخرین پاسخ</th><th></th></tr></thead><tbody>{rows.map(c=><tr key={c.id}><td><strong>{c.name}</strong><small>#{c.id}{c.external_id?` · ${c.external_id}`:''}</small></td><td><b>{money(c.debt_amount)}</b><small>تومان</small></td><td>{c.telegram_chat_id?<><span className="tg">➤</span>{c.telegram_group_title||c.telegram_chat_id}</>:<span className="muted">متصل نیست</span>}</td><td><Status value={c.status}/>{c.collection_active?<small>پیگیری فعال</small>:null}</td><td>{c.last_reply_at?<span dir="ltr">{new Date(c.last_reply_at).toLocaleDateString('fa-IR')}</span>:<span className="muted">—</span>}</td><td><button className="mini" disabled={loading||!c.telegram_chat_id} onClick={()=>send(c.id)}>ارسال پیام</button></td></tr>)}</tbody></table>{!rows.length&&<div className="empty">هنوز مشتری ثبت نشده است.</div>}</div>}

function Customers({rows,search,setSearch,patch,send}){const [edit,setEdit]=useState(null);return <section className="panel"><div className="panel-head"><div><h2>مشتریان</h2><p>اتصال گروه تلگرام و مدیریت مانده حساب</p></div><input className="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="جستجوی مشتری..."/></div>
<CustomerTable rows={rows} send={send}/>
<div className="cards-list">{rows.map(c=><div className="customer-edit" key={c.id}><div><b>{c.name}</b><small>برای اتصال از داخل گروه می‌توانید <code>/bind {c.id}</code> بزنید.</small></div><button className="mini" onClick={()=>setEdit(edit===c.id?null:c.id)}>ویرایش اتصال</button>{edit===c.id&&<GroupForm customer={c} patch={patch}/>}</div>)}</div></section>}
function GroupForm({customer,patch}){const [chat,setChat]=useState(customer.telegram_chat_id||''),[title,setTitle]=useState(customer.telegram_group_title||'');return <form className="group-form" onSubmit={async e=>{e.preventDefault();await patch(customer.id,{telegram_chat_id:chat||null,telegram_group_title:title});}}><input value={title} onChange={e=>setTitle(e.target.value)} placeholder="نام گروه"/><input dir="ltr" value={chat} onChange={e=>setChat(e.target.value)} placeholder="Chat ID مثل -100..."/><button className="btn primary">ذخیره</button></form>}

function ImportPanel({preview,onFile,commit,loading}){return <section className="panel import"><div className="drop"><div className="upload-icon">⇧</div><h2>فایل بدهکاران را وارد کنید</h2><p>نسخه اول XLSX و PDF را می‌خواند. برای بیشترین دقت، Excel پیشنهاد می‌شود.</p><label className="btn primary">انتخاب فایل<input hidden type="file" accept=".xlsx,.pdf" onChange={onFile}/></label></div>{preview&&<><div className="preview-head"><div><h3>{preview.filename}</h3><p>{preview.total} ردیف تشخیص داده شد</p></div><button disabled={loading||!preview.rows.length} className="btn primary" onClick={commit}>ثبت در سیستم</button></div>{preview.warnings?.map((w,i)=><Notice key={i} type="warn">{w}</Notice>)}<div className="table-wrap"><table><thead><tr><th>کد</th><th>نام مشتری</th><th>بدهی</th></tr></thead><tbody>{preview.rows.slice(0,50).map((r,i)=><tr key={i}><td>{r.external_id||'—'}</td><td>{r.name}</td><td>{money(r.debt_amount)} تومان</td></tr>)}</tbody></table></div></>}</section>}

function Promises({rows,refresh}){const change=async(id,status)=>{await api.patch(`/promises/${id}`,{status});refresh()};return <section className="panel"><div className="panel-head"><div><h2>وعده‌های پرداخت</h2><p>تاریخ انتخاب‌شده توسط مشتری در ربات</p></div></div><div className="table-wrap"><table><thead><tr><th>مشتری</th><th>مبلغ</th><th>تاریخ شمسی</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>{rows.map(p=><tr key={p.id}><td><b>{p.customer_name}</b></td><td>{money(p.amount)} تومان</td><td>{p.due_date_jalali||'منتظر انتخاب'}</td><td><Status value={p.status}/></td><td><select value={p.status} onChange={e=>change(p.id,e.target.value)}><option value="awaiting_date">منتظر تاریخ</option><option value="promised">وعده داده</option><option value="paid">پرداخت شد</option><option value="overdue">عقب‌افتاده</option><option value="cancelled">لغو</option></select></td></tr>)}</tbody></table>{!rows.length&&<div className="empty">هنوز وعده‌ای ثبت نشده است.</div>}</div></section>}

function Telegram({status,customers}){return <div className="telegram-grid"><section className="panel"><h2>وضعیت ربات</h2><div className={`bot-state ${status.running?'ok':'off'}`}><span>➤</span><div><b>{status.running?'ربات آنلاین است':'ربات فعال نیست'}</b><p>{status.running?`@${status.username}`:'TELEGRAM_BOT_TOKEN را در فایل .env قرار دهید.'}</p></div></div>{status.running&&!status.admin_lock?<div className="notice warn">برای امنیت، TELEGRAM_ADMIN_IDS را در .env تنظیم کنید. شناسه خودتان را با /myid از ربات بگیرید.</div>:null}<h3>اتصال یک گروه</h3><ol><li>ربات را به گروه مشتری اضافه کنید.</li><li>در BotFather، Privacy Mode را غیرفعال کنید تا پاسخ‌های گروه دریافت شود.</li><li>داخل گروه دستور <code>/bind ID</code> را ارسال کنید.</li></ol></section><section className="panel"><h2>شناسه مشتری‌ها</h2><div className="bind-list">{customers.map(c=><div key={c.id}><span>{c.name}</span><code>/bind {c.id}</code></div>)}</div></section></div>}

createRoot(document.getElementById('root')).render(<App />)
