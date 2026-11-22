"""Render a self-contained, local-only evidence review page."""

import json
import math
import re
from urllib.parse import unquote, urlsplit


_CATEGORIES = {'bot', 'link', 'payment', 'approval'}
_GRADES = {'E0', 'E1', 'E2', 'E3'}
_MEDIA_EXTENSIONS = {
    'image': {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.tif', '.tiff', '.bmp', '.gif'},
    'video': {'.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv', '.mpeg', '.mpg'},
}


def _local_uri(value, kind):
    if not isinstance(value, str) or not value.startswith('file:///'):
        return None
    if re.search(r'[\x00-\x20\x7f]', value):
        return None
    try:
        result = urlsplit(value)
        path = unquote(result.path, errors='strict')
    except (ValueError, UnicodeError):
        return None
    if result.netloc or result.query or result.fragment or path.startswith('//'):
        return None
    if '\\' in path or re.search(r'[\x00-\x1f\x7f]', path):
        return None
    extension = '.' + path.rsplit('.', 1)[-1].lower()
    return value if extension in _MEDIA_EXTENSIONS.get(kind, set()) else None


def _text(value, default=''):
    return value if isinstance(value, str) else default


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    parts = [_finite(n) for n in value]
    if any(n is None for n in parts):
        return None
    x, y, w, h = parts
    x, y = max(0, min(1, x)), max(0, min(1, y))
    w, h = min(1 - x, w), min(1 - y, h)
    return [x, y, w, h] if w > 0 and h > 0 else None


def _data(report):
    sources = []
    for source in report.get('sources', []):
        kind = _text(source.get('kind'))
        sources.append({
            'id': _text(source.get('id')),
            'label': _text(source.get('label'), '未命名材料'),
            'kind': kind,
            'reference': _text(source.get('reference')),
            'file_url': _local_uri(source.get('file_url'), kind),
        })

    findings = []
    for finding in report.get('findings', []):
        timestamp = _finite(finding.get('timestamp'))
        category = _text(finding.get('category'))
        grade = _text(finding.get('grade'))
        findings.append({
            'source_id': _text(finding.get('source_id')),
            'category': category if category in _CATEGORIES else '',
            'title': _text(finding.get('title'), '未命名线索'),
            'summary': _text(finding.get('summary')),
            'status': 'observed' if finding.get('status') == 'observed' else 'pending',
            'grade': grade if grade in _GRADES else 'E0',
            'timestamp': timestamp if timestamp is not None and timestamp >= 0 else None,
            'box': _box(finding.get('box')),
            'method': _text(finding.get('method')),
        })

    coverage = report.get('coverage', {})
    counters = {}
    for key in ('images', 'videos', 'frames', 'reviewed', 'ocr_errors'):
        count = coverage.get(key)
        counters[key] = count if type(count) is int and count >= 0 else 0
    counters['warnings'] = [
        warning for warning in coverage.get('warnings', []) if isinstance(warning, str)
    ]
    return {
        'title': _text(report.get('title'), 'Telegram 防骗证据复核'),
        'mode': _text(report.get('mode')),
        'generated_at': _text(report.get('generated_at')),
        'sources': sources,
        'findings': findings,
        'coverage': counters,
    }


def render(report: dict) -> str:
    """Return an offline HTML document referencing only local raster or video media."""
    payload = json.dumps(_data(report), ensure_ascii=False, allow_nan=False)
    payload = (payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
               .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))
    return _PAGE.replace('__EVIDENCE_JSON__', payload, 1)


_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src file:; media-src file:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>Telegram 防骗证据复核</title>
<style>
:root {
  color-scheme: light;
  --page: #f2f4ef; --paper: #fffefb; --ink: #182925; --subtle: #4d6059;
  --line: #d6e0d8; --green: #145747; --green-deep: #10372d; --green-soft: #e2f1e8;
  --warm: #f6eddd; --ochre: #79501d; --focus: #126a59;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
  background: var(--page); color: var(--ink); line-height: 1.55;
}
* { box-sizing: border-box; }
body { margin: 0; }
button, select { font: inherit; }
button { cursor: pointer; }
[hidden] { display: none !important; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px; }
a { color: var(--green); text-underline-offset: .2rem; }
.skip { position: absolute; inset-inline-start: 1rem; top: -5rem; z-index: 5; background: white; padding: .6rem 1rem; }
.skip:focus { top: 1rem; }
.masthead { background: var(--green-deep); color: #f2f9f3; border-bottom: 3px solid #3f836d; }
.masthead-inner, .shell { width: min(100% - 64px, 1380px); margin-inline: auto; }
.masthead-inner { display: flex; gap: 1rem; justify-content: space-between; align-items: center; min-height: 62px; }
.product { font-size: .89rem; font-weight: 710; letter-spacing: .045em; }
.local { font-size: .78rem; color: #dbebe0; white-space: nowrap; }
.hero { padding: 39px 0 25px; }
.hero h1 { font-size: clamp(1.9rem, 4vw, 3.2rem); letter-spacing: -.028em; line-height: 1.2; margin: 0; font-weight: 760; overflow-wrap: anywhere; }
.hero .meta { color: var(--subtle); font-size: .87rem; margin: .7rem 0 0; overflow-wrap: anywhere; }
.metrics { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); background: var(--paper); border: 1px solid var(--line); border-radius: 13px; margin: 0; overflow: hidden; }
.metric { padding: 15px 19px 14px; }
.metric + .metric { border-left: 1px solid var(--line); }
.metric dt { color: var(--subtle); font-size: .79rem; }
.metric dd { margin: .1rem 0 0; line-height: 1.22; font-size: 1.85rem; font-variant-numeric: tabular-nums; font-weight: 730; }
.metric.emphasis dd { color: var(--ochre); }
.coverage { color: var(--subtle); font-size: .85rem; margin: 12px 0 21px; }
.coverage summary { cursor: pointer; width: fit-content; }
.coverage p { margin: .55rem 0; }
.coverage ul { margin-top: .4rem; overflow-wrap: anywhere; }
.workspace { display: grid; grid-template-columns: minmax(300px, 5fr) minmax(0, 8fr); gap: 18px; align-items: start; padding-bottom: 35px; }
.panel { background: var(--paper); border: 1px solid var(--line); min-width: 0; border-radius: 13px; box-shadow: 0 2px 8px #0f2e1f06; }
.panel-head { padding: 18px 19px 13px; border-bottom: 1px solid var(--line); }
.panel h2 { font-size: 1.09rem; font-weight: 735; margin: 0; }
.filterset { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 9px 12px; margin: 13px 0 0; }
.filterset label { min-width: 0; display: block; font-size: .75rem; color: var(--subtle); }
.filterset label:last-child { grid-column: span 2; }
.filterset select { display: block; width: 100%; color: var(--ink); background: white; border: 1px solid #cbd8cf; padding: .41rem .34rem; margin-top: .18rem; border-radius: 7px; font-size: .84rem; }
.list-count { display: block; font-size: .78rem; color: var(--subtle); margin-top: .7rem; }
.findings-list { padding: 8px; list-style: none; margin: 0; max-height: min(66vh, 710px); overflow: auto; scrollbar-color: #a2baa9 transparent; }
.findings-list li + li { margin-top: 3px; }
.finding-button { width: 100%; text-align: left; background: transparent; color: var(--ink); border: 1px solid transparent; border-left: 3px solid transparent; border-radius: 8px; padding: 9px 9px 8px; }
.finding-button:focus-visible { outline-offset: -3px; }
.finding-button:hover { background: #f4f7f2; }
.finding-button[aria-pressed="true"] { background: var(--green-soft); border-color: #c7ddd1; border-left-color: var(--green); }
.finding-title { display: block; font-size: .9rem; font-weight: 715; overflow-wrap: anywhere; }
.finding-meta, .tags { display: flex; gap: .35rem .5rem; flex-wrap: wrap; align-items: center; margin: .32rem 0; }
.tag { display: inline-block; border-radius: 4px; padding: 1px 5px; color: #294a3b; background: #eef2ed; font-size: .7rem; font-weight: 650; }
.tag[data-state="pending"] { background: var(--warm); color: var(--ochre); }
.tag[data-category="bot"] { background: #e8edf4; color: #2f4d72; }
.tag[data-category="link"] { background: #f4ece1; color: #735022; }
.tag[data-category="payment"] { background: #e5f0e6; color: #315d39; }
.tag[data-category="approval"] { background: #f0e9f1; color: #68436b; }
.location { display: block; color: var(--subtle); font-size: .76rem; overflow-wrap: anywhere; }
.evidence-panel { position: sticky; top: 12px; }
.evidence-copy { padding: 14px 19px 13px; }
.evidence-copy h3 { margin: 0 0 .36rem; font-size: 1.16rem; font-weight: 730; overflow-wrap: anywhere; }
.evidence-copy .description { margin: .5rem 0; font-size: .91rem; overflow-wrap: anywhere; }
.key-values { display: flex; gap: 7px 19px; flex-wrap: wrap; margin: .65rem 0 0; }
.key-values div { min-width: 0; }
.key-values dt { color: var(--subtle); font-size: .72rem; }
.key-values dd { margin: .1rem 0 0; font-size: .83rem; overflow-wrap: anywhere; }
.time { font-variant-numeric: tabular-nums; }
.preview-stage { min-height: 123px; display: flex; justify-content: center; align-items: center; background: #e8eee7; border-block: 1px solid var(--line); padding: 13px; }
.media-wrap { position: relative; max-width: 100%; flex: 0 1 auto; min-width: 0; line-height: 0; }
.evidence-media { display: block; width: auto; height: auto; max-width: 100%; max-height: min(62vh, 635px); border-radius: 5px; background: #e7ede6; }
.region { position: absolute; border: 2px solid #ed9a34; background: #ffc5783d; box-shadow: 0 0 0 1px #57330d; pointer-events: none; border-radius: 2px; }
.preview-tools { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem .65rem; padding: 10px 19px 13px; }
.preview-tools button { border: 1px solid #b8cfc1; color: var(--green-deep); background: #f0f7f0; border-radius: 6px; padding: .37rem .62rem; font-size: .82rem; }
.preview-tools a { font-size: .83rem; overflow-wrap: anywhere; }
.preview-tools p { color: var(--subtle); font-size: .76rem; width: 100%; margin: .05rem 0; overflow-wrap: anywhere; }
.empty { color: var(--subtle); padding: 23px 15px; margin: 0; font-size: .89rem; }
.empty-view { padding: 1.25rem 19px; color: var(--subtle); margin: 0; font-size: .89rem; }
.footnote { margin: 0 0 25px; font-size: .77rem; color: var(--subtle); }
@media (max-width: 870px) {
  .masthead-inner, .shell { width: calc(100% - 30px); }
  .workspace { grid-template-columns: minmax(0,1fr); }
  .findings-list { max-height: 320px; }
  .evidence-panel { position: static; scroll-margin-top: 10px; }
}
@media (max-width: 470px) {
  .metrics { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .metric:nth-child(3) { border-left: 0; }
  .metric:nth-child(n+3) { border-top: 1px solid var(--line); }
  .hero { padding: 24px 0 19px; }
}
</style>
</head>
<body>
<a class="skip" href="#findings-heading">跳到线索列表</a>
<header class="masthead"><div class="masthead-inner">
  <span class="product">Telegram 防骗复核</span><span class="local">本地离线报告</span>
</div></header>
<main class="shell">
  <section class="hero" aria-labelledby="report-title"><h1 id="report-title">Telegram 防骗证据复核</h1><p class="meta" id="report-meta" hidden></p></section>
  <dl class="metrics" aria-label="报告概况">
    <div class="metric"><dt>线索</dt><dd id="total-count">0</dd></div>
    <div class="metric emphasis"><dt>待核</dt><dd id="pending-count">0</dd></div>
    <div class="metric"><dt>证据来源</dt><dd id="source-count">0</dd></div>
    <div class="metric"><dt>扫描视频帧</dt><dd id="frame-count">0</dd></div>
  </dl>
  <details class="coverage"><summary>查看扫描覆盖范围</summary><p id="coverage-summary"></p><ul id="coverage-warnings" hidden></ul></details>
  <div class="workspace">
    <section class="panel" aria-labelledby="findings-heading">
      <div class="panel-head">
        <h2 id="findings-heading">线索列表</h2>
        <div class="filterset" aria-label="筛选线索">
          <label>类别<select id="category-filter"><option value="">全部类别</option><option value="bot">机器人</option><option value="link">外链</option><option value="payment">付款</option><option value="approval">授权</option></select></label>
          <label>状态<select id="status-filter"><option value="">全部状态</option><option value="observed">可见线索</option><option value="pending">待核</option></select></label>
          <label>来源<select id="source-filter"><option value="">全部来源</option></select></label>
        </div>
        <output class="list-count" id="list-count" aria-live="polite"></output>
      </div>
      <ul class="findings-list" id="findings"></ul>
      <p class="empty" id="empty-list" hidden>当前筛选没有匹配线索。</p>
    </section>
    <section class="panel evidence-panel" aria-labelledby="evidence-heading" id="evidence-panel">
      <div class="panel-head"><h2 id="evidence-heading">证据预览</h2></div>
      <p class="empty-view" id="empty-evidence">点选一条线索查看对应位置。</p>
      <div id="evidence" hidden>
        <div class="evidence-copy">
          <h3 id="evidence-title"></h3><div class="tags" id="evidence-tags"></div>
          <p class="description" id="evidence-description"></p>
          <dl class="key-values">
            <div><dt>材料</dt><dd id="evidence-source"></dd></div>
            <div><dt>出处</dt><dd id="evidence-reference"></dd></div>
            <div id="time-detail" hidden><dt>视频时间码</dt><dd class="time" id="evidence-time"></dd></div>
          </dl>
        </div>
        <div class="preview-stage" id="stage"><div class="media-wrap" id="media-wrap"></div></div>
        <div class="preview-tools">
          <button type="button" id="seek" hidden>回到时间码</button>
          <a id="open-source" hidden>打开本地资料</a>
          <p id="media-note" aria-live="polite"></p>
        </div>
      </div>
    </section>
  </div>
  <p class="footnote">E0 表示缺少足以核实的材料，E1 表示可见文字或自述，E2 表示能定位到原始画面，E3 表示有独立凭证。</p>
  <noscript>此报告需在本机启用 JavaScript 才能筛选线索并打开证据预览。</noscript>
</main>
<script type="application/json" id="report-data">__EVIDENCE_JSON__</script>
<script>
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const report = JSON.parse($('report-data').textContent);
  const categoryLabels = new Map([['bot','机器人'],['link','外链'],['payment','付款'],['approval','授权']]);
  const statusLabels = new Map([['pending','待核'],['observed','可见线索']]);
  const methodLabels = new Map([['ocr','OCR 提取'],['review','人工复核']]);
  const sources = new Map(report.sources.map(source => [source.id, source]));
  const filters = ['category-filter', 'status-filter', 'source-filter'].map($);
  const rows = report.findings;
  const fmt = new Intl.NumberFormat('zh-CN');
  let selected = null;
  let renderedSource = null;
  let media = null;
  let marker = null;
  let mediaFailed = false;

  const strCount = n => fmt.format(n);
  const local = uri => typeof uri === 'string' && uri.startsWith('file:///');
  const hasTime = value => Number.isFinite(value) && value >= 0;

  function timecode(seconds) {
    const total = Math.round(seconds * 1000);
    const pad = (value, length = 2) => String(value).padStart(length, '0');
    const h = Math.floor(total / 3600000);
    const m = Math.floor(total / 60000) % 60;
    const s = Math.floor(total / 1000) % 60;
    return (h ? pad(h) + ':' : '') + pad(m) + ':' + pad(s) + '.' + pad(total % 1000, 3);
  }

  function node(type, value, cls) {
    const el = document.createElement(type);
    if (value) el.textContent = value;
    if (cls) el.className = cls;
    return el;
  }

  function tags(finding) {
    const frag = document.createDocumentFragment();
    const category = node('span', categoryLabels.get(finding.category) || '其他', 'tag');
    category.dataset.category = finding.category;
    const state = node('span', statusLabels.get(finding.status), 'tag');
    state.dataset.state = finding.status;
    frag.append(category, state, node('span', finding.grade, 'tag'));
    return frag;
  }

  function setOverview() {
    $('report-title').textContent = report.title;
    document.title = report.title;
    const modes = {case: '本地案例', demo: '合成教学样例', synthetic: '合成教学样例'};
    const meta = [modes[report.mode] || report.mode, report.generated_at].filter(Boolean);
    $('report-meta').textContent = meta.join(' · ');
    $('report-meta').hidden = !meta.length;
    $('total-count').textContent = strCount(rows.length);
    $('pending-count').textContent = strCount(rows.filter(row => row.status === 'pending').length);
    $('source-count').textContent = strCount(sources.size);
    $('frame-count').textContent = strCount(report.coverage.frames);
    const keys = [['images', '张图像'], ['videos', '段视频'], ['frames', '帧视频抽样'],
      ['reviewed', '条人工复核'], ['ocr_errors', '项识别异常']];
    $('coverage-summary').textContent = keys.map(([key, label]) => strCount(report.coverage[key]) + ' ' + label).join(' · ');
    const warnings = $('coverage-warnings');
    warnings.replaceChildren(...report.coverage.warnings.map(text => node('li', text)));
    warnings.hidden = !report.coverage.warnings.length;
    for (const source of sources.values()) {
      if (source.id) {
        const option = node('option', source.label);
        option.value = source.id;
        filters[2].append(option);
      }
    }
  }

  function drawMarker() {
    if (!marker) return;
    const box = selected?.box;
    const show = box && !mediaFailed && (renderedSource?.kind === 'image' ||
      (hasTime(selected.timestamp) && media.readyState >= 2 &&
        Math.abs(media.currentTime - selected.timestamp) < .18));
    marker.hidden = !show;
    if (show) {
      ['left','top','width','height'].forEach((key, index) => {
        marker.style[key] = (box[index] * 100) + '%';
      });
    }
  }

  function jumpToTime() {
    if (!media || media.tagName !== 'VIDEO' || !selected || !hasTime(selected.timestamp) ||
        !media.readyState || mediaFailed) return;
    try {
      media.pause();
      media.currentTime = Math.min(selected.timestamp,
        Number.isFinite(media.duration) ? media.duration : selected.timestamp);
    } catch {
      $('media-note').textContent = '浏览器未能跳到指定位置，可打开本地资料并按时间码查看。';
    }
  }

  function mountMedia(source) {
    const wrap = $('media-wrap');
    wrap.replaceChildren();
    media = marker = null;
    mediaFailed = false;
    renderedSource = source;
    if (!source || !local(source.file_url)) return;
    const isVideo = source.kind === 'video';
    if (!isVideo && source.kind !== 'image') return;
    const player = node(isVideo ? 'video' : 'img', '', 'evidence-media');
    media = player;
    marker = node('div', '', 'region');
    marker.setAttribute('aria-hidden', 'true');
    marker.hidden = true;
    if (isVideo) {
      player.controls = true;
      player.playsInline = true;
      player.preload = 'metadata';
      player.disablePictureInPicture = true;
      player.disableRemotePlayback = true;
      player.setAttribute('controlslist', 'noremoteplayback');
      player.setAttribute('aria-label', source.label);
      player.addEventListener('loadedmetadata', () => { if (media === player) jumpToTime(); });
      for (const event of ['loadeddata', 'seeked', 'timeupdate', 'play']) {
        player.addEventListener(event, () => { if (media === player) drawMarker(); });
      }
    } else {
      player.alt = source.label;
      player.addEventListener('load', () => { if (media === player) drawMarker(); });
    }
    player.addEventListener('error', () => {
      if (media !== player) return;
      mediaFailed = true;
      $('media-note').textContent = '浏览器无法读取此本地媒体。请核对文件位置，或按出处和时间码打开原件。';
      drawMarker();
    });
    wrap.append(player, marker);
    player.src = source.file_url;
  }

  function showEvidence(finding, userPicked = false) {
    selected = finding;
    $('evidence').hidden = !finding;
    $('empty-evidence').hidden = !!finding;
    if (!finding) {
      if (media?.tagName === 'VIDEO') media.pause();
      return;
    }
    const source = sources.get(finding.source_id) || null;
    const seekable = source?.kind === 'video' && hasTime(finding.timestamp);
    $('evidence-title').textContent = finding.title;
    $('evidence-tags').replaceChildren(tags(finding));
    const method = methodLabels.get(finding.method);
    if (method) $('evidence-tags').append(node('span', method, 'tag'));
    $('evidence-description').textContent = finding.summary;
    $('evidence-source').textContent = source?.label || '来源未提供';
    $('evidence-reference').textContent = source?.reference || '未记录';
    $('time-detail').hidden = !seekable;
    const time = seekable ? timecode(finding.timestamp) : '';
    $('evidence-time').textContent = time;
    $('seek').textContent = seekable ? '回到 ' + time : '回到时间码';
    $('seek').hidden = !seekable || !local(source?.file_url);

    const original = $('open-source');
    original.hidden = !local(source?.file_url);
    if (!original.hidden) {
      original.href = source.file_url + (seekable ? '#t=' + finding.timestamp : '');
      original.target = '_blank';
      original.rel = 'noopener noreferrer';
    } else {
      original.removeAttribute('href');
    }

    if (source !== renderedSource || (!media && local(source?.file_url))) mountMedia(source);
    $('stage').hidden = !media;
    $('media-note').textContent = mediaFailed
      ? '浏览器无法读取此本地媒体。请核对文件位置，或按出处和时间码打开原件。'
      : !media ? '此项没有可预览的本地媒体路径。'
      : finding.box ? '橙框标出线索在原画面的位置。' : '这条线索定位在整张图片或指定视频时间。';
    jumpToTime();
    drawMarker();
    for (const button of $('findings').querySelectorAll('button')) {
      button.setAttribute('aria-pressed', String(rows[Number(button.dataset.index)] === finding));
    }
    if (userPicked && matchMedia('(max-width: 870px)').matches) {
      $('evidence-panel').scrollIntoView({block: 'start'});
    }
  }

  function drawList() {
    const [category, status, sourceId] = filters.map(el => el.value);
    const indexes = [];
    const fragment = document.createDocumentFragment();
    rows.forEach((finding, index) => {
      if ((category && finding.category !== category) || (status && finding.status !== status) ||
          (sourceId && finding.source_id !== sourceId)) return;
      indexes.push(index);
      const li = node('li');
      const button = node('button', '', 'finding-button');
      button.type = 'button';
      button.dataset.index = String(index);
      button.setAttribute('aria-controls', 'evidence-panel');
      button.setAttribute('aria-pressed', String(finding === selected));
      const tagsRow = node('span', '', 'finding-meta');
      tagsRow.append(tags(finding));
      const source = sources.get(finding.source_id);
      const description = [source?.label || '来源未提供'];
      if (hasTime(finding.timestamp)) description.push(timecode(finding.timestamp));
      button.append(node('span', finding.title, 'finding-title'), tagsRow,
        node('span', description.join(' · '), 'location'));
      button.addEventListener('click', () => showEvidence(finding, true));
      li.append(button);
      fragment.append(li);
    });
    $('findings').replaceChildren(fragment);
    $('list-count').textContent = '显示 ' + strCount(indexes.length) + ' / ' + strCount(rows.length) + ' 条';
    $('empty-list').hidden = indexes.length > 0;
    if (!indexes.some(index => rows[index] === selected)) showEvidence(rows[indexes[0]] || null);
  }

  setOverview();
  for (const select of filters) select.addEventListener('change', drawList);
  $('seek').addEventListener('click', jumpToTime);
  drawList();
})();
</script>
</body>
</html>
"""

