# server.py (updated)
import asyncio, json, random, websockets
from collections import defaultdict

PORT = 6789
ROOM_CAPACITY = 10

# Roles config (default). You can change counts here.
ROLE_CONFIG = {
    "blackjack": 1,
    "killer": 2,
    "whitejack": 1,
    "seer": 1,
    "doctor": 1,
    "villager": 3
}

# Helper
def make_roles():
    roles = []
    for r,c in ROLE_CONFIG.items():
        roles += [r]*c
    random.shuffle(roles)
    return roles

class Game:
    def __init__(self):
        self.clients = {}  # websocket -> {id,name,alive,role,heals_left,self_heal_used}
        self.idmap = {}    # id -> websocket
        self.next_id = 1
        self.host = None
        self.phase = "lobby"
        self.logs = []
        self.votes = defaultdict(int)
        self.actions_buffer = []  # store actions during phase
        self.seer_checks = {}  # actor_id -> remaining checks for current night
    def broadcast(self, data):
        msg = json.dumps(data)
        return asyncio.gather(*[ws.send(msg) for ws in self.clients.keys()])
    def send(self, ws, data):
        return ws.send(json.dumps(data))
    def snapshot_players(self):
        out = []
        for ws,info in self.clients.items():
            out.append({
                "id": info["id"], "name": info["name"], "alive": info["alive"]
            })
        return out

G = Game()

async def handler(ws, path):
    # register
    G.clients[ws] = {"id": G.next_id, "name": None, "alive": True, "role": None,
                     "heals_left": 0, "self_heal_used": False}
    G.idmap[G.next_id] = ws
    if G.host is None:
        G.host = ws
    gid = G.next_id
    G.next_id += 1
    await G.send(ws, {"type":"connected", "your_id": gid})
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except:
                continue
            t = msg.get("type")
            if t == "join":
                name = msg.get("name","Player"+str(gid))
                G.clients[ws]["name"] = name
                await G.broadcast({"type":"lobby_update", "players": G.snapshot_players()})
            elif t == "start_request" and ws==G.host:
                # only start when exactly ROOM_CAPACITY players
                players_count = len(G.clients)
                if players_count < ROOM_CAPACITY:
                    await G.send(ws, {"type":"error", "message": f"Need {ROOM_CAPACITY} players, have {players_count}"})
                    continue
                # assign roles
                roles = make_roles()
                # assign to alive players in random order
                wss = list(G.clients.keys())
                random.shuffle(wss)
                for i, w in enumerate(wss):
                    role = roles[i]
                    G.clients[w]["role"] = role
                    # set role-specific counters
                    if role == "doctor":
                        G.clients[w]["heals_left"] = 2
                        G.clients[w]["self_heal_used"] = False
                    else:
                        G.clients[w]["heals_left"] = 0
                        G.clients[w]["self_heal_used"] = False
                # initialize seer checks for night (will be set when entering night)
                G.phase = "night"
                # send private role assignment (with starting meta)
                for w, info in G.clients.items():
                    msg = {"type":"assign_role", "role": info["role"]}
                    if info["role"] == "doctor":
                        msg["heals_left"] = info["heals_left"]
                        msg["self_heal_used"] = info["self_heal_used"]
                    if info["role"] == "seer":
                        msg["seer_checks_left"] = 3
                    await G.send(w, msg)
                # set seer checks now that night started
                for w, info in G.clients.items():
                    if info["role"] == "seer" and info["alive"]:
                        G.seer_checks[info["id"]] = 3
                await G.broadcast({"type":"state", "phase": G.phase, "players": G.snapshot_players(), "logs": G.logs})
            elif t == "chat":
                text = msg.get("text","")
                sender = G.clients[ws]["name"]
                await G.broadcast({"type":"chat", "from": sender, "text": text})
            elif t == "action":
                # buffer actions and apply at end of phase or immediately depending
                action = msg.get("action")
                target_id = msg.get("target")
                actor = G.clients[ws]
                if not actor["alive"]:
                    await G.send(ws, {"type":"error","message":"You are dead"})
                    continue
                # enforce allowed actions per phase
                if G.phase not in ("night","discussion","voting"):
                    await G.send(ws, {"type":"error","message":"Not action time"})
                    continue

                # Seer: allow only in night and max 3 per night
                if action == "seer":
                    if G.phase != "night":
                        await G.send(ws, {"type":"error","message":"Seer can only check at night"})
                        continue
                    remaining = G.seer_checks.get(actor["id"], 0)
                    if remaining <= 0:
                        await G.send(ws, {"type":"error","message":"No seer checks left this night"})
                        continue
                    # consume one check immediately and buffer action
                    G.seer_checks[actor["id"]] = remaining - 1
                    G.actions_buffer.append({"actor_id": actor["id"], "action": action, "target": target_id})
                    await G.send(ws, {"type":"action_ack","action":action})
                    # seer result will be revealed during processing (or immediately if you want)
                    continue

                # Doctor: heal action (no target). Only in night.
                if action == "heal":
                    if G.phase != "night":
                        await G.send(ws, {"type":"error","message":"Heal only at night"})
                        continue
                    if actor["role"] != "doctor":
                        await G.send(ws, {"type":"error","message":"Only doctor can heal"})
                        continue
                    if actor["heals_left"] <= 0:
                        await G.send(ws, {"type":"error","message":"No heals left"})
                        continue
                    # buffer heal (no target)
                    G.actions_buffer.append({"actor_id": actor["id"], "action": "heal", "target": None})
                    await G.send(ws, {"type":"action_ack","action":"heal"})
                    continue

                # Guess action allowed in discussion
                if action == "guess":
                    if G.phase != "discussion":
                        await G.send(ws, {"type":"error","message":"Guess only during discussion"})
                        continue
                    G.actions_buffer.append({"actor_id": actor["id"], "action": "guess", "target": target_id, "extra": msg.get("extra")})
                    await G.send(ws, {"type":"action_ack","action":"guess"})
                    continue

                # Kill action allowed in night
                if action == "kill":
                    if G.phase != "night":
                        await G.send(ws, {"type":"error","message":"Kill only at night"})
                        continue
                    # only killers or blackjack can kill
                    if actor["role"] not in ("killer", "blackjack"):
                        await G.send(ws, {"type":"error","message":"Not allowed to kill"})
                        continue
                    G.actions_buffer.append({"actor_id": actor["id"], "action": "kill", "target": target_id})
                    await G.send(ws, {"type":"action_ack","action":"kill"})
                    continue

                await G.send(ws, {"type":"error","message":"unknown or invalid action"})
            elif t == "end_phase" and ws==G.host:
                # host triggers phase transitions
                if G.phase == "night":
                    # process night kills & actions
                    await process_actions()
                    G.phase = "discussion"
                elif G.phase == "discussion":
                    G.phase = "voting"
                    # clear votes
                    G.votes = defaultdict(int)
                elif G.phase == "voting":
                    # tally votes, eliminate top
                    await process_votes()
                    # next is night: reset seer checks for alive seers
                    G.phase = "night"
                    for w, info in G.clients.items():
                        if info["role"] == "seer" and info["alive"]:
                            G.seer_checks[info["id"]] = 3
                await G.broadcast({"type":"state","phase":G.phase,"players":G.snapshot_players(),"logs":G.logs})
            elif t == "vote":
                voter = G.clients[ws]
                if not voter["alive"]:
                    await G.send(ws, {"type":"error","message":"Dead cannot vote"})
                    continue
                target = msg.get("target")
                G.votes[target] += 1
                await G.send(ws, {"type":"vote_ack","target":target})
            else:
                await G.send(ws, {"type":"error","message":"unknown message"})
    except websockets.ConnectionClosed:
        pass
    finally:
        # cleanup
        if ws in G.clients:
            del G.idmap[G.clients[ws]["id"]]
            del G.clients[ws]
        # if host disconnected pick new host
        if G.host==ws:
            G.host = next(iter(G.clients.keys()), None)
        await G.broadcast({"type":"lobby_update", "players": G.snapshot_players()})

async def process_votes():
    # find max
    if not G.votes:
        return
    max_votes = max(G.votes.values())
    top = [k for k,v in G.votes.items() if v==max_votes]
    chosen = random.choice(top)
    ws = G.idmap.get(chosen)
    if ws:
        G.clients[ws]["alive"] = False
        role = G.clients[ws].get("role")
        G.logs.append(f"Player {G.clients[ws]['name']} eliminated by vote.")
        await G.broadcast({"type":"eliminate","id": chosen, "name": G.clients[ws]["name"], "by":"vote", "role": role})
    # reset votes
    G.votes = defaultdict(int)

async def process_actions():
    # Apply buffered actions (simple resolution):
    # Night: killers-> kill target (take majority of kill actions), doctor heals applied automatically (1 heal per doctor use)
    if not G.actions_buffer:
        # still need to check win condition in case nothing happened
        await check_win_condition()
        return

    if G.phase == "night":
        # collect kill actions
        kills = defaultdict(int)
        for a in G.actions_buffer:
            if a["action"]=="kill":
                kills[a["target"]] += 1
        if kills:
            topcount = max(kills.values())
            candidates = [k for k,v in kills.items() if v==topcount]
            victim = random.choice(candidates)
            ws_victim = G.idmap.get(victim)
            # before marking dead, check for healer(s)
            healed_by = None
            # If victim is a doctor and that doctor has self_heal_available, prioritize self-heal
            if ws_victim:
                victim_info = G.clients[ws_victim]
                if victim_info.get("role") == "doctor" and victim_info.get("heals_left",0) > 0 and not victim_info.get("self_heal_used", False):
                    # doctor auto-heals themself
                    victim_info["heals_left"] -= 1
                    victim_info["self_heal_used"] = True
                    healed_by = victim_info["id"]
                    # send role_update to that doctor only
                    await G.send(ws_victim, {"type":"role_update", "heals_left": victim_info["heals_left"], "self_heal_used": victim_info["self_heal_used"]})
            # otherwise try other alive doctors with heals_left > 0
            if healed_by is None:
                # list available doctors (alive) who still have heals
                available = []
                for w, info in G.clients.items():
                    if info["alive"] and info["role"] == "doctor" and info.get("heals_left",0) > 0:
                        available.append((w, info))
                if available:
                    # pick one doctor to auto-heal the victim (randomly)
                    w_doc, doc_info = random.choice(available)
                    doc_info["heals_left"] -= 1
                    # if doc healed themselves (this happens only if doc_info['id']==victim) mark used
                    if doc_info["id"] == victim and not doc_info.get("self_heal_used", False):
                        doc_info["self_heal_used"] = True
                    healed_by = doc_info["id"]
                    # notify that doctor privately their new counters
                    await G.send(w_doc, {"type":"role_update", "heals_left": doc_info["heals_left"], "self_heal_used": doc_info["self_heal_used"]})

            if healed_by is not None:
                G.logs.append(f"Player {G.clients[ws_victim]['name']} was saved by doctor (doctor id {healed_by}).")
                # inform everyone that victim was saved (optional)
                await G.broadcast({"type":"chat","from":"[SYSTEM]","text":f"Player {G.clients[ws_victim]['name']} was saved by a doctor."})
            else:
                # no heal -> kill victim
                if ws_victim:
                    G.clients[ws_victim]["alive"] = False
                    role = G.clients[ws_victim].get("role")
                    G.logs.append(f"Player {G.clients[ws_victim]['name']} was killed at night.")
                    await G.broadcast({"type":"eliminate","id": victim, "name": G.clients[ws_victim]["name"], "by":"night", "role": role})
        # Also process other night-time actions (e.g., seer checks)
        for a in G.actions_buffer:
            if a["action"] == "seer":
                actor_ws = G.idmap.get(a["actor_id"])
                target_ws = G.idmap.get(a["target"])
                if not actor_ws or not target_ws:
                    continue
                targ_role = G.clients[target_ws]["role"]
                evil_set = {"blackjack","killer"}
                mark = "😈" if targ_role in evil_set else "😇"
                # broadcast seer result (revealed as mark)
                await G.broadcast({"type":"seer_result","target_id": G.clients[target_ws]["id"], "mark": mark})
        # clear buffer after resolving
    else:
        # discussion phase skills: guess resolved
        for a in G.actions_buffer:
            actor_ws = G.idmap.get(a["actor_id"])
            actor_role = G.clients[actor_ws]["role"] if actor_ws else None
            target_ws = G.idmap.get(a["target"])
            if a["action"]=="guess":
                guess_role = a.get("extra","")  # e.g. "villager" or "killer"
                if not target_ws:
                    continue
                target_role = G.clients[target_ws]["role"]
                evil = {"blackjack","killer"}
                good = {"whitejack","seer","villager"}
                if actor_role=="blackjack":
                    if (guess_role in good and target_role in good):
                        G.clients[target_ws]["alive"] = False
                        await G.broadcast({"type":"eliminate","id": G.clients[target_ws]["id"], "name": G.clients[target_ws]["name"], "by":"blackjack_guess", "role": target_role})
                        G.logs.append(f"Blackjack {G.clients[actor_ws]['name']} guessed correctly; {G.clients[target_ws]['name']} died.")
                    else:
                        G.clients[actor_ws]["alive"] = False
                        await G.broadcast({"type":"eliminate","id": G.clients[actor_ws]['id'], "name": G.clients[actor_ws]['name'], "by":"blackjack_fail", "role": actor_role})
                        G.logs.append(f"Blackjack {G.clients[actor_ws]['name']} guessed wrong and died.")
                elif actor_role=="whitejack":
                    if (guess_role in evil and target_role in evil):
                        G.clients[target_ws]["alive"] = False
                        await G.broadcast({"type":"eliminate","id": G.clients[target_ws]['id'], "name": G.clients[target_ws]['name'], "by":"whitejack_guess", "role": target_role})
                    else:
                        G.clients[actor_ws]["alive"] = False
                        await G.broadcast({"type":"eliminate","id": G.clients[actor_ws]['id'], "name": G.clients[actor_ws]['name'], "by":"whitejack_fail", "role": actor_role})
        # discussion phase processing ends

    # clear actions
    G.actions_buffer.clear()
    # after resolving actions, check win condition
    await check_win_condition()

async def check_win_condition():
    alive_roles = []
    alive_count = 0
    for info in G.clients.values():
        if info["alive"]:
            alive_roles.append(info["role"])
            alive_count += 1
    evil_alive = sum(1 for r in alive_roles if r in ("blackjack","killer"))
    good_alive = alive_count - evil_alive
    if evil_alive == 0:
        G.phase = "ended"
        await G.broadcast({"type":"game_over","winner":"good"})
        # reveal all roles
        roles = []
        for w,info in G.clients.items():
            roles.append({"id": info["id"], "name": info["name"], "role": info.get("role")})
        await G.broadcast({"type":"roles_revealed", "roles": roles})
    elif evil_alive >= good_alive:
        G.phase = "ended"
        await G.broadcast({"type":"game_over","winner":"evil"})
        roles = []
        for w,info in G.clients.items():
            roles.append({"id": info["id"], "name": info["name"], "role": info.get("role")})
        await G.broadcast({"type":"roles_revealed", "roles": roles})

start_server = websockets.serve(handler, "0.0.0.0", PORT)

print(f"Server running on ws://0.0.0.0:{PORT}")
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
