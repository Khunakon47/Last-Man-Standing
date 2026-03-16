import pygame
from pygame import mixer
import os
import random
import csv
import button

mixer.init()
pygame.init()

SCREEN_WIDTH  = 800
SCREEN_HEIGHT = int(SCREEN_WIDTH * 0.8)
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Last Man Standing")

clock = pygame.time.Clock()
FPS = 60

# CONSTANTS
GRAVITY       = 0.75          # acceleration added to vel_y every frame
SCROLL_THRESH = 200           # pixels from edge before camera starts moving
ROWS          = 16
COLS          = 150
TILE_SIZE     = SCREEN_HEIGHT // ROWS
TILE_TYPES    = 21
MAX_LEVELS    = 3

# Colors
BG        = (144, 201, 120)
RED       = (255,   0,   0)
WHITE     = (255, 255, 255)
GREEN     = (  0, 255,   0)
BLACK     = (  0,   0,   0)
GRAY      = (100, 100, 100)
DARK_GRAY = ( 60,  60,  60, 180)
PINK      = (235,  65,  54)
YELLOW    = (255, 215,   0)
ORANGE    = (255, 140,   0)
CYAN      = (  0, 220, 255)
DEATH_BG  = ( 10,  10,  25, 180)

# Enemy stats scale with level
ENEMY_HP  = {1: 100, 2: 120, 3: 150}
ENEMY_DMG = {1:  10, 2:  15, 3:  20}

# GAME STATE
# Central dict that tracks everything mutable across frames.
state = {
    "screen_scroll":     0,    
    "bg_scroll":         0,    
    "level":             1,
    "start_game":        False,
    "start_intro":       False,  
    "moving_left":       False,
    "moving_right":      False,
    "shoot":             False,
    "grenade":           False,
    "grenade_thrown":    False, 
    "score":             0,
    "kills":             0,
    "shots_fired":       0,
    "damage_taken":      0,
    "survive_ms":        0,      
    "last_tick":         0,     
    "paused":            False,
    "pause_alpha":       0,      
    "music_on":          True,
    "show_death_screen": False,
    "mouse_clicked":     False,  
}

# AUDIO
pygame.mixer.music.load("assets/audio/music2.mp3")
pygame.mixer.music.set_volume(0.3)
pygame.mixer.music.play(-1, 0.0, 5000)  # loop forever, 5 s fade-in

def load_sfx(path, vol=0.5):
    s = pygame.mixer.Sound(path)
    s.set_volume(vol)
    return s

jump_fx    = load_sfx("assets/audio/jump.wav")
shot_fx    = load_sfx("assets/audio/shot.wav")
grenade_fx = load_sfx("assets/audio/grenade.wav")
death_fx   = load_sfx("assets/audio/death.wav")

# IMAGES
start_img   = pygame.image.load("assets/img/start_btn.png").convert_alpha()
exit_img    = pygame.image.load("assets/img/exit_btn.png").convert_alpha()

pine1_img    = pygame.image.load("assets/img/Background/pine1.png").convert_alpha()
pine2_img    = pygame.image.load("assets/img/Background/pine2.png").convert_alpha()
mountain_img = pygame.image.load("assets/img/Background/mountain.png").convert_alpha()
sky_img      = pygame.image.load("assets/img/Background/sky_cloud.png").convert_alpha()

# Load all tile images and scale them to TILE_SIZE
img_list = []
for x in range(TILE_TYPES):
    img = pygame.image.load(f"assets/img/tile/{x}.png").convert_alpha()
    img = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
    img_list.append(img)

bullet_img      = pygame.image.load("assets/img/icons/bullet.png").convert_alpha()
grenade_img     = pygame.image.load("assets/img/icons/grenade.png").convert_alpha()
health_box_img  = pygame.image.load("assets/img/icons/health_box.png").convert_alpha()
ammo_box_img    = pygame.image.load("assets/img/icons/ammo_box.png").convert_alpha()
grenade_box_img = pygame.image.load("assets/img/icons/grenade_box.png").convert_alpha()
item_boxes = {"Health": health_box_img, "Ammo": ammo_box_img, "Grenade": grenade_box_img}

# Fonts
font       = pygame.font.SysFont("Futura", 30)
font_small = pygame.font.SysFont("Futura", 20)
font_big   = pygame.font.SysFont("Futura", 56)
font_med   = pygame.font.SysFont("Futura", 36)
font_title = pygame.font.SysFont("Futura", 72, bold=True)
font_hint  = pygame.font.SysFont("Segoe UI Symbol", 16)

# HELPER FUNCTIONS
def draw_text(text, fnt, colour, x, y):
    screen.blit(fnt.render(text, True, colour), (x, y))

def draw_text_centered(text, fnt, colour, y):
    surf = fnt.render(text, True, colour)
    screen.blit(surf, (SCREEN_WIDTH // 2 - surf.get_width() // 2, y))

def draw_bg():
    """Draw parallax scrolling background layers at different scroll speeds
    to create a sense of depth — far layers move slower than near layers."""
    screen.fill(BG)
    w   = sky_img.get_width()
    bg  = state["bg_scroll"]
    for x in range(5):
        screen.blit(sky_img,      ((x * w) - bg * 0.5, 0))
        screen.blit(mountain_img, ((x * w) - bg * 0.6, SCREEN_HEIGHT - mountain_img.get_height() - 300))
        screen.blit(pine1_img,    ((x * w) - bg * 0.7, SCREEN_HEIGHT - pine1_img.get_height() - 150))
        screen.blit(pine2_img,    ((x * w) - bg * 0.8, SCREEN_HEIGHT - pine2_img.get_height()))

def reset_level():
    """Clear all sprite groups and return a blank tile grid.
    Called both at startup and whenever a level is reloaded."""
    for grp in (enemy_group, bullet_group, grenade_group, explosion_group,
                item_box_group, decoration_group, water_group, exit_group,
                damage_text_group, kill_feed_group):
        grp.empty()
    return [[-1] * COLS for _ in range(ROWS)]  # -1 means empty tile

def _fmt_time(ms):
    """Convert milliseconds to M:SS string for the HUD."""
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"

def _accuracy():
    """Kill-to-shot ratio as a percentage (0 if no shots fired yet)."""
    fired = state["shots_fired"]
    return 0 if fired == 0 else round(state["kills"] * 100 / fired)

def _btn_click(x, y, w, h):
    """Return True only on the single frame the mouse button was pressed inside the rect.
    Using mouse_clicked (not get_pressed) prevents held-click from registering repeatedly."""
    mx, my = pygame.mouse.get_pos()
    return state["mouse_clicked"] and x <= mx <= x + w and y <= my <= y + h

def draw_hud():
    """Draw level / score / time in the top-right corner."""
    lines = [
        f"LEVEL  {state['level']}",
        f"SCORE  {state['score']}",
        f"TIME   {_fmt_time(state['survive_ms'])}",
    ]
    for i, txt in enumerate(lines):
        surf = font_small.render(txt, True, WHITE)
        screen.blit(surf, (SCREEN_WIDTH - surf.get_width() - 10, 52 + i * 22))

def draw_pause_button():
    """Draw the [II] pause button in the top-right. Returns True if clicked."""
    bx, by, bw, bh = SCREEN_WIDTH - 52, 4, 46, 40
    pygame.draw.rect(screen, DARK_GRAY, (bx - 4, by, bw, bh), border_radius=5)
    pygame.draw.rect(screen, GRAY,      (bx - 4, by, bw, bh), 1, border_radius=5)
    pygame.draw.rect(screen, WHITE, (bx + 8,  by + 8, 6, 22))  # left bar
    pygame.draw.rect(screen, WHITE, (bx + 25, by + 8, 6, 22))  # right bar
    return _btn_click(bx, by, bw, bh)

# KILL FEED
# Short notifications that float at the bottom of the screen when an enemy dies.
class KillFeedEntry(pygame.sprite.Sprite):
    def __init__(self, text, colour=ORANGE):
        super().__init__()
        self.image = font_small.render(text, True, colour)
        self.rect  = self.image.get_rect()
        self.timer = 180  # frames before this entry disappears

    def update(self):
        self.timer -= 1
        if self.timer < 60:
            self.image.set_alpha(int(255 * self.timer / 60))  # fade out in the last second
        if self.timer <= 0:
            self.kill()

def add_kill_feed(text, colour=ORANGE):
    kill_feed_group.add(KillFeedEntry(text, colour))
    # Stack entries upward from the bottom of the screen
    for i, e in enumerate(reversed(list(kill_feed_group))):
        e.rect.midbottom = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 10 - i * 24)

# FLOATING DAMAGE TEXT
# Numbers that pop out of an entity when it takes damage.
class DamageText(pygame.sprite.Sprite):
    def __init__(self, x, y, text, colour):
        super().__init__()
        self.image = font_small.render(text, True, colour)
        self.rect  = self.image.get_rect(center=(x, y))
        self.timer = 60    # lifetime in frames
        self.vel_y = -1.5  # floats upward over time

    def update(self):
        self.rect.x += state["screen_scroll"]  # keep position locked to world, not screen
        self.rect.y += self.vel_y
        self.timer  -= 1
        self.image.set_alpha(max(0, int(255 * self.timer / 60)))  # fade out as timer runs down
        if self.timer <= 0:
            self.kill()

# DEATH / WIN SCREEN
# Shown after the player dies or clears all levels. Displays run statistics and action buttons.
class DeathScreen:
    PANEL_W, PANEL_H = 440, 420

    def __init__(self):
        self.visible  = False
        self.win_mode = False  # True = victory screen, False = death screen

    def show(self, win=False):
        self.visible  = True
        self.win_mode = win

    def draw(self):
        if not self.visible:
            return None

        cx = SCREEN_WIDTH  // 2
        cy = SCREEN_HEIGHT // 2
        pw, ph = self.PANEL_W, self.PANEL_H
        accent = YELLOW if self.win_mode else PINK  # gold for win, red for death

        # Dark panel background
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((15, 15, 35, 245))
        screen.blit(panel, (cx - pw//2, cy - ph//2))

        # Coloured top accent bar and border
        pygame.draw.rect(screen, accent, (cx - pw//2, cy - ph//2, pw, 6), border_radius=4)
        pygame.draw.rect(screen, accent, (cx - pw//2, cy - ph//2, pw, ph), 2, border_radius=10)

        title = "YOU WIN" if self.win_mode else "YOU DIED"
        draw_text_centered(title, font_big, accent, cy - ph//2 + 24)

        div_y = cy - ph//2 + 78
        pygame.draw.line(screen, (60, 60, 90),
                         (cx - pw//2 + 24, div_y), (cx + pw//2 - 24, div_y), 1)

        # End-of-run statistics
        stats = [
            ("Level Reached",  f"{state['level']} / {MAX_LEVELS}"),
            ("Time Survived",  _fmt_time(state["survive_ms"])),
            ("Score",          f"{state['score']}"),
            ("Enemies Killed", f"{state['kills']}"),
            ("Shots Fired",    f"{state['shots_fired']}"),
            ("Accuracy",       f"{_accuracy()}%"),
            ("Damage Taken",   f"{state['damage_taken']} HP"),
        ]
        row_y = div_y + 12
        lbl_x = cx - pw//2 + 28
        val_x = cx + pw//2 - 28
        for label, value in stats:
            draw_text(label, font_small, GRAY, lbl_x, row_y)
            vs = font_small.render(value, True, WHITE)
            screen.blit(vs, (val_x - vs.get_width(), row_y))
            row_y += 26

        btn_top = row_y
        pygame.draw.line(screen, (60, 60, 90),
                         (cx - pw//2 + 24, btn_top), (cx + pw//2 - 24, btn_top), 1)

        # Action buttons — each returns a string key when clicked
        action   = None
        btn_defs = [
            ("Restart This Level",   (30, 90, 50),  "restart_level"),
            ("Start Over - Level 1", (30, 50, 110), "restart_from_start"),
            ("Back to Home",         (80, 50, 100), "home"),
        ]
        bw, bh = pw - 48, 34
        bx     = cx - bw // 2
        gap    = 8
        by0    = btn_top + 10

        for i, (label, col, result) in enumerate(btn_defs):
            by = by0 + i * (bh + gap)
            mx, my = pygame.mouse.get_pos()
            hovering  = bx <= mx <= bx + bw and by <= my <= by + bh
            draw_col  = tuple(min(c + 30, 255) for c in col) if hovering else col  # brighten on hover
            pygame.draw.rect(screen, draw_col, (bx, by, bw, bh), border_radius=7)
            pygame.draw.rect(screen, accent if hovering else (70, 70, 100),
                             (bx, by, bw, bh), 1, border_radius=7)
            ls = font_small.render(label, True, WHITE)
            screen.blit(ls, (bx + bw//2 - ls.get_width()//2,
                             by + bh//2 - ls.get_height()//2))
            if _btn_click(bx, by, bw, bh):
                action = result

        return action

# PLAYER
# Handles movement, double-jump, shooting, grenade throwing, damage, and animation.
class Player(pygame.sprite.Sprite):
    MAX_JUMPS = 2  # allows one jump from the ground + one mid-air jump

    def __init__(self, char_type, x, y, scale, speed, ammo, grenades):
        super().__init__()
        self.alive              = True
        self.char_type          = char_type
        self.speed              = speed
        self.ammo               = ammo
        self.start_ammo         = ammo
        self.shoot_cooldown     = 0   # frames until next shot is allowed
        self.grenades           = grenades
        self.health             = 100
        self.max_health         = 100
        self.direction          = 1   # 1 = right, -1 = left
        self.vel_y              = 0   # vertical velocity; increases each frame due to gravity
        self.jump               = False
        self.in_air             = True
        self.jumps_left         = self.MAX_JUMPS
        self.flip               = False  # whether to mirror the sprite horizontally
        self.animation_list     = []
        self.frame_index        = 0
        self.action             = 0   # 0=Idle, 1=Run, 2=Jump, 3=Death
        self.update_time        = pygame.time.get_ticks()
        self.death_sound_played = False
        self.invincible         = 0   # frames of invincibility after being hit (prevents instant multi-hit)
        self.hit_flash          = 0   # frames of red tint overlay after taking damage

        # Load all animation frames for each action into a 2D list
        animation_types = ["Idle", "Run", "Jump", "Death"]
        for anim in animation_types:
            temp, n = [], len(os.listdir(f"assets/img/{self.char_type}/{anim}"))
            for i in range(n):
                img = pygame.image.load(f"assets/img/{self.char_type}/{anim}/{i}.png").convert_alpha()
                img = pygame.transform.scale(img, (int(img.get_width() * scale), int(img.get_height() * scale)))
                temp.append(img)
            self.animation_list.append(temp)

        self.image  = self.animation_list[self.action][self.frame_index]
        self.rect   = self.image.get_rect(center=(x, y))
        self.width  = self.image.get_width()
        self.height = self.image.get_height()

    def update(self):
        self.update_animation()
        self.check_alive()
        if self.shoot_cooldown > 0: self.shoot_cooldown -= 1
        if self.invincible > 0:     self.invincible -= 1
        if self.hit_flash  > 0:     self.hit_flash  -= 1

    def take_damage(self, amount):
        if self.invincible > 0:
            return  # ignore hits during invincibility window
        self.health           -= amount
        state["damage_taken"] += amount
        self.invincible        = 20
        self.hit_flash         = 6
        damage_text_group.add(DamageText(self.rect.centerx, self.rect.top, f"-{amount}", RED))

    def move(self, moving_left, moving_right):
        """Apply horizontal input, gravity, tile collision on both axes, and camera scroll.
        Returns (scroll, level_complete) — scroll is how many pixels the world should shift."""
        scroll = 0
        dx = dy = 0

        if moving_left:
            dx = -self.speed; self.flip = True;  self.direction = -1
        if moving_right:
            dx =  self.speed; self.flip = False; self.direction =  1

        # Jumping: only allowed when jumps_left > 0 (supports double-jump)
        if self.jump and self.jumps_left > 0:
            self.vel_y      = -12   # negative = upward in pygame's coordinate system
            self.jump       = False
            self.in_air     = True
            self.jumps_left -= 1

        # Apply gravity every frame; cap fall speed at 10 to avoid tunnelling through thin tiles
        self.vel_y = min(self.vel_y + GRAVITY, 10)
        dy += self.vel_y

        # Resolve tile collisions separately on each axis to avoid corner-catching
        for tr in world.get_tile_rects():
            if tr.colliderect(self.rect.x + dx, self.rect.y, self.width, self.height):
                dx = 0  # blocked horizontally
            if tr.colliderect(self.rect.x, self.rect.y + dy, self.width, self.height):
                if self.vel_y < 0:
                    self.vel_y = 0; dy = tr.bottom - self.rect.top   # hit ceiling
                else:
                    self.vel_y      = 0
                    self.in_air     = False
                    self.jumps_left = self.MAX_JUMPS   # reset jumps on landing
                    dy = tr.top - self.rect.bottom     # land on top of tile

        # Instant death if touching water or falling off the bottom of the screen
        if pygame.sprite.spritecollide(self, water_group, False):
            self.health = 0
        level_complete = bool(pygame.sprite.spritecollide(self, exit_group, False))
        if self.rect.bottom > SCREEN_HEIGHT:   self.health = 0
        if self.rect.left + dx < 0 or self.rect.right + dx > SCREEN_WIDTH: dx = 0

        self.rect.x += dx
        self.rect.y += dy

        # Trigger camera scroll when player approaches SCROLL_THRESH pixels from either edge
        if (self.rect.right > SCREEN_WIDTH - SCROLL_THRESH and
                state["bg_scroll"] < (world.level_length * TILE_SIZE - SCREEN_WIDTH)) or \
           (self.rect.left < SCROLL_THRESH and state["bg_scroll"] > abs(dx)):
            self.rect.x -= dx   # undo player movement — camera moves instead
            scroll = -dx

        return scroll, level_complete

    def shoot(self):
        """Spawn a bullet in the direction the player is facing, if cooldown allows."""
        if self.shoot_cooldown == 0 and self.ammo > 0:
            self.shoot_cooldown = 20
            bx = self.rect.centerx + 0.75 * self.rect.width * self.direction
            bullet_group.add(Bullet(bx, self.rect.centery, self.direction, owner="player", damage=20))
            self.ammo -= 1
            state["shots_fired"] += 1
            shot_fx.play()

    def update_animation(self):
        self.image = self.animation_list[self.action][self.frame_index]
        if pygame.time.get_ticks() - self.update_time > 100:  # advance frame every 100 ms
            self.update_time = pygame.time.get_ticks()
            self.frame_index += 1
        if self.frame_index >= len(self.animation_list[self.action]):
            # Death animation locks on the last frame; all other animations loop
            self.frame_index = len(self.animation_list[self.action]) - 1 if self.action == 3 else 0

    def update_action(self, new_action):
        """Switch to a new animation only if it differs from the current one (prevents restarting)."""
        if new_action != self.action:
            self.action = new_action; self.frame_index = 0
            self.update_time = pygame.time.get_ticks()

    def check_alive(self):
        if self.health <= 0:
            self.health = 0; self.speed = 0; self.alive = False
            self.update_action(3)  # switch to Death animation
            if not self.death_sound_played:
                death_fx.play(); self.death_sound_played = True

    def draw(self):
        img = self.image
        # Overlay a red tint for a few frames when the player takes a hit
        if self.hit_flash > 0:
            flash = img.copy()
            flash.fill((255, 80, 80, 160), special_flags=pygame.BLEND_RGBA_MULT)
            img = flash
        screen.blit(pygame.transform.flip(img, self.flip, False), self.rect)
        # Small cyan dot above the player's head indicates a second jump is still available
        if self.in_air and self.jumps_left == 1:
            pygame.draw.circle(screen, CYAN, (self.rect.centerx, self.rect.top - 8), 4)

# ENEMY
# Patrols the level, chases the player on sight, shoots when in range, and avoids walls/drops.
class Enemy(pygame.sprite.Sprite):
    PATROL = "patrol"
    CHASE  = "chase"
    SHOOT  = "shoot"

    def __init__(self, x, y, scale, speed, level=1):
        super().__init__()
        self.alive          = True
        self.speed          = speed
        self.health         = ENEMY_HP.get(level, 100)
        self.max_health     = self.health
        self.bullet_dmg     = ENEMY_DMG.get(level, 10)  # damage dealt per bullet
        self.direction      = 1
        self.vel_y          = 0
        self.in_air         = True
        self.flip           = False
        self.animation_list = []
        self.frame_index    = 0
        self.action         = 0   # 0=Idle, 1=Run, 2=Death
        self.update_time    = pygame.time.get_ticks()
        self.shoot_cooldown = 0
        self.move_counter   = 0   # tracks distance walked before reversing during patrol
        self.idle_counter   = 0   # frames left in the current random idle pause
        self.vision         = pygame.Rect(0, 0, 250, 24)  # line-of-sight detection box
        self.alert_timer    = 0   # frames the enemy stays alert after losing sight of player

        animation_types = ["Idle", "Run", "Death"]
        for anim in animation_types:
            temp, n = [], len(os.listdir(f"assets/img/enemy/{anim}"))
            for i in range(n):
                img = pygame.image.load(f"assets/img/enemy/{anim}/{i}.png").convert_alpha()
                img = pygame.transform.scale(img, (int(img.get_width() * scale), int(img.get_height() * scale)))
                temp.append(img)
            self.animation_list.append(temp)

        self.image  = self.animation_list[self.action][self.frame_index]
        self.rect   = self.image.get_rect(center=(x, y))
        self.width  = self.image.get_width()
        self.height = self.image.get_height()

    # PATHFINDING HELPERS
    def _will_hit_wall(self, dx):
        """Check if moving dx pixels would collide with a solid tile."""
        wx = self.rect.x + state["bg_scroll"]
        wy = self.rect.y
        for (_, tx, ty) in world.obstacle_list:
            if pygame.Rect(tx, ty, TILE_SIZE, TILE_SIZE).colliderect(wx + dx, wy, self.width, self.height):
                return True
        return False

    def _ground_ahead(self, dx):
        """Check if there is a tile directly below the next step (is the ground continuous?)."""
        wx     = self.rect.x + state["bg_scroll"]
        step   = self.speed + 2
        probe_x = (wx + self.width + step - 4) if dx > 0 else (wx - step - 4)
        probe   = pygame.Rect(probe_x, self.rect.bottom + 1, 8, TILE_SIZE // 2)
        for (_, tx, ty) in world.obstacle_list:
            if pygame.Rect(tx, ty, TILE_SIZE, TILE_SIZE).colliderect(probe):
                return True
        return False

    def _should_reverse(self, dx):
        """Decide whether the enemy must turn around.
        Walls always trigger a reverse. Ledges only trigger a reverse if the drop
        has no ground below it — this lets the enemy walk down reachable steps."""
        if self.in_air:
            return False  # don't make decisions while airborne
        if self._will_hit_wall(dx):
            return True
        # Cast a deep probe below the next step; if ground exists, the drop is walkable
        drop_probe = pygame.Rect(
            self.rect.centerx + dx * 10,
            self.rect.bottom + 1,
            8, TILE_SIZE * 3   # look 3 tiles deep
        )
        wx_offset = state["bg_scroll"]
        for (_, tx, ty) in world.obstacle_list:
            if drop_probe.colliderect(pygame.Rect(tx - wx_offset, ty, TILE_SIZE, TILE_SIZE)):
                return False   # ground found below — safe to walk forward
        return not self._ground_ahead(dx)

    def _smart_move(self, dx):
        """Move in direction dx, but reverse if a wall or unrecoverable drop is detected."""
        if self._should_reverse(dx):
            self.direction    *= -1
            self.flip          = not self.flip
            self.move_counter  = 0
            return
        self.move(dx < 0, dx > 0)

    # CORE BEHAVIOUR
    def update(self):
        self.update_animation()
        self.check_alive()
        if self.shoot_cooldown > 0: self.shoot_cooldown -= 1

    def move(self, moving_left, moving_right):
        """Apply movement and gravity, resolve tile collisions."""
        dx = dy = 0
        if moving_left:  dx = -self.speed; self.flip = True;  self.direction = -1
        if moving_right: dx =  self.speed; self.flip = False; self.direction =  1

        self.vel_y = min(self.vel_y + GRAVITY, 10)
        dy += self.vel_y

        # Enemy uses world-space coords (wx) because its rect.x doesn't include bg_scroll
        landed = False
        wx = self.rect.x + state["bg_scroll"]
        wy = self.rect.y
        for (_, tx, ty) in world.obstacle_list:
            tr = pygame.Rect(tx, ty, TILE_SIZE, TILE_SIZE)
            if tr.colliderect(wx + dx, wy, self.width, self.height):
                dx = 0
            if tr.colliderect(wx, wy + dy, self.width, self.height):
                if self.vel_y < 0:
                    self.vel_y = 0; dy = tr.bottom - wy
                else:
                    self.vel_y = 0; landed = True; dy = tr.top - (wy + self.height)

        self.in_air  = not landed
        self.rect.x += dx
        self.rect.y += dy

    def shoot(self):
        """Fire a bullet toward the player if cooldown allows."""
        if self.shoot_cooldown == 0:
            self.shoot_cooldown = 45  # slower fire rate than the player (20)
            bx = self.rect.centerx + 0.75 * self.rect.width * self.direction
            bullet_group.add(Bullet(bx, self.rect.centery, self.direction,
                                    owner="enemy", damage=self.bullet_dmg))

    def _face_player(self):
        """Rotate the enemy to always face the player's current position."""
        if player.rect.centerx < self.rect.centerx:
            self.direction = -1; self.flip = True
        else:
            self.direction =  1; self.flip = False

    def ai(self):
        """
        AI state machine with three behaviours:
          - Can see player  → chase and shoot when close enough
          - Alert timer > 0 → stand still briefly after losing sight (looks more natural)
          - Otherwise       → patrol with random idle pauses and automatic direction reversal
        """
        self.rect.x += state["screen_scroll"]  # follow camera so world position stays correct
        if not self.alive or not player.alive:
            return

        # Position vision rect in front of the enemy
        self.vision.center = (self.rect.centerx + 100 * self.direction, self.rect.centery)
        can_see = self.vision.colliderect(player.rect)

        if can_see:
            self.alert_timer = 120  # stay alert for 2 seconds after losing sight
            self._face_player()
            dist = abs(self.rect.centerx - player.rect.centerx)
            if dist < TILE_SIZE * 3:
                self.update_action(0); self.shoot()   # close range: stop and shoot
            else:
                self._smart_move(self.direction * self.speed)
                self.update_action(1)                 # chase
        elif self.alert_timer > 0:
            self.alert_timer -= 1; self.update_action(0)  # stand idle while alert
        else:
            # Patrol: walk until hitting an obstacle, with occasional random pauses
            if self.idle_counter > 0:
                self.idle_counter -= 1; self.update_action(0)
            else:
                if random.randint(1, 300) == 1:
                    self.idle_counter = random.randint(30, 90)  # random pause
                else:
                    self._smart_move(self.direction * self.speed)
                    self.update_action(1)
                    self.move_counter += 1
                    if self.move_counter > TILE_SIZE * 4:   # reverse after walking ~4 tiles
                        self.direction *= -1; self.flip = not self.flip
                        self.move_counter = 0

    def update_animation(self):
        self.image = self.animation_list[self.action][self.frame_index]
        if pygame.time.get_ticks() - self.update_time > 100:
            self.update_time = pygame.time.get_ticks(); self.frame_index += 1
        if self.frame_index >= len(self.animation_list[self.action]):
            self.frame_index = len(self.animation_list[self.action]) - 1 if self.action == 2 else 0

    def update_action(self, new_action):
        if new_action != self.action:
            self.action = new_action; self.frame_index = 0
            self.update_time = pygame.time.get_ticks()

    def check_alive(self):
        if self.health <= 0:
            self.health = 0; self.speed = 0; self.alive = False
            self.update_action(2)  # switch to Death animation

    def draw(self):
        screen.blit(pygame.transform.flip(self.image, self.flip, False), self.rect)
        # Health bar — only visible after the enemy has taken at least one hit
        if self.alive and self.health < self.max_health:
            bw = 40; ratio = self.health / self.max_health
            pygame.draw.rect(screen, BLACK, (self.rect.centerx - bw//2 - 1, self.rect.top - 9, bw + 2, 7))
            pygame.draw.rect(screen, RED,   (self.rect.centerx - bw//2,     self.rect.top - 8, bw,     5))
            pygame.draw.rect(screen, GREEN, (self.rect.centerx - bw//2,     self.rect.top - 8, int(bw * ratio), 5))

# WORLD
# Reads the CSV tile map and spawns all objects at their correct world positions.
class World:
    def __init__(self):
        self.obstacle_list = []   # (img, world_x, world_y) tuples for all solid tiles
        self.level_length  = COLS

    def process_data(self, data):
        """
        Parse the tile grid and spawn all entities and objects.

        Tile index reference:
          0-2   ground surface  (shading: even / left-darker / right-darker)
          3-5   ground subsurface  (no visible top face — placed below 0-2)
          6-8   platform tiles  (floating, open underside — good for mid-air platforms)
          9-10  water  (surface + fill below)
          11    small rock  (decoration only)
          12    crate  (solid obstacle)
          13    large rock  (decoration only)
          14    grass  (decoration only)
          15    player spawn point
          16    enemy spawn point
          17    ammo box pickup
          18    grenade box pickup
          19    health box pickup
          20    level exit door
        """
        self.level_length = len(data[0])
        _player = _health_bar = None
        for y, row in enumerate(data):
            for x, tile in enumerate(row):
                if tile < 0: continue   # -1 = empty, skip
                img = img_list[tile]
                wx, wy = x * TILE_SIZE, y * TILE_SIZE
                if tile <= 8:
                    self.obstacle_list.append((img, wx, wy))  # solid tile
                elif tile == 9:  water_group.add(Water(img, wx, wy))
                elif tile == 10: water_group.add(Water(img, wx, wy))
                elif tile == 11: decoration_group.add(Decoration(img, wx, wy))
                elif tile == 12: self.obstacle_list.append((img, wx, wy))
                elif tile == 13: decoration_group.add(Decoration(img, wx, wy))
                elif tile == 14: decoration_group.add(Decoration(img, wx, wy))
                elif tile == 15:
                    _player     = Player("player", wx, wy, 1.65, 4, 20, 5)
                    _health_bar = HealthBar(10, 10, _player.health, _player.max_health)
                elif tile == 16: enemy_group.add(Enemy(wx, wy, 1.65, 2, level=state["level"]))
                elif tile == 17: item_box_group.add(ItemBox("Ammo",    wx, wy))
                elif tile == 18: item_box_group.add(ItemBox("Grenade", wx, wy))
                elif tile == 19: item_box_group.add(ItemBox("Health",  wx, wy))
                elif tile == 20: exit_group.add(Exit(img, wx, wy))
        return _player, _health_bar

    def get_tile_rects(self):
        """Return screen-space rects for all solid tiles.
        Recalculated every call so the rects always reflect the current camera position."""
        scroll = state["bg_scroll"]
        return [pygame.Rect(wx - scroll, wy, TILE_SIZE, TILE_SIZE)
                for (_, wx, wy) in self.obstacle_list]

    def draw(self):
        scroll = state["bg_scroll"]
        for (img, wx, wy) in self.obstacle_list:
            screen.blit(img, (wx - scroll, wy))

# SPRITES
# Lightweight sprite classes that just follow the camera scroll.
class _ScrollSprite(pygame.sprite.Sprite):
    """Base class for any sprite that moves with the camera each frame."""
    def __init__(self, img, x, y):
        super().__init__()
        self.image = img
        self.rect  = self.image.get_rect()
        self.rect.midtop = (x + TILE_SIZE // 2, y + (TILE_SIZE - self.image.get_height()))
    def update(self): self.rect.x += state["screen_scroll"]

class Decoration(_ScrollSprite): pass
class Water(_ScrollSprite):      pass
class Exit(_ScrollSprite):       pass

class ItemBox(pygame.sprite.Sprite):
    """Pickup box — restores health, ammo, or grenades on contact with the player."""
    def __init__(self, item_type, x, y):
        super().__init__()
        self.item_type = item_type
        self.image     = item_boxes[item_type]
        self.rect      = self.image.get_rect()
        self.rect.midtop = (x + TILE_SIZE // 2, y + (TILE_SIZE - self.image.get_height()))

    def update(self):
        self.rect.x += state["screen_scroll"]
        if pygame.sprite.collide_rect(self, player):
            if   self.item_type == "Health":  player.health = min(player.health + 30, player.max_health)
            elif self.item_type == "Ammo":    player.ammo      += 15
            elif self.item_type == "Grenade": player.grenades  += 3
            self.kill()  # remove the box after pickup

class HealthBar:
    """Animated health bar drawn in the top-left corner.
    Uses lerp so the bar shrinks smoothly instead of jumping instantly."""
    def __init__(self, x, y, health, max_health):
        self.x = x; self.y = y; self.max_health = max_health
        self.disp = float(health)  # display value, interpolated toward actual health

    def draw(self, health):
        self.disp += (health - self.disp) * 0.12  # lerp toward actual value
        ratio = max(0, self.disp / self.max_health)
        pygame.draw.rect(screen, BLACK, (self.x - 2, self.y - 2, 154, 24))
        pygame.draw.rect(screen, RED,   (self.x,     self.y,     150, 20))
        pygame.draw.rect(screen, GREEN, (self.x,     self.y,     int(150 * ratio), 20))
        draw_text(f"{round(self.disp)}", font_small, WHITE, self.x + 155, self.y + 2)

# BULLET
# Fired by both the player and enemies. Damage amount is set at spawn time.
class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, direction, owner="player", damage=20):
        super().__init__()
        self.speed     = 10
        self.owner     = owner   # "player" or "enemy" — determines what it can hit
        self.damage    = damage
        self.image     = bullet_img
        self.rect      = self.image.get_rect(center=(x, y))
        self.direction = direction

    def update(self):
        # Move horizontally and compensate for camera scroll so bullet tracks world position
        self.rect.x += self.direction * self.speed + state["screen_scroll"]
        if self.rect.right < 0 or self.rect.left > SCREEN_WIDTH: self.kill(); return
        for tr in world.get_tile_rects():
            if tr.colliderect(self.rect): self.kill(); return  # destroy on tile hit

        if self.owner == "enemy":
            if self.rect.colliderect(player.rect) and player.alive:
                player.take_damage(self.damage)
                self.kill()
        else:
            for enemy in enemy_group:
                if self.rect.colliderect(enemy.rect) and enemy.alive:
                    was_alive = enemy.health > 0
                    enemy.health -= self.damage
                    damage_text_group.add(DamageText(enemy.rect.centerx, enemy.rect.top,
                                                     str(self.damage), YELLOW))
                    if was_alive and enemy.health <= 0:
                        state["score"] += 100
                        state["kills"] += 1
                        add_kill_feed("Enemy killed! +100", ORANGE)
                    self.kill(); return

# GRENADE
# Thrown by the player; bounces off walls and floors, then explodes after a short fuse.
class Grenade(pygame.sprite.Sprite):
    def __init__(self, x, y, direction):
        super().__init__()
        self.timer     = 100   # frames until detonation
        self.vel_y     = -11
        self.speed     = 7
        self.image     = grenade_img
        self.rect      = self.image.get_rect(center=(x, y))
        self.width     = self.image.get_width()
        self.height    = self.image.get_height()
        self.direction = direction

    def update(self):
        self.vel_y = min(self.vel_y + GRAVITY, 10)
        dx = self.direction * self.speed; dy = self.vel_y
        for tr in world.get_tile_rects():
            if tr.colliderect(self.rect.x + dx, self.rect.y, self.width, self.height):
                self.direction *= -1; dx = self.direction * self.speed  # bounce off wall
            if tr.colliderect(self.rect.x, self.rect.y + dy, self.width, self.height):
                self.speed = 0  # stop rolling on floor impact
                if self.vel_y < 0: self.vel_y = 0; dy = tr.bottom - self.rect.top
                else:              self.vel_y = 0; dy = tr.top - self.rect.bottom
        self.rect.x += dx + state["screen_scroll"]
        self.rect.y += dy
        self.timer -= 1

        if self.timer <= 0:
            self.kill(); grenade_fx.play()
            explosion_group.add(Explosion(self.rect.x, self.rect.y, 0.5))
            # Deal 50 damage to everything within a 2-tile blast radius
            if abs(self.rect.centerx - player.rect.centerx) < TILE_SIZE * 2 and \
               abs(self.rect.centery - player.rect.centery) < TILE_SIZE * 2:
                player.take_damage(50)
            for enemy in enemy_group:
                if abs(self.rect.centerx - enemy.rect.centerx) < TILE_SIZE * 2 and \
                   abs(self.rect.centery - enemy.rect.centery) < TILE_SIZE * 2:
                    was_alive = enemy.health > 0
                    enemy.health -= 50
                    damage_text_group.add(DamageText(enemy.rect.centerx, enemy.rect.top, "50", YELLOW))
                    if was_alive and enemy.health <= 0:
                        state["score"] += 100; state["kills"] += 1
                        add_kill_feed("Enemy killed! +100", ORANGE)

# EXPLOSION
# Frame-based animation spawned at the grenade's impact point.
class Explosion(pygame.sprite.Sprite):
    def __init__(self, x, y, scale):
        super().__init__()
        self.images = []
        for n in range(1, 6):
            img = pygame.image.load(f"assets/img/explosion/exp{n}.png").convert_alpha()
            img = pygame.transform.scale(img, (int(img.get_width() * scale), int(img.get_height() * scale)))
            self.images.append(img)
        self.frame_index = 0
        self.image   = self.images[0]
        self.rect    = self.image.get_rect(center=(x, y))
        self.counter = 0  # sub-frame counter so animation runs slower than 60 fps

    def update(self):
        self.rect.x += state["screen_scroll"]
        self.counter += 1
        if self.counter >= 4:  # advance one frame every 4 game frames (~15 fps)
            self.counter = 0; self.frame_index += 1
            if self.frame_index >= len(self.images): self.kill()
            else: self.image = self.images[self.frame_index]

# SCREEN FADE
# Used for the level intro wipe-in (direction 1) and the death blackout (direction 2).
class ScreenFade:
    def __init__(self, direction, colour, speed):
        self.direction    = direction   # 1 = horizontal split, 2 = vertical wipe down
        self.colour       = colour
        self.speed        = speed       # pixels of fade progress per frame
        self.fade_counter = 0

    def fade(self):
        """Draw the fade overlay and return True when the fade is complete."""
        self.fade_counter += self.speed
        has_alpha = len(self.colour) == 4

        if self.direction == 1:  # two panels slide in from both sides
            for rect in [
                (0 - self.fade_counter, 0, SCREEN_WIDTH // 2, SCREEN_HEIGHT),
                (SCREEN_WIDTH // 2 + self.fade_counter, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
            ]:
                if has_alpha:
                    s = pygame.Surface((abs(rect[2]), rect[3]), pygame.SRCALPHA)
                    s.fill(self.colour); screen.blit(s, (rect[0], rect[1]))
                else:
                    pygame.draw.rect(screen, self.colour, rect)

        elif self.direction == 2:  # single panel wipes down from the top
            h = int(self.fade_counter)
            if has_alpha:
                s = pygame.Surface((SCREEN_WIDTH, h), pygame.SRCALPHA)
                s.fill(self.colour); screen.blit(s, (0, 0))
            else:
                pygame.draw.rect(screen, self.colour, (0, 0, SCREEN_WIDTH, h))

        return self.fade_counter >= SCREEN_HEIGHT  # True = fade finished

# PAUSE SCREEN
# Semi-transparent overlay with resume / music toggle / exit buttons.
def draw_pause_screen():
    # Smoothly fade the overlay in rather than snapping to full opacity
    state["pause_alpha"] = min(state["pause_alpha"] + 18, 200)
    alpha = state["pause_alpha"]

    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, alpha))
    screen.blit(overlay, (0, 0))

    # Don't render buttons until the overlay is mostly opaque (avoids clicking through during fade)
    if alpha < 120:
        return None

    pw, ph = 280, 230
    cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
    panel  = pygame.Surface((pw, ph), pygame.SRCALPHA)
    panel.fill((20, 20, 40, min(alpha + 30, 240)))
    pygame.draw.rect(panel, CYAN, (0, 0, pw, ph), 2, border_radius=14)
    screen.blit(panel, (cx - pw//2, cy - ph//2))

    draw_text_centered("PAUSED", font_med, CYAN, cy - ph//2 + 20)
    pygame.draw.line(screen, (80, 80, 120),
                     (cx - pw//2 + 20, cy - ph//2 + 58),
                     (cx + pw//2 - 20, cy - ph//2 + 58), 1)

    music_label = "Music: ON" if state["music_on"] else "Music: OFF"
    btns = [
        ("Resume",       (35, 100, 35)),
        (music_label,    (60, 60, 110)),
        ("Back to Home", (80, 50, 100)),
    ]
    bw, bh = 220, 40
    gap    = 12
    by0    = cy - ph//2 + 72
    action = None
    for i, (label, colour) in enumerate(btns):
        bx = cx - bw // 2
        by = by0 + i * (bh + gap)
        mx, my = pygame.mouse.get_pos()
        hovering = bx <= mx <= bx + bw and by <= my <= by + bh
        draw_col = tuple(min(c + 30, 255) for c in colour) if hovering else colour
        pygame.draw.rect(screen, draw_col, (bx, by, bw, bh), border_radius=8)
        pygame.draw.rect(screen, (100, 100, 140), (bx, by, bw, bh), 1, border_radius=8)
        ls = font_small.render(label, True, WHITE)
        screen.blit(ls, (bx + bw//2 - ls.get_width()//2, by + bh//2 - ls.get_height()//2))
        if _btn_click(bx, by, bw, bh):
            action = label
    return action

# HOME SCREEN
# Animated title screen with gradient sky, twinkling stars, parallax silhouettes,
# rising particles, a drop-in title, and a control-hint card.
class HomeScreen:
    def __init__(self):
        self.bg_scroll  = 0.0
        self.star_timer = 0
        self.stars      = [(random.randint(0, SCREEN_WIDTH),
                            random.randint(0, SCREEN_HEIGHT // 2),
                            random.uniform(0.3, 1.0))
                           for _ in range(60)]
        self.particles    = []
        self.title_y      = -80   # starts above the screen and drops into position
        self.title_vy     = 0.0
        self.alpha_in     = 0     # controls fade-in of buttons and hints
        self._spawn_timer = 0

    def _draw_bg(self):
        """Gradient sky strips + scrolling silhouettes + twinkling stars."""
        sky_colours = [
            (8,  12,  40),
            (18, 25,  70),
            (30, 45, 100),
            (50, 80, 130),
        ]
        strip_h = SCREEN_HEIGHT // len(sky_colours)
        for i, col in enumerate(sky_colours):
            pygame.draw.rect(screen, col, (0, i * strip_h, SCREEN_WIDTH, strip_h + 2))

        # Flicker each star based on a sine-like pattern and its own brightness seed
        self.star_timer += 1
        for (sx, sy, brightness) in self.stars:
            flicker = brightness * (0.6 + 0.4 * abs(
                (self.star_timer * 0.03 + sx * 0.1) % 2 - 1))
            c = int(200 * flicker)
            r = 2 if brightness > 0.7 else 1
            pygame.draw.circle(screen, (c, c, min(c + 40, 255)), (sx, sy), r)

        s = self.bg_scroll
        w = sky_img.get_width()
        for x in range(5):
            screen.blit(mountain_img, ((x * w) - s * 0.3,
                        SCREEN_HEIGHT - mountain_img.get_height() - 160))
            screen.blit(pine1_img,    ((x * w) - s * 0.5,
                        SCREEN_HEIGHT - pine1_img.get_height() - 60))
            screen.blit(pine2_img,    ((x * w) - s * 0.7,
                        SCREEN_HEIGHT - pine2_img.get_height()))

        pygame.draw.rect(screen, (15, 30, 15),  (0, SCREEN_HEIGHT - 36, SCREEN_WIDTH, 36))
        pygame.draw.rect(screen, (25, 55, 25),  (0, SCREEN_HEIGHT - 38, SCREEN_WIDTH,  4))

        self.bg_scroll += 0.4   # scroll slowly to the right each frame
        if self.bg_scroll > sky_img.get_width():
            self.bg_scroll = 0.0

    def _spawn_particle(self):
        """Spawn a small glowing dot that rises from the ground line."""
        x = random.randint(60, SCREEN_WIDTH - 60)
        y = SCREEN_HEIGHT - 36
        self.particles.append([
            x, y,
            random.uniform(-0.6, 0.6),   # horizontal drift
            random.uniform(-2.5, -0.8),  # upward velocity
            0,                           # age (frames)
            random.randint(50, 100),     # lifetime (frames)
            random.randint(2, 4),        # radius
            random.choice([(200, 230, 100), (100, 220, 160), (255, 200, 80)])
        ])

    def _update_particles(self):
        self._spawn_timer += 1
        if self._spawn_timer >= 4:   # spawn one particle every 4 frames
            self._spawn_timer = 0
            self._spawn_particle()
        for p in self.particles[:]:
            p[0] += p[2]; p[1] += p[3]; p[4] += 1
            if p[4] >= p[5]:
                self.particles.remove(p); continue
            ratio      = 1 - p[4] / p[5]
            alpha_surf = pygame.Surface((p[6]*2, p[6]*2), pygame.SRCALPHA)
            pygame.draw.circle(alpha_surf, (*p[7], int(180 * ratio)), (p[6], p[6]), p[6])
            screen.blit(alpha_surf, (int(p[0] - p[6]), int(p[1] - p[6])))

    def _update_title(self):
        """Ease the title down from above the screen with a dampened bounce."""
        target_y = 130
        if self.title_y < target_y:
            self.title_vy += 0.8          # accelerate downward
            self.title_y   = min(self.title_y + self.title_vy, target_y)
            self.title_vy *= 0.85         # dampen velocity for a soft landing
        else:
            self.title_y = target_y
        if self.title_y >= target_y - 20:
            self.alpha_in = min(self.alpha_in + 5, 255)  # start fading in UI elements

    def _draw_title(self):
        """Render the game title with a black outline for readability."""
        title = "LAST MAN"
        sub   = "STANDING"
        for ox, oy in [(-3,0),(3,0),(0,-3),(0,3)]:  # 4-direction outline
            s = font_title.render(title, True, (0, 0, 0))
            screen.blit(s, (SCREEN_WIDTH//2 - s.get_width()//2 + ox, self.title_y + oy))
        s = font_title.render(title, True, (255, 230, 60))
        screen.blit(s, (SCREEN_WIDTH//2 - s.get_width()//2, self.title_y))

        for ox, oy in [(-2,0),(2,0),(0,-2),(0,2)]:
            s2 = font_title.render(sub, True, (0, 0, 0))
            screen.blit(s2, (SCREEN_WIDTH//2 - s2.get_width()//2 + ox, self.title_y + 76 + oy))
        s2 = font_title.render(sub, True, (255, 100, 50))
        screen.blit(s2, (SCREEN_WIDTH//2 - s2.get_width()//2, self.title_y + 76))

    def _draw_hint(self):
        """Control reference card — fades in after the title animation settles."""
        if self.alpha_in < 80:
            return
        hints = [
            ("Move",    "A / D  or  ← →"),
            ("Jump",    "W / ↑  (double jump)"),
            ("Shoot",   "Space"),
            ("Grenade", "Q"),
            ("Pause",   "P"),
        ]
        x0 = SCREEN_WIDTH // 2 - 180
        y0 = 460
        h  = len(hints) * 22 + 18
        surf = pygame.Surface((375, h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 100))
        screen.blit(surf, (x0 - 8, y0 - 8))
        pygame.draw.rect(screen, (80, 120, 80), (x0 - 8, y0 - 8, 376, h), 1, border_radius=6)
        for i, (action, key) in enumerate(hints):
            a_surf = font_hint.render(action, True, (160, 200, 160))
            k_surf = font_hint.render(key,    True, WHITE)
            a_surf.set_alpha(self.alpha_in)
            k_surf.set_alpha(self.alpha_in)
            screen.blit(a_surf, (x0 + 4, y0 + i * 22 - 2))
            right_edge = x0 + 352
            screen.blit(k_surf, (right_edge - k_surf.get_width(), y0 + i * 22 - 2))

    def _draw_badge(self):
        """Small version + level count badge at the bottom of the screen."""
        v = font_hint.render("v1.0  |  3 Levels", True, (120, 160, 120))
        v.set_alpha(self.alpha_in)
        screen.blit(v, (SCREEN_WIDTH // 2 - v.get_width() // 2, SCREEN_HEIGHT - 28))

    def draw(self, start_btn, exit_btn):
        self._draw_bg()
        self._update_particles()
        self._update_title()
        self._draw_title()

        sw = start_btn.image.get_width()
        sh = start_btn.image.get_height()
        ew = exit_btn.image.get_width()

        btn_start_y = 280
        btn_exit_y  = btn_start_y + sh + 10

        start_btn.image.set_alpha(self.alpha_in)   # fade buttons in with the rest of the UI
        exit_btn.image.set_alpha(self.alpha_in)
        start_btn.rect.topleft = (SCREEN_WIDTH // 2 - sw // 2, btn_start_y)
        exit_btn.rect.topleft  = (SCREEN_WIDTH // 2 - ew // 2, btn_exit_y)

        action = None
        if start_btn.draw(screen): action = "start"
        if exit_btn.draw(screen):  action = "exit"

        self._draw_hint()
        self._draw_badge()
        return action

# SETUP
# Create all objects and load level 1 before entering the main loop.
intro_fade   = ScreenFade(1, BLACK, 4)    # horizontal split wipe at level start
death_fade   = ScreenFade(2, DEATH_BG, 6) # vertical dark wipe when player dies
death_screen = DeathScreen()

home_screen  = HomeScreen()
start_button = button.Button(0, 0, start_img, 0.7)
exit_button  = button.Button(0, 0, exit_img,  0.7)

# Sprite groups — one group per object type for easy batch update/draw/clear
enemy_group       = pygame.sprite.Group()
bullet_group      = pygame.sprite.Group()
grenade_group     = pygame.sprite.Group()
explosion_group   = pygame.sprite.Group()
item_box_group    = pygame.sprite.Group()
decoration_group  = pygame.sprite.Group()
water_group       = pygame.sprite.Group()
exit_group        = pygame.sprite.Group()
damage_text_group = pygame.sprite.Group()
kill_feed_group   = pygame.sprite.Group()

# Load the first level from its CSV file
world_data = reset_level()
with open(f'assets/level{state["level"]}_data.csv', newline='') as csvfile:
    for x, row in enumerate(csv.reader(csvfile)):
        if x >= ROWS: break
        for y, tile in enumerate(row):
            if y >= COLS: break
            world_data[x][y] = int(tile)
world = World()
player, health_bar = world.process_data(world_data)

def load_level(lvl):
    """Clear the current level and rebuild the world from a new CSV file."""
    global world, player, health_bar
    wd = reset_level()
    with open(f"assets/level{lvl}_data.csv", newline='') as f:
        for x, row in enumerate(csv.reader(f)):
            if x >= ROWS: break
            for y, tile in enumerate(row):
                if y >= COLS: break
                wd[x][y] = int(tile)
    world = World()
    player, health_bar = world.process_data(wd)

# MAIN LOOP
run = True
while run:
    clock.tick(FPS)  # cap the loop at FPS; also returns ms since last call

    # MENU
    if not state["start_game"]:
        action = home_screen.draw(start_button, exit_button)
        if action == "start":
            state["start_game"]  = True
            state["start_intro"] = True
            state["last_tick"]   = pygame.time.get_ticks()

    # GAMEPLAY
    else:
        draw_bg()
        world.draw()

        # HUD — health bar, ammo icons, grenade icons, level/score/time
        health_bar.draw(player.health)
        draw_text("AMMO: ",     font, WHITE, 10, 35)
        for x in range(player.ammo):
            screen.blit(bullet_img, (90 + x * 10, 40))   # one icon per bullet
        draw_text("GRENADES: ", font, WHITE, 10, 60)
        for x in range(player.grenades):
            screen.blit(grenade_img, (135 + x * 15, 60)) # one icon per grenade
        draw_hud()

        if not state["show_death_screen"]:
            if draw_pause_button():
                state["paused"] = not state["paused"]

        if not state["paused"] and not state["show_death_screen"]:
            # Advance survive timer only while the player is alive
            now = pygame.time.get_ticks()
            if state["last_tick"] > 0 and player.alive:
                state["survive_ms"] += now - state["last_tick"]
            state["last_tick"] = now
            player.update()
        player.draw()

        for enemy in enemy_group:
            if not state["paused"] and not state["show_death_screen"]:
                enemy.ai(); enemy.update()
            enemy.draw()

        # Update and draw all remaining sprite groups
        all_groups = (bullet_group, grenade_group, explosion_group, item_box_group,
                      decoration_group, water_group, exit_group,
                      damage_text_group, kill_feed_group)
        for grp in all_groups:
            if not state["paused"] and not state["show_death_screen"]:
                grp.update()
            grp.draw(screen)

        # Level intro wipe — plays every time a new level is loaded
        if state["start_intro"]:
            if intro_fade.fade():
                state["start_intro"] = False; intro_fade.fade_counter = 0

        if not state["paused"] and not state["show_death_screen"]:
            if player.alive:
                # Handle player actions for this frame
                if state["shoot"]:
                    player.shoot()
                elif state["grenade"] and not state["grenade_thrown"] and player.grenades > 0:
                    grenade_group.add(Grenade(
                        player.rect.centerx + 0.5 * player.rect.width * player.direction,
                        player.rect.top, player.direction))
                    player.grenades -= 1; state["grenade_thrown"] = True

                # Pick animation based on movement state (priority: jump > run > idle)
                if player.in_air:
                    player.update_action(2)
                elif state["moving_left"] or state["moving_right"]:
                    player.update_action(1)
                else:
                    player.update_action(0)

                scroll, level_complete = player.move(state["moving_left"], state["moving_right"])
                state["screen_scroll"] = scroll       # shift all sprites by this amount
                state["bg_scroll"]    -= scroll       # move the camera in the opposite direction

                if level_complete:
                    intro_fade.fade_counter = 0; state["start_intro"] = True
                    state["level"] += 1; state["bg_scroll"] = 0
                    if state["level"] <= MAX_LEVELS:
                        load_level(state["level"])
                    else:
                        # Player has cleared all levels — show the win screen
                        state["show_death_screen"] = True
                        death_screen.show(win=True)
            else:
                state["screen_scroll"] = 0  # stop scrolling when dead
                # Wait for the death animation to finish before starting the fade
                death_anim_done = (player.frame_index >= len(player.animation_list[3]) - 1)
                if death_anim_done:
                    if not state["show_death_screen"]:
                        if death_fade.fade():   # returns True when fade is complete
                            state["show_death_screen"] = True
                            death_screen.show(win=False)

        # PAUSE OVERLAY
        if state["paused"]:
            pause_action = draw_pause_screen()
            if pause_action == "Resume":
                state["paused"]      = False
                state["pause_alpha"] = 0   # reset so the overlay fades in again next time
            elif pause_action in ("Music: ON", "Music: OFF"):
                state["music_on"] = not state["music_on"]
                if state["music_on"]: pygame.mixer.music.unpause()
                else:                 pygame.mixer.music.pause()
            elif pause_action == "Back to Home":
                state.update({"start_game": False, "paused": False, "pause_alpha": 0,
                              "level": 1, "score": 0, "kills": 0, "shots_fired": 0,
                              "damage_taken": 0, "survive_ms": 0, "bg_scroll": 0,
                              "screen_scroll": 0, "show_death_screen": False})
                load_level(1)

        # DEATH / WIN OVERLAY
        if state["show_death_screen"]:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill(DEATH_BG)
            screen.blit(overlay, (0, 0))
            action = death_screen.draw()
            if action == "restart_level":
                death_fade.fade_counter = 0; intro_fade.fade_counter = 0
                state.update({"start_intro": True, "bg_scroll": 0,
                              "show_death_screen": False, "screen_scroll": 0,
                              "last_tick": pygame.time.get_ticks()})
                death_screen.visible = False
                load_level(state["level"])
            elif action == "restart_from_start":
                # Reset all stats and reload from level 1
                death_fade.fade_counter = 0; intro_fade.fade_counter = 0
                state.update({"level": 1, "score": 0, "kills": 0,
                              "shots_fired": 0, "damage_taken": 0,
                              "survive_ms": 0, "last_tick": pygame.time.get_ticks(),
                              "start_intro": True, "bg_scroll": 0,
                              "show_death_screen": False, "screen_scroll": 0})
                death_screen.visible = False
                load_level(1)
            elif action == "home":
                death_fade.fade_counter = 0; intro_fade.fade_counter = 0
                death_screen.visible = False
                state.update({"start_game": False, "paused": False, "pause_alpha": 0,
                              "level": 1, "score": 0, "kills": 0, "shots_fired": 0,
                              "damage_taken": 0, "survive_ms": 0, "bg_scroll": 0,
                              "screen_scroll": 0, "show_death_screen": False})
                load_level(1)

    # EVENT HANDLING
    state["mouse_clicked"] = False  # reset single-frame flag at the start of each event pass

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            state["mouse_clicked"] = True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_a, pygame.K_LEFT):  state["moving_left"]  = True
            if event.key in (pygame.K_d, pygame.K_RIGHT): state["moving_right"] = True
            if event.key == pygame.K_SPACE:                state["shoot"]        = True
            if event.key == pygame.K_q:                    state["grenade"]      = True
            if event.key == pygame.K_p and not state["show_death_screen"]:
                state["paused"]      = not state["paused"]
                state["pause_alpha"] = 0
            if event.key in (pygame.K_w, pygame.K_UP) and player.alive and not state["show_death_screen"]:
                if player.jumps_left > 0:
                    player.jump = True; jump_fx.play()
            if event.key == pygame.K_ESCAPE:
                run = False
        if event.type == pygame.KEYUP:
            if event.key in (pygame.K_a, pygame.K_LEFT):  state["moving_left"]  = False
            if event.key in (pygame.K_d, pygame.K_RIGHT): state["moving_right"] = False
            if event.key == pygame.K_SPACE:                state["shoot"]        = False
            if event.key == pygame.K_q:
                state["grenade"] = False; state["grenade_thrown"] = False

    pygame.display.update()

pygame.quit()