from urllib.parse import quote

HEAD = '<meta name="color-scheme" content="dark"><script>document.documentElement.classList.add("dark");</script>'


def _mask(paths):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>')
    return 'url("data:image/svg+xml,' + quote(svg) + '")'


MASK = {
    "user": _mask('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    "server": _mask('<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/>'
                    '<path d="M7 7.5h.01M7 16.5h.01"/>'),
    "sliders": _mask('<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/>'
                     '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>'),
    "folder": _mask('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
    "team": _mask('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>'),
    "power": _mask('<path d="M12 3v9"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>'),
}

CSS = """
:root, .dark {
  --s950: #060913; --s900: #0a0f1d; --s850: #0e1626; --s800: #152238; --s750: #1b2a45; --s700: #1e2b42;
  --m28-blue: #3b82f6; --m28-blue-d: #2563eb; --m28-amber: #fbbf24;
  --body-background-fill: #060913; --background-fill-primary: #0a0f1d; --background-fill-secondary: #0e1626;
  --block-background-fill: #0a0f1d; --block-border-color: #1e2b42; --block-label-background-fill: #0e1626;
  --block-label-text-color: #94a3b8; --block-title-text-color: #cbd5e1; --block-info-text-color: #94a3b8;
  --block-title-background-fill: transparent; --block-label-border-color: #1e2b42; --block-title-border-color: transparent;
  --border-color-primary: #1e2b42; --border-color-accent: #3b82f6; --panel-background-fill: #0a0f1d;
  --body-text-color: #e2e8f0; --body-text-color-subdued: #94a3b8;
  --input-background-fill: #0e1626; --input-background-fill-focus: #0e1626; --input-border-color: #1e2b42; --input-border-color-focus: #3b82f6;
  --button-secondary-background-fill: #0e1626; --button-secondary-background-fill-hover: #152238; --button-secondary-border-color: #1e2b42;
  --button-secondary-text-color: #cbd5e1; --button-secondary-text-color-hover: #ffffff;
  --color-accent: #3b82f6; --color-accent-soft: rgba(59, 130, 246, .18); --link-text-color: #60a5fa;
  --table-even-background-fill: #0a0f1d; --table-odd-background-fill: #0e1626;
  --checkbox-background-color: #0e1626; --checkbox-border-color: #1e2b42;
  color-scheme: dark;
}
html, body, gradio-app, .gradio-container { background: #060913 !important; color: #e2e8f0; }
.gradio-container { max-width: 1680px !important; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0a0f1d; }
::-webkit-scrollbar-thumb { background: #1e2b42; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #3b82f6; }
kbd { background: rgba(255, 255, 255, .08) !important; border: 1px solid rgba(255, 255, 255, .15) !important; color: #e2e8f0 !important; border-radius: 4px !important; }

.column:has(> #m28-appbar) { gap: 8px !important; }
#m28-appbar { position: sticky; top: 0; z-index: 50; align-items: center; justify-content: space-between; gap: 8px 16px; flex-wrap: wrap;
  padding: 6px 12px !important; background: rgba(10, 15, 29, .95); backdrop-filter: blur(10px); border: 1px solid #1e2b42; border-radius: 14px; }
#m28-brand-wrap, #m28-batch { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; padding: 0 !important; }
.m28-brand { display: flex; align-items: center; gap: 10px; }
.m28-logo { width: 32px; height: 32px; border-radius: 9px; display: inline-flex; align-items: center; justify-content: center; color: #fff;
  background: linear-gradient(135deg, #3b82f6, #4f46e5); box-shadow: 0 4px 14px rgba(59, 130, 246, .25); }
.m28-brand-name { font-size: 15px; font-weight: 700; color: #f1f5f9; letter-spacing: -.01em; white-space: nowrap; }
.m28-pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 12px; cursor: pointer; font-size: 13px;
  color: #94a3b8; background: #0e1626; border: 1px solid #1e2b42; transition: background .15s, border-color .15s; }
.m28-pill:hover { background: #152238; border-color: rgba(59, 130, 246, .5); color: #e2e8f0; }
.m28-pill > .ic:first-child { color: #fbbf24; }
.m28-pill-run { font-family: var(--font-mono); color: #fcd34d; }
.m28-pill-muted { border-left: 1px solid #1e2b42; padding-left: 8px; white-space: nowrap; }
#m28-batch { position: relative; overflow: visible !important; }
#m28-right { flex: 0 1 auto !important; width: auto !important; gap: 8px; flex-wrap: wrap; align-items: center; justify-content: flex-end; }   /* cụm đợt + cụm nút: luôn đứng sát nhau bên phải */
#m28-right > * { flex: 0 0 auto !important; min-width: 0 !important; width: auto !important; }
.m28-pillgrp { position: relative; display: inline-flex; align-items: stretch; }
.m28-pillgrp .m28-pill { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.m28-pill-caret { display: inline-flex; align-items: center; justify-content: center; width: 32px; cursor: pointer; color: #94a3b8;
  background: #0e1626; border: 1px solid #1e2b42; border-left: 0; border-radius: 0 12px 12px 0; transition: background .15s, color .15s; }
.m28-pill-caret:hover { background: #152238; color: #e2e8f0; }
.m28-pill-caret .ic { transition: transform .15s; }
#m28-batch.m28-menu-open .m28-pill-caret { background: #152238; color: #fff; }
#m28-batch.m28-menu-open .m28-pill-caret .ic { transform: rotate(180deg); }
.m28-pill-menu { display: none; position: absolute; top: calc(100% + 6px); left: 0; z-index: 200; min-width: 300px; max-height: min(420px, 70vh); overflow-y: auto;
  padding: 6px; border-radius: 12px; background: #0a0f1d; border: 1px solid #1e2b42; box-shadow: 0 16px 40px rgba(0, 0, 0, .55); }
#m28-batch.m28-menu-open .m28-pill-menu { display: flex; flex-direction: column; gap: 2px; }
.m28-mi-head { padding: 4px 8px 6px; font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; color: #64748b; }
.m28-mi { display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 10px; border: 0; border-radius: 8px; cursor: pointer; text-align: left;
  font-size: 13px; color: #cbd5e1; background: transparent; }
.m28-mi:hover:not(:disabled) { background: #152238; color: #fff; }
.m28-mi:disabled { opacity: .45; cursor: not-allowed; }
.m28-mi-cur { background: rgba(59, 130, 246, .14); }
.m28-mi-name { font-family: var(--font-mono); font-weight: 700; color: #fcd34d; }
.m28-mi-date { color: #64748b; font-size: 13px; }
.m28-mi-tag { margin-left: auto; padding: 1px 8px; border-radius: 999px; font-size: 13px; color: #93c5fd; background: rgba(37, 99, 235, .18); white-space: nowrap; }
.m28-mi-empty { padding: 8px 10px; font-size: 13px; color: #94a3b8; }
.m28-mi-all { margin-top: 4px; padding: 8px 10px; border: 0; border-top: 1px solid #1e2b42; border-radius: 0 0 8px 8px; cursor: pointer; text-align: left;
  font-size: 13px; font-weight: 700; color: #93c5fd; background: transparent; }
.m28-mi-all:hover { background: #152238; }
#m28-tools { flex: 0 1 auto !important; width: auto !important; gap: 6px; flex-wrap: wrap; align-items: center; justify-content: flex-end; }
#m28-tools > * { flex: 0 0 auto !important; min-width: 0 !important; width: auto !important; }
#m28-tools #close-row { gap: 6px; flex-wrap: nowrap; }
#m28-tools button { display: inline-flex !important; align-items: center; gap: 6px; min-height: 32px !important; min-width: 0 !important;
  width: auto !important; padding: 0 12px !important; border-radius: 12px !important; font-size: 13px !important; font-weight: 600 !important;
  white-space: nowrap; color: #cbd5e1 !important; background: #0e1626 !important; border: 1px solid #1e2b42 !important; box-shadow: none !important; }
#m28-tools button:hover { color: #fff !important; background: #152238 !important; border-color: rgba(59, 130, 246, .5) !important; }
#m28-tools button.stop { color: #fca5a5 !important; background: rgba(239, 68, 68, .12) !important; border-color: rgba(239, 68, 68, .45) !important; }
#m28-tools button.primary { color: #6ee7b7 !important; background: rgba(16, 185, 129, .12) !important; border-color: rgba(16, 185, 129, .45) !important; }
#m28-tools button::before { content: ""; flex: 0 0 14px; width: 14px; height: 14px; background: currentColor;
  -webkit-mask: var(--ic) center / contain no-repeat; mask: var(--ic) center / contain no-repeat; }
#cd-open-reviewer { --ic: @@user@@; }
#cd-open-cvat { --ic: @@server@@; }
#cd-open-tflip { --ic: @@sliders@@; }
#cd-open-paths { --ic: @@folder@@; }
#btn-lead { --ic: @@team@@; }
#btn-dong { --ic: @@power@@; }
#m28-tools #btn-dong { font-size: 0 !important; gap: 0 !important; padding: 0 9px !important; color: #94a3b8 !important; }
#btn-dong::before { flex-basis: 16px !important; width: 16px !important; height: 16px !important; }
#btn-dong:hover { color: #f87171 !important; background: rgba(239, 68, 68, .15) !important; border-color: rgba(239, 68, 68, .4) !important; }

#tabs > .tab-wrapper, #tabs > .tab-container, #tabs > div:first-child:has(> [role="tablist"]), #tabs > [role="tablist"] { display: none !important; }
#tabs { margin-top: 0 !important; }

#m28-steps { margin-top: 0; padding: 4px 8px !important; background: #0a0f1d; border: 1px solid #1e2b42; border-radius: 14px; }
#m28-steps .html-container, #m28-brand-wrap .html-container, #m28-batch .html-container, #progress .html-container, #pagelbl .html-container,
#bot-cvat .html-container, #cheat .html-container, #info .html-container, #conf .html-container { padding: 0 !important; }
.m28-steps { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.m28-steps-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.m28-step { display: inline-flex; align-items: center; gap: 9px; padding: 7px 14px 7px 8px; border-radius: 12px; font-size: 13px; font-weight: 700;
  white-space: nowrap; text-decoration: none !important; color: #94a3b8 !important; border: 1px solid transparent; background: transparent; cursor: pointer;
  transition: background .15s, color .15s; }
.m28-step:hover { background: #0e1626; color: #e2e8f0 !important; }
.m28-step.st-off, .m28-step.st-off:hover { opacity: .4; cursor: not-allowed; background: transparent; color: #94a3b8 !important; }   /* chưa mở đợt: khoá bước 2–4 */
.m28-step i { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; font-style: normal;
  font-size: 13px; font-weight: 800; color: #94a3b8; background: #1e293b; }
.m28-step.st-done { color: #6ee7b7 !important; }
.m28-step.st-done i { color: #34d399; background: rgba(16, 185, 129, .18); }
.m28-step.st-cur i { color: #fff; background: #2563eb; box-shadow: 0 0 0 3px rgba(59, 130, 246, .25); }
.m28-step.st-cur { color: #e2e8f0 !important; }
.m28-step.st-warn i { background: #d97706; }
.m28-step.st-view, .m28-nav.st-view { color: #fff !important; background: rgba(59, 130, 246, .12); border-color: rgba(59, 130, 246, .45); }
.m28-step:focus-visible, .m28-nav:focus-visible { outline: 2px solid #3b82f6; outline-offset: 2px; }
.m28-step-sep { display: inline-flex; color: #334155; }
.m28-nav-extra { margin-left: auto; display: flex; gap: 4px; flex-wrap: wrap; }
.m28-nav { display: inline-flex; align-items: center; padding: 6px 11px; border-radius: 10px; font-size: 13px; font-weight: 600; white-space: nowrap;
  text-decoration: none !important; color: #94a3b8 !important; border: 1px solid transparent; }
.m28-nav:hover { background: #0e1626; color: #e2e8f0 !important; }
body:not(.m28-lead) .m28-lead-only { display: none !important; }     /* chỉ luật ẨN có điều kiện: Gradio thêm tiền tố .gradio-container … .contain vào mọi luật
                                                                       nên luật "hiện khi body.m28-lead" luôn thua luật ẩn có tiền tố; bật Team lead là hết ẩn */
.m28-step-hint { display: inline-flex; max-width: 100%; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 4px 12px; border-radius: 999px;
  font-size: 13px; font-weight: 600; color: #93c5fd; background: rgba(59, 130, 246, .10); border: 1px solid rgba(59, 130, 246, .25); }
.m28-step-hint b { color: #fff; }
.m28-dot { width: 8px; height: 8px; border-radius: 50%; background: #60a5fa; animation: m28-blink 1.6s ease-in-out infinite; }
@keyframes m28-blink { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .m28-dot { animation: none; } }
.cd-link-btn { padding: 3px 12px !important; min-height: 26px !important; font-size: 13px !important; border-radius: 9px !important; }

#progress { margin-top: 0; }
#tab-ra { padding-top: 0 !important; }
.m28-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; padding: 8px 14px; border-radius: 16px;
  border: 1px solid rgba(59, 130, 246, .4); background: linear-gradient(90deg, rgba(23, 37, 84, .55), #0a0f1d 45%, #0a0f1d);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .35); }
.m28-head-ic { width: 36px; height: 36px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; color: #60a5fa;
  background: rgba(59, 130, 246, .2); border: 1px solid rgba(59, 130, 246, .3); flex: 0 0 auto; }
.m28-head-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.m28-head .m28-top { display: flex; align-items: center; gap: 4px 10px; flex-wrap: wrap; }
.m28-kicker { font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #94a3b8; }
.m28-run { font-family: var(--font-mono); font-size: 16px; font-weight: 800; color: #fcd34d; }
.m28-state { font-size: 13px; font-weight: 700; padding: 2px 10px; border-radius: 999px; color: #93c5fd; background: rgba(59, 130, 246, .2);
  border: 1px solid rgba(59, 130, 246, .3); }
.m28-head .m28-sub { font-size: 13px; color: #94a3b8; }
.m28-head .m28-prog { flex: 1 1 380px; display: flex; align-items: center; gap: 8px 10px; flex-wrap: wrap; min-width: 0; }
.m28-head .m28-count { font-size: 13px; font-weight: 700; color: #cbd5e1; }
.m28-bar.m28-bar3 { display: flex; flex: 1 1 140px; min-width: 100px; height: 8px; border-radius: 999px; overflow: hidden; background: #060913; border: 1px solid #1e2b42; }
.m28-bar3 > i { display: block; height: 100%; border-radius: 0 !important; transition: width .25s; }
.m28-bar3 > .b-nhan { background: #10b981 !important; } .m28-bar3 > .b-gan_tay { background: #f59e0b !important; } .m28-bar3 > .b-bo { background: #f43f5e !important; }
.m28-pct { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: #cbd5e1; }
.m28-head .m28-chip { font-size: 13px; line-height: 18px; padding: 1px 9px; }
.m28-head-btns { display: inline-flex; gap: 8px; margin-left: auto; flex-wrap: wrap; }
.m28-head-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; min-height: 32px; border-radius: 12px; cursor: pointer;
  font-size: 13px; font-weight: 700; color: #e2e8f0; background: #0e1626; border: 1px solid #1e2b42; }
.m28-head-btn:hover { background: #152238; border-color: rgba(59, 130, 246, .6); color: #fff; }
.m28-head-btn .ic { color: #fbbf24; }
.m28-head-btn-blue { color: #93c5fd; background: rgba(37, 99, 235, .2); border-color: rgba(59, 130, 246, .4); }
.m28-head-btn-blue .ic { color: inherit; }
.m28-done-bar { border-radius: 14px !important; }

#ra-bar { margin: 0 0 8px !important; padding: 4px 8px !important; background: #0a0f1d; border: 1px solid #1e2b42; border-radius: 12px; }
#filter { background: #060913 !important; border: 1px solid #1e2b42 !important; border-radius: 10px !important; padding: 4px !important; }
#filter label { background: transparent !important; border: 0 !important; box-shadow: none !important; border-radius: 7px !important;
  padding: 4px 12px !important; font-size: 13px !important; font-weight: 700 !important; color: #94a3b8 !important; }
#filter label:hover { color: #fff !important; }
#filter label.selected, #filter label:has(input:checked) { background: #1e293b !important; color: #fff !important; }
#filter .wrap { width: 100%; display: grid !important; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3px !important; }   /* 2×2: đều nhau, không cắt chữ */
#filter label { flex: 1 1 auto !important; min-width: 0 !important; padding: 4px 6px !important; justify-content: center !important; text-align: center; white-space: nowrap; }

#pager button { min-height: 28px !important; border-radius: 9px !important; font-size: 13px !important; background: #0e1626 !important; }

.m28-card { background: #0a0f1d !important; border: 1px solid #1e2b42 !important; border-radius: 16px !important; padding: 12px !important; }
#center.m28-card { gap: 10px !important; }
#left { gap: 10px !important; }
#big { background: #060913 !important; border: 1px solid rgba(30, 43, 66, .8) !important; border-radius: 12px !important; }
#grid { background: #060913 !important; border: 1px solid rgba(30, 43, 66, .8) !important; border-radius: 12px !important; padding: 4px 6px !important; }
#grid .thumbnail-item { border-radius: 10px !important; background: #0e1626 !important; }
#grid .thumbnail-item.m28-cur { outline: 2px solid #3b82f6 !important; outline-offset: 1px; box-shadow: 0 0 0 5px rgba(59, 130, 246, .22) !important; }
.m28-zoom { background: rgba(10, 15, 29, .9) !important; border-color: #1e2b42 !important; backdrop-filter: blur(6px); }

#info { min-height: 0 !important; }
.m28-meta-card { margin: 0 !important; background: #0e1626 !important; border: 1px solid #1e2b42 !important; border-radius: 12px !important; padding: 10px 12px !important; }
.m28-meta-card .m28-info th, .m28-meta-card .m28-info td { padding: 3px 8px 3px 0 !important; font-size: 13px !important; line-height: 1.35; }
.m28-meta-card .m28-info th { width: 92px; color: #94a3b8 !important; font-weight: 600; white-space: normal; vertical-align: top; }
.m28-meta-card .m28-pts { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.m28-meta-card .face-name { font-family: var(--font-mono); font-size: 15px !important; color: #f1f5f9; }
.m28-meta-card .m28-pts { color: #fbbf24; }

#decide button { border: 0 !important; border-radius: 12px !important; min-height: 66px !important; font-size: 15px !important;
  transition: transform .08s, filter .15s; }
#decide button:active:not(:disabled) { transform: scale(.97); }
#btn-nhan { background: linear-gradient(135deg, #059669, #0f766e) !important; box-shadow: 0 8px 20px rgba(16, 185, 129, .2) !important; }
#btn-gantay { background: linear-gradient(135deg, #d97706, #c2410c) !important; box-shadow: 0 8px 20px rgba(245, 158, 11, .2) !important; }
#btn-bo { background: linear-gradient(135deg, #e11d48, #b91c1c) !important; box-shadow: 0 8px 20px rgba(244, 63, 94, .2) !important; }
#decide #btn-cakho { min-height: 40px !important; background: linear-gradient(135deg, #7c3aed, #4f46e5) !important; box-shadow: 0 6px 16px rgba(124, 58, 237, .2) !important; }
#reason { background: transparent !important; border: 0 !important; padding: 0 !important; box-shadow: none !important; }
#reason [data-testid="block-info"], #reason legend, #reason .block-info { font-size: 13px !important; color: #94a3b8 !important; font-weight: 700 !important; }
#reason .wrap { gap: 6px !important; }
#reason label { justify-content: center; text-align: center; min-height: 36px; padding: 6px 6px !important; border-radius: 9px !important; font-size: 13px !important;
  font-weight: 600 !important; color: #cbd5e1 !important; background: #0e1626 !important; border: 1px solid #1e2b42 !important; box-shadow: none !important; }
#reason label:hover { background: #1b2a45 !important; }
#reason label.selected, #reason label:has(input:checked) { color: #fff !important; background: rgba(37, 99, 235, .28) !important; border-color: #3b82f6 !important; }
#reason input[type=radio] { position: absolute; opacity: 0; width: 1px; height: 1px; pointer-events: none; }
#nav button { border-radius: 12px !important; font-size: 14px !important; background: #0e1626 !important; border: 1px solid #1e2b42 !important; }
#nav button:hover:not(:disabled) { background: #152238 !important; }
#msg { min-height: 0 !important; }
#msg:not(:has(.html-container > div > *)) { display: none; }
#cheat { position: absolute !important; width: 0 !important; height: 0 !important; min-height: 0 !important; padding: 0 !important; border: 0 !important;
  overflow: visible !important; }   /* chỉ chứa popup Phím tắt (mở bằng biểu tượng ở góc ảnh lớn / phím H): không chiếm chỗ trong cột giữa */
.m28-cheat-pop[hidden] { display: none !important; }
.m28-cheat-box { width: min(880px, 100%) !important; }
.m28-cheat-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; }
.m28-cheat-grid section { padding: 10px 12px; border-radius: 10px; border: 1px solid #1e2b42; background: #0a0f1d; }
.m28-cheat-grid h4 { margin: 0 0 6px; font-size: 15px; color: #e2e8f0; }
.m28-cheat-grid p { margin: 0 0 6px; font-size: 14px; line-height: 1.55; color: #cbd5e1; }
.m28-cheat-keys { color: #cbd5e1; }
.m28-cheat-close { min-height: 42px; width: 100%; border-radius: 10px; font-weight: 800; cursor: pointer; color: #e2e8f0; background: #0e1626; border: 1px solid #1e2b42; }
@media (max-width: 760px) { .m28-cheat-grid { grid-template-columns: 1fr; } }

#conf { padding: 0 !important; }
.conf-table-wrapper { background: #0a0f1d !important; border: 1px solid #1e2b42 !important; border-radius: 16px !important; padding: 12px 14px !important; }
.conf-group-card { background: #0e1626 !important; border-color: #1e2b42 !important; }
.conf-scroll-box { background: #060913 !important; border-color: #1e2b42 !important; }
.conf-table thead { background: #0a0f1d !important; }
#bot-cvat { margin-top: 2px !important; }
#side { gap: 10px !important; background: #0a0f1d !important; border: 1px solid #1e2b42 !important; border-radius: 16px !important; padding: 10px 12px !important; }
#side .conf-table-wrapper, #side .m28-meta-card { background: transparent !important; border: 0 !important; border-radius: 0 !important; padding: 0 !important; }
.side-tabs { background: #060913 !important; border-color: #1e2b42 !important; }
.side-tab { color: #94a3b8 !important; }
.side-tab:hover, .side-tab[aria-selected="true"] { color: #f1f5f9 !important; }
.side-tab[aria-selected="true"] { background: rgba(37, 99, 235, .28) !important; }
.m28-modal-box { border-radius: 16px !important; border-color: #1e2b42 !important; }
.cd-note, .nap-note, .dot-muted, .m28-note, .m28-guide, .m28-keys, .ck-note, .tk-note, .tk-ghi, .push-next, .push-envhelp, #cd-remember-note { display: none !important; }
.nap-box.nap-err .nap-note:not(.push-next), .nap-box.nap-warn .nap-note:not(.push-next) { display: block !important; }
"""
for _k, _v in MASK.items():
    CSS = CSS.replace(f"@@{_k}@@", _v)
