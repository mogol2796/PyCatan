import random

from Classes.Constants import MaterialConstants, BuildConstants
from Classes.Materials import Materials
from Classes.TradeOffer import TradeOffer
from Interfaces.AgentInterface import AgentInterface


class CardRoadThiefAgent_v2(AgentInterface):
    """
    Agent that prioritizes buying development cards > building roads > building cities/towns.
    The thief is placed strategically to block the player with the most Victory Points,
    choosing the tile with the highest expected value (based on token probability and multipliers
    for cities and towns), while continuing to avoid tiles that block the agent's own resources.
    Other behavior is inherently random, like RandomAgent.
    """
    def __init__(self, agent_id):
        super().__init__(agent_id)

    def on_trade_offer(self, board_instance, offer=TradeOffer(), player_id=int):
        answer = random.randint(0, 2)
        if answer:
            if answer == 2:
                gives = Materials(random.randint(0, self.hand.resources.cereal),
                                  random.randint(0, self.hand.resources.mineral),
                                  random.randint(0, self.hand.resources.clay),
                                  random.randint(0, self.hand.resources.wood),
                                  random.randint(0, self.hand.resources.wool))
                receives = Materials(random.randint(0, self.hand.resources.cereal),
                                     random.randint(0, self.hand.resources.mineral),
                                     random.randint(0, self.hand.resources.clay),
                                     random.randint(0, self.hand.resources.wood),
                                     random.randint(0, self.hand.resources.wool))
                return TradeOffer(gives, receives)
            else:
                return True
        else:
            return False

    def on_turn_start(self):
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)
        return None

    def on_having_more_than_7_materials_when_thief_is_called(self):
        return self.hand

    def on_moving_thief(self):
        # Calculate apparent Victory Points (vp) of all players based on buildings on the board.
        # This will be used to target the player with the highest VP.
        vp_scores = {0: 0, 1: 0, 2: 0, 3: 0}
        for node in self.board.nodes:
            if node['player'] != -1:
                # 2 VP for city, 1 VP for town/settlement
                vp_scores[node['player']] += 2 if node['has_city'] else 1

        # Sort opponents by their VP in descending order
        opponents = [p for p in range(4) if p != self.id]
        opponents.sort(key=lambda p: vp_scores[p], reverse=True)

        # Helper to convert a token number to its probabilistic base (dots). e.g. 8 => 5, 2 => 1, 10 => 3
        # Allows giving highest base value to most probable tokens like 6 and 8.
        def get_prob_base(token):
            if token in [0, 7]:
                return 0
            return 6 - abs(7 - token)

        # Gather terrains where we don't have our own buildings, to avoid blocking ourselves,
        # and where the thief is not currently stationed.
        valid_terrains = []
        for t_dict in self.board.terrain:
            if t_dict.get('has_thief', False):
                continue
            
            has_my_building = False
            for node_id in t_dict['contacting_nodes']:
                if self.board.nodes[node_id]['player'] == self.id:
                    has_my_building = True
                    break
            
            if not has_my_building:
                valid_terrains.append(t_dict['id'])

        best_terrain = -1
        target_player = -1

        # Iterate opponent by opponent (starting with the highest VP)
        for opp in opponents:
            best_t_for_opp = -1
            max_v = -1
            
            # Evaluate valid terrains for this opponent to find the highest value tile
            for t_id in valid_terrains:
                t_dict = self.board.terrain[t_id]
                base_prob = get_prob_base(t_dict['probability'])
                
                if base_prob == 0:
                    continue
                
                multiplier = 0.0
                has_opp = False
                for node_id in t_dict['contacting_nodes']:
                    node = self.board.nodes[node_id]
                    if node['player'] == opp:
                        has_opp = True
                        # City x2 multiplier, Village x1.5 multiplier
                        multiplier += 2.0 if node['has_city'] else 1.5
                
                if has_opp:
                    # Tile value = base * sum of multipliers
                    val = base_prob * multiplier
                    if val > max_v:
                        max_v = val
                        best_t_for_opp = t_id
            
            # Once we find at least one tile to block for the top opponent, commit to it
            if best_t_for_opp != -1:
                best_terrain = best_t_for_opp
                target_player = opp
                break

        # Fallbacks: If no opponent has buildings in terrains without ours, pick randomly
        if best_terrain == -1:
            if len(valid_terrains) > 0:
                best_terrain = random.choice(valid_terrains)
            else:
                # Total fallback if we literally occupy every single terrain
                all_t = [t['id'] for t in self.board.terrain if not t.get('has_thief', False)]
                best_terrain = random.choice(all_t) if len(all_t) > 0 else random.randint(0, 18)

            # Pick a random opponent present in the selected tile
            possible_targets = []
            for node_id in self.board.terrain[best_terrain]['contacting_nodes']:
                occupier = self.board.nodes[node_id]['player']
                if occupier != -1 and occupier != self.id:
                    possible_targets.append(occupier)
            
            target_player = random.choice(possible_targets) if len(possible_targets) > 0 else -1

        return {'terrain': best_terrain, 'player': target_player}

    def on_turn_end(self):
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)
        return None

    def on_commerce_phase(self):
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        answer = random.randint(0, 1)
        if answer:
            if self.hand.resources.cereal >= 4:
                return {'gives': MaterialConstants.CEREAL, 'receives': MaterialConstants.MINERAL}
            if self.hand.resources.mineral >= 4:
                return {'gives': MaterialConstants.MINERAL, 'receives': MaterialConstants.CEREAL}
            if self.hand.resources.clay >= 4:
                return {'gives': MaterialConstants.CLAY, 'receives': MaterialConstants.CEREAL}
            if self.hand.resources.wood >= 4:
                return {'gives': MaterialConstants.WOOD, 'receives': MaterialConstants.CEREAL}
            if self.hand.resources.wool >= 4:
                return {'gives': MaterialConstants.WOOL, 'receives': MaterialConstants.CEREAL}

            return None
        else:
            gives = Materials(random.randint(0, self.hand.resources.cereal),
                              random.randint(0, self.hand.resources.mineral),
                              random.randint(0, self.hand.resources.clay),
                              random.randint(0, self.hand.resources.wood),
                              random.randint(0, self.hand.resources.wool))
            receives = Materials(random.randint(0, self.hand.resources.cereal),
                                 random.randint(0, self.hand.resources.mineral),
                                 random.randint(0, self.hand.resources.clay),
                                 random.randint(0, self.hand.resources.wood),
                                 random.randint(0, self.hand.resources.wool))
            trade_offer = TradeOffer(gives, receives)
            return trade_offer

    def on_build_phase(self, board_instance):
        self.board = board_instance

        # Allows the use of development cards randomly just like RandomAgent.py
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        # 1. Dev Card First
        if self.hand.resources.has_more(BuildConstants.CARD):
            return {'building': BuildConstants.CARD}
        
        # 2. Road Second
        if self.hand.resources.has_more(BuildConstants.ROAD):
            valid_road_nodes = self.board.valid_road_nodes(self.id)
            if len(valid_road_nodes) > 0:
                road_node = random.randint(0, len(valid_road_nodes) - 1)
                return {'building': BuildConstants.ROAD,
                        'node_id': valid_road_nodes[road_node]['starting_node'],
                        'road_to': valid_road_nodes[road_node]['finishing_node']}

        # 3. If neither is possible or no place for road, build randomly between City or Town
        options = []
        
        if self.hand.resources.has_more(BuildConstants.TOWN):
            valid_town_nodes = self.board.valid_town_nodes(self.id)
            if len(valid_town_nodes) > 0:
                options.append({'type': BuildConstants.TOWN, 'nodes': valid_town_nodes})

        if self.hand.resources.has_more(BuildConstants.CITY):
            valid_city_nodes = self.board.valid_city_nodes(self.id)
            if len(valid_city_nodes) > 0:
                options.append({'type': BuildConstants.CITY, 'nodes': valid_city_nodes})

        # Pick randomly between the available Town/City options (if any are possible)
        if len(options) > 0:
            choice = random.choice(options)
            node_idx = random.randint(0, len(choice['nodes']) - 1)
            return {'building': choice['type'], 'node_id': choice['nodes'][node_idx]}

        return None

    def on_game_start(self, board_instance):
        return super().on_game_start(board_instance)

    def on_monopoly_card_use(self):
        material = random.randint(0, 4)
        return material

    # noinspection DuplicatedCode
    def on_road_building_card_use(self):
        valid_nodes = self.board.valid_road_nodes(self.id)
        if len(valid_nodes) > 1:
            while True:
                road_node = random.randint(0, len(valid_nodes) - 1)
                road_node_2 = random.randint(0, len(valid_nodes) - 1)
                if road_node != road_node_2:
                    return {'node_id': valid_nodes[road_node]['starting_node'],
                            'road_to': valid_nodes[road_node]['finishing_node'],
                            'node_id_2': valid_nodes[road_node_2]['starting_node'],
                            'road_to_2': valid_nodes[road_node_2]['finishing_node'],
                            }
        elif len(valid_nodes) == 1:
            return {'node_id': valid_nodes[0]['starting_node'],
                    'road_to': valid_nodes[0]['finishing_node'],
                    'node_id_2': None,
                    'road_to_2': None,
                    }
        return None

    def on_year_of_plenty_card_use(self):
        material, material2 = random.randint(0, 4), random.randint(0, 4)
        return {'material': material, 'material_2': material2}
