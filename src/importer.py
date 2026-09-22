
import json, shutil, urllib.request, urllib.error
from pathlib import Path
from .db import connect, init, using_turso

def value(stats,key,default=None):
    v=stats.get(key)
    return default if not isinstance(v,dict) else v.get("value",default)

def fetch_tracker(match_id):
    # Intentionally ordinary HTTP only. If Tracker/Cloudflare refuses it, caller gets a clean fallback message.
    url=f"https://api.tracker.gg/api/v2/valorant/standard/matches/{match_id}"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            body=r.read()
            ctype=r.headers.get("content-type","")
        if b"<!DOCTYPE html" in body[:200] or "json" not in ctype.lower():
            raise RuntimeError("Tracker a renvoyé son challenge Cloudflare au lieu du JSON.")
        return json.loads(body)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Tracker refuse l'import direct (HTTP {e.code}). Utilise l'import JSON pour l'instant.")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Impossible de joindre Tracker: {e.reason}")

def import_payload(payload,db_path,raw_dir):
    data=payload.get("data",payload)
    if "attributes" not in data or "segments" not in data:
        raise ValueError("Ce fichier ne ressemble pas à une réponse de match Tracker.")
    mid=data["attributes"]["id"]; segs=data["segments"]; meta=data.get("metadata",{})
    init(db_path); con=connect(db_path)
    def canonical(rid):
        if not rid: return rid
        row=con.execute("SELECT canonical_riot_id FROM player_aliases WHERE alias_riot_id=?",(rid,)).fetchone()
        return row["canonical_riot_id"] if row else rid
    if con.execute("SELECT 1 FROM matches WHERE match_id=?",(mid,)).fetchone():
        con.close(); return mid,False

    # Immutable source of truth. On Vercel/Turso it lives in the database itself;
    # locally we also keep the historical JSON file exactly like the original app.
    payload_json=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    con.execute("INSERT OR IGNORE INTO raw_matches(match_id,payload_json) VALUES(?,?)",(mid,payload_json))
    if not using_turso():
        raw_dir.mkdir(parents=True,exist_ok=True)
        (raw_dir/f"{mid}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    con.execute("INSERT INTO matches(match_id,map_name,date_started,duration_ms,rounds,is_ranked) VALUES(?,?,?,?,?,?)",
                (mid,meta.get("mapName"),meta.get("dateStarted"),meta.get("duration"),meta.get("rounds"),int(bool(meta.get("isRanked")))))
    for s in segs:
        typ=s.get("type"); a=s.get("attributes",{}); md=s.get("metadata",{}); st=s.get("stats",{})
        if typ=="team-summary":
            con.execute("INSERT INTO teams VALUES(?,?,?,?,?,?,?,?,?)",(mid,a.get("teamId"),int(bool(md.get("hasWon"))),
                value(st,"roundsWon"),value(st,"roundsLost"),value(st,"kills"),value(st,"deaths"),value(st,"assists"),value(st,"damage")))
        elif typ=="player-summary":
            source_rid=a.get("platformUserIdentifier")
            rid=canonical(source_rid)
            default_name=(rid.split("#",1)[0] if rid else "Unknown")
            con.execute("INSERT OR IGNORE INTO player_profiles(riot_id,display_name) VALUES(?,?)",(rid,default_name))
            con.execute("INSERT OR IGNORE INTO player_aliases(alias_riot_id,canonical_riot_id) VALUES(?,?)",(source_rid,rid))
            cols = {
              "match_id":mid,"riot_id":rid,"team_id":md.get("teamId"),"agent":md.get("agentName"),
              "agent_image":md.get("agentImageUrl"),"account_level":md.get("accountLevel"),
              "placement":value(st,"placement"),"score":value(st,"score"),"acs":value(st,"scorePerRound"),
              "kills":value(st,"kills"),"deaths":value(st,"deaths"),"assists":value(st,"assists"),
              "damage":value(st,"damage"),"adr":value(st,"damagePerRound"),"damage_received":value(st,"damageReceived"),
              "dd_delta_round":value(st,"damageDeltaPerRound"),"first_kills":value(st,"firstKills"),"first_deaths":value(st,"firstDeaths"),
              "esr":value(st,"esr"),"headshots":value(st,"headshots"),"hs_accuracy":value(st,"hsAccuracy"),
              "survived":value(st,"survived"),"traded":value(st,"traded"),"kast":value(st,"kast"),
              "clutches":value(st,"clutches"),"clutches_lost":value(st,"clutchesLost"),
              "single_kills":value(st,"singleKills"),"double_kills":value(st,"doubleKills"),"triple_kills":value(st,"tripleKills"),
              "quadra_kills":value(st,"quadraKills"),"penta_kills":value(st,"pentaKills"),"plants":value(st,"plants"),"defuses":value(st,"defuses"),
              "attack_kills":value(st,"attackKills"),"attack_deaths":value(st,"attackDeaths"),"attack_assists":value(st,"attackAssists"),
              "attack_adr":value(st,"attackDamagePerRound"),"attack_kast":value(st,"attackKast"),
              "attack_first_kills":value(st,"attackFirstKills"),"attack_first_deaths":value(st,"attackFirstDeaths"),
              "defense_kills":value(st,"defenseKills"),"defense_deaths":value(st,"defenseDeaths"),"defense_assists":value(st,"defenseAssists"),
              "defense_adr":value(st,"defenseDamagePerRound"),"defense_kast":value(st,"defenseKast"),
              "defense_first_kills":value(st,"defenseFirstKills"),"defense_first_deaths":value(st,"defenseFirstDeaths"),
              "tags_json":json.dumps(md.get("tags") or [],ensure_ascii=False)
            }
            names=",".join(cols); qs=",".join("?" for _ in cols)
            con.execute(f"INSERT INTO player_matches({names}) VALUES({qs})",tuple(cols.values()))
            # Preserve every numeric player-summary stat, including fields not yet surfaced by the UI.
            for key,obj in st.items():
                if isinstance(obj,dict):
                    raw=obj.get("value")
                    num=float(raw) if isinstance(raw,(int,float)) else None
                    con.execute("INSERT OR REPLACE INTO player_match_stats VALUES(?,?,?,?,?)",
                                (mid,rid,key,num,str(obj.get("displayValue",""))))
            # Ability casts: Tracker keys vary by agent, so keep any cast-like summary field generically.
            for key,obj in st.items():
                if isinstance(obj,dict) and "cast" in key.lower() and isinstance(obj.get("value"),(int,float)):
                    con.execute("INSERT OR REPLACE INTO ability_usage VALUES(?,?,?,?)",(mid,rid,key,int(obj["value"])))
        elif typ=="player-round":
            rid=canonical(a.get("platformUserIdentifier"))
            side=md.get("teamSide")
            con.execute("""INSERT OR REPLACE INTO player_rounds
              (match_id,round_no,riot_id,side,score,kills,deaths,assists,damage,loadout_value,remaining_credits,spent_credits)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
              (mid,a.get("round"),rid,side,value(st,"score"),value(st,"kills"),value(st,"deaths"),value(st,"assists"),
               value(st,"damage"),value(st,"loadoutValue"),value(st,"remainingCredits"),value(st,"spentCredits")))
        elif typ=="round-summary":
            plant=md.get("plant") or {}; de=md.get("defuse") or {}
            con.execute("INSERT INTO rounds VALUES(?,?,?,?,?,?,?,?)",(mid,a.get("round"),value(st,"winningTeam"),value(st,"roundResult"),
                canonical(plant.get("platformUserIdentifier")),plant.get("site"),plant.get("roundTime"),canonical(de.get("platformUserIdentifier"))))
        elif typ=="player-round-kills":
            con.execute("""INSERT INTO kills(match_id,round_no,killer,victim,weapon,weapon_category,round_time,game_time,assistants_json)
                           VALUES(?,?,?,?,?,?,?,?,?)""",(mid,a.get("round"),canonical(a.get("platformUserIdentifier")),canonical(a.get("opponentPlatformUserIdentifier")),
                           md.get("weaponName"),md.get("weaponCategory"),md.get("roundTime"),md.get("gameTime"),
                           json.dumps(md.get("assistants") or [],ensure_ascii=False)))
        elif typ=="player-round-damage":
            con.execute("""INSERT INTO damage_events(match_id,round_no,attacker,target,damage,headshots,bodyshots,legshots)
                           VALUES(?,?,?,?,?,?,?,?)""",(mid,a.get("round"),canonical(a.get("platformUserIdentifier")),canonical(a.get("opponentPlatformUserIdentifier")),
                           value(st,"damage"),value(st,"headshots"),value(st,"bodyshots"),value(st,"legshots")))
        elif typ=="player-loadout":
            con.execute("""INSERT INTO loadout_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(mid,canonical(a.get("platformUserIdentifier")),a.get("loadout"),
                           value(st,"roundsPlayed"),value(st,"roundsWon"),value(st,"kills"),value(st,"deaths"),value(st,"assists"),
                           value(st,"damage"),value(st,"damagePerRound"),value(st,"scorePerRound"),value(st,"kAST"),
                           value(st,"firstBloods"),value(st,"firstDeaths")))
    con.commit(); con.close()
    return mid,True

def import_file(path,db_path,raw_dir):
    return import_payload(json.loads(Path(path).read_text(encoding="utf-8")),db_path,raw_dir)
