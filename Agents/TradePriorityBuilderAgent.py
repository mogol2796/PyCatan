import random

from Classes.Constants import MaterialConstants, BuildConstants
from Classes.Materials import Materials
from Classes.TradeOffer import TradeOffer
from Interfaces.AgentInterface import AgentInterface


class TradePriorityBuilderAgent(AgentInterface):
    """
    Agent that behaves identically to PriorityBuilderAgent for building logic,
    but implements a smart trading mechanism in the commerce phase.
    It proposes trades to other players, attempting to gather the missing 
    resources for City > Village > Road by sacrificing surplus resources that 
    are not required for the active building target. If the trade bounces, 
    it will attempt the next best building target in the same turn.
    """
    def __init__(self, agent_id):
        super().__init__(agent_id)
        self.trade_queue_active = False
        self.trade_queue = []

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
        self.trade_queue = []
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
        self.trade_queue = []
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)
        return None

    def on_commerce_phase(self):
        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        # Smart trading logic activation
        if not getattr(self, 'trade_queue_active', False):
            self.trade_queue_active = True
            
            cereal = self.hand.resources.cereal
            ore = self.hand.resources.mineral
            clay = self.hand.resources.clay
            wood = self.hand.resources.wood
            wool = self.hand.resources.wool
            
            # Target 1: City (Cost: 2 Cereal, 3 Ore)
            miss_cereal_c = max(0, 2 - cereal)
            miss_ore_c = max(0, 3 - ore)
            miss_city = miss_cereal_c + miss_ore_c
            surplus_city = {
                'cereal': max(0, cereal - 2), 'mineral': max(0, ore - 3),
                'clay': clay, 'wood': wood, 'wool': wool
            }
            
            # Target 2: Town/Village (Cost: 1 Cereal, 1 Wood, 1 Clay, 1 Wool)
            miss_cereal_v = max(0, 1 - cereal)
            miss_wood_v = max(0, 1 - wood)
            miss_clay_v = max(0, 1 - clay)
            miss_wool_v = max(0, 1 - wool)
            miss_village = miss_cereal_v + miss_wood_v + miss_clay_v + miss_wool_v
            surplus_village = {
                'cereal': max(0, cereal - 1), 'mineral': ore,
                'clay': max(0, clay - 1), 'wood': max(0, wood - 1), 'wool': max(0, wool - 1)
            }
            
            # Target 3: Road (Cost: 1 Wood, 1 Clay)
            miss_wood_r = max(0, 1 - wood)
            miss_clay_r = max(0, 1 - clay)
            miss_road = miss_wood_r + miss_clay_r
            surplus_road = {
                'cereal': cereal, 'mineral': ore,
                'clay': max(0, clay - 1), 'wood': max(0, wood - 1), 'wool': wool
            }
            
            # We assign base scores representing priorities: City (3), Town (2), Road (1).
            # Subtracting the amount of missing cards produces the final score (penalties).
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
            
            # Sort by score highest to lowest
            targets.sort(key=lambda x: x['score'], reverse=True)
            self.trade_queue = targets

        # Propose the highest viable trade in our evaluated queue
        while len(self.trade_queue) > 0:
            target = self.trade_queue.pop(0)
            
            # We don't trade if we already possess all materials needed for this target
            if target['missing'] == 0:
                continue
                
            total_surplus = sum(target['surplus'].values())
            # We must have something surplus to lock in the required resources!
            if total_surplus > 0:
                gives = Materials(target['surplus']['cereal'], target['surplus']['mineral'],
                                  target['surplus']['clay'], target['surplus']['wood'], target['surplus']['wool'])
                receives = Materials(target['req']['cereal'], target['req']['mineral'],
                                     target['req']['clay'], target['req']['wood'], target['req']['wool'])
                
                return TradeOffer(gives, receives)
        
        # If queue exhausted and no trades could be formulated, commerce is done
        return None

    def on_build_phase(self, board_instance):
        self.board = board_instance

        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        # 1. Priority: City
        if self.hand.resources.has_more(BuildConstants.CITY):
            valid_nodes = self.board.valid_city_nodes(self.id)
            if len(valid_nodes):
                city_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.CITY, 'node_id': valid_nodes[city_node]}

        # 2. Priority: Town (Settlement)
        if self.hand.resources.has_more(BuildConstants.TOWN):
            valid_nodes = self.board.valid_town_nodes(self.id)
            if len(valid_nodes):
                town_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.TOWN, 'node_id': valid_nodes[town_node]}

        # 3. Priority: Road
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
