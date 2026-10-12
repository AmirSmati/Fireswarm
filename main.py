
import pygame

from simulation import create_initial_world
from renderer import Renderer
from movement import advance_world
from allocation import assign_available_drones


TICK_INTERVAL_MS = 350


def main():
    world = create_initial_world()
    renderer = Renderer(world)

    running = True
    last_tick = pygame.time.get_ticks()

    try:
        while running:
            running = renderer.draw(world)

            if not running:
                break

            now = pygame.time.get_ticks()

            if now - last_tick >= TICK_INTERVAL_MS:
                assign_available_drones(world)
                advance_world(world)
                last_tick = now

    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
