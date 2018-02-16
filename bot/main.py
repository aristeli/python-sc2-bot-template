import random

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer

rally_point_towards_center = 40

RUSH_AFTER_N_ZERGLINGS = 30
EXPANSION_IS_USED_IF_DISTANCE_TO_HATCHERY_IS_LESS_THAN = 10

class ZergRushBot(sc2.BotAI):
    def __init__(self):
        self.drone_counter = 0
        self.extractor_started = False
        self.spawning_pool_started = False
        self.moved_workers_to_gas = False
        self.moved_workers_from_gas = False
        self.queeen_started = False
        self.mboost_started = False
        self.rally_point = None
        self.spawn_point = None
        self.rush_started = False

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send("(glhf)")

        if not self.units(HATCHERY).ready.exists:
            for unit in self.workers | self.units(ZERGLING) | self.units(QUEEN):
                await self.do(unit.attack(self.enemy_start_locations[0]))
            return

        hatchery = self.units(HATCHERY).ready.first
        if not self.spawn_point and hatchery:
            self.spawn_point = hatchery.position
        larvae = self.units(LARVA)

        enemy_target = self.known_enemy_structures.random_or(self.enemy_start_locations[0]).position
        if not self.rally_point:
            self.rally_point = hatchery.position.to2.towards(self.game_info.map_center, rally_point_towards_center)

        zerglings = self.units(ZERGLING)
        if zerglings.amount > RUSH_AFTER_N_ZERGLINGS or self.rush_started:
            self.rush_started = True
            for zl in zerglings:
                await self.do(zl.attack(enemy_target))

        for zl in self.units(ZERGLING).idle:
            if zl.position.distance_to(self.rally_point) >= 15:
                await self.do(zl.attack(self.rally_point))

        for queen in self.units(QUEEN).idle:
            abilities = await self.get_available_abilities(queen)
            if AbilityId.EFFECT_INJECTLARVA in abilities:
                await self.do(queen(EFFECT_INJECTLARVA, hatchery))

        if self.vespene >= 100:
            sp = self.units(SPAWNINGPOOL).ready
            if sp.exists and self.minerals >= 100 and not self.mboost_started:
                await self.do(sp.first(RESEARCH_ZERGLINGMETABOLICBOOST))
                self.mboost_started = True

            if not self.moved_workers_from_gas:
                self.moved_workers_from_gas = True
                for drone in self.workers:
                    m = self.state.mineral_field.closer_than(10, drone.position)
                    await self.do(drone.gather(m.random, queue=True))

        if self.supply_left < 2:
            if self.can_afford(OVERLORD) and larvae.exists:
                await self.do(larvae.random.train(OVERLORD))

        if self.units(SPAWNINGPOOL).ready.exists:
            if larvae.exists and self.can_afford(ZERGLING):
                await self.do(larvae.random.train(ZERGLING))

        if self.units(EXTRACTOR).ready.exists and not self.moved_workers_to_gas:
            self.moved_workers_to_gas = True
            extractor = self.units(EXTRACTOR).first
            for drone in self.workers.random_group_of(3):
                await self.do(drone.gather(extractor))

        if self.minerals > 500:
            pos = self.find_unused_closest_expansion()
            if pos:
                err = await self.build(HATCHERY, pos)
                if not err:
                    self.spawning_pool_started = True
            #for d in range(4, 15):
                #pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                #if await self.can_place(HATCHERY, pos):
                    #self.spawning_pool_started = True
                    #await self.do(self.workers.random.build(HATCHERY, pos))
                    #break

        if self.drone_counter < 3:
            if self.can_afford(DRONE):
                self.drone_counter += 1
                await self.do(larvae.random.train(DRONE))

        if not self.extractor_started:
            if self.can_afford(EXTRACTOR):
                drone = self.workers.random
                target = self.state.vespene_geyser.closest_to(drone.position)
                err = await self.do(drone.build(EXTRACTOR, target))
                if not err:
                    self.extractor_started = True

        elif not self.spawning_pool_started:
            if self.can_afford(SPAWNINGPOOL):
                for d in range(4, 15):
                    pos = hatchery.position.to2.towards(self.game_info.map_center, d)
                    if await self.can_place(SPAWNINGPOOL, pos):
                        drone = self.workers.closest_to(pos)
                        err = await self.do(drone.build(SPAWNINGPOOL, pos))
                        if not err:
                            self.spawning_pool_started = True
                            break

        elif not self.queeen_started and self.units(SPAWNINGPOOL).ready.exists:
            if self.can_afford(QUEEN):
                r = await self.do(hatchery.train(QUEEN))
                if not r:
                    self.queeen_started = True

    def find_unused_closest_expansion(self):
        hatcheries = self.units(HATCHERY)
        closest_expansions = self.spawn_point.sort_by_distance(self.expansion_locations.keys())

        def filter_unused(expansion):
            nearby_hatcheries = hatcheries.closer_than(EXPANSION_IS_USED_IF_DISTANCE_TO_HATCHERY_IS_LESS_THAN, expansion)
            return len(nearby_hatcheries) == 0

        unused_expansions = list(filter(filter_unused, closest_expansions))
        if len(unused_expansions) == 0:
            return None
        return unused_expansions[0]