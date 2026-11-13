'use strict';
const assert = require('node:assert/strict');
const {splitText, buildSegments, createBriefingAudio} = require('../briefing-audio.js');

const edition = {date: '2026-11-13', items: Array.from({length: 10}, (_, i) => ({
  title: `Título ${i + 1}.`, journal: 'Revista científica',
  what_happened: `Hallazgo ${i + 1}.`, why_relevant: `Limitaciones ${i + 1}.`,
  practical_implication: `Implicación ${i + 1}.`, url: 'https://doi.org/not-for-reading'
}))};

function setup(supported = true) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {innerHTML: '', textContent: '', disabled: false});
    return nodes.get(id);
  };
  const spoken = [], events = {};
  let cancellations = 0;
  const env = {
    document: {getElementById: node},
    addEventListener: (name, handler) => { events[name] = handler; }
  };
  if (supported) {
    env.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
    env.speechSynthesis = {
      getVoices: () => [{lang: 'en-US', localService: true}, {lang: 'es-ES', localService: true}, {lang: 'es-AR', localService: true}],
      speak: utterance => spoken.push(utterance),
      cancel: () => { cancellations++; }
    };
  }
  const audio = createBriefingAudio(env);
  audio.mount(edition);
  return {audio, env, node, spoken, events, cancellations: () => cancellations};
}

let checks = 0;
function test(name, run) {
  run(); checks++;
  console.log('ok - ' + name);
}

test('all ten items and their limitations are read in editorial order, without URLs', () => {
  const segments = buildSegments(edition), text = segments.map(x => x.text).join(' ');
  assert.equal(new Set(segments.filter(x => x.item).map(x => x.item)).size, 10);
  assert(text.indexOf('Título 1.') < text.indexOf('Título 10.'));
  for (let i = 1; i <= 10; i++) for (const field of ['Título', 'Hallazgo', 'Limitaciones', 'Implicación']) assert(text.includes(`${field} ${i}.`));
  assert(!text.includes('doi.org'));
});

test('long passages use short segments without dropping or changing words', () => {
  const text = Array.from({length: 300}, (_, i) => `palabra${i}`).join(' ');
  const chunks = splitText(text);
  assert(chunks.every(x => x.length <= 220));
  assert.equal(chunks.join(' '), text);
  assert.deepEqual(buildSegments({items: []}), []);
});

test('mount never autoplays and play chooses a Spanish voice from the device', () => {
  const t = setup();
  assert.equal(t.spoken.length, 0);
  t.node('briefAudioPlay').onclick();
  assert.equal(t.spoken.length, 1);
  assert.equal(t.spoken[0].lang, 'es-AR');
  assert.equal(t.node('briefAudioPlay').disabled, true);
  assert.equal(t.node('briefAudioPause').disabled, false);
  t.audio.play();
  assert.equal(t.spoken.length, 1);
});

test('pause cancels speech, ignores late end events and resumes at the last word', () => {
  const t = setup();
  t.audio.play();
  const first = t.spoken[0];
  first.onboundary({charIndex: 13});
  t.audio.pause();
  assert.equal(t.cancellations(), 1);
  assert.equal(t.node('briefAudioPlay').textContent, 'Continuar');
  first.onend();
  assert.equal(t.spoken.length, 1);
  t.audio.play();
  assert.equal(t.spoken[1].text, first.text.slice(13));
});

test('engines without word boundary events can pause and replay only the current short segment', () => {
  const t = setup();
  t.audio.play();
  const first = t.spoken[0];
  t.audio.pause(); t.audio.play();
  assert.equal(t.spoken[1].text, first.text);
});

test('stop prevents queued callbacks from continuing and resets the next reading', () => {
  const t = setup();
  t.audio.play();
  const first = t.spoken[0];
  t.audio.stop(); first.onend(); first.onerror();
  assert.equal(t.spoken.length, 1);
  assert.equal(t.node('briefAudioStop').disabled, true);
  t.audio.play();
  assert.equal(t.spoken[1].text, first.text);
});

test('changing edition cancels the old reading without starting the new one', () => {
  const t = setup();
  t.audio.play();
  const first = t.spoken[0];
  t.audio.mount({...edition, date: '2026-11-12'});
  first.onend();
  assert.equal(t.cancellations(), 1);
  assert.equal(t.spoken.length, 1);
  assert.equal(t.node('briefAudioPause').disabled, true);
});

test('completion re-enables playback after every segment in order', () => {
  const t = setup(), segments = buildSegments(edition);
  t.audio.play();
  for (let i = 0; i < segments.length; i++) {
    assert.equal(t.spoken[i].text, segments[i].text);
    t.spoken[i].onend();
  }
  assert.equal(t.spoken.length, segments.length);
  assert.equal(t.node('briefAudioStatus').textContent, 'Lectura finalizada.');
  assert.equal(t.node('briefAudioPlay').disabled, false);
});

test('unavailable speech APIs disable playback and explain availability', () => {
  const t = setup(false);
  assert.equal(t.node('briefAudioPlay').disabled, true);
  assert(t.node('briefAudioStatus').textContent.includes('no está disponible'));
  t.audio.play(); t.audio.pause(); t.audio.stop();
  assert.equal(t.spoken.length, 0);
});

test('speech errors and page exit leave controls stopped', () => {
  const t = setup();
  t.audio.play(); t.spoken[0].onerror();
  assert(t.node('briefAudioStatus').textContent.includes('No se pudo'));
  assert.equal(t.node('briefAudioPlay').disabled, false);
  t.audio.play(); t.events.pagehide();
  assert.equal(t.node('briefAudioStop').disabled, true);
});

console.log(`${checks} audio checks passed.`);
