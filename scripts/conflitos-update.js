#!/usr/bin/env node
/*
 * World Conflicts — atualizador de dados externos.
 * 1) Últimas notícias de cada conflito (Google Notícias RSS, fallback GDELT)
 * 2) Chefes de Estado/governo atuais de todos os países (Wikidata)
 * Grava data/conflitos-live.json. Rodado pelo GitHub Actions a cada 6 h.
 *
 * Uso: node scripts/conflitos-update.js [--out data/conflitos-live.json] [--fixtures dir]
 *   --fixtures: pasta com <id>.xml (RSS) e wikidata.json para testes offline
 */
'use strict';
const fs = require('fs');
const path = require('path');
const Core = require('../conflitos-core.js');

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const ROOT = path.resolve(__dirname, '..');
const OUT = path.resolve(ROOT, opt('--out', 'data/conflitos-live.json'));
const FIXTURES = opt('--fixtures', null);
const UA = 'WorldConflictsBot/1.0 (+https://github.com/centerspec01/wc)';

async function get(url, ms = 20000, accept = '*/*') {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA, Accept: accept }, signal: ctl.signal, redirect: 'follow' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.text();
  } finally { clearTimeout(t); }
}

async function newsFor(c) {
  try {
    const xml = FIXTURES ? fs.readFileSync(path.join(FIXTURES, c.id + '.xml'), 'utf8') : await get(Core.gnewsUrl(c.busca || c.nome));
    const items = Core.parseRSS(xml, 8);
    if (items.length) return { ok: true, items, via: 'Google Notícias' };
  } catch (e) { console.log(`  ! Google Notícias ${c.id}: ${e.message}`); }
  if (FIXTURES) return { ok: false, items: [] };
  try {
    const items = Core.parseGdelt(JSON.parse(await get(Core.gdeltUrl(c.buscaEn || c.busca || c.nome, 8)))).slice(0, 8);
    return { ok: items.length > 0, items, via: 'GDELT' };
  } catch (e) { console.log(`  ! GDELT ${c.id}: ${e.message}`); }
  return { ok: false, items: [] };
}

async function leaders() {
  const txt = FIXTURES ? fs.readFileSync(path.join(FIXTURES, 'wikidata.json'), 'utf8')
    : await get(Core.wikidataUrl(), 60000, 'application/sparql-results+json');
  return Core.parseWikidata(JSON.parse(txt));
}

(async () => {
  const base = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/conflitos.json'), 'utf8'));
  let prev = {};
  try { prev = JSON.parse(fs.readFileSync(OUT, 'utf8')); } catch (_) {}

  const noticias = {};
  let ok = 0;
  for (const c of base.conflitos) {          // sequencial para não sobrecarregar a fonte
    const r = await newsFor(c);
    if (r.ok) { noticias[c.id] = r.items; ok++; }
    else if (prev.noticias && prev.noticias[c.id]) noticias[c.id] = prev.noticias[c.id]; // mantém as anteriores
    console.log(`${r.ok ? '✔' : '✘'} ${c.id.padEnd(20)} ${String(r.items.length).padStart(2)} notícias ${r.via ? '(' + r.via + ')' : ''}`);
    await new Promise((res) => setTimeout(res, FIXTURES ? 0 : 700));
  }

  let lideres = prev.lideres || {};
  let lideresAtualizado = prev.lideresAtualizado || null;
  try {
    const l = await leaders();
    if (Object.keys(l).length > 100) { lideres = l; lideresAtualizado = new Date().toISOString(); }
    console.log(`✔ Wikidata: líderes de ${Object.keys(l).length} países`);
  } catch (e) { console.log(`✘ Wikidata: ${e.message} — mantendo dados anteriores`); }

  if (!ok && !Object.keys(lideres).length) {
    console.error('Nenhuma fonte respondeu — mantendo arquivo anterior.');
    process.exit(1);
  }

  const data = {
    updated: new Date().toISOString(),
    fontes: { noticias: 'Google Notícias / GDELT', lideres: 'Wikidata (P35 chefe de Estado, P6 chefe de governo)' },
    lideresAtualizado,
    noticias,
    lideres,
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(data, null, 1));
  console.log(`\nNotícias de ${ok}/${base.conflitos.length} conflitos →`, path.relative(process.cwd(), OUT));
})();
