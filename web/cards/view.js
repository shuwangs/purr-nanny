/* Read-only renderer. Health conclusions and statistics come exclusively from the server. */
(function () {
  'use strict';
  const root = document.getElementById('result');
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = String(text);
    if (cls) el.className = cls;
    return el;
  }
  function section(title) {
    const el = node('section'); el.append(node('h2', title)); root.append(el); return el;
  }
  function readable(value) {
    if (value === null || value === undefined) return 'Unknown';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (Array.isArray(value)) return value.length ? value.map(readable).join(', ') : 'None supplied';
    if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key.replaceAll('_', ' ')}: ${readable(item)}`).join(' · ');
    return String(value).replaceAll('_', ' ');
  }
  const signalNames = {
    urinary_obstruction_signs: 'Difficulty passing urine',
    vomiting_concerning_signs: 'Vomiting with concerning signs',
    frequent_vomiting_24h: 'Repeated vomiting in 24 hours',
    vomiting_frequency_doubled: 'Increase in recorded vomiting',
    weight_loss_30d: 'Weight loss over 30 days',
    not_eating_24h: 'Prolonged loss of appetite'
  };
  const patternNames = {frequency:'Recorded frequency', vomiting_after_meal:'Vomiting after meals', weight_trend:'Weight change', food_change_comparison:'Food change comparison'};
  const eventNames = {vomiting:'Vomiting', appetite:'Appetite', litter:'Litter box observation', energy:'Energy', weight:'Weight', feeding:'Feeding', water:'Water', litter_cleaning:'Litter cleaning', medication:'Medication', food_change:'Food change'};
  function displayZone(data) {
    const candidate = data.display_timezone || data.window?.timezone;
    try { if (candidate) { new Intl.DateTimeFormat('en-US', {timeZone:candidate}).format(); return candidate; } } catch (_) {}
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  }
  function dateText(value, zone) {
    if (!value) return 'Time unknown';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Time unknown';
    return new Intl.DateTimeFormat('en-US', {timeZone:zone, month:'short', day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit', timeZoneName:'short'}).format(date);
  }
  function windowText(value, zone) {
    return `${dateText(value?.start, zone)} → ${dateText(value?.end, zone)}`;
  }
  function render(data) {
    root.replaceChildren();
    if (!data || data.schema_version !== '1.0') {
      root.append(node('p', 'Unable to display this result: unsupported or missing schema.', 'notice')); return;
    }
    if (data.error) { root.append(node('p', data.error.message || 'Request failed.', 'notice')); return; }
    const events = Array.isArray(data.timeline) ? data.timeline : (Array.isArray(data.events) ? data.events : []);
    if (data.includes_sample_data || events.some(e => e.source === 'seed')) root.append(node('p', 'Includes sample data for demo', 'sample'));
    root.append(node('p', data.cat?.name || 'Cat care record', 'subtitle'));
    const zone = displayZone(data);
    const byId = new Map(events.map((event, index) => [event.event_id, {event, number:index + 1}]));
    function evidenceText(ids) {
      if (!Array.isArray(ids) || !ids.length) return 'No supporting observations supplied';
      return ids.map(id => {
        const match = byId.get(id);
        return match ? `Observation ${match.number} · ${eventNames[match.event.event_type] || 'Observation'} · ${dateText(match.event.occurred_at, zone)}` : 'Supporting observation outside this view';
      }).join('; ');
    }
    root.append(node('p', windowText(data.window, zone), 'muted'));
    root.append(node('p', data.display_timezone || data.window?.timezone ? 'Times shown in household local time.' : 'Times shown in your device’s local time.', 'muted'));
    const flags = Array.isArray(data.red_flags) ? data.red_flags : [];
    if (flags.length) {
      const s = section('Priority signals');
      for (const flag of [...flags].sort((a, b) => ({emergency:0, urgent:1, warning:2}[a.level] ?? 3) - ({emergency:0, urgent:1, warning:2}[b.level] ?? 3))) {
        const card = node('article', undefined, 'flag');
        card.append(node('h3', `${({emergency:'Emergency', urgent:'Urgent', warning:'Warning'}[flag.level] || 'Signal')} · ${signalNames[flag.rule_id] || 'Health warning'}`), node('p', flag.recommended_wording || 'Review this signal with a veterinarian.'));
        card.append(node('p', evidenceText(flag.evidence), 'muted'));
        s.append(card);
      }
    }
    if (!data.analysis_status || data.analysis_status === 'unavailable') root.append(node('p', 'Health analysis unavailable. An empty signal list does not establish that your cat is healthy.', 'notice'));
    for (const limitation of data.limitations || []) root.append(node('p', limitation, 'muted'));
    const notifications = {disabled:'Notifications disabled.', queued:'Notification queued; sending is not yet confirmed.', sent:'Notification accepted by the provider. Delivery and reading are unconfirmed.', uncertain:'Notification outcome uncertain. Provider acceptance and delivery are unconfirmed; review before retrying.', failed:'Notification failed. Do not assume the family was notified.'};
    root.append(node('p', notifications[data.notification_status?.state] || 'Notification status unknown.', 'muted'));
    if (data.feeding_summary) {
      const feeding = section('Feeding records');
      feeding.append(node('p', `${data.feeding_summary.count} feeding records on this day.`));
      if (data.feeding_summary.plan_status === 'not_configured') feeding.append(node('p', 'No meal schedule configured. These records do not establish overfeeding.', 'muted'));
      for (const record of data.feeding_summary.records || []) {
        feeding.append(node('p', `${record.meal_label || 'Meal not specified'} · ${dateText(record.occurred_at, zone)} · Care performed by: ${record.performed_by || 'Unknown'} · Recorded by: ${record.recorded_by || 'Unknown'}${record.reporter ? ' · Reported by: ' + record.reporter : ''} · ${record.food || 'Food unknown'} · ${record.amount || 'Amount unknown'}`));
      }
    }
    for (const note of data.care_notes || []) root.append(node('p', note.message, 'notice'));
    if ((data.follow_up || []).length) {
      const s = section('Details still needed');
      for (const item of data.follow_up) s.append(node('p', item.question || readable(item)));
    }
    const patterns = section('Patterns');
    if (!(data.patterns || []).length) patterns.append(node('p', 'No pattern result supplied.'));
    for (const pattern of data.patterns || []) {
      const card = node('article');
      card.append(node('h3', patternNames[pattern.pattern_id] || pattern.name || 'Recorded pattern'));
      // Show evidence and numerical context without exposing internal identifiers.
      const dl = node('dl');
      for (const [key, value] of Object.entries(pattern)) {
        if (['pattern_id', 'name', 'type'].includes(key)) continue;
        const text = key === 'evidence' ? evidenceText(value) : key === 'window' ? windowText(value, zone)
          : (key === 'change_kg' || key === 'change_percent') && typeof value === 'number' && Number.isFinite(value)
          ? `${new Intl.NumberFormat('en-US', {maximumFractionDigits:key === 'change_kg' ? 3 : 1}).format(value)}${key === 'change_kg' ? ' kg' : '%'}` : readable(value);
        dl.append(node('dt', key.replaceAll('_', ' ')), node('dd', text));
      }
      card.append(dl); patterns.append(card);
    }
    const timeline = section(document.body.dataset.view === 'vet-summary' ? 'Veterinary timeline' : 'Today’s care & observations');
    if (!events.length) timeline.append(node('p', 'No events recorded in this window.'));
    for (const event of events) {
      const card = node('article', undefined, 'event');
      card.append(node('h3', eventNames[event.event_type] || 'Observation'));
      card.append(node('p', `${dateText(event.occurred_at, zone)} · Care performed by: ${event.performed_by || 'Unknown'} · Recorded by: ${event.recorded_by || 'Unknown'}${event.reporter ? ' · Reported by: ' + event.reporter : ''}`, 'muted'));
      if (event.first_recorded_by && event.first_recorded_by !== event.recorded_by) card.append(node('p', `First recorded by: ${event.first_recorded_by} · Latest entry by: ${event.recorded_by || 'Unknown'}`, 'muted'));
      if (event.time_defaulted) card.append(node('p', 'Occurrence time defaulted when recorded; confirm if needed.', 'muted'));
      if (event.source === 'seed') card.append(node('p', 'Sample event', 'sample'));
      const dl = node('dl');
      for (const [key, value] of Object.entries(event.details || {})) dl.append(node('dt', (key === 'meal_id' ? 'Meal' : key.replaceAll('_', ' '))), node('dd', value === null ? 'Unknown' : key === 'meal_id' ? (data.cat?.meal_schedule || []).find(slot => slot.meal_id === value)?.label || 'Meal not specified' : readable(value)));
      card.append(dl, node('small', `Recorded: ${dateText(event.recorded_at, zone)}`)); timeline.append(card);
    }
    if (data.disclaimer) root.append(node('p', data.disclaimer, 'muted'));
    root.append(node('p', 'A factual care record for discussion with a veterinarian. This is not a diagnosis.', 'muted'));
  }
  window.CatNannyView = {render};
  let initialized = false;
  function send(message) { window.parent.postMessage({jsonrpc:'2.0', ...message}, '*'); }
  function reportSize() {
    if (initialized && document.body.scrollHeight) send({method:'ui/notifications/size-changed', params:{height:document.body.scrollHeight}});
  }
  if (window.parent !== window) {
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(reportSize).observe(document.body);
    window.addEventListener('message', event => {
      if (event.source !== window.parent || !event.data || event.data.jsonrpc !== '2.0') return;
      const msg = event.data;
      if (msg.id === 'cat-nanny-init' && msg.result) { initialized = true; send({method:'ui/notifications/initialized'}); reportSize(); }
      if (!initialized) return;
      if (msg.method === 'ui/notifications/tool-result') { render(msg.params?.structuredContent); reportSize(); }
      if (msg.method === 'ui/notifications/tool-cancelled') { root.replaceChildren(node('p', 'Request cancelled. No result available.', 'notice')); }
      if (msg.method === 'ui/resource-teardown' && msg.id !== undefined) send({id:msg.id, result:{}});
      if (msg.method === 'ping' && msg.id !== undefined) send({id:msg.id, result:{}});
    });
    send({id:'cat-nanny-init', method:'ui/initialize', params:{protocolVersion:'2026-01-26', appInfo:{name:'Purr Nanny',version:'0.1.0'}, appCapabilities:{}}});
  }
})();
