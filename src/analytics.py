import json
import statistics

from .db import connect

STANDARD_WEAPONS = (
    "Classic","Shorty","Frenzy","Ghost","Sheriff",
    "Stinger","Spectre",
    "Bucky","Judge",
    "Bulldog","Guardian","Phantom","Vandal",
    "Marshal","Outlaw","Operator",
    "Ares","Odin"
)

EXCLUDED_KILL_SOURCES = ("Fall","Bomb")

AGENT_SIGNATURE_TITLES = {
    "Astra": "Astro Guardian",
    "Brimstone": "Protocol's Captain",
    "Chamber": "Weapon Designer",
    "Clove": "Second Life",
    "Fade": "Dream Eater",
    "Gekko": "Globule's Friend",
    "Harbor": "Ocean Vanguard",
    "Iso": "Chinese Hitman",
    "Jett": "Swift Storm",
    "KAY/O": "CLAN/KER",
    "Killjoy": "German Genius",
    "Miks": "Disc Jockey",
    "Neon": "Bioelectric Speed",
    "Omen": "Shadow Hunter",
    "Phoenix": "Hothead",
    "Raze": "Boomzinho",
    "Reyna": "Life Reaver",
    "Sage": "Life Warden",
    "Skye": "Nature's Wrath",
    "Sova": "Deadeye",
    "Tejo": "Hermano",
    "Veto": "Evolved Mutant",
    "Viper": "Biohazard",
    "Vyse": "Steel Thorn",
    "Waylay": "Prismatic",
    "Yoru": "Riftwalker",
}

def _weapon_sql_placeholders():
    return ",".join("?" for _ in STANDARD_WEAPONS)

def safe(a,b): return 0 if not b else a/b
def pct(a,b): return 100*safe(a,b)

def overall(db, riot):
    c=connect(db)
    x=c.execute("""SELECT COUNT(*) games,SUM(m.rounds) rounds,SUM(pm.kills) k,SUM(pm.deaths) d,SUM(pm.assists) a,
      SUM(pm.damage) dmg,SUM(pm.score) score,SUM(pm.first_kills) fk,SUM(pm.first_deaths) fd,SUM(pm.headshots) hs,
      SUM(pm.survived) survived,SUM(pm.traded) traded,SUM(pm.clutches) clutches,
      SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END) wins
      FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
      JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id WHERE pm.riot_id=?""",(riot,)).fetchone()
    c.close()
    return dict(x)|{"wr":pct(x["wins"],x["games"]),"kd":safe(x["k"],x["d"]),"kpr":safe(x["k"],x["rounds"]),
                    "apr":safe(x["a"],x["rounds"]),"adr":safe(x["dmg"],x["rounds"]),"acs":safe(x["score"],x["rounds"]),
                    "fc_rate":pct(x["fk"]+x["fd"],x["rounds"]),"fc_success":pct(x["fk"],x["fk"]+x["fd"]),"fkfd":safe(x["fk"],x["fd"])}

def agents(db,riot):
    c=connect(db); rows=c.execute("""SELECT pm.agent,COUNT(*) games,SUM(m.rounds) rounds,SUM(pm.kills) k,SUM(pm.deaths)d,
    SUM(pm.assists)a,SUM(pm.damage)dmg,SUM(pm.score)score,SUM(pm.first_kills)fk,SUM(pm.first_deaths)fd,
    SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END)wins FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
    JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id WHERE pm.riot_id=? GROUP BY pm.agent ORDER BY games DESC""",(riot,)).fetchall(); c.close(); return rows

def maps(db,riot):
    c=connect(db); rows=c.execute("""SELECT m.map_name,COUNT(*) games,SUM(m.rounds) rounds,SUM(pm.kills) k,SUM(pm.deaths)d,
    SUM(pm.damage)dmg,SUM(pm.score)score,SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END)wins
    FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id
    WHERE pm.riot_id=? GROUP BY m.map_name ORDER BY games DESC""",(riot,)).fetchall(); c.close(); return rows

def weapons(db,riot):
    c=connect(db)
    rows=c.execute("""SELECT k.weapon,COUNT(*) kills
      FROM kills k
      JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
      JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
      WHERE k.killer=? AND pk.team_id<>pv.team_id
        AND k.weapon IS NOT NULL AND k.weapon<>'' AND k.weapon NOT IN ('Fall','Bomb')
      GROUP BY k.weapon ORDER BY kills DESC,k.weapon""",(riot,)).fetchall()
    c.close(); return rows

def duels(db,riot):
    c=connect(db)
    rows=c.execute("""WITH opp AS (
      SELECT k.victim opponent,COUNT(*) k,0 d
      FROM kills k
      JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
      JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
      WHERE k.killer=? AND pk.team_id<>pv.team_id GROUP BY k.victim
      UNION ALL
      SELECT k.killer opponent,0 k,COUNT(*) d
      FROM kills k
      JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
      JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
      WHERE k.victim=? AND pk.team_id<>pv.team_id GROUP BY k.killer
    )
    SELECT opponent,SUM(k) kills,SUM(d) deaths,SUM(k)-SUM(d) diff FROM opp
      WHERE opponent<>? GROUP BY opponent ORDER BY diff DESC, (SUM(k)+SUM(d)) DESC""",(riot,riot,riot)).fetchall()
    c.close(); return rows

def economy(db,riot):
    c=connect(db); rows=c.execute("""SELECT loadout,SUM(rounds_played) rounds,SUM(rounds_won) wins,SUM(kills) k,SUM(deaths)d,
    SUM(assists)a,SUM(damage)dmg FROM loadout_stats WHERE riot_id=? GROUP BY loadout ORDER BY rounds DESC""",(riot,)).fetchall(); c.close(); return rows

def sides(db,riot):
    c=connect(db); return [dict(r) for r in c.execute("""SELECT side,COUNT(*) rounds,SUM(kills) k,SUM(deaths)d,SUM(assists)a,SUM(damage)dmg,
      SUM(score)score,SUM(CASE WHEN kills>0 OR assists>0 THEN 1 ELSE 0 END) contribution_rounds
      FROM player_rounds WHERE riot_id=? GROUP BY side""",(riot,)).fetchall()]

def multikills_match(db, match_id):
    c=connect(db)
    rows=c.execute("""SELECT pm.riot_id,pm.team_id,
      SUM(CASE WHEN x.kc=2 THEN 1 ELSE 0 END) k2,
      SUM(CASE WHEN x.kc=3 THEN 1 ELSE 0 END) k3,
      SUM(CASE WHEN x.kc=4 THEN 1 ELSE 0 END) k4,
      SUM(CASE WHEN x.kc>=5 THEN 1 ELSE 0 END) k5
      FROM player_matches pm
      LEFT JOIN (
        SELECT k.killer riot_id,k.round_no,COUNT(*) kc
        FROM kills k
        JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
        JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
        WHERE k.match_id=? AND pk.team_id<>pv.team_id
        GROUP BY k.killer,k.round_no
      ) x ON x.riot_id=pm.riot_id
      WHERE pm.match_id=? GROUP BY pm.riot_id,pm.team_id ORDER BY pm.team_id,pm.score DESC""",(match_id,match_id)).fetchall()
    c.close(); return rows

def multikills_alltime(db, riot):
    c=connect(db)
    x=c.execute("""SELECT
      SUM(CASE WHEN kc=2 THEN 1 ELSE 0 END) k2,
      SUM(CASE WHEN kc=3 THEN 1 ELSE 0 END) k3,
      SUM(CASE WHEN kc=4 THEN 1 ELSE 0 END) k4,
      SUM(CASE WHEN kc>=5 THEN 1 ELSE 0 END) k5
      FROM (
        SELECT k.match_id,k.round_no,COUNT(*) kc
        FROM kills k
        JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
        JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
        WHERE k.killer=? AND pk.team_id<>pv.team_id
        GROUP BY k.match_id,k.round_no
      )""",(riot,)).fetchone()
    c.close(); return dict(x) if x else {"k2":0,"k3":0,"k4":0,"k5":0}

def teammates(db, riot):
    c=connect(db)
    rows=c.execute("""SELECT b.riot_id teammate,COUNT(*) games,SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END) wins
      FROM player_matches a JOIN player_matches b ON b.match_id=a.match_id AND b.team_id=a.team_id AND b.riot_id<>a.riot_id
      JOIN teams t ON t.match_id=a.match_id AND t.team_id=a.team_id
      WHERE a.riot_id=? GROUP BY b.riot_id ORDER BY games DESC,wins DESC""",(riot,)).fetchall()
    c.close(); return rows

def leaderboard(db):
    c=connect(db)
    rows=c.execute("""SELECT pm.riot_id,COUNT(*) games,SUM(m.rounds) rounds,
      SUM(CASE WHEN t.won=1 THEN 1 ELSE 0 END) wins,SUM(pm.kills) k,SUM(pm.deaths)d,
      SUM(pm.assists)a,SUM(pm.damage)dmg,SUM(pm.score)score,SUM(pm.first_kills)fk,SUM(pm.first_deaths)fd
      FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
      JOIN teams t ON t.match_id=pm.match_id AND t.team_id=pm.team_id
      GROUP BY pm.riot_id ORDER BY (1.0*SUM(pm.score)/SUM(m.rounds)) DESC""").fetchall()
    c.close(); return rows


PLAYSTYLE_MIN_GAMES = 5
UNDERUSED_WEAPONS = ("Frenzy","Bulldog","Ares","Guardian")

def _q(values, q):
    vals=sorted(float(v) for v in values if v is not None)
    if not vals: return 0.0
    if len(vals)==1: return vals[0]
    pos=(len(vals)-1)*q
    lo=int(pos); hi=min(lo+1,len(vals)-1); f=pos-lo
    return vals[lo]*(1-f)+vals[hi]*f

def _player_feature_rows(db):
    c=connect(db)
    ids=[r["riot_id"] for r in c.execute("SELECT riot_id FROM player_profiles")]
    out=[]
    for rid in ids:
        o=overall(db,rid)
        if (o.get("games") or 0) < PLAYSTYLE_MIN_GAMES: 
            continue
        pm=c.execute("""SELECT m.rounds,pm.acs,pm.hs_accuracy,pm.attack_kills,pm.attack_deaths,
                              pm.defense_kills,pm.defense_deaths,pm.triple_kills,pm.quadra_kills,pm.penta_kills
                       FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
                       WHERE pm.riot_id=?""",(rid,)).fetchall()
        rounds=o.get("rounds") or 0
        hs_num=sum((x["hs_accuracy"] or 0)*(x["rounds"] or 0) for x in pm)
        hs=hs_num/rounds if rounds else 0
        acss=[x["acs"] or 0 for x in pm]
        acs_sd=statistics.pstdev(acss) if len(acss)>=2 else 0
        surv=(o.get("survived") or 0)/rounds if rounds else 0
        multi3=((sum((x["triple_kills"] or 0)+(x["quadra_kills"] or 0)+(x["penta_kills"] or 0) for x in pm))/rounds if rounds else 0)
        out.append({
            "riot_id":rid,"games":o["games"],"rounds":rounds,"hs":hs,"adr":o["adr"],
            "fc_rate":o["fc_rate"],"fc_success":o["fc_success"],"apr":o["apr"],
            "survival":surv,"multi3":multi3,"acs_sd":acs_sd,
            "kast":0, "attack_kd":safe(sum(x["attack_kills"] or 0 for x in pm),sum(x["attack_deaths"] or 0 for x in pm)),
            "defense_kd":safe(sum(x["defense_kills"] or 0 for x in pm),sum(x["defense_deaths"] or 0 for x in pm)),
        })
        # round-weighted KAST from direct per-match Tracker values
        kast_num=c.execute("""SELECT SUM(pm.kast*m.rounds) v FROM player_matches pm
                              JOIN matches m ON m.match_id=pm.match_id WHERE pm.riot_id=?""",(rid,)).fetchone()["v"] or 0
        out[-1]["kast"]=kast_num/rounds if rounds else 0
    c.close()
    return out


def _new_dimension_metrics(db):
    """Derived playstyle dimensions from round/event data. Kept qualitative;
    thresholds are applied later against the current eligible Lobby population."""
    c=connect(db)
    players=[r["riot_id"] for r in c.execute("""SELECT riot_id FROM player_matches
        GROUP BY riot_id HAVING COUNT(*)>=?""",(PLAYSTYLE_MIN_GAMES,))]
    metrics={p:{
        "early_share":0,"late_share":0,"last_man_rate":0,"trade_rate":0,
        "eco_farm_rate":0,"eco_strike_rate":0,"pistol_kd":0,"pistol_wr":0,
        "plants_rate":0,"defuses_rate":0,"damage_taken":0,"death_rate":0,"kpr":0,
        "one_done_rate":0,"utility_rate":0,"ult_rate":0,"nondmg_assist_rate":0,
        "weapon_variety":0,"scope_share":0,"behind_wr":0,"ahead_wr":0,
        "pressure_wr":0,"closeout_fail":0,"momentum_rate":0,"cold_start_gap":0,
        "hero_round_rate":0,"clutch_big":0,"clutch_lost_close":0,
        "map_edge":0,"kill_events":0,"timed_kills":0,
    } for p in players}

    # Basic totals from player matches.
    for p in players:
        r=c.execute("""SELECT SUM(m.rounds) rounds,SUM(pm.kills) k,SUM(pm.deaths) d,
            SUM(pm.damage_received) recv,SUM(pm.plants) plants,SUM(pm.defuses) defuses
            FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
            WHERE pm.riot_id=?""",(p,)).fetchone()
        rounds=r["rounds"] or 0
        metrics[p]["damage_taken"]=safe(r["recv"] or 0,rounds)
        metrics[p]["death_rate"]=safe(r["d"] or 0,rounds)
        metrics[p]["kpr"]=safe(r["k"] or 0,rounds)
        metrics[p]["plants_rate"]=safe(r["plants"] or 0,rounds)
        metrics[p]["defuses_rate"]=safe(r["defuses"] or 0,rounds)

    # Legitimate enemy kill events + timing / weapon diversity.
    kill_events=c.execute("""SELECT k.match_id,k.round_no,k.killer,k.victim,k.weapon,k.round_time,
        pk.team_id killer_team,pv.team_id victim_team,k.assistants_json
        FROM kills k
        JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
        JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
        WHERE pk.team_id<>pv.team_id AND k.weapon NOT IN ('Fall','Bomb')""").fetchall()
    by_player={p:[] for p in players}
    kill_lookup={}
    for k in kill_events:
        if k["killer"] in by_player:
            by_player[k["killer"]].append(k)
        kill_lookup.setdefault((k["match_id"],k["round_no"]),[]).append(k)
    for p,ev in by_player.items():
        if not ev: continue
        timed=[x for x in ev if x["round_time"] is not None]
        metrics[p]["kill_events"]=len(ev)
        metrics[p]["timed_kills"]=len(timed)
        metrics[p]["early_share"]=safe(sum(1 for x in timed if x["round_time"]<=25000),len(timed))
        metrics[p]["late_share"]=safe(sum(1 for x in timed if x["round_time"]>=75000),len(timed))
        ws=[x["weapon"] for x in ev if x["weapon"]]
        metrics[p]["weapon_variety"]=len(set(ws))
        scoped=sum(1 for x in ev if x["weapon"] in ("Marshal","Outlaw","Operator"))
        metrics[p]["scope_share"]=safe(scoped,len(ev))

    # Last man standing + one-and-done + momentum/cold start from player rounds.
    rounds_by_match={}
    for r in c.execute("""SELECT pr.match_id,pr.round_no,pr.riot_id,pr.kills,pr.deaths,pm.team_id
        FROM player_rounds pr JOIN player_matches pm
        ON pm.match_id=pr.match_id AND pm.riot_id=pr.riot_id
        ORDER BY pr.match_id,pr.round_no"""):
        rounds_by_match.setdefault((r["match_id"],r["round_no"]),[]).append(r)
    per_player_rounds={p:[] for p in players}
    for key,rs in rounds_by_match.items():
        for r in rs:
            if r["riot_id"] not in metrics: continue
            mates=[x for x in rs if x["team_id"]==r["team_id"] and x["riot_id"]!=r["riot_id"]]
            if r["deaths"]==0 and mates and sum(1 for x in mates if (x["deaths"] or 0)>0)>=len(mates):
                metrics[r["riot_id"]]["_last_man"]=metrics[r["riot_id"]].get("_last_man",0)+1
            if (r["kills"] or 0)==1:
                metrics[r["riot_id"]]["_one_rounds"]=metrics[r["riot_id"]].get("_one_rounds",0)+1
                if (r["deaths"] or 0)>0:
                    metrics[r["riot_id"]]["_one_done"]=metrics[r["riot_id"]].get("_one_done",0)+1
            per_player_rounds[r["riot_id"]].append(r)
    for p in players:
        total=len(per_player_rounds[p])
        metrics[p]["last_man_rate"]=safe(metrics[p].get("_last_man",0),total)
        metrics[p]["one_done_rate"]=safe(metrics[p].get("_one_done",0),metrics[p].get("_one_rounds",0))

        # Momentum: kill rounds that are part of 2+ consecutive kill-round streaks.
        seq=sorted(per_player_rounds[p], key=lambda x:(x["match_id"],x["round_no"]))
        impactful=0; streak_rounds=0; prev=None; streak=[]
        for r in seq+[None]:
            if r is not None and (r["kills"] or 0)>0 and prev and r["match_id"]==prev["match_id"] and r["round_no"]==prev["round_no"]+1:
                streak.append(r)
            elif r is not None and (r["kills"] or 0)>0:
                if len(streak)>=2: streak_rounds+=len(streak)
                streak=[r]
            else:
                if len(streak)>=2: streak_rounds+=len(streak)
                streak=[]
            if r is not None and (r["kills"] or 0)>0: impactful+=1
            prev=r
        metrics[p]["momentum_rate"]=safe(streak_rounds,impactful)

        # Cold start: first 5 rounds of each match vs remainder KPR.
        starts=[]; rests=[]
        bym={}
        for r in seq: bym.setdefault(r["match_id"],[]).append(r)
        for rs in bym.values():
            rs=sorted(rs,key=lambda x:x["round_no"])
            starts.extend(rs[:5]); rests.extend(rs[5:])
        sk=sum((x["kills"] or 0) for x in starts); rk=sum((x["kills"] or 0) for x in rests)
        metrics[p]["cold_start_gap"]=safe(rk,len(rests))-safe(sk,len(starts)) if starts and rests else 0

    # Trade Machine: revenge kill within 5 seconds of an enemy killing a teammate.
    # A trade is credited to p when p kills the same enemy shortly after that enemy's kill.
    for key,evs in kill_lookup.items():
        evs=sorted([x for x in evs if x["round_time"] is not None],key=lambda x:x["round_time"])
        for i,death in enumerate(evs):
            victim=death["victim"]; killer=death["killer"]; t=death["round_time"]
            # teammates of victim derive from player_matches in event team ids
            victim_team=death["victim_team"]
            for nxt in evs[i+1:]:
                if nxt["round_time"]-t>5000: break
                if nxt["victim"]==killer and nxt["killer_team"]==victim_team and nxt["killer"] in metrics:
                    metrics[nxt["killer"]]["_trades"]=metrics[nxt["killer"]].get("_trades",0)+1
                    break
    for p in players:
        rounds=len(per_player_rounds[p])
        metrics[p]["trade_rate"]=safe(metrics[p].get("_trades",0),rounds)

    # Economy: compare player's team-average loadout to enemy team-average loadout per round.
    for key,rs in rounds_by_match.items():
        teams={}
        for r in rs:
            # retrieve value from source row separately
            pass
    econ_rows=c.execute("""SELECT pr.match_id,pr.round_no,pr.riot_id,pr.loadout_value,pm.team_id
        FROM player_rounds pr JOIN player_matches pm
        ON pm.match_id=pr.match_id AND pm.riot_id=pr.riot_id""").fetchall()
    econ_by_round={}
    for r in econ_rows: econ_by_round.setdefault((r["match_id"],r["round_no"]),[]).append(r)
    for key,rs in econ_by_round.items():
        team_vals={}
        for r in rs: team_vals.setdefault(r["team_id"],[]).append(r["loadout_value"] or 0)
        avgs={t:safe(sum(v),len(v)) for t,v in team_vals.items()}
        for r in rs:
            p=r["riot_id"]
            if p not in metrics: continue
            own=avgs.get(r["team_id"],0)
            opp=max((v for t,v in avgs.items() if t!=r["team_id"]),default=0)
            rr=c.execute("SELECT winner FROM rounds WHERE match_id=? AND round_no=?",key).fetchone()
            won=bool(rr and rr["winner"]==r["team_id"])
            if opp and own>=3200 and opp<=2200:
                metrics[p]["_eco_farm_n"]=metrics[p].get("_eco_farm_n",0)+1
                metrics[p]["_eco_farm_w"]=metrics[p].get("_eco_farm_w",0)+(1 if won else 0)
            if own<=2200 and opp>=3200:
                metrics[p]["_eco_strike_n"]=metrics[p].get("_eco_strike_n",0)+1
                metrics[p]["_eco_strike_w"]=metrics[p].get("_eco_strike_w",0)+(1 if won else 0)
    for p in players:
        metrics[p]["eco_farm_rate"]=safe(metrics[p].get("_eco_farm_w",0),metrics[p].get("_eco_farm_n",0))
        metrics[p]["eco_strike_rate"]=safe(metrics[p].get("_eco_strike_w",0),metrics[p].get("_eco_strike_n",0))

    # Pistols from Tracker loadout aggregate.
    for p in players:
        r=c.execute("""SELECT SUM(rounds_played) rounds,SUM(rounds_won) wins,SUM(kills) k,SUM(deaths) d
            FROM loadout_stats WHERE riot_id=? AND LOWER(loadout)='pistol'""",(p,)).fetchone()
        if r and (r["rounds"] or 0):
            metrics[p]["pistol_kd"]=safe(r["k"] or 0,r["d"] or 0)
            metrics[p]["pistol_wr"]=safe(r["wins"] or 0,r["rounds"] or 0)
            metrics[p]["_pistol_rounds"]=r["rounds"] or 0

    # Ability usage.
    for p in players:
        rows=c.execute("""SELECT ability,SUM(casts) casts FROM ability_usage WHERE riot_id=?
            GROUP BY ability""",(p,)).fetchall()
        total=sum((r["casts"] or 0) for r in rows if not str(r["ability"]).endswith("PerRound"))
        ult=sum((r["casts"] or 0) for r in rows if r["ability"]=="ultimateCasts")
        rr=max(1,len(per_player_rounds[p]))
        metrics[p]["utility_rate"]=safe(total,rr)
        metrics[p]["ult_rate"]=safe(ult,rr)

    # Non-damage assists: assistant on a kill without a same-round damage event vs that victim.
    damage_pairs={(r["match_id"],r["round_no"],r["attacker"],r["target"]) for r in
        c.execute("SELECT match_id,round_no,attacker,target FROM damage_events WHERE damage>0")}
    for k in kill_events:
        try: assistants=json.loads(k["assistants_json"] or "[]")
        except Exception: assistants=[]
        for ass in assistants:
            if isinstance(ass,dict):
                aid=ass.get("platformUserIdentifier") or ass.get("riot_id") or ass.get("name")
            else: aid=ass
            if aid in metrics and (k["match_id"],k["round_no"],aid,k["victim"]) not in damage_pairs:
                metrics[aid]["_nondmg_assists"]=metrics[aid].get("_nondmg_assists",0)+1
    for p in players:
        metrics[p]["nondmg_assist_rate"]=safe(metrics[p].get("_nondmg_assists",0),max(1,len(per_player_rounds[p])))

    # Clutch detail from Tracker tags.
    for p in players:
        big=lost_close=0
        for r in c.execute("SELECT tags_json FROM player_matches WHERE riot_id=?",(p,)):
            try: tags=json.loads(r["tags_json"] or "[]")
            except Exception: tags=[]
            for t in tags:
                key=str(t.get("key") or "")
                count=t.get("count") or 1
                if key.startswith("clutch1v") and key not in ("clutch1v1",):
                    big+=count
                if key.startswith("clutchLost1v"):
                    lost_close+=count
        metrics[p]["clutch_big"]=big
        metrics[p]["clutch_lost_close"]=lost_close

    # Map edge: best meaningful map K/D versus player's overall K/D.
    for p in players:
        maps_=maps(db,p)
        po=overall(db,p)
        best=0
        for x in maps_:
            if (x["games"] or 0)>=2:
                mkd=safe(x["k"],x["d"])
                best=max(best,mkd-po["kd"])
        metrics[p]["map_edge"]=best

    # Score-state dimensions: behind/ahead/pressure/closeout.
    match_rounds={}
    for r in c.execute("SELECT match_id,round_no,winner FROM rounds ORDER BY match_id,round_no"):
        match_rounds.setdefault(r["match_id"],[]).append(r)
    team_for={(r["match_id"],r["riot_id"]):r["team_id"] for r in c.execute("SELECT match_id,riot_id,team_id FROM player_matches")}
    for mid,rs in match_rounds.items():
        score={"Red":0,"Blue":0}
        for rr in rs:
            before=dict(score)
            for p in players:
                team=team_for.get((mid,p))
                if not team: continue
                opp="Blue" if team=="Red" else "Red"
                won=rr["winner"]==team
                diff=before.get(team,0)-before.get(opp,0)
                total=before.get(team,0)+before.get(opp,0)
                if diff<=-3:
                    metrics[p]["_behind_n"]=metrics[p].get("_behind_n",0)+1
                    metrics[p]["_behind_w"]=metrics[p].get("_behind_w",0)+(1 if won else 0)
                if diff>=3:
                    metrics[p]["_ahead_n"]=metrics[p].get("_ahead_n",0)+1
                    metrics[p]["_ahead_w"]=metrics[p].get("_ahead_w",0)+(1 if won else 0)
                if total>=16 and abs(diff)<=1:
                    metrics[p]["_pressure_n"]=metrics[p].get("_pressure_n",0)+1
                    metrics[p]["_pressure_w"]=metrics[p].get("_pressure_w",0)+(1 if won else 0)
                # Match point: >=12 and currently one round ahead (normal or OT).
                if before.get(team,0)>=12 and diff==1:
                    metrics[p]["_close_n"]=metrics[p].get("_close_n",0)+1
                    metrics[p]["_close_fail"]=metrics[p].get("_close_fail",0)+(0 if won else 1)
            score[rr["winner"]]=score.get(rr["winner"],0)+1
    for p in players:
        metrics[p]["behind_wr"]=safe(metrics[p].get("_behind_w",0),metrics[p].get("_behind_n",0))
        metrics[p]["ahead_wr"]=safe(metrics[p].get("_ahead_w",0),metrics[p].get("_ahead_n",0))
        metrics[p]["pressure_wr"]=safe(metrics[p].get("_pressure_w",0),metrics[p].get("_pressure_n",0))
        metrics[p]["closeout_fail"]=safe(metrics[p].get("_close_fail",0),metrics[p].get("_close_n",0))

    # Clutch beast / hero rounds = clutches + 3K+ normalized by rounds.
    for p in players:
        r=c.execute("""SELECT SUM(pm.clutches) cl,SUM(pm.triple_kills+pm.quadra_kills+pm.penta_kills) hero,
            SUM(m.rounds) rounds FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
            WHERE pm.riot_id=?""",(p,)).fetchone()
        metrics[p]["hero_round_rate"]=safe((r["cl"] or 0)+(r["hero"] or 0),r["rounds"] or 0)

    c.close()
    return metrics

def playstyle_tags(db, riot, min_games=PLAYSTYLE_MIN_GAMES):
    """Porofessor-like qualitative insights. Prototype thresholds use the current Lobby population.
    No exact numbers are exposed in tag copy. Max 5 tags returned."""
    population=_player_feature_rows(db)
    me=next((x for x in population if x["riot_id"]==riot),None)
    if not me or me["games"] < min_games:
        return []

    def qs(key):
        vals=[x[key] for x in population]
        return _q(vals,.25),_q(vals,.75)

    hs25,hs75=qs("hs"); adr25,adr75=qs("adr"); fc25,fc75=qs("fc_rate")
    fcs25,fcs75=qs("fc_success"); apr25,apr75=qs("apr"); surv25,surv75=qs("survival")
    m325,m375=qs("multi3"); sd25,sd75=qs("acs_sd"); kast25,kast75=qs("kast")
    tags=[]
    def add(key,name,desc,tone,priority):
        tags.append({"key":key,"name":name,"description":desc,"tone":tone,"priority":priority})

    # Aim
    if me["hs"] >= max(hs75,28):
        add("sharpshooter","Sharpshooter","High headshot rate","positive",82)
    elif me["hs"] <= min(hs25,18):
        add("bodyshot","Bodyshot Enjoyer","Low headshot rate","negative",58)

    # Opening: only label low success when the player ACTUALLY takes lots of first contact.
    if me["fc_rate"] >= fc75 and me["fc_success"] >= max(fcs75,55):
        add("opening-specialist","Opening Specialist","High first contact engagement winrate","positive",92)
    elif me["fc_rate"] >= fc75 and me["fc_success"] <= min(fcs25,42):
        add("opening-struggles","First Blood Donor","Frequently loses opening engagements","negative",88)
    elif me["fc_rate"] >= fc75:
        add("aggressive-entry","Aggressive Entry","Frequently takes first contact","neutral",63)

    # Damage, not vague "impact".
    if me["adr"] >= max(adr75,155):
        add("damage-dealer","Damage Dealer","Consistently deals high damage","positive",84)
    elif me["adr"] <= min(adr25,115):
        add("low-damage","Low Damage","Consistently deals low damage","negative",72)

    if me["survival"] >= max(surv75,.30):
        add("hard-to-kill","Hard to Kill","Survives rounds frequently","positive",66)
    elif me["survival"] <= min(surv25,.18):
        add("early-exit","Early Exit","Dies frequently during rounds","negative",48)

    # Multikills intentionally start at 3K+.
    if me["multi3"] >= max(m375,.045):
        add("multikill-threat","Multi-Kill Threat","Frequently converts 3K+ rounds","positive",90)

    # Consistency / variance.
    if me["acs_sd"] >= max(sd75,55):
        add("hot-cold","Hot & Cold","Highly variable match performance","neutral",70)
    elif me["acs_sd"] <= min(sd25,35):
        add("consistent","Consistent","Consistent match performance","positive",68)

    if me["apr"] >= max(apr75,.32):
        add("assist-machine","Assist Machine","Frequently contributes through assists","positive",62)
    if me["kast"] >= max(kast75,78):
        add("kast-merchant","KAST Merchant","Frequently contributes to rounds","positive",76)

    # Side specialty: requires a meaningful gap and a strong side.
    if me["attack_kd"]-me["defense_kd"] >= .28 and me["attack_kd"]>=1.10:
        add("attack-specialist","Attack Specialist","Strong attacking-side performance","positive",67)
    elif me["defense_kd"]-me["attack_kd"] >= .28 and me["defense_kd"]>=1.10:
        add("defense-specialist","Defense Specialist","Strong defensive-side performance","positive",67)

    c=connect(db)

    # Clutch tags: specific sample minimum, independent from overall 5-game gate.
    cr=c.execute("""SELECT SUM(clutches) w,SUM(clutches_lost) l FROM player_matches WHERE riot_id=?""",(riot,)).fetchone()
    cw,cl=(cr["w"] or 0),(cr["l"] or 0); attempts=cw+cl
    if attempts>=3:
        conv=safe(cw,attempts)
        if conv>=.50: add("clutch-player","Clutch Player","Strong clutch conversion","positive",86)
        elif conv<=.20: add("clutch-struggler","Clutch Struggler","Struggles in clutch situations","negative",64)

    # Weapon signatures. Compare kills/round against the current eligible population.
    all_rounds={x["riot_id"]:x["rounds"] for x in population}
    weapon_rows=c.execute(f"""SELECT k.killer riot_id,k.weapon,COUNT(*) kills
                             FROM kills k
                             JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
                             JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
                             WHERE k.killer IS NOT NULL AND pk.team_id<>pv.team_id
                               AND k.weapon IN ({_weapon_sql_placeholders()})
                             GROUP BY k.killer,k.weapon""",STANDARD_WEAPONS).fetchall()
    by_weapon={}
    by_player={}
    for r in weapon_rows:
        by_weapon.setdefault(r["weapon"],{})[r["riot_id"]]=r["kills"]
        by_player.setdefault(r["riot_id"],{})[r["weapon"]]=r["kills"]
    myw=by_player.get(riot,{})
    total_weapon_kills=sum(myw.values()) or 1

    def weapon_signature(weapon, name, desc, tone="positive", priority=75, min_kills=4, min_share=.07):
        kills=myw.get(weapon,0)
        if kills < min_kills or kills/total_weapon_kills < min_share: return
        rates=[]
        for p in population:
            rr=all_rounds.get(p["riot_id"],0)
            rates.append(safe(by_weapon.get(weapon,{}).get(p["riot_id"],0),rr))
        myrate=safe(kills,me["rounds"])
        if myrate >= max(_q(rates,.75), .03):
            add("weapon-"+weapon.lower().replace(" ","-"),name,desc,tone,priority)

    weapon_signature("Operator","Operator Specialist","Strong Operator performance","positive",84,4,.06)
    weapon_signature("Sheriff","Sheriff Specialist","Strong Sheriff performance","positive",78,4,.06)
    for w in UNDERUSED_WEAPONS:
        weapon_signature(w,f"{w} Specialist",f"Strong {w} performance","positive",77,3,.045)

    odin=myw.get("Odin",0)
    if odin>=4 and odin/total_weapon_kills>=.07:
        add("war-criminal","War Criminal","Plays Odin a lot","neutral",74)

    # Agent loyalist family: one tag per actual dominant agent.
    ag=c.execute("""SELECT pm.agent,COUNT(*) games,SUM(m.rounds) rounds,MAX(m.date_started) last_seen
                    FROM player_matches pm JOIN matches m ON m.match_id=pm.match_id
                    WHERE pm.riot_id=? GROUP BY pm.agent ORDER BY rounds DESC,last_seen DESC""",(riot,)).fetchall()
    if ag and me["rounds"]:
        top=ag[0]
        share=safe(top["rounds"],me["rounds"])
        if (top["games"] or 0)>=2 and share>=.60:
            agent_name=top["agent"]
            title=AGENT_SIGNATURE_TITLES.get(agent_name,f"{agent_name} Loyalist")
            add("agent-"+agent_name.lower().replace(" ","-"),title,f"Frequently plays {agent_name}","neutral",73)

    # Chamber easter egg: both Headhunter and Tour de Force must rank in the player's
    # top five legitimate enemy kill sources. Tracker naming for the ult is normalized.
    top_sources=c.execute("""SELECT k.weapon,COUNT(*) kills
      FROM kills k
      JOIN player_matches pk ON pk.match_id=k.match_id AND pk.riot_id=k.killer
      JOIN player_matches pv ON pv.match_id=k.match_id AND pv.riot_id=k.victim
      WHERE k.killer=? AND pk.team_id<>pv.team_id
        AND k.weapon IS NOT NULL AND k.weapon<>'' AND k.weapon NOT IN ('Fall','Bomb')
      GROUP BY k.weapon ORDER BY kills DESC,k.weapon LIMIT 5""",(riot,)).fetchall()
    source_names={str(x["weapon"]).strip().lower().replace(" ","") for x in top_sources}
    has_headhunter="headhunter" in source_names
    has_tdf=any(x in source_names for x in ("tourdeforce","tourdeforce"))
    if has_headhunter and has_tdf:
        add("fabrons-fabric","Fabron's Fabric","Headhunter and Tour de Force define this Chamber loadout","neutral",96)


    # --- V5.3 additional gameplay dimensions ---
    dims=_new_dimension_metrics(db)
    dm=dims.get(riot,{})
    def dq(key,q=.75):
        vals=[x.get(key,0) for x in dims.values()]
        return _q(vals,q)

    # Trade / timing
    if dm.get("trade_rate",0)>=max(dq("trade_rate"),.035):
        add("trade-machine","Trade Machine","Frequently converts teammate deaths into trades","positive",83)
    if dm.get("timed_kills",0)>=8 and dm.get("early_share",0)>=max(dq("early_share"),.28):
        add("early-bird","Early Bird","Frequently finds kills early in rounds","neutral",61)
    if dm.get("timed_kills",0)>=6 and dm.get("late_share",0)>=max(dq("late_share"),.20):
        add("late-bloomer","Late Bloomer","Frequently finds kills late in rounds","neutral",61)
    if dm.get("last_man_rate",0)>=max(dq("last_man_rate"),.08):
        add("last-man-standing","Last Man Standing","Frequently ends up as the final teammate alive","neutral",59)

    # Clutches
    if dm.get("clutch_big",0)>=2:
        add("against-all-odds","Against All Odds","Frequently converts outnumbered clutches","positive",89)
    if dm.get("clutch_lost_close",0)>=2:
        add("almost-there","Almost There","Frequently comes close in lost clutch situations","negative",57)

    # Economy / pistols
    if dm.get("_eco_farm_n",0)>=5 and dm.get("eco_farm_rate",0)>=.75:
        add("eco-farmer","Eco Farmer","Punishes low-buy opponents consistently","positive",64)
    if dm.get("_eco_strike_n",0)>=5 and dm.get("eco_strike_rate",0)>=.45:
        add("eco-striker","Eco Striker","Wins rounds despite a weaker team buy","positive",84)
    if dm.get("_pistol_rounds",0)>=6:
        if dm.get("pistol_kd",0)>=max(dq("pistol_kd"),1.15):
            add("pistolero","Pistolero","Strong pistol-round performance","positive",72)
        elif dm.get("pistol_kd",0)<=min(_q([x.get("pistol_kd",0) for x in dims.values() if x.get("_pistol_rounds",0)>=6],.25),.75):
            add("pistol-panic","Pistol Panic","Struggles during pistol rounds","negative",55)

    # Objective
    if dm.get("plants_rate",0)>=max(dq("plants_rate"),.06):
        add("wingman","Wingman","Frequently takes responsibility for planting the spike","neutral",56)
    if dm.get("defuses_rate",0)>=max(dq("defuses_rate"),.025):
        add("defuse-duty","Defuse Duty","Frequently handles spike defuses","neutral",56)

    # Damage profile
    dr75=dq("death_rate"); dt75=dq("damage_taken"); kpr25=_q([x.get("kpr",0) for x in dims.values()],.25)
    if me["adr"]>=max(adr75,155) and dm.get("death_rate",0)>=dr75:
        add("glass-cannon","Glass Cannon","Deals heavy damage while dying frequently","neutral",79)
    if dm.get("damage_taken",0)>=max(dt75,155):
        add("magnet-pull","Magnet Pull","Absorbs unusually high enemy damage","neutral",60)
    if me["adr"]>=max(adr75,150) and dm.get("kpr",0)<=kpr25:
        add("chip-damage","Chip Damage","Deals high damage without converting many kills","neutral",65)
    if dm.get("_one_rounds",0)>=8 and dm.get("one_done_rate",0)>=max(dq("one_done_rate"),.65):
        add("one-and-done","One and Done","Frequently gets one kill before dying","negative",63)

    # Utility / assists
    if dm.get("utility_rate",0)>=max(dq("utility_rate"),1.20):
        add("utility-merchant","Utility Merchant","Uses utility at a very high rate","positive",71)
    if dm.get("ult_rate",0)>=max(dq("ult_rate"),.045):
        add("ult-addict","Ult Addict","Uses ultimates very frequently","neutral",58)
    if dm.get("utility_rate",0)<=min(_q([x.get("utility_rate",0) for x in dims.values()],.25),.65):
        add("utility-hoarder","Utility Hoarder","Uses relatively little utility","negative",60)
    if dm.get("nondmg_assist_rate",0)>=max(dq("nondmg_assist_rate"),.055):
        add("setup-artist","Setup Artist","Creates frequent non-damage assists","positive",81)

    # Weapon identity
    if dm.get("weapon_variety",0)>=max(dq("weapon_variety"),8):
        add("walking-armory","Walking Armory","Finds kills with a wide variety of weapons","neutral",62)
    if dm.get("kill_events",0)>=8 and dm.get("scope_share",0)>=max(dq("scope_share"),.18):
        add("scoper","Scoper","Frequently finds kills with scoped sniper weapons","neutral",69)

    # Map identity
    if dm.get("map_edge",0)>=.30:
        add("home-turf","Home Turf","Performs significantly better on a favorite map","positive",74)

    # Score-state / pressure
    if dm.get("_behind_n",0)>=5 and dm.get("behind_wr",0)>=.55:
        add("fnatic-mindset","FNATIC Mindset","Performs strongly when the team is trailing","positive",85)
    if dm.get("_ahead_n",0)>=5 and dm.get("ahead_wr",0)>=.72:
        add("front-runner","Front Runner","Converts leads consistently","positive",67)
    if dm.get("_pressure_n",0)>=5 and dm.get("pressure_wr",0)>=.60:
        add("pressure-player","Pressure Player","Performs strongly in close late-round scorelines","positive",87)
    if dm.get("_close_n",0)>=3 and dm.get("closeout_fail",0)>=.60:
        add("prx-throw","PRX's Throw","Frequently fails to convert match-point opportunities","negative",82)

    # Hero / momentum / starts
    if dm.get("hero_round_rate",0)>=max(dq("hero_round_rate"),.07):
        add("clutch-beast","Clutch Beast","Frequently takes over rounds with clutches or 3K+ plays","positive",91)
    if dm.get("momentum_rate",0)>=max(dq("momentum_rate"),.38):
        add("momentum-player","Momentum Player","Frequently strings together consecutive kill rounds","positive",66)
    if dm.get("cold_start_gap",0)>=max(dq("cold_start_gap"),.22):
        add("cold-start","Cold Start","Often starts slowly before improving later","neutral",54)

    c.close()

    # Keep only the five strongest/distinctive labels.
    # First choose by strength, then group visually by tone:
    # positive (green) -> neutral (orange) -> negative (red),
    # while preserving priority inside each group.
    tone_rank={"positive":2,"negative":2,"neutral":1}
    selected=sorted(tags,key=lambda x:(x["priority"],tone_rank[x["tone"]]),reverse=True)[:5]
    tone_order={"positive":0,"neutral":1,"negative":2}
    selected.sort(key=lambda x:(tone_order[x["tone"]],-x["priority"]))
    return selected
