/*
 * Brasil Gossips — núcleo compartilhado (navegador + Node).
 * Lista de fontes RSS, parser RSS/Atom sem dependências,
 * extração de imagem e classificação por categoria.
 */
(function (root) {
  'use strict';

  const CATEGORIES = [
    { id: 'novidades', label: 'Novidades',        emoji: '✨', color: '#FF4FA3' },
    { id: 'romances',  label: 'Romances',         emoji: '💘', color: '#FF5C7A' },
    { id: 'politica',  label: 'Política',         emoji: '🏛️', color: '#4CC9F0' },
    { id: 'tv',        label: 'TV & Cinema',      emoji: '🎬', color: '#F5C542' },
    { id: 'teen',      label: 'Teen',             emoji: '🎧', color: '#A78BFA' },
    { id: 'festas',    label: 'Festas & Eventos', emoji: '🥂', color: '#3DDC97' },
  ];

  // cat = categoria padrão da fonte; max = limite de itens por fonte.
  const gnews = (q) =>
    'https://news.google.com/rss/search?q=' + encodeURIComponent(q + ' when:2d') +
    '&hl=pt-BR&gl=BR&ceid=BR:pt-419';

  const FEEDS = [
    { name: 'Hugo Gloss',        url: 'https://hugogloss.uol.com.br/feed/',                     cat: 'novidades', max: 20 },
    { name: 'Leo Dias',          url: 'https://www.metropoles.com/colunas/leo-dias/feed',       cat: 'novidades', max: 20 },
    { name: 'Metrópoles Entret.',url: 'https://www.metropoles.com/entretenimento/feed',         cat: 'novidades', max: 15 },
    { name: 'g1 Pop & Arte',     url: 'https://g1.globo.com/rss/g1/pop-arte/',                  cat: 'tv',        max: 15 },
    { name: 'Contigo',           url: 'https://contigo.com.br/feed',                            cat: 'novidades', max: 15 },
    { name: 'Caras',             url: 'https://caras.com.br/feed',                              cat: 'novidades', max: 15 },
    { name: 'Quem',              url: 'https://revistaquem.globo.com/rss/quem/',                cat: 'novidades', max: 15 },
    { name: 'O Fuxico',          url: 'https://www.ofuxico.com.br/feed/',                       cat: 'novidades', max: 15 },
    { name: 'NaTelinha',         url: 'https://natelinha.uol.com.br/rss',                       cat: 'tv',        max: 15 },
    { name: 'Notícias da TV',    url: 'https://noticiasdatv.uol.com.br/feed',                   cat: 'tv',        max: 15 },
    { name: 'Omelete',           url: 'https://www.omelete.com.br/rss',                         cat: 'tv',        max: 12 },
    { name: 'Capricho',          url: 'https://capricho.abril.com.br/feed/',                    cat: 'teen',      max: 15 },
    { name: 'Todateen',          url: 'https://todateen.uol.com.br/feed/',                      cat: 'teen',      max: 15 },
    { name: 'Glamurama',         url: 'https://glamurama.uol.com.br/feed/',                     cat: 'festas',    max: 15 },
    { name: 'Igor Gadelha',      url: 'https://www.metropoles.com/colunas/igor-gadelha/feed',   cat: 'politica',  max: 12 },
    { name: 'Poder360',          url: 'https://www.poder360.com.br/feed/',                      cat: 'politica',  max: 12 },
    { name: 'g1 Política',       url: 'https://g1.globo.com/rss/g1/politica/',                  cat: 'politica',  max: 10 },
    // Reforço via Google Notícias (sem imagem na maioria das vezes)
    { name: 'Google Notícias', url: gnews('fofoca famosos'),                                  cat: 'novidades', max: 10, aggregator: true },
    { name: 'Google Notícias', url: gnews('namoro OR affair OR término famosos'),              cat: 'romances',  max: 10, aggregator: true },
    { name: 'Google Notícias', url: gnews('bastidores Brasília fofoca política'),              cat: 'politica',  max: 8,  aggregator: true },
    { name: 'Google Notícias', url: gnews('novela OR BBB OR "A Fazenda" OR série estreia'),   cat: 'tv',        max: 10, aggregator: true },
    { name: 'Google Notícias', url: gnews('influenciadora OR tiktoker OR youtuber polêmica'), cat: 'teen',      max: 8,  aggregator: true },
    { name: 'Google Notícias', url: gnews('festa famosos OR aniversário famosos OR premiação'), cat: 'festas',  max: 10, aggregator: true },
  ];

  // Palavras‑chave por categoria (sem acento, minúsculas). Peso 2 = forte.
  const RULES = {
    romances: [
      ['namor', 2], ['affair', 2], ['casal', 1], ['beij', 1], ['ficando', 2], ['termin', 1],
      ['separa', 2], ['divorci', 2], ['noiv', 2], ['casament', 1], ['casou', 2], ['casam', 1],
      ['traic', 2], [' trai ', 2], [' traiu', 2], ['crush', 2], ['romance', 2], ['apaixonad', 2], ['reat', 2],
      ['assume relac', 3], ['relacionamento', 2], ['ex-marido', 2], ['ex-mulher', 2], ['ex-namorad', 2],
      ['marido', 1], ['esposa', 1], ['namorada', 2], ['namorado', 2], ['flagra', 1], ['pedido de casamento', 3],
      ['lua de mel', 3], ['gravida', 1], ['gestacao', 1], ['amor', 1], ['ciume', 2],
    ],
    politica: [
      [' lula', 2], ['bolsonaro', 2], ['presidente', 1], ['senador', 2], ['deputad', 2], ['ministr', 2],
      [' stf ', 2], ['eleic', 2], ['prefeit', 2], ['governador', 2], ['governo', 1], ['politic', 2],
      ['congresso', 2], ['camara', 1], ['planalto', 2], ['brasilia', 1], ['partido', 2], ['candidat', 2],
      ['moraes', 2], ['michelle', 1], ['janja', 2], ['tarcisio', 2], ['haddad', 2], [' pt ', 1], [' pl ', 1],
      [' cpi ', 2], ['impeachment', 3], ['vereador', 2], ['primeira-dama', 2], ['trump', 1],
    ],
    tv: [
      ['novela', 2], ['bbb', 2], ['big brother', 2], ['a fazenda', 2], ['reality', 2], ['filme', 2],
      ['serie', 2], ['netflix', 2], ['globoplay', 2], ['prime video', 2], ['disney+', 2], [' hbo', 2],
      ['cinema', 2], ['estreia', 2], [' ator ', 1], ['atriz', 1], ['tv globo', 2], ['sbt', 2], [' record ', 1],
      [' band ', 1], ['apresentador', 2], ['apresentadora', 2], ['programa', 1], ['emissora', 2],
      ['oscar', 2], ['trailer', 2], ['bilheteria', 2], ['elenco', 2], ['personagem', 2], ['capitulo', 2],
      ['streaming', 2], ['eliminad', 2], ['paredao', 2], ['the voice', 2], ['domingao', 2], ['fantastico', 1],
    ],
    teen: [
      ['teen', 3], ['influenciador', 2], ['influenciadora', 2], ['influencer', 2], ['tiktok', 2],
      ['tiktoker', 3], ['youtuber', 3], ['k-pop', 3], ['kpop', 3], [' bts ', 2], ['blackpink', 3],
      ['jovem', 1], ['adolescente', 2], [' fas ', 1], ['fandom', 3], ['taylor swift', 2], ['olivia rodrigo', 3],
      ['sabrina carpenter', 3], ['billie eilish', 3], ['gamer', 2], ['streamer', 2], ['twitch', 2],
      ['viral', 1], ['trend', 2], ['meme', 2], ['larissa manoela', 1], ['virginia', 1], ['instagram', 1],
    ],
    festas: [
      ['festa', 2], ['aniversario', 2], ['comemor', 1], [' show', 1], ['festival', 2], ['evento', 2],
      ['baile', 2], ['carnaval', 2], ['reveillon', 2], ['premiac', 2], ['premio', 1], ['red carpet', 3],
      ['tapete vermelho', 3], ['lancamento', 1], ['rock in rio', 3], ['lollapalooza', 3], [' gala ', 2],
      ['met gala', 3], ['look', 1], ['convidad', 2], ['celebra', 1], ['cha revelacao', 3], ['cha de bebe', 3],
      ['halloween', 2], ['balada', 2], ['camarote', 3], ['desfile', 2], ['sao joao', 2], [' natal ', 1],
    ],
  };

  function norm(s) {
    return String(s || '')
      .toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function classify(title, summary, feedCat) {
    const text = (' ' + norm(title) + ' ' + norm(title) + ' ' + norm(summary) + ' ')
      .replace(/[^a-z0-9+\-]+/g, ' ');
    const scores = {};
    for (const [cat, words] of Object.entries(RULES)) {
      let sc = 0;
      for (const [w, p] of words) if (text.includes(w)) sc += p;
      if (cat === feedCat) sc += 2;
      scores[cat] = sc;
    }
    const cats = Object.entries(scores)
      .filter(([, s]) => s >= 3)
      .sort((a, b) => b[1] - a[1])
      .map(([c]) => c);
    if (feedCat && feedCat !== 'novidades' && !cats.includes(feedCat)) cats.push(feedCat);
    // Toda fofoca também é "novidade"
    cats.push('novidades');
    return [...new Set(cats)];
  }

  // ── Parser RSS/Atom por regex (sem DOM) ──
  const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', hellip: '…', ndash: '–', mdash: '—',
    lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”', laquo: '«', raquo: '»' };

  function decode(s) {
    return String(s || '').replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
      if (e[0] === '#') {
        const n = e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return isFinite(n) ? String.fromCodePoint(n) : m;
      }
      const v = ENT[e.toLowerCase()];
      return v !== undefined ? v : m;
    });
  }

  function unCdata(s) {
    return String(s || '').replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1');
  }

  function stripTags(html) {
    return decode(String(html || '')
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' '))
      .replace(/\s+/g, ' ')
      .trim();
  }

  function tag(block, name) {
    const re = new RegExp('<' + name + '(?:\\s[^>]*)?>([\\s\\S]*?)</' + name + '>', 'i');
    const m = block.match(re);
    return m ? unCdata(m[1]).trim() : '';
  }

  function attr(block, name, at) {
    const re = new RegExp('<' + name + '\\b[^>]*?\\b' + at + '\\s*=\\s*["\']([^"\']+)["\']', 'i');
    const m = block.match(re);
    return m ? decode(m[1]) : '';
  }

  function findImage(block) {
    // media:content / media:thumbnail / enclosure
    const mediaRe = /<(media:content|media:thumbnail|enclosure)\b([^>]*)>/gi;
    let m;
    while ((m = mediaRe.exec(block))) {
      const a = m[2];
      const url = (a.match(/\burl\s*=\s*["']([^"']+)["']/i) || [])[1];
      const type = (a.match(/\btype\s*=\s*["']([^"']+)["']/i) || [])[1] || '';
      const medium = (a.match(/\bmedium\s*=\s*["']([^"']+)["']/i) || [])[1] || '';
      if (url && (m[1].toLowerCase() !== 'enclosure' || /image/i.test(type) || /\.(jpe?g|png|webp|gif)/i.test(url))
          && !/video|audio/i.test(type + medium)) {
        return decode(url);
      }
    }
    // <img src> no conteúdo
    const html = decode(unCdata(block));
    const img = html.match(/<img\b[^>]*?\b(?:data-src|src)\s*=\s*["']([^"']+)["']/i);
    if (img && !/pixel|feedburner|gravatar|emoji|1x1|spacer/i.test(img[1])) return img[1];
    return '';
  }

  function cleanTitle(t, aggregator) {
    let s = stripTags(decode(unCdata(t)));
    let source = '';
    if (aggregator) {
      // Google Notícias: "Título - Veículo"
      const i = s.lastIndexOf(' - ');
      if (i > 20) { source = s.slice(i + 3).trim(); s = s.slice(0, i).trim(); }
    }
    return { title: s, source };
  }

  function parseFeed(xml, feed) {
    const out = [];
    if (!xml || typeof xml !== 'string') return out;
    const isAtom = /<feed\b[^>]*xmlns=["']http:\/\/www\.w3\.org\/2005\/Atom/i.test(xml) && !/<item\b/i.test(xml);
    const blocks = xml.match(isAtom ? /<entry\b[\s\S]*?<\/entry>/gi : /<item\b[\s\S]*?<\/item>/gi) || [];
    for (const b of blocks.slice(0, feed.max || 15)) {
      const t = cleanTitle(tag(b, 'title'), feed.aggregator);
      if (!t.title) continue;
      let link = isAtom ? (attr(b, 'link', 'href')) : decode(stripTags(tag(b, 'link')));
      if (!link) link = decode(tag(b, 'guid'));
      if (!/^https?:\/\//i.test(link)) continue;
      const rawSummary = tag(b, 'description') || tag(b, 'summary') || tag(b, 'content:encoded') || tag(b, 'content');
      let summary = stripTags(rawSummary);
      if (feed.aggregator) summary = '';
      if (summary.length > 260) summary = summary.slice(0, 257).replace(/\s+\S*$/, '') + '…';
      const dateStr = tag(b, 'pubDate') || tag(b, 'published') || tag(b, 'updated') || tag(b, 'dc:date');
      const d = new Date(dateStr);
      const date = isNaN(d) ? null : d.toISOString();
      let image = findImage(b);
      if (image && image.startsWith('//')) image = 'https:' + image;
      if (image && !/^https?:\/\//i.test(image)) image = '';
      if (image) image = image.replace(/^http:\/\//i, 'https://');
      const categories = classify(t.title, summary, feed.cat);
      out.push({
        id: hash(link),
        title: t.title,
        summary,
        link,
        image,
        date,
        source: t.source || feed.name,
        feed: feed.name,
        categories,
      });
    }
    return out;
  }

  function hash(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(36);
  }

  // Junta itens, remove duplicados (link ou título parecido) e ordena por data.
  function merge(lists) {
    const byKey = new Map();
    for (const it of lists.flat()) {
      if (!it || !it.title) continue;
      const k = norm(it.title).replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 70);
      const prev = byKey.get(k) || [...byKey.values()].find((p) => p.link === it.link);
      if (prev) {
        if (!prev.image && it.image) prev.image = it.image;
        if (!prev.summary && it.summary) prev.summary = it.summary;
        prev.categories = [...new Set([...prev.categories.filter((c) => c !== 'novidades'), ...it.categories])];
        if (!prev.categories.includes('novidades')) prev.categories.push('novidades');
        continue;
      }
      byKey.set(k, { ...it, categories: [...it.categories] });
    }
    return [...byKey.values()].sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  }

  const api = { CATEGORIES, FEEDS, RULES, classify, parseFeed, merge, stripTags, decode, norm, hash };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.FofocasCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
