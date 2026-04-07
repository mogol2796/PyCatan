import random

from Classes.Constants import *
from Classes.Materials import Materials
from Classes.TradeOffer import TradeOffer
from Interfaces.AgentInterface import AgentInterface


class heuristicInitialPlacement(AgentInterface):
    """
    Agente como RandomAgent, pero con on_game_start heuristico.
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
        terrain = random.randint(0, 18)
        player = -1
        for node in self.board.terrain[terrain]['contacting_nodes']:
            if self.board.nodes[node]['player'] != -1:
                player = self.board.nodes[node]['player']
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

        if len(self.development_cards_hand.hand) and random.randint(0, 1):
            return self.development_cards_hand.select_card(0)

        answer = random.randint(0, 2)
        # Pueblo / carretera
        if self.hand.resources.has_more(BuildConstants.TOWN) and answer == 0:
            answer = random.randint(0, 1)
            # Elegimos aleatoriamente si hacer un pueblo o una carretera
            if answer:
                valid_nodes = self.board.valid_town_nodes(self.id)
                if len(valid_nodes):
                    town_node = random.randint(0, len(valid_nodes) - 1)
                    return {'building': BuildConstants.TOWN, 'node_id': valid_nodes[town_node]}
            else:
                valid_nodes = self.board.valid_road_nodes(self.id)
                if len(valid_nodes):
                    road_node = random.randint(0, len(valid_nodes) - 1)
                    return {'building': BuildConstants.ROAD,
                            'node_id': valid_nodes[road_node]['starting_node'],
                            'road_to': valid_nodes[road_node]['finishing_node']}

        # Ciudad
        elif self.hand.resources.has_more(BuildConstants.CITY) and answer == 1:
            valid_nodes = self.board.valid_city_nodes(self.id)
            if len(valid_nodes):
                city_node = random.randint(0, len(valid_nodes) - 1)
                return {'building': BuildConstants.CITY, 'node_id': valid_nodes[city_node]}

        # Carta de desarrollo
        elif self.hand.resources.has_more(BuildConstants.CARD) and answer == 2:
            return {'building': BuildConstants.CARD}

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
