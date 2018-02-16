import random
from math import pi

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer

rally_point_towards_center = 40

MAX_HATCHERIES = 3
RUSH_AFTER_N_ZERGLINGS = 30
EXPANSION_IS_USED_IF_DISTANCE_TO_HATCHERY_IS_LESS_THAN = 10
DRONE_BELONGS_TO_HATCHERY_DISTANCE = 10

MAX_DRONES_PER_HATCHERY = 16

class ZergRushBot(sc2.BotAI):
    def __init__(self):
        self.drone_counter = 0
        self.extractor_started = False
        self.first_creep_tumor_built = False
        self.spawning_pool_started = False
        self.moved_workers_to_gas = False
        self.moved_workers_from_gas = False
        self.mboost_started = False
        self.rally_point = None
        self.spawn_point = None
        self.rush_started = False
        self.last_unit_built = ''

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send("(glhf)")

        if not self.units(HATCHERY).ready.exists:
            for unit in self.workers | self.units(ZERGLING) | self.units(QUEEN):
                await self.do(unit.attack(self.enemy_start_locations[0]))
            return

        hatcheries = self.units(HATCHERY)
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
            if AbilityId.BUILD_CREEPTUMOR_QUEEN in abilities and not self.first_creep_tumor_built and self.units(SPAWNINGPOOL).ready.exists:
                print("Building first creep tumor")
                first_spawning_pool_pos = self.units(SPAWNINGPOOL).ready.first.position
                first_tumor_pos = first_spawning_pool_pos.to2.towards(self.game_info.map_center, 6)
                # can_place does not work here for some reason
                # if await self.can_place(CREEPTUMORQUEEN, first_tumor_pos):
                err = await self.do(queen(BUILD_CREEPTUMOR_QUEEN, first_tumor_pos))
                if not err:
                    print("First creep tumor built.")
                    self.first_creep_tumor_built = True
                    break
            if self.first_creep_tumor_built and AbilityId.EFFECT_INJECTLARVA in abilities:
                closest_hatchery = hatcheries.ready.closest_to(queen.position)
                if closest_hatchery:
                    await self.do(queen(EFFECT_INJECTLARVA, closest_hatchery))


        # Expand creep tumors
        for creeptumor in self.units(CREEPTUMORBURROWED).ready:
            abilities = await self.get_available_abilities(creeptumor)
            if AbilityId.BUILD_CREEPTUMOR_TUMOR in abilities:
                next_tumor_pos = creeptumor.position.random_on_distance(6 + 10 * random.random())
                # next_tumor_pos = creeptumor.position.to2.towards_random_angle(self.enemy_start_locations[0], pi/8, 6 + 6 * random.random())
                await self.do(creeptumor(BUILD_CREEPTUMOR_TUMOR, next_tumor_pos))

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
            if self.can_afford(OVERLORD) and larvae.exists and self.units_being_built('Overlord') == 0:
                await self.do(larvae.random.train(OVERLORD))

        if self.can_afford(DRONE) and self.last_unit_built is not 'drone':
            for hatchery in hatcheries.ready:
                hatchery_drones = self.units(DRONE).closer_than(DRONE_BELONGS_TO_HATCHERY_DISTANCE, hatchery.position)

                hatching_eggs = self.units(EGG).closer_than(DRONE_BELONGS_TO_HATCHERY_DISTANCE, hatchery.position)
                hatching_drones = list(filter(lambda egg: len(egg.orders) > 0 and egg.orders[0].ability._proto.button_name == 'Drone', hatching_eggs))
                if hatchery_drones.amount + len(hatching_drones) < MAX_DRONES_PER_HATCHERY and len(hatching_drones) == 0:
                    usable_larvae = larvae.closer_than(DRONE_BELONGS_TO_HATCHERY_DISTANCE, hatchery.position)
                    if usable_larvae.exists:
                        self.last_unit_built = 'drone'
                        await self.do(usable_larvae.random.train(DRONE))

        if self.units(SPAWNINGPOOL).ready.exists:
            if larvae.exists and self.can_afford(ZERGLING):
                self.last_unit_built = 'zergling'
                await self.do(larvae.random.train(ZERGLING))

        if self.units(EXTRACTOR).ready.exists and not self.moved_workers_to_gas:
            self.moved_workers_to_gas = True
            extractor = self.units(EXTRACTOR).first
            for drone in self.workers.random_group_of(3):
                await self.do(drone.gather(extractor))

        for drone in self.units(DRONE).idle:
            await self.do(drone.gather(self.state.mineral_field.closest_to(drone.position)))

        if self.minerals > 500 and len(hatcheries) < MAX_HATCHERIES:
            pos = await self.get_next_expansion()
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

        elif self.units(SPAWNINGPOOL).ready.exists:
            queens = self.units(QUEEN)
            hatcheries_without_queen = hatcheries.ready.filter(lambda cur:
                len(cur.orders) == 0 and queens.closer_than(DRONE_BELONGS_TO_HATCHERY_DISTANCE, cur.position).amount == 0
            )
            if self.can_afford(QUEEN) and hatcheries_without_queen.amount > 0:
                await self.do(hatcheries_without_queen[0].train(QUEEN))

    def units_being_built(self, unit_name):
        hatching_eggs = self.units(EGG)
        hatching_units = list(filter(lambda egg: len(egg.orders) > 0 and egg.orders[0].ability._proto.button_name == unit_name, hatching_eggs))
        return len(hatching_units)