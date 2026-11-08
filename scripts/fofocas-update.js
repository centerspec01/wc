#!/usr/bin/env node
/*
 * Busca as fontes RSS de fofoca, completa imagens que faltam (og:image)
 * e grava data/fofocas.json. Rodado pelo GitHub Actions a cada 30 min.
 *
 * Uso: node scripts/fofocas-update.js [--out data/fofocas.json] [--fixtures dir]
 */
'use strict';
const fs = require('fs');
const path = require('path');
const Core = require('../fofocas-core.js');

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const OUT = path.resolve(__dirname, '..', opt('--out', 'data/fofocas.json'));
const FIXTURES = opt('--fixtures', null); // pasta com <hash da url>.xml para testes offline
const UA = 'Mozilla/5.0 (compatible; BrasilGossipsBot/1.0; +https://github.com/centerspec01/wc)';

async function get(url, ms = 12000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA, Accept: '*/*' }, signal: ctl.signal, redirect: 'follow' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.text();
  } finally { clearTimeout(t); }
}

async function loadFeed(feed) {
  try {
    const xml = FIXTURES
      ? fs.readFileSync(path.join(FIXTURES, Core.hash(feed.url) + '.xml'), 'utf8')
      : await get(feed.url);
    const items = Core.parseFeed(xml, feed);
    console.log(`✔ ${feed.name.padEnd(20)} ${String(items.length).padStart(3)} itens  ${feed.cat}`);
    return { ok: true, items };
  } catch (e) {
    console.log(`✘ ${feed.name.padEnd(20)} ${e.message}`);
    return { ok: false, items: [] };
  }
}

async function ogImage(url) {
  const html = await get(url, 8000);
  const head = html.slice(0, 200000);
  const m = head.match(/<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)(?::src)?["'][^>]*content=["']([^"']+)["']/i)
         || head.match(/<meta[^>]+content=["']([^"']+)["'][^>]*(?:property|name)=["'](?:og:image|twitter:image)["']/i);
  return m ? Core.decode(m[1]).replace(/^http:\/\//i, 'https://') : '';
}

async function pool(list, n, fn) {
  let i = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < list.length) { const it = list[i++]; await fn(it); }
  }));
}

(async () => {
  const results = await Promise.all(Core.FEEDS.map(loadFeed));
  const okCount = results.filter((r) => r.ok).length;
  let items = Core.merge(results.map((r) => r.items));

  // Mantém só as últimas 72h (ou as 40 mais recentes se a janela ficar vazia)
  const cutoff = Date.now() - 72 * 3600e3;
  const recent = items.filter((it) => it.date && Date.parse(it.date) > cutoff);
  items = (recent.length >= 40 ? recent : items).slice(0, 300);

  // Completa imagens faltantes direto da página da matéria (não Google Notícias)
  if (!FIXTURES) {
    const missing = items.filter((it) => !it.image && !/news\.google\.com/.test(it.link)).slice(0, 80);
    let found = 0;
    await pool(missing, 8, async (it) => {
      try { const img = await ogImage(it.link); if (img) { it.image = img; found++; } } catch (_) {}
    });
    console.log(`og:image: ${found}/${missing.length} imagens completadas`);
  }

  if (!items.length) {
    console.error('Nenhum item obtido — mantendo arquivo anterior.');
    process.exit(okCount ? 0 : 1);
  }

  const data = {
    updated: new Date().toISOString(),
    sources: okCount,
    count: items.length,
    items,
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(data, null, 1));
  const byCat = {};
  for (const it of items) for (const c of it.categories) byCat[c] = (byCat[c] || 0) + 1;
  console.log(`\n${items.length} fofocas de ${okCount}/${Core.FEEDS.length} fontes →`, path.relative(process.cwd(), OUT));
  console.log(byCat);
})();
