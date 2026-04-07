import random

from Classes.Constants import MaterialConstants, BuildConstants, HarborConstants
from Classes.Materials import Materials
from Classes.TradeOffer import TradeOffer
from Interfaces.AgentInterface import AgentInterface


class TradePriorityBuilderAgent_v2(AgentInterface):
    """
    Advanced agent that prioritizes missing resources for City > Village > Road.
    It constructs precise Player Trade offers. If those fail, it seamlessly falls
    back to Bank trades, exploiting specific sea ports it owns (2:1 or 3:1) or 
    default (4:1) ratios, picking surplus resources iteratively to complete its targets.
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

    def on_moving_thief(self):
        terrain = random.randint(0, 18)
        player = -1
        for node in self.board.terrain[terrain]['contacting_nodes']:
            if self.board.nodes[node]['player'] != -1:
                player = self.board.nodes[node]['player']
        return {'terrain': terrain, 'player': player}

    def on_turn_end(self):
        self.trade_queue_active = False
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)
        return None

    def on_commerce_phase(self):
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        # Reset states whenever a fresh commerce phase opens up in a new context/turn
        if not getattr(self, 'trade_queue_active', False):
            self.trade_queue_active = True
            self.tried_targets_player = set()
            self.failed_bank_trades = set()

        cereal = self.hand.resources.cereal
        ore = self.hand.resources.mineral
        clay = self.hand.resources.clay
        wood = self.hand.resources.wood
        wool = self.hand.resources.wool
        
        # --- Build Phase Math Goals ---
        
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
        
        # Target 3: Road (1 Wood, 1 Clay)
        miss_wood_r = max(0, 1 - wood)
        miss_clay_r = max(0, 1 - clay)
        miss_road = miss_wood_r + miss_clay_r
        surplus_road = {
            'cereal': cereal, 'mineral': ore,
            'clay': max(0, clay - 1), 'wood': max(0, wood - 1), 'wool': wool
        }
        
        targets = [
            {'type': 'city', 'score': 3 - miss_city, 'missing': miss_city,
             'req': {'cereal': miss_cereal_c, 'mineral': miss_ore_c, 'clay': 0, 'wood': 0, 'wool': 0},
             'surplus': surplus_city},
            {'type': 'village', 'score': 2 - miss_village, 'missing': miss_village,
             'req': {'cereal': miss_cereal_v, 'mineral': 0, 'clay': miss_clay_v, 'wood': miss_wood_v, 'wool': miss_wool_v},
             'surplus': surplus_village},
            {'type': 'road', 'score': 1 - miss_road, 'missing': miss_road,
             'req': {'cereal': 0, 'mineral': 0, 'clay': miss_clay_r, 'wood': miss_wood_r, 'wool': 0},
             'surplus': surplus_road}
        ]
        
        targets.sort(key=lambda x: x['score'], reverse=True)

        # -- PHASE 1: Try Player Trades first --
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

        # -- PHASE 2: Fallback to Bank / Port Trades -- 
        # (Only reached if all player trades bounced or none were possible)
        mat_to_id = {'cereal': 0, 'mineral': 1, 'clay': 2, 'wood': 3, 'wool': 4}
        
        for target in targets:
            if target['missing'] > 0:
                missing_mats = [mat for mat, amt in target['req'].items() if amt > 0]
                
                for req_mat in missing_mats:
                    req_id = mat_to_id[req_mat]
                    
                    # Find a surplus material robust enough to fulfill a bank request
                    for surp_mat, surp_amt in target['surplus'].items():
                        if surp_amt <= 0: continue
                        surp_id = mat_to_id[surp_mat]

                        # Infinite loop safeguard in case of PyCatan bug rejecting valid bank trades silently
                        trade_sig = f"{surp_id}_to_{req_id}_{sum(self.hand.resources)}"
                        if trade_sig in self.failed_bank_trades:
                            continue

                        # dynamically check if we possess a maritime port to decrease our required transaction ratio!
                        harbor = self.board.check_for_player_harbors(self.id, surp_id)
                        ratio = 4
                        if harbor == surp_id:
                            ratio = 2
                        elif harbor == HarborConstants.ALL:
                            ratio = 3
                            
                        # Perform the bank transaction if we own enough surplus
                        if surp_amt >= ratio:
                            self.failed_bank_trades.add(trade_sig)
                            return {'gives': surp_id, 'receives': req_id}

        # End of phase if perfectly optimized
        return None

    def on_build_phase(self, board_instance):
        self.board = board_instance

        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        if self.hand.resources.has_more(BuildConstants.CITY):
            valid_nodes = self.board.valid_city_nodes(self.id)
            if len(valid_nodes):
                city_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.CITY, 'node_id': valid_nodes[city_node]}

        if self.hand.resources.has_more(BuildConstants.TOWN):
            valid_nodes = self.board.valid_town_nodes(self.id)
            if len(valid_nodes):
                town_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.TOWN, 'node_id': valid_nodes[town_node]}

        if self.hand.resources.has_more(BuildConstants.ROAD):
            valid_nodes = self.board.valid_road_nodes(self.id)
            if len(valid_nodes):
                road_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.ROAD,
                        'node_id': valid_nodes[road_node]['starting_node'],
                        'road_to': valid_nodes[road_node]['finishing_node']}

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
