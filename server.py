
from urllib.parse import urlparse,parse_qs,quote,unquote
from pathlib import Path
import json, html, mimetypes, io, traceback, os, base64, hmac
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from src.db import connect,init
from src.importer import import_payload,fetch_tracker

ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv("THE_LOBBY_DB", str(ROOT/"inhouse.db")))
RAW=Path(os.getenv("THE_LOBBY_RAW", str(ROOT/"data"/"raw")))
STATIC=ROOT/"static"

DISCORD_INVITE=os.getenv("DISCORD_INVITE","https://discord.gg/yAqfGTbtPw")
SITE_NAME=os.getenv("SITE_NAME","The Lobby")
SITE_TAGLINE=os.getenv("SITE_TAGLINE","Private Valorant Inhouses")
HOST=os.getenv("HOST","0.0.0.0")
PORT=int(os.getenv("PORT","8765"))
ADMIN_USER=os.getenv("ADMIN_USER","")
ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD","")
MAX_IMPORT_BYTES=int(os.getenv("MAX_IMPORT_BYTES",str(15*1024*1024)))

DB.parent.mkdir(parents=True,exist_ok=True)
if not os.getenv("TURSO_DATABASE_URL"):
    RAW.mkdir(parents=True,exist_ok=True)
init(DB)

def esc(x): return html.escape(str(x if x is not None else ""))
def n(v,d=1): return "—" if v is None else f"{v:.{d}f}"
def pct(a,b): return 0 if not b else 100*a/b
def ratio(a,b): return a if not b else a/b
def player_url(r): return "/player?riot="+quote(r,safe="")
def match_url(m): return "/match?id="+quote(m,safe="")

CSS=r"""
:root{--bg:#0c1016;--panel:#151b24;--panel2:#1c2430;--line:#2a3442;--text:#edf2f7;--muted:#91a0b4;--red:#ff4655;--green:#4bc58b;--blue:#52a8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Inter,Segoe UI,system-ui,sans-serif}a{color:inherit;text-decoration:none}
nav{height:64px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:26px;padding:0 max(22px,calc((100% - 1180px)/2));background:#10151d;position:sticky;top:0;z-index:4}
.brand{font-weight:900;letter-spacing:.8px}.brand b{color:var(--red)}nav a:hover{color:white}.navlink{color:var(--muted)}
main{max-width:1180px;margin:auto;padding:30px 22px 70px}.hero,.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px}.hero{padding:24px}.panel{margin-top:18px;overflow:hidden}
h1{margin:3px 0 6px;font-size:31px}.eyebrow,.muted,small{color:var(--muted)}.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-top:18px}
.stat{background:var(--panel2);padding:14px}.stat b{display:block;font-size:21px;margin-top:4px}.section-title{padding:16px 18px;border-bottom:1px solid var(--line);font-weight:800}
table{width:100%;border-collapse:collapse}th,td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:right}th{font-size:11px;color:var(--muted);text-transform:uppercase}th:first-child,td:first-child{text-align:left}
tr.click:hover{background:#1d2632;cursor:pointer}.win{color:var(--green)}.loss{color:#ff7882}.pill{padding:3px 7px;border-radius:6px;background:#263142;font-size:12px}
.agent{display:flex;align-items:center;gap:10px}.agent img{width:36px;height:36px;object-fit:contain}.tabs{display:flex;gap:4px;margin-top:18px}.tabs a{padding:10px 14px;border-radius:8px;color:var(--muted)}.tabs a.active{background:var(--panel2);color:white}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}.rounds{display:flex;flex-wrap:wrap;gap:6px;padding:16px}.round{width:34px;height:34px;display:grid;place-items:center;border-radius:6px;font-weight:800}.rred{background:#5b2931}.rblue{background:#1f4c75}
form.import{display:flex;gap:8px;margin-top:16px}input,button{font:inherit;border-radius:8px;border:1px solid var(--line);padding:11px 13px}input{background:#0f141c;color:white;flex:1}button{background:var(--red);color:white;font-weight:800;cursor:pointer}.notice{padding:12px 14px;border:1px solid var(--line);background:#111821;border-radius:8px;margin-top:12px}.avatar{width:90px;height:90px;border-radius:10px;background:#222c39;object-fit:cover}.profile-head{display:flex;gap:18px;align-items:center}
@media(max-width:800px){.stats{grid-template-columns:repeat(3,1fr)}.grid2{grid-template-columns:1fr}form.import{flex-direction:column}}
"""

def layout(title,body):
    return f"""<!doctype html><html lang=fr><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{esc(title)} · {esc(SITE_NAME)}</title><style>{CSS}
/* V3 */
:root{{--bg:#0b1118;--panel:#111a24;--panel2:#16212d;--line:#243241;--text:#edf4fb;--muted:#8fa1b3;--accent:#ff4655;--good:#22c997;--great:#28c7d9;--warn:#f2a93b;--bad:#ff5d6c}}
body{{background:radial-gradient(circle at 20% -10%,#172536 0,transparent 35%),var(--bg);color:var(--text)}}
.panel,.hero{{background:linear-gradient(180deg,rgba(24,36,49,.96),rgba(15,24,34,.96));border:1px solid var(--line);box-shadow:0 14px 38px rgba(0,0,0,.18);border-radius:14px}}
.matchtabs{{display:grid;grid-template-columns:repeat(2,1fr);margin:16px 0 22px;border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.matchtabs a{{padding:16px;text-align:center;color:var(--muted);background:var(--panel);font-weight:800}}.matchtabs a.active{{color:white;background:var(--panel2);box-shadow:inset 0 -3px var(--accent)}}
.mkgrid{{display:grid;grid-template-columns:minmax(180px,1.8fr) repeat(4,minmax(58px,.55fr));gap:7px;align-items:center;padding:7px 14px}}.mkhead{{color:var(--muted);font-size:11px;font-weight:800}}.mkplayer{{font-weight:800}}
.mkcell{{text-align:center;padding:10px 6px;border-radius:7px;background:#202d3a;color:#66788a;font-weight:900}}.on2{{background:#116f5d;color:#eafff8}}.on3{{background:#148f91;color:white}}.on4{{background:#1476a8;color:white}}.on5{{background:#5854c7;color:white}}
.teamlabel{{padding:18px 14px 7px;font-size:18px;font-weight:900;border-top:1px solid var(--line)}}
.metric-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px;margin:14px 0}}.metric{{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:14px}}.metric small{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;font-weight:800}}.metric b{{display:block;font-size:24px;margin-top:4px}}.vgood{{color:var(--great)}}.good{{color:var(--good)}}.warnv{{color:var(--warn)}}.badv{{color:var(--bad)}}

/* FINAL UI */
:root{{--surface:#101923;--surface2:#152231;--surface3:#1b2b3b;--stroke:#26394b;--soft:#93a7ba;--cyan:#39d0d8;--green:#35d49a;--amber:#f5b84b;--red2:#ff6472;}}
.wrap{{max-width:1240px!important;padding:24px!important}}
h1{{font-size:clamp(28px,4vw,46px)!important;letter-spacing:-.035em;margin:.18em 0!important}}
.hero{{padding:26px!important;margin-bottom:18px!important}}
.stats{{gap:10px!important}}.stat{{border-radius:11px!important;background:var(--surface2)!important;border:1px solid var(--stroke)!important}}
.stat b{{font-size:22px!important}}
.panel{{overflow:hidden;margin:16px 0!important}}.section-title{{padding:14px 16px!important;background:rgba(255,255,255,.018);border-bottom:1px solid var(--stroke)}}
table{{width:100%;border-spacing:0!important}}tbody tr{{transition:.16s ease}}tbody tr:hover{{background:rgba(57,208,216,.055)!important}}
th{{font-size:10px!important;text-transform:uppercase;letter-spacing:.08em;color:var(--soft)!important;background:rgba(255,255,255,.018)}}
td{{border-bottom:1px solid rgba(255,255,255,.035)!important}}
a{{transition:.15s ease}}a:hover{{color:var(--cyan)!important}}
.tabs{{gap:5px!important;background:var(--surface);padding:5px;border:1px solid var(--stroke);border-radius:11px}}
.tabs a{{border-radius:8px!important;padding:10px 15px!important}}.tabs a.active{{background:var(--surface3)!important;color:white!important}}
.grid2{{gap:16px!important}}
.metric-strip{{grid-template-columns:repeat(4,1fr)!important}}.metric{{position:relative;overflow:hidden}}
.metric b{{font-size:27px!important;letter-spacing:-.03em}}.metric:after{{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;background:currentColor;opacity:.65}}
.matchtabs{{max-width:560px;margin:16px auto 22px!important}}
.matchtabs a{{position:relative}}.matchtabs a.active{{box-shadow:inset 0 -3px var(--cyan)!important}}
.mkcell{{font-variant-numeric:tabular-nums}}
.diff-pos{{color:var(--green)!important;font-weight:900}}.diff-neg{{color:var(--red2)!important;font-weight:900}}.diff-zero{{color:var(--soft)!important;font-weight:800}}
.score-win{{color:var(--green);font-weight:900}}.score-loss{{color:var(--red2);font-weight:900}}
.pill{{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;background:var(--surface3);border:1px solid var(--stroke);font-size:11px;font-weight:800}}
.qol-note{{font-size:11px;color:var(--soft);margin:8px 0 0}}
@media(max-width:760px){{.wrap{{padding:13px!important}}.metric-strip{{grid-template-columns:repeat(2,1fr)!important}}.grid2{{grid-template-columns:1fr!important}}.mkgrid{{grid-template-columns:minmax(120px,1.5fr) repeat(4,48px)!important;padding:6px 8px!important}}table{{font-size:12px}}}}

.match-hero{{min-height:250px;background-size:cover;background-position:center;border:1px solid var(--stroke);border-radius:16px;padding:24px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 18px 50px rgba(0,0,0,.25);overflow:hidden}}
.match-kicker{{font-size:12px;font-weight:900;letter-spacing:.13em;color:#c9d6e2;text-transform:uppercase}}
.match-score{{display:grid;grid-template-columns:1fr 1fr;gap:24px;max-width:650px;margin:18px auto;width:100%}}
.score-side{{text-align:center;padding:12px;border-radius:13px;background:rgba(9,15,22,.58);backdrop-filter:blur(7px);border:1px solid rgba(255,255,255,.09)}}.score-side.winner{{border-color:rgba(53,212,154,.34)}}
.score-team{{font-size:13px;color:#c4d0dc;font-weight:800;margin-bottom:5px}}.score-number{{font-size:64px;line-height:1;font-weight:950;letter-spacing:-.055em;color:#aebccd}}.score-side.winner .score-number{{color:#41dda5}}
.result-pill{{display:inline-flex;margin-top:10px;padding:4px 9px;border-radius:999px;font-size:10px;font-weight:950}}.result-pill.win{{background:rgba(53,212,154,.16);color:#58e7b3}}.result-pill.loss{{background:rgba(255,100,114,.14);color:#ff7c87}}
.match-meta{{text-align:center;color:#a7b6c5;font-size:12px}}.team-table-title{{padding:16px 18px;font-size:18px;font-weight:900;border-bottom:1px solid var(--stroke)}}.team-table-title span{{margin-left:9px;color:var(--soft);font-size:11px}}
.playercell a{{display:flex!important;flex-direction:column;gap:6px;line-height:1.15;padding:3px 0}}.playercell b{{font-size:14px}}.playercell span{{font-size:11px;color:var(--soft);font-weight:650}}.table-scroll{{overflow-x:auto}}
.hero .muted{{margin-top:9px;line-height:1.6}}td{{line-height:1.42}}.mkplayer{{line-height:1.35}}.metric small{{margin-bottom:6px;line-height:1.3}}
.landing{{min-height:230px;display:flex;align-items:center;padding:34px;border-radius:16px;margin-bottom:18px;border:1px solid var(--stroke);background:radial-gradient(circle at 80% 20%,rgba(57,208,216,.13),transparent 32%),linear-gradient(135deg,#121e2a,#0d151e)}}.landing p{{max-width:610px;color:var(--soft);line-height:1.6;margin:0 0 20px}}
.discord-cta{{display:inline-flex;padding:11px 15px;border-radius:9px;background:#5865F2;color:white!important;font-weight:900;font-size:12px}}.discord-cta.disabled{{opacity:.55}}
@media(max-width:650px){{.match-score{{gap:10px}}.score-number{{font-size:48px}}.match-hero{{min-height:220px;padding:16px}}}}

/* FINAL V3 — welcome, cards, portraits, maps */
.match-player{{display:flex;align-items:center;gap:12px;min-width:180px}}
.agent-portrait{{width:42px;height:42px;flex:0 0 42px;border-radius:10px;overflow:hidden;background:linear-gradient(145deg,#243648,#14202c);border:1px solid rgba(255,255,255,.1)}}
.agent-portrait img{{width:100%;height:100%;object-fit:cover;display:block}}
.player-copy{{display:flex;flex-direction:column;gap:6px;min-width:0}}.player-copy b{{font-size:14px}}.player-copy span{{font-size:11px;color:var(--soft)}}
.welcome-hero{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(260px,.7fr);gap:28px;align-items:center;padding:42px;border:1px solid var(--stroke);border-radius:18px;background:radial-gradient(circle at 78% 18%,rgba(57,208,216,.17),transparent 28%),radial-gradient(circle at 10% 90%,rgba(255,70,85,.10),transparent 30%),linear-gradient(135deg,#142231,#0c141d);box-shadow:0 20px 60px rgba(0,0,0,.22)}}
.welcome-copy h1{{font-size:clamp(36px,5vw,62px)!important;max-width:720px;margin:8px 0 14px!important}}.welcome-copy p{{max-width:700px;color:#a8b9c9;font-size:15px;line-height:1.75;margin:0 0 24px}}
.welcome-actions{{display:flex;gap:10px;flex-wrap:wrap}}.secondary-cta{{display:inline-flex;padding:11px 15px;border-radius:9px;border:1px solid var(--stroke);background:rgba(255,255,255,.035);font-weight:900;font-size:12px;color:#dce8f3!important}}
.welcome-stats{{display:grid;gap:10px}}.welcome-stats div{{padding:18px;border-radius:13px;background:rgba(7,13,20,.48);border:1px solid rgba(255,255,255,.08)}}.welcome-stats b{{display:block;font-size:30px;letter-spacing:-.04em}}.welcome-stats span{{display:block;margin-top:3px;color:var(--soft);font-size:11px}}
.home-section-head{{display:flex;align-items:end;justify-content:space-between;gap:20px;margin:30px 2px 14px}}.home-section-head h2{{margin:3px 0 0;font-size:25px}}.home-section-head>span{{font-size:11px;color:var(--soft)}}
.match-card-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
.home-match{{min-height:190px;background-size:cover;background-position:center;border:1px solid var(--stroke);border-radius:15px;padding:17px;display:flex;flex-direction:column;justify-content:space-between;color:white!important;overflow:hidden;box-shadow:0 12px 30px rgba(0,0,0,.18);transform:translateY(0);transition:.18s ease}}
.home-match:hover{{transform:translateY(-3px);border-color:rgba(57,208,216,.45);box-shadow:0 18px 38px rgba(0,0,0,.28)}}.home-match-top{{display:flex;justify-content:space-between;font-size:10px;color:#d0dbe5;font-weight:750}}
.home-match-bottom{{display:flex;align-items:end;justify-content:space-between;gap:15px}}.home-match-bottom small{{display:block;font-size:9px;color:#9fb0c0;letter-spacing:.12em;font-weight:900}}.home-match-bottom strong{{display:block;font-size:27px;margin-top:2px}}
.home-score{{display:flex;align-items:center;gap:7px;font-size:31px;letter-spacing:-.04em}}.home-score span{{font-size:17px;color:#8092a4}}
.map-cell{{display:flex;align-items:center;gap:12px;min-width:190px}}.map-cell>div{{display:flex;flex-direction:column;gap:3px}}.map-cell small{{color:var(--soft);font-size:10px}}
.map-thumb{{width:76px;height:44px;object-fit:cover;border-radius:8px;border:1px solid rgba(255,255,255,.09)}}.map-thumb-fallback{{width:76px;height:44px;border-radius:8px;background:var(--surface3)}}
@media(max-width:820px){{.welcome-hero{{grid-template-columns:1fr;padding:26px}}.welcome-stats{{grid-template-columns:repeat(3,1fr)}}.match-card-grid{{grid-template-columns:1fr}}}}
@media(max-width:540px){{.welcome-stats{{grid-template-columns:1fr}}.home-section-head>span{{display:none}}}}

/* FINAL V4 — Players + KAST polish */
.players-hero{{display:flex;justify-content:space-between;align-items:end;gap:24px;padding:30px 32px;border:1px solid var(--stroke);border-radius:16px;background:radial-gradient(circle at 88% 18%,rgba(57,208,216,.13),transparent 28%),linear-gradient(135deg,#142231,#0d151e)}}
.players-hero h1{{margin:4px 0 8px!important}}.players-hero p{{max-width:720px;color:var(--soft);line-height:1.6;margin:0}}.players-count{{text-align:right;min-width:150px}}.players-count b{{display:block;font-size:40px;line-height:1}}.players-count span{{display:block;color:var(--soft);font-size:11px;margin-top:6px}}
.leaderboard-head{{display:flex;justify-content:space-between;align-items:center;padding:22px 4px 10px;color:var(--soft);font-size:10px;font-weight:900;letter-spacing:.09em}}
.player-rank-list{{display:grid;gap:8px}}.player-rank-card{{display:grid;grid-template-columns:44px 48px minmax(180px,1.6fr) repeat(5,minmax(74px,.55fr));align-items:center;gap:10px;padding:12px 16px;border:1px solid var(--stroke);border-radius:12px;background:linear-gradient(90deg,rgba(24,37,50,.94),rgba(15,24,34,.94));color:var(--text)!important;transition:.17s ease}}
.player-rank-card:hover{{transform:translateX(4px);border-color:rgba(57,208,216,.4);background:linear-gradient(90deg,rgba(27,44,59,.98),rgba(17,28,39,.98))}}
.rank-no{{font-size:12px;color:var(--soft);font-weight:900}}.rank-avatar{{width:42px;height:42px;border-radius:10px;overflow:hidden;background:var(--surface3);display:grid;place-items:center;font-weight:900;color:var(--cyan)}}.rank-avatar img{{width:100%;height:100%;object-fit:cover}}
.rank-name{{display:flex;flex-direction:column;gap:5px;min-width:0}}.rank-name b{{font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.rank-name span{{font-size:10px;color:var(--soft)}}.rank-stat small{{display:block;color:var(--soft);font-size:9px;font-weight:900;letter-spacing:.06em;margin-bottom:4px}}.rank-stat b{{font-size:15px;font-variant-numeric:tabular-nums}}
@media(max-width:900px){{.player-rank-card{{grid-template-columns:36px 44px minmax(150px,1fr) repeat(3,70px)}}.rank-stat:nth-last-child(-n+2){{display:none}}}}
@media(max-width:620px){{.players-hero{{align-items:start;flex-direction:column}}.players-count{{text-align:left}}.player-rank-card{{grid-template-columns:32px 42px 1fr 62px}}.rank-stat{{display:none}}.rank-stat:nth-of-type(4){{display:block}}.leaderboard-head span:last-child{{display:none}}}}

/* V4.1 */
.aliases{{margin:2px 0 8px;color:var(--soft);font-size:11px;font-style:italic}}.aliases span{{font-style:normal;color:#71869a;margin-right:4px}}
.profile-tools{{display:flex;justify-content:flex-end;margin-top:-4px}}.profile-tools a{{font-size:9px;font-weight:900;letter-spacing:.09em;color:var(--soft);padding:5px 8px;border:1px solid var(--stroke);border-radius:7px}}
.identity-form{{display:flex;gap:9px;padding:16px}}.alias-list{{display:flex;gap:8px;flex-wrap:wrap;padding:16px 16px 0}}.alias-chip{{padding:6px 9px;border-radius:7px;background:var(--surface3);border:1px solid var(--stroke);font-size:11px;color:#c9d7e4}}
.adv-panel{{position:relative}}.adv-panel:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:3px}}
.fc-panel:before{{background:linear-gradient(#39d0d8,#35d49a)}}.combat-panel:before{{background:linear-gradient(#ff6472,#f5b84b)}}.roundimpact-panel:before{{background:linear-gradient(#8d7dff,#39d0d8)}}
.fc-panel .stat:nth-child(1) b,.fc-panel .stat:nth-child(4) b{{color:#63c8ff}}
.combat-panel .stat:nth-child(1) b{{color:#57dda8}}.combat-panel .stat:nth-child(2) b{{color:#ff7784}}.combat-panel .stat:nth-child(3) b{{color:#70bfff}}.combat-panel .stat:nth-child(6) b{{color:#c99cff}}
.roundimpact-panel .stat:nth-child(1) b{{color:#57dda8}}.roundimpact-panel .stat:nth-child(2) b{{color:#70bfff}}.roundimpact-panel .stat:nth-child(3) b{{color:#38c997}}.roundimpact-panel .stat:nth-child(4) b{{color:#31b6c9}}.roundimpact-panel .stat:nth-child(5) b{{color:#498ed4}}.roundimpact-panel .stat:nth-child(6) b{{color:#9a7bea}}
@media(max-width:620px){{.identity-form{{flex-direction:column}}}}

/* V4.2 — VLR-inspired Recent Inhouses */
.recent-results{{display:grid;gap:3px;background:rgba(255,255,255,.015)}}
.recent-result{{display:grid;grid-template-columns:minmax(180px,1.5fr) minmax(120px,.8fr) minmax(120px,.8fr) 105px;min-height:72px;align-items:stretch;background:linear-gradient(90deg,#192633,#15212c);border-bottom:1px solid rgba(255,255,255,.035);color:var(--text)!important;transition:.16s ease;overflow:hidden}}
.recent-result:hover{{background:linear-gradient(90deg,#203244,#192936);transform:translateX(3px)}}
.recent-map-art{{background-size:cover;background-position:center;display:flex;flex-direction:column;justify-content:flex-end;padding:10px 14px;border-right:1px solid rgba(255,255,255,.04)}}
.recent-map-art b{{font-size:13px;letter-spacing:.01em}}.recent-map-art span{{font-size:10px;color:#c0ceda;margin-top:3px}}
.recent-agent-cell{{display:flex;align-items:center;gap:10px;padding:0 14px;font-size:12px;font-weight:800;color:#c9d6e2}}
.recent-agent-cell img{{width:38px;height:38px;border-radius:9px;object-fit:cover;border:1px solid rgba(255,255,255,.08);background:var(--surface3)}}
.recent-context{{display:flex;flex-direction:column;justify-content:center;gap:5px;padding:0 14px;border-left:1px solid rgba(255,255,255,.035)}}
.recent-context b{{font-size:13px}}.recent-context span{{font-size:10px;color:var(--soft)}}
.recent-result-score{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;border-left:1px solid rgba(255,255,255,.05)}}
.recent-result-score span{{font-size:10px;font-weight:950;letter-spacing:.08em}}.recent-result-score b{{font-size:19px;font-variant-numeric:tabular-nums}}
.recent-result-score.recent-win{{background:rgba(53,212,154,.22);color:#66e3b3}}.recent-result-score.recent-loss{{background:rgba(255,100,114,.18);color:#ff8b95}}
@media(max-width:720px){{.recent-result{{grid-template-columns:minmax(135px,1.2fr) minmax(95px,.8fr) 88px}}.recent-context{{display:none}}}}

/* V5 */
.home-punchline{{font-size:18px!important;color:#d9e5ef!important;font-weight:700;letter-spacing:-.01em;margin:4px 0 22px!important}}
.project-note{{margin:20px 0 6px;padding:22px 24px;border:1px solid var(--stroke);border-radius:14px;background:linear-gradient(135deg,rgba(21,34,47,.8),rgba(13,22,31,.78))}}
.project-note p{{max-width:860px;color:#aebdcc;line-height:1.7;margin:7px 0 14px}}.project-chips{{display:flex;gap:8px;flex-wrap:wrap}}.project-chips span{{padding:6px 9px;border-radius:999px;border:1px solid var(--stroke);background:rgba(255,255,255,.03);color:#b9c8d6;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.05em}}
.home-section-head>a{{font-size:10px;font-weight:900;color:var(--cyan)!important;letter-spacing:.06em}}
.page-intro{{padding:28px 2px 16px}}.page-intro p{{max-width:720px;color:var(--soft);line-height:1.65}}
.archive-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.archive-match{{min-height:205px;background-size:cover;background-position:center;border:1px solid var(--stroke);border-radius:15px;padding:17px;display:flex;flex-direction:column;justify-content:space-between;color:white!important;transition:.18s ease;box-shadow:0 12px 30px rgba(0,0,0,.18)}}.archive-match:hover{{transform:translateY(-3px);border-color:rgba(57,208,216,.45)}}.archive-meta{{display:flex;justify-content:space-between;font-size:10px;color:#d0dbe5}}.archive-bottom{{display:flex;align-items:end;justify-content:space-between}}.archive-bottom small{{display:block;font-size:9px;color:#9fb0c0;letter-spacing:.12em;font-weight:900}}.archive-bottom strong{{font-size:28px}}.archive-score{{font-size:32px;font-weight:950}}.archive-score span{{color:#8395a6;font-size:17px;margin:0 6px}}
.mkplayer-row{{min-height:58px}}.mkplayer{{display:flex;align-items:center;height:100%;font-size:13px;line-height:1.2;padding-left:2px}}
.weapon-cell{{display:flex;align-items:center;gap:12px;min-height:38px}}.weapon-cell img{{width:58px;height:30px;object-fit:contain;filter:drop-shadow(0 3px 8px rgba(0,0,0,.3))}}.weapon-fallback{{width:58px;text-align:center;color:var(--soft)}}
.mate-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px}}.mate-card{{display:grid;grid-template-columns:44px minmax(0,1fr) 62px 70px;align-items:center;gap:10px;padding:11px;border:1px solid var(--stroke);border-radius:11px;background:rgba(255,255,255,.022);color:var(--text)!important}}.mate-card:hover{{background:rgba(57,208,216,.055);border-color:rgba(57,208,216,.3)}}.mate-avatar{{width:40px;height:40px;border-radius:9px;overflow:hidden;background:var(--surface3);display:grid;place-items:center;font-weight:900}}.mate-avatar img{{width:100%;height:100%;object-fit:cover}}.mate-name{{display:flex;flex-direction:column;gap:4px;min-width:0}}.mate-name span,.mate-record small,.mate-wr small{{font-size:9px;color:var(--soft)}}.mate-record,.mate-wr{{text-align:right}}.mate-record b,.mate-wr b{{display:block;font-size:14px;margin-top:3px}}
.insight-panel{{margin-top:22px!important}}.prototype-badge{{float:right;font-size:9px;color:var(--soft);font-weight:700;text-transform:none;letter-spacing:0}}.insight-grid{{display:flex;flex-wrap:wrap;gap:10px;padding:16px}}.insight-tag{{min-width:180px;max-width:260px;padding:10px 12px;border-radius:9px;border:1px solid;box-shadow:0 7px 18px rgba(0,0,0,.14)}}.insight-tag b{{display:block;font-size:12px;margin-bottom:4px}}.insight-tag span{{font-size:10px;opacity:.87;line-height:1.35}}.insight-tag.positive{{background:rgba(53,212,154,.14);border-color:rgba(53,212,154,.34);color:#7ce9bf}}.insight-tag.neutral{{background:rgba(245,184,75,.13);border-color:rgba(245,184,75,.32);color:#ffd178}}.insight-tag.negative{{background:rgba(255,100,114,.13);border-color:rgba(255,100,114,.32);color:#ff939c}}
@media(max-width:820px){{.archive-grid{{grid-template-columns:1fr}}.mate-grid{{grid-template-columns:1fr}}}}

/* V5.1 — insight hover tooltips */
.insight-grid{{overflow:visible}}
.insight-tag{{position:relative;min-width:auto;max-width:none;padding:9px 12px;cursor:help;outline:none}}
.insight-tag b{{margin:0;font-size:11px;white-space:nowrap}}
.insight-tooltip{{position:absolute;left:50%;bottom:calc(100% + 10px);transform:translate(-50%,6px);min-width:190px;max-width:260px;padding:9px 11px;border-radius:9px;background:#0a1118;border:1px solid var(--stroke);box-shadow:0 12px 28px rgba(0,0,0,.35);color:#dbe7f1;font-size:10px;line-height:1.45;font-weight:650;opacity:0;visibility:hidden;pointer-events:none;transition:.15s ease;z-index:25;text-align:center}}
.insight-tooltip:after{{content:"";position:absolute;left:50%;top:100%;transform:translateX(-50%);border:6px solid transparent;border-top-color:#0a1118}}
.insight-tag:hover .insight-tooltip,.insight-tag:focus .insight-tooltip{{opacity:1;visibility:visible;transform:translate(-50%,0)}}

/* V5.2 — Advanced information hierarchy */
.metric-strip + .insight-panel{{margin-top:14px!important}}
.insight-panel + .panel{{margin-top:16px!important}}

/* V5.2.1 — tooltip overflow fix */
.insight-panel,.insight-panel .section-title,.insight-grid{{overflow:visible!important}}
.insight-tag{{position:relative;z-index:1}}
.insight-tag:hover,.insight-tag:focus{{z-index:50}}
.insight-tooltip{{
  left:50%;
  right:auto;
  width:max-content;
  min-width:180px;
  max-width:min(280px,calc(100vw - 32px));
  white-space:normal;
}}
.insight-grid .insight-tag:first-child .insight-tooltip{{
  left:0;
  transform:translate(0,6px);
}}
.insight-grid .insight-tag:first-child:hover .insight-tooltip,
.insight-grid .insight-tag:first-child:focus .insight-tooltip{{
  transform:translate(0,0);
}}
.insight-grid .insight-tag:first-child .insight-tooltip:after{{
  left:18px;
  transform:none;
}}
.insight-grid .insight-tag:last-child .insight-tooltip{{
  left:auto;
  right:0;
  transform:translate(0,6px);
}}
.insight-grid .insight-tag:last-child:hover .insight-tooltip,
.insight-grid .insight-tag:last-child:focus .insight-tooltip{{
  transform:translate(0,0);
}}
.insight-grid .insight-tag:last-child .insight-tooltip:after{{
  left:auto;
  right:18px;
  transform:none;
}}
</style></head>
<body><nav><a class=brand href="/"><b>THE</b> LOBBY</a><a class=navlink href="/">Home</a><a class=navlink href="/matches">Matches</a><a class=navlink href="/players">Players</a></nav><main>{body}</main></body></html>"""

def overall(con,rid):
    r=con.execute("""SELECT COUNT(*) games,SUM(m.rounds) rounds,SUM(pm.kills) kills,SUM(pm.deaths) deaths,SUM(pm.assists) assists,
      SUM(pm.damage) damage,SUM(pm.score) score,SUM(pm.first_kills) fk,SUM(pm.first_deaths) fd,SUM(pm.headshots) hs,
      SUM(pm.survived) survived,SUM(pm.traded) traded,SUM(pm.kast*m.rounds) kast_weighted,SUM(pm.clutches) clutches,SUM(pm.clutches_lost) clutches_lost,
      SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END) wins,
      SUM(pm.attack_kills) ak,SUM(pm.attack_deaths) ad,SUM(pm.attack_assists) aa,
      SUM(pm.defense_kills) dk,SUM(pm.defense_deaths) dd,SUM(pm.defense_assists) da,
      SUM(pm.attack_first_kills) afk,SUM(pm.attack_first_deaths) afd,
      SUM(pm.defense_first_kills) dfk,SUM(pm.defense_first_deaths) dfd,
      SUM(pm.single_kills) sk,SUM(pm.double_kills) d2,SUM(pm.triple_kills) d3,SUM(pm.quadra_kills) d4,SUM(pm.penta_kills) d5
      FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
      JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id WHERE pm.riot_id=?""",(rid,)).fetchone()
    return r

_WEAPON_ICON_CACHE=None
def simple_datetime(value):
    if not value: return ""
    try:
        from datetime import datetime
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        return dt.strftime("%d/%m/%Y · %H:%M")
    except Exception:
        return value[:16].replace("T"," · ")

def display_name(rid):
    con=connect(DB); r=con.execute("SELECT display_name FROM player_profiles WHERE riot_id=?",(rid,)).fetchone(); con.close()
    return r["display_name"] if r else (rid.split("#",1)[0] if rid else "Unknown")

def player_avatar(rid):
    con=connect(DB)
    p=con.execute("SELECT avatar_path FROM player_profiles WHERE riot_id=?",(rid,)).fetchone()
    if p and p["avatar_path"]:
        con.close(); return p["avatar_path"],"custom"
    row=con.execute("""SELECT pm.agent,pm.agent_image,SUM(m.rounds) r,MAX(m.date_started) last_seen
      FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
      WHERE pm.riot_id=? AND pm.agent_image IS NOT NULL AND pm.agent_image<>''
      GROUP BY pm.agent,pm.agent_image ORDER BY r DESC,last_seen DESC LIMIT 1""",(rid,)).fetchone()
    con.close()
    return (row["agent_image"],"agent") if row and row["agent_image"] else ("","none")

def raw_payload(mid):
    # Turso/serverless source of truth first; local JSON remains a compatible fallback.
    try:
        con=connect(DB)
        row=con.execute("SELECT payload_json FROM raw_matches WHERE match_id=?",(mid,)).fetchone()
        con.close()
        if row and row["payload_json"]:
            return json.loads(row["payload_json"])
    except Exception:
        pass
    p=RAW/(mid+".json")
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return None


def weapon_icons():
    from src.analytics import EXCLUDED_KILL_SOURCES
    global _WEAPON_ICON_CACHE
    if _WEAPON_ICON_CACHE is not None: return _WEAPON_ICON_CACHE
    excluded=set(EXCLUDED_KILL_SOURCES); out={}; payloads=[]
    try:
        con=connect(DB)
        rows=con.execute("SELECT payload_json FROM raw_matches").fetchall()
        con.close()
        payloads=[json.loads(r["payload_json"]) for r in rows if r["payload_json"]]
    except Exception:
        payloads=[]
    if not payloads:
        for p in RAW.glob("*.json"):
            try: payloads.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception: pass
    for payload in payloads:
        for seg in payload.get("data",{}).get("segments",[]):
            if seg.get("type")!="player-round-kills": continue
            md=seg.get("metadata") or {}
            name=md.get("weaponName"); img=md.get("weaponImageUrl")
            if name and name not in excluded and img and name not in out: out[name]=img
    _WEAPON_ICON_CACHE=out
    return out

def matches_page():
    con=connect(DB)
    ms=con.execute("""SELECT m.*,tw.rounds_won ws,tl.rounds_won ls
      FROM matches m LEFT JOIN teams tw ON tw.match_id=m.match_id AND tw.won=1
      LEFT JOIN teams tl ON tl.match_id=m.match_id AND tl.won=0 ORDER BY m.date_started DESC""").fetchall()
    con.close()
    cards=""
    for x in ms:
        img=match_visual(x["match_id"])
        style=("background-image:linear-gradient(180deg,rgba(7,12,18,.08),rgba(7,12,18,.93)),url('%s');"%esc(img)) if img else ""
        cards+=f"""<a class=archive-match href="{match_url(x['match_id'])}" style="{style}">
          <div class=archive-meta><span>{esc((x['date_started'] or '')[:10])}</span><span>{x['rounds']} rounds</span></div>
          <div class=archive-bottom><div><small>MAP</small><strong>{esc(x['map_name'])}</strong></div><div class=archive-score>{x['ws']}<span>:</span>{x['ls']}</div></div></a>"""
    return layout("Matches",f"""<section class=page-intro><div class=eyebrow>MATCH ARCHIVE</div><h1>Matches</h1>
      <p>Toutes les inhouses enregistrées depuis le début. Une game, un scoreboard, ses multikills et son historique.</p></section>
      <section class=archive-grid>{cards}</section>""")

def home():
    con=connect(DB)
    ms=con.execute("""SELECT m.*,tw.rounds_won ws,tl.rounds_won ls
      FROM matches m LEFT JOIN teams tw ON tw.match_id=m.match_id AND tw.won=1
      LEFT JOIN teams tl ON tl.match_id=m.match_id AND tl.won=0 ORDER BY m.date_started DESC LIMIT 4""").fetchall()
    pc=con.execute("SELECT COUNT(*) n FROM player_profiles").fetchone()["n"]
    rounds=con.execute("SELECT COALESCE(SUM(rounds),0) n FROM matches").fetchone()["n"]
    kills=con.execute("SELECT COUNT(*) n FROM kills WHERE killer IS NOT NULL").fetchone()["n"]
    con.close()
    cards=""
    for x in ms:
        img=match_visual(x["match_id"])
        style=("background-image:linear-gradient(180deg,rgba(7,12,18,.12),rgba(7,12,18,.94)),url('%s');"%esc(img)) if img else ""
        cards+=f"""<a class=home-match href="{match_url(x['match_id'])}" style="{style}">
          <div class=home-match-top><span>{esc((x['date_started'] or '')[:10])}</span><span>{x['rounds']} rounds</span></div>
          <div class=home-match-bottom><div><small>MAP</small><strong>{esc(x['map_name'])}</strong></div>
          <div class=home-score><b>{x['ws']}</b><span>:</span><b>{x['ls']}</b></div></div></a>"""
    return layout("Home",f"""<section class=welcome-hero>
      <div class=welcome-copy><div class=eyebrow>{esc(SITE_TAGLINE.upper())}</div><h1>{esc(SITE_NAME)}</h1>
      <p class=home-punchline>Play together. Improve together. Run it back.</p>
      <div class=welcome-actions><a class=discord-cta href="{esc(DISCORD_INVITE)}" target="_blank" rel="noopener">REJOINDRE LE DISCORD ↗</a><a class=secondary-cta href="/players">VOIR LES JOUEURS</a></div></div>
      <div class=welcome-stats><div><b>{pc}</b><span>joueurs</span></div><div><b>{rounds}</b><span>rounds joués</span></div><div><b>{kills}</b><span>kills enregistrés</span></div></div>
      </section>
      <section class=project-note><div class=eyebrow>THE PROJECT</div><p>The Lobby est notre espace privé d’inhouses Valorant : jouer sérieusement sans pression de RR, progresser en équipe, tester des rôles, créer des rivalités et garder une trace de toutes nos games.</p><div class=project-chips><span>10 joueurs</span><span>équipes équilibrées</span><span>BO1</span><span>stats all-time</span></div></section>
      <div class=home-section-head><div><div class=eyebrow>RECENT</div><h2>Derniers matchs</h2></div><a href="/matches">VOIR TOUS LES MATCHS →</a></div>
      <section class=match-card-grid>{cards}</section>""")


def players():
    con=connect(DB); ids=con.execute("SELECT riot_id,display_name,avatar_path FROM player_profiles ORDER BY riot_id").fetchall()
    data=[]
    for p in ids:
        o=overall(con,p["riot_id"]); kd=ratio(o["kills"],o["deaths"]); adr=ratio(o["damage"],o["rounds"]); acs=ratio(o["score"],o["rounds"]); kast=ratio(o["kast_weighted"],o["rounds"]); wr=pct(o["wins"],o["games"])
        data.append((p,o,kd,adr,acs,kast,wr))
    data.sort(key=lambda x:(x[4],x[2]),reverse=True)
    cards=[]
    for rank,(p,o,kd,adr,acs,kast,wr) in enumerate(data,1):
        avatar_src,_=player_avatar(p["riot_id"])
        avatar=(f'<img src="{esc(avatar_src)}" alt="">' if avatar_src else '<span>'+esc(p["display_name"][:1].upper())+'</span>')
        kdclass="vgood" if kd>=1.25 else "good" if kd>=1 else "warnv" if kd>=.8 else "badv"
        kastclass="vgood" if kast>=78 else "good" if kast>=72 else "warnv" if kast>=65 else "badv"
        cards.append(f"""<a class=player-rank-card href="{player_url(p['riot_id'])}">
          <div class=rank-no>#{rank}</div><div class=rank-avatar>{avatar}</div><div class=rank-name><b>{esc(p['display_name'])}</b><span>{o['games']} games · {wr:.0f}% Winrate</span></div>
          <div class=rank-stat><small>ACS</small><b>{acs:.0f}</b></div><div class=rank-stat><small>K:D</small><b class={kdclass}>{kd:.2f}</b></div>
          <div class=rank-stat><small>ADR</small><b>{adr:.1f}</b></div><div class=rank-stat><small>KAST</small><b class={kastclass}>{kast:.0f}%</b></div>
          <div class=rank-stat><small>FK / FD</small><b>{o['fk']} / {o['fd']}</b></div></a>""")
    con.close()
    return layout("Players",f"""<section class=players-hero><div><div class=eyebrow>ALL-TIME DATABASE</div><h1>Players</h1><p>Les performances cumulées de toutes les inhouses archivées. Classement affiché par ACS, avec les métriques principales accessibles d'un coup d'œil.</p></div><div class=players-count><b>{len(data)}</b><span>joueurs enregistrés</span></div></section>
      <div class=leaderboard-head><span>RANKING · ACS</span><span>Cliquer sur un joueur pour ouvrir son profil</span></div><section class=player-rank-list>{''.join(cards)}</section>""")

def player(rid,advanced=False):
    con=connect(DB); prof=con.execute("SELECT * FROM player_profiles WHERE riot_id=?",(rid,)).fetchone()
    if not prof: con.close(); return layout("404","<h1>Joueur introuvable</h1>")
    o=overall(con,rid); games=o["games"]; rounds=o["rounds"]; kd=ratio(o["kills"],o["deaths"]); adr=ratio(o["damage"],rounds); acs=ratio(o["score"],rounds); kast=ratio(o["kast_weighted"],rounds)
    hs_row=con.execute("""SELECT SUM(pm.hs_accuracy*m.rounds) v,SUM(m.rounds) r
      FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id WHERE pm.riot_id=?""",(rid,)).fetchone()
    hs=ratio(hs_row["v"] or 0,hs_row["r"] or 0)
    wr=pct(o["wins"],games); engagement=pct(o["fk"]+o["fd"],rounds); entry=pct(o["fk"],o["fk"]+o["fd"]); fkfd=ratio(o["fk"],o["fd"])
    avatar_src,avatar_kind=player_avatar(rid)
    avatar = f'<img class=avatar src="{esc(avatar_src)}" title="{"Most played agent" if avatar_kind=="agent" else "Player avatar"}">' if avatar_src else '<div class=avatar></div>'
    alias_rows=con.execute("SELECT alias_riot_id FROM player_aliases WHERE canonical_riot_id=? ORDER BY created_at,alias_riot_id",(rid,)).fetchall()
    alias_html=('<div class=aliases><span>aliases:</span> '+", ".join(esc(x["alias_riot_id"]) for x in alias_rows)+'</div>') if alias_rows else ""
    head=f"""<section class=hero><div class=profile-head>{avatar}<div><div class=eyebrow>PLAYER PROFILE</div><h1>{esc(prof['display_name'])}</h1>{alias_html}<div class=muted>{games} inhouses · {wr:.1f}% winrate · {rounds} rounds</div></div></div>
    <div class=stats><div class=stat>ACS<b>{acs:.0f}</b></div><div class=stat>K:D<b>{kd:.2f}</b></div><div class=stat>KAST<b>{kast:.1f}%</b></div><div class=stat>ADR<b>{adr:.1f}</b></div><div class=stat>HS%<b>{hs:.0f}%</b></div><div class=stat>FK:FD<b>{fkfd:.2f}</b></div><div class=stat>Winrate<b>{wr:.0f}%</b></div></div>
    <div class=tabs><a class="{'active' if not advanced else ''}" href="{player_url(rid)}">Overview</a><a class="{'active' if advanced else ''}" href="/advanced?riot={quote(rid,safe='')}">Advanced stats</a></div></section>"""
    if advanced:
        attack_kd=ratio(o["ak"],o["ad"]); defense_kd=ratio(o["dk"],o["dd"])
        multirounds=(o["d2"] or 0)+(o["d3"] or 0)+(o["d4"] or 0)+(o["d5"] or 0)
        from src.analytics import maps as a_maps, weapons as a_weapons, duels as a_duels, economy as a_economy
        econ=a_economy(DB,rid); weapons=a_weapons(DB,rid); duels=a_duels(DB,rid); maps_=a_maps(DB,rid)
        econ_rows="".join(f"<tr><td><b>{esc((x['loadout'] or '').capitalize())}</b></td><td>{x['rounds']}</td><td>{pct(x['wins'],x['rounds']):.0f}%</td><td>{ratio(x['k'],x['d']):.2f}</td><td>{ratio(x['dmg'],x['rounds']):.1f}</td></tr>" for x in econ)
        wicons=weapon_icons()
        weapon_rows="".join(f"<tr><td><div class=weapon-cell>{('<img src='+esc(wicons.get(x['weapon']))+' alt=>') if wicons.get(x['weapon']) else '<span class=weapon-fallback>•</span>'}<b>{esc(x['weapon'])}</b></div></td><td>{x['kills']}</td></tr>" for x in weapons[:14])
        duel_rows="".join(f"<tr><td><b>{esc(x['opponent'])}</b></td><td>{x['kills']}</td><td>{x['deaths']}</td><td>{x['diff']:+d}</td></tr>" for x in duels)
        map_rows="".join(f"<tr><td><b>{esc(x['map_name'])}</b></td><td>{x['games']}</td><td>{x['rounds']}</td><td>{pct(x['wins'],x['games']):.0f}%</td><td>{ratio(x['k'],x['d']):.2f}</td><td>{ratio(x['score'],x['rounds']):.0f}</td><td>{ratio(x['dmg'],x['rounds']):.1f}</td></tr>" for x in maps_)
        body=f"""<div class=grid2>
        <section class="panel adv-panel fc-panel"><div class=section-title>First contact</div><div class=stats style="margin:0;border:0;border-radius:0;grid-template-columns:repeat(3,1fr)">
        <div class=stat>Engagement rate<b>{engagement:.1f}%</b></div>
        <div class=stat>Entry success<b class="{'badv' if entry<25 else 'warnv' if entry<45 else 'good' if entry<65 else 'vgood'}">{entry:.1f}%</b></div>
        <div class=stat>FK : FD<b>{o['fk']} : {o['fd']}</b></div>
        <div class=stat>FK / round<b>{ratio(o['fk'],rounds):.2f}</b></div>
        <div class=stat>Attack FK/FD<b>{ratio(o['afk'],o['afd']):.2f}</b></div>
        <div class=stat>Defense FK/FD<b>{ratio(o['dfk'],o['dfd']):.2f}</b></div>
        </div></section>
        <section class="panel adv-panel combat-panel"><div class=section-title>Combat & impact</div><div class=stats style="margin:0;border:0;border-radius:0;grid-template-columns:repeat(3,1fr)"><div class=stat>Kills<b>{o['kills']}</b></div><div class=stat>Deaths<b>{o['deaths']}</b></div><div class=stat>Assists<b>{o['assists']}</b></div><div class=stat>Attack K:D<b>{attack_kd:.2f}</b></div><div class=stat>Defense K:D<b>{defense_kd:.2f}</b></div><div class=stat>Clutches<b>{o['clutches']}</b></div></div></section></div>
        <section class="panel adv-panel roundimpact-panel"><div class=section-title>Round impact</div><div class=stats style="margin:0;border:0;border-radius:0"><div class=stat>Survived<b>{o['survived']}</b></div><div class=stat>Traded<b>{o['traded']}</b></div><div class=stat>2K rounds<b>{o['d2']}</b></div><div class=stat>3K rounds<b>{o['d3']}</b></div><div class=stat>4K rounds<b>{o['d4']}</b></div><div class=stat>5K rounds<b>{o['d5']}</b></div></div></section>
        <section class=panel><div class=section-title>Economy</div><table><thead><tr><th>Buy</th><th>Rounds</th><th>Winrate</th><th>K:D</th><th>ADR</th></tr></thead><tbody>{econ_rows}</tbody></table></section>
        <div class=grid2>
        <section class=panel><div class=section-title>Weapons</div><table><thead><tr><th>Weapon</th><th>Kills</th></tr></thead><tbody>{weapon_rows}</tbody></table></section>
        </div>
        """
    else:
        agents=con.execute("""SELECT agent,agent_image,COUNT(*) games,SUM(m.rounds) rounds,SUM(pm.kills) k,SUM(pm.deaths) d,SUM(pm.assists) a,SUM(pm.score) score,SUM(pm.damage) damage,SUM(pm.first_kills) fk,SUM(pm.first_deaths) fd,
          SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END) wins FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id WHERE riot_id=? GROUP BY agent,agent_image ORDER BY games DESC,rounds DESC""",(rid,)).fetchall()
        ar="".join(f"""<tr><td><div class=agent>{('<img src='+esc(a['agent_image'])+'>' if a['agent_image'] else '')}<b>{esc(a['agent'])}</b></div></td><td>{a['games']}</td><td>{a['rounds']}</td><td>{pct(a['wins'],a['games']):.0f}%</td><td>{ratio(a['score'],a['rounds']):.0f}</td><td>{ratio(a['k'],a['d']):.2f}</td><td>{ratio(a['damage'],a['rounds']):.1f}</td><td>{ratio(a['fk'],a['fd']):.2f}</td></tr>""" for a in agents)
        recent=con.execute("""SELECT pm.*,m.map_name,m.date_started,t.won,t.rounds_won,opp.rounds_won opp_score FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id JOIN teams opp ON opp.match_id=pm.match_id AND opp.team_id<>pm.team_id WHERE pm.riot_id=? ORDER BY m.date_started DESC""",(rid,)).fetchall()
        rr=""
        for g in recent:
            map_img=match_visual(g["match_id"])
            map_style=("background-image:linear-gradient(180deg,rgba(7,12,18,.05),rgba(7,12,18,.88)),url('%s');"%esc(map_img)) if map_img else ""
            agent_img=('<img src="%s" alt="">%s'%(esc(g["agent_image"]),esc(g["agent"]))) if g["agent_image"] else esc(g["agent"])
            result_class="recent-win" if g["won"] else "recent-loss"
            result_label="W" if g["won"] else "L"
            rr+=f"""<a class=recent-result href="{match_url(g['match_id'])}">
              <div class=recent-map-art style="{map_style}"><b>{esc(g['map_name'])}</b><span>{esc((g['date_started'] or '')[:10])}</span></div>
              <div class=recent-agent-cell>{agent_img}</div>
              <div class=recent-context><b>{g['kills']} / {g['deaths']} / {g['assists']}</b><span>{n(g['acs'],0)} ACS</span></div>
              <div class="recent-result-score {result_class}"><span>{result_label}</span><b>{g['rounds_won']} : {g['opp_score']}</b></div>
            </a>"""
        body=f"""<section class=panel><div class=section-title>Agents · all time</div><table><thead><tr><th>Agent</th><th>Use</th><th>Rnd</th><th>Winrate</th><th>ACS</th><th>K:D</th><th>ADR</th><th>FK:FD</th></tr></thead><tbody>{ar}</tbody></table></section>
        <section class=panel><div class=section-title>Recent inhouses</div><div class=recent-results>{rr}</div></section>"""
    con.close(); return layout(prof["display_name"],head+(player_v3_blocks(rid) if advanced else "")+body)

def match(mid):
    con=connect(DB)
    m=con.execute("SELECT * FROM matches WHERE match_id=?",(mid,)).fetchone()
    if not m: con.close(); return layout("404","<h1>Match introuvable</h1>")
    teams=con.execute("SELECT * FROM teams WHERE match_id=? ORDER BY won DESC,rounds_won DESC",(mid,)).fetchall()
    players=con.execute("""SELECT pm.*,pp.display_name FROM player_matches pm JOIN player_profiles pp ON pp.riot_id=pm.riot_id
      WHERE pm.match_id=? ORDER BY pm.team_id,pm.score DESC""",(mid,)).fetchall()
    con.close()
    byteam={}
    for p in players: byteam.setdefault(p["team_id"],[]).append(p)
    img=match_visual(mid)
    bg=("background-image:linear-gradient(90deg,rgba(8,14,20,.93),rgba(8,14,20,.42),rgba(8,14,20,.84)),url('%s');"%esc(img)) if img else ""
    scorecards=""
    for t in teams:
        scorecards += '<div class="score-side %s"><div class=score-team>%s</div><div class=score-number>%s</div><div class="result-pill %s">%s</div></div>' % ("winner" if t["won"] else "",esc(t["team_id"]),t["rounds_won"],"win" if t["won"] else "loss","WIN" if t["won"] else "LOSS")
    tables=""
    for t in teams:
        rows=""
        for p in byteam.get(t["team_id"],[]):
            rows += '<tr><td class=playercell><a href="/player?riot=%s"><div class=match-player><div class=agent-portrait>%s</div><div class=player-copy><b>%s</b><span>%s</span></div></div></a></td><td><b>%s</b> / %s / %s</td><td>%.0f</td><td>%.1f</td><td>%.0f%%</td><td>%.0f%%</td><td>%s</td><td>%s</td></tr>' % (quote(p["riot_id"]),('<img src="%s" alt="">'%esc(p["agent_image"]) if p["agent_image"] else ''),esc(p["display_name"]),esc(p["agent"] or "—"),p["kills"],p["deaths"],p["assists"],p["acs"],p["adr"],p["kast"],p["hs_accuracy"],p["first_kills"],p["first_deaths"])
        tables += '<section class=panel><div class=team-table-title>%s <span>%s rounds</span></div><div class=table-scroll><table><thead><tr><th>Player</th><th>K / D / A</th><th>ACS</th><th>ADR</th><th>KAST</th><th>HS%%</th><th>FK</th><th>FD</th></tr></thead><tbody>%s</tbody></table></div></section>' % (esc(t["team_id"]),t["rounds_won"],rows)
    body='<section class=match-hero style="%s"><div class=match-kicker>INHOUSE · %s</div><div class=match-score>%s</div><div class=match-meta>%s · %s rounds</div></section>%s%s' % (bg,esc(m["map_name"]),scorecards,esc(simple_datetime(m["date_started"])),m["rounds"],match_tabs(mid,"overview"),tables)
    return layout(str(m["map_name"])+" · Match",body)

def data_audit():
    con=connect(DB)
    tables=["matches","player_profiles","player_matches","player_match_stats","player_rounds","rounds","kills","damage_events","loadout_stats","ability_usage"]
    counts={t:con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    statkeys=con.execute("SELECT COUNT(DISTINCT stat_key) FROM player_match_stats").fetchone()[0]
    con.close()
    cards="".join(f'<div class=stat>{esc(k)}<b>{v}</b></div>' for k,v in counts.items())
    return layout("Data audit",f"""<section class=hero><div class=eyebrow>V2 DATA LAYER</div><h1>Data audit</h1>
    <div class=muted>Avant le redesign : vérification de tout ce qu'on conserve réellement.</div>
    <div class=stats>{cards}<div class=stat>summary stat keys<b>{statkeys}</b></div></div></section>""")


def match_visual(mid):
    payload=raw_payload(mid)
    if not payload: return ""
    return payload.get("data",{}).get("metadata",{}).get("mapImageUrl","") or ""

def match_tabs(mid,active):
    items=[("overview","Overview"),("performance","Performance")]
    return '<div class=matchtabs>'+''.join('<a class="%s" href="/match?id=%s%s">%s</a>' % ("active" if active==k else "",quote(mid),"&tab="+k if k!="overview" else "",label) for k,label in items)+'</div>'

def match_performance(mid):
    from src.analytics import multikills_match
    con=connect(DB); m=con.execute("SELECT * FROM matches WHERE match_id=?",(mid,)).fetchone()
    if not m: con.close(); return layout("404","<h1>Match introuvable</h1>")
    rows=multikills_match(DB,mid); teams={}
    for r in rows: teams.setdefault(r["team_id"],[]).append(r)
    def cell(v,cl):
        v=v or 0
        return '<div class="mkcell %s">%s</div>' % (cl if v else "",v if v else "—")
    blocks=""
    for team,rr in teams.items():
        blocks+='<div class=teamlabel>%s</div><div class="mkgrid mkhead"><div>PLAYER</div><div>2K</div><div>3K</div><div>4K</div><div>5K</div></div>' % esc(team)
        for r in rr:
            blocks+='<div class=mkgrid><div class=mkplayer><a href="/player?riot=%s">%s</a></div>%s%s%s%s</div>' % (quote(r["riot_id"]),esc(display_name(r["riot_id"])),cell(r["k2"],"on2"),cell(r["k3"],"on3"),cell(r["k4"],"on4"),cell(r["k5"],"on5"))
    con.close()
    body='<section class=hero><div class=eyebrow>PERFORMANCE · MATCH ONLY</div><h1>%s</h1><div class=muted>%s · %s rounds</div></section>%s<div class=qol-note>Les valeurs ci-dessous concernent uniquement ce match, pas les statistiques all-time.</div><section class=panel><div class=section-title>Multi-kills · ce match uniquement</div>%s</section>' % (esc(m["map_name"]),esc(simple_datetime(m["date_started"])),m["rounds"],match_tabs(mid,"performance"),blocks)
    return layout(str(m["map_name"])+" · Performance",body)

def player_v3_blocks(rid):
    from src.analytics import multikills_alltime,overall as analytics_overall,teammates,duels,maps as a_maps,playstyle_tags
    mk=multikills_alltime(DB,rid); o=analytics_overall(DB,rid); mates=teammates(DB,rid); hh=duels(DB,rid); maps_=a_maps(DB,rid)
    fc=o.get("fc_rate",0); success=o.get("fc_success",0); kd=o.get("kd",0); adr=o.get("adr",0)
    def pc(v,kind):
        if kind=="success": return "badv" if v<25 else "warnv" if v<45 else "good" if v<65 else "vgood"
        if kind=="kd": return "badv" if v<.8 else "warnv" if v<1 else "good" if v<1.25 else "vgood"
        if kind=="adr": return "badv" if v<110 else "warnv" if v<135 else "good" if v<165 else "vgood"
        return ""
    strip='<div class=metric-strip><div class=metric><small>First contact rate</small><b>%.1f%%</b></div><div class=metric><small>First contact success</small><b class=%s>%.1f%%</b></div><div class=metric><small>K/D</small><b class=%s>%.2f</b></div><div class=metric><small>ADR</small><b class=%s>%.1f</b></div></div>' % (fc,pc(success,"success"),success,pc(kd,"kd"),kd,pc(adr,"adr"),adr)

    mh='<section class=panel><div class=section-title>Multi-kills · all time</div><div class="mkgrid mkhead"><div></div><div>2K</div><div>3K</div><div>4K</div><div>5K</div></div><div class="mkgrid mkplayer-row"><div class=mkplayer>%s</div><div class="mkcell on2">%s</div><div class="mkcell on3">%s</div><div class="mkcell on4">%s</div><div class="mkcell on5">%s</div></div></section>' % (esc(display_name(rid)),mk["k2"] or "—",mk["k3"] or "—",mk["k4"] or "—",mk["k5"] or "—")

    hrows=""
    for x in hh:
        dc="diff-pos" if x["diff"]>0 else "diff-neg" if x["diff"]<0 else "diff-zero"
        hrows+='<tr><td><a href="/player?riot=%s">%s</a></td><td>%s</td><td>%s</td><td class=%s>%+d</td></tr>'%(quote(x["opponent"]),esc(display_name(x["opponent"])),x["kills"],x["deaths"],dc,x["diff"])
    h2h='<section class=panel><div class=section-title>Head-to-head</div><table><thead><tr><th>Opponent</th><th>Kills</th><th>Deaths</th><th>+/-</th></tr></thead><tbody>%s</tbody></table></section>'%hrows

    def map_thumb(name):
        c=connect(DB); r=c.execute("SELECT match_id FROM matches WHERE map_name=? ORDER BY date_started DESC LIMIT 1",(name,)).fetchone(); c.close()
        return match_visual(r["match_id"]) if r else ""
    mrows=""
    for x in maps_:
        thumb=map_thumb(x["map_name"])
        visual=('<img class=map-thumb src="%s" alt="">'%esc(thumb)) if thumb else '<div class=map-thumb-fallback></div>'
        mrows+='<tr><td><div class=map-cell>%s<div><b>%s</b><small>%s games</small></div></div></td><td>%.0f%%</td><td>%.2f</td><td>%.0f</td><td>%.1f</td></tr>'%(visual,esc(x["map_name"]),x["games"],100*x["wins"]/x["games"] if x["games"] else 0,x["k"]/x["d"] if x["d"] else x["k"],x["score"]/x["rounds"] if x["rounds"] else 0,x["dmg"]/x["rounds"] if x["rounds"] else 0)
    maphtml='<section class=panel><div class=section-title>Maps</div><table><thead><tr><th>Map</th><th>Winrate</th><th>K/D</th><th>ACS</th><th>ADR</th></tr></thead><tbody>%s</tbody></table></section>'%mrows

    mate_rows=""
    for x in mates:
        av,_=player_avatar(x["teammate"])
        avh=('<img src="%s" alt="">'%esc(av)) if av else '<span>'+esc(display_name(x["teammate"])[:1])+'</span>'
        mate_rows+='<a class=mate-card href="/player?riot=%s"><div class=mate-avatar>%s</div><div class=mate-name><b>%s</b><span>%s games together</span></div><div class=mate-record><small>W-L</small><b>%s-%s</b></div><div class=mate-wr><small>Winrate</small><b>%.0f%%</b></div></a>'%(quote(x["teammate"]),avh,esc(display_name(x["teammate"])),x["games"],x["wins"],x["games"]-x["wins"],100*x["wins"]/x["games"] if x["games"] else 0)
    mateshtml='<section class=panel><div class=section-title>Teammates</div><div class=mate-grid>%s</div></section>'%mate_rows

    tags=playstyle_tags(DB,rid)
    tags_html=""
    if tags:
        pills="".join('<div class="insight-tag %s" tabindex="0"><b>%s</b><div class=insight-tooltip>%s</div></div>'%(t["tone"],esc(t["name"]),esc(t["description"])) for t in tags)
        tags_html='<section class="panel insight-panel"><div class=section-title>Playstyle insights <span class=prototype-badge>3+ games</span></div><div class=insight-grid>%s</div></section>'%pills

    return strip+tags_html+mh+'<div class=grid2>'+h2h+maphtml+'</div>'+mateshtml


def import_page(msg=""):
    note=f'<div class=notice>{esc(msg)}</div>' if msg else ""
    return layout("Import",f"""<section class=hero><div class=eyebrow>ADD TO DATABASE</div><h1>Import an inhouse</h1>
    <div class=muted>Le JSON est la méthode fiable actuelle. L'import par ID reste expérimental tant que Tracker renvoie son challenge Cloudflare hors navigateur.</div>{note}</section>
    <section class=panel><div class=section-title>1 · Import JSON — recommandé</div>
      <div style="padding:18px"><input id=jsonfile type=file accept=".json,.txt,application/json">
      <button id=jsonbtn style="margin-left:8px">IMPORT JSON</button><div id=jsonstatus class=muted style="margin-top:10px">Sélectionne le fichier Response exporté depuis DevTools.</div></div>
    </section>
    <section class=panel><div class=section-title>2 · Match ID — expérimental</div>
      <form class=import method=post action="/admin/import-id" style="padding:18px;margin:0">
      <input name=match_id placeholder="56df5ec9-259a-41e5-a5a5-261ce7afd3e8" required><button>TRY MATCH ID</button></form>
    </section>
<script>
document.getElementById('jsonbtn').onclick=async()=>{{const f=document.getElementById('jsonfile').files[0];
 const st=document.getElementById('jsonstatus'); if(!f){{st.textContent='Choisis un JSON.';return}}
 st.textContent='Import en cours…';
 try{{const r=await fetch('/admin/import-json',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:await f.text()}});
 if(r.redirected){{location.href=r.url;return}} st.textContent=await r.text();}}
 catch(e){{st.textContent='Erreur: '+e;}}
}};
</script>""")


def admin_configured():
    return bool(ADMIN_USER and ADMIN_PASSWORD)

def valid_admin_header(header):
    if not admin_configured() or not header or not header.startswith("Basic "):
        return False
    try:
        decoded=base64.b64decode(header[6:]).decode("utf-8")
        user,password=decoded.split(":",1)
        return hmac.compare_digest(user,ADMIN_USER) and hmac.compare_digest(password,ADMIN_PASSWORD)
    except Exception:
        return False

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)


def admin_denied():
    return PlainTextResponse(
        "Authentication required.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="The Lobby Admin"'},
    )


def is_admin(request: Request):
    return valid_admin_header(request.headers.get("authorization"))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="same-origin"
    return response


def page(content,status=200):
    return HTMLResponse(content,status_code=status)


@app.get("/health")
def health():
    return PlainTextResponse("ok")


@app.get("/")
def route_home():
    try: return page(home())
    except Exception:
        traceback.print_exc(); return page(layout("Erreur","<section class=hero><h1>Erreur serveur</h1><div class=muted>Une erreur inattendue est survenue.</div></section>"),500)


@app.get("/matches")
def route_matches():
    try: return page(matches_page())
    except Exception:
        traceback.print_exc(); return page(layout("Erreur","<section class=hero><h1>Erreur serveur</h1></section>"),500)


@app.get("/players")
def route_players():
    try: return page(players())
    except Exception:
        traceback.print_exc(); return page(layout("Erreur","<section class=hero><h1>Erreur serveur</h1></section>"),500)


@app.get("/player")
def route_player(riot: str=""):
    try: return page(player(riot))
    except Exception:
        traceback.print_exc(); return page(layout("Erreur","<section class=hero><h1>Erreur serveur</h1></section>"),500)


@app.get("/advanced")
def route_advanced(riot: str=""):
    try: return page(player(riot,True))
    except Exception:
        traceback.print_exc(); return page(layout("Erreur","<section class=hero><h1>Erreur serveur</h1></section>"),500)


@app.get("/match")
def route_match(id: str="", tab: str="overview"):
    try:
        return page(match_performance(id) if tab=="performance" else match(id))
    except Exception:
        traceback.print_exc(); return page(layout("Erreur","<section class=hero><h1>Erreur serveur</h1></section>"),500)


@app.get("/admin/import")
def route_admin_import(request: Request, msg: str=""):
    if not is_admin(request): return admin_denied()
    return page(import_page(msg))


@app.get("/admin/data-audit")
def route_admin_audit(request: Request):
    if not is_admin(request): return admin_denied()
    return page(data_audit())


@app.post("/admin/import-id")
async def route_import_id(request: Request):
    if not is_admin(request): return admin_denied()
    try:
        body=await request.body()
        if len(body)>MAX_IMPORT_BYTES: return PlainTextResponse("payload too large",status_code=413)
        mid=parse_qs(body.decode()).get("match_id",[""])[0].strip()
        payload=fetch_tracker(mid)
        got,_=import_payload(payload,DB,RAW)
        return RedirectResponse(match_url(got),status_code=303)
    except Exception as e:
        return RedirectResponse("/admin/import?msg="+quote(str(e),safe=""),status_code=303)


@app.post("/admin/import-json")
async def route_import_json(request: Request):
    if not is_admin(request): return admin_denied()
    try:
        body=await request.body()
        if len(body)>MAX_IMPORT_BYTES: return PlainTextResponse("payload too large",status_code=413)
        payload=json.loads(body.decode("utf-8"))
        mid,_=import_payload(payload,DB,RAW)
        return RedirectResponse(match_url(mid),status_code=303)
    except Exception as e:
        return RedirectResponse("/admin/import?msg="+quote(str(e),safe=""),status_code=303)


if __name__=="__main__":
    if not admin_configured():
        print("[warning] ADMIN_USER / ADMIN_PASSWORD are not configured; admin routes remain locked.")
    import uvicorn
    print(f"{SITE_NAME} -> http://127.0.0.1:{PORT}")
    uvicorn.run(app,host=HOST,port=PORT)
