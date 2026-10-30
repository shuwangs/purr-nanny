const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(tag='div', id='') { this.tag=tag; this.id=id; this.children=[]; this.listeners={}; this.textContent=''; this.value=''; this.hidden=false; this.style={}; this.dataset={}; this.options=this.children; this.attributes={}; this.open=false; if(tag==='iframe')this.contentWindow={sent:[],postMessage(message){this.sent.push(message);}}; }
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
  insertBefore(node, before){node.parent=this;this.children.splice(this.children.indexOf(before),0,node);}
  replaceChildren(...nodes){this.children.length=0;this.append(...nodes);}
  addEventListener(type,fn){this.listeners[type]=fn;}
  setAttribute(key,value){this.attributes[key]=value;}
  focus(){this.focused=true;}
  remove(){this.parent.children=this.parent.children.filter(e=>e!==this);}
  showModal(){this.open=true;}
  close(){this.open=false;}
  text(){return [this.textContent,...this.children.map(e=>e.text())].join('\n');}
  async fire(type, values={}){return this.listeners[type]?.({preventDefault(){},...values});}
}
const ids = ['voice-alternatives','voice-input','voice-language','voice-status','echo-status','add-pet','pet-dialog','pet-form','pet-name','pet-meals','pet-status','pet-submit','pet-cancel','echo-content','echo-empty','messages','message-input','cat-select','recorder-select','request-status','welcome','send-message','today-shortcut','vet-shortcut','new-chat','retry-message','retry-row','cat-hint','connection','environment-label','chat-form','login-dialog','login-form','login-password','login-submit','login-status'];
const nodes = Object.fromEntries(ids.map(id=>[id,new Element('div',id)]));
nodes.messages.append(nodes.welcome);
let petAttempts=0;let onMessage;let fetches=[];let chatAttempts=0;let messageSerial=0;let sessionAuthorized=true;
const timers=new Map();let timerId=0;
const document={getElementById:id=>nodes[id],createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
const fetch = async (url, options) => {
  const body=options.body && JSON.parse(options.body);fetches.push({url,body,options});
  if(url==='/api/chat/login'){sessionAuthorized=true;return {ok:true,json:async()=>({ok:true})};}
  if(url==='/api/chat/session')return {ok:sessionAuthorized,status:sessionAuthorized?200:401,json:async()=>sessionAuthorized?{cats:[{cat_id:'miso',name:'Miso'}],recorders:['Shu','Alex','Yuan'],mode_label:'Local test'}:{error:'unauthorized'}};
  if(url==='/api/pets'){
    petAttempts++;
    if(petAttempts===1)throw Error('Response lost');
    return {ok:true,json:async()=>({cat:{cat_id:'new-pet',name:body.name}})};
  }
  if(url==='/api/chat'){
    chatAttempts++;
    if(chatAttempts===1)throw Error('Network response lost');
    return {ok:true,json:async()=>({reply:'<img src=x onerror=alert(1)>',conversation_id:'conversation-1',results:[{tool:'get_today',structuredContent:{schema_version:'1.0',red_flags:[{rule_id:'urgent',level:'urgent',recommended_wording:'Urgent guidance'},{rule_id:'emergency',level:'emergency',recommended_wording:'Emergency guidance'}],follow_up:[{field:'blood',question:'Was there blood?'},{field:'lethargy',question:'Is your cat lethargic?'}],includes_sample_data:true,notification_status:{state:'sent'},events:[]}}]})};
  }
  throw Error('Unexpected URL');
};
let speech;
class SpeechRecognition { constructor(){speech=this;this.phrases=[];} start(){} stop(){this.onend();} abort(){} }
const window={SpeechRecognition,SpeechRecognitionPhrase:class {constructor(phrase,boost){this.phrase=phrase;this.boost=boost;}},addEventListener:(type,fn)=>onMessage=fn};
function Option(text,value){const n=new Element('option');n.textContent=text;n.value=value;return n;}
vm.runInNewContext(fs.readFileSync('web/chat/chat.js','utf8'),{window,document,Option,fetch,AbortController,crypto:{randomUUID:()=>`request-${++messageSerial}`},setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id)});
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
(async()=>{
  await settle();assert.equal(nodes.connection.textContent,'Ready');assert.equal(nodes['cat-select'].value,'miso');
  nodes['recorder-select'].value='Shu';
  nodes['voice-language'].value='en-US';
  await nodes['voice-input'].fire('click');
  assert.equal(speech.maxAlternatives,5); assert.deepEqual(speech.phrases,[]); // Do not send experimental hints to remote services.
  speech.onresult({resultIndex:0,results:[Object.assign([{transcript:'are fed miso at 10 a.m.'},{transcript:'I fed Miso at 10 a.m.'}],{isFinal:true})]});
  await nodes['voice-input'].fire('click');
  assert.equal(nodes['message-input'].value,'are fed miso at 10 a.m.');
  assert.equal(nodes['voice-alternatives'].hidden,false);
  await nodes['voice-alternatives'].children[0].fire('click');
  assert.equal(nodes['message-input'].value,'I fed Miso at 10 a.m.');
  assert.match(nodes['echo-content'].text(),/I fed Miso/);
  assert.equal(fetches.filter(f=>f.url==='/api/chat').length,0);
  nodes['message-input'].value='';

  nodes['voice-language'].value='zh-CN'; nodes['message-input'].value='Existing draft';
  await nodes['voice-input'].fire('click');
  assert.equal(speech.lang,'zh-CN'); assert.equal(nodes['send-message'].disabled,true);
  speech.onresult({resultIndex:0,results:[Object.assign([{transcript:'猫刚吐了'}],{isFinal:false})]});
  assert.match(nodes['echo-content'].text(),/猫刚吐了/);
  assert.equal(nodes['message-input'].value,'Existing draft');
  speech.onresult({resultIndex:0,results:[Object.assign([{transcript:'猫刚吐了'}],{isFinal:true})]});
  await nodes['voice-input'].fire('click');
  assert.equal(nodes['message-input'].value,'Existing draft 猫刚吐了');
  assert.equal(fetches.filter(f=>f.url==='/api/chat').length,0);
  assert.equal(nodes['send-message'].disabled,false);
  await nodes['voice-input'].fire('click');
  speech.onerror({error:'not-allowed'}); speech.onend();
  assert.match(nodes['voice-status'].textContent,/denied/);
  assert.match(nodes['message-input'].value,/Existing draft/);

  await nodes['voice-input'].fire('click');
  speech.onerror({error:'service-not-allowed'}); speech.onend();
  assert.match(nodes['voice-status'].textContent,/speech recognition service/);
  assert.equal(nodes['voice-input'].disabled,false);
  assert.match(nodes['message-input'].value,/Existing draft/);
  await nodes['voice-input'].fire('click');
  speech.onerror({error:'unexpected-service-error'}); speech.onend();
  assert.match(nodes['voice-status'].textContent,/unexpected-service-error/);

  nodes['message-input'].value='Miso vomited';await nodes['chat-form'].fire('submit');await settle();
  assert.equal(nodes['retry-row'].hidden,false);assert.equal(nodes['send-message'].disabled,true);
  assert.equal(nodes.messages.children.filter(n=>n.className==='message user').length,1);
  await nodes['retry-message'].fire('click');await settle();
  const attempts=fetches.filter(f=>f.url==='/api/chat');
  assert.equal(attempts.length,2);assert.deepEqual(attempts[0].body,attempts[1].body);assert.equal(attempts[1].body.cat_id,'miso');assert.equal(attempts[1].body.recorded_by,'Shu');
  assert.equal(nodes['retry-row'].hidden,true);assert.equal(nodes['send-message'].disabled,false);
  assert.equal(nodes.messages.children.filter(n=>n.className==='message user').length,1); // Retry doesn't duplicate user bubble.
  assert.match(nodes.messages.text(),/Urgent guidance[\s\S]*Was there blood/);
  assert.match(nodes.messages.text(),/Includes sample data/);
  assert.doesNotMatch(nodes.messages.text(),/Is your cat lethargic/); // One missing detail at a time.
  assert.match(nodes.messages.text(),/Delivery and reading are unconfirmed/);
  const assistant=nodes.messages.children.find(n=>n.className==='message assistant');
  assert.equal(assistant.children[1].children[1].className,'safety-signals');
  assert.equal(assistant.children[1].children[2].textContent,'<img src=x onerror=alert(1)>');
  assert.ok(assistant.text().indexOf('Emergency guidance') < assistant.text().indexOf('Urgent guidance'));
  assert.ok(assistant.text().indexOf('Urgent guidance') < assistant.text().indexOf('<img'));
  assert.ok(assistant.text().indexOf('Urgent guidance') < assistant.text().indexOf('Was there blood?'));
  assert.equal(nodes['echo-empty'].hidden,true);
  assert.match(nodes['echo-content'].text(),/Emergency guidance/);
  assert.match(nodes['echo-content'].text(),/Was there blood/);
  assert.match(nodes['echo-content'].text(),/<img src=x/);
  const shell=nodes['echo-content'].children.find(n=>n.className==='card-shell'), frame=shell.children.find(n=>n.tag==='iframe');
  assert.equal(frame.src,'/apps/today.html');assert.equal(frame.attributes.sandbox,'allow-scripts');
  onMessage({source:{},data:{jsonrpc:'2.0',id:'init',method:'ui/initialize'}});assert.equal(frame.contentWindow.sent.length,0);
  onMessage({source:frame.contentWindow,data:{jsonrpc:'2.0',id:'init',method:'ui/initialize'}});assert.equal(frame.contentWindow.sent[0].result.protocolVersion,'2026-01-26');
  onMessage({source:frame.contentWindow,data:{jsonrpc:'2.0',method:'ui/notifications/initialized'}});
  assert.equal(frame.contentWindow.sent[2].method,'ui/notifications/tool-result');
  assert.equal(frame.contentWindow.sent[2].params.structuredContent.schema_version,'1.0');
  onMessage({source:frame.contentWindow,data:{jsonrpc:'2.0',method:'ui/notifications/size-changed',params:{height:999999}}});assert.equal(frame.style.height,'10000px');
  nodes['message-input'].value='No blood';await nodes['chat-form'].fire('submit');await settle();
  assert.equal(fetches.filter(f=>f.url==='/api/chat').at(-1).body.conversation_id,'conversation-1');
  await nodes['new-chat'].fire('click');assert.equal(nodes.messages.children.length,1);assert.equal(nodes.welcome.hidden,false);assert.equal(nodes['echo-content'].children.length,0);assert.equal(nodes['echo-empty'].hidden,false);
  nodes['message-input'].value='Today';await nodes['chat-form'].fire('submit');await settle();
  assert.equal(fetches.filter(f=>f.url==='/api/chat').at(-1).body.conversation_id,undefined);
  sessionAuthorized=false;await window.CatNannyChat.connect();assert.equal(nodes['login-dialog'].open,true);
  nodes['login-password'].value='synthetic-chat-password-for-test';await nodes['login-form'].fire('submit');await settle();
  assert.equal(nodes['login-password'].value,'');assert.equal(nodes['login-dialog'].open,false);
  assert.equal(fetches.filter(f=>f.url==='/api/chat').at(-1).body.token,undefined);
  const login=fetches.find(f=>f.url==='/api/chat/login');
  assert.deepEqual(login.body,{password:'synthetic-chat-password-for-test'});
  assert.equal(login.body.token,undefined);
  await nodes['add-pet'].fire('click');assert.equal(nodes['pet-dialog'].open,true);
  nodes['pet-name'].value='   ';await nodes['pet-form'].fire('submit');
  assert.equal(petAttempts,0);
  nodes['pet-name'].value='  Luna  ';nodes['pet-meals'].value='2';
  await nodes['pet-form'].fire('submit');
  assert.equal(nodes['pet-dialog'].open,true);assert.equal(nodes['pet-name'].disabled,true);
  assert.equal(nodes['pet-submit'].textContent,'Retry save');
  assert.equal(nodes['send-message'].disabled,true);
  await nodes['pet-form'].fire('submit');
  const petRequests=fetches.filter(f=>f.url==='/api/pets');
  assert.deepEqual(petRequests[0].body,petRequests[1].body);
  assert.equal(petRequests[1].body.name,'Luna');assert.equal(petRequests[1].body.meals_per_day,2);
  assert.equal(nodes['cat-select'].value,'new-pet');assert.equal(nodes['pet-dialog'].open,false);
  assert.match(nodes['request-status'].textContent,/Luna was added/);
  assert.equal(nodes['send-message'].disabled,false);
  console.log('Chat UI retry, session, login and card bridge assertions passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
