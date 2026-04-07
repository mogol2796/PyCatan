import random

from Classes.Constants import MaterialConstants, BuildConstants
from Classes.Materials import Materials
from Classes.TradeOffer import TradeOffer
from Interfaces.AgentInterface import AgentInterface


class CardRoadThiefAgent(AgentInterface):
    """
    Agent that prioritizes buying development cards. If not possible, it builds roads.
    If neither is possible or there's no place for a road, it randomly builds a City or Town.
    The thief is placed randomly, but avoiding tiles that would block the agent's own resources.
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
        # Find terrains where the agent DOES NOT have a settlement/city
        valid_terrains = []
        for terrain_idx in range(19):
            has_my_building = False
            for node in self.board.terrain[terrain_idx]['contacting_nodes']:
                if self.board.nodes[node]['player'] == self.id:
                    has_my_building = True
                    break
            
            if not has_my_building:
                valid_terrains.append(terrain_idx)

        # Place thief randomly avoiding our own tiles, or fully randomly if we are everywhere 
        # (which is virtually impossible but added as a fallback)
        if len(valid_terrains) > 0:
            terrain = random.choice(valid_terrains)
        else:
            terrain = random.randint(0, 18)

        # Pick a target player to steal from
        player = -1
        for node in self.board.terrain[terrain]['contacting_nodes']:
            occupant = self.board.nodes[node]['player']
            # Only steal from other players
            if occupant != -1 and occupant != self.id:
                player = occupant
                
        return {'terrain': terrain, 'player': player}

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
