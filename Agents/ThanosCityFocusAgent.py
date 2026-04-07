import random

from Classes.Constants import MaterialConstants, BuildConstants, HarborConstants, TerrainConstants
from Classes.Materials import Materials
from Classes.TradeOffer import TradeOffer
from Interfaces.AgentInterface import AgentInterface


class ThanosCityFocusAgent(AgentInterface):
    """
    The ultimate Catan strategist Thanos.
    1. Perfect heuristic village placement (avoids deserts/bad numbers).
    2. Savage thief movement focusing purely on mathematically hindering the top player.
    3. Construct building priorities sequentially: City > Town > Dev Card > Road.
    4. Seamless trading machine connecting precise player trade offers bouncing down
       to optimized port/bank execution.
    """
    def __init__(self, agent_id):
        super().__init__(agent_id)
        self.trade_queue_active = False
        self.tried_targets_player = set()
        self.failed_bank_trades = set()

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
        self.trade_queue_active = False
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)
        return None

    def on_having_more_than_7_materials_when_thief_is_called(self):
        return self.hand

    def on_turn_end(self):
        self.trade_queue_active = False
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)
        return None

    def on_game_start(self, board_instance):
        self.board = board_instance
        valid_nodes = self.board.valid_starting_nodes()
        
        if not valid_nodes:
            return super().on_game_start(board_instance)

        best_node = None
        best_score = -float('inf')

        for node_id in valid_nodes:
            score = 0
            node = self.board.nodes[node_id]
            terrains = [self.board.terrain[t_id] for t_id in node['contacting_terrain']]
            types_set = set()

            bad_number_found = False
            desert_found = False
            for t in terrains:
                prob = t['probability']
                t_type = t['terrain_type']

                if prob in [1, 2, 11, 12]:
                    bad_number_found = True

                if t_type == TerrainConstants.DESERT:
                    desert_found = True

                if prob in [6, 8]:
                    score += 10

                if t_type in [TerrainConstants.CEREAL, TerrainConstants.MINERAL]:
                    score += 5

                if t_type != TerrainConstants.DESERT:
                    types_set.add(t_type)

            # Hard avoid 1, 2, 11, 12
            if bad_number_found:
                score -= 5

            # Avoid the desert like the plague
            if desert_found:
                score -= 1000

            # Diversify resources
            score += len(types_set) * 2

            if score > best_score:
                best_score = score
                best_node = node_id

        possible_roads = self.board.nodes[best_node]['adjacent']
        road_to = possible_roads[random.randint(0, len(possible_roads) - 1)]

        return best_node, road_to

    def on_moving_thief(self):
        # Calculate apparent Victory Points (vp)
        vp_scores = {0: 0, 1: 0, 2: 0, 3: 0}
        for node in self.board.nodes:
            if node['player'] != -1:
                vp_scores[node['player']] += 2 if node['has_city'] else 1

        opponents = [p for p in range(4) if p != self.id]
        opponents.sort(key=lambda p: vp_scores[p], reverse=True)

        def get_prob_base(token):
            if token in [0, 7]: return 0
            return 6 - abs(7 - token)

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

        for opp in opponents:
            best_t_for_opp = -1
            max_v = -1
            
            for t_id in valid_terrains:
                t_dict = self.board.terrain[t_id]
                base_prob = get_prob_base(t_dict['probability'])
                
                if base_prob == 0: continue
                
                multiplier = 0.0
                has_opp = False
                for node_id in t_dict['contacting_nodes']:
                    node = self.board.nodes[node_id]
                    if node['player'] == opp:
                        has_opp = True
                        multiplier += 2.0 if node['has_city'] else 1.5
                
                if has_opp:
                    val = base_prob * multiplier
                    if val > max_v:
                        max_v = val
                        best_t_for_opp = t_id
            
            if best_t_for_opp != -1:
                best_terrain = best_t_for_opp
                target_player = opp
                break

        if best_terrain == -1:
            if len(valid_terrains) > 0:
                best_terrain = random.choice(valid_terrains)
            else:
                all_t = [t['id'] for t in self.board.terrain if not t.get('has_thief', False)]
                best_terrain = random.choice(all_t) if len(all_t) > 0 else random.randint(0, 18)

            possible_targets = []
            for node_id in self.board.terrain[best_terrain]['contacting_nodes']:
                occupier = self.board.nodes[node_id]['player']
                if occupier != -1 and occupier != self.id:
                    possible_targets.append(occupier)
            
            target_player = random.choice(possible_targets) if len(possible_targets) > 0 else -1

        return {'terrain': best_terrain, 'player': target_player}

    def on_build_phase(self, board_instance):
        self.board = board_instance

        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        # 1. City
        if self.hand.resources.has_more(BuildConstants.CITY):
            valid_nodes = self.board.valid_city_nodes(self.id)
            if len(valid_nodes):
                city_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.CITY, 'node_id': valid_nodes[city_node]}

        # 2. Town / Village
        if self.hand.resources.has_more(BuildConstants.TOWN):
            valid_nodes = self.board.valid_town_nodes(self.id)
            if len(valid_nodes):
                town_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.TOWN, 'node_id': valid_nodes[town_node]}

        # 3. Development Card
        if self.hand.resources.has_more(BuildConstants.CARD):
            return {'building': BuildConstants.CARD}

        # 4. Road
        if self.hand.resources.has_more(BuildConstants.ROAD):
            valid_nodes = self.board.valid_road_nodes(self.id)
            if len(valid_nodes):
                road_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.ROAD,
                        'node_id': valid_nodes[road_node]['starting_node'],
                        'road_to': valid_nodes[road_node]['finishing_node']}

        return None

    def on_commerce_phase(self):
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        if not getattr(self, 'trade_queue_active', False):
            self.trade_queue_active = True
            self.tried_targets_player = set()
            self.failed_bank_trades = set()

        cereal = self.hand.resources.cereal
        ore = self.hand.resources.mineral
        clay = self.hand.resources.clay
        wood = self.hand.resources.wood
        wool = self.hand.resources.wool
        
        # Target 1: City (2 Cereal, 3 Ore)
        miss_cereal_c = max(0, 2 - cereal)
        miss_ore_c = max(0, 3 - ore)
        miss_city = miss_cereal_c + miss_ore_c
        surplus_city = {
            'cereal': max(0, cereal - 2), 'mineral': max(0, ore - 3),
            'clay': clay, 'wood': wood, 'wool': wool
        }
        
        # Target 2: Town/Village (1 Cereal, 1 Wood, 1 Clay, 1 Wool)
        miss_cereal_v = max(0, 1 - cereal)
        miss_wood_v = max(0, 1 - wood)
        miss_clay_v = max(0, 1 - clay)
        miss_wool_v = max(0, 1 - wool)
        miss_village = miss_cereal_v + miss_wood_v + miss_clay_v + miss_wool_v
        surplus_village = {
            'cereal': max(0, cereal - 1), 'mineral': ore,
            'clay': max(0, clay - 1), 'wood': max(0, wood - 1), 'wool': max(0, wool - 1)
        }

        # Target 3: Development Card (1 Cereal, 1 Ore, 1 Wool)
        miss_cereal_d = max(0, 1 - cereal)
        miss_ore_d = max(0, 1 - ore)
        miss_wool_d = max(0, 1 - wool)
        miss_card = miss_cereal_d + miss_ore_d + miss_wool_d
        surplus_card = {
            'cereal': max(0, cereal - 1), 'mineral': max(0, ore - 1), 'wool': max(0, wool - 1),
            'clay': clay, 'wood': wood
        }
        
        # Target 4: Road (1 Wood, 1 Clay)
        miss_wood_r = max(0, 1 - wood)
        miss_clay_r = max(0, 1 - clay)
        miss_road = miss_wood_r + miss_clay_r
        surplus_road = {
            'cereal': cereal, 'mineral': ore,
            'clay': max(0, clay - 1), 'wood': max(0, wood - 1), 'wool': wool
        }
        
        # Assign corresponding bases (City = 4, Town = 3, Dev Card = 2, Road = 1)
        targets = [
            {'type': 'city', 'score': 4 - miss_city, 'missing': miss_city,
             'req': {'cereal': miss_cereal_c, 'mineral': miss_ore_c, 'clay': 0, 'wood': 0, 'wool': 0},
             'surplus': surplus_city},
            {'type': 'village', 'score': 3 - miss_village, 'missing': miss_village,
             'req': {'cereal': miss_cereal_v, 'mineral': 0, 'clay': miss_clay_v, 'wood': miss_wood_v, 'wool': miss_wool_v},
             'surplus': surplus_village},
            {'type': 'card', 'score': 2 - miss_card, 'missing': miss_card,
             'req': {'cereal': miss_cereal_d, 'mineral': miss_ore_d, 'clay': 0, 'wood': 0, 'wool': miss_wool_d},
             'surplus': surplus_card},
            {'type': 'road', 'score': 1 - miss_road, 'missing': miss_road,
             'req': {'cereal': 0, 'mineral': 0, 'clay': miss_clay_r, 'wood': miss_wood_r, 'wool': 0},
             'surplus': surplus_road}
        ]
        
        targets.sort(key=lambda x: x['score'], reverse=True)

        for target in targets:
            if target['missing'] > 0:
                if target['type'] not in self.tried_targets_player:
                    self.tried_targets_player.add(target['type'])
                    
                    total_surplus = sum(target['surplus'].values())
                    if total_surplus > 0:
                        gives = Materials(target['surplus']['cereal'], target['surplus']['mineral'],
                                          target['surplus']['clay'], target['surplus']['wood'], target['surplus']['wool'])
                        receives = Materials(target['req']['cereal'], target['req']['mineral'],
                                             target['req']['clay'], target['req']['wood'], target['req']['wool'])
                        return TradeOffer(gives, receives)

        mat_to_id = {'cereal': 0, 'mineral': 1, 'clay': 2, 'wood': 3, 'wool': 4}
        
        for target in targets:
            if target['missing'] > 0:
                missing_mats = [mat for mat, amt in target['req'].items() if amt > 0]
                
                for req_mat in missing_mats:
                    req_id = mat_to_id[req_mat]
                    
                    for surp_mat, surp_amt in target['surplus'].items():
                        if surp_amt <= 0: continue
                        surp_id = mat_to_id[surp_mat]

                        # Sum of resources logic to prevent infinite fallback loops if a bank trade is rejected.
                        trade_sig = f"{surp_id}_to_{req_id}_{sum(self.hand.resources)}"
                        if trade_sig in self.failed_bank_trades:
                            continue

                        harbor = self.board.check_for_player_harbors(self.id, surp_id)
                        ratio = 4
                        if harbor == surp_id:
                            ratio = 2
                        elif harbor == HarborConstants.ALL:
                            ratio = 3
                            
                        if surp_amt >= ratio:
                            self.failed_bank_trades.add(trade_sig)
                            return {'gives': surp_id, 'receives': req_id}

        return None

    def on_monopoly_card_use(self):
        return random.randint(0, 4)

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
