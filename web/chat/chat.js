/* Same-origin chat client. The server owns tool selection, identity and event updates. */
(function () {
  'use strict';
  const el = id => document.getElementById(id);
  const messages = el('messages'), input = el('message-input'), catSelect = el('cat-select'), recorderSelect = el('recorder-select');
  const frames = new Map();
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null, listening = false, voiceDraft = '', voiceFinal = '', voiceGeneration = 0;
  function clearVoiceChoices() { el('voice-alternatives').replaceChildren(); el('voice-alternatives').hidden = true; }
  function voiceChoices(choices) {
    clearVoiceChoices();
    for (const text of [...new Set(choices)].filter(t => t && t !== input.value).slice(0, 5)) {
      const button = node('button', 'Use: ' + text, 'secondary'); button.type = 'button';
      button.disabled = listening;
      button.addEventListener('click', () => {
        if (input.disabled) return;
        input.value = text; clearVoiceChoices(); syncDisplay('draft', text);
        status('Suggested transcript selected. Check the pet, action and time before sending.'); input.focus();
      });
      el('voice-alternatives').append(button);
    }
    el('voice-alternatives').hidden = !el('voice-alternatives').children.length;
  }
  // Suggestions only: never silently rewrite a health or care record.
  function feedingSuggestion(text) {
    const pet = [...catSelect.options].find(option => option.value && option.value === catSelect.value)?.textContent;
    if (!pet || !/^[a-z]+$/i.test(pet)) return null;
    const match = text.match(/^(?:i|eye|are)\s+fed\s+([a-z]+)\b(.*)$/i);
    if (!match) return null;
    const a = match[1].toLowerCase(), b = pet.toLowerCase();
    const row = Array.from({length:b.length + 1}, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let diagonal = row[0]; row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const previous = row[j]; row[j] = Math.min(row[j] + 1, row[j-1] + 1, diagonal + (a[i-1] === b[j-1] ? 0 : 1)); diagonal = previous;
      }
    }
    if (a !== b && (Math.min(a.length,b.length) < 3 || row[b.length] > 1)) return null;
    return 'I fed ' + pet + match[2];
  }
  function clearDisplay() {
    for (const entry of frames.values()) clearTimeout(entry.timer);
    frames.clear(); el('echo-content').replaceChildren(); el('echo-empty').hidden = true;
  }
  function syncDisplay(role, text, signals = [], extras = []) {
    clearDisplay();
    const summary = node('section', undefined, 'echo-conversation');
    summary.append(node('span', role === 'draft' ? 'VOICE DRAFT · NOT SENT' : role === 'user' ? 'YOU · AWAITING RESPONSE' : 'PURR NANNY · LATEST RESPONSE', 'eyebrow'));
    for (const signal of signals) summary.append(node('p', signal.text, 'safety-signals'));
    summary.append(node('p', text, 'message-text'));
    for (const extra of extras) summary.append(node('p', extra.text, 'follow-up'));
    el('echo-content').append(summary); el('echo-content').parentElement && (el('echo-content').parentElement.scrollTop = 0);
  }
  function stopVoice(discard = false) {
    if (!recognition) return;
    if (discard) { voiceGeneration++; recognition.abort(); recognition = null; listening = false; controls(); }
    else recognition.stop();
  }

  let busy = false, connected = false, conversationId = null, pending = null, pendingPet = null;
  const cardRoutes = {get_today:'/apps/today.html',get_vet_summary:'/apps/vet-summary.html'};
  const cardNames = {get_today:'Today’s care',get_vet_summary:'Veterinary summary'};
  function node(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  }
  function scrollToLatest() { messages.scrollTop = messages.scrollHeight; }
  function status(text) { el('request-status').textContent = text; el('echo-status').textContent = text; }
  function controls() {
    el('add-pet').disabled = busy || !connected || !!pending || listening;
    input.disabled = busy || !connected || !!pending || !!pendingPet || listening;
    el('voice-input').disabled = !Recognition || busy || !connected || !!pending || !!pendingPet;
    el('voice-input').textContent = listening ? 'Stop listening' : 'Start voice input';
    el('voice-input').setAttribute('aria-pressed', String(listening));
    el('voice-language').disabled = listening || busy; 
    el('send-message').disabled = input.disabled;
    recorderSelect.disabled = input.disabled;
    catSelect.disabled = input.disabled || catSelect.options.length < 2;
    el('today-shortcut').disabled = input.disabled || !catSelect.value;
    el('vet-shortcut').disabled = el('today-shortcut').disabled;
    el('new-chat').disabled = busy || !!pendingPet || listening;
    el('retry-message').disabled = busy;
    for (const button of el('voice-alternatives').children) button.disabled = input.disabled;
    for (const button of document.querySelectorAll('[data-message]')) button.disabled = input.disabled;
  }
  function message(role, text) {
    el('welcome').hidden = true;
    const row = node('article', undefined, `message ${role}`);
    if (role !== 'user') row.append(node('span', '✳', 'avatar'));
    const body = node('div', undefined, 'message-body');
    body.append(node('span', role === 'user' ? 'You' : 'Purr Nanny', 'message-label'), node('p', text, 'message-text'));
    row.append(body); messages.append(row); scrollToLatest(); return body;
  }
  function setCats(cats, selected) {
    if (!Array.isArray(cats)) return;
    catSelect.replaceChildren();
    catSelect.append(new Option(cats.length ? 'Choose a cat…' : 'No cats yet', ''));
    for (const cat of cats) {
      if (typeof cat.cat_id === 'string' && typeof cat.name === 'string') catSelect.append(new Option(cat.name, cat.cat_id));
    }
    if (cats.some(cat => cat.cat_id === selected)) catSelect.value = selected;
    else if (cats.length === 1) catSelect.value = cats[0].cat_id;
    el('cat-hint').textContent = cats.length ? 'Choose a cat to keep every observation in the right record.' : 'Use Add pet to create your first cat profile.';
  }
  async function jsonRequest(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch(url, {...options, credentials:'same-origin', signal:controller.signal, headers:{Accept:'application/json', ...(options.body ? {'Content-Type':'application/json'} : {})}});
      let data;
      try { data = await response.json(); } catch (_) { throw Error('The service returned an unreadable response.'); }
      if (!response.ok) {
        const error = Error(response.status === 401 || response.status === 403 ? 'Sign in to reconnect to your household.' : (typeof data.error === 'string' ? data.error : data.error?.message) || 'The service could not complete this request.');
        error.status = response.status; error.partial = data; throw error;
      }
      return data;
    } finally { clearTimeout(timer); }
  }
  function addCard(parent, tool, result) {
    const route = cardRoutes[tool];
    if (!route || !result || result.schema_version !== '1.0') return;
    const display = el('echo-content');
    const shell = node('section', undefined, 'card-shell');
    const heading = node('div', undefined, 'card-heading');
    heading.append(node('h3', cardNames[tool]), node('span', 'Shared care record'));
    const frame = node('iframe', undefined, 'care-card');
    frame.setAttribute('title', cardNames[tool]);
    frame.setAttribute('sandbox', 'allow-scripts');
    const cardStatus = node('p', 'Loading care card…', 'card-status');
    const entry = {frame, result, status:cardStatus, initialized:false, timer:null};
    frames.set(frame, entry);
    shell.append(heading, cardStatus, frame); (display || parent).append(shell);
    // Register before navigation: initialization may arrive as soon as HTML loads.
    frame.src = route;
    entry.timer = setTimeout(() => {
      if (!entry.initialized) cardStatus.textContent = 'The care card could not load. The chat response remains available; try the view again.';
    }, 15000);
  }
  window.addEventListener('message', event => {
    const entry = [...frames.values()].find(item => item.frame.contentWindow === event.source);
    const msg = event.data;
    if (!entry || !msg || msg.jsonrpc !== '2.0') return;
    const send = data => entry.frame.contentWindow.postMessage({jsonrpc:'2.0', ...data}, '*');
    if (msg.method === 'ui/initialize' && msg.id !== undefined) {
      send({id:msg.id,result:{protocolVersion:'2026-01-26',hostInfo:{name:'Purr Nanny web chat',version:'0.1.0'},hostCapabilities:{},hostContext:{displayMode:'inline'}}});
    } else if (msg.method === 'ui/notifications/initialized') {
      entry.initialized = true; clearTimeout(entry.timer); entry.status.hidden = true;
      send({method:'ui/notifications/tool-input',params:{arguments:{}}});
      send({method:'ui/notifications/tool-result',params:{structuredContent:entry.result}});
    } else if (entry.initialized && msg.method === 'ui/notifications/size-changed') {
      const height = msg.params?.height;
      if (typeof height === 'number' && Number.isFinite(height)) entry.frame.style.height = `${Math.max(220, Math.min(10000, Math.ceil(height)))}px`;
    }
  });
  function renderReply(data) {
    if (!data || typeof data.reply !== 'string' || !Array.isArray(data.results)) throw Error('The service response is incomplete.');
    conversationId = data.conversation_id || conversationId;
    const body = message('assistant', data.reply);
    const questions = new Map();
    for (const item of data.results) {
      const result = item.structuredContent;
      if (item.is_error) questions.set(`error:${item.tool}`, {text:result?.error?.message || 'A care-record operation could not be completed.'});
      if (!result || typeof result !== 'object') continue;
      // Prioritize warnings even when the returned tool is an event logger rather than a card.
      for (const flag of result.red_flags || []) {
        if (typeof flag.recommended_wording === 'string') questions.set(`flag:${flag.rule_id}`, {text:flag.recommended_wording, priority:({emergency:3,urgent:2,warning:1}[flag.level] || 1)});
      }
      for (const follow of result.follow_up || []) {
        if (typeof follow.question === 'string') questions.set(`question:${follow.field}`, {text:follow.question});
      }
      if (result.includes_sample_data) questions.set('sample', {text:'Includes sample data for demo'});
      const notification = result.notification_status?.state;
      if (notification === 'sent') questions.set('notification', {text:'Notification accepted by the provider. Delivery and reading are unconfirmed.'});
      if (notification === 'failed' || notification === 'uncertain') questions.set('notification', {text:'Family notification is not confirmed. Do not assume anyone was notified.'});
      if (notification === 'queued') questions.set('notification', {text:'Notification queued; sending is not yet confirmed.'});
      if (Array.isArray(result.cats)) setCats(result.cats, catSelect.value);
      if (result.cat?.cat_id && item.tool === 'add_cat') {
        const cats = [...catSelect.options].filter(o => o.value).map(o => ({cat_id:o.value,name:o.textContent}));
        if (!cats.some(c => c.cat_id === result.cat.cat_id)) cats.push(result.cat);
        setCats(cats, result.cat.cat_id);
      }
    }
    const extraQuestions = data.follow_up?.questions || (Array.isArray(data.follow_up) ? data.follow_up : []);
    for (const question of extraQuestions) {
      if (typeof question.question === 'string') questions.set(`question:${question.field}`, {text:question.question});
    }
    let firstQuestionSeen = false;
    for (const [key, question] of questions) {
      if (key.startsWith('question:')) {
        if (firstQuestionSeen || data.reply.includes(question.text)) questions.delete(key);
        firstQuestionSeen = true;
      }
    }
    const prioritySignals = [...questions.entries()].filter(([, question]) => question.priority).sort(([,a],[,b]) => b.priority-a.priority);
    if (prioritySignals.length) {
      const safety = node('section', undefined, 'safety-signals');
      safety.setAttribute('aria-label', 'Priority health signals');
      safety.append(node('h3', 'Priority health signals'));
      for (const [key, signal] of prioritySignals) { safety.append(node('p', signal.text)); questions.delete(key); }
      // Structured safety guidance leads even if ordinary model prose omits it.
      body.insertBefore(safety, body.children[1]);
    }
    if (questions.size) {
      const box = node('div', undefined, 'follow-up');
      for (const q of [...questions.values()].sort((a,b) => (b.priority || 0)-(a.priority || 0))) box.append(node('p',q.text));
      body.append(box);
    }
    syncDisplay('assistant', data.reply, prioritySignals.map(([, signal]) => signal), [...questions.values()]);
    const card = [...data.results].reverse().find(item => !item.is_error && cardRoutes[item.tool] && item.structuredContent?.schema_version === '1.0');
    if (card) addCard(body, card.tool, card.structuredContent);
    if (Array.isArray(data.cats)) setCats(data.cats, catSelect.value);
    // Keep the reply and priority signals visible above a potentially long care card.
    const row = body.parentElement;
    if (row && Number.isFinite(row.offsetTop)) messages.scrollTop = row.offsetTop - messages.offsetTop;
    else scrollToLatest();
  }
  async function send(text, retry = false) {
    if (busy || !connected || listening) return;
    if (!retry) {
      if (pending || !text.trim()) return;
      pending = {message:text.trim(), ...(recorderSelect.value ? {recorded_by:recorderSelect.value} : {}), request_id:crypto.randomUUID(), ...(catSelect.value ? {cat_id:catSelect.value} : {}), ...(conversationId ? {conversation_id:conversationId} : {})};
      clearVoiceChoices();
      message('user', text.trim()); syncDisplay('user', text.trim()); input.value = '';
    }
    if (!pending) return;
    busy = true; controls(); el('retry-row').hidden = true; status('Purr Nanny is checking the shared record…');
    try {
      const data = await jsonRequest('/api/chat', {method:'POST',body:JSON.stringify(pending)});
      renderReply(data); pending = null; status('');
    } catch (error) {
      if (error.status === 401 || error.status === 403) showLogin();
      if (typeof error.partial?.reply === 'string' && Array.isArray(error.partial?.results)) renderReply(error.partial);
      status(error.name === 'AbortError' ? 'The request took too long. Its outcome is unknown; retry the same message to check.' : error.message || 'Connection lost. Retry the same message.');
      el('retry-row').hidden = false;
    } finally { busy = false; controls(); if (!pending) input.focus(); }
  }
  async function connect() {
    stopVoice(true); connected = false; controls(); status('Connecting to the household care service…');
    try {
      const data = await jsonRequest('/api/chat/session');
      if (!Array.isArray(data.cats)) throw Error('Unable to load the household’s cat profiles.');
      if (Array.isArray(data.recorders)) {
        const selected = recorderSelect.value;
        recorderSelect.replaceChildren(new Option('Choose a recorder…',''));
        for (const name of data.recorders) recorderSelect.append(new Option(name,name));
        if (data.recorders.includes(selected)) recorderSelect.value = selected;
      }
      setCats(data.cats, catSelect.value); conversationId = pending?.conversation_id || conversationId || data.conversation_id || null;
      connected = true; el('connection').textContent = 'Ready';
      el('environment-label').textContent = data.mode_label || 'Local simulated Alexa experience';
      status(pending ? 'Reconnected. Retry the same message to check its result.' : ''); el('retry-row').hidden = !pending;
    } catch (error) { if (error.status === 401 || error.status === 403) showLogin(); el('connection').textContent = 'Offline'; status(error.message || 'Unable to connect.'); el('retry-row').hidden = false; }
    controls();
  }
  function resetConversation() {
    if (busy) return;
    stopVoice(true); clearVoiceChoices();
    conversationId = null; pending = null;
    for (const item of frames.values()) clearTimeout(item.timer);
    frames.clear();
    if (el('echo-content')) { el('echo-content').replaceChildren(); el('echo-empty').hidden = false; }
    for (const row of [...messages.children]) if (row.id !== 'welcome') row.remove();
    el('welcome').hidden = false; input.value = ''; status('New conversation. Saved care records stay available.');
    el('retry-row').hidden = true; controls(); input.focus();
  }
  function showLogin() {
    stopVoice(true);
    const dialog = el('login-dialog'); if (!dialog.open) dialog.showModal();
    el('login-password').focus();
  }
  el('add-pet').addEventListener('click', () => {
    if (busy || pending || !connected) return;
    el('pet-dialog').showModal();
    (pendingPet ? el('pet-submit') : el('pet-name')).focus();
  });
  el('pet-cancel').addEventListener('click', () => el('pet-dialog').close());
  el('pet-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !connected) return;
    if (!pendingPet) {
      const name = el('pet-name').value.trim(), meals = el('pet-meals').value;
      if (!name || name.length > 80 || (meals && (!Number.isInteger(Number(meals)) || Number(meals) < 1 || Number(meals) > 12))) {
        el('pet-status').textContent = 'Enter a name and optional whole-number meals per day from 1 to 12.'; return;
      }
      pendingPet = {name, request_id:crypto.randomUUID(), ...(meals ? {meals_per_day:Number(meals)} : {})};
    }
    busy = true; controls();
    el('pet-submit').disabled = true; el('pet-cancel').disabled = true;
    el('pet-name').disabled = true; el('pet-meals').disabled = true;
    el('pet-status').textContent = 'Saving pet…';
    try {
      const data = await jsonRequest('/api/pets', {method:'POST', body:JSON.stringify(pendingPet)});
      if (!data.cat?.cat_id || typeof data.cat.name !== 'string') throw Error('Could not confirm the saved profile. Retry to check.');
      const cats = [...catSelect.options].filter(o => o.value && o.value !== data.cat.cat_id).map(o => ({cat_id:o.value,name:o.textContent}));
      cats.push(data.cat); setCats(cats, data.cat.cat_id);
      pendingPet = null; busy = false; resetConversation();
      status(`${data.cat.name} was added. You can start recording their care.`);
      el('pet-dialog').close(); el('pet-name').value = ''; el('pet-meals').value = ''; el('pet-status').textContent = '';
    } catch (error) {
      if (error.status === 400 || error.status === 409) pendingPet = null;
      if (error.status === 401 || error.status === 403) { el('pet-dialog').close(); showLogin(); }
      el('pet-status').textContent = error.message || 'Could not confirm the save. Retry to check.';
    } finally {
      busy = false; controls(); el('pet-submit').disabled = false; el('pet-cancel').disabled = false;
      el('pet-name').disabled = !!pendingPet; el('pet-meals').disabled = !!pendingPet;
      el('pet-submit').textContent = pendingPet ? 'Retry save' : 'Add pet';
      el('pet-cancel').textContent = pendingPet ? 'Close' : 'Cancel';
    }
  });
  el('pet-dialog').addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  el('login-form').addEventListener('submit', async event => {
    event.preventDefault(); const passwordInput = el('login-password'), password = passwordInput.value;
    passwordInput.value = ''; el('login-submit').disabled = true; el('login-status').textContent = 'Connecting…';
    try {
      await jsonRequest('/api/chat/login', {method:'POST',body:JSON.stringify({password})});
      el('login-dialog').close(); el('login-status').textContent = '';
      await connect();
    } catch (_) { el('login-status').textContent = 'Unable to sign in. Check your chat password and service configuration.'; passwordInput.focus(); }
    finally { el('login-submit').disabled = false; }
  });
  el('chat-form').addEventListener('submit', event => { event.preventDefault(); send(input.value); });
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(input.value); } });
  input.addEventListener('input', () => { clearVoiceChoices(); if (!input.disabled) syncDisplay('draft', input.value || 'Your draft is empty.'); });
  el('retry-message').addEventListener('click', () => pending ? send('',true) : connect());
  el('new-chat').addEventListener('click', resetConversation);
  catSelect.addEventListener('change', resetConversation);
  el('today-shortcut').addEventListener('click', () => send('What happened today?'));
  el('vet-shortcut').addEventListener('click', () => send('Show the veterinary summary for the last 7 days'));
  for (const button of document.querySelectorAll('[data-message]')) button.addEventListener('click', () => send(button.dataset.message));
  el('voice-input').addEventListener('click', () => {
    if (listening) { stopVoice(); return; }
    if (!Recognition || input.disabled) return;
    voiceDraft = input.value; voiceFinal = ''; clearVoiceChoices();
    let candidates = [];
    const generation = ++voiceGeneration;
    const session = new Recognition(); recognition = session;
    session.lang = el('voice-language').value || 'en-US';
    session.continuous = false; session.interimResults = true; session.maxAlternatives = 5;
    // Browser API exposure does not guarantee the remote service supports
    // contextual phrases. Keep dictation compatible with those services.
    session.onresult = event => {
      if (generation !== voiceGeneration) return;
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const prefix = voiceFinal;
          voiceFinal += event.results[i][0].transcript + ' ';
          candidates = candidates.map(text => (text + ' ' + event.results[i][0].transcript).trim());
          for (let j = 1; j < event.results[i].length; j++) candidates.push((prefix + event.results[i][j].transcript).trim());
        }
        else interim += event.results[i][0].transcript;
      }
      input.value = [voiceDraft, voiceFinal.trim()].filter(Boolean).join(' ');
      const preview = [input.value, interim].filter(Boolean).join(' ');
      el('voice-status').textContent = interim ? 'Hearing: ' + interim : 'Transcript ready. Review and press Send.';
      syncDisplay('draft', preview || 'Listening…');
    };
    session.onerror = event => {
      if (generation !== voiceGeneration) return;
      const errors = {'not-allowed':'Microphone access was denied. Allow it in browser settings or type your message.', 'service-not-allowed':'This browser cannot use its speech recognition service. Open this page in Chrome or Safari and allow microphone access.', 'phrases-not-supported':'The speech service rejected contextual hints. Reload this page and try again.', aborted:'Voice input was interrupted. Try again; your draft is preserved.', 'audio-capture':'No microphone is available. Connect one or type your message.', network:'Speech recognition could not connect. Try again or type your message.', 'no-speech':'No speech detected. Try again or type your message.', 'language-not-supported':'This voice language is unavailable. Choose another language or type your message.'};
      el('voice-status').textContent = errors[event.error] || 'Voice input failed (' + (event.error || 'unknown error') + '). Your draft is preserved; try again or type instead.';
      status(el('voice-status').textContent);
    };
    session.onend = () => {
      if (generation !== voiceGeneration) return;
      recognition = null; listening = false; controls(); input.focus();
      // Interim recognition is never submitted or treated as a final transcript.
      syncDisplay('draft', input.value || 'No transcript. Type a message or try voice input again.');
      if (!voiceFinal.trim() && el('voice-status').textContent.startsWith('Listening')) { el('voice-status').textContent = 'No speech detected. Try again or type your message.'; status(el('voice-status').textContent); }
      if (voiceFinal.trim()) {
        const suggestion = session.lang.startsWith('en') ? feedingSuggestion(voiceFinal.trim()) : null;
        voiceChoices([...candidates, ...(suggestion ? [suggestion] : [])].map(text => [voiceDraft, text].filter(Boolean).join(' ')));
        el('voice-status').textContent = 'Check the transcript' + (el('voice-alternatives').hidden ? ' or edit it below.' : ' or choose a suggestion below.') + ' You can also select 中文 and speak Mandarin.';
        status('Voice draft ready for review. Nothing has been submitted.');
      }
    };
    try {
      listening = true; controls(); session.start();
      el('voice-status').textContent = 'Listening… Speak, then stop to review your message.';
      status('Listening… Nothing is saved until you press Send.');
      syncDisplay('draft', input.value || 'Listening…');
    } catch (_) {
      recognition = null; listening = false; controls();
      el('voice-status').textContent = 'Unable to start voice input. Try again or type your message.';
      status(el('voice-status').textContent);
    }
  });
  if (!Recognition) el('voice-status').textContent = 'Voice input is unavailable in this browser. You can still type your message.';
  window.CatNannyChat = {connect};
  connect();
})();
