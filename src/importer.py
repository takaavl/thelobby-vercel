
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


def _bulk_insert(con, prefix, rows, cols_per_row, max_params=720):
    """Insert rows in multi-value chunks to minimize remote DB round trips."""
    if not rows:
        return
    chunk_size=max(1,max_params//cols_per_row)
    row_q="("+",".join("?" for _ in range(cols_per_row))+")"
    for i in range(0,len(rows),chunk_size):
        chunk=rows[i:i+chunk_size]
        sql=prefix+" VALUES "+",".join(row_q for _ in chunk)
        params=tuple(v for row in chunk for v in row)
        con.execute(sql,params)

def _purge_match(con, mid):
    """Remove a previous interrupted import of this exact match."""
    # Child/event tables first; explicit deletes work both locally and remotely.
    for table in (
        "ability_usage","player_match_stats","loadout_stats","damage_events","kills",
        "player_rounds","rounds","player_matches","teams","raw_matches","matches"
    ):
        con.execute(f"DELETE FROM {table} WHERE match_id=?",(mid,))
    con.execute("DELETE FROM import_status WHERE match_id=?",(mid,))

def import_payload(payload,db_path,raw_dir):
    data=payload.get("data",payload)
    if "attributes" not in data or "segments" not in data:
        raise ValueError("Ce fichier ne ressemble pas à une réponse de match Tracker.")

    mid=data["attributes"]["id"]
    segs=data["segments"]
    meta=data.get("metadata",{})

    init(db_path)
    con=connect(db_path)

    try:
        # A completed import is a real duplicate. An interrupted one is cleaned and retried.
        status=con.execute("SELECT status FROM import_status WHERE match_id=?",(mid,)).fetchone()
        exists=con.execute("SELECT 1 FROM matches WHERE match_id=?",(mid,)).fetchone()
        if exists and status and status["status"]=="complete":
            return mid,False
        if exists or status:
            _purge_match(con,mid)
            con.commit()

        con.execute(
            "INSERT OR REPLACE INTO import_status(match_id,status,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
            (mid,"importing")
        )

        # Preload aliases once: no SELECT-per-segment over the network.
        alias_map={}
        try:
            for r in con.execute("SELECT alias_riot_id,canonical_riot_id FROM player_aliases"):
                alias_map[r["alias_riot_id"]]=r["canonical_riot_id"]
        except Exception:
            pass

        def canonical(rid):
            return alias_map.get(rid,rid) if rid else rid

        # First discover every player identity in the payload so all later event rows can
        # normalize through one in-memory map.
        profile_rows=[]
        alias_rows=[]
        seen_profiles=set()
        seen_aliases=set()
        for seg in segs:
            if seg.get("type")!="player-summary":
                continue
            a=seg.get("attributes",{})
            source_rid=a.get("platformUserIdentifier")
            if not source_rid:
                continue
            rid=alias_map.get(source_rid,source_rid)
            alias_map[source_rid]=rid
            if rid not in seen_profiles:
                profile_rows.append((rid,rid.split("#",1)[0] if rid else "Unknown"))
                seen_profiles.add(rid)
            if source_rid not in seen_aliases:
                alias_rows.append((source_rid,rid))
                seen_aliases.add(source_rid)

        _bulk_insert(con,
            "INSERT OR IGNORE INTO player_profiles(riot_id,display_name)",
            profile_rows,2)
        _bulk_insert(con,
            "INSERT OR IGNORE INTO player_aliases(alias_riot_id,canonical_riot_id)",
            alias_rows,2)

        # Immutable source of truth. Remote mode stores it in Turso; local mode also
        # keeps the original JSON file on disk.
        payload_json=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
        con.execute(
            "INSERT OR REPLACE INTO raw_matches(match_id,payload_json) VALUES(?,?)",
            (mid,payload_json)
        )
        if not using_turso():
            raw_dir.mkdir(parents=True,exist_ok=True)
            (raw_dir/f"{mid}.json").write_text(
                json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"
            )

        con.execute(
            "INSERT INTO matches(match_id,map_name,date_started,duration_ms,rounds,is_ranked) VALUES(?,?,?,?,?,?)",
            (mid,meta.get("mapName"),meta.get("dateStarted"),meta.get("duration"),
             meta.get("rounds"),int(bool(meta.get("isRanked"))))
        )

        teams=[]
        player_matches=[]
        player_stats=[]
        ability_usage=[]
        player_rounds=[]
        rounds=[]
        kills=[]
        damage=[]
        loadouts=[]

        for seg in segs:
            typ=seg.get("type")
            a=seg.get("attributes",{})
            md=seg.get("metadata",{})
            st=seg.get("stats",{})

            if typ=="team-summary":
                teams.append((
                    mid,a.get("teamId"),int(bool(md.get("hasWon"))),
                    value(st,"roundsWon"),value(st,"roundsLost"),value(st,"kills"),
                    value(st,"deaths"),value(st,"assists"),value(st,"damage")
                ))

            elif typ=="player-summary":
                source_rid=a.get("platformUserIdentifier")
                rid=canonical(source_rid)
                cols=(
                    mid,rid,md.get("teamId"),md.get("agentName"),md.get("agentImageUrl"),
                    md.get("accountLevel"),value(st,"placement"),value(st,"score"),
                    value(st,"scorePerRound"),value(st,"kills"),value(st,"deaths"),
                    value(st,"assists"),value(st,"damage"),value(st,"damagePerRound"),
                    value(st,"damageReceived"),value(st,"damageDeltaPerRound"),
                    value(st,"firstKills"),value(st,"firstDeaths"),value(st,"esr"),
                    value(st,"headshots"),value(st,"hsAccuracy"),value(st,"survived"),
                    value(st,"traded"),value(st,"kast"),value(st,"clutches"),
                    value(st,"clutchesLost"),value(st,"singleKills"),value(st,"doubleKills"),
                    value(st,"tripleKills"),value(st,"quadraKills"),value(st,"pentaKills"),
                    value(st,"plants"),value(st,"defuses"),value(st,"attackKills"),
                    value(st,"attackDeaths"),value(st,"attackAssists"),
                    value(st,"attackDamagePerRound"),value(st,"attackKast"),
                    value(st,"attackFirstKills"),value(st,"attackFirstDeaths"),
                    value(st,"defenseKills"),value(st,"defenseDeaths"),
                    value(st,"defenseAssists"),value(st,"defenseDamagePerRound"),
                    value(st,"defenseKast"),value(st,"defenseFirstKills"),
                    value(st,"defenseFirstDeaths"),
                    json.dumps(md.get("tags") or [],ensure_ascii=False)
                )
                player_matches.append(cols)

                for key,obj in st.items():
                    if isinstance(obj,dict):
                        raw=obj.get("value")
                        num=float(raw) if isinstance(raw,(int,float)) else None
                        player_stats.append(
                            (mid,rid,key,num,str(obj.get("displayValue","")))
                        )
                        if "cast" in key.lower() and isinstance(raw,(int,float)):
                            ability_usage.append((mid,rid,key,int(raw)))

            elif typ=="player-round":
                rid=canonical(a.get("platformUserIdentifier"))
                player_rounds.append((
                    mid,a.get("round"),rid,md.get("teamSide"),value(st,"score"),
                    value(st,"kills"),value(st,"deaths"),value(st,"assists"),
                    value(st,"damage"),value(st,"loadoutValue"),
                    value(st,"remainingCredits"),value(st,"spentCredits")
                ))

            elif typ=="round-summary":
                plant=md.get("plant") or {}
                de=md.get("defuse") or {}
                rounds.append((
                    mid,a.get("round"),value(st,"winningTeam"),value(st,"roundResult"),
                    canonical(plant.get("platformUserIdentifier")),plant.get("site"),
                    plant.get("roundTime"),canonical(de.get("platformUserIdentifier"))
                ))

            elif typ=="player-round-kills":
                kills.append((
                    mid,a.get("round"),canonical(a.get("platformUserIdentifier")),
                    canonical(a.get("opponentPlatformUserIdentifier")),
                    md.get("weaponName"),md.get("weaponCategory"),md.get("roundTime"),
                    md.get("gameTime"),
                    json.dumps(md.get("assistants") or [],ensure_ascii=False)
                ))

            elif typ=="player-round-damage":
                damage.append((
                    mid,a.get("round"),canonical(a.get("platformUserIdentifier")),
                    canonical(a.get("opponentPlatformUserIdentifier")),value(st,"damage"),
                    value(st,"headshots"),value(st,"bodyshots"),value(st,"legshots")
                ))

            elif typ=="player-loadout":
                loadouts.append((
                    mid,canonical(a.get("platformUserIdentifier")),a.get("loadout"),
                    value(st,"roundsPlayed"),value(st,"roundsWon"),value(st,"kills"),
                    value(st,"deaths"),value(st,"assists"),value(st,"damage"),
                    value(st,"damagePerRound"),value(st,"scorePerRound"),value(st,"kAST"),
                    value(st,"firstBloods"),value(st,"firstDeaths")
                ))

        _bulk_insert(con,"INSERT INTO teams",teams,9)
        _bulk_insert(con,
            """INSERT INTO player_matches(
            match_id,riot_id,team_id,agent,agent_image,account_level,placement,score,acs,
            kills,deaths,assists,damage,adr,damage_received,dd_delta_round,first_kills,
            first_deaths,esr,headshots,hs_accuracy,survived,traded,kast,clutches,
            clutches_lost,single_kills,double_kills,triple_kills,quadra_kills,penta_kills,
            plants,defuses,attack_kills,attack_deaths,attack_assists,attack_adr,attack_kast,
            attack_first_kills,attack_first_deaths,defense_kills,defense_deaths,
            defense_assists,defense_adr,defense_kast,defense_first_kills,
            defense_first_deaths,tags_json)""",
            player_matches,48)
        _bulk_insert(con,"INSERT OR REPLACE INTO player_match_stats",player_stats,5)
        _bulk_insert(con,"INSERT OR REPLACE INTO ability_usage",ability_usage,4)
        _bulk_insert(con,
            """INSERT OR REPLACE INTO player_rounds(
            match_id,round_no,riot_id,side,score,kills,deaths,assists,damage,
            loadout_value,remaining_credits,spent_credits)""",
            player_rounds,12)
        _bulk_insert(con,"INSERT INTO rounds",rounds,8)
        _bulk_insert(con,
            """INSERT INTO kills(
            match_id,round_no,killer,victim,weapon,weapon_category,round_time,game_time,
            assistants_json)""",
            kills,9)
        _bulk_insert(con,
            """INSERT INTO damage_events(
            match_id,round_no,attacker,target,damage,headshots,bodyshots,legshots)""",
            damage,8)
        _bulk_insert(con,"INSERT INTO loadout_stats",loadouts,14)

        con.execute(
            "UPDATE import_status SET status='complete',updated_at=CURRENT_TIMESTAMP WHERE match_id=?",
            (mid,)
        )
        con.commit()
        return mid,True

    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()

def import_file(path,db_path,raw_dir):
    return import_payload(json.loads(Path(path).read_text(encoding="utf-8")),db_path,raw_dir)
