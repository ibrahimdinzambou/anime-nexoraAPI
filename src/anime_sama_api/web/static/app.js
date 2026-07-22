const $ = (selector) => document.querySelector(selector);
const api = (path) => fetch(path).then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.error || 'Erreur API'); return body; });
let selectedSlug = '';

function slugFromUrl(url) { const parts = new URL(url).pathname.split('/').filter(Boolean); const i = parts.indexOf('catalogue'); return i >= 0 ? parts[i + 1] : parts.at(-1); }
function setMessage(text = '') { $('#message').textContent = text; }

$('#search-form').addEventListener('submit', async (event) => {
  event.preventDefault(); setMessage(''); const query = $('#search-input').value.trim();
  $('#results').className = 'results empty-state'; $('#results').innerHTML = '<span class="empty-icon">…</span><p>Recherche en cours.</p>';
  try { const endpoint = query ? `/api/v1/search?q=${encodeURIComponent(query)}` : '/api/v1/catalogues?limit=24'; const {data, count} = await api(endpoint); $('#result-count').textContent = `${count} titre${count > 1 ? 's' : ''}`; renderResults(data); }
  catch (error) { setMessage(error.message); $('#results').innerHTML = '<span class="empty-icon">!</span><p>Impossible de charger les résultats.</p>'; }
});

$('#browse-button').addEventListener('click', () => { $('#search-input').value = ''; $('#search-form').requestSubmit(); });

function renderResults(items) {
  if (!items.length) { $('#results').innerHTML = '<span class="empty-icon">∅</span><p>Aucun titre trouvé.</p>'; return; }
  $('#results').className = 'results'; $('#results').innerHTML = items.map((item, index) => `<article class="card" data-slug="${slugFromUrl(item.url)}" data-index="${index}"><img src="${item.image_url || ''}" alt="" loading="lazy"><div class="card-body"><h3>${item.name || 'Sans titre'}</h3><span class="tag">${(item.categories || []).join(' · ') || 'ANIME'}</span></div></article>`).join('');
  document.querySelectorAll('.card').forEach(card => card.addEventListener('click', () => selectCatalogue(card.dataset.slug, card)));
}

async function selectCatalogue(slug, card) {
  selectedSlug = slug; document.querySelectorAll('.card').forEach(item => item.classList.remove('active')); card.classList.add('active'); $('#selected-title').textContent = 'Chargement…';
  try { const [detail, seasons] = await Promise.all([api(`/api/v1/catalogue/${encodeURIComponent(slug)}`), api(`/api/v1/catalogue/${encodeURIComponent(slug)}/seasons`)]); renderDetails(detail.data, seasons.data); }
  catch (error) { $('#details').innerHTML = `<p>${error.message}</p>`; }
}
function renderDetails(detail, seasons) {
  $('#selected-title').textContent = detail.name; $('#details').className = 'details'; $('#details').innerHTML = `<h2>${detail.name}</h2><span class="tag">${(detail.languages || []).join(' · ')}</span><p class="synopsis">${detail.synopsis || 'Aucun synopsis disponible.'}</p><div class="season-label">SAISONS</div><div class="season-list">${seasons.map((s, i) => `<button class="season" data-season="${s.url}" data-name="${s.name}">${s.name || `Saison ${i + 1}`}</button>`).join('') || '<span class="tag">Aucune saison trouvée.</span>'}</div><div id="episodes"></div>`;
  document.querySelectorAll('.season').forEach(button => button.addEventListener('click', () => loadEpisodes(button)));
}
async function loadEpisodes(button) {
  document.querySelectorAll('.season').forEach(item => item.classList.remove('active')); button.classList.add('active'); const seasonSlug = new URL(button.dataset.season).pathname.split('/').filter(Boolean).at(-1); const target = $('#episodes'); target.innerHTML = '<div class="season-label">ÉPISODES · CHARGEMENT…</div>';
  try { const {data} = await api(`/api/v1/catalogue/${encodeURIComponent(selectedSlug)}/seasons/${encodeURIComponent(seasonSlug)}/episodes`); target.innerHTML = `<div class="season-label">ÉPISODES · ${data.length}</div><div class="episode-list">${data.map(item => `<button class="episode" data-index="${item.index}">EP ${String(item.index).padStart(2, '0')}</button>`).join('')}</div>`; data.forEach((item, i) => document.querySelectorAll('.episode')[i].addEventListener('click', () => playEpisode(item))); }
  catch (error) { target.innerHTML = `<p class="tag">${error.message}</p>`; }
}
function playEpisode(episode) {
  const languages = Object.entries(episode.languages || {}); const player = languages.flatMap(([, urls]) => urls)[0]; if (!player) { setMessage('Aucun lecteur disponible pour cet épisode.'); return; }
  $('#player-label').textContent = `${episode.short_name} · épisode ${episode.index}`; $('#player-placeholder').hidden = true; $('#player').hidden = false; $('#player').src = player; $('#player').scrollIntoView({behavior:'smooth', block:'center'});
}
