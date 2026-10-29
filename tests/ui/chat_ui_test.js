const {JSDOM} = require('jsdom');
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');

let fails = 0, passes = 0;
const ok = (c, m) => { if (c) passes++; else { fails++; console.log('FAIL:', m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));

function boot(handler) {
  const calls = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', url: 'http://127.0.0.1:8000/static/chat.html',
    beforeParse(w) {
      w.fetch = async (url, opt = {}) => {
        const path = url.replace('http://127.0.0.1:8000', '');
        const body = opt.body && typeof opt.body === 'string' ? JSON.parse(opt.body) : opt.body;
        calls.push({path, method: opt.method || 'GET', body, headers: opt.headers});
        const r = await handler(path, opt, body);
        return {ok: r.status < 400, status: r.status, json: async () => r.json};
      };
      w.HTMLElement.prototype.scrollIntoView = () => {};
      w.requestAnimationFrame = f => setTimeout(f, 0);
    }
  });
  // jsdom lacks requestSubmit in some versions
  const d = dom.window.document;
  return {dom, d, w: dom.window, calls};
}
const general = (answer, extra = {}) => ({status: 200, json: Object.assign({
  run_id: 'r1', status: 'general_answer', source: 'general', answer, note: 'Nothing in your documents answers this, so this reply comes from general knowledge.',
  citations: [], evidence: [], verification: null, model: 'qwen2.5:3b', saved: true,
  trace: {route: 'general'}, timings_ms: {total: 3200}}, extra)});
const docAnswer = () => ({status: 200, json: {
  run_id: 'r2', status: 'answered', source: 'documents', answer: 'It uses pgvector [1].', saved: true, model: 'qwen2.5:3b',
  citations: [{n: 1, chunk_id: 'c1', filename: 'design_v1.md', label: 'v1', heading_path: 'Storage'}],
  verification: [{claim: 'It uses pgvector.', verdict: 'supported', better_sources: []}],
  trace: {route: 'vector', gate_vector_score: 0.8, gate_threshold: 0.6, retrieve_ms: 10, generate_ms: 2000, verify_ms: 500},
  timings_ms: {total: 2600}}});

async function send(env, text) {
  const q = env.d.getElementById('q');
  q.value = text;
  q.dispatchEvent(new env.w.Event('input'));
  const ev = new env.w.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true});
  q.dispatchEvent(ev);
  await sleep(60);
  return ev;
}

(async () => {
  // ---------- layout ----------
  {
    const env = boot(async () => ({status: 200, json: {}}));
    await sleep(30);
    const kids = Array.from(env.d.body.children).map(e => e.tagName);
    ok(kids.indexOf('FOOTER') > kids.indexOf('MAIN'), 'composer (footer) comes after the conversation');
    ok(env.d.getElementById('q').tagName === 'TEXTAREA', 'input is a textarea');
    ok(env.d.querySelector('.empty h2').textContent.includes('How can I help'), 'empty state shown');
    ok(/\nbody\{[^}]*overflow:hidden/.test(html), 'page itself does not scroll (composer stays pinned)');
    ok(env.d.getElementById('scope').options.length === 3, 'three answer scopes');
  }

  // ---------- general answer + markdown + history + XSS ----------
  {
    const answers = [
      general('Here is **bold**, `code` and a list:\n\n- one\n- two\n\n```python\nprint("hi")\n```\n\n<img src=x onerror="window.__xss=1"> <script>window.__xss=2</script>'),
      general('Second answer.')];
    const env = boot(async (p) => p === '/api/v1/chat' ? answers.shift() : {status: 200, json: {chat_model: 'qwen2.5:3b', provider: 'ollama'}});
    await sleep(40);
    const ev = await send(env, 'Explain RAG');
    ok(ev.defaultPrevented, 'Enter submits (not a newline)');
    await sleep(80);
    const chatCalls = () => env.calls.filter(c => c.path === '/api/v1/chat');
    ok(chatCalls().length === 1, 'one chat request sent');
    const b1 = chatCalls()[0].body;
    ok(b1.message === 'Explain RAG' && b1.scope === 'auto' && Array.isArray(b1.history) && b1.history.length === 0, 'first request: message, scope auto, empty history');
    ok(b1.workspace_id === 'demo-workspace', 'workspace sent when set');
    ok(chatCalls()[0].headers['X-User-Id'] === 'demo-user', 'user header sent');
    ok(!env.d.querySelector('.empty'), 'empty state removed after first message');
    const bot = env.d.querySelector('.a:not(.err) .b:not(.dots)');
    ok(bot && bot.querySelector('strong') && bot.querySelector('strong').textContent === 'bold', 'bold rendered');
    ok(bot.querySelector('p code') && bot.querySelector('p code').textContent === 'code', 'inline code rendered');
    ok(bot.querySelectorAll('ul li').length === 2, 'bullet list rendered');
    ok(bot.querySelector('pre code').textContent === 'print("hi")', 'code block rendered without the language tag');
    ok(bot.querySelector('.copy'), 'copy button on code block');
    ok(!bot.querySelector('img') && !bot.querySelector('script'), 'HTML in the answer is NOT turned into elements');
    ok(bot.textContent.includes('<img src=x'), 'HTML shown as plain text');
    ok(env.w.__xss === undefined, 'no script executed (XSS)');
    ok(env.d.querySelector('.badge.gen'), 'general badge shown');
    ok(env.d.body.textContent.includes('Nothing in your documents answers this'), 'fallback note shown');
    ok(env.d.querySelector('.fb'), 'feedback shown for a saved general answer');
    ok(env.d.body.textContent.includes('general · qwen2.5:3b'), 'meta line names the model');
    ok(env.d.getElementById('modelinfo').textContent.includes('qwen2.5:3b (ollama)'), 'active model shown in settings');

    await send(env, 'And a follow up?');
    await sleep(80);
    const b2 = chatCalls()[1].body;
    ok(b2.history.length === 2 && b2.history[0].role === 'user' && b2.history[0].content === 'Explain RAG' && b2.history[1].role === 'assistant', 'second request carries the first exchange as history');

    // scope + settings persisted and sent
    env.d.getElementById('scope').value = 'general';
    env.d.getElementById('scope').dispatchEvent(new env.w.Event('change'));
    answers.push(general('Third.'));
    await send(env, 'Third question');
    await sleep(80);
    ok(chatCalls()[2].body.scope === 'general', 'scope selector value is sent');
    ok(env.w.localStorage.getItem('nx_scope') === 'general', 'scope remembered');

    // new chat clears history
    env.d.getElementById('newchat').click();
    ok(!!env.d.querySelector('.empty') && env.d.querySelectorAll('.u').length === 0, 'New chat clears the conversation');
    answers.push(general('Fresh.'));
    await send(env, 'After reset');
    await sleep(80);
    ok(chatCalls()[3].body.history.length === 0, 'New chat also clears the history sent to the model');
  }

  // ---------- document answer ----------
  {
    const env = boot(async (p) => p === '/api/v1/chat' ? docAnswer() : {status: 200, json: {text: 'Passage text'}});
    await sleep(30);
    await send(env, 'What stores embeddings?');
    await sleep(80);
    ok(env.d.querySelector('.badge.doc'), 'documents badge shown');
    ok(env.d.querySelector('.chip') && env.d.querySelector('.chip').textContent.includes('design_v1.md'), 'citation chip shown');
    ok(env.d.querySelector('.s-supported'), 'claim check shown');
    ok(env.d.body.textContent.includes('search: vector') && env.d.body.textContent.includes('verify 0.5 s'), 'search/timing line shown');
    env.d.querySelector('.chip button').click();
    await sleep(60);
    ok(env.d.querySelector('.pass').textContent === 'Passage text', 'View passage loads the chunk');
    ok(env.calls.some(c => c.path === '/api/v1/chunks/c1'), 'chunk endpoint called');
  }

  // ---------- unsaved general answer: no feedback buttons ----------
  {
    const env = boot(async () => general('No workspace answer', {saved: false}));
    await sleep(30);
    await send(env, 'hello');
    await sleep(80);
    ok(!env.d.querySelector('.fb'), 'no feedback buttons when the run was not saved');
  }

  // ---------- errors ----------
  for (const [status, json, expect] of [
    [503, {detail: 'The language-model service returned 401: the API key was rejected (check LLM_API_KEY).'}, 'API key was rejected'],
    [404, {detail: 'Workspace not found'}, 'Workspace not found for this user'],
    [429, {}, 'Too many requests'],
    [422, {}, 'too long'],
    [500, {}, 'error (500)']]) {
    const env = boot(async () => ({status, json}));
    await sleep(30);
    await send(env, 'hi');
    await sleep(80);
    ok(env.d.querySelector('.a.err .b') && env.d.querySelector('.a.err .b').textContent.includes(expect), `error ${status} explained`);
    ok(!env.d.getElementById('send').disabled, `send re-enabled after ${status}`);
    ok(!env.d.querySelector('.dots'), `waiting indicator removed after ${status}`);
  }
  {
    const env = boot(async () => { throw new Error('network'); });
    await sleep(30);
    await send(env, 'hi');
    await sleep(80);
    ok(env.d.querySelector('.a.err .b').textContent.includes('Cannot reach the Nexus server'), 'network failure explained');
  }

  // ---------- input behaviour ----------
  {
    const env = boot(async () => general('x'));
    await sleep(30);
    const q = env.d.getElementById('q');
    q.value = 'line one';
    const ev = new env.w.KeyboardEvent('keydown', {key: 'Enter', shiftKey: true, bubbles: true, cancelable: true});
    q.dispatchEvent(ev);
    await sleep(40);
    ok(!ev.defaultPrevented && env.calls.filter(c => c.path === '/api/v1/chat').length === 0, 'Shift+Enter does not send');
    q.value = '   ';
    q.dispatchEvent(new env.w.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
    await sleep(40);
    ok(env.calls.filter(c => c.path === '/api/v1/chat').length === 0, 'blank message is not sent');
  }
  {
    // empty workspace -> no workspace_id in the request
    const env = boot(async () => general('x'));
    await sleep(30);
    env.d.getElementById('ws').value = '';
    await send(env, 'hello');
    await sleep(80);
    ok(!('workspace_id' in env.calls.find(c => c.path === '/api/v1/chat').body), 'no workspace_id sent when the box is empty');
  }

  // ---------- upload creates a workspace when none is set ----------
  {
    const seq = [];
    const env = boot(async (p, opt) => {
      seq.push(opt.method + ' ' + p.split('?')[0]);
      if (p === '/api/v1/workspaces') return {status: 200, json: {workspace_id: 'new-ws'}};
      if (p.startsWith('/api/v1/documents/upload')) return {status: 200, json: {status: 'ok'}};
      if (p.includes('/index')) return {status: 200, json: {}};
      return {status: 200, json: {}};
    });
    await sleep(30);
    env.d.getElementById('ws').value = '';
    const file = new env.w.File(['hello'], 'a.md', {type: 'text/markdown'});
    Object.defineProperty(env.d.getElementById('file'), 'files', {value: [file], configurable: true});
    env.d.getElementById('file').dispatchEvent(new env.w.Event('change'));
    await sleep(150);
    ok(seq.indexOf('POST /api/v1/workspaces') < seq.indexOf('POST /api/v1/documents/upload') && seq.some(s => s.includes('/index')), 'upload: workspace created first, then upload, then index');
    ok(env.d.getElementById('ws').value === 'new-ws', 'new workspace id filled in');
    ok(env.d.body.textContent.includes('1 file(s) added and indexed'), 'upload success message');
  }

  console.log(`\nUI checks: ${passes} passed, ${fails} failed`);
  process.exit(fails ? 1 : 0);
})();
