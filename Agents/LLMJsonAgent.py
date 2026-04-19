import os

from Agents.LLMClient import create_chat_client_from_env
from Agents.RandomAgent import RandomAgent
from Classes.Constants import BuildConstants, HarborConstants, TerrainConstants


def _dice_weight(number):
    # Expected relative frequency for 2d6 outcomes (excluding 7 which yields no resources).
    return {
        2: 1,
        3: 2,
        4: 3,
        5: 4,
        6: 5,
        8: 5,
        9: 4,
        10: 3,
        11: 2,
        12: 1,
    }.get(number, 0)


def _top_starting_candidates(board, k=12):
    valid = board.valid_starting_nodes()
    scored = []
    for node_id in valid:
        score = 0
        for ter_id in board.nodes[node_id]["contacting_terrain"]:
            terrain = board.terrain[ter_id]
            if terrain["terrain_type"] == TerrainConstants.DESERT:
                continue
            score += _dice_weight(terrain["probability"])

        scored.append((score, node_id))

    scored.sort(reverse=True)
    top = scored[: max(1, min(k, len(scored)))]
    return [node_id for _, node_id in top]


class LLMJsonAgent(RandomAgent):
    """
    Hybrid agent:
    - Uses a (remote) LLM to decide initial placement and a small build plan per turn.
    - Falls back to RandomAgent behaviour on any invalid output / missing credentials / errors.

    Configuration (environment variables):
    - LLM_PROVIDER: openai_compat (default), ollama, bedrock
    - LLM_MODEL (provider-dependent)
    - Optional: LLM_TIMEOUT_S, LLM_TEMPERATURE, LLM_MAX_TOKENS
    - Optional: LLM_LOG_DIR (writes jsonl logs, one file per process)
    - Optional: LLM_BUILD_ACTIONS (default 3)
    - Optional: LLM_START_CANDIDATES (default 12)
    """

    def __init__(self, agent_id, max_build_actions=None, start_candidates=None, **kwargs):
        super().__init__(agent_id)
        self._llm = create_chat_client_from_env()
        self._build_queue = []
        self._build_planned_this_turn = False

        try:
            self._max_build_actions = int(max_build_actions or os.getenv("LLM_BUILD_ACTIONS") or 3)
            self._start_candidates = int(start_candidates or os.getenv("LLM_START_CANDIDATES") or 12)
        except Exception:
            self._max_build_actions = 3
            self._start_candidates = 12

    def on_turn_start(self):
        self._build_queue = []
        self._build_planned_this_turn = False
        return super().on_turn_start()

    def on_game_start(self, board_instance):
        self.board = board_instance
        if not self._llm:
            return super().on_game_start(board_instance)

        valid_nodes = board_instance.valid_starting_nodes()
        candidates = _top_starting_candidates(board_instance, k=self._start_candidates)
        candidate_objs = []
        for node_id in candidates:
            terrains = []
            for ter_id in board_instance.nodes[node_id]["contacting_terrain"]:
                ter = board_instance.terrain[ter_id]
                terrains.append(
                    {
                        "id": ter_id,
                        "type": int(ter["terrain_type"]),
                        "dice": int(ter["probability"]),
                        "w": int(_dice_weight(ter["probability"])),
                    }
                )
            candidate_objs.append(
                {
                    "node_id": int(node_id),
                    "coastal": bool(board_instance.is_coastal_node(node_id)),
                    "harbor": int(board_instance.nodes[node_id].get("harbor", HarborConstants.NONE)),
                    "adjacent": [int(n) for n in board_instance.nodes[node_id]["adjacent"]],
                    "terrains": terrains,
                }
            )

        system = (
            "You play Settlers of Catan. Return ONLY valid JSON. No markdown, no extra text. "
            "Choose a legal starting placement from the provided candidates."
        )
        user = {
            "phase": "initial_placement",
            "player_id": int(self.id),
            "candidates": candidate_objs,
            "output_schema": {"node_id": "int", "road_to": "int"},
        }
        decision = self._llm.chat_json(system, user)
        if not isinstance(decision, dict):
            return super().on_game_start(board_instance)

        try:
            node_id = int(decision.get("node_id"))
            road_to = int(decision.get("road_to"))
        except Exception:
            return super().on_game_start(board_instance)

        if node_id not in valid_nodes:
            return super().on_game_start(board_instance)
        if road_to not in board_instance.nodes[node_id]["adjacent"]:
            return super().on_game_start(board_instance)

        return node_id, road_to

    def on_build_phase(self, board_instance):
        self.board = board_instance

        if self._build_queue:
            return self._build_queue.pop(0)

        if not self._llm:
            return super().on_build_phase(board_instance)

        if not self._build_planned_this_turn:
            self._build_planned_this_turn = True
            plan = self._request_build_plan(board_instance)
            if plan:
                self._build_queue = plan
                return self._build_queue.pop(0)

        return super().on_build_phase(board_instance)

    def _request_build_plan(self, board_instance):
        can_afford = {
            "city": bool(self.hand.resources.has_more(BuildConstants.CITY)),
            "town": bool(self.hand.resources.has_more(BuildConstants.TOWN)),
            "road": bool(self.hand.resources.has_more(BuildConstants.ROAD)),
            "card": bool(self.hand.resources.has_more(BuildConstants.CARD)),
        }

        valid = {
            "city_nodes": [int(n) for n in board_instance.valid_city_nodes(self.id)],
            "town_nodes": [int(n) for n in board_instance.valid_town_nodes(self.id)],
            "road_edges": [
                {"node_id": int(e["starting_node"]), "road_to": int(e["finishing_node"])}
                for e in board_instance.valid_road_nodes(self.id)
            ],
        }

        system = (
            "You control a Catan agent. Return ONLY valid JSON. No markdown, no extra text. "
            "Propose a short build plan using ONLY the legal moves given. "
            "If you want to stop building, return an action with building='none'."
        )
        user = {
            "phase": "build_plan",
            "player_id": int(self.id),
            "hand": {
                "cereal": int(self.hand.resources.cereal),
                "mineral": int(self.hand.resources.mineral),
                "clay": int(self.hand.resources.clay),
                "wood": int(self.hand.resources.wood),
                "wool": int(self.hand.resources.wool),
            },
            "can_afford": can_afford,
            "legal_moves": valid,
            "max_actions": int(self._max_build_actions),
            "output_schema": {
                "actions": [
                    {"building": "city|town|road|card|none", "node_id": "int?", "road_to": "int?"}
                ]
            },
        }

        decision = self._llm.chat_json(system, user)
        if not isinstance(decision, dict):
            return None

        actions = decision.get("actions")
        if not isinstance(actions, list):
            return None

        city_nodes = set(valid["city_nodes"])
        town_nodes = set(valid["town_nodes"])
        road_edges = {(e["node_id"], e["road_to"]) for e in valid["road_edges"]}

        planned = []
        for action in actions[: self._max_build_actions]:
            if not isinstance(action, dict):
                continue
            building = str(action.get("building", "")).strip().lower()
            if building in ("none", "pass", ""):
                break

            if building == BuildConstants.CARD:
                if not can_afford["card"]:
                    continue
                planned.append({"building": BuildConstants.CARD})
                continue

            try:
                node_id = int(action.get("node_id"))
            except Exception:
                continue

            if building == BuildConstants.CITY:
                if not can_afford["city"]:
                    continue
                if node_id in city_nodes:
                    planned.append({"building": BuildConstants.CITY, "node_id": node_id})
                continue

            if building == BuildConstants.TOWN:
                if not can_afford["town"]:
                    continue
                if node_id in town_nodes:
                    planned.append({"building": BuildConstants.TOWN, "node_id": node_id})
                continue

            if building == BuildConstants.ROAD:
                if not can_afford["road"]:
                    continue
                try:
                    road_to = int(action.get("road_to"))
                except Exception:
                    continue
                if (node_id, road_to) in road_edges:
                    planned.append(
                        {"building": BuildConstants.ROAD, "node_id": node_id, "road_to": road_to}
                    )
                continue

        return planned or None
