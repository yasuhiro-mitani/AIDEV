// Countdown App (multi-target)
// Data model in localStorage under key 'countdownTargets'

const STORAGE_KEY = 'countdownTargetsV1';
const form = document.getElementById('target-form');
const listEl = document.getElementById('countdown-list');
const template = document.getElementById('countdown-item-template');

// Push elements
const pushStatusEl = document.getElementById('push-status');
const btnSub = document.getElementById('push-subscribe-btn');
const btnUnsub = document.getElementById('push-unsubscribe-btn');
const btnTest = document.getElementById('push-test-btn');

let targets = load();

function load(){
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch(e){ return []; }
}
function save(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(targets)); }

function humanDiff(ms){
  if(ms <= 0) return '0d 00:00:00';
  const sec = Math.floor(ms/1000);
  const d = Math.floor(sec/86400);
  const h = Math.floor((sec%86400)/3600);
  const m = Math.floor((sec%3600)/60);
  const s = sec%60;
  return `${d}d ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function render(){
  listEl.innerHTML = '';
  const now = Date.now();
  targets.sort((a,b)=> a.timestamp - b.timestamp);
  for(const t of targets){
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.id = t.id;
    node.querySelector('.item-title').textContent = t.title;
    const diff = t.timestamp - now;
    const timeEl = node.querySelector('.time-remaining');
    timeEl.textContent = diff <= 0 ? timeEl.dataset.finishedText : humanDiff(diff);
    if(diff <= 0) timeEl.classList.add('finished');
    const dateEl = node.querySelector('.target-date');
    dateEl.textContent = new Date(t.timestamp).toLocaleString();
    const notifyEl = node.querySelector('.notify-status');
    notifyEl.textContent = t.dailyNotify ? '毎朝通知: ON (Beta)' : '';
    node.querySelector('.remove-btn').addEventListener('click', ()=> removeTarget(t.id));
    listEl.appendChild(node);
  }
}

function addTarget(title, datetime, dailyNotify){
  const ts = new Date(datetime).getTime();
  if(isNaN(ts)) return alert('日付が不正です');
  targets.push({ id: crypto.randomUUID(), title, timestamp: ts, dailyNotify: !!dailyNotify });
  save();
  render();
}

function removeTarget(id){
  targets = targets.filter(t=> t.id !== id);
  save();
  render();
}

form.addEventListener('submit', e=>{
  e.preventDefault();
  const title = document.getElementById('title').value.trim();
  const dt = document.getElementById('datetime').value;
  const daily = document.getElementById('dailyNotify').checked;
  if(!title) return;
  addTarget(title, dt, daily);
  form.reset();
});

// Live update
setInterval(()=>{
  const now = Date.now();
  for(const li of listEl.children){
    const id = li.dataset.id; const t = targets.find(t=> t.id === id); if(!t) continue;
    const diff = t.timestamp - now;
    const timeEl = li.querySelector('.time-remaining');
    timeEl.textContent = diff <= 0 ? timeEl.dataset.finishedText : humanDiff(diff);
    if(diff <= 0) timeEl.classList.add('finished');
  }
}, 1000);

// Register service worker (basic offline)
if('serviceWorker' in navigator){
  window.addEventListener('load', ()=>{
    navigator.serviceWorker.register('./service-worker.js').catch(console.error);
  });
}

render();

// Push subscription logic
async function getPublicKey(){
  const r = await fetch('/api/push/public-key');
  const j = await r.json();
  return j.publicKey;
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

async function currentSubscription(){
  if(!('serviceWorker' in navigator)) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

function updatePushUI(state){
  pushStatusEl.textContent = state;
  const subscribed = state.startsWith('購読中');
  btnSub.disabled = subscribed;
  btnUnsub.disabled = !subscribed;
  btnTest.disabled = !subscribed;
}

async function subscribe(){
  if(Notification.permission === 'denied') return alert('通知がブロックされています (ブラウザ設定を確認)');
  if(Notification.permission !== 'granted'){
    const perm = await Notification.requestPermission();
    if(perm !== 'granted') return;
  }
  const key = await getPublicKey();
  if(!key || key.startsWith('REPLACE_ME')) return alert('サーバのVAPIDキーが設定されていません');
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) });
  await fetch('/api/push/subscribe', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(sub) });
  updatePushUI('購読中');
}

async function unsubscribe(){
  const sub = await currentSubscription();
  if(!sub) return;
  await fetch('/api/push/subscribe', { method:'DELETE', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ endpoint: sub.endpoint }) });
  await sub.unsubscribe();
  updatePushUI('未登録');
}

async function initPush(){
  if(!('serviceWorker' in navigator) || !('PushManager' in window)){
    updatePushUI('未対応ブラウザ');
    btnSub.disabled = btnUnsub.disabled = btnTest.disabled = true;
    return;
  }
  const sub = await currentSubscription();
  updatePushUI(sub ? '購読中' : '未登録');
}

btnSub?.addEventListener('click', subscribe);
btnUnsub?.addEventListener('click', unsubscribe);
btnTest?.addEventListener('click', async ()=>{
  await fetch('/api/push/test', { method:'POST' });
  alert('テスト通知送信リクエストを送信しました');
});

initPush();
