/*
 * World Conflicts — núcleo compartilhado (navegador + Node).
 * Legendas de regime/espectro, cálculo de tempo transcorrido,
 * parser RSS, consulta Wikidata e mesclagem de dados externos.
 */
(function (root) {
  'use strict';

  const REGIMES = [
    { id: 'democracia_plena',  label: 'Democracia plena',        color: '#2f7fd1' },
    { id: 'democracia_falha',  label: 'Democracia imperfeita',   color: '#7cc0ea' },
    { id: 'hibrido',           label: 'Regime híbrido',          color: '#f2c14e' },
    { id: 'autoritario',       label: 'Autoritário',             color: '#e8743b' },
    { id: 'ditadura_militar',  label: 'Ditadura militar',        color: '#9c2a10' },
    { id: 'partido_unico',     label: 'Partido único',           color: '#d63447' },
    { id: 'monarquia_absoluta',label: 'Monarquia absoluta',      color: '#8e5bd6' },
    { id: 'teocracia',         label: 'Teocracia',               color: '#1f9d74' },
    { id: 'transicao',         label: 'Transição / Estado dividido', color: '#a3a7b3' },
    { id: 'territorio',        label: 'Território / sem soberania plena', color: '#4b5263' },
  ];

  const ESPECTROS = [
    { id: 'esquerda',        label: 'Esquerda',        color: '#d7263d' },
    { id: 'centro_esquerda', label: 'Centro-esquerda', color: '#f28b8b' },
    { id: 'centro',          label: 'Centro',          color: '#e9c46a' },
    { id: 'centro_direita',  label: 'Centro-direita',  color: '#7fb2e5' },
    { id: 'direita',         label: 'Direita',         color: '#1f5fbf' },
    { id: 'nao_aplicavel',   label: 'Sem ideologia definida (militar, monárquico, personalista)', color: '#6b7280' },
  ];

  const STATUS = {
    'ativo':        { label: 'Ativo',          color: '#ff4d4f' },
    'cessar-fogo':  { label: 'Cessar-fogo',    color: '#f5a623' },
    'negociacao':   { label: 'Em negociação',  color: '#f5d142' },
    'tensao':       { label: 'Tensão',         color: '#c084fc' },
    'congelado':    { label: 'Congelado',      color: '#60a5fa' },
    'transicao':    { label: 'Transição',      color: '#34d399' },
  };

  const INTENSIDADE = {
    alta:  { label: 'Alta',  radius: 13 },
    media: { label: 'Média', radius: 10 },
    baixa: { label: 'Baixa', radius: 7 },
  };

  const byId = (list) => Object.fromEntries(list.map((x) => [x.id, x]));
  const REGIME_BY_ID = byId(REGIMES);
  const ESPECTRO_BY_ID = byId(ESPECTROS);

  /* ---------- tempo transcorrido ---------- */
  function parseDate(s) {
    const [y, m, d] = String(s).split('-').map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
  }

  function elapsed(start, now) {
    now = now || new Date();
    const a = parseDate(start);
    let y = now.getFullYear() - a.getFullYear();
    let m = now.getMonth() - a.getMonth();
    let d = now.getDate() - a.getDate();
    if (d < 0) { m--; d += new Date(now.getFullYear(), now.getMonth(), 0).getDate(); }
    if (m < 0) { y--; m += 12; }
    const days = Math.floor((now - a) / 86400000);
    return { anos: y, meses: m, dias: d, totalDias: days };
  }

  function elapsedText(start, now) {
    const e = elapsed(start, now);
    const p = [];
    if (e.anos) p.push(e.anos + (e.anos === 1 ? ' ano' : ' anos'));
    if (e.meses) p.push(e.meses + (e.meses === 1 ? ' mês' : ' meses'));
    if (e.dias || !p.length) p.push(e.dias + (e.dias === 1 ? ' dia' : ' dias'));
    return p.length > 1 ? p.slice(0, -1).join(', ') + ' e ' + p[p.length - 1] : p[0];
  }

  const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  function fmtDate(s) {
    const d = parseDate(s);
    return d.getDate() + ' ' + MESES[d.getMonth()] + ' ' + d.getFullYear();
  }

  /* ---------- RSS (Google Notícias) ---------- */
  const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
  function decode(s) {
    return String(s || '')
      .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
      .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
      .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
      .replace(/&([a-z]+);/gi, (m, n) => (n.toLowerCase() in ENT ? ENT[n.toLowerCase()] : m))
      .trim();
  }
  const tag = (xml, t) => { const m = xml.match(new RegExp('<' + t + '[^>]*>([\\s\\S]*?)</' + t + '>', 'i')); return m ? decode(m[1]) : ''; };

  function parseRSS(xml, max) {
    const out = [];
    const items = String(xml).match(/<item[\s>][\s\S]*?<\/item>/gi) || [];
    for (const it of items) {
      let titulo = tag(it, 'title').replace(/<[^>]+>/g, '');
      const fonte = tag(it, 'source');
      if (fonte && titulo.endsWith(' - ' + fonte)) titulo = titulo.slice(0, -(fonte.length + 3));
      const link = tag(it, 'link');
      const pub = tag(it, 'pubDate');
      const t = Date.parse(pub);
      if (!titulo || !link) continue;
      out.push({ titulo, link, fonte, data: isNaN(t) ? '' : new Date(t).toISOString() });
    }
    const seen = new Set();
    return out
      .filter((n) => { const k = n.titulo.toLowerCase().slice(0, 70); if (seen.has(k)) return false; seen.add(k); return true; })
      .sort((a, b) => (b.data || '').localeCompare(a.data || ''))
      .slice(0, max || 8);
  }

  function gnewsUrl(q, days) {
    return 'https://news.google.com/rss/search?q=' + encodeURIComponent(q + ' when:' + (days || 7) + 'd') +
      '&hl=pt-BR&gl=BR&ceid=BR:pt-419';
  }

  function gdeltUrl(q, max) {
    return 'https://api.gdeltproject.org/api/v2/doc/doc?query=' + encodeURIComponent(q) +
      '&mode=artlist&format=json&sort=datedesc&timespan=7d&maxrecords=' + (max || 10);
  }

  function parseGdelt(json) {
    const arts = (json && json.articles) || [];
    return arts.map((a) => {
      const s = String(a.seendate || '');
      const iso = s.length >= 15 ? s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8) + 'T' + s.slice(9, 11) + ':' + s.slice(11, 13) + ':' + s.slice(13, 15) + 'Z' : '';
      return { titulo: a.title, link: a.url, fonte: a.domain, data: iso };
    }).filter((n) => n.titulo && n.link);
  }

  /* ---------- Wikidata: chefes de Estado e de governo atuais ---------- */
  const WIKIDATA_SPARQL = `
SELECT ?iso ?papel ?pessoaLabel ?rank WHERE {
  ?pais wdt:P298 ?iso .
  FILTER NOT EXISTS { ?pais wdt:P576 ?fim . }
  { ?pais p:P35 ?st . ?st ps:P35 ?pessoa . BIND("estado" AS ?papel) }
  UNION
  { ?pais p:P6 ?st . ?st ps:P6 ?pessoa . BIND("governo" AS ?papel) }
  ?st wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  FILTER NOT EXISTS { ?st pq:P582 ?ate . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,pt-br,en". }
}`;

  function wikidataUrl() {
    return 'https://query.wikidata.org/sparql?format=json&query=' + encodeURIComponent(WIKIDATA_SPARQL);
  }

  // Retorna { ISO3: { estado: "Nome", governo: "Nome" } }, preferindo declarações de rank "preferred".
  function parseWikidata(json) {
    const acc = {};
    for (const b of (json && json.results && json.results.bindings) || []) {
      const iso = b.iso.value, papel = b.papel.value, nome = b.pessoaLabel.value;
      if (/^Q\d+$/.test(nome)) continue; // sem rótulo
      const pref = /PreferredRank$/.test(b.rank.value);
      const slot = ((acc[iso] = acc[iso] || {})[papel] = acc[iso][papel] || { pref: [], normal: [] });
      const arr = pref ? slot.pref : slot.normal;
      if (!arr.includes(nome)) arr.push(nome);
    }
    const out = {};
    for (const [iso, papeis] of Object.entries(acc)) {
      out[iso] = {};
      for (const [papel, s] of Object.entries(papeis)) {
        const nomes = s.pref.length ? s.pref : s.normal;
        if (nomes.length && nomes.length <= 3) out[iso][papel] = nomes.join(' / ');
      }
    }
    return out;
  }

  /* ---------- mesclagem com fontes externas ---------- */
  // ext pode conter: { conflitos: [...], governos: {id: {...}}, lideres: {...}, noticias: {...} }
  function merge(base, ext) {
    if (!ext || typeof ext !== 'object') return base;
    const out = {
      conflitos: base.conflitos.slice(),
      governos: Object.assign({}, base.governos),
      lideres: Object.assign({}, base.lideres),
      noticias: Object.assign({}, base.noticias),
    };
    for (const c of ext.conflitos || []) {
      if (!c || !c.id) continue;
      const i = out.conflitos.findIndex((x) => x.id === c.id);
      if (c.remover) { if (i >= 0) out.conflitos.splice(i, 1); continue; }
      if (i >= 0) out.conflitos[i] = Object.assign({}, out.conflitos[i], c);
      else if (c.nome && c.pontos) out.conflitos.push(c);
    }
    const gov = ext.governos && (ext.governos.paises || ext.governos);
    for (const [k, v] of Object.entries(gov || {})) out.governos[k] = Object.assign({}, out.governos[k], v);
    Object.assign(out.lideres, ext.lideres || {});
    Object.assign(out.noticias, ext.noticias || {});
    return out;
  }

  const api = {
    REGIMES, ESPECTROS, STATUS, INTENSIDADE, REGIME_BY_ID, ESPECTRO_BY_ID,
    elapsed, elapsedText, fmtDate, parseDate,
    decode, parseRSS, gnewsUrl, gdeltUrl, parseGdelt,
    WIKIDATA_SPARQL, wikidataUrl, parseWikidata, merge,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.WC = api;
})(typeof self !== 'undefined' ? self : this);
