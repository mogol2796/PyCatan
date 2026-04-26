import argparse
import csv
import hashlib
import importlib
import json
import os
import random
import time
from datetime import datetime

from Managers.GameDirector import GameDirector

VICTORY_POINTS_TO_WIN = 10

DEFAULT_MAX_ROUNDS = 200
DEFAULT_MATCHES_PER_POSITION = 1
DEFAULT_POSITIONS = [0, 1, 2, 3]

DEFAULT_RESULTS_CSV = "benchmark_vs_llm_vs_estandar_resultados.csv"
DEFAULT_DETAILS_CSV = "benchmark_vs_llm_vs_estandar_detalle.csv"
DEFAULT_RUNS_CSV = "benchmark_vs_llm_runs.csv"

DEFAULT_OPPONENT_SETS = 1

STANDARD_OPPONENT_POOL = [
    "RandomAgent.RandomAgent",
    "AdrianHerasAgent.AdrianHerasAgent",
    "AlexPastorAgent.AlexPastorAgent",
    "AlexPelochoJaimeAgent.AlexPelochoJaimeAgent",
    "CarlesZaidaAgent.CarlesZaidaAgent",
    "CrabisaAgent.CrabisaAgent",
    "EdoAgent.EdoAgent",
    "PabloAleixAlexAgent.PabloAleixAlexAgent",
    "SigmaAgent.SigmaAgent",
    "TristanAgent.TristanAgent",
]


PROMPT_PROFILES = {
    "baseline_v1": {
        "start_system_prompt": (
            "You play Settlers of Catan. Return ONLY a JSON object with exactly these keys: node_id, road_to. "
            "Do not include any other keys and do not repeat the input. "
            "node_id must be one of candidates[].node_id. "
            "road_to must be one of candidates[].adjacent for the chosen node. "
            "Example: {\"node_id\": 24, \"road_to\": 23}."
        ),
        "build_system_prompt": (
            "You control a Catan agent. Return ONLY a JSON object with exactly one key: actions (a list). "
            "Do not include any other keys and do not repeat the input. "
            "Propose up to max_actions actions. Use ONLY legal_moves and ONLY actions you can afford (see can_afford). "
            "If can_afford[building] is false, do not propose that building. "
            "For 'city'/'town', choose node_id from the corresponding list. "
            "For 'road', choose a (node_id, road_to) pair exactly from legal_moves.road_edges. "
            "For 'card', use {\"building\":\"card\"} (no node_id/road_to needed). "
            "If you cannot build anything, return {\"actions\":[{\"building\":\"none\"}]}."
        ),
    },
    "economy_v1": {
        "start_system_prompt": (
            "You play Settlers of Catan. Return ONLY a JSON object with exactly these keys: node_id, road_to. "
            "Do not include any other keys and do not repeat the input. "
            "Choose a legal starting placement from the provided candidates. "
            "Prefer high total dice weight (sum of terrains[].w), avoid desert, and prefer diversity of terrain types. "
            "Prefer a good harbor if coastal (harbor != -1). "
            "IDs: terrain_type {-1 desert,0 cereal,1 mineral,2 clay,3 wood,4 wool}; "
            "harbor {-1 none,0 cereal,1 mineral,2 clay,3 wood,4 wool,5 all}."
        ),
        "build_system_prompt": (
            "You control a Catan agent. Return ONLY a JSON object with exactly one key: actions (a list). "
            "Do not include any other keys and do not repeat the input. "
            "Propose up to max_actions actions using ONLY legal_moves and only when can_afford is true. "
            "Economy focus: prefer building a town, then a city, then a road, then a card; otherwise stop with "
            "building='none'."
        ),
    },
    "cities_cards_v1": {
        "start_system_prompt": (
            "You play Settlers of Catan. Return ONLY a JSON object with exactly these keys: node_id, road_to. "
            "Do not include any other keys and do not repeat the input. "
            "Choose a legal starting placement from the provided candidates. "
            "City/dev-card focus: prefer candidates that include mineral (terrain_type=1) and wool (terrain_type=4) "
            "with high dice weight (terrains[].w). Avoid desert. "
            "Prefer coastal with a useful harbor (harbor != -1). "
            "IDs: terrain_type {-1 desert,0 cereal,1 mineral,2 clay,3 wood,4 wool}; "
            "harbor {-1 none,0 cereal,1 mineral,2 clay,3 wood,4 wool,5 all}."
        ),
        "build_system_prompt": (
            "You control a Catan agent. Return ONLY a JSON object with exactly one key: actions (a list). "
            "Do not include any other keys and do not repeat the input. "
            "Propose up to max_actions actions using ONLY legal_moves and only when can_afford is true. "
            "City/dev-card focus: prefer building a city, then buying a card, then building a town, then a road; "
            "otherwise stop with building='none'."
        ),
    },
}


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _timestamp_id():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def cargar_agente(ruta_clase):
    if not ruta_clase.startswith("Agents."):
        ruta_clase = f"Agents.{ruta_clase}"
    modulo, clase = ruta_clase.rsplit(".", 1)
    mod = importlib.import_module(modulo)
    return getattr(mod, clase)


def crear_clase_agente_configurada(agente_clase, **kwargs):
    class AgenteConfigurado(agente_clase):
        def __init__(self, agent_id):
            super().__init__(agent_id, **kwargs)

    AgenteConfigurado.__name__ = agente_clase.__name__
    return AgenteConfigurado


def _is_llm_agent_class(agent_cls):
    return "llm" in str(getattr(agent_cls, "__name__", "")).lower()


def _agent_label(agent_cls, prompt_tag="", extra_tags=None):
    name = str(getattr(agent_cls, "__name__", "UnknownAgent"))
    provider = (os.getenv("LLM_PROVIDER") or "").strip()
    model = (os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "").strip()

    parts = []
    if provider:
        parts.append(provider)
    if model:
        parts.append(model)
    if prompt_tag:
        parts.append(f"prompt={prompt_tag}")
    if extra_tags:
        for tag in extra_tags:
            tag = str(tag or "").strip()
            if tag:
                parts.append(tag)

    details = " ".join(parts).strip()
    return f"{name} ({details})" if details else name


def _extract_endgame_victory_points(game_trace):
    last_round = max(game_trace["game"].keys(), key=lambda r: int(r.split("_")[-1]))
    last_turn = max(game_trace["game"][last_round].keys(), key=lambda t: int(t.split("_")[-1].lstrip("P")))
    return game_trace["game"][last_round][last_turn]["end_turn"]["victory_points"]


def _compute_match_result(victory_points, position, rounds_played, max_rounds):
    vp_int = {p: int(v) for p, v in (victory_points or {}).items()}

    agent_id = f"J{position}"
    points = int(vp_int.get(agent_id, 0))

    max_vp = max(vp_int.values()) if vp_int else 0
    top_players = [p for p, v in vp_int.items() if v == max_vp]
    tie_for_first = len(top_players) > 1
    has_victory_condition = max_vp >= VICTORY_POINTS_TO_WIN

    is_win = has_victory_condition and (not tie_for_first)
    winner = top_players[0] if is_win else None
    victory = 1 if winner == agent_id else 0

    ordered = sorted(vp_int.items(), key=lambda item: item[1], reverse=True)
    rank = 4
    for idx, (player, _) in enumerate(ordered, start=1):
        if player == agent_id:
            rank = idx
            break

    timeout = 1 if (not has_victory_condition and rounds_played >= max_rounds) else 0
    draw = 1 if not is_win else 0

    return {
        "victory": victory,
        "points": points,
        "rank": rank,
        "winner": winner,
        "max_vp": max_vp,
        "tie_for_first": tie_for_first,
        "has_victory_condition": has_victory_condition,
        "timeout": timeout,
        "draw": draw,
        "vp": vp_int,
    }


def _run_match(agent_cls, opponent_classes, position, max_rounds, store_trace, game_number, shuffle_opponents):
    match_agents = list(opponent_classes)
    if shuffle_opponents:
        random.shuffle(match_agents)
    match_agents.insert(position, agent_cls)

    game_director = GameDirector(agents=match_agents, max_rounds=max_rounds, store_trace=store_trace)

    started = time.time()
    game_trace = game_director.game_start(game_number=game_number, print_outcome=False)
    duration_s = time.time() - started

    rounds_played = len(game_trace.get("game", {}))
    victory_points = _extract_endgame_victory_points(game_trace)
    result = _compute_match_result(victory_points, position, rounds_played, max_rounds)
    result["duration_s"] = duration_s
    result["rounds_played"] = rounds_played
    result["seat_J0_agent"] = str(getattr(match_agents[0], "__name__", "UnknownAgent"))
    result["seat_J1_agent"] = str(getattr(match_agents[1], "__name__", "UnknownAgent"))
    result["seat_J2_agent"] = str(getattr(match_agents[2], "__name__", "UnknownAgent"))
    result["seat_J3_agent"] = str(getattr(match_agents[3], "__name__", "UnknownAgent"))

    if store_trace:
        trace_dir = getattr(game_director.trace_loader, "full_path", None)
        result["trace_dir"] = str(trace_dir) if trace_dir else ""

    return result


def _apply_env_overrides(args):
    if args.llm_provider:
        os.environ["LLM_PROVIDER"] = args.llm_provider
    if args.llm_model:
        os.environ["LLM_MODEL"] = args.llm_model
        if (args.llm_provider or os.getenv("LLM_PROVIDER") or "").strip().lower() == "ollama":
            os.environ["OLLAMA_MODEL"] = args.llm_model
    if args.llm_api_base:
        os.environ["LLM_API_BASE"] = args.llm_api_base
    if args.ollama_base_url:
        os.environ["OLLAMA_BASE_URL"] = args.ollama_base_url
    if args.json_response:
        os.environ["LLM_JSON_RESPONSE_FORMAT"] = "1"
    if args.llm_timeout_s is not None:
        os.environ["LLM_TIMEOUT_S"] = str(args.llm_timeout_s)
    if args.llm_temperature is not None:
        os.environ["LLM_TEMPERATURE"] = str(args.llm_temperature)
    if args.llm_max_tokens is not None:
        os.environ["LLM_MAX_TOKENS"] = str(args.llm_max_tokens)


def _ensure_log_dir(run_id, explicit_log_dir=None):
    if explicit_log_dir:
        os.environ["LLM_LOG_DIR"] = explicit_log_dir
        os.makedirs(explicit_log_dir, exist_ok=True)
        return explicit_log_dir

    existing = (os.getenv("LLM_LOG_DIR") or "").strip()
    if existing:
        os.makedirs(existing, exist_ok=True)
        return existing

    auto_dir = os.path.join("llm_logs", run_id)
    os.makedirs(auto_dir, exist_ok=True)
    os.environ["LLM_LOG_DIR"] = auto_dir
    return auto_dir


def _read_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def _collect_llm_stats(log_dir):
    stats = {
        "calls_total": 0,
        "calls_initial_placement": 0,
        "calls_build_plan": 0,
        "errors_total": 0,
        "latency_ms_avg": None,
        "latency_ms_p95": None,
        "invalid_output": 0,
        "illegal_move": 0,
        "no_valid_actions": 0,
    }

    latencies = []

    if not log_dir or not os.path.isdir(log_dir):
        return stats

    for name in os.listdir(log_dir):
        if name.startswith("llm_log_") and name.endswith(".jsonl"):
            for row in _read_jsonl(os.path.join(log_dir, name)):
                if "error" in row:
                    stats["errors_total"] += 1
                    continue
                t_ms = row.get("t_ms")
                if isinstance(t_ms, int):
                    latencies.append(t_ms)
                stats["calls_total"] += 1

                phase = None
                req = row.get("request") or {}
                user = req.get("user") or {}
                if isinstance(user, dict):
                    phase = user.get("phase")
                if phase == "initial_placement":
                    stats["calls_initial_placement"] += 1
                elif phase == "build_plan":
                    stats["calls_build_plan"] += 1

        if name.startswith("llm_agent_events_") and name.endswith(".jsonl"):
            for row in _read_jsonl(os.path.join(log_dir, name)):
                evt = (row.get("event") or "").strip()
                if evt == "llm_invalid_output":
                    stats["invalid_output"] += 1
                elif evt == "llm_illegal_move":
                    stats["illegal_move"] += 1
                elif evt == "llm_no_valid_actions":
                    stats["no_valid_actions"] += 1

    if latencies:
        latencies_sorted = sorted(latencies)
        stats["latency_ms_avg"] = sum(latencies_sorted) / len(latencies_sorted)
        idx = int(round(0.95 * (len(latencies_sorted) - 1)))
        stats["latency_ms_p95"] = latencies_sorted[max(0, min(idx, len(latencies_sorted) - 1))]

    return stats


def _write_csv(path, header, rows, append=False):
    file_exists = os.path.exists(path)
    write_header = (not append) or (not file_exists)
    mode = "a" if append else "w"
    with open(path, mode=mode, newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(header)
        w.writerows(rows)


def _parse_args():
    p = argparse.ArgumentParser(description="Experimentos ligeros: LLMJsonAgent vs agentes estándar (3 oponentes).")

    p.add_argument("--agent", default="LLMJsonAgent.LLMJsonAgent", help="Agente a evaluar (módulo.clase).")
    p.add_argument("--matches", type=int, default=DEFAULT_MATCHES_PER_POSITION, help="Partidas por posición.")
    p.add_argument(
        "--positions",
        nargs="*",
        type=int,
        choices=[0, 1, 2, 3],
        default=list(DEFAULT_POSITIONS),
        help="Posiciones a evaluar (0-3).",
    )
    p.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS, help="Máximo de rondas por partida.")
    p.add_argument("--seed", type=int, default=None, help="Semilla base para reproducibilidad.")
    p.add_argument("--store-trace", action="store_true", help="Guarda trazas JSON (recomendado pocas partidas).")

    # Oponentes estándar
    p.add_argument(
        "--opponents",
        nargs="*",
        default=None,
        help=(
            "Tres oponentes (módulo.clase). Si se indican, se usan siempre (exactamente 3). "
            "Ej: AdrianHerasAgent.AdrianHerasAgent AlexPastorAgent.AlexPastorAgent SigmaAgent.SigmaAgent"
        ),
    )
    p.add_argument(
        "--opponent-sets",
        type=int,
        default=DEFAULT_OPPONENT_SETS,
        help="Número de tríos de oponentes a muestrear (si no usas --opponents).",
    )
    p.add_argument(
        "--opponent-pool",
        nargs="*",
        default=None,
        help="Pool para muestrear tríos (módulo.clase). Default: pool estándar del benchmark.",
    )
    p.add_argument(
        "--shuffle-opponents",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Baraja el orden de los 3 oponentes en cada partida (default: True).",
    )

    # Prompt profile (edita PROMPT_PROFILES arriba)
    p.add_argument("--prompt", default="baseline_v1", help="Nombre del prompt profile.")
    p.add_argument("--prompt-tag", default=None, help="Etiqueta a guardar en logs/CSVs (default: igual que --prompt).")

    # Output
    p.add_argument("--csv", default=DEFAULT_RESULTS_CSV, help="CSV de resultados (formato legacy).")
    p.add_argument("--details-csv", default=DEFAULT_DETAILS_CSV, help="CSV con detalle por partida.")
    p.add_argument("--runs-csv", default=DEFAULT_RUNS_CSV, help="CSV con resumen por ejecución.")
    p.add_argument("--append-csv", action="store_true", help="Añade resultados en vez de sobrescribir.")

    # LLM env helpers (opcional; puedes usar env vars directamente)
    p.add_argument("--llm-provider", default=None, help="Setea LLM_PROVIDER (ej: ollama).")
    p.add_argument("--llm-model", default=None, help="Setea LLM_MODEL (o OLLAMA_MODEL si usas env).")
    p.add_argument("--llm-api-base", default=None, help="Setea LLM_API_BASE.")
    p.add_argument("--ollama-base-url", default=None, help="Setea OLLAMA_BASE_URL.")
    p.add_argument("--json-response", action="store_true", help="Setea LLM_JSON_RESPONSE_FORMAT=1.")
    p.add_argument("--llm-timeout-s", type=float, default=None, help="Setea LLM_TIMEOUT_S.")
    p.add_argument("--llm-temperature", type=float, default=None, help="Setea LLM_TEMPERATURE.")
    p.add_argument("--llm-max-tokens", type=int, default=None, help="Setea LLM_MAX_TOKENS.")
    p.add_argument("--log-dir", default=None, help="Directorio para LLM_LOG_DIR (si no, auto por run).")

    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    _apply_env_overrides(args)

    run_id = _timestamp_id()

    prompt_profile = PROMPT_PROFILES.get(args.prompt)
    if prompt_profile is None:
        raise SystemExit(f"Prompt profile desconocido: {args.prompt}. Disponibles: {sorted(PROMPT_PROFILES.keys())}")

    prompt_tag = args.prompt_tag if args.prompt_tag is not None else args.prompt
    os.environ["LLM_PROMPT_TAG"] = prompt_tag

    agent_cls = cargar_agente(args.agent)
    agent_is_llm = _is_llm_agent_class(agent_cls)

    log_dir = ""
    if agent_is_llm:
        try:
            from Agents.LLMClient import create_chat_client_from_env

            if create_chat_client_from_env() is None:
                print(
                    "\n[AVISO] LLM no configurado (no hay cliente). "
                    "LLMJsonAgent se comportará como RandomAgent.\n"
                    "Ejemplo (PowerShell):\n"
                    "  $env:LLM_PROVIDER='ollama'\n"
                    "  $env:OLLAMA_MODEL='llama3.1:8b'\n"
                )
        except Exception:
            pass

        log_dir = _ensure_log_dir(run_id, explicit_log_dir=args.log_dir)

    # Inyectamos prompts en el agente (sin depender de env vars).
    if agent_is_llm:
        agent_cls = crear_clase_agente_configurada(
            agent_cls,
            prompt_tag=prompt_tag,
            start_system_prompt=prompt_profile["start_system_prompt"],
            build_system_prompt=prompt_profile["build_system_prompt"],
        )

    # Preparar oponentes estándar (3 oponentes por partida).
    def _normalize_agent_path(path):
        path = str(path or "").strip()
        if not path:
            return ""
        return path if path.startswith("Agents.") else f"Agents.{path}"

    def _unique_preserve_order(items):
        seen = set()
        out = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    opponent_pool = args.opponent_pool if args.opponent_pool else list(STANDARD_OPPONENT_POOL)
    opponent_pool = [_normalize_agent_path(p) for p in opponent_pool if str(p or "").strip()]
    opponent_pool = _unique_preserve_order(opponent_pool)

    opponents_mode = "sampled"
    opponent_sets = []
    if args.opponents:
        opps = [_normalize_agent_path(p) for p in args.opponents if str(p or "").strip()]
        if len(opps) != 3:
            raise SystemExit("--opponents requiere exactamente 3 agentes (módulo.clase).")
        opponent_sets = [opps]
        opponents_mode = "fixed"
    else:
        if len(opponent_pool) < 3:
            raise SystemExit("La pool de oponentes debe tener al menos 3 agentes.")
        n_sets = max(1, int(args.opponent_sets))
        rng = random.Random(int(args.seed)) if args.seed is not None else random.Random()
        for _ in range(n_sets):
            opponent_sets.append(rng.sample(opponent_pool, 3))

    agent_cache = {}

    def _load_agent_cached(path):
        path = _normalize_agent_path(path)
        if path not in agent_cache:
            agent_cache[path] = cargar_agente(path)
        return agent_cache[path]

    opponent_sets_loaded = [[_load_agent_cached(p) for p in trio] for trio in opponent_sets]

    extra_tags = ["bench=estandar", f"oppsets={len(opponent_sets_loaded)}"]
    agent_name = _agent_label(agent_cls, prompt_tag=prompt_tag if agent_is_llm else "", extra_tags=extra_tags)

    config_obj = {
        "run_id": run_id,
        "agent": args.agent,
        "agent_label": agent_name,
        "llm": {
            "provider": (os.getenv("LLM_PROVIDER") or "").strip(),
            "model": (os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "").strip(),
            "base_url": (os.getenv("OLLAMA_BASE_URL") or os.getenv("LLM_API_BASE") or "").strip(),
            "timeout_s": (os.getenv("LLM_TIMEOUT_S") or "").strip(),
            "temperature": (os.getenv("LLM_TEMPERATURE") or "").strip(),
            "max_tokens": (os.getenv("LLM_MAX_TOKENS") or "").strip(),
            "json_response_format": (os.getenv("LLM_JSON_RESPONSE_FORMAT") or "").strip(),
            "log_dir": log_dir,
            "prompt_tag": prompt_tag,
            "prompt_profile": args.prompt,
            "start_system_prompt": prompt_profile["start_system_prompt"],
            "build_system_prompt": prompt_profile["build_system_prompt"],
            "start_prompt_sha256": _sha256_text(prompt_profile["start_system_prompt"]),
            "build_prompt_sha256": _sha256_text(prompt_profile["build_system_prompt"]),
        },
        "benchmark": {
            "matches_per_position": int(args.matches),
            "positions": list(args.positions),
            "max_rounds": int(args.max_rounds),
            "seed": args.seed,
            "store_trace": bool(args.store_trace),
            "opponents_mode": opponents_mode,
            "opponent_pool": opponent_pool,
            "opponent_sets": opponent_sets,
            "shuffle_opponents": bool(args.shuffle_opponents),
        },
    }

    if log_dir:
        with open(os.path.join(log_dir, "run_config.json"), "w", encoding="utf-8") as f:
            json.dump(config_obj, f, ensure_ascii=False, indent=2)

    total_games = max(1, int(args.matches)) * len(args.positions) * len(opponent_sets_loaded)
    print(
        f"\n== {agent_name} ==\nPartidas totales: {total_games} | oppsets={len(opponent_sets_loaded)} "
        f"| posiciones={args.positions} | matches={args.matches}\n"
    )
    for idx, trio in enumerate(opponent_sets_loaded, start=1):
        trio_names = ", ".join(str(getattr(a, "__name__", "UnknownAgent")) for a in trio)
        print(f"- OppSet {idx}: {trio_names}")
    print(f"- shuffle_opponents={bool(args.shuffle_opponents)}\n")

    all_results = []
    started_all = time.time()
    game_idx = 0

    for opp_set_idx, opponent_trio in enumerate(opponent_sets_loaded, start=1):
        for pos in args.positions:
            for m in range(int(args.matches)):
                game_idx += 1

                if args.seed is not None:
                    random.seed(int(args.seed) + game_idx)

                r = _run_match(
                    agent_cls=agent_cls,
                    opponent_classes=opponent_trio,
                    position=pos,
                    max_rounds=int(args.max_rounds),
                    store_trace=bool(args.store_trace),
                    game_number=game_idx,
                    shuffle_opponents=bool(args.shuffle_opponents),
                )
                r["run_id"] = run_id
                r["game_index"] = game_idx
                r["opponent_set_index"] = opp_set_idx
                r["position"] = pos
                all_results.append(r)

                status = (
                    "WIN"
                    if r["victory"]
                    else ("TIMEOUT" if r["timeout"] else ("DRAW" if r["draw"] else "LOSS"))
                )
                winner_str = r["winner"] or "-"
                print(
                    f"[{game_idx}/{total_games}] set={opp_set_idx} pos={pos} {status} "
                    f"agentVP={r['points']} maxVP={r['max_vp']} winner={winner_str} "
                    f"rounds={r['rounds_played']} t={r['duration_s']:.1f}s"
                )

    duration_all_s = time.time() - started_all

    wins = sum(r["victory"] for r in all_results)
    points_sum = sum(r["points"] for r in all_results)
    rank_sum = sum(r["rank"] for r in all_results)
    draws = sum(r["draw"] for r in all_results)
    timeouts = sum(r["timeout"] for r in all_results)
    rounds_avg = sum(r["rounds_played"] for r in all_results) / len(all_results)
    avg_game_s = duration_all_s / len(all_results)

    ratio_victorias = wins / len(all_results)
    media_puntos = points_sum / len(all_results)
    puesto_medio = rank_sum / len(all_results)

    # CSV legacy (mismo formato que los benchmarks existentes)
    _write_csv(
        args.csv,
        ["Agente", "Victorias", "Puntos", "Partidas", "Ratio Victorias", "Media Puntos", "Puesto Medio"],
        [
            [
                agent_name,
                wins,
                points_sum,
                len(all_results),
                f"{ratio_victorias:.4f}",
                f"{media_puntos:.2f}",
                f"{puesto_medio:.2f}",
            ]
        ],
        append=args.append_csv,
    )

    # CSV detalle por partida
    details_header = [
        "run_id",
        "game_index",
        "opponent_set_index",
        "position",
        "seat_J0_agent",
        "seat_J1_agent",
        "seat_J2_agent",
        "seat_J3_agent",
        "victory",
        "winner",
        "draw",
        "timeout",
        "rounds_played",
        "duration_s",
        "agent_points",
        "agent_rank",
        "max_vp",
        "tie_for_first",
        "has_victory_condition",
        "vp_J0",
        "vp_J1",
        "vp_J2",
        "vp_J3",
        "trace_dir",
    ]
    details_rows = []
    for r in all_results:
        vp = r.get("vp") or {}
        details_rows.append(
            [
                run_id,
                r.get("game_index"),
                r.get("opponent_set_index"),
                r.get("position"),
                r.get("seat_J0_agent", ""),
                r.get("seat_J1_agent", ""),
                r.get("seat_J2_agent", ""),
                r.get("seat_J3_agent", ""),
                r.get("victory"),
                r.get("winner") or "",
                r.get("draw"),
                r.get("timeout"),
                r.get("rounds_played"),
                f"{float(r.get('duration_s') or 0.0):.3f}",
                r.get("points"),
                r.get("rank"),
                r.get("max_vp"),
                int(bool(r.get("tie_for_first"))),
                int(bool(r.get("has_victory_condition"))),
                vp.get("J0", ""),
                vp.get("J1", ""),
                vp.get("J2", ""),
                vp.get("J3", ""),
                r.get("trace_dir", ""),
            ]
        )
    _write_csv(args.details_csv, details_header, details_rows, append=args.append_csv)

    llm_stats = _collect_llm_stats(log_dir) if agent_is_llm else {}

    runs_header = [
        "run_id",
        "timestamp",
        "agent",
        "agent_label",
        "provider",
        "model",
        "prompt_tag",
        "prompt_profile",
        "start_prompt_sha256",
        "build_prompt_sha256",
        "matches_per_position",
        "positions",
        "max_rounds",
        "seed",
        "games",
        "wins",
        "win_rate",
        "avg_points",
        "avg_rank",
        "draws",
        "timeouts",
        "avg_rounds",
        "duration_s",
        "avg_game_s",
        "llm_calls_total",
        "llm_calls_initial_placement",
        "llm_calls_build_plan",
        "llm_errors_total",
        "llm_latency_ms_avg",
        "llm_latency_ms_p95",
        "llm_invalid_output",
        "llm_illegal_move",
        "llm_no_valid_actions",
        "log_dir",
    ]

    llm_meta = config_obj.get("llm", {})
    runs_row = [
        run_id,
        run_id,
        args.agent,
        agent_name,
        llm_meta.get("provider", ""),
        llm_meta.get("model", ""),
        prompt_tag,
        args.prompt,
        llm_meta.get("start_prompt_sha256", ""),
        llm_meta.get("build_prompt_sha256", ""),
        int(args.matches),
        " ".join(str(p) for p in args.positions),
        int(args.max_rounds),
        "" if args.seed is None else int(args.seed),
        len(all_results),
        wins,
        f"{ratio_victorias:.4f}",
        f"{media_puntos:.2f}",
        f"{puesto_medio:.2f}",
        draws,
        timeouts,
        f"{rounds_avg:.2f}",
        f"{duration_all_s:.3f}",
        f"{avg_game_s:.3f}",
        llm_stats.get("calls_total", ""),
        llm_stats.get("calls_initial_placement", ""),
        llm_stats.get("calls_build_plan", ""),
        llm_stats.get("errors_total", ""),
        f"{llm_stats.get('latency_ms_avg'):.2f}" if llm_stats.get("latency_ms_avg") is not None else "",
        llm_stats.get("latency_ms_p95", ""),
        llm_stats.get("invalid_output", ""),
        llm_stats.get("illegal_move", ""),
        llm_stats.get("no_valid_actions", ""),
        log_dir,
    ]
    _write_csv(args.runs_csv, runs_header, [runs_row], append=True)

    print(f"\nResultados legacy: {args.csv}")
    print(f"Detalle partidas: {args.details_csv}")
    print(f"Resumen ejecuciones: {args.runs_csv}")
    if log_dir:
        print(f"LLM logs/config: {log_dir}")
