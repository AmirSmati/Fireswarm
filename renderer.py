import pygame


CELL = 42
PANEL_WIDTH = 520
MARGIN = 20

BACKGROUND = (22, 27, 38)
GRID_COLOR = (54, 62, 76)
TEXT_COLOR = (235, 239, 245)
BASE_COLOR = (70, 150, 255)
MUTED_TEXT = (180, 195, 210)


def status_name(obj):
    status = getattr(obj, "status", "")
    return str(getattr(status, "value", status)).lower()


def grid_size(world):
    width = getattr(world, "grid_width", getattr(world, "width", None))
    height = getattr(world, "grid_height", getattr(world, "height", None))

    if width is not None and height is not None:
        return int(width), int(height)

    objects = list(world.drones.values()) + list(world.incidents.values())
    max_x = max((obj.x for obj in objects), default=10)
    max_y = max((obj.y for obj in objects), default=10)
    return max(12, max_x + 3), max(12, max_y + 3)


def base_position(world):
    base = getattr(world, "base_position", None)

    if isinstance(base, (tuple, list)) and len(base) >= 2:
        return base[0], base[1]

    if hasattr(world, "base_x") and hasattr(world, "base_y"):
        return world.base_x, world.base_y

    return 0, 0


class Renderer:
    def __init__(self, world):
        pygame.init()
        self.selected_severity = 1

        self.cell = CELL
        self.width, self.height = grid_size(world)

        board_width = self.width * self.cell
        board_height = self.height * self.cell

        self.board_left = MARGIN
        self.board_top = 60
        self.panel_left = self.board_left + board_width + 30

        self.screen = pygame.display.set_mode(
            (
                self.panel_left + PANEL_WIDTH,
                max(400, self.board_top + board_height + MARGIN),
            )
        )

        pygame.display.set_caption("Firewatch Swarm")
        self.font = pygame.font.SysFont("consolas", 17)
        self.small_font = pygame.font.SysFont("consolas", 13)
        self.title_font = pygame.font.SysFont("consolas", 25, bold=True)
        self.clock = pygame.time.Clock()

    def draw_text(self, text, x, y, font=None, color=TEXT_COLOR):
        image = (font or self.font).render(str(text), True, color)
        self.screen.blit(image, (x, y))

    def draw(self, world, on_grid_click=None):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False

                # Number keys select the severity for the next fire.
                if pygame.K_1 <= event.key <= pygame.K_5:
                    self.selected_severity = event.key - pygame.K_0
                    print(f"[UI] Selected severity: {self.selected_severity}")

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_x, mouse_y = event.pos
                inside_grid = (
                    self.board_left <= mouse_x < self.board_left + self.width * self.cell
                    and self.board_top <= mouse_y < self.board_top + self.height * self.cell
                )

                if inside_grid and on_grid_click is not None:
                    grid_x = (mouse_x - self.board_left) // self.cell
                    grid_y = (mouse_y - self.board_top) // self.cell
                    on_grid_click(
                        int(grid_x),
                        int(grid_y),
                        self.selected_severity,
                    )

        self.screen.fill(BACKGROUND)
        self.draw_text("FIREWATCH SWARM", MARGIN, 16, self.title_font)
        self.draw_text(
            f"New fire severity: {self.selected_severity} (press 1-5)",
            self.panel_left,
            25,
            self.font,
        )

        # Grid
        for x in range(self.width + 1):
            px = self.board_left + x * self.cell
            pygame.draw.line(
                self.screen,
                GRID_COLOR,
                (px, self.board_top),
                (px, self.board_top + self.height * self.cell),
            )

        for y in range(self.height + 1):
            py = self.board_top + y * self.cell
            pygame.draw.line(
                self.screen,
                GRID_COLOR,
                (self.board_left, py),
                (self.board_left + self.width * self.cell, py),
            )

        def center(x, y):
            return (
                self.board_left + int(x) * self.cell + self.cell // 2,
                self.board_top + int(y) * self.cell + self.cell // 2,
            )

        # Base
        bx, by = base_position(world)
        base_center = center(bx, by)
        pygame.draw.rect(
            self.screen,
            BASE_COLOR,
            (base_center[0] - 13, base_center[1] - 13, 26, 26),
        )
        self.draw_text("B", base_center[0] - 5, base_center[1] - 9)

        # Fires / incidents
        for fire in world.incidents.values():
            pos = center(fire.x, fire.y)
            active = status_name(fire) == "active"

            if active:
                color = (
                    (255, 75, 45)
                    if fire.severity >= 4
                    else (255, 150, 45)
                    if fire.severity >= 2
                    else (255, 205, 70)
                )
                radius = 8 + min(int(fire.severity), 5) * 2
                pygame.draw.circle(self.screen, color, pos, radius)
                self.draw_text(
                    str(fire.severity),
                    pos[0] - 5,
                    pos[1] - 9,
                    self.small_font,
                    (30, 25, 20),
                )
            else:
                pygame.draw.circle(self.screen, (105, 115, 130), pos, 8)
                pygame.draw.line(
                    self.screen,
                    TEXT_COLOR,
                    (pos[0] - 4, pos[1] - 4),
                    (pos[0] + 4, pos[1] + 4),
                    2,
                )
                pygame.draw.line(
                    self.screen,
                    TEXT_COLOR,
                    (pos[0] - 4, pos[1] + 4),
                    (pos[0] + 4, pos[1] - 4),
                    2,
                )

        # Drones
        drone_colors = {
            "idle": (80, 220, 130),
            "en_route": (75, 180, 255),
            "suppressing": (255, 210, 70),
            "returning": (190, 130, 255),
            "refilling": (80, 220, 220),
            "disabled": (125, 125, 135),
        }

        for drone in world.drones.values():
            pos = center(drone.x, drone.y)
            color = drone_colors.get(status_name(drone), TEXT_COLOR)
            pygame.draw.circle(self.screen, color, pos, 11)
            pygame.draw.circle(self.screen, BACKGROUND, pos, 11, 2)

            label = str(drone.drone_id).replace("drone_", "D")
            self.draw_text(
                label,
                pos[0] - 9,
                pos[1] - 7,
                self.small_font,
                (15, 20, 25),
            )

        # Current world status (left side of the information panel)
        px = self.panel_left
        py = self.board_top

        self.draw_text("WORLD STATUS", px, py, self.title_font)
        py += 45
        self.draw_text(f"Tick: {world.tick}", px, py)
        py += 35

        active_fires = sum(
            status_name(fire) == "active"
            for fire in world.incidents.values()
        )
        self.draw_text(f"Active fires: {active_fires}", px, py)
        py += 35

        self.draw_text("DRONES", px, py)
        py += 28

        for drone in world.drones.values():
            self.draw_text(
                f"{drone.drone_id}: {status_name(drone)}",
                px,
                py,
                self.small_font,
            )
            py += 23

        py += 15
        self.draw_text("FIRES", px, py)
        py += 28

        for fire in world.incidents.values():
            self.draw_text(
                f"{fire.incident_id}: {status_name(fire)} (S{fire.severity})",
                px,
                py,
                self.small_font,
            )
            py += 23

        # Decision timeline (right side of the information panel)
        timeline_x = self.panel_left + 250
        timeline_y = self.board_top

        self.draw_text(
            "DECISION TIMELINE",
            timeline_x,
            timeline_y,
            self.title_font,
        )
        timeline_y += 38

        recent_events = list(getattr(world, "events", []))[-8:]

        if not recent_events:
            self.draw_text(
                "No events yet.",
                timeline_x,
                timeline_y,
                self.small_font,
                MUTED_TEXT,
            )
        else:
            for entry in recent_events:
                header = f"[{entry.tick}] {entry.event_type}"
                detail = entry.message

                self.draw_text(
                    header[:27],
                    timeline_x,
                    timeline_y,
                    self.small_font,
                )
                timeline_y += 18

                self.draw_text(
                    detail[:29],
                    timeline_x,
                    timeline_y,
                    self.small_font,
                    MUTED_TEXT,
                )
                timeline_y += 27

        self.draw_text(
            "Press Q or ESC to close",
            px,
            self.screen.get_height() - 30,
            self.small_font,
            (165, 175, 190),
        )

        pygame.display.flip()
        self.clock.tick(30)
        return True


def run_preview(world):
    renderer = Renderer(world)
    running = True

    while running:
        running = renderer.draw(world)

    pygame.quit()
