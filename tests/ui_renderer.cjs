const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  text() { return [this.textContent, ...this.children.map(e => e.text())].join('\n'); }
}
const root = new Element('div');
const messages = [];
const parent = {postMessage: m => messages.push(m)};
let listener;
const window = {parent, addEventListener: (type, fn) => listener = fn};
const document = {body:{dataset:{view:'vet-summary'}}, getElementById:() => root, createElement:tag => new Element(tag)};
vm.runInNewContext(fs.readFileSync('web/cards/view.js', 'utf8'), {window, document});
const fixture = {schema_version:'1.0', analysis_status:'evaluated', cat:{name:'<img src=x onerror=alert(1)>'}, timeline:[{event_id:'seed-1', source:'seed', event_type:'feeding', occurred_at:'2026-10-12T17:00:00Z', details:{amount:null}}], patterns:[{pattern_id:'meal',status:'insufficient_data',denominator:0,sample_size:0}], red_flags:[{level:'urgent',rule_id:'second',recommended_wording:'Urgent guidance'}, {level:'emergency',rule_id:'first',recommended_wording:'Emergency guidance'}], follow_up:[{question:'Which meal?'}], notification_status:{state:'sent'}};
const deliver = (data, source=parent) => listener({source, data:{jsonrpc:'2.0', ...data}});
assert.equal(messages[0].method, 'ui/initialize');
deliver({method:'ui/notifications/tool-result',params:{structuredContent:fixture}});
assert.equal(root.text(), ''); // Result before handshake is ignored.
deliver({id:'cat-nanny-init',result:{protocolVersion:'2026-01-26'}});
assert.equal(messages[1].method, 'ui/notifications/initialized');
deliver({method:'ui/notifications/tool-result',params:{structuredContent:fixture}}, {});
assert.equal(root.text(), ''); // Unrelated windows cannot inject records.
deliver({method:'ui/notifications/tool-result',params:{structuredContent:fixture}});
assert.match(root.text(), /Includes sample data for demo/);
assert.match(root.text(), /Feeding/); // Veterinary summary uses timeline, not events.
assert.match(root.text(), /Unknown/);
assert.match(root.text(), /Delivery and reading are unconfirmed/);
assert.match(root.text(), /insufficient data/);
assert.ok(root.text().indexOf('Emergency guidance') < root.text().indexOf('Urgent guidance'));
assert.ok(root.text().indexOf('Urgent guidance') < root.text().indexOf('Which meal?'));
assert.equal(root.children.find(e => e.className === 'subtitle').textContent, fixture.cat.name); // Untrusted text is never HTML.
window.CatNannyView.render({schema_version:'1.0',analysis_status:'unavailable',events:[],notification_status:{state:'failed'}});
assert.match(root.text(), /Health analysis unavailable/);
assert.match(root.text(), /Notification failed/);
assert.match(root.text(), /No events recorded/);
assert.doesNotMatch(root.text(), /Emergency guidance/); // Previous result cleared.
window.CatNannyView.render({schema_version:'9'});
assert.match(root.text(), /unsupported or missing schema/);
deliver({method:'ui/notifications/tool-cancelled'});
assert.match(root.text(), /Request cancelled/);
console.log('UI renderer and bridge assertions passed');

const privateId = 'c04d0a0a-78b7-4d65-b91e-53a340d2e69b';
const localFixture = {...fixture, display_timezone:'America/Chicago', window:{start:'2026-10-12T05:00:00Z', end:'2026-10-13T05:00:00Z'}, timeline:[{...fixture.timeline[0], event_id:privateId, recorded_at:'2026-10-12T17:01:00Z'}], red_flags:[{level:'urgent', rule_id:'vomiting_concerning_signs', evidence:[privateId, 'hidden-uuid'], recommended_wording:'Seek care.'}], patterns:[{pattern_id:'vomiting_after_meal', window:{start:'2026-10-12T05:00:00Z',end:'2026-10-13T05:00:00Z'}, evidence:[privateId], denominator:3, sample_size:3}]};
window.CatNannyView.render(localFixture);
assert.match(root.text(), /12:00 PM CDT/);
assert.match(root.text(), /Vomiting with concerning signs/);
assert.match(root.text(), /Observation 1/);
assert.match(root.text(), /outside this view/);
assert.doesNotMatch(root.text(), /vomiting_concerning_signs|vomiting_after_meal|c04d0a0a|hidden-uuid|2026-10-12T|UTC timestamps/);
window.CatNannyView.render({...localFixture, display_timezone:'America/Chicago', timeline:[{...localFixture.timeline[0], occurred_at:'2026-01-12T18:00:00Z'}]});
assert.match(root.text(), /12:00 PM CST/);
window.CatNannyView.render({...localFixture, display_timezone:'invalid/timezone', window:{}, timeline:[{...localFixture.timeline[0],occurred_at:'invalid'}]});
assert.match(root.text(), /Time unknown/);
window.CatNannyView.render({...localFixture, feeding_summary:{count:2, plan_status:'configured', records:[{meal_label:'Breakfast', occurred_at:'2026-10-12T13:00:00Z', reporter:'Alex', food:'wet food', amount:'40 g'},{meal_label:'Dinner', occurred_at:'2026-10-12T23:00:00Z', reporter:'Shu', food:'wet food', amount:'40 g'}]},care_notes:[{message:'Breakfast already has a feeding record. Please confirm whether an additional feeding took place.'}]});
assert.match(root.text(), /2 feeding records/);
assert.match(root.text(), /Breakfast.*8:00 AM CDT.*Alex.*40 g/);
assert.match(root.text(), /Dinner.*6:00 PM CDT.*Shu/);
assert.match(root.text(), /Please confirm/);
window.CatNannyView.render({...localFixture, feeding_summary:{count:3,plan_status:'not_configured',records:[]},care_notes:[]});
assert.match(root.text(), /do not establish overfeeding/);
assert.doesNotMatch(root.text(), /Please confirm/);
window.CatNannyView.render({...localFixture, red_flags:[{rule_id:'weight_loss_30d',level:'warning',recommended_wording:'Mention this at your next veterinary visit.'}],patterns:[{pattern_id:'weight_trend',status:'observed',change_kg:-0.30000000000000027,change_percent:-7.142857142857149}]});
assert.match(root.text(), /Weight loss over 30 days/);
assert.match(root.text(), /-0\.3 kg/);
assert.match(root.text(), /-7\.1%/);
assert.doesNotMatch(root.text(), /30000000000000027|142857142857/);

window.CatNannyView.render({...localFixture, timeline:[{event_id:'attributed-event',event_type:'feeding',occurred_at:'2026-10-12T13:00:00Z',performed_by:'Alex',recorded_by:'Shu',details:{}}]});
assert.match(root.text(), /Care performed by: Alex.*Recorded by: Shu/);
