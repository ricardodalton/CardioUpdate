/* Read the selected daily briefing using the device's speech service. */
(function (root) {
  'use strict';

  function splitText(text, limit = 220) {
    const words = String(text || '').replace(/\s+/g, ' ').trim().split(' ');
    const chunks = [];
    let chunk = '';
    for (const word of words) {
      if (!word) continue;
      if (chunk && chunk.length + word.length + 1 > limit) {
        chunks.push(chunk);
        chunk = '';
      }
      chunk += (chunk ? ' ' : '') + word;
    }
    if (chunk) chunks.push(chunk);
    return chunks;
  }

  function buildSegments(edition) {
    const items = (edition && Array.isArray(edition.items)) ? edition.items : [];
    if (!items.length) return [];
    const segments = [];
    const add = (text, item) => splitText(text).forEach(text => segments.push({text, item}));
    const day = new Date(String(edition.date || '') + 'T12:00:00');
    const date = Number.isNaN(day.getTime()) ? '' : day.toLocaleDateString('es-AR', {
      day: 'numeric', month: 'long', year: 'numeric'
    });
    add(`CardioUpdate. Briefing${date ? ' del ' + date : ''}. ${items.length} novedades.`, 0);
    items.forEach((item, i) => {
      add(`Noticia ${i + 1} de ${items.length}. ${item.title || ''}`, i + 1);
      if (item.journal) add(`Fuente: ${item.journal}.`, i + 1);
      for (const [field, label] of [
        ['what_happened', 'Hallazgo principal'],
        ['why_relevant', 'Por qué es relevante'],
        ['practical_implication', 'Implicación práctica']
      ]) {
        if (item[field]) add(`${label}. ${item[field]}`, i + 1);
      }
    });
    return segments;
  }

  function createBriefingAudio(env) {
    const synth = env.speechSynthesis;
    const supported = Boolean(synth && typeof synth.speak === 'function' &&
      typeof synth.cancel === 'function' && typeof env.SpeechSynthesisUtterance === 'function');
    const state = {edition: null, segments: [], position: 0, offset: 0,
      running: false, paused: false, completed: false, token: 0, utterance: null, message: ''};
    const el = id => env.document.getElementById(id);

    function update() {
      const play = el('briefAudioPlay'), pause = el('briefAudioPause'), stop = el('briefAudioStop');
      if (play) {
        play.disabled = !supported || (state.running && !state.paused);
        play.textContent = state.paused ? 'Continuar' : state.completed ? 'Escuchar de nuevo' : 'Escuchar briefing';
      }
      if (pause) pause.disabled = !supported || !state.running || state.paused;
      if (stop) stop.disabled = !supported || !state.running;
      const status = el('briefAudioStatus');
      if (status) status.textContent = state.message || (supported
        ? 'Lectura en español con la voz del dispositivo.'
        : 'La lectura en voz alta no está disponible en este navegador.');
    }

    function stop(message = 'Audio detenido.') {
      const active = state.running;
      state.token++;
      state.running = false;
      state.paused = false;
      state.completed = false;
      state.segments = [];
      state.position = 0;
      state.offset = 0;
      state.utterance = null;
      state.message = message;
      if (supported && active) synth.cancel();
      update();
    }

    function speakCurrent() {
      if (!state.running || state.paused) return;
      const segment = state.segments[state.position];
      if (!segment) {
        state.running = false;
        state.completed = true;
        state.utterance = null;
        state.message = 'Lectura finalizada.';
        update();
        return;
      }
      const token = ++state.token;
      const offset = state.offset;
      const utterance = new env.SpeechSynthesisUtterance(segment.text.slice(offset));
      const voices = typeof synth.getVoices === 'function' ? synth.getVoices() : [];
      const spanish = voice => /^es(?:[-_]|$)/i.test(voice.lang || '');
      const argentine = voice => /^es[-_]AR$/i.test(voice.lang || '');
      const voice = voices.find(v => argentine(v) && v.localService) || voices.find(argentine) ||
        voices.find(v => spanish(v) && v.localService) || voices.find(spanish);
      utterance.lang = voice ? voice.lang : 'es-AR';
      if (voice) utterance.voice = voice;
      utterance.rate = 1;
      state.utterance = utterance; // Retain the native object while it is speaking.
      state.message = segment.item ? `Escuchando noticia ${segment.item} de ${state.edition.items.length}.` : 'Comenzando el briefing.';
      utterance.onboundary = event => {
        if (token !== state.token || !Number.isInteger(event.charIndex)) return;
        if (event.charIndex >= 0 && event.charIndex < utterance.text.length) state.offset = offset + event.charIndex;
      };
      utterance.onend = () => {
        if (token !== state.token || !state.running || state.paused) return;
        state.position++;
        state.offset = 0;
        speakCurrent();
      };
      utterance.onerror = () => {
        if (token !== state.token) return;
        stop('No se pudo reproducir el audio. Probá abrir la página en Safari o Chrome y tocar Escuchar nuevamente.');
      };
      update();
      try { synth.speak(utterance); }
      catch (_) { utterance.onerror(); }
    }

    function play() {
      if (!supported || !state.edition || (state.running && !state.paused)) return;
      if (!state.paused) {
        state.segments = buildSegments(state.edition);
        state.position = 0;
        state.offset = 0;
      }
      if (!state.segments.length) return;
      state.running = true;
      state.paused = false;
      state.completed = false;
      // Speak directly in the click handler; mobile browsers require a user gesture.
      speakCurrent();
    }

    function pause() {
      if (!supported || !state.running || state.paused) return;
      // Cancel and retain our position instead of relying on native pause support,
      // which varies between mobile speech engines. Resume at the last word event,
      // or replay the current short segment when the engine has no boundaries.
      state.token++;
      state.paused = true;
      state.utterance = null;
      state.message = 'Audio en pausa.';
      synth.cancel();
      update();
    }

    function mount(edition) {
      if (edition !== state.edition) {
        stop('');
        state.edition = edition;
      }
      const controls = el('briefingAudio');
      if (!controls) return;
      controls.innerHTML = '<button type="button" id="briefAudioPlay">Escuchar briefing</button>' +
        '<button type="button" id="briefAudioPause" disabled>Pausar</button>' +
        '<button type="button" id="briefAudioStop" disabled>Detener</button>' +
        '<p id="briefAudioStatus" role="status" aria-live="polite"></p>';
      el('briefAudioPlay').onclick = play;
      el('briefAudioPause').onclick = pause;
      el('briefAudioStop').onclick = () => stop();
      update();
    }

    if (typeof env.addEventListener === 'function') env.addEventListener('pagehide', () => stop(''));
    return {mount, play, pause, stop};
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {splitText, buildSegments, createBriefingAudio};
  if (root && root.document) root.CardioUpdateBriefingAudio = createBriefingAudio(root);
})(typeof window !== 'undefined' ? window : globalThis);
